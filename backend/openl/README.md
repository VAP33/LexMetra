# backend/openl — OpenL Tablets migration (RULE-01)

Working artifacts for migrating the LMPC rule engine to OpenL Tablets. See
`docs/cdd/agents/RULE-01/` for the full context (STATE / WORKLOG / DECISIONS /
HANDOFF). `rule_engine.py` / `exemption.py` remain the source of truth — nothing
here is cut over until TEST-01 proves rule-by-rule parity and ARCH-01 signs off.

## Layout
- `openl_client.py` — HTTP client (httpx) for the deployed OpenL service; reuses
  `exemption.py` normalization and maps OpenL's `exemption_type` → `ExemptionResult`.
- `config/application.properties` — DEV overrides (embedded REST deployer ON + repo-file).
- `config/application-prod.properties` — PROD-style config (deployer OFF + repo-zip).
- `scripts/build_exemption_project.py` — generates the Rule 3/26 decision table
  (xlsx) + deployment zip, with thresholds READ FROM `rules/rules.json`.
- `scripts/build_smoke.py` — trivial project used to de-risk the deploy pipeline.
- `scripts/differential_exemption.py` — legacy-vs-OpenL parity harness + fixture generator.
- `dist/` — generated artifacts: `lmpc-exemption.zip` (deployable), `LmpcExemption.xlsx`
  (human-readable table), `exemption_differential.json` (TEST-01 fixtures).

## Reproduce (local dev, podman or docker)
```bash
# 1. Run OpenL RuleServices with the dev deployer enabled
podman run -d --name openl-rules -p 8080:8080 \
  -v "$PWD/backend/openl/config/application.properties:/opt/openl/application.properties:ro" \
  openltablets/ws:6.4.0

# 2. Build the rule project from rules.json
backend/.venv/bin/python backend/openl/scripts/build_exemption_project.py

# 3. Deploy it (dev REST deployer)
curl -X POST -H "Content-Type: application/zip" \
  --data-binary @backend/openl/dist/lmpc-exemption.zip \
  http://localhost:8080/admin/deploy/lexmetra

# 4. Prove parity vs the legacy engine (expects OpenL at OPENL_BASE_URL)
backend/.venv/bin/python backend/openl/scripts/differential_exemption.py
# => 1532 cases, 1532 matches, 0 mismatches
```

Env vars read by `openl_client.py`: `OPENL_BASE_URL` (default `http://localhost:8080`),
`OPENL_EXEMPTION_PATH` (default `lexmetra/lexmetra`).

## Production deployment (for DEVOPS-01)
Keep the deployer OFF; mount deployment zip(s) read-only into
`/opt/openl/local/repositories/zipped/` and use `config/application-prod.properties`
(`production-repository.$ref = repo-zip`). See `docs/cdd/agents/RULE-01/HANDOFF.md`.
