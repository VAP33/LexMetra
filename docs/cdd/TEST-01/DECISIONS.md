# DECISIONS — TEST-01

## 2026-09-15 — Canonical baseline is the clean-DB run, not the demo `.env` run
- Context: The default demo `.env` (with `LMPC_BOOTSTRAP_DEMO_USERS=true`) causes 8 auth-integration tests to skip, because the app's startup re-seeds demo users after the test fixture truncates the DB, defeating the one-shot bootstrap registration.
- Options considered: (a) report the 469/15 demo-env numbers as the baseline; (b) report the clean-DB numbers as canonical and document the demo-env delta.
- Decision: Canonical baseline = clean-DB run (`lmpc_test`, bootstrap off): **480 passed / 4 skipped / 78.1%**. The demo-env numbers are documented as a secondary configuration.
- Why: `conftest.py` explicitly documents the suite expects a "disposable dev/test database". The clean-DB run exercises more real code (auth, JSONB round-trips) and is the honest ceiling of "what passes when run as designed".
- Reversible? Yes, trivially — both configs and their commands are recorded in `TEST-BASELINE.md`.

## 2026-09-15 — Install poppler-utils to unblock PDF read-back tests
- Context: 5 `test_report_evidence.py` tests skip without `pdftotext`.
- Options considered: leave skipped and report; or install `poppler-utils` (an environment dependency, not a code change) and report the true result.
- Decision: Installed `poppler-utils`; those 5 now run and pass. Documented that it is an env dependency not currently declared as required.
- Why: TEST-01's job is ground truth. A skip that a one-line, non-invasive env install converts to a real pass should be reported as a pass, with the dependency called out.
- Reversible? Yes — uninstall poppler and they revert to skips.

## 2026-09-15 — Do NOT patch the data-gated skips (barcode + synthetic image)
- Context: 2 barcode real-photo tests expect an `images dataset/` dir; 2 API tests expect `dataset/images/prod001_compliant.png`. Neither path is in the checkout (though the Bru barcode photo does exist under `dataset/real images/`).
- Options considered: (a) create/symlink the expected dirs or regenerate synthetic images to force the tests to run; (b) leave skipped and document precisely.
- Decision: Leave skipped; document cause, exact expected paths, and the path mismatch. Flag the barcode path mismatch to the barcode/dataset owner.
- Why: TEST-01 must "report accurately, not quietly patch". Fabricating fixture layout or retargeting test paths is a code/data change in another agent's scope and would hide a real gap from the team.
- Reversible? N/A — no change made.

## 2026-09-15 — Differential (old-engine vs OpenL) harness deferred
- Context: The contract requires a differential harness before any OpenL production cutover, but no OpenL decision table exists yet.
- Decision: Defer; record the interface contract in `TEST-BASELINE.md` so RULE-01 can build against it.
- Why: There is nothing to diff against until RULE-01 ships a first OpenL table. Building it now would test nothing.
- Reversible? Yes — it is planned work, not a change.
