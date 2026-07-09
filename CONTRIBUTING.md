# Contributing to SafeWatch AI

This is a two-person collaborative build. These conventions keep the work parallel and merge-friendly.

---

## Component Ownership

| Component | Path | Owner |
|---|---|---|
| LangGraph orchestration | `src/agents/` | Nadeem |
| Compliance RAG | `src/rag/` | Nadeem |
| Risk Scoring Agent | `src/governance/risk_scoring.py` | Nadeem |
| Governance Agent | `src/governance/policy_engine.py` | Nadeem |
| Azure infrastructure | `infra/` | Nadeem |
| API layer | `src/api/` | Nadeem |
| Computer Vision / PPE detection | `src/vision/` | Ashifa |
| Document Validation | `src/document/` | Ashifa |
| Operations Console | `ui/operations-console/` | Ashifa |
| Governance Dashboard | `ui/governance-dashboard/` | Ashifa |
| HITL workflow & integration | `src/api/hitl.py` | Shared |

**Rule of thumb:** stay inside your own directories. Cross-boundary changes go through a PR with the other owner as reviewer.

---

## Branching

```
main            ← protected, always working
├── feat/vision-ppe-detection
├── feat/compliance-rag
├── feat/risk-scoring
└── feat/ops-console
```

- Branch from `main`, prefix with `feat/`, `fix/`, or `docs/`
- Open a PR into `main` — no direct pushes
- One approval required before merge

---

## Interface Contracts

Because we build in parallel, the **contracts between components are agreed before implementation**. Each component returns a typed Pydantic model. Stub these first, fill them in after.

### Vision Agent → orchestrator

```python
class Detection(BaseModel):
    violation_type: Literal["missing_helmet", "missing_vest",
                            "missing_harness", "unsafe_zone_entry"]
    confidence: float          # 0.0 – 1.0
    bounding_box: tuple[int, int, int, int] | None
    worker_count: int
```

### Document Agent → orchestrator

```python
class PermitValidation(BaseModel):
    permit_id: str
    is_valid: bool
    is_expired: bool
    expiry_date: date | None
    missing_approvals: list[str]
    work_type: str
    zone_classification: str
```

### RAG Agent → orchestrator

```python
class RegulationCitation(BaseModel):
    regulation: str            # e.g. "OSHAD SF38"
    clause: str                # e.g. "Section 5.4"
    text: str
    source_uri: str
    compliance_status: Literal["compliant", "non_compliant"]
```

### Risk Scoring Agent → Governance Agent

```python
class RiskAssessment(BaseModel):
    score: int                 # 0 – 100
    band: Literal["low", "medium", "high", "critical"]
    contributing_factors: list[str]
    rationale: str
```

### Governance Agent → HITL

```python
class GovernanceDecision(BaseModel):
    route: Literal["auto_log", "safety_officer",
                   "hse_manager", "escalation_committee"]
    hard_overrides_triggered: list[str]
    policy_version: str
    requires_human_approval: bool
```

**Changes to these contracts require agreement from both owners before implementation.**

---

## Governance Policy Rules

The policy engine is **deterministic**. Rules are evaluated in this order:

**1. Hard overrides (evaluate first — absolute, regardless of score)**
```
IF permit_expired                          → block_closure
IF contractor_violations > 3 in 7 days     → escalation_committee
```

**2. Risk band routing**
```
IF score < 30                              → auto_log
IF 30 <= score < 60                        → safety_officer
IF 60 <= score < 80                        → hse_manager
IF score >= 80                             → escalation_committee
```

Bands are exhaustive and non-overlapping. Boundary convention is `>= lower, < upper`.

> An LLM must never be the final arbiter of a safety escalation.
> The LLM proposes. Deterministic policy disposes. A human approves.

---

## Code Standards

- **Python:** `ruff` for lint + format, `mypy` for types. Run before pushing.
- **Type hints required** on all public functions.
- **No secrets in code.** Everything through `.env` (see `.env.example`).
- **No real site imagery or real permits committed.** `data/` is gitignored.

```bash
ruff check src/ && ruff format src/ && mypy src/ && pytest
```

---

## Commit Messages

```
feat(vision): add harness detection to PPE model
fix(governance): correct risk band boundary at 30
docs(adr): record LangGraph decision rationale
```

---

## Scope Discipline

**v1 is Layers 1–6.** Layers 7 (Audit Data Lake) and 8 (Watcher Agent, Predictive Safety) are Phase 2 and are **not** to be built now, regardless of how tempting.

If you want to add something outside v1 scope, open an issue tagged `phase-2` rather than a PR.

---

## Disclaimer

This is an architecture demonstrator. The regulatory corpus is drawn from publicly available summaries. It is **not** an accredited compliance tool and must not be used for regulatory certification.
