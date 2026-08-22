"""
Build the compliance RAG index end-to-end, live against Azure.

Run once to stand up the full pipeline:
  1. create (or update) the HNSW + BM25 hybrid index
  2. chunk the corpus (section-aware)
  3. embed each chunk with text-embedding-3-large
  4. upload the vectorized chunks
  5. run a sample hybrid query to prove retrieval works

Usage:
  python -m scripts.build_rag_index

Reads config from environment (.env):
  AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY
  AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY
"""

from __future__ import annotations

import os
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv

from src.rag.azure_retriever import AzureSearchRetriever
from src.rag.chunking import chunk_corpus
from src.rag.embedding import Embedder
from src.rag.index_schema import create_index

INDEX_NAME = "safewatch-regulations"
CORPUS = Path("data/regulations/sample_corpus.json")


def main() -> None:
    load_dotenv()

    search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    search_key = os.environ["AZURE_SEARCH_API_KEY"]

    print("1. Creating index...")
    create_index(search_endpoint, search_key, INDEX_NAME)

    print("2. Chunking corpus...")
    chunks = chunk_corpus(CORPUS)
    print(f"   {len(chunks)} chunks")

    print("3. Embedding chunks...")
    embedder = Embedder()
    texts = [f"{c.title}. {c.content}" for c in chunks]
    vectors = embedder.embed_batch(texts)

    print("4. Uploading...")
    docs = [c.to_search_document(v) for c, v in zip(chunks, vectors, strict=True)]
    client = SearchClient(
        endpoint=search_endpoint,
        index_name=INDEX_NAME,
        credential=AzureKeyCredential(search_key),
    )
    result = client.upload_documents(documents=docs)
    print(f"   uploaded {sum(1 for r in result if r.succeeded)}/{len(docs)}")

    print("5. Test hybrid query (missing_harness)...")
    retriever = AzureSearchRetriever(
        endpoint=search_endpoint,
        api_key=search_key,
        index_name=INDEX_NAME,
        embedder=embedder,
    )
    hits = retriever.retrieve("missing_harness")
    for h in hits:
        print(f"   [{h['score']:.3f}] {h['regulation']} {h['clause']} - {h['title']}")

    print("\nDone. Full RAG pipeline is live.")


if __name__ == "__main__":
    main()
