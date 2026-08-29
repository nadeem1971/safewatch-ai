"""
SafeWatch AI - HTTP API.

FastAPI layer over the orchestration pipeline. Turns the running system into a
service the UIs (Operations Console, Governance Dashboard) call.

Endpoints:
  POST /incidents            submit an incident (JSON), run the pipeline, persist, return the packet
  POST /incidents/upload     submit an incident with an image file + permit fields (multipart)
  GET  /incidents/{id}       fetch a stored incident
  GET  /incidents            list incidents pending human review (the governance queue)
  GET  /health               liveness

The API owns no domain logic. It validates input, invokes the orchestrator,
persists the result through the repository interface, and returns the reviewer
packet. All judgement stays in the agents; all storage stays behind the
repository.
"""

from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
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

# Violation types the demo upload flow recognizes, for the honest filename->hint mapping.
_KNOWN_VIOLATIONS: tuple[str, ...] = (
    "missing_harness",
    "missing_helmet",
    "missing_vest",
    "unsafe_zone_entry",
)


class IncidentRequest(BaseModel):
    """Incoming incident (JSON path). vision_hint stands in for real detection."""

    vision_hint: ViolationType | None = Field(default=None)
    worker_count: int = Field(default=1, ge=0)
    zone_is_elevated: bool = False
    permit_id: str = "PTW-DEMO-001"
    permit_is_valid: bool = True
    permit_is_expired: bool = False
    work_type: str = "general"
    zone_classification: str = "standard"
    contractor_recent_violations: int = Field(default=0, ge=0)


def _hint_from_filename(filename: str) -> ViolationType | None:
    """
    DEMO STUB: derive the violation hint from the uploaded file's name.

    This is NOT computer vision. The real Vision agent (issues #5/#6) will run a
    fine-tuned PPE detection model on the image bytes. Until then, the upload
    endpoint reads the intended violation from the filename so the pipeline can
    be exercised with a real upload UI. Documented as a stub in PRODUCTION-NOTES.
    """
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

    # The two UIs are served separately in dev, so allow browser calls from them.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    orch = orchestrator or build_orchestrator()
    repo = repository or InMemoryIncidentRepository()

    def _run_and_store(state: IncidentState) -> dict:
        result = orch.run(state)
        return repo.save(result["reviewer_packet"])

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
        worker_count: int = Form(1),  # noqa: B008
        zone_is_elevated: bool = Form(False),  # noqa: B008
        permit_is_valid: bool = Form(True),  # noqa: B008
        permit_is_expired: bool = Form(False),  # noqa: B008
    ) -> dict:
        # Read the file so a real upload happens; detection is stubbed off the name.
        await image.read()
        hint = _hint_from_filename(image.filename or "")
        state: IncidentState = {
            "vision_hint": hint,
            "worker_count": worker_count,
            "zone_is_elevated": zone_is_elevated,
            "permit_is_valid": permit_is_valid,
            "permit_is_expired": permit_is_expired,
        }
        record = _run_and_store(state)
        record["_uploaded_filename"] = image.filename
        record["_detection_source"] = "stub:filename"  # honest about how hint was derived
        return record

    @app.get("/incidents/{incident_id}")
    def get_incident(incident_id: str) -> dict:
        record = repo.get(incident_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return record

    @app.get("/incidents")
    def list_pending() -> list[dict]:
        return repo.list_pending()

    return app


app = create_app()
