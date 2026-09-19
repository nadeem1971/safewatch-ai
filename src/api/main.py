"""
SafeWatch AI - HTTP API.

FastAPI layer over the orchestration pipeline, plus the human-review endpoints
the Governance Dashboard uses to close the loop.

Incident intake:
  POST /incidents            submit an incident (JSON)
  POST /incidents/upload     submit with an image file + permit fields (multipart)

Governance review (the human gate):
  GET  /incidents            list incidents pending human review (the queue)
  GET  /incidents/all        list every incident (dashboard overview)
  GET  /incidents/{id}       fetch one incident
  POST /incidents/{id}/decision   record a human decision (approve/reject/escalate)
  GET  /incidents/{id}/audit      the audit trail for an incident
  GET  /stats                aggregate counts for the dashboard

  GET  /health               liveness

The API owns no domain logic. Judgement stays in the agents; the human decision
is recorded verbatim with its reviewer and an audit record, so the human half of
the loop is as traceable as the automated half.
"""

from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.contracts import ViolationType
from src.governance.policy_engine import GovernanceEngine
from src.orchestration.orchestrator import IncidentState, Orchestrator
from src.persistence.repository import (
    HUMAN_DECISIONS,
    IncidentRepository,
    InMemoryIncidentRepository,
)
from src.rag.agent import ComplianceRAGAgent, InMemoryRetriever
from src.risk.scoring import RiskScoringAgent

CORPUS_PATH = "data/regulations/sample_corpus.json"

_KNOWN_VIOLATIONS: tuple[str, ...] = (
    "missing_harness",
    "missing_helmet",
    "missing_vest",
    "unsafe_zone_entry",
)


class IncidentRequest(BaseModel):
    vision_hint: ViolationType | None = Field(default=None)
    worker_count: int = Field(default=1, ge=0)
    zone_is_elevated: bool = False
    permit_id: str = "PTW-DEMO-001"
    permit_is_valid: bool = True
    permit_is_expired: bool = False
    work_type: str = "general"
    zone_classification: str = "standard"
    contractor_recent_violations: int = Field(default=0, ge=0)


class DecisionRequest(BaseModel):
    decision: str = Field(description="approved | rejected | escalated")
    reviewer: str = Field(default="hse_manager", description="Who is deciding.")
    note: str = Field(default="", description="Reviewer's rationale.")


def _hint_from_filename(filename: str) -> ViolationType | None:
    """DEMO STUB: derive the violation hint from the file name, not the pixels.
    Real Vision agent (issues #5/#6) will run a PPE model on the image bytes."""
    lowered = filename.lower()
    for violation in _KNOWN_VIOLATIONS:
        if violation in lowered:
            return violation  # type: ignore[return-value]
    return None


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
    app = FastAPI(title="SafeWatch AI", version="1.0.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    orch = orchestrator or build_orchestrator()
    repo = repository or InMemoryIncidentRepository()

    def _run_and_store(state: IncidentState) -> dict:
        return repo.save(orch.run(state)["reviewer_packet"])

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
        return _run_and_store(state)

    @app.post("/incidents/upload")
    async def submit_incident_upload(
        image: UploadFile = File(...),  # noqa: B008
        worker_count: int = Form(1),
        zone_is_elevated: bool = Form(False),
        permit_is_valid: bool = Form(True),
        permit_is_expired: bool = Form(False),
    ) -> dict:
        await image.read()
        state: IncidentState = {
            "vision_hint": _hint_from_filename(image.filename or ""),
            "worker_count": worker_count,
            "zone_is_elevated": zone_is_elevated,
            "permit_is_valid": permit_is_valid,
            "permit_is_expired": permit_is_expired,
        }
        record = _run_and_store(state)
        record["_uploaded_filename"] = image.filename
        record["_detection_source"] = "stub:filename"
        return record

    @app.get("/incidents")
    def list_pending() -> list[dict]:
        """The governance review queue: incidents awaiting human approval."""
        return repo.list_pending()

    @app.get("/incidents/all")
    def list_all() -> list[dict]:
        return repo.list_all()

    @app.get("/incidents/{incident_id}")
    def get_incident(incident_id: str) -> dict:
        record = repo.get(incident_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return record

    @app.post("/incidents/{incident_id}/decision")
    def record_decision(incident_id: str, body: DecisionRequest) -> dict:
        if body.decision not in HUMAN_DECISIONS:
            raise HTTPException(
                status_code=422,
                detail=f"decision must be one of {HUMAN_DECISIONS}",
            )
        updated = repo.record_decision(
            incident_id=incident_id,
            decision=body.decision,
            reviewer=body.reviewer,
            note=body.note,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return updated

    @app.get("/incidents/{incident_id}/audit")
    def get_audit(incident_id: str) -> list[dict]:
        if repo.get(incident_id) is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return repo.list_audit(incident_id)

    @app.get("/stats")
    def stats() -> dict:
        all_incidents = repo.list_all()
        by_band: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for inc in all_incidents:
            by_band[inc["risk_band"]] = by_band.get(inc["risk_band"], 0) + 1
            by_status[inc["status"]] = by_status.get(inc["status"], 0) + 1
        return {
            "total": len(all_incidents),
            "pending_review": len(repo.list_pending()),
            "by_band": by_band,
            "by_status": by_status,
        }

    return app


app = create_app()
