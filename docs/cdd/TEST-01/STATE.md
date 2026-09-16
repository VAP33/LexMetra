# STATE — TEST-01
Last updated: 2026-09-16

## Current phase
done (Wave 0 floor) + partial (OpenL differential harness skip-if-down)

## What exists right now (verified by me, not assumed)
- Floor unchanged: `docs/cdd/TEST-BASELINE.md` **480 passed / 4 skipped / 0 failed / 78.1%** at `ca3d221`.
- `backend/tests/test_openl_differential.py`: skips when OpenL `/admin/healthcheck/readiness` is not 200.
- This host 2026-09-16 full suite (prior run this session): **489 passed, 19 skipped, 3 failed**. Failures: `test_ocr_engine.py` — Tesseract binary absent. Not a code regression vs the TEST-01 host (Tesseract 5.3.4).
- Wave 1/2 focused files 2026-09-16: **24 passed, 3 skipped, 0 failed**.
- Dataset barcode tests retargeted to `dataset_paths` (skip unless Bru photo AND tesseract).

## What is NOT done yet
- Unskipped OpenL differential as a CI gate (remaining rules not migrated; OpenL not in default compose).
- Coverage re-measure of the new modules on a Tesseract host.

## Blocked on
- Tesseract on this workstation for OCR engine tests.
- Running OpenL for unskipped differential.

## Next action
On a Tesseract+Postgres host matching TEST-BASELINE, re-run the full suite and confirm 0 failed. Keep OpenL tests skip-if-down until RULE-01 cutover.
