"""
Placeholder agents for the pipeline slots not yet implemented.

These are DELIBERATE STUBS, clearly labelled. They let the orchestrator run
end-to-end today while the real Vision and Document agents are built (issues
#5/#6 and #7). Each returns a contract-valid result derived from simple input
cues, so the downstream governance loop can be exercised with realistic shapes.

What production does instead is documented in docs/PRODUCTION-NOTES.md:
  - VisionAgentStub  -> fine-tuned Azure AI Vision PPE detection model
  - DocumentAgentStub -> Azure AI Document Intelligence permit extraction

These stubs never claim to do real detection. A stub that matched a filename
and reported "PPE violation detected" would be dishonest; these are named and
documented as placeholders so no reviewer is misled about what runs.
"""

from __future__ import annotations

from datetime import date

from src.contracts import Detection, PermitValidation, ViolationType


class VisionAgentStub:
    """STUB. Maps an explicit hint to a Detection. Not real computer vision.

    The orchestrator passes a `vision_hint` (e.g. "missing_harness") so tests
    and demos are deterministic. The real agent will consume image bytes.
    """

    MODEL_VERSION = "stub-vision-v0"

    def analyze(self, vision_hint: ViolationType | None, worker_count: int = 1) -> list[Detection]:
        if vision_hint is None:
            return []
        confidence = 0.9  # fixed; a real model returns a genuine score
        return [
            Detection(
                violation_type=vision_hint,
                confidence=confidence,
                worker_count=worker_count,
            )
        ]


class DocumentAgentStub:
    """STUB. Builds a PermitValidation from explicit flags. Not real OCR.

    The real agent will consume a permit PDF via Azure AI Document Intelligence.
    """

    MODEL_VERSION = "stub-document-v0"

    def validate(
        self,
        permit_id: str = "PTW-DEMO-001",
        is_valid: bool = True,
        is_expired: bool = False,
        work_type: str = "general",
        zone_classification: str = "standard",
    ) -> PermitValidation:
        return PermitValidation(
            permit_id=permit_id,
            is_valid=is_valid,
            is_expired=is_expired,
            expiry_date=date(2027, 1, 1) if not is_expired else date(2025, 1, 1),
            work_type=work_type,
            zone_classification=zone_classification,
        )
