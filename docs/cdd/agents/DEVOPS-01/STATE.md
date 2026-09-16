# STATE — DEVOPS-01
Last updated: 2026-09-16

## Current phase
partial — CI, compose OpenL profile, env sync, dataset-path retarget done. DEPENDENCIES/ archive blocked (folder absent in this tree).

## What exists right now (verified by me, not assumed)
- `.github/workflows/pytest.yml`: GitHub Actions on PR/push, Postgres 16 service, Tesseract+poppler, clean-DB env matching TEST-BASELINE.
- `docker-compose.yml`: `openl` service `openltablets/ws:6.4.0` behind compose profile `openl`, repo-zip mount of `backend/openl/dist/lmpc-exemption.zip`, prod properties (deployer off).
- `.env.example` / `backend/.env.example`: OPENL_*, LMPC_OCR_LANGUAGES, LMPC_ENABLE_OPENL, LMPC_ENABLE_CONSUMER_SCAN, LMPC_ENABLE_FSSAI.
- `backend/Dockerfile`: `tesseract-ocr-hin`, `tesseract-ocr-mar`, `poppler-utils`.
- `archive/README.md`: archive procedure. `ls DEPENDENCIES` → no such file (cannot move what is not here).
- Dataset tool/test fallbacks retargeted to `dataset/images dataset` and `dataset/real images` via `backend/dataset_paths.py`.

## What is NOT done yet
- `podman compose up --build` / `docker compose up --build` not run this session (long image build; OpenL zip must exist).
- DEPENDENCIES/ physical move — tree not present in this checkout.

## Blocked on
- Host copy of `DEPENDENCIES/` if it still exists on another machine.

## Next action
On a checkout that still has `DEPENDENCIES/`: `mkdir -p archive && mv DEPENDENCIES archive/pre-lexmetra`. Then `podman compose up --build` and confirm `/health`.
