# DECISIONS — RULE-01

## 2026-09-15 — Use podman (not docker) to run OpenL
- Context: TASK step 1 says "pull `openltablets/ws`" via Docker, but this host has
  no docker daemon socket; it has rootless podman 5.8.4 (same as DEVOPS-01 used).
- Options considered: (a) install/start dockerd; (b) use podman, which is
  CLI-compatible for pull/run/logs.
- Decision: use podman. Commands are identical (`podman pull/run/logs`).
- Why: podman is already the verified runtime here; installing dockerd is out of
  RULE-01 scope (DEVOPS-01 owns runtime). The image and its REST contract are
  runtime-agnostic — DEVOPS-01's compose service will still say `openltablets/ws`.
- Reversible? Yes, trivially — the artifact handed to DEVOPS-01 is the image
  tag + deploy config, not the local runtime choice.

## 2026-09-15 — Pin image tag to `openltablets/ws:6.4.0`
- Context: pulled `:latest`; DEVOPS-01 needs an exact, reproducible tag for compose.
- Decision: hand off `openltablets/ws:6.4.0` (the version label on today's `:latest`).
- Why: `:latest` drifts; 6.4.0 is the version the package names and what we tested.
- Reversible? Yes — a later OpenL release is a one-line tag bump + re-test.

## 2026-09-15 — First rule to migrate: Rule 3 scope/exemption (+ Rule 26(a))
- Context: TASK step 2 says pick the smallest, cleanest rule; suggests Rule 3.
- Decision: migrate the `backend/exemption.py` logic (Rule 3 quantity exclusion +
  industrial/institutional + Rule 26(a) small-pack), which is exactly one pure,
  self-contained, well-tested function reading thresholds from `rules.json`.
- Why: it is a pure function with no image/OCR dependency, has its own test file
  (`test_exemption.py`), and its four legal-safety behaviors are explicit — an
  ideal, low-risk first decision table with a clear parity oracle.
- Reversible? Yes — nothing is cut over; `exemption.py`/`rule_engine.py` stay
  authoritative until TEST-01 proves parity and ARCH-01 signs off (per §2.5).

## 2026-09-15 — OpenL returns `exemption_type`; Python resolver maps it to the verdict
- Context: `ExemptionResult` has 5 fields (is_exempt, reason, rule_id, exemption_type,
  review_required). Constructing a 5-field object per row in a decision table is verbose
  and error-prone; and the legacy `reason` embeds dynamic values (quantities) that OpenL
  cannot reproduce byte-for-byte.
- Decision: the OpenL decision table returns ONE string — the `exemption_type` (the legal
  classification). The Python client maps that type → the full `ExemptionResult`.
- Why: the legal content (branch precedence, thresholds, exclusion sets) is 100% in OpenL.
  The mapping (type → is_exempt/rule_id/review_required) is a *deterministic consequence*
  of the type plus each rule's `verification_status` in rules.json — NOT an independent
  legal threshold, so it does not violate "never silently change a threshold".
- Parity is asserted on `(is_exempt, exemption_type, rule_id, review_required)`. `reason`
  prose is deliberately EXCLUDED from parity (descriptive text, not a legal value).
- Reversible? Yes — the table could later return a full datatype if a downstream need
  requires OpenL-authored reason text.

## 2026-09-15 — Canonical numeric inputs with a -1.0 sentinel (no nulls into OpenL)
- Context: exemption.py separates mass vs volume (never converts between them) and treats
  zero/negative/absent quantity as "not established". Passing nullable Doubles into OpenL
  risks NPEs in decision-table expressions.
- Decision: the Python client pre-normalizes (reusing exemption.py's own `_to_grams`,
  `_to_millilitres`, `quantity_is_established`) and passes `massG`/`volumeMl` as doubles
  with **-1.0 = "not applicable"**, plus an explicit `quantityEstablished` boolean and the
  tri-state Optionals flattened to booleans.
- Why: unit aliasing / establishment is data-cleaning, not legal policy — it already lives
  in exemption.py and is reused verbatim, so the differential test isolates ONLY the legal
  decision, which is what moved into OpenL. The sentinel keeps decision-table expressions
  null-safe and simple. This is a representational choice, documented per the package's
  "if representation forces a change, document it" rule; NO threshold value changed.
- Reversible? Yes.

## 2026-09-15 — Thresholds are GENERATED from rules.json into the table
- Context: the package forbids silently changing legal thresholds during migration.
- Decision: the xlsx generator reads Rule 3 (25 kg / 50 kg / 25 l) and Rule 26(a)
  (10 g / 10 ml) thresholds directly from `rules/rules.json` and bakes them into the
  decision table. rules.json remains the single source of truth; the table is derived.
- Why: eliminates hand-transcription drift and makes the provenance explicit/auditable.
  The migration inherently moves thresholds INTO the decision table (that is what an OpenL
  rule IS); generating them from the JSON is the safest way to do that faithfully.
- FLAG FOR LEGAL LEAD: the thresholds still carry `verification_status:
  needs_official_verification` in rules.json; migrating them to OpenL does NOT verify them.
- Reversible? Yes — regenerate from an updated rules.json.

## 2026-09-15 — Two verified deploy methods; recommend repo-zip volume for DEVOPS-01
- Context: package item 7 — hand DEVOPS-01 the exact deploy config, "don't leave them guessing".
- Options verified end-to-end: (a) DEV: embedded REST deployer (`ruleservice.deployer.enabled
  = true` + `repo-file`) — `POST /admin/deploy`; (b) PROD: `production-repository.$ref =
  repo-zip`, deployer OFF, deployment zip mounted read-only into
  `/opt/openl/local/repositories/zipped/`.
- Decision: recommend (b) repo-zip volume for the compose service; keep the deployer
  disabled in any shared/prod environment (it lets anyone deploy any rules).
- Why: (b) is declarative, reproducible, and read-only; (a) is a convenience for local dev.
- Reversible? Yes — both are config-only.

## 2026-09-15 — Client uses httpx (already a backend dependency)
- Context: `openl_client.py` will move into the backend for the eventual resolver.
- Decision: use `httpx` (already pinned in `backend/requirements.txt`), not `requests`.
- Why: avoids introducing a new backend runtime dependency for the resolver cutover.
- Reversible? Yes.
