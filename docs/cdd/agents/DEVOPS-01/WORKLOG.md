# WORKLOG — DEVOPS-01

## 2026-09-16 — CI, OpenL compose profile, env, archive attempt
- What I did:
  - Added GitHub Actions pytest workflow matching TEST-BASELINE env.
  - Added compose `openl` profile with RULE-01's verified image tag and repo-zip path.
  - Synced `.env.example` with new `config.py` variables.
  - Dockerfile: Hindi/Marathi tess packs + poppler-utils.
  - Attempted DEPENDENCIES archive: folder not in this working tree.
- What I verified:
  - `ls DEPENDENCIES` → `No such file or directory`
  - `podman version` → 5.8.4; `docker version` → 29.8.0
  - pytest this host: **489 passed, 19 skipped, 3 failed** — the 3 failures are `test_ocr_engine.py` needing a Tesseract binary (`rpm -q tesseract` → not installed). Not a CI-config bug.
- What I did NOT verify:
  - Full `compose up --build` (not run).
  - GitHub Actions on a real PR (no push).
- Files touched:
  - `.github/workflows/pytest.yml`, `docker-compose.yml`, `.env.example`, `backend/.env.example`, `backend/Dockerfile`, `archive/README.md`
