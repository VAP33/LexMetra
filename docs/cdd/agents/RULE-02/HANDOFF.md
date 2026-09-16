# HANDOFF — RULE-02
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
RULE-03's ACTIVE hook should call `record_deploy` / refuse ACTIVE when zip resolve fails. FSSAI-01 should reuse `module="fssai"` on DeployRecord rather than a second scheme. Remaining LMPC decision tables are still RULE-01's job.

## What I own that is now stable
- `DeployRecord` fields
- Dated zip resolve

## What I own that is still in flux
- Generic xlsx generator

## Contracts I changed
- Manifest format (additive). No pipeline Pydantic freeze break.

## Open questions
- Should a missing zip for `inspection_date` fail the inspection or fall back to `rule_engine.py`? Today production still uses `rule_engine.py` entirely (`LMPC_ENABLE_OPENL` default false).
