"""Contract validation. These tests protect the seams."""

from datetime import date

import pytest
from pydantic import ValidationError

from src.contracts import (
    Detection,
    GovernanceDecision,
    PermitValidation,
    RegulationCitation,
    RiskAssessment,
)


def test_detection_accepts_valid_input() -> None:
    d = Detection(
        violation_type="missing_harness",
        confidence=0.91,
        bounding_box=(10, 20, 110, 220),
        worker_count=3,
    )
    assert d.violation_type == "missing_harness"


def test_detection_rejects_confidence_above_one() -> None:
    with pytest.raises(ValidationError):
        Detection(violation_type="missing_helmet", confidence=1.4, worker_count=1)


def test_detection_rejects_unknown_violation_type() -> None:
    with pytest.raises(ValidationError):
        Detection(violation_type="missing_boots", confidence=0.5, worker_count=1)


def test_permit_validation_captures_expiry() -> None:
    p = PermitValidation(
        permit_id="PTW-2026-0417",
        is_valid=False,
        is_expired=True,
        expiry_date=date(2026, 6, 30),
        missing_approvals=["HSE Manager"],
        work_type="work_at_height",
        zone_classification="elevated",
    )
    assert p.is_expired is True
    assert p.missing_approvals == ["HSE Manager"]


def test_regulation_citation_requires_compliance_status() -> None:
    with pytest.raises(ValidationError):
        RegulationCitation(
            regulation="OSHAD SF38",
            clause="Section 5.4",
            text="Workers at height shall wear approved fall-protection equipment.",
            source_uri="https://example.org/oshad-sf38",
        )


def test_risk_assessment_rejects_score_above_100() -> None:
    with pytest.raises(ValidationError):
        RiskAssessment(score=101, band="critical", rationale="out of range")


def test_risk_assessment_rejects_negative_score() -> None:
    with pytest.raises(ValidationError):
        RiskAssessment(score=-1, band="low", rationale="out of range")


def test_governance_decision_records_policy_version() -> None:
    g = GovernanceDecision(
        route="hse_manager",
        hard_overrides_triggered=[],
        policy_version="v1.0.0",
        requires_human_approval=True,
    )
    assert g.policy_version == "v1.0.0"


def test_governance_decision_rejects_unknown_route() -> None:
    with pytest.raises(ValidationError):
        GovernanceDecision(
            route="ask_the_model",
            policy_version="v1.0.0",
            requires_human_approval=True,
        )
