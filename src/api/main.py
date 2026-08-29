"""
SafeWatch AI - HTTP API.

FastAPI layer over the orchestration pipeline. Turns the running system into a
service the UIs (Operations Console, Governance Dashboard) call.

Endpoints:
  POST /incidents            submit an incident, run the pipeline, persist, return the packet
  GET  /incidents/{id}       fetch a stored incident
  GET  /incidents            list incidents pending human review (the governance queue)
  GET  /health               liveness

The API owns no domain logic. It validates input, invokes the orchestrator,
persists the result through the repository interface, and returns the reviewer
packet. All judgement stays in the agents; all storage stays behind the
repository. This keeps the API thin and the core testable without HTTP.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.contracts import ViolationType
from src.governance.policy_engine import GovernanceEngine
from src.orchestration.orchestrator import IncidentState, Orchestrator
from src.persistence.repository import (
    IncidentRepository,
    InMemoryIncidentRepository,
)
from src.rag.agent import ComplianceRAGAgent, InMemoryRetriever
from src.risk.scoring import RiskScoringAgent

CORPUS_PATH = "data/regulations/sample_corpus.json"


class IncidentRequest(BaseModel):
    """Incoming incident. In v1 the vision/document inputs are hints; the real
    agents will accept image bytes and a permit PDF (see stubs / PRODUCTION-NOTES)."""

    vision_hint: ViolationType | None = Field(
        default=None, description="Detected violation type, or None for a clean site."
    )
    worker_count: int = Field(default=1, ge=0)
    zone_is_elevated: bool = False
    permit_id: str = "PTW-DEMO-001"
    permit_is_valid: bool = True
    permit_is_expired: bool = False
    work_type: str = "general"
    zone_classification: str = "standard"
    contractor_recent_violations: int = Field(default=0, ge=0)


def build_orchestrator() -> Orchestrator:
    return Orchestrator(
        rag_agent=ComplianceRAGAgent(InMemoryRetriever(CORPUS_PATH)),
        risk_agent=RiskScoringAgent(),
        governance_engine=GovernanceEngine(),
    )


def create_app(
    orchestrator: Orchestrator | None = None,
    repository: IncidentRepository | None = None,
) -> FastAPI:
    """Application factory. Dependencies are injectable so tests supply their own."""
    app = FastAPI(title="SafeWatch AI", version="1.0.0")
    orch = orchestrator or build_orchestrator()
    repo = repository or InMemoryIncidentRepository()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/incidents")
    def submit_incident(request: IncidentRequest) -> dict:
        state: IncidentState = {
            "vision_hint": request.vision_hint,
            "worker_count": request.worker_count,
            "zone_is_elevated": request.zone_is_elevated,
            "permit_id": request.permit_id,
            "permit_is_valid": request.permit_is_valid,
            "permit_is_expired": request.permit_is_expired,
            "work_type": request.work_type,
            "zone_classification": request.zone_classification,
            "contractor_recent_violations": request.contractor_recent_violations,
        }
        result = orch.run(state)
        record = repo.save(result["reviewer_packet"])
        return record

    @app.get("/incidents/{incident_id}")
    def get_incident(incident_id: str) -> dict:
        record = repo.get(incident_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return record

    @app.get("/incidents")
    def list_pending() -> list[dict]:
        """The governance review queue: incidents awaiting human approval."""
        return repo.list_pending()

    return app


app = create_app()
