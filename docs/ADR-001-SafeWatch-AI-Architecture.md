# ADR-001: SafeWatch AI — Architecture Decision Record

| | |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-07-09 |
| **Authors** | Nadeem Ahmad, Ashifa Nassar |
| **Supersedes** | — |

---

## 1. Context

Construction and industrial sites across the GCC operate under strict occupational safety regimes — OSHAD (Abu Dhabi), TRAKHEES (Dubai), and MOMRA (Saudi Arabia). Compliance today is predominantly manual: a safety officer walks the site, observes violations, cross-references regulations from memory or a binder, and files a report after the fact.

This creates three failure modes:

1. **Reactive detection** — violations are found after an incident, not before.
2. **Inconsistent enforcement** — whether a violation is escalated depends on which officer saw it.
3. **Weak auditability** — when a regulator asks *why* a decision was made, the trail is thin.

SafeWatch AI addresses this by combining computer vision, retrieval over the regulatory corpus, and agentic orchestration into a system that detects violations, cites the governing regulation, scores risk, applies deterministic policy, and routes to a human for approval — with every decision logged.

---

## 2. Decision

We will build SafeWatch AI as a **layered, agent-orchestrated platform on Microsoft Azure**, with LangGraph as the multi-agent orchestration framework and a human-in-the-loop approval gate on every consequential action.

The v1 build covers Layers 1–6 of the reference architecture. Layers 7–8 (Audit Data Lake, Watcher Agent) are documented as Phase 2.

---

## 3. Architecture Overview

### Layers (v1 scope)

| Layer | Purpose | Azure Service |
|---|---|---|
| **1. Data Sources** | Site imagery, permits, regulatory corpus | — |
| **2. Ingestion** | Event-driven landing of unstructured data | Blob Storage + Event Grid |
| **3. AI Processing** | PPE detection, document extraction, regulation retrieval | AI Vision, Document Intelligence, AI Search + Azure OpenAI |
| **4. Agentic Orchestration** | Multi-agent workflow | Container Apps + LangGraph |
| **5. Risk & Governance** | Risk scoring, deterministic policy enforcement | Application logic |
| **6. Human in the Loop** | Approval, escalation, override | Logic Apps + Teams/Email |

### Deferred to Phase 2

| Layer | Rationale for deferral |
|---|---|
| **7. Audit & Data Lake** | Requires historical volume to be meaningful; Cosmos DB incident log is sufficient for v1 traceability |
| **8. Watcher & Intelligence** | Trend detection and predictive forecasting need a data history that does not exist at v1 |

### Agent Flow (v1)

```
Site Image + Permit
        │
        ▼
   Vision Agent ──────► PPE violation detected (helmet / vest / harness / unsafe zone)
        │
        ▼
 Document Agent ──────► Permit validity, expiry, required approvals
        │
        ▼
    RAG Agent ────────► Retrieves governing regulation + clause + citation
        │
        ▼
Risk Scoring Agent ───► Composite score (0–100) from PPE severity, zone class,
        │                worker count, permit status, contractor history
        ▼
Governance Agent ─────► Deterministic policy evaluation → routing decision
        │
        ▼
  Human Approval ─────► Approve / Escalate / Reject / Request Investigation
        │
        ▼
  Incident Record (Cosmos DB)
```

---

## 4. Key Decisions & Rationale

### 4.1 Why Azure (over AWS / GCP)

| Consideration | Rationale |
|---|---|
| **Data residency** | Azure operates UAE North and UAE Central regions — mandatory for regulated GCC workloads |
| **Enterprise fit** | GCC enterprise clients are predominantly Microsoft-first (M365, Teams, SharePoint); HITL notification integrates natively |
| **Sovereign alignment** | Azure underpins the dominant sovereign cloud deployments in the region |
| **Team capability** | Existing depth in Azure architecture and AI services reduces delivery risk |

**Tradeoff accepted:** Azure AI Vision's out-of-the-box PPE detection is less mature than some specialized CV platforms. Mitigated by fine-tuning a pretrained model rather than relying on stock detection.

### 4.2 Why LangGraph (over CrewAI / AutoGen / Semantic Kernel)

- **Explicit state graph** — safety decisions demand a deterministic, inspectable flow. LangGraph's graph model makes the path from detection to decision auditable, which a free-form conversational agent framework does not.
- **Native interrupt/resume** — the human-in-the-loop gate is a first-class primitive, not a bolt-on.
- **Proven pattern** — the same orchestration pattern (governor → policy → executor → HITL) has been delivered in production previously by the team.

**Tradeoff accepted:** LangGraph is Python-centric and less integrated with the Azure SDK surface than Semantic Kernel. Accepted in exchange for orchestration control and auditability.

### 4.3 Why deterministic policy, not LLM-based governance

The Governance Agent evaluates **hard-coded rules**, not model judgment:

```
IF risk_score >= 80          → HSE Manager approval required
IF permit_expired            → Block closure
IF contractor_violations > 3 in 7 days → Escalate to Compliance Director
IF risk_score < 30           → Auto-log, no approval required
```

An LLM must never be the final arbiter of a safety escalation. The LLM *proposes*; deterministic policy *disposes*; a human *approves*. This separation is the core governance principle of the platform.

