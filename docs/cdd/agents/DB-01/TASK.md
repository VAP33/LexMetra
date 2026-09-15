# CDD Package — DB-01 (Database / Migrations)

(Verbatim from `CDD/Wave 1/5 DB-01.md`, copied here for persistent context.)

**Agent ID:** DB-01
**Role:** Shared-resource gatekeeper for schema changes. Every later agent that needs a new table or column (FSSAI, Consumer, Authority, Analytics) comes through you so migrations don't collide.

**Purpose:** Own `backend/db/schema.sql` and `persistence.py`, and prepare (don't yet build, unless a Wave 1 agent needs it now) the migration path for tables Wave 2/3 agents will need.

**You must:**
1. Read the current schema fully: `products`, `inspections`, `inspection_facts`, `users`, `audit_log` tables (per README + IMPLEMENTATION_STATUS.md), including the idempotent `ALTER TABLE ... IF NOT EXISTS` migration pattern already established — follow that same pattern for any new migrations, don't introduce a different migration mechanism.
2. For Wave 1, your immediate job is small: confirm the schema is stable and documented for OCR-01, EVID-01, and RULE-01 to build against without needing schema changes yet. If any of them do need a column addition (e.g. RULE-01 might need an `openl_rule_version` column on `inspection_facts` to track which engine produced which verdict during the parity period), review and approve that specific addition — but don't add anything speculative.
3. Prepare (as documentation, not code, until the owning agent is active) a stub migration plan for tables Wave 2/3 will need: an FSSAI results table (FSSAI-01), a `complaints`/`consumer_reports` table (CON-02), an `authority_cases` table (AUTH-01). Sketch the shape now so those agents aren't starting from zero, but don't create the tables before those agents actually need them — an unused table is dead weight and a merge-conflict risk.
4. Confirm Postgres 16 + the existing `docker-compose.yml` volume setup (`lmpc_pgdata`) correctly persists across container restarts — a quick real check (start, write, restart, confirm data survived), not an assumption.

**You must NOT:**
- Create Wave 2/3 tables before those agents are active — this just creates dead schema and merge risk for no current benefit.
- Change existing table structures without checking every consumer first (`persistence.py`, and anything RULE-01/OCR-01/EVID-01 touch) — this table set is load-bearing for the whole running system.

## CONTEXT.md

- `backend/db/persistence.py` (39K) and `schema.sql` (13K) are real and tested per the README (scan → save → list → detail → mark-reviewed → product-history, confirmed over actual SQL round-trips).
- Migration pattern already in use: idempotent `ALTER TABLE ... IF NOT EXISTS` blocks run at startup, not a separate migration tool (no Alembic in `requirements.txt`) — this is a deliberate lightweight choice for the current stage; don't introduce a heavier migration framework without checking with ARCH-01 first, since it would be a meaningful architecture change.
- Redis is explicitly documented (in `docker-compose.yml` comments) as "operational cache only — never source of legal truth." Do not let any future migration accidentally make Redis load-bearing for anything legal/audit-related.

## CONTRACTS.md

**Contract you own:** `backend/db/schema.sql`, migration pattern, `persistence.py`'s public functions.
**Contract you consume:** nothing blocking for Wave 1 — you can start immediately alongside ARCH-01/TEST-01/DEVOPS-01.
**Contract you produce:** the stub migration sketches for FSSAI-01, CON-02, AUTH-01 to build from when their waves start.
