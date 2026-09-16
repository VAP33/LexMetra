# STATE — DB-01
Last updated: 2026-09-16

## Current phase
partial — Wave 2 tables created because owning agents are active; Wave 3 stubbed only

## What exists right now (verified by me, not assumed)
- `backend/db/schema.sql` additive tables: `consumer_scans`, `fssai_inspection_results`, `openl_deploy_manifest`, `knowledge_chunk_embeddings`.
- `CREATE EXTENSION IF NOT EXISTS vector` wrapped so stock `postgres:16-alpine` still boots.
- `backend/db/persistence.py`: save/get consumer scan, FSSAI results, truncate of new tables in test cleanup.
- `backend/db/WAVE23_STUBS.md`: CON-02 `consumer_reports`, AUTH-01 `authority_cases` as comments only. No extra RBAC roles.

## What is NOT done yet
- Proven persist-across-restart of `lmpc_pgdata` this session (compose up not run here).
- Native pgvector column type (JSONB used so CI image works).
- Alembic — not introduced (follows existing IF NOT EXISTS pattern).

## Blocked on
- Nothing for Wave 1 consumers (OCR/EVID/RULE-01 needed no schema change).
- pgvector image swap is DEVOPS-01 / optional.

## Next action
On a live compose stack: insert one `consumer_scans` row, restart Postgres, confirm the row survives. Then stop. Do not create CON-02/AUTH-01 tables yet.
