# DECISIONS — EVID-01

## 2026-09-16 — Read-model, not a producer change
- Context: Package forbids changing OCR/CV/rule outputs.
- Decision: `evidence_view.build_evidence_chain` reads persisted inspection JSON + facts. Missing bbox/engine is shown as not observed, not invented.
- Why: Honesty invariant (absence ≠ non-compliance) must survive the viewer.
- Reversible? Yes.

## 2026-09-16 — Contract documented for FE-02 simplification
- Decision: Inspector gets full chain (bboxes, rule IDs). Consumer/FE-02 must use CON-01's simplified shape, not this endpoint.
- Why: CON-01 must not leak internals.
- Reversible? No without an SCR.