### 4.4 Why human-in-the-loop is non-negotiable

Every consequential action — escalation, incident closure, contractor flagging — passes a human gate. This is a design constraint, not a v1 limitation. Risk-tiered approval:

| Risk band | Route |
|---|---|
| Low (< 30) | Auto-log |
| Medium (30–59) | Safety Officer review |
| High (60–79) | HSE Manager approval |
| Critical (≥ 80) | Escalation committee |

### 4.5 Why static images in v1, not live CCTV streams

Live stream ingestion adds substantial infrastructure complexity (IoT Hub, stream processing, frame sampling, latency budgets) without changing the core AI or governance logic being demonstrated. Batch/static image processing proves the end-to-end loop. Stream ingestion is a Phase 2 concern.

### 4.6 Why two UIs, not six

The interface footprint is deliberately minimized to two surfaces:

- **Operations Console** — single-screen workflow for safety officers: upload → detect → cite → score → report → submit.
- **Governance Dashboard** — risk visibility, trends, approvals, and audit posture for HSE and executive leadership.

This mirrors how enterprise safety platforms are actually consumed and concentrates effort on the AI and governance layers rather than frontend surface area.

---

## 5. Technology Stack

| Concern | Choice |
|---|---|
| Cloud | Microsoft Azure (UAE North) |
| LLM | Azure OpenAI — GPT-4o |
| Computer Vision | Azure AI Vision / Custom Vision (fine-tuned on public PPE dataset) |
| Document extraction | Azure AI Document Intelligence |
| Retrieval | Azure AI Search (hybrid: vector + semantic) |
| Orchestration | LangGraph |
| Compute | Azure Container Apps |
| Storage | Blob Storage (raw), Cosmos DB (incidents, audit trail) |
| Eventing | Azure Event Grid |
| Notification / HITL | Azure Logic Apps + Teams/Email (MCP) |
| Dashboard | Power BI Embedded |

---

## 6. Consequences

### Positive

- Regulatory citation on every finding makes AI output defensible to auditors.
- Deterministic governance layer bounds LLM authority.
- Layered design allows Phase 2 additions (Watcher, predictive layer) without rearchitecting.
- Azure-native stack aligns with GCC enterprise procurement and data residency requirements.

### Negative / Accepted Risks

| Risk | Mitigation |
|---|---|
| CV model accuracy on real site conditions (lighting, occlusion, distance) | Fine-tune pretrained model; report precision/recall honestly; scope v1 to controlled imagery |
| Azure OpenAI regional quota/availability for GPT-4o | Confirm region availability before build; fallback region identified |
| RAG citation hallucination | Enforce grounded generation; every claim must map to a retrieved clause; measure citation accuracy explicitly |
| Scope creep into Phase 2 features | Layers 7–8 explicitly out of v1; roadmap documented separately |
| Regulatory corpus is publicly summarized, not authoritative full text | Clearly disclosed; platform demonstrates the pattern, not certified compliance |

---

## 7. Success Criteria (v1)

- End-to-end loop executes: image + permit in → violation detected → regulation cited → risk scored → policy applied → human notified → decision recorded.
- RAG agent returns a correct governing clause for at least three distinct violation categories.
- Governance Agent routing matches the approval matrix in all test cases.
- Both UIs functional and demonstrable.
- Precision/recall of the CV model reported honestly against a held-out set.

---

## 8. Explicitly Out of Scope for v1

- Live CCTV stream ingestion
- Predictive risk forecasting / incident probability modelling
- Multi-site and multi-tenant governance
- Production-grade authentication and RBAC
- Mobile application
- Certified regulatory compliance (this is a demonstrator, not an accredited compliance tool)

---

## 9. Open Questions

1. Confirm GPT-4o availability and quota in UAE North; identify fallback region.
2. Finalise risk-scoring weights — currently proposed, requires calibration against sample scenarios.
3. Confirm MCP selection for the HITL notification path.
4. Determine whether contractor history is seeded synthetically for v1 demonstration.

---

## 10. Component Ownership

| Component | Owner |
|---|---|
| LangGraph orchestration | Nadeem |
| Compliance RAG (Azure AI Search) | Nadeem |
| Risk Scoring Agent | Nadeem |
| Governance Agent | Nadeem |
| Azure infrastructure | Nadeem |
| Computer Vision / PPE detection | Ashifa |
| Document Validation | Ashifa |
| Operations Console (UI) | Ashifa |
| Governance Dashboard (UI) | Ashifa |
| HITL workflow & integration | Shared |

---

## 11. Roadmap

| Phase | Content |
|---|---|
| **1 — MVP (current)** | PPE detection, Compliance RAG, Document Validation, Risk Scoring, Governance Agent, HITL |
| **2 — Governance Expansion** | Audit data lake, model/prompt/policy versioning, full traceability |
| **3 — Operational Intelligence** | Watcher Agent, trend analysis, contractor scoring |
| **4 — Predictive Safety** | Risk forecasting, incident probability, preventive recommendations |
| **5 — Enterprise Scale** | Multi-site, multi-tenant governance, executive safety command centre |
