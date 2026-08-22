"""
Governance Agent — Deterministic Policy Engine.

This is the heart of SafeWatch AI's safety guarantee. It decides how each
assessed incident is routed for human review. It is deterministic by design:
the same inputs always produce the same routing, and the routing is decided by
hard-coded policy, never by model judgment.

    The LLM proposes. Deterministic policy disposes. A human approves.

An LLM must never be the final arbiter of a safety escalation. Upstream agents
(vision, document, RAG, risk scoring) may use models to *propose* findings, but
the routing decision that determines whether a human sees an incident is made
here, in auditable code.

Evaluation order is significant:

    1. Hard overrides  — absolute conditions that force a route regardless of
                         the numeric risk score (e.g. an expired permit).
    2. Risk band       — if no hard override fires, route by the risk score.

Every decision records the policy version that produced it, so any historical
decision can be explained against the exact rules in force at the time.
"""

from __future__ import annotations

from src.contracts import GovernanceDecision, PermitValidation, RiskAssessment

# Bump when any rule below changes. Recorded on every decision for auditability.
POLICY_VERSION = "1.0.0"

# Risk band thresholds. Bands are exhaustive and non-overlapping.
# Convention: lower bound inclusive, upper bound exclusive.
THRESHOLD_LOW = 30  # < 30           -> auto_log
THRESHOLD_HIGH = 60  # 30..59        -> safety_officer
THRESHOLD_CRITICAL = 80  # 60..79    -> hse_manager;  >= 80 -> escalation_committee

# Contractor repeat-offence override.
CONTRACTOR_VIOLATION_LIMIT = 3


class GovernanceEngine:
    """Deterministic router from a risk assessment to a human-review route."""

    def __init__(self, policy_version: str = POLICY_VERSION) -> None:
        self._policy_version = policy_version

    def decide(
        self,
        risk: RiskAssessment,
        permit: PermitValidation | None = None,
        contractor_recent_violations: int = 0,
    ) -> GovernanceDecision:
        """
        Produce the routing decision for one incident.

        Hard overrides are evaluated first and can force escalation regardless
        of the risk score. If none fire, routing falls to the risk band.
        """
        hard_overrides = self._evaluate_hard_overrides(
            permit=permit,
            contractor_recent_violations=contractor_recent_violations,
        )

        if hard_overrides:
            # Any hard override forces the highest-scrutiny human route.
            return GovernanceDecision(
                route="escalation_committee",
                hard_overrides_triggered=hard_overrides,
                policy_version=self._policy_version,
                requires_human_approval=True,
            )

        route = self._route_by_band(risk.score)
        return GovernanceDecision(
            route=route,
            hard_overrides_triggered=[],
            policy_version=self._policy_version,
            requires_human_approval=(route != "auto_log"),
        )

    @staticmethod
    def _evaluate_hard_overrides(
        permit: PermitValidation | None,
        contractor_recent_violations: int,
    ) -> list[str]:
        """Absolute conditions that force escalation regardless of score."""
        triggered: list[str] = []

        if permit is not None and permit.is_expired:
            triggered.append("permit_expired")

        if permit is not None and not permit.is_valid:
            triggered.append("permit_invalid")

        if contractor_recent_violations > CONTRACTOR_VIOLATION_LIMIT:
            triggered.append("contractor_repeat_violations")

        return triggered

    @staticmethod
    def _route_by_band(score: int) -> str:
        """Route by risk score. Bands are exhaustive and non-overlapping."""
        if score < THRESHOLD_LOW:
            return "auto_log"
        if score < THRESHOLD_HIGH:
            return "safety_officer"
        if score < THRESHOLD_CRITICAL:
            return "hse_manager"
        return "escalation_committee"
