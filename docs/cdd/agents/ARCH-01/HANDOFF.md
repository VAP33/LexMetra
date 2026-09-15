# HANDOFF — ARCH-01
Prepared: 2026-09-15

## Summary for the next agent (or my future self)
Wave 0 architecture gatekeeping is done. Contracts are frozen (`01-CONTRACTS.md`),
the owner decisions are recorded (OpenL mandatory + custom engine kept as reference;
React is the surface + `dashboard.html` frozen-not-deleted), the repo baseline is
formalized (`00-REPOSITORY-BASELINE.md`), and `DEPENDENCIES/` is classified for
DEVOPS-01 to archive. Everything is docs-only; no feature code was written or changed.

## What I own that is now stable (safe for others to depend on)
- `docs/cdd/00-REPOSITORY-BASELINE.md` — the verified "what exists" reference (except §6, pending TEST-01).
- `docs/cdd/01-CONTRACTS.md` §1 — `ExtractedFact`/`ProductInspection` frozen with 4 legal-safety invariants. Build against these; propose changes as SCRs.
- `docs/cdd/AGENT-EXECUTION-GUIDE.md` — roles, waves, Definition of Done, PR gates.
- `docs/cdd/agents/ARCH-01/DECISIONS.md` — D-01…D-05, the locked decisions.
- `RegulatoryContext` single-sourcing (D-04): use `backend/models.py`, don't fork it.

## What I own that is still in flux (do NOT depend on this yet)
- `01-CONTRACTS.md` §2.4 — the exact OpenL request/response JSON. Shape is fixed
  (input = ExtractedFact[] + RegulatoryContext; output maps to RuleFinding[]/overall_status
  over HTTP to `openltablets/ws`), but the byte-level payload is finalized only after
  RULE-01 deploys the first decision table. Coordinate with me before hardcoding JSON.
- Baseline §6 (test numbers) — placeholder until TEST-01 reports.

## Contracts I changed
- None changed. I **froze existing** ones (`schema.py`, `models.py`) and **defined one new**
  one (RuleSet Resolver → OpenL). No fields were altered in code.

## Direct handoffs (action required by others)
- **DEVOPS-01:** Execute `02-DEPENDENCIES-CLASSIFICATION.md` (archive, don't delete). Note
  the correction in §3 — the only `DEPENDENCIES/` references are already-dead dataset
  fallbacks, so the archive move is safe; verify with `docker compose up --build` anyway.
- **TEST-01:** Run pytest, produce `docs/cdd/TEST-BASELINE.md`; I fold the numbers into
  baseline §6. Also record how the dataset-dependent tools/tests behave given the dead
  `images dataset` fallback (real path is `dataset/images dataset`).
- **RULE-01:** Build the OpenL path against `01-CONTRACTS.md` §2. Keep `rule_engine.py` as
  the parity reference (D-01). Confirm the exact `openltablets/ws` image tag + rule-deploy
  path to DEVOPS-01 before the compose service is added.
- **FE-01:** Consolidate onto `frontend/react-app/` (D-02); do not delete `dashboard.html`.

## Open questions I could not resolve myself
- **Legal accuracy:** every rule carries `verification_status: "needs_official_verification"`.
  This needs a human legal reviewer against gazette text — outside any coding subagent's scope.
- **Commit/branch policy:** these docs are written but uncommitted. Owner to confirm whether to
  commit `docs/cdd/**` on `main` or a dedicated branch.
