# WORKLOG — ARCH-01

## 2026-09-15 — Wave 0: freeze contracts, record decisions, classify DEPENDENCIES
- What I did:
  - Read the ARCH-01 package, `_TEMPLATES.md`, the Stage 1 assessment, and the sibling TEST-01 / DEVOPS-01 packages in full before writing anything.
  - Verified repo facts directly in source rather than trusting the assessment/README:
    - `backend/schema.py` — confirmed `ExtractedFact`, `ProductInspection`, `RuleFinding`, `FactStatus` (4 members), `EvidenceAgreement` invariant helper.
    - `backend/models.py` — confirmed canonical `RegulatoryContext` (line 19), re-exported via `backend/regulatory/models.py`.
    - `backend/rule_engine.py` — confirmed `run_inspection(...)` entrypoint (line 1921) returns `ProductInspection`; verdict shape = `ProductInspection.findings: RuleFinding[]` + `overall_status`.
    - `frontend/` — confirmed working `dashboard.html`/`capture.html` and an early `react-app/` scaffold (main.tsx + config, no components beyond scaffold).
    - `DEPENDENCIES/` — enumerated the full tree.
  - Authored the five repo docs: `00-REPOSITORY-BASELINE.md`, `01-CONTRACTS.md`, `02-DEPENDENCIES-CLASSIFICATION.md`, `AGENT-EXECUTION-GUIDE.md`, and the ARCH-01 packet (`DECISIONS/STATE/WORKLOG/HANDOFF`).
  - Formalized the two owner decisions (OpenL mandatory + keep custom engine as reference; React surface + freeze dashboard) and my own classifications (schema ownership, single-sourced RegulatoryContext, DEPENDENCIES archive).
- What I verified (commands run, actual output):
  - `rg -n "DEPENDENCIES" --glob '!DEPENDENCIES/**'` → found 6 active files (`backend/tests/test_barcode_decode.py`, `backend/tools/{eval_pipeline,bench_ocr,dump_fields,rebuild_product_index,test_bru_real_scan}.py`) referencing a `DEPENDENCIES/images dataset` fallback — contradicting Stage 1's "no references" claim.
  - `ls "DEPENDENCIES/images dataset"` and `ls "images dataset"` → both **do not exist**; real dataset is `dataset/images dataset`. So the fallback refs are already dead; archiving `DEPENDENCIES/` breaks nothing.
  - `git log --oneline` → confirmed HEAD context (`ccd795c` is the tip of the docs/dataset history).
- What I did NOT verify (assumed, or deferred):
  - Did NOT run `pytest` — that's TEST-01's ground-truth scope; baseline §6 left as an explicit placeholder.
  - Did NOT run `docker compose up --build` — DEVOPS-01's scope.
  - Did NOT open every one of the ~26 files under `DEPENDENCIES/need fixing/` individually; classified as a group from the tree + the known LMPC-snapshot provenance.
  - OpenL request/response JSON left shape-level, pending RULE-01's first decision table (deliberate).
- Files touched (all new, docs-only — no feature code, per ARCH-01 constraints):
  - `docs/cdd/00-REPOSITORY-BASELINE.md`
  - `docs/cdd/01-CONTRACTS.md`
  - `docs/cdd/02-DEPENDENCIES-CLASSIFICATION.md`
  - `docs/cdd/AGENT-EXECUTION-GUIDE.md`
  - `docs/cdd/agents/ARCH-01/{DECISIONS,STATE,WORKLOG,HANDOFF}.md`
