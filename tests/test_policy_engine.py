"""
Tests for the deterministic governance engine.

These tests are the safety contract in executable form. The band-boundary tests
in particular guard against off-by-one errors at the exact thresholds where a
misclassification would send a serious incident to auto-log instead of a human.
"""

from datetime import date

import pytest

from src.contracts import GovernanceDecision, PermitValidation, RiskAssessment
from src.governance.policy_engine import POLICY_VERSION, GovernanceEngine


@pytest.fixture
def engine() -> GovernanceEngine:
    return GovernanceEngine()


def _risk(score: int) -> RiskAssessment:
    band = "low" if score < 30 else "medium" if score < 60 else "high" if score < 80 else "critical"
    return RiskAssessment(score=score, band=band, rationale="test")


def _valid_permit() -> PermitValidation:
    return PermitValidation(
        permit_id="PTW-1",
        is_valid=True,
        is_expired=False,
        expiry_date=date(2027, 1, 1),
        work_type="general",
        zone_classification="standard",
    )


# --- Risk band routing: exhaustive boundaries -------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "auto_log"),
        (29, "auto_log"),  # last auto-log score
        (30, "safety_officer"),  # first human-gate score
        (59, "safety_officer"),
        (60, "hse_manager"),
        (79, "hse_manager"),
        (80, "escalation_committee"),
        (100, "escalation_committee"),
    ],
)
def test_risk_band_boundaries(engine: GovernanceEngine, score: int, expected: str) -> None:
    decision = engine.decide(_risk(score), permit=_valid_permit())
    assert decision.route == expected


def test_below_30_is_the_only_auto_log(engine: GovernanceEngine) -> None:
    # The safety-critical property: anything >= 30 must reach a human.
    assert engine.decide(_risk(29), permit=_valid_permit()).requires_human_approval is False
    assert engine.decide(_risk(30), permit=_valid_permit()).requires_human_approval is True


# --- Hard overrides evaluate first ------------------------------------------


def test_expired_permit_forces_escalation_regardless_of_low_score(
    engine: GovernanceEngine,
) -> None:
    # Score 5 would normally auto-log; an expired permit must override that.
    expired = PermitValidation(
        permit_id="PTW-2",
        is_valid=False,
        is_expired=True,
        expiry_date=date(2025, 1, 1),
        work_type="work_at_height",
        zone_classification="elevated",
    )
    decision = engine.decide(_risk(5), permit=expired)
    assert decision.route == "escalation_committee"
    assert "permit_expired" in decision.hard_overrides_triggered
    assert decision.requires_human_approval is True


def test_contractor_repeat_violations_force_escalation(
    engine: GovernanceEngine,
) -> None:
    decision = engine.decide(
        _risk(10),
        permit=_valid_permit(),
        contractor_recent_violations=4,
    )
    assert decision.route == "escalation_committee"
    assert "contractor_repeat_violations" in decision.hard_overrides_triggered


def test_contractor_at_limit_does_not_override(engine: GovernanceEngine) -> None:
    # Exactly at the limit (3) is not "> 3"; no override.
    decision = engine.decide(
        _risk(10),
        permit=_valid_permit(),
        contractor_recent_violations=3,
    )
    assert decision.hard_overrides_triggered == []
    assert decision.route == "auto_log"


def test_multiple_overrides_all_recorded(engine: GovernanceEngine) -> None:
    expired_invalid = PermitValidation(
        permit_id="PTW-3",
        is_valid=False,
        is_expired=True,
        expiry_date=date(2025, 1, 1),
        work_type="hot_work",
        zone_classification="restricted",
    )
    decision = engine.decide(
        _risk(50),
        permit=expired_invalid,
        contractor_recent_violations=5,
    )
    assert "permit_expired" in decision.hard_overrides_triggered
    assert "permit_invalid" in decision.hard_overrides_triggered
    assert "contractor_repeat_violations" in decision.hard_overrides_triggered
    assert decision.route == "escalation_committee"


# --- No permit supplied ------------------------------------------------------


def test_missing_permit_does_not_crash_and_routes_by_score(
    engine: GovernanceEngine,
) -> None:
    decision = engine.decide(_risk(45), permit=None)
    assert decision.route == "safety_officer"
    assert decision.hard_overrides_triggered == []


# --- Auditability ------------------------------------------------------------


def test_every_decision_records_policy_version(engine: GovernanceEngine) -> None:
    decision = engine.decide(_risk(70), permit=_valid_permit())
    assert decision.policy_version == POLICY_VERSION


def test_decision_is_a_governance_decision(engine: GovernanceEngine) -> None:
    decision = engine.decide(_risk(70), permit=_valid_permit())
    assert isinstance(decision, GovernanceDecision)


# --- Determinism -------------------------------------------------------------


def test_same_inputs_produce_identical_decisions(engine: GovernanceEngine) -> None:
    r = _risk(65)
    p = _valid_permit()
    first = engine.decide(r, permit=p)
    second = engine.decide(r, permit=p)
    assert first == second
