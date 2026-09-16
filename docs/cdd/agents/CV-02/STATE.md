# STATE — CV-02
Last updated: 2026-09-16

## Current phase
partial — stronger heuristics + UNCERTAIN cap; no trained tamper classifier

## What exists right now (verified by me, not assumed)
- `sticker_detection.py`: extra signals `color_boundary` and `print_pattern_discontinuity`. Suspicion **score formula otherwise unchanged**.
- `rule_engine.py`: `ADVISORY-CV-STICKER` `RuleFinding` with `status=UNCERTAIN` only, `review_required=True`, `verification_status=advisory_not_a_legal_rule`.
- No real tampered-pack photos in `dataset/real images/` used as a labeled train set.
- Tests: `backend/tests/test_sticker_advisory.py`.

## What is NOT done yet
- Trained classifier with disclosed synthetic-vs-real validation.
- EVID-01 display of per-heuristic scores beyond the finding reason string (reason lists fired heuristic names).

## Blocked on
- Ethical/legal source of real tampered labels (data, not architecture).

## Next action
Keep the advisory cap. If synthetic overlays are used later, label them synthetic in WORKLOG and never quote that accuracy as real-tamper performance.
