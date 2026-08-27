"""
Tests for the deterministic risk scoring agent.

Verify that scores are bounded, that the most severe violation dominates,
that aggravating factors raise the score, and that every score is explainable.
"""

from datetime import date

import pytest

from src.contracts import Detection, PermitValidation, RiskAssessment
from src.risk.scoring import RISK_POLICY_VERSION, RiskScoringAgent


@pytest.fixture
def agent() -> RiskScoringAgent:
    return RiskScoringAgent()


def _detection(violation: str, workers: int = 1, confidence: float = 0.9) -> Detection:
    return Detection(
        violation_type=violation,
        confidence=confidence,
        worker_count=workers,
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


def test_no_detections_is_low_risk(agent: RiskScoringAgent) -> None:
    assessment = agent.score(detections=[])
    assert assessment.score == 0
    assert assessment.band == "low"
    assert isinstance(assessment, RiskAssessment)


def test_missing_harness_scores_higher_than_missing_vest(
    agent: RiskScoringAgent,
) -> None:
    harness = agent.score([_detection("missing_harness")])
    vest = agent.score([_detection("missing_vest")])
    assert harness.score > vest.score


def test_most_severe_violation_dominates(agent: RiskScoringAgent) -> None:
    # Several minor issues must not out-score one critical one.
    many_minor = agent.score([_detection("missing_vest") for _ in range(4)])
    one_critical = agent.score([_detection("missing_harness")])
    assert one_critical.score >= many_minor.score


def test_elevated_zone_raises_score(agent: RiskScoringAgent) -> None:
    flat = agent.score([_detection("missing_harness")], zone_is_elevated=False)
    elevated = agent.score([_detection("missing_harness")], zone_is_elevated=True)
    assert elevated.score > flat.score


def test_expired_permit_raises_score(agent: RiskScoringAgent) -> None:
    without = agent.score([_detection("missing_helmet")])
    with_permit = agent.score([_detection("missing_helmet")], permit=_expired_permit())
    assert with_permit.score > without.score


def test_multiple_workers_raise_score_but_capped(agent: RiskScoringAgent) -> None:
    one = agent.score([_detection("missing_helmet", workers=1)])
    crowd = agent.score([_detection("missing_helmet", workers=20)])
    assert crowd.score > one.score
    # Bonus is capped, so it never runs away.
    assert crowd.score <= 100


def test_score_never_exceeds_100(agent: RiskScoringAgent) -> None:
    assessment = agent.score(
        [_detection("missing_harness", workers=50)],
        permit=_expired_permit(),
        zone_is_elevated=True,
    )
    assert 0 <= assessment.score <= 100


def test_critical_combination_reaches_critical_band(agent: RiskScoringAgent) -> None:
    assessment = agent.score(
        [_detection("missing_harness", workers=3)],
        permit=_expired_permit(),
        zone_is_elevated=True,
    )
    assert assessment.band == "critical"


def test_every_assessment_is_explainable(agent: RiskScoringAgent) -> None:
    assessment = agent.score([_detection("missing_harness")], zone_is_elevated=True)
    assert assessment.contributing_factors
    assert assessment.rationale
    # Rationale references the factors.
    assert "violation" in assessment.rationale


def test_scoring_is_deterministic(agent: RiskScoringAgent) -> None:
    dets = [_detection("missing_harness", workers=2)]
    first = agent.score(dets, zone_is_elevated=True)
    second = agent.score(dets, zone_is_elevated=True)
    assert first == second


def test_policy_version_available() -> None:
    assert RISK_POLICY_VERSION
