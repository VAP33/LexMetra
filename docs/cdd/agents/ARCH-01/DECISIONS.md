# DECISIONS — ARCH-01

> Records architectural decisions locked for LexMetra. The first two are **project-owner
> decisions** ARCH-01 is formalizing (not open questions); the rest are ARCH-01's own
> classifications. Any agent who thinks a DECIDED item is wrong files a Scope Change
> Request (CDD Instructions §46) — they do not silently override it.

## 2026-09-15 — D-01: OpenL Tablets is mandatory (custom engine kept as reference)
- Context: Vision requires OpenL; repo has a hand-written `rule_engine.py` instead. Stage 1 flagged this as the highest-stakes open question (SIH "open-source rule engine" is a scored USP).
- Options considered:
  1. Keep the custom engine, formally drop OpenL.
  2. Adopt OpenL and delete the custom engine.
  3. Adopt OpenL, keep the custom engine as a reference for differential testing until parity is proven. **(chosen)**
- Decision: **OpenL Tablets is mandatory.** `backend/rule_engine.py` is **not deleted**; it stays as the reference implementation for differential testing until OpenL parity is proven rule-by-rule, then it may be retired.
- Why: Decision came from the project owner. Option 3 satisfies the requirement while honoring "current working functionality is valuable" and the CDD differential-testing-before-cutover rule. OpenL is a JVM service (`openltablets/ws`) called over HTTP — see `01-CONTRACTS.md` §2.
- Reversible? Partially. Dropping OpenL later = Scope Change Request. Retiring the custom engine is a one-way door only after differential parity is signed off by TEST-01.

## 2026-09-15 — D-02: React app is the frontend surface; `dashboard.html` frozen (not deleted)
- Context: Two competing frontends exist — a working `dashboard.html` and a very early `frontend/react-app/` scaffold. Building on both wastes effort (Stage 1 risk #3).
- Options considered:
  1. Keep building on `dashboard.html`.
  2. Build on the React app; freeze and eventually retire the static dashboard. **(chosen)**
  3. Maintain both indefinitely.
- Decision: **`frontend/react-app/` is the surface to build on.** `frontend/dashboard.html` is **frozen** (no new features) and scheduled for retirement once React reaches feature parity. **Do not delete it yet** — RULE/EVID/OCR agents may still need a working reference UI during migration.
- Why: Project-owner decision; consolidating before building more UI avoids duplicated surface work. Keeping the dashboard as a live reference de-risks the migration.
- Reversible? Yes at cost — retiring the dashboard prematurely would remove the only working UI reference. Retire only after React parity.

## 2026-09-15 — D-03: `ExtractedFact` / `ProductInspection` are the canonical pipeline contract
- Context: OCR, CV, rule engine, DB, report gen, and frontend all import from `backend/schema.py`. Uncontrolled edits here break every module at once.
- Decision: ARCH-01 owns `backend/schema.py`'s `ExtractedFact` / `ProductInspection` (and nested models). Any field change requires ARCH-01 sign-off via Scope Change Request. Frozen and documented in `01-CONTRACTS.md`, including four legal-safety invariants.
- Why: One stable seam is what makes parallel Wave 1+ work possible without constant breakage.
- Reversible? The ownership rule is not meant to be reversed. Individual field changes are reversible via the same SCR process.

## 2026-09-15 — D-04: `RegulatoryContext` stays single-sourced in `backend/models.py`
- Context: RULE-01 needs a RuleSet Resolver → OpenL contract; that contract needs regulatory context. Risk of a second, divergent `RegulatoryContext` being invented.
- Decision: Reuse the existing `RegulatoryContext` from `backend/models.py` (re-exported via `backend/regulatory/models.py`). The new OpenL contract's input side references it directly; no second model. `inspection_date` is required and drives dated rule-version selection.
- Why: A duplicate context model would silently drift and reintroduce time-travelling-verdict bugs the engine already guards against.
- Reversible? Yes, but pointless — divergence is the failure mode we're preventing.

## 2026-09-15 — D-05: Entire `DEPENDENCIES/` tree classified NON-CORE → archive (not delete)
- Context: `DEPENDENCIES/` holds an old `LMPC-Compliance-Platform` snapshot, a 38 MB zip of it, `apply_scripts/`, a `need fixing/` staging folder, loose docs, and a patch diff. Risk: an agent mistakes it for a second live backend (Stage 1 risk #4).
- Decision: Classify the whole tree NON-CORE. DEVOPS-01 archives it to `archive/pre-lexmetra` (or external), **archive not delete**. Full item-by-item table + a correction in `02-DEPENDENCIES-CLASSIFICATION.md`.
- Correction recorded: Stage 1's "nothing references `DEPENDENCIES/`" was **wrong** — 6 tools/tests reference a `DEPENDENCIES/images dataset` fallback. But that path doesn't exist (real data is `dataset/images dataset`), so the fallback is already dead and archiving breaks nothing; the stale refs are routed to TEST-01 / tools owner.
- Why: Keeps the working tree unambiguous; preserves history for future diffing.
- Reversible? Fully — it's an archive move, recoverable from the archive branch.
