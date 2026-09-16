# Wave 2/3 schema stubs (DB-01)

These tables are **not created** until the owning agent needs them. Creating
unused tables is dead weight and a merge-conflict risk.

## CON-01 (Wave 2, now active) — created

`consumer_scans` — see `schema.sql`. Distinct from inspector `inspections`.

## FSSAI-01 (Wave 2, now active) — created

`fssai_inspection_results` — parallel domain; does not mutate `overall_status`.

## RULE-02 (Wave 2, now active) — created

`openl_deploy_manifest` — durable copy of the file-backed zip manifest.

## RAG-02 (Wave 2, now active) — created

`knowledge_chunk_embeddings` — JSONB vectors. `CREATE EXTENSION vector` is
attempted and ignored when the postgres image has no pgvector.

## CON-02 (Wave 3, not in this pass) — stub only

```sql
-- CREATE TABLE consumer_reports / complaints (
--   report_id TEXT PRIMARY KEY,
--   scan_id TEXT REFERENCES consumer_scans(scan_id),
--   reporter_key TEXT,
--   status TEXT,           -- OPEN | TRIAGED | CLOSED
--   body TEXT,
--   created_at TIMESTAMPTZ
-- );
```

## AUTH-01 (Wave 3, not in this pass) — stub only

```sql
-- CREATE TABLE authority_cases (
--   case_id TEXT PRIMARY KEY,
--   inspection_id TEXT REFERENCES inspections(inspection_id),
--   assigned_to TEXT,
--   status TEXT,           -- OPEN | ASSIGNED | RESOLVED
--   created_at TIMESTAMPTZ
-- );
```

Do **not** add `authority` or `consumer` rows to `users.role`. RBAC stays
inspector / reviewer / admin unless ARCH-01 signs an SCR.
