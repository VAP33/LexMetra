# CDD Package — RULE-03 (Amendment Workflow Completion)

(Verbatim from `CDD/Wave 2/RULE-03.md`, copied here for persistent context.)

**Agent ID:** RULE-03
**Depends on:** OCR-01 (fused OCR output, for the gazette-image leg only — coordinate directly, don't block your whole scope on their completion), RULE-02 (redeploy trigger target).

**Purpose:** Finish the gazette-amendment pipeline end-to-end: a scanned/photographed gazette notification goes in, a structured diff against the current rule comes out, a human approves it, and — new in this pass — an approved amendment actually triggers a redeployed OpenL rule version via RULE-02's pipeline.

**You must:**
1. Read `backend/amendments.py` fully — the state machine (`DRAFT→...→APPROVED→SCHEDULED`, `ACTIVE` deliberately not auto-reachable) already encodes the governance philosophy correctly. You're completing the pipeline feeding into it and the pipeline it triggers, not redesigning the state machine.
2. Complete the OCR→diff leg: gazette image/PDF → OCR (use OCR-01's engine once their fusion lands; Tesseract-only is fine as an interim if OCR-01 isn't done yet — note which you used) → structured extraction of the amended rule text → diff against the current `rules.json` entry for that rule ID.
3. Surface the diff to a human reviewer (extend the React app or the existing amendment review surface — check what exists first, don't assume nothing does) for the `DRAFT→REVIEW→APPROVED` transitions.
4. **New scope beyond what existed before:** when an amendment reaches `SCHEDULED` and its effective date arrives (the `ACTIVE` transition), trigger RULE-02's versioned-deploy pipeline to generate and deploy the updated OpenL rule project for that rule — this is the seam the RULE-01 package flagged as existing but not yet built ("Don't build this yet; just be aware the seam exists" — it's now in scope for you).
5. Every amendment that changes a threshold must carry the same `verification_status: needs_official_verification` discipline forward — an approved amendment is a workflow approval, not a legal verification; don't conflate the two.

**You must NOT:**
- Auto-transition anything to `ACTIVE` without the effective date actually arriving — this was a deliberate governance choice in the existing state machine, don't relax it for convenience.
- Build a second diff/versioning mechanism — trigger RULE-02's pipeline, don't reimplement rule deployment yourself.

## CONTEXT.md

- `backend/amendments.py` state machine is real and tested (`test_build09_amendment_publication.py`, 10/0 passing per `TEST-BASELINE.md`) — this is load-bearing, read it before changing anything.
- The OCR→diff leg is currently `PARTIAL` per the repository baseline — some scaffolding likely exists (check for a gazette-specific extraction path in `ocr_extraction.py` or a separate module) before assuming you're starting from zero.
- RULE-02's versioned-deploy manifest is your trigger target for the new `SCHEDULED→ACTIVE` hook — coordinate the exact manifest format with them directly since you're both Final-Wave agents running in parallel.

## CONTRACTS.md

**Contract you consume:** OCR-01's fused OCR output (for gazette text extraction); RULE-02's versioned-deploy manifest/trigger interface.
**Contract you produce:** the `SCHEDULED→ACTIVE` redeploy hook — document its trigger condition and failure behavior (what happens if RULE-02's pipeline fails at the exact effective-date moment — this must not silently leave stale rules active).
