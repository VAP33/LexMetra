# DECISIONS — CV-02

## 2026-09-16 — No FAIL from sticker CV
- Context: Package forbids sticker suspicion driving FAIL.
- Decision: new finding id `ADVISORY-CV-STICKER`, status always UNCERTAIN. Existing `__possible_alteration__` facts remain UNCERTAIN.
- Why: USP4 + §1.3 (CV anomaly ≠ legal finding).
- Reversible? No without ARCH-01 SCR.

## 2026-09-16 — Heuristics over an unvalidatable classifier
- Decision: do not train. Strengthen signals and name which heuristic fired.
- Why: no honest real-tamper validation set.
- Reversible? Yes, if labeled data appears.
