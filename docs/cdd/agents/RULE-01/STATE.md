# STATE — RULE-01
Last updated: 2026-09-15

## Current phase
implementing — Steps 1–3 of the package DONE and verified. First rule migrated to
OpenL with proven differential parity. Now at the package's designed handoff point:
TEST-01 builds the official harness; remaining rules (step 4) are gated on it.

## What exists right now (verified by me, not assumed)
- **OpenL RuleServices running** (`openl-rules`, `docker.io/openltablets/ws` v6.4.0,
  host :8080). `GET /` 200, `GET /admin/services` shows `lmpc_exemption` = DEPLOYED,
  health endpoints 200.
- **First rule migrated**: Rule 3 scope/exemption + Rule 26(a) small-pack as an OpenL
  decision table. Deployed and callable at
  `POST http://localhost:8080/lexmetra/lexmetra/classifyExemption` (JSON body).
- **Differential parity PROVEN**: 1532/1532 cases match `exemption.classify_exemption`
  on `(is_exempt, exemption_type, rule_id, review_required)`; the literal
  `test_exemption.py` fixtures also match. Fixtures written to
  `backend/openl/dist/exemption_differential.json`.
- **Two deploy methods verified**: dev REST deployer (POST /admin/deploy) and
  production repo-zip volume mount (deployer OFF).
- **Additive-only**: `git status` shows RULE-01 added only `backend/openl/` and
  `docs/cdd/agents/RULE-01/`. No feature code touched.
- Working files:
  - `backend/openl/scripts/build_exemption_project.py` — generates the xlsx+zip from rules.json.
  - `backend/openl/openl_client.py` — HTTP client + type→verdict mapping (httpx).
  - `backend/openl/scripts/differential_exemption.py` — the parity harness / fixture generator.
  - `backend/openl/config/application.properties` (dev), `application-prod.properties` (prod).
  - `backend/openl/dist/lmpc-exemption.zip` — the deployable artifact.

## What is NOT done yet
- Remaining rules (Rule 6 declarations, 6(11) unit price, 7(2) numeral height, 8 placement,
  24 wholesale, 26 partial-relaxation, Second Schedule, etc.) — NOT migrated. Step 4,
  gated on TEST-01's official harness per package ordering.
- The full `RuleSet Resolver → OpenL` in the backend + feature flag + `/inspect`,`/scan`
  wiring — step 6, only "once all rules pass differential testing".
- `01-CONTRACTS.md` §2.4 byte-level JSON — to be finalized WITH ARCH-01 now that a first
  table is deployed (request/response samples below in HANDOFF).
- DEVOPS-01 compose service — recommended config is ready in HANDOFF (their call to add).

## Blocked on
- Nothing hard-blocking RULE-01. Step 4 (migrate remaining rules with per-rule diff) is
  sequenced AFTER TEST-01 turns this harness into the official regression gate — that is
  the package's intended dependency, not an accidental block.

## Next action
Report the milestone; coordinate with TEST-01 (adopt `differential_exemption.py` /
`exemption_differential.json` as the harness seed) and ARCH-01 (finalize §2.4 JSON using
the deployed request/response samples in HANDOFF). Then, once the harness is the gate,
migrate the next rule (candidate: Rule 6(11) unit price — also fairly self-contained).
