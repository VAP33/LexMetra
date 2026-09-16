# HANDOFF — RULE-03
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
Gazette→diff is a library, not a full reviewer product. The load-bearing new behavior is **refuse ACTIVE** if RULE-02 cannot record a new zip. Do not bypass `amendments.py` to force ACTIVE.

## What I own that is now stable
- Failure semantics for OpenL redeploy at the ACTIVE seam.

## What I own that is still in flux
- Reviewer UI
- Quality of OCR on gazette scans

## Contracts I changed
- None of frozen inspection models.

## Open questions
- Where should operators upload gazette images? New authenticated endpoint vs existing amendment drafts API — not added this pass.
