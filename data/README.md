# Data

**No real site imagery, permits, or contractor records are committed to this repository.**

## Directory purpose

| Path | Contents | Committed? |
|---|---|---|
| `sample_images/` | Public PPE detection samples (Roboflow Construction Site Safety dataset) | No — download locally |
| `regulations/` | Publicly available regulatory summaries used for the RAG corpus | Yes (text only) |
| `permits/` | Synthetic permit-to-work samples for document validation testing | No — generate locally |

## Sourcing the CV dataset

The PPE detection model is fine-tuned on a publicly available construction site safety dataset.
Download it locally into `sample_images/` — do not commit.

## Regulatory corpus

The RAG index is built from publicly available summaries of OSHAD, TRAKHEES, MOMRA, and ISO 45001
guidance. These are **summaries, not authoritative full text**.

> This is an architecture demonstrator, not an accredited compliance tool.
