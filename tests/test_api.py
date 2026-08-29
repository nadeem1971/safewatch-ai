"""
API tests using FastAPI's TestClient.

These exercise the HTTP surface end-to-end: an incident POSTed in runs the real
pipeline, is persisted, and comes back as a stored record; the review queue
reflects what needs human approval. The pipeline underneath is the same one the
orchestrator tests cover, so these focus on the HTTP + persistence seam.
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
    app = create_app(orchestrator=orch, repository=InMemoryIncidentRepository())
    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_submit_clean_site_auto_logs(client: TestClient) -> None:
    r = client.post("/incidents", json={"vision_hint": None})
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "auto_log"
    assert body["status"] == "auto_logged"
    assert body["requires_human_approval"] is False


def test_submit_critical_incident_pends_review(client: TestClient) -> None:
    r = client.post(
        "/incidents",
        json={
            "vision_hint": "missing_harness",
            "worker_count": 3,
            "zone_is_elevated": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["requires_human_approval"] is True
    assert body["status"] == "pending_review"
    assert body["risk_band"] in ("high", "critical")


def test_submitted_incident_is_retrievable(client: TestClient) -> None:
    submitted = client.post("/incidents", json={"vision_hint": "missing_helmet"}).json()
    fetched = client.get(f"/incidents/{submitted['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == submitted["id"]


def test_unknown_incident_returns_404(client: TestClient) -> None:
    r = client.get("/incidents/does-not-exist")
    assert r.status_code == 404


def test_review_queue_lists_only_pending(client: TestClient) -> None:
    # One auto-log, one escalation.
    client.post("/incidents", json={"vision_hint": None})  # auto_log
    client.post(
        "/incidents",
        json={
            "vision_hint": "missing_harness",
            "zone_is_elevated": True,
            "worker_count": 3,
        },
    )  # pending
    queue = client.get("/incidents").json()
    assert len(queue) == 1
    assert queue[0]["status"] == "pending_review"


def test_expired_permit_incident_pends_review(client: TestClient) -> None:
    r = client.post(
        "/incidents",
        json={
            "vision_hint": "missing_helmet",
            "permit_is_valid": False,
            "permit_is_expired": True,
        },
    )
    body = r.json()
    assert body["requires_human_approval"] is True
    assert "permit_expired" in body["hard_overrides"]
