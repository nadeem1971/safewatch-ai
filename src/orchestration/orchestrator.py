"""
SafeWatch AI - LangGraph orchestration.

Wires the agents into one deterministic pipeline:

    vision -> document -> rag -> risk -> governance -> report

State flows through a typed dict; each node reads what it needs and writes its
result. The graph is linear in v1 (no branching), which keeps the audit trail
simple: every incident traverses every stage in the same order.

The orchestrator itself makes no decisions. It sequences the agents and
assembles the final reviewer packet. All judgement lives in the agents:
retrieval in RAG, scoring in risk, routing in governance - and the human gate
beyond governance. The LLM proposes, deterministic policy disposes, a human
approves; the orchestrator only carries state between those steps.

Real LangGraph is used when installed; a minimal sequential fallback runs the
same nodes in the same order when it is not, so the pipeline is testable in any
environment.
"""

from __future__ import annotations

from typing import TypedDict

from src.agents.stubs import DocumentAgentStub, VisionAgentStub
from src.contracts import (
    Detection,
    GovernanceDecision,
    PermitValidation,
    RegulationCitation,
    RiskAssessment,
    ViolationType,
)
from src.governance.policy_engine import GovernanceEngine
from src.rag.agent import ComplianceRAGAgent
from src.risk.scoring import RiskScoringAgent

try:
    from langgraph.graph import END, StateGraph

    _HAS_LANGGRAPH = True
except ModuleNotFoundError:  # pragma: no cover - environment-dependent
    _HAS_LANGGRAPH = False


class IncidentState(TypedDict, total=False):
    # Inputs
    vision_hint: ViolationType | None
    worker_count: int
    zone_is_elevated: bool
    permit_id: str
    permit_is_valid: bool
    permit_is_expired: bool
    work_type: str
    zone_classification: str
    contractor_recent_violations: int
    # Produced by the pipeline
    detections: list[Detection]
    permit: PermitValidation | None
    citations: list[RegulationCitation]
    risk: RiskAssessment
    governance: GovernanceDecision
    reviewer_packet: dict


class Orchestrator:
    """Sequences the agents into the incident-analysis pipeline."""

    def __init__(
        self,
        rag_agent: ComplianceRAGAgent,
        risk_agent: RiskScoringAgent,
        governance_engine: GovernanceEngine,
        vision_agent: VisionAgentStub | None = None,
        document_agent: DocumentAgentStub | None = None,
    ) -> None:
        self._rag = rag_agent
        self._risk = risk_agent
        self._gov = governance_engine
        self._vision = vision_agent or VisionAgentStub()
        self._document = document_agent or DocumentAgentStub()
        self._compiled = self._build_graph() if _HAS_LANGGRAPH else None

    # --- Nodes ---------------------------------------------------------------

    def _vision_node(self, state: IncidentState) -> IncidentState:
        state["detections"] = self._vision.analyze(
            vision_hint=state.get("vision_hint"),
            worker_count=state.get("worker_count", 1),
        )
        return state

    def _document_node(self, state: IncidentState) -> IncidentState:
        state["permit"] = self._document.validate(
            permit_id=state.get("permit_id", "PTW-DEMO-001"),
            is_valid=state.get("permit_is_valid", True),
            is_expired=state.get("permit_is_expired", False),
            work_type=state.get("work_type", "general"),
            zone_classification=state.get("zone_classification", "standard"),
        )
        return state

    def _rag_node(self, state: IncidentState) -> IncidentState:
        citations: list[RegulationCitation] = []
        for detection in state.get("detections", []):
            citation = self._rag.cite(detection.violation_type)
            if citation is not None:
                citations.append(citation)
        state["citations"] = citations
        return state

    def _risk_node(self, state: IncidentState) -> IncidentState:
        state["risk"] = self._risk.score(
            detections=state.get("detections", []),
            permit=state.get("permit"),
            zone_is_elevated=state.get("zone_is_elevated", False),
        )
        return state

    def _governance_node(self, state: IncidentState) -> IncidentState:
        state["governance"] = self._gov.decide(
            risk=state["risk"],
            permit=state.get("permit"),
            contractor_recent_violations=state.get("contractor_recent_violations", 0),
        )
        return state

    def _report_node(self, state: IncidentState) -> IncidentState:
        """Assemble the reviewer packet - what a human sees at the gate."""
        risk = state["risk"]
        gov = state["governance"]
        state["reviewer_packet"] = {
            "detections": [d.model_dump() for d in state.get("detections", [])],
            "permit": state["permit"].model_dump() if state.get("permit") else None,
            "citations": [c.model_dump() for c in state.get("citations", [])],
            "risk_score": risk.score,
            "risk_band": risk.band,
            "risk_rationale": risk.rationale,
            "route": gov.route,
            "hard_overrides": gov.hard_overrides_triggered,
            "requires_human_approval": gov.requires_human_approval,
            "policy_version": gov.policy_version,
        }
        return state

    # --- Graph ---------------------------------------------------------------

    def _build_graph(self):
        graph = StateGraph(IncidentState)
        graph.add_node("vision", self._vision_node)
        graph.add_node("document", self._document_node)
        graph.add_node("rag", self._rag_node)
        graph.add_node("risk", self._risk_node)
        graph.add_node("governance", self._governance_node)
        graph.add_node("report", self._report_node)

        graph.set_entry_point("vision")
        graph.add_edge("vision", "document")
        graph.add_edge("document", "rag")
        graph.add_edge("rag", "risk")
        graph.add_edge("risk", "governance")
        graph.add_edge("governance", "report")
        graph.add_edge("report", END)
        return graph.compile()

    # --- Public API ----------------------------------------------------------

    def run(self, state: IncidentState) -> IncidentState:
        """Run the full pipeline on one incident, return the final state."""
        if self._compiled is not None:
            return self._compiled.invoke(state)
        # Sequential fallback - same nodes, same order.
        for node in (
            self._vision_node,
            self._document_node,
            self._rag_node,
            self._risk_node,
            self._governance_node,
            self._report_node,
        ):
            state = node(state)
        return state
