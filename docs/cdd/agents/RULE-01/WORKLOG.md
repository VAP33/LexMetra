# WORKLOG — RULE-01

Append-only. Never delete entries. This is the "why", not just the "what".

## 2026-09-15 — Step 1: stand up OpenL Tablets locally (DONE)
- What I did:
  - Read the full CDD framework before touching anything: `AGENT-EXECUTION-GUIDE.md`,
    `01-CONTRACTS.md`, ARCH-01 `HANDOFF/STATE`, `TEST-BASELINE.md`, TEST-01 `HANDOFF`,
    and the parity sources `rules/rules.json`, `backend/exemption.py`.
  - Discovered the environment has **podman 5.8.4** (rootless), no docker daemon,
    no podman-compose. DEVOPS-01's stack already runs (db/redis/backend).
  - Pulled the OpenL RuleServices image and started it.
- What I verified (commands + actual output):
  - `podman pull docker.io/openltablets/ws:latest` → success, image `7ab2aff7d117`.
  - `podman image inspect …` → version label **6.4.0**, exposes 8080/tcp,
    cmd `/opt/openl/start.sh`, workdir `/opt/openl`.
  - `podman run -d --name openl-rules -p 8080:8080 …` → container up.
  - `podman logs openl-rules` → "Started oejs.ServerConnector@…{0.0.0.0:8080}",
    Jetty 12.1.12, admin publish address `/admin`.
  - `curl` probes:
    - `GET http://localhost:8080/` → **200**
    - `GET http://localhost:8080/admin/services` → **`[]`** (no services yet)
    - `GET http://localhost:8080/admin/healthcheck/startup` → **200**
    - `GET http://localhost:8080/admin/healthcheck/readiness` → **200**
- What I did NOT verify (deferred):
  - How to deploy a rule project to this instance (REST deploy endpoint vs
    mounted production-repository volume) — next step.
  - Any actual rule execution round-trip — next step.
- Files touched: created `docs/cdd/agents/RULE-01/{README,TASK,CONTEXT,CONTRACTS,STATE,WORKLOG,DECISIONS,HANDOFF}.md`.
  No feature code changed. `rule_engine.py` untouched (and stays untouched until parity).

## 2026-09-15 — Steps 2 & 3: first rule as OpenL decision table + differential parity (DONE)
- What I did:
  - De-risked the deploy pipeline with a trivial `SimpleRules` project: built xlsx
    via openpyxl → zipped → `POST /admin/deploy` → executed over HTTP. Confirmed the
    plumbing (build → deploy → call) before investing in the real table.
  - Discovered deployment mechanics: default `production-repository.$ref = repo-jar`
    (classpath, read-only); dev-only REST deployer gated by `ruleservice.deployer.enabled`.
    Enabled the deployer + `repo-file` via a mounted `application.properties` for dev.
  - Authored the **Rule 3 scope/exemption + Rule 26(a) small-pack** logic as an explicit
    OpenL **decision table** (`backend/openl/scripts/build_exemption_project.py`), with
    thresholds READ FROM `rules/rules.json` (not hand-typed). Signature:
    `String classifyExemption(String saleType, String productCategory, double massG,
    double volumeMl, boolean quantityEstablished, boolean isPrepackagedFalse,
    boolean directIndInst, boolean isExportOnly)` → returns the `exemption_type` string.
  - Wrote `backend/openl/openl_client.py`: reuses exemption.py's normalization helpers,
    calls OpenL over HTTP (httpx), maps `exemption_type` → the existing `ExemptionResult`.
  - Wrote `backend/openl/scripts/differential_exemption.py`: runs a 1532-case matrix
    through BOTH `exemption.classify_exemption` (oracle) and OpenL, compares the legal
    decision, writes `dist/exemption_differential.json` (the fixture format for TEST-01).
- What I verified (commands + actual output):
  - `POST /admin/deploy/lexmetra` (lmpc-exemption.zip) → 201; `GET /admin/services` →
    `lmpc_exemption` status **DEPLOYED** (compiled clean).
  - 8 hand-picked branch calls all correct, incl. tricky ones:
    cement 30kg→`none` (limit 50kg), cement 60kg→`rule_3_quantity_exclusion`,
    tobacco 5g→`none` (R26 exclusion), unknown qty→`quantity_not_established`,
    wholesale 5kg→`different_declaration_regime`.
  - `differential_exemption.py` → **1532 cases, 1532 matches, 0 mismatches** →
    "FULL PARITY: OpenL matches exemption.py on every case."
  - The 3 literal `test_exemption.py` fixtures (+2 unit-safety cases) → ALL MATCH.
  - **Production-style deploy verified** (no dev deployer): `application-prod.properties`
    with `production-repository.$ref = repo-zip`, zip mounted at
    `/opt/openl/local/repositories/zipped/` → service DEPLOYED, executed correctly
    (`retail sugar 5g` → `rule_26_small_pack`) on a second container (port 8081).
  - `git status`: RULE-01 added ONLY `backend/openl/` + `docs/cdd/agents/RULE-01/`;
    `exemption.py`/`rule_engine.py`/`main.py`/`schema.py`/`rules.json` untouched.
- What I did NOT verify (deferred / not mine):
  - Full pytest suite (pytest not in this venv; test env is TEST-01/DEVOPS-01's). My
    changes are strictly additive and import no existing test, so the floor is unaffected.
  - Only ONE rule migrated so far (the exemption slice). Remaining rules (6/7/8/24/26
    declaration paths, etc.) are NOT migrated — that is step 4, gated on TEST-01's
    official harness per the package ordering.
  - Reason-string parity (excluded by design — see DECISIONS.md).
- Files touched (all new): `backend/openl/{openl_client.py,config/*.properties,
  scripts/*.py,dist/*}`. Installed build/test tooling into `backend/.venv`
  (openpyxl; httpx already present).
