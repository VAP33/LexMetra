# HANDOFF — RULE-01
Prepared: 2026-09-15 (living document — update as work progresses)

## Summary for the next agent (or my future self)
OpenL Tablets is stood up and the FIRST Legal Metrology rule is migrated and proven:
Rule 3 scope/exemption + Rule 26(a) small-pack now execute inside an OpenL decision
table, reachable over HTTP, with **1532/1532 differential parity** against the legacy
`exemption.py` (plus the literal `test_exemption.py` fixtures). Nothing is cut over;
`rule_engine.py`/`exemption.py` remain the source of truth. The next steps are
sequenced: TEST-01 turns the differential harness into the official gate, then the
remaining rules are migrated one-by-one behind it, then the resolver + feature-flag
cutover.

## What I own that is now stable (safe for others to depend on)

### For DEVOPS-01 — the OpenL compose service (package item 4) — NOW UNBLOCKED
Verified, concrete config (no more guessing):
- **Image:** `openltablets/ws:6.4.0` (pin 6.4.0; it is today's `:latest`).
- **Port:** container **8080** (HTTP, Jetty).
- **Healthcheck:** `GET /admin/healthcheck/readiness` → 200 when ready
  (`/admin/healthcheck/startup` → 200 once booted). Use readiness for compose.
- **Rule deployment (RECOMMENDED, production-safe):** deployer OFF; mount deployment
  zip(s) read-only and point the production repository at them:
  - Mount `backend/openl/dist/lmpc-exemption.zip` →
    `/opt/openl/local/repositories/zipped/lmpc-exemption.zip:ro`
  - Provide `/opt/openl/application.properties` (see
    `backend/openl/config/application-prod.properties`) containing:
    `ruleservice.deployer.enabled = false` and `production-repository.$ref = repo-zip`.
  - Verified: service comes up DEPLOYED and executes with the deployer disabled.
- **Do NOT enable the embedded REST deployer in shared/prod** (it lets anyone deploy
  any rules). It is fine for local dev only (`application.properties`).
- **New env var (for the backend, not OpenL):** the resolver reads `OPENL_BASE_URL`
  (default `http://localhost:8080`) and `OPENL_EXEMPTION_PATH` (service path). Coordinate
  the final names with ARCH-01/config.py before wiring. Add `OPENL_BASE_URL` to
  `.env.example` when the resolver lands (that is DEVOPS-01's `.env.example` scope).
- NOTE: the service URL path depends on deploy method (dev deployer named `lexmetra` →
  `lexmetra/lexmetra`; repo-zip zip-name `lmpc-exemption` → `lmpc-exemption/lmpc-exemption`).
  The client path is env-configurable so this is not load-bearing; a stable `<url>` can be
  pinned in `rules-deploy.xml` if a fixed path is desired.

### For TEST-01 — the differential harness seed (my "Contract you produce")
- `backend/openl/scripts/differential_exemption.py` — runs the same inputs through the
  legacy engine and OpenL and emits `{input, old_engine_result, openl_result, match}`.
- `backend/openl/dist/exemption_differential.json` — 1532 fixtures in exactly that shape.
- Parity is on `(is_exempt, exemption_type, rule_id, review_required)`; `reason` prose is
  excluded by design (dynamic text, not a legal value). Please adopt this as the seed for
  the official OpenL regression gate; the interface matches your TEST-BASELINE §"OpenL /
  differential harness" sketch (`fixture → {old, openl} → diff`).
- OpenL must run for the harness: `podman run -d --name openl-rules -p 8080:8080
  -v .../application.properties:/opt/openl/application.properties:ro openltablets/ws:6.4.0`
  then deploy `backend/openl/dist/lmpc-exemption.zip` (dev: `POST /admin/deploy/lexmetra`).

### For ARCH-01 — finalize `01-CONTRACTS.md` §2.4 with real samples
The first table is deployed, so the byte-level JSON can now be pinned. Sample for the
exemption slice (single rule; the full resolver aggregates many):
- Request `POST /{service}/classifyExemption` (application/json):
  `{"saleType","productCategory","massG","volumeMl","quantityEstablished",
    "isPrepackagedFalse","directIndInst","isExportOnly"}`
- Response: a JSON string `exemption_type` ∈ {not_prepackaged,
  industrial_or_institutional_direct_sale, export_only_transaction,
  rule_3_quantity_exclusion, rule_26_small_pack, quantity_not_established,
  different_declaration_regime, unknown_sale_type, none}.
- The resolver maps that onto `RuleFinding`/`ProductInspection` (§1.2). Confirms the
  §1.3 invariant that OpenL can emit EXEMPT and UNCERTAIN-class outcomes, not only PASS/FAIL.

## What I own that is still in flux (do NOT depend on this yet)
- Only ONE rule migrated. The other rules and the full resolver are NOT done.
- The in-backend resolver (httpx client → RuleFinding[]) and the feature flag — step 6,
  only after all rules pass parity. `openl_client.py` is the seed but not yet wired into
  `main.py`.

## Contracts I changed
- None. Consumed `01-CONTRACTS.md` §1 + §2 as-is.

## Open questions I could not resolve myself
- **Legal accuracy** stays with a human Legal Lead. Every migrated threshold still carries
  `verification_status: needs_official_verification` in rules.json; migrating it to a
  decision table does NOT verify it. Flag Rule 3 (25/50 kg, 25 l) and Rule 26(a) (10 g/ml)
  for gazette re-verification.
- **Commit policy** for `backend/openl/**` (mirrors ARCH-01's open question about
  `docs/cdd/**`): owner to confirm branch/commit approach.
