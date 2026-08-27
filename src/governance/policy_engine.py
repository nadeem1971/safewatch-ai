"""
Governance Agent — Deterministic Policy Engine.

The heart of SafeWatch AI's safety guarantee. Decides how each assessed
incident is routed for human review. Deterministic by design: the same inputs
always produce the same routing, decided by hard-coded policy, never by model
judgment.

    The LLM proposes. Deterministic policy disposes. A human approves.

An LLM must never be the final arbiter of a safety escalation. Upstream agents
may use models to *propose* findings, but the routing decision is made here, in
auditable code.

Routing is computed as the *maximum* of:
    1. The route implied by the risk-band (score).
    2. The route each hard override demands.

This is graduated escalation: an override lifts the route to at least its own
level, but never lowers it. A high risk score already routing to the escalation
committee is not pulled down by a lesser override, and a lesser override on a
low score still lifts it to that override's level. The final route is always
the most cautious of all applicable rules.

Every decision records the policy version, the specific rules that fired, and
the actions the decision blocks — so any historical decision is fully
explainable against the rules in force at the time.
"""

from __future__ import annotations

from src.contracts import GovernanceDecision, PermitValidation, RiskAssessment

# Bump when any rule below changes. Recorded on every decision for auditability.
POLICY_VERSION = "2.0.0"

# Risk band thresholds. Bands are exhaustive and non-overlapping.
# Convention: lower bound inclusive, upper bound exclusive.
THRESHOLD_LOW = 30  # < 30        -> auto_log
THRESHOLD_HIGH = 60  # 30..59     -> safety_officer
THRESHOLD_CRITICAL = 80  # 60..79 -> hse_manager;  >= 80 -> escalation_committee

CONTRACTOR_VIOLATION_LIMIT = 3

# Ordered escalation ladder. Higher index = more scrutiny.
# max_route() uses this to take the most cautious applicable route.
_ROUTE_ORDER = {
    "auto_log": 0,
    "safety_officer": 1,
    "hse_manager": 2,
    "escalation_committee": 3,
}


def max_route(current: str, candidate: str) -> str:
    """Return the higher-scrutiny of two routes. Never lowers the route."""
    return candidate if _ROUTE_ORDER[candidate] > _ROUTE_ORDER[current] else current


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

        The route starts at the risk-band level, then each hard override lifts
        it toward more scrutiny (never less). The result is the maximum of all
        applicable rules.
        """
        # Base route from the risk band.
        route = self._route_by_band(risk.score)
        triggered_rules: list[str] = [f"risk_band.{risk.band}"]
        overrides: list[str] = []
        blocked_actions: list[str] = []

        # --- Hard overrides: each lifts the route to at least its own level ---

        if permit is not None and permit.is_expired:
            overrides.append("permit_expired")
            triggered_rules.append("hard_override.permit_expired")
            blocked_actions.append("close_incident_without_hse_review")
            route = max_route(route, "hse_manager")

        if permit is not None and not permit.is_valid:
            overrides.append("permit_invalid")
            triggered_rules.append("hard_override.permit_invalid")
            route = max_route(route, "hse_manager")

        if contractor_recent_violations > CONTRACTOR_VIOLATION_LIMIT:
            overrides.append("contractor_repeat_violations")
            triggered_rules.append("hard_override.contractor_repeat_violations")
            route = max_route(route, "escalation_committee")

        return GovernanceDecision(
            route=route,
            hard_overrides_triggered=sorted(set(overrides)),
            policy_version=self._policy_version,
            requires_human_approval=(route != "auto_log"),
        )

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
