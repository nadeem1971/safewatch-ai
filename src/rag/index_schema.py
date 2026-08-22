"""
Azure AI Search index definition for the compliance corpus.

Creates an index with:
  - text fields (regulation, clause, title, content) searchable via BM25
  - a vector field (contentVector) backed by an HNSW graph, cosine metric
  - filterable metadata (violation_types) for pre-filtering
  - a semantic configuration for optional semantic reranking

This is the schema half of "full RAG": keyword (BM25) + vector (HNSW) in one
index, which is what lets a single query run hybrid retrieval with Reciprocal
Rank Fusion server-side.
"""

from __future__ import annotations

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

# text-embedding-3-large produces 3072-dimensional vectors.
EMBEDDING_DIMENSIONS = 3072
HNSW_CONFIG_NAME = "safewatch-hnsw"
VECTOR_PROFILE_NAME = "safewatch-vector-profile"
SEMANTIC_CONFIG_NAME = "safewatch-semantic"


def build_index(index_name: str) -> SearchIndex:
    """Construct the SearchIndex definition (does not create it remotely)."""
    fields = [
        SimpleField(
            name="id", type=SearchFieldDataType.String, key=True, filterable=True
        ),
        SearchableField(
            name="regulation", type=SearchFieldDataType.String, filterable=True
        ),
        SearchableField(
            name="clause", type=SearchFieldDataType.String, filterable=True
        ),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="violation_types",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
            facetable=True,
        ),
        SimpleField(name="source_uri", type=SearchFieldDataType.String),
        SearchField(
            name="contentVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name=VECTOR_PROFILE_NAME,
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name=HNSW_CONFIG_NAME,
                parameters=HnswParameters(
                    m=4,
                    ef_construction=400,
                    ef_search=500,
                    metric="cosine",
                ),
            )
        ],
        profiles=[
            VectorSearchProfile(
                name=VECTOR_PROFILE_NAME,
                algorithm_configuration_name=HNSW_CONFIG_NAME,
            )
        ],
    )

    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=SEMANTIC_CONFIG_NAME,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="regulation")],
                ),
            )
        ]
    )

    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )


def create_index(endpoint: str, api_key: str, index_name: str) -> None:
    """Create or update the index on the live Azure AI Search service."""
    client = SearchIndexClient(
        endpoint=endpoint, credential=AzureKeyCredential(api_key)
    )
    index = build_index(index_name)
    result = client.create_or_update_index(index)
    print(f"Index ready: {result.name}")
