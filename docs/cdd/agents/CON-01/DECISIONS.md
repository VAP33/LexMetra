# DECISIONS — CON-01

## 2026-09-16 — UNCERTAIN is a first-class consumer outcome
- Context: Lay UI temptation is to flatten UNCERTAIN into pass/fail.
- Decision: `overall_status` uses the same four FactStatus members. Copy says "could not confirm", never "looks fine" or "violation".
- Why: §1.3 invariants apply to simplified views too.
- Reversible? No without an SCR.

## 2026-09-16 — Distinct table, evidentially weaker
- Decision: `consumer_scans` + `evidentially_weaker_than_inspector=true`.
- Why: Phone photos must not be mixed into Inspector evidence without a source field.
- Reversible? Adding a `source` column on `inspections` would be a later SCR; not done.
