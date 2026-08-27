"""
Risk Scoring Agent.

Computes a composite risk score (0-100) for an incident from its contributing
factors, and maps that score to a risk band. This is the input the Governance
Engine routes on.

The scoring is deterministic and transparent: each factor contributes a bounded
number of points, the total is capped at 100, and every contributing factor is
recorded in the assessment's rationale so a score can always be explained.

Like the governance engine, this is deliberately rule-based rather than
model-driven. A safety risk score that fed a routing decision must be
inspectable and defensible, not the opaque output of a model.

Weights are a starting calibration and are versioned; they would be tuned
against real incident outcomes in production (see PRODUCTION-NOTES).
"""

from __future__ import annotations

from src.contracts import Detection, PermitValidation, RiskAssessment, ViolationType

RISK_POLICY_VERSION = "1.0.0"

# Base severity points per violation type. Missing fall protection at height is
# the most dangerous, so it dominates; a missing helmet is serious but lower.
_VIOLATION_BASE_POINTS: dict[ViolationType, int] = {
    "missing_harness": 55,
    "unsafe_zone_entry": 45,
    "missing_helmet": 30,
    "missing_vest": 20,
}

# Additional points for aggravating context.
_ELEVATED_ZONE_BONUS = 20  # violation in an elevated/high-risk zone
_MULTI_WORKER_BONUS_PER_HEAD = 5  # each additional worker exposed
_MULTI_WORKER_CAP = 15
_EXPIRED_PERMIT_BONUS = 15
_INVALID_PERMIT_BONUS = 10

# Band thresholds must match the governance engine's bands.
_BAND_LOW = 30
_BAND_HIGH = 60
_BAND_CRITICAL = 80


class RiskScoringAgent:
    """Deterministic composite risk scorer."""

    def __init__(self, policy_version: str = RISK_POLICY_VERSION) -> None:
        self._policy_version = policy_version

    def score(
        self,
        detections: list[Detection],
        permit: PermitValidation | None = None,
        zone_is_elevated: bool = False,
    ) -> RiskAssessment:
        """
        Compute the composite risk assessment for an incident.

        The score is the sum of the most severe detection's base points plus
        bounded bonuses for aggravating context, capped at 100. Using the max
        detection as the base (rather than summing all) avoids a pile of minor
        issues out-scoring one critical one.
        """
        factors: list[str] = []
        score = 0

        if detections:
            base_points = max(_VIOLATION_BASE_POINTS.get(d.violation_type, 10) for d in detections)
            worst = max(
                detections,
                key=lambda d: _VIOLATION_BASE_POINTS.get(d.violation_type, 10),
            )
            score += base_points
            factors.append(f"violation:{worst.violation_type} (+{base_points})")

            total_workers = sum(d.worker_count for d in detections)
            if total_workers > 1:
                bonus = min(
                    (total_workers - 1) * _MULTI_WORKER_BONUS_PER_HEAD,
                    _MULTI_WORKER_CAP,
                )
                score += bonus
                factors.append(f"workers_exposed:{total_workers} (+{bonus})")

        if zone_is_elevated:
            score += _ELEVATED_ZONE_BONUS
            factors.append(f"elevated_zone (+{_ELEVATED_ZONE_BONUS})")

        if permit is not None:
            if permit.is_expired:
                score += _EXPIRED_PERMIT_BONUS
                factors.append(f"permit_expired (+{_EXPIRED_PERMIT_BONUS})")
            if not permit.is_valid:
                score += _INVALID_PERMIT_BONUS
                factors.append(f"permit_invalid (+{_INVALID_PERMIT_BONUS})")

        score = min(score, 100)
        band = self._band(score)

        if not factors:
            factors.append("no_violations_detected")
            rationale = "No violations detected; baseline low risk."
        else:
            rationale = "Composite score from: " + ", ".join(factors) + f". Band: {band}."

        return RiskAssessment(
            score=score,
            band=band,
            contributing_factors=factors,
            rationale=rationale,
        )

    @staticmethod
    def _band(score: int) -> str:
        if score < _BAND_LOW:
            return "low"
        if score < _BAND_HIGH:
            return "medium"
        if score < _BAND_CRITICAL:
            return "high"
        return "critical"
