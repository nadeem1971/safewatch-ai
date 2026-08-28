"""
End-to-end orchestration tests.

These run the full pipeline (vision -> document -> rag -> risk -> governance
-> report) and assert on the reviewer packet a human would see. They cover the
three canonical scenarios the system exists to handle, and prove the agents
compose correctly - the score from risk drives the route from governance, and
the citation from RAG lands in the packet.
"""

from pathlib import Path

import pytest

from src.agents.stubs import DocumentAgentStub, VisionAgentStub
from src.governance.policy_engine import GovernanceEngine
from src.orchestration.orchestrator import IncidentState, Orchestrator
from src.rag.agent import ComplianceRAGAgent, InMemoryRetriever
from src.risk.scoring import RiskScoringAgent

CORPUS = Path(__file__).parent.parent / "data" / "regulations" / "sample_corpus.json"


@pytest.fixture
def orchestrator() -> Orchestrator:
    return Orchestrator(
        rag_agent=ComplianceRAGAgent(InMemoryRetriever(CORPUS)),
        risk_agent=RiskScoringAgent(),
        governance_engine=GovernanceEngine(),
        vision_agent=VisionAgentStub(),
        document_agent=DocumentAgentStub(),
    )


def test_valid_permit_no_violation_auto_logs(orchestrator: Orchestrator) -> None:
    # Clean site, valid permit -> low risk -> auto-log, no human needed.
    state: IncidentState = {
        "vision_hint": None,
        "permit_is_valid": True,
        "permit_is_expired": False,
    }
    result = orchestrator.run(state)
    packet = result["reviewer_packet"]
    assert packet["route"] == "auto_log"
    assert packet["requires_human_approval"] is False


def test_missing_harness_at_height_escalates(orchestrator: Orchestrator) -> None:
    # Critical PPE issue at height -> high risk -> escalation, with a citation.
    state: IncidentState = {
        "vision_hint": "missing_harness",
        "worker_count": 3,
        "zone_is_elevated": True,
        "permit_is_valid": True,
        "permit_is_expired": False,
    }
    result = orchestrator.run(state)
    packet = result["reviewer_packet"]
    assert packet["risk_band"] in ("high", "critical")
    assert packet["route"] in ("hse_manager", "escalation_committee")
    assert packet["requires_human_approval"] is True
    # RAG must have grounded a citation for the harness violation.
    assert len(packet["citations"]) >= 1
    # A grounded citation exists (any real clause governing the harness violation).
    assert all(c["regulation"] and c["clause"] and c["source_uri"] for c in packet["citations"])


def test_expired_permit_forces_human_review(orchestrator: Orchestrator) -> None:
    # Even a minor visual issue with an expired permit must reach a human.
    state: IncidentState = {
        "vision_hint": "missing_helmet",
        "permit_is_valid": False,
        "permit_is_expired": True,
    }
    result = orchestrator.run(state)
    packet = result["reviewer_packet"]
    assert "permit_expired" in packet["hard_overrides"]
    assert packet["requires_human_approval"] is True
    assert packet["route"] in ("hse_manager", "escalation_committee")


def test_reviewer_packet_is_complete(orchestrator: Orchestrator) -> None:
    # The packet a human sees must carry every element of the decision.
    state: IncidentState = {"vision_hint": "missing_vest", "worker_count": 1}
    packet = orchestrator.run(state)["reviewer_packet"]
    for key in (
        "detections",
        "citations",
        "risk_score",
        "risk_band",
        "route",
        "policy_version",
        "requires_human_approval",
    ):
        assert key in packet


def test_pipeline_is_deterministic(orchestrator: Orchestrator) -> None:
    state: IncidentState = {
        "vision_hint": "missing_harness",
        "worker_count": 2,
        "zone_is_elevated": True,
    }
    first = orchestrator.run(dict(state))["reviewer_packet"]
    second = orchestrator.run(dict(state))["reviewer_packet"]
    assert first == second


def test_citation_is_grounded_not_fabricated(orchestrator: Orchestrator) -> None:
    # No detection -> no citation. The pipeline never invents regulations.
    state: IncidentState = {"vision_hint": None}
    packet = orchestrator.run(state)["reviewer_packet"]
    assert packet["citations"] == []
