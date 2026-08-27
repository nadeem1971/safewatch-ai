"""
Tests for the deterministic governance engine (graduated escalation).

Band-boundary tests guard the exact thresholds. Graduated-escalation tests
verify that overrides lift the route to at least their own level but never
lower a route that the risk score already set higher.
"""

from datetime import date

import pytest

from src.contracts import GovernanceDecision, PermitValidation, RiskAssessment
from src.governance.policy_engine import POLICY_VERSION, GovernanceEngine, max_route


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


def _expired_permit() -> PermitValidation:
    return PermitValidation(
        permit_id="PTW-X",
        is_valid=False,
        is_expired=True,
        expiry_date=date(2025, 1, 1),
        work_type="work_at_height",
        zone_classification="elevated",
    )


# --- Risk band routing: exhaustive boundaries -------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "auto_log"),
        (29, "auto_log"),
        (30, "safety_officer"),
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
    assert engine.decide(_risk(29), permit=_valid_permit()).requires_human_approval is False
    assert engine.decide(_risk(30), permit=_valid_permit()).requires_human_approval is True


# --- max_route helper --------------------------------------------------------


def test_max_route_takes_higher_scrutiny() -> None:
    assert max_route("auto_log", "hse_manager") == "hse_manager"
    assert max_route("escalation_committee", "safety_officer") == "escalation_committee"
    assert max_route("safety_officer", "safety_officer") == "safety_officer"


# --- Graduated escalation ----------------------------------------------------


def test_expired_permit_lifts_low_score_to_hse_manager(
    engine: GovernanceEngine,
) -> None:
    # Score 5 alone -> auto_log; expired permit lifts it to hse_manager (not committee).
    decision = engine.decide(_risk(5), permit=_expired_permit())
    assert decision.route == "hse_manager"
    assert "permit_expired" in decision.hard_overrides_triggered
    assert decision.requires_human_approval is True


def test_override_does_not_lower_a_higher_risk_route(engine: GovernanceEngine) -> None:
    # Score 90 -> escalation_committee; an expired permit (hse_manager level)
    # must NOT pull it down.
    decision = engine.decide(_risk(90), permit=_expired_permit())
    assert decision.route == "escalation_committee"


def test_contractor_violations_lift_to_committee(engine: GovernanceEngine) -> None:
    decision = engine.decide(
        _risk(10),
        permit=_valid_permit(),
        contractor_recent_violations=4,
    )
    assert decision.route == "escalation_committee"
    assert "contractor_repeat_violations" in decision.hard_overrides_triggered


def test_contractor_at_limit_does_not_override(engine: GovernanceEngine) -> None:
    decision = engine.decide(
        _risk(10),
        permit=_valid_permit(),
        contractor_recent_violations=3,
    )
    assert decision.hard_overrides_triggered == []
    assert decision.route == "auto_log"


def test_highest_of_multiple_overrides_wins(engine: GovernanceEngine) -> None:
    # Expired+invalid permit (hse_manager) plus contractor violations (committee)
    # on a mid score -> committee, with all overrides recorded.
    decision = engine.decide(
        _risk(50),
        permit=_expired_permit(),
        contractor_recent_violations=5,
    )
    assert decision.route == "escalation_committee"
    assert "permit_expired" in decision.hard_overrides_triggered
    assert "permit_invalid" in decision.hard_overrides_triggered
    assert "contractor_repeat_violations" in decision.hard_overrides_triggered


# --- No permit ---------------------------------------------------------------


def test_missing_permit_routes_by_score(engine: GovernanceEngine) -> None:
    decision = engine.decide(_risk(45), permit=None)
    assert decision.route == "safety_officer"
    assert decision.hard_overrides_triggered == []


# --- Auditability & determinism ---------------------------------------------


def test_every_decision_records_policy_version(engine: GovernanceEngine) -> None:
    decision = engine.decide(_risk(70), permit=_valid_permit())
    assert decision.policy_version == POLICY_VERSION


def test_decision_is_a_governance_decision(engine: GovernanceEngine) -> None:
    decision = engine.decide(_risk(70), permit=_valid_permit())
    assert isinstance(decision, GovernanceDecision)


def test_same_inputs_produce_identical_decisions(engine: GovernanceEngine) -> None:
    r, p = _risk(65), _valid_permit()
    assert engine.decide(r, permit=p) == engine.decide(r, permit=p)
