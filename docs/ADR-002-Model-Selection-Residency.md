# ADR-002: Model Selection and Data Residency Findings in UAE North

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-02 |
| **Author** | Nadeem Ahmad |
| **Relates to** | ADR-001 §4.1 (data residency), §6 (accepted risks), §9 (open questions) |

---

## 1. Context

ADR-001 §4.1 argued for Azure over AWS and GCP primarily on **data residency** — that UAE North allows regulated GCC workloads to keep data in-region. Open question #1 in §9 flagged that this assumption needed verification: was GPT-4o actually deployable in UAE North, and under what conditions?

This ADR records what provisioning revealed. The assumption was partly correct and partly not, and the distinction matters for how the platform's residency posture is described.

---

## 2. Findings

### 2.1 Chat models are GlobalStandard-only in UAE North

Every chat-capable model available in UAE North — GPT-4o, the GPT-5 family, o-series — is offered **only** under `GlobalStandard` or `GlobalProvisionedManaged` SKUs. **No regional `Standard` SKU exists for chat models in this region.**

The practical consequence: under Global Standard, data at rest remains in UAE North, but **inference compute may be routed to available capacity in other Azure regions globally.** This is different from a regional Standard deployment, where processing stays in-region.

### 2.2 Embeddings are available as regional Standard

`text-embedding-3-large`, `text-embedding-3-small`, and `text-embedding-ada-002` **are** offered as regional `Standard` in UAE North.

This matters because the **regulatory corpus is the sensitive, persistent asset** in this system. Because embeddings run regionally, the corpus is embedded and indexed entirely within UAE North. The RAG index — the durable store of regulatory content — never leaves the region.

### 2.3 GPT-4o deprecates within the project lifespan

`gpt-4o` (all versions) carries a deprecation date of **2026-10-01**. The v1 milestone targets 20 August 2026. Building on GPT-4o would mean shipping onto a model retired roughly six weeks later.

---

## 3. Decisions

### 3.1 Model selection

**Chat: `gpt-5.4` (version 2026-03-05), GlobalStandard.**
- Runway to 2027-03-05 — comfortably beyond the project lifespan.
- Four months mature at time of selection, so not bleeding-edge.
- Had allocated quota (1000 units) in the subscription; `gpt-5.5` did not.
- Rejected `gpt-4o` (deprecating), `gpt-5.6-*` (released the same week — too fresh for a stable dependency).

**Embeddings: `text-embedding-3-large` (version 1), regional Standard.**
- Chosen specifically for the regional SKU, to keep the corpus in-region.

### 3.2 Residency posture (amends ADR-001 §4.1)

The data-residency claim in ADR-001 is refined to:

> The regulatory corpus — the sensitive, persistent data — is embedded and indexed entirely within UAE North via a regional Standard embeddings deployment. Chat inference data at rest remains in UAE North, but compute may route to global Azure capacity under the GlobalStandard SKU, which is the only chat SKU offered in the region. Full in-region inference would require a Provisioned Managed commitment or a different region, and is deferred as a production-hardening concern.

This is a narrower and more accurate claim than "all processing stays in-region."

---

## 4. Consequences

**Positive**
- The residency statement is now tested and honest, rather than asserted. This is defensible to an auditor or interviewer.
- The corpus — the part that actually matters for regulatory sensitivity — genuinely stays in-region.
- Model choice is future-proofed past the project lifespan.

**Accepted**
- Chat inference may leave the region under Global Standard. For an accredited production deployment this would need revisiting (Provisioned Managed, or a region offering regional chat SKUs). Documented as a hardening-path item, not solved in v1.

---

## 5. Verification

```
Resource group:    rg-safewatch-ai (UAE North)
OpenAI account:    safewatch-openai
Deployments:
  gpt-5.4                  GlobalStandard   (chat)
  text-embedding-3-large   Standard         (embeddings, regional)
```
