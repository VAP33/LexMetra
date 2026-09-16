# STATE — RULE-02
Last updated: 2026-09-16

## Current phase
partial — immutable zip manifest + dated resolve; builder still exemption-specific

## What exists right now (verified by me, not assumed)
- `backend/openl/pipeline.py`: `DeployRecord`, `record_deploy`, `resolve_zip_for_date` (returns **None** if no zip covers the date — never "today's" zip by accident).
- Manifest file `backend/openl/manifests/deploy_manifest.jsonl` plus SQL `openl_deploy_manifest`.
- Does **not** migrate extra rules (RULE-01 step 4).
- Does **not** touch `exemption.py` / `rule_engine.py`.
- Tests: `backend/tests/test_openl_pipeline.py` — **3 passed** (re-run after import fix).

## What is NOT done yet
- Shared xlsx builder that emits tables for Rule 6/7/8/24/26-partial/Second Schedule from `rules.json`.
- Automatic prod repo-zip copy into `/opt/openl/local/repositories/zipped/`.

## Blocked on
- RULE-01 remaining-rule specs for a generalized generator (can still extend the builder independently).

## Next action
Extract a `build_openl_workbook(rule_spec) -> xlsx` from `build_exemption_project.py` without changing the exemption zip that already passed 1532-case parity.
