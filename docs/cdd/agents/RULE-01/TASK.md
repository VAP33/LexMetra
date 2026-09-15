# CDD Package — RULE-01 (Rule Engine — OpenL Tablets Migration)

(Verbatim from `CDD/Wave 1/1 RULE-01.md`, copied here for persistent context.)

**Agent ID:** RULE-01
**Role:** Own the migration from the custom Python rule engine to OpenL Tablets. This is the highest-priority, highest-risk Wave 1 agent — the project owner has confirmed OpenL is a hard requirement (an SIH evaluator criterion), so this is not optional scope.

**Purpose:** Get real Legal Metrology rules executing inside OpenL Tablets, reachable from the FastAPI backend, with parity against the existing `rule_engine.py` proven by TEST-01's differential harness before anything is cut over in production.

**You must, in order:**
1. **Do not start by writing decision tables.** First, stand up OpenL Tablets locally: pull `openltablets/ws` (the OpenL RuleServices Docker image), confirm it starts, confirm its default REST endpoints respond. This is a JVM app — you are not writing Java or Python OpenL bindings, you are configuring and deploying Excel-based rule projects to a running service and calling it over HTTP.
2. Pick **one rule** from `rules/rules.json` — the smallest, cleanest one (Rule 3 exemption logic is a reasonable first candidate; avoid Rule 32, which the README itself flags as an unpopulated placeholder) — and re-express it as an OpenL decision table (Excel `.xls`/`.xlsx`), deploy it to your local OpenL instance, and call it from a small Python script over HTTP. Get this single round-trip working before touching anything else.
3. Hand this working single-rule round-trip to TEST-01 to build the differential harness against.
4. Only after the harness exists, migrate the remaining rules one at a time, running the differential test after each one. A rule is "migrated" only when OpenL's output matches `rule_engine.py`'s output on every existing test fixture for that rule — not before.
5. Every rule you migrate must preserve the `verification_status: "needs_official_verification"` flag from `rules.json` — migrating the code is not the same as verifying the legal accuracy, and the README is explicit that a human Legal Lead still owns that separately. Do not silently drop or "clean up" this flag.
6. Once all rules pass differential testing, implement the `RuleSet Resolver → OpenL` contract ARCH-01 defined, replacing the direct `rule_engine.py` calls in `main.py`'s `/inspect` and `/scan` endpoints — but only behind a feature flag, so the old path can still be forced on if something regresses.
7. Update `docker-compose.yml` handoff to DEVOPS-01 with the exact image tag and rule-deployment configuration you actually used — don't leave them guessing.

**You must NOT:**
- Delete or stop maintaining `rule_engine.py` until full parity is proven and ARCH-01 signs off on cutover — it remains the source of truth until then.
- Invent a fictional Python-native OpenL API. If you find yourself writing `import openl`, stop — that's not how this integrates.
- Silently change any rule's legal threshold while "migrating" it. If OpenL's decision-table format forces a representational change, document it in DECISIONS.md and flag it for the Legal Lead's re-verification — never assume the migration is legally equivalent just because the code compiles.

## CONTEXT.md (from package)

- OpenL Tablets: LGPL-3 licensed, actively maintained (6.4.0 released Aug 2026), Java-based. Deploys Excel rule spreadsheets as REST APIs via the `openltablets/ws` Docker image (OpenL RuleServices WS). This is the standard integration path — confirmed current as of this task, not assumed from stale training knowledge.
- Existing rules live in `rules/rules.json` (40K), encoding Legal Metrology Act 2009 + LMPC Rules 2011 — Rules 3, 6, 7, 8, 12, 26, 27, 32, Second Schedule. Every entry carries `verification_status: "needs_official_verification"`.
- Existing engine: `backend/rule_engine.py` (96K) — ties exemption + mandatory fields + numeral height + unit price + sticker suspicion into one PASS/FAIL/UNCERTAIN/EXEMPT verdict. This is your parity target, not your enemy — it's tested against two real product photos successfully.
- Related tests already exist: `test_build05_rule_versioning.py`, `test_build06_rule_version_runtime.py`, `test_rule_engine.py` — read these before writing anything, they encode the current expected behavior.
- Amendment governance (`backend/amendments.py`) already assumes rules eventually deploy somewhere — its `ApprovalState.SCHEDULED → ACTIVE` transition is exactly where an OpenL deployment step belongs once you're further along. Don't build this yet; just be aware the seam exists.

## CONTRACTS.md (from package)

**Contract you consume:** `RuleSet Resolver → OpenL` shape (from ARCH-01) — the input/output JSON contract your OpenL service must honor so nothing downstream changes.
**Contract you consume:** `ExtractedFact`/`ProductInspection` (from `backend/schema.py`, owned by ARCH-01) — this is what OpenL's decision tables receive as input; don't redefine field names, map to the existing ones.
**Contract you produce:** the differential-test fixture format TEST-01 needs (same input → old engine result + OpenL result).
**Contract you hand to DEVOPS-01:** the exact `openltablets/ws` image tag, rule-deployment path/config, and any new environment variables needed in `docker-compose.yml`.
