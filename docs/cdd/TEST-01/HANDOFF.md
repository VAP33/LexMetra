# HANDOFF — TEST-01
Prepared: 2026-09-15

## Summary for the next agent (or my future self)
The backend suite is green: **480 passed, 4 skipped, 0 failed, 0 errored, 78.1%
coverage** on a clean test DB (see `docs/cdd/TEST-BASELINE.md` for exact
commands and per-file counts). There are no genuine code-bug failures anywhere —
every non-pass is a deliberate, classified skip driven by missing fixture data
or an optional dependency. Use `TEST-BASELINE.md` as the regression floor: any
PR that drops a file's pass count or introduces a failure fails review.

## What I own that is now stable (safe for others to depend on)
- `docs/cdd/TEST-BASELINE.md` — the single source of truth for "does this pass
  right now", format `<test file>: <pass>/<skip> as of <commit>`.
- The two reproducible run configurations (clean-DB canonical; demo-`.env`
  secondary) and their exact commands + env vars.
- Verified facts: OCR degrades gracefully without Tesseract; PDF generation +
  read-back works with poppler; Postgres round-trips confirmed.

## What I own that is still in flux (do NOT depend on this yet)
- The differential (legacy `rule_engine.py` vs OpenL) harness — **exists** as skip-if-down (`test_openl_differential.py`). Not a CI gate yet.

## Contracts I changed
- None. No production or test code was modified by TEST-01. Only new docs under
  `docs/cdd/` were added. (Note: the branch also carries two unrelated
  environment fixes — `scikit-learn` in requirements and the Vite `base` path —
  made during environment setup, not part of the TEST-01 report.)

## Open questions I could not resolve myself
- Barcode `TestRealPhotographs`: the expected `images dataset/` path does not
  exist, but the Bru photo it wants IS in `dataset/real images/`. Should the
  barcode-test owner retarget the fixture path, or should the dataset be
  reorganized? (Out of TEST-01 scope to change.)
- Synthetic `dataset/images/prod001_compliant.png` is referenced by 2 API tests
  but not shipped. Should `dataset/generate_dataset.py` output be committed, or
  should CI regenerate it before the run?
- `poppler-utils` is required for the PDF read-back tests but is not declared as
  a dependency anywhere — should it be added to the container/docs as a test dep?
