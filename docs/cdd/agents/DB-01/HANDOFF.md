# HANDOFF — DB-01
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
Schema is still idempotent SQL at startup. Wave 2 got real tables. Wave 3 did not. Redis remains non-legal. Do not add `consumer`/`authority` roles in `users.role`.

## What I own that is now stable
- Additive DDL in `schema.sql` for the four Wave 2 tables.
- `WAVE23_STUBS.md` sketches.

## What I own that is still in flux
- pgvector native type
- Restart-persistence demonstration on this host

## Contracts I changed
- Additive tables only. No change to `inspections` / `inspection_facts` columns.

## Open questions
- Should OpenL deploy records live only in JSONL (`openl/manifests/`) or also always in SQL? Both exist; SQL is the durable copy.
