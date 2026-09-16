# STATE — FSSAI-01
Last updated: 2026-09-16

## Current phase
partial — parallel engine + JSON rules; gazette not ingested; OpenL FSSAI project not built

## What exists right now (verified by me, not assumed)
- `rules/rules_fssai.json` — separate file, `module: fssai`, every rule `needs_official_verification`, `corpus_status: unsourced_implementation_encoding`.
- `backend/fssai/engine.py`: evaluates licence / veg mark / ingredients / date. **Absence → UNCERTAIN, never FAIL.**
- `GET /inspections/{id}/fssai` + persist `fssai_inspection_results`. Does not mutate `ProductInspection.overall_status` (ARCH-01 D-07).
- Tests: `backend/tests/test_fssai_engine.py`.

## What is NOT done yet
- Verbatim FSSAI gazette/regulation text (same honesty bar as RAG-01).
- OpenL decision tables for FSSAI (RULE-02 pipeline can record a zip; none generated).
- Additive `module_statuses` on ProductInspection (blocked on ARCH-01; D-07 deferred).

## Blocked on
- Official text sourcing (human Legal Lead / downloadable gazette).
- RULE-01-style OpenL project for a second domain (time/data, not a frozen-contract block).

## Next action
Replace implementation-encoding rule text with sourced clauses, keeping the parallel file. Do not merge into `rules.json`.
