# WORKLOG — TEST-01

## 2026-09-15 — Establish the real test baseline
- What I did:
  - Stood up the runtime the suite needs: Python venv + `backend/requirements.txt`, Tesseract OCR, PostgreSQL 16, Redis, and later `poppler-utils`. Created a disposable `lmpc_test` database.
  - Ran the full backend suite multiple ways and recorded actual counts (not file counts).
  - Classified every skip by cause (test isolation / missing data / missing system dep).
  - Verified specific README claims by running the code path, not by trusting prose.
  - Wrote `docs/cdd/TEST-BASELINE.md` (the regression floor) and these package files.
- What I verified (tests run, commands executed, actual output):
  - `python -m pytest backend/tests` (demo `.env`): **469 passed, 15 skipped**, 0 failed/errored, 76% coverage.
  - Clean-DB run: `DATABASE_URL=…/lmpc_test LMPC_BOOTSTRAP_DEMO_USERS=false LMPC_DEV_MODE=true python -m pytest backend/tests --cov=backend`: **480 passed, 4 skipped**, 0 failed/errored, **78.1% coverage**.
  - Skip reasons (`-rs`): 8× "user already exists…" (auth/test-isolation), 2× "Synthetic dataset image not present", 2× "images dataset/ not present", 5× "pdftotext not installed".
  - OCR degradation: set `pytesseract.tesseract_cmd` to a bogus path, `run_ocr(blank)` → `[]`, no exception. README claim holds.
  - PDF read-back tests pass once `poppler-utils` is installed (`test_report_evidence.py` 28/5 → 33/0).
- What I did NOT verify (assumed, or deferred):
  - The 2 real-photo barcode tests and 2 synthetic-image API tests — data not shipped in this checkout; left skipped, not patched.
  - Differential harness vs OpenL — deferred; no OpenL table exists yet.
  - Did not attempt to raise coverage; measuring, not changing, is the mandate.
- Files touched:
  - `docs/cdd/TEST-BASELINE.md` (new)
  - `docs/cdd/TEST-01/STATE.md`, `WORKLOG.md`, `DECISIONS.md`, `HANDOFF.md` (new)
  - Artifacts: `test_baseline_clean_output.log`, `test_baseline_full_output.log`, `test_baseline_clean.xml`, `coverage.json`, `skip_reasons.txt`.
  - No production/test code changed.
