# CDD Package — CON-01 (Consumer Scan / Dashboard)

(Verbatim from `CDD/Wave 2/CON-01.md`, copied here for persistent context.)

**Agent ID:** CON-01
**Depends on:** nothing blocking — start immediately. **You are the pacing item** for CON-02, AUTH-01, and FE-02 — publish your contract shape as early as reasonably solid, even before the full feature is polished, so the rest of the chain isn't idle.

**Purpose:** Expose the existing inspection pipeline to the public as a simplified, consumer-facing scan feature — this is genuinely new surface area (the current pipeline is Inspector-only), not an extension of existing code.

**You must, in rough order:**
1. **Resolve the public-access question first, explicitly, as a Scope Change Request to ARCH-01 (and flag to DEVOPS-01):** the existing `/scan` pipeline runs real OCR/CV compute and is currently behind auth (inspector/reviewer/admin). A public consumer endpoint needs: no-login-required access (or a lightweight consumer identity — device ID, or optional phone/email), and **abuse/cost protection** (rate limiting, maybe a CAPTCHA on repeated use) since public unauthenticated compute-heavy endpoints are a real cost and availability risk, not a detail. Get this reviewed before building the endpoint, not after.
2. Design `POST /consumer/scan` — internally reuses the existing OCR→CV→rule-engine pipeline (`ProductInspection`), but returns a **simplified** response: plain-language verdict, the mandatory `disclaimer` field carried forward unchanged, and enough detail to act on without exposing raw evidence complexity (that's EVID-01's Inspector-facing view, not this one).
3. **Preserve the four legal-safety invariants in the simplified view too:** `UNCERTAIN` must not be flattened into "looks fine" or "violation" — represent it honestly to a lay consumer (e.g. "couldn't confirm this from the photo" rather than silently picking a side).
4. Persist consumer scans distinctly from Inspector scans in the DB (coordinate the table addition with DB-01) — a consumer's casual phone-camera scan is evidentially weaker than an Inspector's calibrated capture; don't conflate them in a single `inspections` table without a clear source/type field.
5. **Publish your response contract early** (even a draft) to `01-CONTRACTS.md` via ARCH-01, since CON-02, AUTH-01, and FE-02 are all waiting on this shape specifically to start their own work.

**You must NOT:**
- Expose raw pipeline internals (bboxes, confidence per OCR engine, rule IDs) to the consumer response — that's evidence-viewer territory, not consumer-facing.
- Skip the public-access/abuse-protection review to move faster — an unthrottled public endpoint hitting a real OCR/CV pipeline is a genuine production risk, not bureaucracy.

## CONTEXT.md

- The existing `/scan` endpoint and its full pipeline (`ExtractedFact`/`ProductInspection`) are real and tested — you're wrapping and simplifying, not rebuilding OCR/CV/rules.
- RBAC today has 3 tiers (inspector/reviewer/admin), all requiring login. There is no existing "no-auth" or "consumer" access path anywhere in the current auth system — this is genuinely new, not an extension.
- Your response shape is the single most-awaited artifact in the Final Wave — CON-02, AUTH-01, and FE-02 all key off it. A reasonable, published-early draft beats a perfect, late one.

## CONTRACTS.md

**Contract you consume:** `ProductInspection`/`ExtractedFact` (internal use, unchanged) — you wrap, not fork.
**Contract you produce:** the Consumer Scan Response shape — publish to `01-CONTRACTS.md` as soon as it's stable enough to build against, even if the full feature (rate limiting, consumer identity) is still in progress.
**Contract you request:** a public/consumer access decision from ARCH-01 + DEVOPS-01 (auth model, rate limiting approach) — this blocks your own endpoint from safely shipping, so raise it immediately, don't discover it late.
