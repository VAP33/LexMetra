# STATE — ARCH-01
Last updated: 2026-09-16

## Current phase
done (Wave 0 gatekeeping) + Wave 2 SCR recorder — frozen pipeline models unchanged; additive contracts drafted

## What exists right now (verified by me, not assumed)
- Wave 0 docs still canonical. §6 folded from TEST-01 (`480/4/0`, 78.1% at `ca3d221`).
- `01-CONTRACTS.md` §2.4 exemption JSON recorded; Wave 2 drafts: CON-01 consumer scan, FSSAI per-module GET, RAG-02 embeddings table.
- DECISIONS D-06 (consumer flag+RPM, no new role), D-07 (FSSAI parallel), D-08 (YOLO not shipped).
- `ExtractedFact` / `ProductInspection` / `RuleFinding` still `extra="forbid"` — no silent field adds.

## What is NOT done yet
- Remaining OpenL rules JSON (full RuleSet Resolver aggregation) — RULE-01 cutover still off.
- Optional ProductInspection `module_statuses` (D-07 deferred).
- Changes are written but NOT committed (owner has not asked).

## Blocked on
- Nothing for ARCH-01 docs. DEPENDENCIES archive awaits a tree that exists on disk.

## Next action
Keep §1 frozen. Review any Wave 3 SCR that wants a `consumer` role, `module_statuses` on ProductInspection, or FAIL-from-sticker.
