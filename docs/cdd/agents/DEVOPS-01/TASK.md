# CDD Package — DEVOPS-01 (Docker / CI-CD / Repo Hygiene)

(Verbatim from `CDD/Wave 0/3 DEVOPS-01.md`, copied here for persistent context.)

**Agent ID:** DEVOPS-01
**Role:** Keep the repository clean and the deployment story truthful.

**Purpose:** Execute the `DEPENDENCIES/` cleanup ARCH-01 classifies, confirm the existing Docker setup still builds cleanly, and stand up CI so TEST-01's regression gate actually runs automatically.

**You must:**
1. Wait for ARCH-01's classification of `DEPENDENCIES/` (old `LMPC-Compliance-Platform` snapshot, `archives/LMPC_current.zip`, `need fixing/` staging files, `apply_scripts/` patch scripts), then execute it — most likely: move the whole `DEPENDENCIES/` tree to a separate `archive/pre-lexmetra` branch or an external location, out of the active working tree, so no agent mistakes it for live code. Do not delete anything — archive, don't destroy.
2. Run `docker compose up --build` against the existing `docker-compose.yml` and confirm it still succeeds after the `DEPENDENCIES/` move (nothing in the active build should reference that folder, but verify — don't assume).
3. Set up CI (GitHub Actions is the safe default given the repo is already on GitHub) to run TEST-01's `pytest` suite on every PR, blocking merge on regression below the TEST-BASELINE floor.
4. Once OpenL Tablets is in play (RULE-01), extend `docker-compose.yml` with the `openltablets/ws` service — do not attempt this until RULE-01 has confirmed the exact image tag and rule-deployment path they're using; adding it speculatively risks a config that doesn't match what RULE-01 actually builds.
5. Confirm `.env.example` still matches every environment variable actually read by `config.py` after other agents' changes land — this drifts easily and silently.

**You must NOT:**
- Touch `backend/rule_engine.py`, `rag/`, or any feature code — pure infra/repo scope.
- Delete `DEPENDENCIES/` outright. Archive it. Someone may need to diff against the earlier snapshot later.

## CONTEXT.md

- Current Docker setup is real and complete: Postgres 16, Redis 7, backend with healthchecks, all wired via `docker-compose.yml` at repo root. This already works — your job is to not break it while cleaning up, and to extend it, not replace it.
- `DEPENDENCIES/LMPC-Compliance-Platform/` differs from the current `backend/` in 63 files — it's an earlier snapshot of the same project (LMPC was this project's earlier name), not a real dependency. `DEPENDENCIES/archives/LMPC_current.zip` is a zipped copy of the same thing. `DEPENDENCIES/apply_scripts/` are scripts (`apply_build02.py` through `apply_build06.py`) that were used to mechanically apply past BUILD_01–12 patch sessions — historically useful, operationally dead.
- No CI currently exists in the repo (single commit, no `.github/workflows/`).

## CONTRACTS.md

**Contract you own:** `docker-compose.yml`, `.github/workflows/*`, `.env.example`.
**Contract you consume:** ARCH-01's classification decision (blocking — do not archive anything before this lands). RULE-01's OpenL deployment shape (blocking for the compose extension specifically, not for the rest of your scope).
**Contract you produce:** a CI status badge / gate that RULE-02, OCR-01, CV-01, and every later agent's PRs must pass.
