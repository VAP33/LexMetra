# CDD Package — ANA-01 (Analytics / Intelligence)

(Verbatim from `CDD/Wave 3.3/ANA-01.md`, copied here for persistent context.)

**Agent ID:** ANA-01
**Depends on:** CON-02 and AUTH-01 having real records flowing for the aggregation queries to mean anything. **You can and should start the schema/interface design immediately** — don't wait idle — but the actual dashboards need data to be meaningful, so sequence your own work: design first, populate-and-validate once records exist.

**Purpose:** Turn the growing body of inspections, consumer complaints, and Authority cases into aggregate signal — trend lines, geographic/category clustering, repeat-offender patterns — read-only, informational, never feeding back into any individual verdict.

**You must:**
1. Design the aggregation schema/queries against the **shapes** CON-02 and AUTH-01 have published (even before real data exists) — e.g. "complaints per product category over time," "inspections with `review_required=True` by region," "case resolution time by Authority."
2. Build as **read-only** endpoints/views over existing tables (`inspections`, `complaints`, `authority_cases`) — you do not own or modify these tables, you query them (coordinate with DB-01 if you need an index for query performance, but the schema itself belongs to CON-02/AUTH-01/DB-01).
3. Preserve the legal-safety framing at the aggregate level too: a spike in `UNCERTAIN` findings for a product category is "more scans need human review," not "this category is non-compliant" — aggregation must not launder individual-level uncertainty into a confident category-level claim.
4. Once CON-02/AUTH-01 have real records (even a small number from initial testing), validate your queries against actual data and report real numbers — don't ship charts that have only ever been tested against fabricated sample data.
5. Surface this as a new view in the Inspector/Authority React app (extending AUTH-01's work, not a third frontend) — Analytics is an internal tool, not consumer-facing.

**You must NOT:**
- Build dashboards that imply certainty the underlying data doesn't have (e.g. don't quietly treat `UNCERTAIN` findings the same as `FAIL` in a "violation rate" chart — that's the same invariant every other agent respects, applied at the aggregate level).
- Modify the `inspections`/`complaints`/`authority_cases` schemas — you're a read-only consumer.

## CONTEXT.md

- This is the last agent in the dependency chain — CON-01 → CON-02 → AUTH-01 → ANA-01. Your design work can and should proceed in parallel with the rest of the Final Wave; your validation work is naturally gated by real data existing.
- The existing `overall_status ∈ {PASS, FAIL, UNCERTAIN, EXEMPT}` four-way split is the same vocabulary your aggregates must use — don't collapse it into a binary "compliant/non-compliant" for a simpler chart; that's exactly the kind of certainty-laundering the invariants exist to prevent.

## CONTRACTS.md

**Contract you consume:** CON-02's complaint-record contract, AUTH-01's case-lifecycle record, existing `inspections`/`ProductInspection` data — all read-only.
**Contract you produce:** none — you are a terminal consumer, like FE-02.
