# HANDOFF — CV-02
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
Sticker detection is still advisory. Score is richer; legality is not. EVID-01 can show the finding reason. Never map this to FAIL in CON-01 copy either.

## What I own that is now stable
- Extra signal keys on the sticker region object.
- UNCERTAIN cap in `rule_engine.py`.

## What I own that is still in flux
- Thresholds (0.18 color, 0.20 pattern) — heuristic, not calibrated.

## Contracts I changed
- Additive RuleFinding id. Frozen FactStatus usage only.

## Open questions
- Should advisory findings be omitted from consumer `items[]`? CON-01 currently maps facts; keep language non-accusatory.
