# CONTEXT — RULE-01

Repo + environment facts RULE-01 verified on disk / in the running environment,
not assumed. Read alongside `docs/cdd/00-REPOSITORY-BASELINE.md` and
`docs/cdd/01-CONTRACTS.md`.

## Environment (verified 2026-09-15)
- Container runtime: **podman 5.8.4** (rootless, uid 1000). No `docker` daemon
  socket; DEVOPS-01's stack was verified via podman. No `podman-compose`.
- `java` on host: OpenJDK 27-ea (only relevant for local tooling; OpenL runs in
  its own container with its own JVM — we do NOT write Java).
- Host already runs DEVOPS-01's stack: `lexmetra-db-1` (Postgres 16, host
  :55432), `lexmetra-redis-1` (Redis 7), `lexmetra-backend-1` (host :8000).
- Host port **8080** is free and now used by the OpenL container.

## OpenL image (verified 2026-09-15)
- Pulled `docker.io/openltablets/ws:latest`.
  - Image ID `7ab2aff7d117`, size ~390 MB, created 2026-09-10.
  - **`org.opencontainers.image.version` label = `6.4.0`** (matches the package's
    "6.4.0 released Aug 2026" claim). Use tag `openltablets/ws:6.4.0` for pinning.
  - Exposes `8080/tcp`. Entrypoint `/__cacert_entrypoint.sh`, cmd `/opt/openl/start.sh`,
    workdir `/opt/openl`. Server is **Jetty 12.1.12** (not Tomcat), OpenL RuleServices.
- Started as container `openl-rules` (`-p 8080:8080`). Boots in ~7s of JVM time.
- Verified default REST endpoints respond:
  - `GET /` → 200 (RuleServices web UI).
  - `GET /admin/services` → `[]` (JSON; no rule services deployed yet — expected).
  - `GET /admin/healthcheck/startup` → 200.
  - `GET /admin/healthcheck/readiness` → 200.
- Admin API is published under `/admin` (per startup log:
  "Setting the server's publish address to be /admin").

## The parity target (verified in source)
- `backend/rule_engine.py` (~96K) — `run_inspection(...)` is the entrypoint
  (ARCH-01 noted signature at line 1921). Produces `ProductInspection` with
  `findings: List[RuleFinding]` and `overall_status ∈ {PASS,FAIL,UNCERTAIN,EXEMPT}`.
- `backend/exemption.py` — self-contained Rule 3 scope/exemption + Rule 26(a)
  small-pack classifier. Reads thresholds from `rules/rules.json` (does NOT
  hardcode policy). Pure function `classify_exemption(ExemptionInput) ->
  ExemptionResult`. This is the cleanest, smallest, most self-contained unit and
  is the chosen **first migration candidate** (matches the package's suggestion).
  - Key legal-safety behaviors that MUST be preserved in OpenL:
    - Weight and volume are never inter-converted (no density assumption).
    - Zero/negative/absent net quantity ⇒ "quantity_not_established" ⇒
      `is_exempt=False, review_required=True` (NOT a confident non-exemption).
    - Wholesale is NOT an exemption (different declaration regime).
    - Rule 26(a) exclusions (tobacco, pan masala) block the small-pack exemption.
    - `review_required = (verification_status != "verified")`.
- `rules/rules.json` `LMPC-2011-R3-SCOPE` thresholds:
  `general_package_quantity_exemption`: weight_kg_gt=25, volume_l_gt=25;
  `cement_fertilizer_exception`: weight_kg_gt=50. Both carry
  `status: needs_official_verification`.
- `rules/rules.json` `LMPC-2011-R26-SMALL-PACKS`: small_pack_upper_bound
  weight_g_lte=10, volume_ml_lte=10; partial_relaxation_range 10–20 g/ml;
  exclusions tobacco (2016-01-01) + pan masala (2026-02-01).

## Tests that encode current behavior (read before changing anything)
- `backend/tests/test_rule_engine.py` (40 tests), `test_exemption.py` (4),
  `test_build05_rule_versioning.py` (6), `test_build06_rule_version_runtime.py` (6).
- Regression floor: `docs/cdd/TEST-BASELINE.md` — 480 passed / 4 skipped / 0 fail
  on clean DB. Do not drop below this.
