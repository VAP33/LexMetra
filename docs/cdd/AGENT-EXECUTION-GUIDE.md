# Agent Execution Guide (LexMetra CDD)

**Owner:** ARCH-01. **Audience:** every subagent working on LexMetra under Contract-Driven Development.
**Read order for any new agent:** this guide → `00-REPOSITORY-BASELINE.md` → `01-CONTRACTS.md` → your own package → `TEST-BASELINE.md` (when it exists).
**Last updated:** 2026-09-15 @ commit `ccd795c`

---

## 1. The one-paragraph mental model

LexMetra is a **modular monolith** (FastAPI + Postgres + Redis + Docker). We are
**extending it additively behind stable contracts** — not rewriting it. The code that
works today (rule engine, RAG governance, CV pipeline, auth, audit) is *valuable* and
stays. Every new capability targets the existing contracts in `backend/schema.py` and
`backend/models.py`. If you find yourself forking a contract or ripping out working
code, stop — that is a Scope Change Request, not a task.

## 2. Non-negotiable ground rules

1. **No claim without a command.** "It works" requires the command and its actual
   output. File counts are not test results. (TEST-01 owns ground truth.)
2. **Contracts are frozen.** `ExtractedFact` / `ProductInspection` / `RegulatoryContext`
   changes go through ARCH-01 as a written Scope Change Request (CDD Instructions §46).
   Additive optional fields are usually fast-approved; renames/removals/invariant
   changes are blocked by default.
3. **Verify, don't assume — including the assessment.** The Stage 1 report and this
   guide can be wrong. (Example already found: `DEPENDENCIES/` was assumed
   reference-free; it wasn't — see `02-DEPENDENCIES-CLASSIFICATION.md` §3.) When your
   package says "verify — don't assume," actually verify.
4. **Absence ≠ non-compliance. Confidence ≠ legality. Conflict is about the reading,
   not the package.** These are legal-safety invariants (`01-CONTRACTS.md` §1.3). Never
   convert uncertainty or low confidence into a `FAIL`.
5. **Archive, don't destroy.** Historical/non-core material is moved out of the way, not
   deleted.
6. **The four locked decisions** (OpenL mandatory, keep `rule_engine.py` as reference,
   React is the frontend surface, `dashboard.html` frozen-not-deleted) came from the
   project owner. Disagreement is a Scope Change Request, not a unilateral override.
   See `agents/ARCH-01/DECISIONS.md`.

## 3. Roles at a glance (from Stage 1 §C)

| Wave | Agents | Depends on |
|---|---|---|
| **0** | ARCH-01 (contracts/decisions), TEST-01 (real pytest + regression gate), DEVOPS-01 (repo hygiene, Docker, CI) | none |
| **1** | RULE-01, OCR-01, EVID-01, FE-01 (consolidation), DB-01 | ARCH-01 decisions |
| **2** | RULE-02, RULE-03, CV-01, CV-02, RAG-01, RAG-02, FSSAI-01 | Wave 1 outputs |
| **3** | CON-01 → CON-02 → AUTH-01 → FE-02 | stable backend contracts |
| **4** | ANA-01 | Wave 3 records |

Full ownership table and dependency graph: `00-REPOSITORY-BASELINE.md` and the Stage 1
assessment §C/§D.

## 4. Per-agent working files (the CDD packet)

Every agent keeps four living files under `docs/cdd/agents/<AGENT-ID>/`, using the
templates in `_TEMPLATES.md`. These are what let a fresh agent resume after a context
wipe without relying on memory:

- **STATE.md** — current phase, what exists (verified, not assumed), what's blocked, the single next action.
- **WORKLOG.md** — append-only "what I did / verified / did NOT verify / files touched." Never delete entries.
- **DECISIONS.md** — context, options, decision, why, reversibility. One entry per real decision.
- **HANDOFF.md** — summary for the next agent: what's stable to depend on, what's still in flux, contracts changed, open questions.

Keep STATE.md and WORKLOG.md current *as you work*, not at the end.

## 5. Definition of Done (every PR)

A change is "done" only when all of these hold:

1. **Tests:** the suite still passes at or above the TEST-01 floor recorded in
   `docs/cdd/TEST-BASELINE.md` for the current commit. Dropping below the floor fails
   review.
2. **Contracts:** no frozen-contract field changed without a linked ARCH-01 sign-off.
   `ProductInspection` stays `extra="forbid"`.
3. **Invariants:** the four legal-safety invariants (`01-CONTRACTS.md` §1.3) are
   provably intact for any code touching facts/findings/status.
4. **CI green:** DEVOPS-01's GitHub Actions gate passes (runs the pytest suite on every
   PR; blocks merge on regression).
5. **Packet updated:** your STATE/WORKLOG/DECISIONS/HANDOFF reflect the change.
6. **Scope honored:** you touched only what your package owns. Cross-cutting edits are
   coordinated through the owning agent (e.g. schema → ARCH-01, docker/CI → DEVOPS-01,
   test floor → TEST-01).

## 6. How to propose a contract change (Scope Change Request)

1. Open a short SCR note (in your DECISIONS.md and the PR description): what field,
   why, who else consumes it, and whether it's additive-optional or breaking.
2. Tag ARCH-01. Additive-optional with a safe default → usually approved quickly.
   Rename/removal/type-change/invariant-touching → must be justified against the §1.3
   guarantees before any code merges.
3. On approval, ARCH-01 updates `01-CONTRACTS.md` and the consumers list; you implement.

## 7. OpenL & differential testing (applies to RULE-01, TEST-01, DEVOPS-01)

- OpenL Tablets is a **JVM service** (`openltablets/ws`) called over HTTP — not a pip
  package. The seam is the **RuleSet Resolver → OpenL** contract (`01-CONTRACTS.md` §2).
- `rule_engine.py` is **not deleted**; it is the parity reference.
- **No production cutover** until TEST-01's differential harness proves rule-by-rule
  parity (same input → `{old_engine_result, openl_result}` → diff), as required by CDD
  Instructions. DEVOPS-01 adds the compose service only after RULE-01 confirms the exact
  image tag and rule-deployment path.

## 8. Escalate (don't silently resolve) when…

- A frozen contract seems to need a breaking change.
- Two agents' scopes overlap or their contracts conflict.
- A vision claim contradicts the verified baseline.
- A legal-accuracy question arises (rules carry `needs_official_verification`; that needs
  a human legal reviewer against gazette text — no coding agent resolves it).
