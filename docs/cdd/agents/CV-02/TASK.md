# CDD Package — CV-02 (Tamper/Sticker Detection Upgrade)

(Verbatim from `CDD/Wave 2/CV-02.md`, copied here for persistent context.)

**Agent ID:** CV-02
**Depends on:** nothing blocking — start immediately. Low collision risk with CV-01, but confirm before changing shared preprocessing utilities both of you might touch.

**Purpose:** Move `sticker_detection.py` from a pure heuristic baseline toward a more defensible tamper-suspicion signal, while preserving its explicitly advisory-only status (USP4 — it flags for human review, it never issues a verdict).

**You must:**
1. Read `sticker_detection.py` fully, including its own docstring on scope — it is explicitly heuristic and advisory, and that framing must not change; you are improving detection quality, not upgrading it to an authoritative verdict.
2. Assess what real training data exists for tamper/sticker anomalies specifically — this is likely thinner than layout data (real tampered-label examples are hard to source ethically and legally). Be honest in your STATE/WORKLOG about what you could and couldn't validate against real examples versus synthetic/simulated tampering (e.g. synthetically overlaying a sticker on a real product photo).
3. If a trained-classifier upgrade isn't realistically validatable with available data, focus instead on **strengthening the heuristic signal set** (e.g. edge-consistency checks, print-pattern discontinuity, color/texture boundary analysis) and on making the advisory output more informative (which specific heuristic fired, not just a single suspicion score) — this is real, useful, honestly-scoped progress even without a trained model.
4. Ensure the output remains capped appropriately: sticker/tamper suspicion feeds into `review_required=True` and a `RuleFinding` with `status` never stronger than `UNCERTAIN` on its own — it must never independently drive a `FAIL`, per the existing invariant that a CV anomaly is a reason for human review, not a legal finding by itself.

**You must NOT:**
- Let sticker-detection output drive `status=FAIL` directly. Per the existing architecture (and the frozen invariants in `01-CONTRACTS.md` §1.3), this signal caps at `UNCERTAIN`/`review_required=True` — never a standalone violation.
- Claim a trained-classifier accuracy number without disclosing exactly what it was validated against (synthetic overlays vs. real tampered samples are very different claims).

## CONTEXT.md

- `sticker_detection.py` — classical CV, explicitly documented as advisory-only, matching USP4 in the vision exactly.
- Real tampered-product photos are unlikely to exist in the current dataset (`dataset/real images/`, `dataset/images dataset/`) — check what's actually there before assuming otherwise, but plan for the likely case that you're working mostly with synthetic simulation.

## CONTRACTS.md

**Contract you consume:** `ExtractedFact`/`RuleFinding` shape (ARCH-01/`schema.py`) — your output feeds into these unchanged.
**Contract you produce:** an improved (or more informative) tamper-suspicion signal for EVID-01's evidence viewer to display — coordinate the exact shape with EVID-01 if it changes from today's single suspicion score.
