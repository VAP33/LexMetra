# CDD Package — RULE-02 (Rule Versioning/Governance for OpenL)

(Verbatim from `CDD/Wave 2/RULE-02.md`, copied here for persistent context.)

**Agent ID:** RULE-02
**Depends on:** RULE-01's proven pattern (Rule 3/26(a) migration, `build_exemption_project.py`, repo-zip deploy). Can start now — RULE-01's pattern is already documented in their HANDOFF/WORKLOG, you don't need to wait for them to finish the remaining rules.

**Purpose:** Generalize RULE-01's one-off "generate a decision table from `rules.json`" script into a repeatable, versioned deployment pipeline, so every future rule migration (and every future amendment) follows one governed path instead of a bespoke script per rule.

**You must:**
1. Read `backend/openl/scripts/build_exemption_project.py` and `differential_exemption.py` in full — this is your reference pattern, not a rewrite target.
2. Generalize the xlsx-generation approach so it can express more than one rule family: a shared builder module that takes a rule spec (from `rules.json`) and emits an OpenL decision table, rather than one hardcoded script per rule.
3. Extend `backend/regulatory/`'s existing immutable, effective-dated versioning pattern to cover **OpenL deployment artifacts**: each generated rule-project zip must be tied to a specific `rules.json` content hash + effective date, and once deployed, that zip is never mutated — a rule change produces a new versioned zip, exactly mirroring how the existing RAG publication governance treats knowledge chunks as immutable once published.
4. Build the versioned-deploy record: a table or file (coordinate with DB-01 if it needs to be a DB table vs. a file manifest) mapping `{rule_id, rule_version, effective_date, zip_hash, deployed_at}` — this is what lets an inspection dated in the past be evaluated against the OpenL rule set that was actually in force then, matching `rule_engine.py`'s existing `apply_rule_versions(...)` dated-inspection behavior (see `01-CONTRACTS.md` §2.2).
5. Do not migrate additional individual rules yourself — that's RULE-01's ongoing step 4. Your job is the **pipeline** those migrations run through, generalized from their first example.

**You must NOT:**
- Touch `exemption.py` or `rule_engine.py` — parity references stay untouched until cutover.
- Invent a second versioning scheme separate from the existing `regulatory/` immutability pattern. Extend it.

## CONTEXT.md

- RULE-01 has already proven the mechanics end-to-end for one rule: xlsx generation via `openpyxl` from `rules.json` thresholds → zip → deploy via `POST /admin/deploy` (dev) or repo-zip volume mount (prod, deployer disabled) → verified with a 1532-case differential harness. Your job is turning that proof into a reusable pipeline, not re-deriving it.
- `backend/regulatory/` and `backend/rag/publication.py` already implement immutable, effective-dated publication for knowledge chunks — read this code, it's the pattern to mirror for rule-project zips, not a new design from scratch.
- OpenL's production deployment method (repo-zip, deployer disabled) is the one to build the pipeline around — RULE-01's HANDOFF.md has the exact config paths (`/opt/openl/local/repositories/zipped/`, `application-prod.properties`).

## CONTRACTS.md

**Contract you consume:** RULE-01's generator pattern (`build_exemption_project.py`) and deploy config (HANDOFF.md); `01-CONTRACTS.md` §2.2's dated-rule-version requirement.
**Contract you produce:** the versioned-deploy manifest format, which RULE-03 needs for its amendment→redeploy trigger, and which FSSAI-01 should reuse rather than fork for its own rule domain.
