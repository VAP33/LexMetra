# CDD Package — CON-02 (Consumer Reporting → Authority Queue)

(Verbatim from `CDD/Wave 3.1/CON-02.md`, copied here for persistent context.)

**Agent ID:** CON-02
**Depends on:** CON-01's Consumer Scan Response contract published (real blocker — start your schema/design thinking now, but the actual endpoint build waits for that contract). **AUTH-01 depends on you** the same way you depend on CON-01 — publish your complaint-record contract as early as reasonable.

**Purpose:** Let a consumer turn a scan result (or an independent report, e.g. "I bought this and something's wrong" without having used the scan feature) into a complaint that reaches an Authority's queue.

**You must:**
1. Once CON-01's scan response shape lands, design a `complaints` (or `consumer_reports`) table (coordinate with DB-01 — this is a new table, not a change to existing ones): references an optional `consumer_scan_id` (nullable — a complaint doesn't require a prior scan), free-text description, optional photo evidence, location (if provided), status (`SUBMITTED → UNDER_REVIEW → RESOLVED`, mirroring the amendment state machine's discipline of explicit, non-implicit transitions), and a timestamp/consumer-identity link (whatever CON-01 settled on — device ID, phone/email, etc.).
2. Build `POST /consumer/complaints` and a consumer-facing "my reports" view (status only — a consumer shouldn't see internal Authority notes).
3. Carry the legal-safety framing forward: a complaint referencing a scan with `overall_status=UNCERTAIN` must be presented to the Authority as "flagged for review," not as a pre-judged violation — the complaint is a *report*, not a verdict, regardless of what the underlying scan found.
4. Publish the complaint-record contract (what fields, what states) to `01-CONTRACTS.md` via ARCH-01 as soon as it's stable — AUTH-01 needs it to build their queue against.

**You must NOT:**
- Require a prior CON-01 scan to file a complaint — many real consumer complaints won't come with one.
- Auto-escalate a complaint's status without a defined trigger (mirror the amendment workflow's discipline: explicit transitions, not silent ones).

## CONTEXT.md

- No complaint/reporting infrastructure exists at all today — this is genuinely new, like CON-01.
- The existing amendment state machine (`backend/amendments.py`) is a good model for how to structure explicit, auditable status transitions — reuse the pattern's spirit (explicit transitions, no silent auto-progression), not necessarily its exact code.
- Whatever consumer-identity approach CON-01 settles on (device ID vs. phone/email) is what you build against — don't invent a second identity scheme.

## CONTRACTS.md

**Contract you consume:** CON-01's Consumer Scan Response shape and consumer-identity approach.
**Contract you produce:** the complaint-record contract (fields + status states) — publish early; AUTH-01 is waiting on this specifically.
