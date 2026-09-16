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

## 2026-09-16 — D-06: Public consumer scan is flag + rate-limit, not a new RBAC role
- Context: CON-01 asked for public `/consumer/scan`. Adding a `consumer` role would expand the 3-tier RBAC (inspector/reviewer/admin) without an owner decision.
- Options considered:
  1. New `consumer` role + login. Rejected (SCR would be required; FE-02/AUTH-01 not in this pass).
  2. Open unauthenticated `/scan`. Rejected (cost/abuse).
  3. Feature-flagged `POST /consumer/scan` + IP sliding-window RPM. **(chosen)**
- Decision: No fourth role. `LMPC_ENABLE_CONSUMER_SCAN` default false. `LMPC_CONSUMER_SCAN_RPM` rate limit. Response is `ConsumerScanResponse` (no bboxes/rule IDs). UNCERTAIN stays first-class.
- Why: Unblocks CON-02/FE-02 contract work without expanding auth surface.
- Reversible? Yes — disable the flag. Adding a consumer role later is a new SCR.

## 2026-09-16 — D-07: FSSAI stays a parallel domain; `overall_status` remains LMPC
- Context: FSSAI-01 needs a per-module status. `ProductInspection` is `extra="forbid"`.
- Decision: Do **not** add `module_statuses` to `ProductInspection` in this pass. Persist `fssai_inspection_results` and expose `GET /inspections/{id}/fssai`. Absence of an FSSAI mark is UNCERTAIN, never FAIL. Do not merge into `rules.json`.
- Why: Preserves USP5 (distinct legal bases) and the frozen pipeline contract.
- Reversible? An additive optional field on ProductInspection is a future SCR.

## 2026-09-16 — D-08: YOLO not shipped; classical CV retained
- Context: CV-01 default plan was YOLOv8n fine-tune. Inventory: 50 synthetic images, 30 real, 50 synthetic annotations. Below the honest-finetune bar (`>=200` real + non-synthetic labels).
- Decision: No weights file. `layout_ensemble.detect_layout` wraps classical `detect_regions`. Documented in `00-REPOSITORY-BASELINE.md`.
- Why: Package explicitly allows this as the safest-minimal-default.
- Reversible? Yes — drop weights into `backend/models/layout_yolov8n.pt` and set `LMPC_ENABLE_YOLO_LAYOUT` after a measured bake-off.
