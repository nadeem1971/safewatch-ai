"""
Compliance RAG Agent.

Given a detected violation type, retrieves the governing regulation clause
from the corpus and returns a grounded RegulationCitation.

Grounding rule: this agent NEVER invents a regulation. If retrieval finds no
governing clause, it returns None. Every field in a returned citation traces
to a real entry in the corpus. This is the property that makes the agent's
output defensible to an auditor.

Retrieval strategy is pluggable. v1 ships a deterministic in-memory retriever
so the pipeline is testable without Azure. A vector-backed retriever against
Azure AI Search implements the same protocol and swaps in without changing the
agent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from src.contracts import RegulationCitation, ViolationType


class ClauseRetriever(Protocol):
    """Anything that can return candidate clauses for a violation type."""

    def retrieve(self, violation_type: ViolationType) -> list[dict]: ...


class InMemoryRetriever:
    """
    Deterministic retriever over the local corpus.

    Loads clauses once, indexes them by the violation types they govern.
    No network, no embeddings — used for development and tests, and as the
    reference implementation the vector retriever must match.
    """

    def __init__(self, corpus_path: str | Path) -> None:
        raw = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
        self._clauses: list[dict] = raw["clauses"]
        self._by_violation: dict[str, list[dict]] = {}
        for clause in self._clauses:
            for vt in clause["violation_types"]:
                self._by_violation.setdefault(vt, []).append(clause)

    def retrieve(self, violation_type: ViolationType) -> list[dict]:
        return self._by_violation.get(violation_type, [])


class ComplianceRAGAgent:
    """Maps a detected violation to its governing clause, grounded in the corpus."""

    def __init__(self, retriever: ClauseRetriever) -> None:
        self._retriever = retriever

    def cite(self, violation_type: ViolationType) -> RegulationCitation | None:
        """
        Return the governing citation for a violation, or None if the corpus
        has no clause for it. Never fabricates a clause.

        When several clauses govern the same violation, the most specific
        (non-ISO, i.e. jurisdiction-specific) clause is preferred over the
        general management-system standard, since a site officer needs the
        operative local rule, not the meta-standard.
        """
        candidates = self._retriever.retrieve(violation_type)
        if not candidates:
            return None

        chosen = self._most_specific(candidates)

        return RegulationCitation(
            regulation=chosen["regulation"],
            clause=chosen["clause"],
            text=chosen["text"],
            source_uri=chosen["source_uri"],
            compliance_status="non_compliant",
        )

    @staticmethod
    def _most_specific(candidates: list[dict]) -> dict:
        # Prefer jurisdiction-specific regulations over the ISO meta-standard.
        specific = [c for c in candidates if not c["regulation"].startswith("ISO")]
        pool = specific or candidates
        # Stable, deterministic tie-break by clause id.
        return min(pool, key=lambda c: c["id"])
