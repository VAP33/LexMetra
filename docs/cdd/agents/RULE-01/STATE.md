# STATE — RULE-01
Last updated: 2026-09-16

## Current phase
partial — exemption OpenL + resolver exist; remaining rules and `/inspect`/`/scan` cutover **not** done

## What exists right now (verified by me, not assumed)
- **OpenL RuleServices (verified 2026-09-15, not re-probed this session):** image `openltablets/ws:6.4.0`. `test_openl_differential.py` skipped here (readiness not 200).
- **First rule migrated**: Rule 3 scope/exemption + Rule 26(a) small-pack as an OpenL
  decision table. Deployed and callable at
  `POST http://localhost:8080/lexmetra/lexmetra/classifyExemption` (JSON body).
- **Differential parity PROVEN**: 1532/1532 cases match `exemption.classify_exemption`
  on `(is_exempt, exemption_type, rule_id, review_required)`; the literal
  `test_exemption.py` fixtures also match. Fixtures written to
  `backend/openl/dist/exemption_differential.json`.
- **Two deploy methods verified**: dev REST deployer (POST /admin/deploy) and
  production repo-zip volume mount (deployer OFF).
- **Additive-only (2026-09-15)**: first RULE-01 commit added `backend/openl/` + packet.
- **2026-09-16 resolver (no production cutover):** `backend/openl/resolver.py` can call OpenL then fall back to `exemption.py`. `LMPC_ENABLE_OPENL` defaults **false**. `/inspect` and `/scan` still use `rule_engine.py`.
- Working files:
  - `backend/openl/scripts/build_exemption_project.py` — generates the xlsx+zip from rules.json.
  - `backend/openl/openl_client.py` — HTTP client + type→verdict mapping (httpx).
  - `backend/openl/scripts/differential_exemption.py` — the parity harness / fixture generator.
  - `backend/openl/config/application.properties` (dev), `application-prod.properties` (prod).
  - `backend/openl/dist/lmpc-exemption.zip` — the deployable artifact.

## What is NOT done yet
- Remaining rules (Rule 6 declarations, 6(11) unit price, 7(2) numeral height, 8 placement,
  24 wholesale, 26 partial-relaxation, Second Schedule, etc.) — **NOT migrated**.
- Production cutover of `/inspect` and `/scan` — **not done** (flag default false, by design).
- DEVOPS-01 compose profile `openl` is now in `docker-compose.yml` (was HANDOFF-only).

## Blocked on
- Nothing hard-blocking RULE-01. Step 4 (migrate remaining rules with per-rule diff) is
  sequenced AFTER TEST-01 turns this harness into the official regression gate — that is
  the package's intended dependency, not an accidental block.

## Next action
Report the milestone; coordinate with TEST-01 (adopt `differential_exemption.py` /
`exemption_differential.json` as the harness seed) and ARCH-01 (finalize §2.4 JSON using
the deployed request/response samples in HANDOFF). Then, once the harness is the gate,
migrate the next rule (candidate: Rule 6(11) unit price — also fairly self-contained).
