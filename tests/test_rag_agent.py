"""
Tests for the Compliance RAG agent.

The load-bearing test is test_no_clause_returns_none_not_fabrication:
it encodes the grounding guarantee. If retrieval finds nothing, the agent
returns None rather than inventing a plausible-sounding regulation.
"""

from pathlib import Path

import pytest

from src.contracts import RegulationCitation
from src.rag.agent import ComplianceRAGAgent, InMemoryRetriever

CORPUS = Path(__file__).parent.parent / "data" / "regulations" / "sample_corpus.json"


@pytest.fixture
def agent() -> ComplianceRAGAgent:
    return ComplianceRAGAgent(InMemoryRetriever(CORPUS))


def test_helmet_violation_cites_head_protection_clause(
    agent: ComplianceRAGAgent,
) -> None:
    citation = agent.cite("missing_helmet")
    assert citation is not None
    assert isinstance(citation, RegulationCitation)
    assert citation.regulation == "OSHAD SF38"
    assert citation.clause == "Section 6.1"
    assert citation.compliance_status == "non_compliant"


def test_harness_violation_cites_fall_protection_clause(
    agent: ComplianceRAGAgent,
) -> None:
    citation = agent.cite("missing_harness")
    assert citation is not None
    # Fall-protection or permit clause — both jurisdiction-specific, not ISO.
    assert not citation.regulation.startswith("ISO")


def test_vest_violation_cites_high_vis_clause(agent: ComplianceRAGAgent) -> None:
    citation = agent.cite("missing_vest")
    assert citation is not None
    assert citation.clause == "Section 3.2"


def test_every_citation_field_is_populated(agent: ComplianceRAGAgent) -> None:
    citation = agent.cite("unsafe_zone_entry")
    assert citation is not None
    assert citation.regulation
    assert citation.clause
    assert citation.text
    assert citation.source_uri.startswith("http")


def test_jurisdiction_specific_preferred_over_iso(agent: ComplianceRAGAgent) -> None:
    # missing_helmet is governed by both OSHAD SF38 6.1 and ISO 45001 8.1.2.
    # The operative local rule should win.
    citation = agent.cite("missing_helmet")
    assert citation is not None
    assert not citation.regulation.startswith("ISO")


def test_no_clause_returns_none_not_fabrication() -> None:
    # A retriever that finds nothing must produce no citation — never an invented one.
    class EmptyRetriever:
        def retrieve(self, violation_type: str) -> list[dict]:
            return []

    agent = ComplianceRAGAgent(EmptyRetriever())
    assert agent.cite("missing_helmet") is None


def test_retriever_indexes_all_violation_types(agent: ComplianceRAGAgent) -> None:
    # Every violation type in the contract has at least one governing clause.
    for vt in (
        "missing_helmet",
        "missing_vest",
        "missing_harness",
        "unsafe_zone_entry",
    ):
        assert agent.cite(vt) is not None, f"no clause for {vt}"


def test_selection_is_deterministic(agent: ComplianceRAGAgent) -> None:
    # Same input, same citation, every time — no randomness in retrieval.
    first = agent.cite("missing_harness")
    second = agent.cite("missing_harness")
    assert first == second
