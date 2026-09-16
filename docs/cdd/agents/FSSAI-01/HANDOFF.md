# HANDOFF — FSSAI-01
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
FSSAI is a second module, not a Legal Metrology rule family. Findings use `RuleFinding` and four statuses. `overall_status` is still LMPC-only. Rule text is **not** gazette.

## What I own that is now stable
- File split `rules/rules_fssai.json`
- Evaluator semantics (UNCERTAIN on absence)

## What I own that is still in flux
- Sourced legal wording
- OpenL FSSAI zip

## Contracts I changed
- Additive HTTP `GET /inspections/{id}/fssai`. Draft in `01-CONTRACTS.md`.

## Open questions
- Food vs non-food routing: evaluator uses inspection category heuristics (`_FOODISH`). Confirm with ARCH-01 if non-food should be `NOT_APPLICABLE` without running rules.
