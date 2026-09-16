# CDD Package — AUTH-01 (Authority Case Workflow)

(Verbatim from `CDD/Wave 3.2/AUTH-01.md`, copied here for persistent context.)

**Agent ID:** AUTH-01
**Depends on:** CON-02's complaint-record contract published (real blocker for the queue itself — you can design the RBAC/UI shell in the meantime).

**Purpose:** Give Legal Metrology / FSSAI enforcement officials a queue of consumer complaints and Inspector-flagged (`review_required=True`) inspections to triage, assign, and resolve — the vision's USP7/8, currently entirely unbuilt.

**You must:**
1. **Raise the RBAC question first, as a Scope Change Request to ARCH-01 and DB-01:** does "Authority" become a 4th role alongside inspector/reviewer/admin, or is it a permission variant of an existing role? This is a real schema/auth decision, not a detail — don't build a parallel auth system, extend the existing JWT+bcrypt+RBAC one once the role question is resolved.
2. Once CON-02's contract lands, build the Authority queue: complaints (from CON-02) plus Inspector-flagged inspections (`review_required=True`, already a field on `ExtractedFact`/`RuleFinding`) in one unified view, filterable and assignable to an Authority user.
3. Build the case lifecycle: `OPEN → ASSIGNED → IN_PROGRESS → RESOLVED` (or similar — coordinate exact states with ARCH-01, mirroring the amendment workflow's discipline of explicit transitions), with resolution notes.
4. Extend the existing React app (`frontend/react-app/`) with an Authority-facing view — reuse the existing Inspector app's patterns and `api-client.ts`, since Authority users are professional/internal users like Inspectors, not public consumers (this is different from FE-02's consumer-facing surface, which is a separate app for exactly that reason).
5. Preserve the same legal-safety framing throughout: an `UNCERTAIN` finding sitting in the Authority queue is "needs human judgment," never pre-labeled as confirmed non-compliance.

**You must NOT:**
- Build a second authentication system — extend the existing RBAC once the role question is resolved through ARCH-01/DB-01.
- Auto-resolve or auto-assign cases without an explicit rule the Authority team actually wants — default to manual assignment unless told otherwise.

## CONTEXT.md

- Existing RBAC: JWT + bcrypt, 3 tiers (inspector/reviewer/admin), bootstrap-admin pattern — real and working (`test_auth.py`, 5/0 passing). This is what you extend, not replace.
- `review_required` already exists as a field on both `ExtractedFact` and `RuleFinding` — the Inspector-flagged half of your queue's input already exists in the data model, you're building the view/workflow around it, not adding the field.
- The React app (`frontend/react-app/`) already has working auth-gated routing (per FE-01's parity work) — your Authority view is a new route/section in the same app, not a new frontend project (unlike FE-02, which is deliberately separate — see FE-02 package for why).

## CONTRACTS.md

**Contract you consume:** CON-02's complaint-record contract; existing `review_required`/`RuleFinding` fields; existing RBAC/auth.
**Contract you request:** the Authority role/permission decision from ARCH-01 + DB-01 — raise this immediately, it blocks meaningful progress on the queue's access control.
**Contract you produce:** the case-lifecycle record, which ANA-01 will eventually aggregate over.
