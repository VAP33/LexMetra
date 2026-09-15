# CONTRACTS — RULE-01

Authoritative contract definitions live in `docs/cdd/01-CONTRACTS.md` (owned by
ARCH-01). This file only records RULE-01's side: what it consumes, produces, and
hands off. Do not fork any contract here — propose changes as SCRs to ARCH-01.

## Consume (do not fork)
- **`RuleSet Resolver → OpenL`** (`01-CONTRACTS.md` §2): shape frozen; exact
  request/response JSON finalized jointly with ARCH-01 *after* the first decision
  table is deployed. Input = `ExtractedFact[]` + existing `RegulatoryContext`
  (`backend/models.py`); output maps back to `RuleFinding[]` + `overall_status`.
- **`ExtractedFact` / `ProductInspection` / `RuleFinding`** (`backend/schema.py`,
  `01-CONTRACTS.md` §1): the verdict shapes OpenL output must map onto. Four
  legal-safety invariants (§1.3) apply unchanged to OpenL output:
  1. `FactStatus` = exactly {PASS, FAIL, UNCERTAIN, EXEMPT}; no fifth verdict.
  2. Confidence ≠ legality; low confidence never silently becomes FAIL.
  3. Absence ≠ non-compliance; insufficient coverage ⇒ UNCERTAIN, never FAIL.
  4. Conflicting readings cap a finding at UNCERTAIN.
  → An OpenL table that can only emit PASS/FAIL is **non-conformant**: it must be
    able to emit UNCERTAIN and EXEMPT.
- **`RegulatoryContext`** (`backend/models.py`): pass-through fields incl.
  `inspection_date` (required — drives dated rule versioning). A dated request
  with no resolvable rule version is an ERROR, not a fallback to "today".

## Produce
- The **OpenL rule projects** (Excel decision tables + `rules-deploy.xml`) and the
  **RuleSet Resolver** client in the FastAPI backend that maps OpenL JSON ⇄ the
  frozen verdict shapes.
- The **differential-test fixture format** TEST-01 needs: same input →
  `{old_engine_result, openl_result}` for a rule, comparable on the
  `RuleFinding`/`overall_status` shapes.
- The finalized byte-level `01-CONTRACTS.md` §2.4 JSON (jointly, with ARCH-01),
  once the first table is deployed.

## Hand to DEVOPS-01 (for the compose extension — blocking for them)
- Exact image tag, rule-deployment path/config, new env vars. See
  `HANDOFF.md` for the current confirmed values.
