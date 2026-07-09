"""
SafeWatch AI - Interface Contracts

Every agent returns a typed model and nothing else. No dicts across
boundaries, no shared mutable state. These are the seams that let each
agent be built and tested in isolation.

Changes here ripple through every module. Change deliberately.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

ViolationType = Literal[
    "missing_helmet",
    "missing_vest",
    "missing_harness",
    "unsafe_zone_entry",
]

RiskBand = Literal["low", "medium", "high", "critical"]

Route = Literal[
    "auto_log",
    "safety_officer",
    "hse_manager",
    "escalation_committee",
]


class Detection(BaseModel):
    """Output of the Vision Agent. One instance per detected violation."""

    violation_type: ViolationType
    confidence: float = Field(ge=0.0, le=1.0)
    bounding_box: tuple[int, int, int, int] | None = None
    worker_count: int = Field(ge=0)


class PermitValidation(BaseModel):
    """Output of the Document Agent."""

    permit_id: str
    is_valid: bool
    is_expired: bool
    expiry_date: date | None = None
    missing_approvals: list[str] = Field(default_factory=list)
    work_type: str
    zone_classification: str


class RegulationCitation(BaseModel):
    """
    Output of the RAG Agent.

    Every field must be grounded in a retrieved clause. If retrieval
    returns nothing, the agent returns no citation. It does not generate one.
    """

    regulation: str
    clause: str
    text: str
    source_uri: str
    compliance_status: Literal["compliant", "non_compliant"]


class RiskAssessment(BaseModel):
    """Output of the Risk Scoring Agent."""

    score: int = Field(ge=0, le=100)
    band: RiskBand
    contributing_factors: list[str] = Field(default_factory=list)
    rationale: str


class GovernanceDecision(BaseModel):
    """
    Output of the Governance Agent.

    Produced by deterministic policy, never by model judgment.
    The LLM proposes. Deterministic policy disposes. A human approves.
    """

    route: Route
    hard_overrides_triggered: list[str] = Field(default_factory=list)
    policy_version: str
    requires_human_approval: bool
