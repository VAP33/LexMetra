# HANDOFF — EVID-01
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
Inspectors can load `GET /inspections/{id}/evidence`. The React viewer consumes it and states the three honesty rules in copy. FE-02 must not reuse this payload as-is.

## What I own that is now stable (safe for others to depend on)
- Evidence JSON shape in `evidence_view.py` / `01-CONTRACTS.md` ownership table.

## What I own that is still in flux
- Live UI against stored inspections with on-disk images.

## Contracts I changed
- New additive HTTP contract only. Frozen pipeline models untouched.

## Open questions
- Should stored inspections stream the original image bytes from this endpoint, or only a URL? Today: URL + `image_path_present`.
