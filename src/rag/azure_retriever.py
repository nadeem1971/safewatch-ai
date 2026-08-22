"""
Azure AI Search hybrid retriever.

Implements the same ClauseRetriever protocol as InMemoryRetriever, so the
ComplianceRAGAgent consumes it without any change. This is the "full RAG"
retrieval half:

  - keyword BM25 search over the text fields
  - vector search over the HNSW-indexed contentVector
  - both fused server-side by Azure via Reciprocal Rank Fusion (RRF)
  - optional pre-filter on violation_types to narrow the vector space
  - top-k results (default 5)

The agent still decides grounding and citation. The retriever only fetches;
it never generates.
"""

from __future__ import annotations

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from src.rag.embedding import Embedder

TOP_K = 5


class AzureSearchRetriever:
    """Hybrid (BM25 + vector) retriever over the compliance index."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        index_name: str,
        embedder: Embedder | None = None,
        top_k: int = TOP_K,
    ) -> None:
        self._client = SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=AzureKeyCredential(api_key),
        )
        self._embedder = embedder or Embedder()
        self._top_k = top_k

    def retrieve(self, violation_type: str) -> list[dict]:
        """
        Hybrid-retrieve clauses relevant to a violation type.

        The query text is the violation type expressed as natural language, so
        BM25 has keyword signal; the same text is embedded for the vector arm.
        A filter on violation_types pre-narrows the candidate set.
        """
        query_text = violation_type.replace("_", " ")
        query_vector = self._embedder.embed(query_text)

        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=self._top_k,
            fields="contentVector",
        )

        results = self._client.search(
            search_text=query_text,  # BM25 arm
            vector_queries=[vector_query],  # vector arm; fused by RRF
            filter=f"violation_types/any(v: v eq '{violation_type}')",
            select=["id", "regulation", "clause", "title", "content", "source_uri"],
            top=self._top_k,
        )

        out: list[dict] = []
        for r in results:
            out.append(
                {
                    "id": r["id"],
                    "regulation": r["regulation"],
                    "clause": r["clause"],
                    "title": r["title"],
                    "text": r["content"],
                    "source_uri": r["source_uri"],
                    "violation_types": [violation_type],
                    "score": r.get("@search.score", 0.0),
                }
            )
        return out
