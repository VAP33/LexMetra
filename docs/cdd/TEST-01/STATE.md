# STATE — TEST-01
Last updated: 2026-09-15

## Current phase
done (Wave 0 baseline) — differential harness deferred until RULE-01 delivers OpenL

## What exists right now (verified by me, not assumed)
- `docs/cdd/TEST-BASELINE.md`: written; the regression floor. 480 passed / 4 skipped / 0 failed / 0 errored on a clean test DB; 78.1% coverage. Verified by running pytest and reading output.
- Full backend test suite: 484 tests, 32 modules + 3 under `tests/regulatory/`. Runs green (no failures/errors) in both the demo `.env` and clean-DB configurations.
- Coverage: 78.1% total (clean-DB run), measured with `pytest-cov` (`coverage.json` artifact).
- OCR graceful-degradation claim: verified — `run_ocr` returns `[]` (no crash) when the Tesseract binary is absent.
- Environment: venv at `/workspace/.venv`, Postgres 16 + Redis running, Tesseract 5.3.4, poppler-utils installed. `lmpc` (demo/dev) and `lmpc_test` (disposable test) databases exist.

## What is NOT done yet
- Differential test harness (old `rule_engine.py` vs OpenL). Blocked: no OpenL decision table exists yet (RULE-01).
- 4 residual skips are data-gated, not fixed here (see Blocked on / DECISIONS): synthetic `dataset/images/prod001_compliant.png` and the `images dataset/` barcode fixtures are not in the checkout.

## Blocked on
- Differential harness: RULE-01's first working OpenL decision table.
- 2 barcode + 2 API skips: missing fixture data (owned by the dataset/barcode owners, not TEST-01 — flagged, not patched).

## Next action
When RULE-01 publishes an OpenL decision table, build the differential harness:
feed shared `ProductInspection` fixtures to both `rule_engine.run_inspection`
and the OpenL service, diff the verdicts/facts, and emit a report. Wire it into
`docs/cdd/TEST-BASELINE.md` as an additional gate before any production cutover.
