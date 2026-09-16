# STATE — RULE-03
Last updated: 2026-09-16

## Current phase
partial — gazette OCR→diff + refuse ACTIVE on failed redeploy; no React amendment reviewer UI

## What exists right now (verified by me, not assumed)
- `backend/amendment_gazette.py`: OCR via existing Tesseract path (`run_ocr`), Rule-N mention extract, diff vs `rules.json`, `activate_with_openl_redeploy` that **must not** mark ACTIVE if OpenL zip/redeploy is missing.
- Existing `amendments.py` state machine **not** redesigned (`ACTIVE` still not auto-reachable from the old machine).
- Tests: `backend/tests/test_amendment_gazette.py` (failed-redeploy refuses ACTIVE).
- Gazette OCR not run on a real notification image on this host (no Tesseract).

## What is NOT done yet
- Human review UI in React for DRAFT→REVIEW→APPROVED.
- Live OpenL zip rebuild on SCHEDULED→ACTIVE when effective date arrives.
- Verbatim gazette vs `rules.json` legal accuracy.

## Blocked on
- OCR-01 fusion optional (Tesseract interim is allowed).
- RULE-02 generic builder for non-exemption rules.
- A real gazette sample image.

## Next action
Add a React amendment-diff screen that shows `diff_against_rules_json` output. Keep `verification_status=needs_official_verification` on any threshold change.
