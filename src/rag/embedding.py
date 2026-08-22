"""
Embedding client for Azure OpenAI text-embedding-3-large.

Wraps the embeddings endpoint with retry/backoff so transient throttling
doesn't fail an indexing run. Used both at index time (embedding chunks) and
query time (embedding the search query), so the same model produces both
sides of the vector comparison.
"""

from __future__ import annotations

import os

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

EMBEDDING_DEPLOYMENT = "text-embedding-3-large"
API_VERSION = "2024-10-21"


def _build_client() -> AzureOpenAI:
    """
    Prefer Managed Identity / Entra ID auth; fall back to key auth for local dev.

    In deployed environments (Container Apps) DefaultAzureCredential resolves to
    the managed identity — no key in the environment. Locally, if a key is set,
    key auth is used. This is the seam that lets the security work (Managed
    Identity) drop in without changing calling code.
    """
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")

    if api_key:
        return AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=API_VERSION,
        )

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    return AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=API_VERSION,
    )


class Embedder:
    def __init__(self) -> None:
        self._client = _build_client()

    @retry(
        stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30)
    )
    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(
            model=EMBEDDING_DEPLOYMENT,
            input=text,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # The embeddings API accepts a list; one call for the whole batch.
        response = self._client.embeddings.create(
            model=EMBEDDING_DEPLOYMENT,
            input=texts,
        )
        return [item.embedding for item in response.data]
