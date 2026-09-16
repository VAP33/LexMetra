# DECISIONS — RULE-02

## 2026-09-16 — Dated resolve returns None, not latest
- Context: Inspecting a historical pack with "whatever zip is on disk" would time-travel verdicts.
- Decision: `resolve_zip_for_date` yields None when no record covers the date. Callers must not substitute today's artifact.
- Why: Mirrors `apply_rule_versions` dated behavior in `01-CONTRACTS.md` §2.2.
- Reversible? No without an SCR.

## 2026-09-16 — File JSONL + SQL copy
- Decision: JSONL is the operator-visible manifest; SQL is durable for DB-01.
- Why: OpenL zip deploy is a filesystem concern; inspections are in Postgres.
- Reversible? Yes.
