"""
Section-aware chunking for the regulatory corpus.

Regulations are already structured into clauses, so the natural chunk boundary
is the clause itself, not an arbitrary token window. Each clause becomes one
chunk that carries its full metadata (regulation, clause ref, governing
violation types, source URI). This keeps every retrievable unit independently
citable — a retrieved chunk always knows exactly which regulation and clause it
came from, which is what makes grounded citation possible.

For clauses whose body exceeds the target size, the text is split on sentence
boundaries into overlapping sub-chunks that each inherit the parent clause's
metadata, so citation integrity survives the split.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Target chunk size in characters. Regulatory clauses are short, so most
# clauses fit in a single chunk; this only triggers sub-splitting for long ones.
TARGET_CHARS = 900
OVERLAP_CHARS = 150


@dataclass
class Chunk:
    """One retrievable, independently-citable unit."""

    id: str
    regulation: str
    clause: str
    title: str
    content: str
    violation_types: list[str] = field(default_factory=list)
    source_uri: str = ""

    def to_search_document(self, vector: list[float]) -> dict:
        """Shape for upload into the Azure AI Search index.

        Azure Search document keys may only contain letters, digits, underscore,
        dash, or equals. Clause ids like 'oshad-sf38-5.4' contain dots, so the
        key is sanitized (dots -> underscore) while the original clause reference
        is preserved in the 'clause' field for citation.
        """
        safe_key = self.id.replace(".", "_")
        return {
            "id": safe_key,
            "regulation": self.regulation,
            "clause": self.clause,
            "title": self.title,
            "content": self.content,
            "violation_types": self.violation_types,
            "source_uri": self.source_uri,
            "contentVector": vector,
        }


def _split_sentences(text: str) -> list[str]:
    # Lightweight sentence split — regulatory text is well-punctuated.
    parts = re.split(r"(?<=[.;])\s+", text.strip())
    return [p for p in parts if p]


def _sub_chunk(text: str, target: int, overlap: int) -> list[str]:
    """Split an over-long clause into overlapping sentence-aligned windows."""
    sentences = _split_sentences(text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > target:
            chunks.append(current.strip())
            # Start next window with a tail overlap for context continuity.
            current = (current[-overlap:] + " " + sentence).strip()
        else:
            current = (current + " " + sentence).strip()
    if current:
        chunks.append(current.strip())
    return chunks


def chunk_corpus(
    corpus_path: str | Path,
    target_chars: int = TARGET_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[Chunk]:
    """Turn the clause corpus into a list of citable chunks."""
    raw = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    chunks: list[Chunk] = []

    for clause in raw["clauses"]:
        body = clause["text"]
        if len(body) <= target_chars:
            chunks.append(
                Chunk(
                    id=clause["id"],
                    regulation=clause["regulation"],
                    clause=clause["clause"],
                    title=clause["title"],
                    content=body,
                    violation_types=clause["violation_types"],
                    source_uri=clause["source_uri"],
                )
            )
        else:
            for i, piece in enumerate(_sub_chunk(body, target_chars, overlap_chars)):
                chunks.append(
                    Chunk(
                        id=f"{clause['id']}--{i}",
                        regulation=clause["regulation"],
                        clause=clause["clause"],
                        title=clause["title"],
                        content=piece,
                        violation_types=clause["violation_types"],
                        source_uri=clause["source_uri"],
                    )
                )

    return chunks
