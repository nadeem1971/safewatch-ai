"""
Tests for the governance review endpoints: the human gate.

These verify the human half of the loop - a pending incident can be approved,
rejected, or escalated; the decision is recorded on the incident and in a
separate audit record; and the queue and stats reflect the change.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.governance.policy_engine import GovernanceEngine
from src.orchestration.orchestrator import Orchestrator
from src.persistence.repository import InMemoryIncidentRepository
from src.rag.agent import ComplianceRAGAgent, InMemoryRetriever
from src.risk.scoring import RiskScoringAgent

CORPUS = Path(__file__).parent.parent / "data" / "regulations" / "sample_corpus.json"


@pytest.fixture
def client() -> TestClient:
    orch = Orchestrator(
        rag_agent=ComplianceRAGAgent(InMemoryRetriever(CORPUS)),
        risk_agent=RiskScoringAgent(),
        governance_engine=GovernanceEngine(),
    )
    return TestClient(create_app(orchestrator=orch, repository=InMemoryIncidentRepository()))


def _submit_pending(client: TestClient) -> str:
    r = client.post(
        "/incidents",
        json={
            "vision_hint": "missing_harness",
            "worker_count": 3,
            "zone_is_elevated": True,
        },
    )
    return r.json()["id"]


def test_approve_moves_incident_out_of_queue(client: TestClient) -> None:
    incident_id = _submit_pending(client)
    assert len(client.get("/incidents").json()) == 1  # in queue

    r = client.post(
        f"/incidents/{incident_id}/decision",
        json={
            "decision": "approved",
            "reviewer": "j.doe",
            "note": "Verified, action taken",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert r.json()["decided_by"] == "j.doe"
    assert len(client.get("/incidents").json()) == 0  # out of queue


def test_reject_and_escalate_are_valid(client: TestClient) -> None:
    for decision in ("rejected", "escalated"):
        incident_id = _submit_pending(client)
        r = client.post(f"/incidents/{incident_id}/decision", json={"decision": decision})
        assert r.status_code == 200
        assert r.json()["status"] == decision


def test_invalid_decision_rejected(client: TestClient) -> None:
    incident_id = _submit_pending(client)
    r = client.post(f"/incidents/{incident_id}/decision", json={"decision": "maybe"})
    assert r.status_code == 422


def test_decision_on_unknown_incident_404(client: TestClient) -> None:
    r = client.post("/incidents/nope/decision", json={"decision": "approved"})
    assert r.status_code == 404


def test_decision_creates_audit_record(client: TestClient) -> None:
    incident_id = _submit_pending(client)
    client.post(
        f"/incidents/{incident_id}/decision",
        json={"decision": "approved", "reviewer": "a.khan", "note": "cleared on site"},
    )
    audit = client.get(f"/incidents/{incident_id}/audit").json()
    assert len(audit) == 1
    assert audit[0]["decision"] == "approved"
    assert audit[0]["reviewer"] == "a.khan"
    assert audit[0]["note"] == "cleared on site"
    assert audit[0]["type"] == "audit"


def test_all_incidents_listed(client: TestClient) -> None:
    client.post("/incidents", json={"vision_hint": None})  # auto-log
    _submit_pending(client)  # pending
    all_inc = client.get("/incidents/all").json()
    assert len(all_inc) == 2


def test_stats_reflect_state(client: TestClient) -> None:
    client.post("/incidents", json={"vision_hint": None})  # auto_logged, low
    incident_id = _submit_pending(client)  # pending, critical
    client.post(f"/incidents/{incident_id}/decision", json={"decision": "approved"})

    stats = client.get("/stats").json()
    assert stats["total"] == 2
    assert stats["pending_review"] == 0  # the critical one was approved
    assert "critical" in stats["by_band"] or "low" in stats["by_band"]
    assert stats["by_status"].get("approved") == 1
