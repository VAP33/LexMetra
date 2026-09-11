# Build 11 — Final Validation & Production Hardening

Build 11 is the final hardening pass before the repository is handed back for
human verification and the final GitHub push. It does not replace legal review.

## Completed in this worktree

- Removed automatic legal rule activation. Effective dates create eligibility
  only; a scheduled amendment requires explicit human-authorized activation.
- Runtime rule selection now accepts only `ACTIVE` rule versions. `APPROVED` and
  `SCHEDULED` records cannot silently become applicable merely because their
  effective date has arrived.
- Preserved historical rule-version intervals and immutable RAG chunk checks.
- Kept Redis strictly operational/non-authoritative. Regulatory truth remains
  in the dated rule/RAG persistence layer.
- Added a regression test proving that `APPROVED` and `SCHEDULED` versions are
  not runtime-eligible until explicit activation.
- Added the missing Anthropic SDK declaration for the optional VLM provider.
- Removed local secrets and runtime-generated database/upload/report artifacts
  from the deliverable worktree; `.gitignore` now matches the repository's
  secret/runtime-artifact policy.
- Preserved the PaddleOCR child-process isolation introduced in Build 10 so a
  native Paddle runtime failure cannot crash the API process.

## Validation completed here

- Build 04–11 focused safety/RAG/publication suites: **101 passed, 0 failed**.
- Current broader backend suite excluding `test_auth.py`: **385 passed, 15 skipped**.
- `test_auth.py` could not be collected in this offline environment because the
  Python environment does not contain `python-jose`/`passlib`; network package
  installation also failed because package-index DNS is unavailable. This is an
  environment limitation, not evidence that authentication is correct.
- Full-suite attempt stopped at auth collection for the same missing dependency.
- Python compilation of the manually restored/hardened core modules passed.

## Remaining acceptance gates

1. Install backend dependencies in a networked/clean environment and run the
   complete suite including authentication.
2. Run Docker Compose validation and startup with PostgreSQL + Redis.
3. Run the real-image OCR/vision benchmark and confirm multilingual/OCR fallback
   behavior on the committed dataset.
4. Verify the final dashboard/authenticated browser flow and report/audit paths.
5. Reconcile the worktree against the latest GitHub `main`, especially files
   restored from the stale local snapshot.
6. Perform the final duplicate-tree comparison before any removal of historical
   `Chatgpt Patch/` content that exists on GitHub.
7. Verify every legal rule marked `needs_official_verification` against primary
   government sources before treating those thresholds as legally verified.

## Safety invariants

AI extracts evidence. RAG retrieves knowledge. Applicability determines scope.
The deterministic rule engine determines compliance. Humans resolve material
uncertainty and authorize legal activation.

Never treat `NOT_OBSERVED` as `FAIL`; never infer a legal rule without a source;
never apply a future rule to a historical inspection; never let RAG absence,
VLM absence, barcode absence, pHash results, or uncalibrated measurement create
an unsupported legal conclusion.
