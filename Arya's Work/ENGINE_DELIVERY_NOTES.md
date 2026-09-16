# LexMetra Generic Rule Engine — Delivery Notes

This document is the write-up requested in the task brief (items 1–18).

---

## 1. What was found in the attached project

LexMetra is a working FastAPI + OCR + Postgres + dashboard prototype for
Indian Legal Metrology (Packaged Commodities) Rules, 2011 ("LMPC")
compliance screening. Key pieces:

- `backend/schema.py` — the shared pydantic contract (`ProductInspection`,
  `ExtractedFact`, `RuleFinding`, `InspectionSummary`, evidence/measurement
  types). This is the stable integration surface every module honors.
- `backend/rule_engine.py` (2,405 lines) — the **existing decision logic**.
  `run_inspection(...)` is called from three places in `backend/main.py`
  (`/inspect`, the OCR `/scan` pipeline, and a re-evaluation endpoint).
- `backend/exemption.py` — Rule 3/24/25/26 scope/exemption classification
  (wholesale, export-only, small-pack thresholds).
- `backend/unit_price.py` — Rule 6(11) unit-sale-price arithmetic.
- `rules/rules.json` — rule **metadata** (IDs, legal citations, thresholds,
  versioning) for 19 LMPC rules.
- `backend/tests/test_rule_engine.py` (1,137 lines) — the existing
  regression suite pinning `run_inspection`'s behaviour.

**The critical finding, matching the brief's warning not to assume the
existing engine is correct:** `rules/rules.json` looks like rule data, but
it is not executable. The actual pass/FAIL/UNCERTAIN logic for every
declaration, every exemption threshold, and the unit-price tolerance check
is hard-coded, field-by-field, directly in Python inside
`rule_engine.py`/`exemption.py`. There is no condition language, no
applicability/exemption separation at the data level, no dependency graph,
no rule validation layer, and no way to add a new regulation or product
category without writing new Python functions. This is exactly the
"incomplete/incorrect rule-engine architecture" the brief anticipated.

## 2. What existing rule-engine components were retained

- **`schema.py` contracts** — `ProductInspection`, `ExtractedFact`,
  `RuleFinding`, `InspectionSummary` are reused unchanged as the output
  contract (one additive change, see §3).
- **`exemption.classify_exemption`** — retained as-is and reused as an
  *evidence provider*: it still does the Rule 3/24/25/26 scope
  classification math; the adapter just feeds its `is_exempt` result into
  the generic engine as evidence rather than letting it directly branch
  Python control flow.
- **`unit_price.compute_unit_sale_price`** — retained as-is and reused the
  same way, as the calculation that produces the "expected unit price"
  evidence value the generic engine's tolerance rule compares against.
- **`rules/rules.json`** — left untouched (still used by the legacy path)
  as the source of legal citations/thresholds that were transcribed into
  the new rule data.
- **The legacy `rule_engine.run_inspection` function and all three call
  sites in `main.py` — completely untouched.** This was a deliberate
  compatibility decision: the 1,137-line legacy test suite pins its exact
  behaviour, and this sandbox has no network access to install
  `pydantic`/`pytest`/FastAPI and actually re-run that suite to confirm a
  from-scratch rewrite hadn't regressed it. Rather than risk silently
  breaking a suite I could not execute, the new engine was added as a
  **second, independently-reachable decision path** (`/inspect/v2/engine`),
  so both can be run and compared before anyone switches the default.

## 3. What was replaced

Nothing existing was deleted or rewritten in place. One narrow, additive
schema change was made:

- `schema.FactStatus` gained two new enum members: `NOT_APPLICABLE` and
  `ENGINE_ERROR` (previously it only had `PASS/FAIL/UNCERTAIN/EXEMPT`,
  which cannot represent applicability separately from compliance, or a
  broken-rule-configuration state, as the brief requires in §7–9). This is
  purely additive — nothing in the codebase exhaustively iterates
  `FactStatus`, so existing comparisons against the original four members
  are unaffected. (I could not run the legacy test suite in this sandbox to
  double-check this claim against dependency-requiring code; see §16/§18.)

Conceptually, **for any rule evaluated through the new
`/inspect/v2/engine` path**, the per-field hard-coded Python decision logic
in `rule_engine.py` is replaced by data (`rules/generic/lmpc_rules.json`)
interpreted by the generic engine. The legacy `/inspect` path is
unaffected and keeps using the old logic.

## 4. What was newly implemented

**`backend/engine/`** — a new, standalone, dependency-free (stdlib only)
package:

| File | Responsibility |
|---|---|
| `evidence.py` | Generic normalized-evidence contract (`Evidence`, `EvidenceValue`), dot-path resolution, presence vs. null vs. missing. |
| `conditions.py` | The condition DSL: every operator in the brief (`eq`, `neq`, `gt/gte/lt/lte`, `between`, `contains`/`not_contains`/`starts_with`/`ends_with`, `regex`, `in_list`/`not_in_list`, `boolean`, `date_*`, `exists`/`missing`/`null`/`not_null`, `always`/`never`), `and`/`or`/`not` with arbitrary nesting, **three-valued (Kleene) logic** so unknowns propagate correctly instead of being coerced to true/false. No `eval`/`exec`. |
| `units.py` | Deterministic mass/volume/length/time/count/ratio conversion registry; extensible via `register_unit()` without touching engine code. |
| `calc.py` | Deterministic derived calculations (`add/sub/mul/div`, `percent_diff`, `abs`, `convert_unit`) — no `eval`. |
| `rule_model.py` | The generic `Rule`/`RuleSet` schema (plain dataclasses, see §6). |
| `validate.py` | Rule validation: duplicate IDs, unknown operators, malformed conditions, bad regex, missing conditions, bad date ranges, unknown dependencies, circular dependencies. Raises before any evaluation happens. |
| `dependency.py` | Topological sort + explicit cycle detection with the actual cycle path. |
| `evaluator.py` | `RuleEngine` — orchestrates applicability → exemptions → derived calcs → requirements → evidence-citation → per-rule audit trail. |
| `aggregate.py` | Severity/priority-aware overall-result aggregation (not a PASS/FAIL count). |
| `results.py` | `RuleResult`, `EngineReport`, `ApplicabilityStatus`, `ComplianceStatus` result types. |
| `lexmetra_adapter.py` | The integration layer described in §4/§24 of the brief — translates between LexMetra's pydantic contracts and the generic engine. |
| `tests/` | 69 passing tests (see §16). |

**`rules/generic/lmpc_rules.json`** — the real LMPC mandatory-declaration,
exemption-linked, unit-price-tolerance, and numeral-height rules,
re-expressed as data for the generic engine (11 rules).

**`rules/generic/example_food_labeling_rules.json`** — a second,
unrelated, illustrative regulation (packaged-food allergen/nutrition
labeling) used purely to prove "no module bias": the identical
`RuleEngine` class evaluates it correctly with zero code changes.

**One new API endpoint**: `POST /inspect/v2/engine` in `backend/main.py`,
same request/response contract as `/inspect`, backed by the new engine.

## 5. Final architecture

```
LEGAL REQUIREMENTS (LMPC 2011, or any future regulation)
        |
STRUCTURED RULE DATA          rules/generic/<regulation>.json
        |
GENERIC RULE ENGINE           backend/engine/  (regulation-agnostic code)
        |
EVIDENCE + PRODUCT DATA       backend/engine/lexmetra_adapter.py builds
                               Evidence from RawExtraction + exemption.py +
                               unit_price.py (unchanged domain services)
        |
DETERMINISTIC EVALUATION      engine.RuleEngine.evaluate()
        |
EXPLAINABLE COMPLIANCE RESULT engine.EngineReport --(adapter)--> the
                               EXISTING ProductInspection/RuleFinding/
                               ExtractedFact/InspectionSummary contract
        |
EXISTING REPORT / UI          report.py, dashboard — unchanged, consume
                               ProductInspection exactly as before
```

`backend/engine/` contains **zero** references to "Legal Metrology",
"MRP", "India", or any product category. Everything regulation-specific
lives in `rules/generic/*.json` and in the adapter's field-name choices.

## 6. Rule schema

`engine.rule_model.Rule` (plain dataclass, all fields optional except
`rule_id` and — at evaluation time — either `condition` or
`requirements`):

```
rule_id, name, description
legal_source, regulation, provision, source_page
version, effective_from, effective_to, supersedes, verification_status
applies_to: {context_key: [allowed values]}      # coarse scope match
applicability: <condition tree> | null            # null = always applicable
exemptions: [{id, description, condition}]        # first true one exempts
derived: [{name, expr}]                           # calculations, run before requirements
condition: <condition tree>                       # implicit single requirement
requirements: [{id, description, condition, message_pass/fail/uncertain}]
evidence_required: [field names]                  # documentation/validation aid
depends_on: [rule_id, ...]                        # dependency graph
severity: critical|major|normal|minor|advisory
priority: int
message_pass/fail/uncertain/not_applicable/exempt: optional templates
```

A condition node is `{"op": ..., "field": ..., ...}` or a combinator
`{"op": "and"|"or"|"not", "args": [...]}`. See `rules/generic/*.json` for
real examples of every operator in use.

## 7. How applicability works

`applies_to` is checked first (coarse scope, e.g. `{"trade_type": ["retail",
"ecommerce"]}}`); then `applicability` (a full condition tree) is
evaluated. The three-valued result maps directly:

- condition **TRUE** → `APPLICABLE` → proceed to exemptions/requirements
- condition **FALSE** → `NOT_APPLICABLE` → rule stops here, reported as
  `NOT_APPLICABLE`, **never** `FAIL`
- condition **UNKNOWN** (missing evidence needed to judge scope) →
  `UNCERTAIN` → rule stops here, reported as `UNCERTAIN`, not silently
  treated as either applicable or not

## 8. How exemptions work

After applicability is confirmed `APPLICABLE`, each entry in `exemptions`
is evaluated in order. The **first one that evaluates TRUE** short-circuits
the rule to `EXEMPTED` — distinct from both `NOT_APPLICABLE` (out of scope
entirely) and `PASS` (evaluated and compliant). If an exemption condition
is `UNKNOWN`, it simply does not fire (evaluation continues to the next
exemption / to the requirements) — an unresolvable exemption claim never
grants an exemption by default.

## 9. How UNCERTAIN is handled

Three-valued (Kleene K3) logic runs through every condition, calculation,
and aggregation step. A leaf condition is `UNKNOWN` whenever:
- the referenced evidence field is absent (`EvidenceValue.present is
  False/None` or path resolves to `MISSING`), or
- its `confidence` is below the configured floor (default 0.55).

`AND` propagates `UNKNOWN` unless a `FALSE` sibling already dominates;
`OR` propagates `UNKNOWN` unless a `TRUE` sibling already dominates. This
is what guarantees "insufficient evidence" can never silently become PASS
or FAIL (locked in by `test_uncertain_never_silently_becomes_pass_or_fail`
and `test_and_false_dominates_over_unknown` /
`test_or_true_dominates_over_unknown` in `tests/test_core.py`).

A genuine data/config problem (bad regex, unparseable date, incompatible
units, unresolved dependency) is **not** UNCERTAIN — it raises
`RuleConfigurationError`, captured per-rule as `ComplianceStatus.ENGINE_ERROR`
(never silently PASS/FAIL), and forces the overall aggregation to
`ENGINE_ERROR` so a broken rule can never hide inside an otherwise-green
report.

## 10. How evidence is tracked

`Evidence` holds `EvidenceValue` objects: `value`, `unit`, `confidence`,
`present`, `source_text`, `source_page`, `provenance`, `alternatives`,
`notes`. Every leaf condition that references a field records an
`EvidenceCitation` (field, observed value, normalized value, confidence,
source page, provenance) into the rule's `RuleResult.evidence` list, and
every field an `UNKNOWN` result couldn't resolve is listed in
`missing_evidence`. Nothing is ever fabricated: absent evidence stays
absent (`present=None`/`MISSING`), never defaulted to a guessed value.

## 11. How the audit trail works

Every rule evaluation builds an ordered `trace["stages"]` list:
`rule_selected → applicability → exemption_check (0+) → calculation →
condition_evaluation (1+) → evidence → rule_result`, each stage carrying
the actual sub-trace (operator, field, observed/expected values, tri-state
result) that produced it — not a post-hoc summary. `EngineReport` also
records the dependency-resolved evaluation order. See
`test_audit_trail_contains_full_pipeline_stages` and
`test_lmpc_ruleset_produces_full_audit_trail_for_every_rule`.

## 12. How overall compliance is calculated

`engine.aggregate.aggregate()` (not a PASS/FAIL count):

1. Any rule `ENGINE_ERROR` → overall `ENGINE_ERROR` (blocks any verdict).
2. Any `FAIL` on a `critical`/`major` severity rule → overall `FAIL`.
3. Any other `FAIL` → overall `FAIL` (configurable to downgrade to
   `UNCERTAIN` via `AggregationPolicy.downgrade_minor_fail_to_uncertain`,
   off by default — conservative).
4. No `FAIL`, but any `UNCERTAIN` → overall `UNCERTAIN`.
5. All applicable rules `PASS` → overall `PASS`.
6. No rule applicable at all → overall `NOT_APPLICABLE`.

The `AggregationExplanation` returned always states which rule(s) drove the
result and which policy branch fired.

## 13. How to add a completely new regulation

1. Write `rules/generic/<your_regulation>.json` (schema in §6) — no code.
2. Write a small evidence-building function (or reuse
   `engine.evidence.Evidence` directly) that populates the field names your
   rules reference, from whatever source system you have (OCR, a form, an
   API).
3. `RuleEngine(load_ruleset(path)).evaluate(evidence, context)`.

`rules/generic/example_food_labeling_rules.json` in this delivery is a
complete, working example of exactly this, evaluated by the same
unmodified `engine.evaluator` code as LMPC (see
`backend/engine/tests/test_genericity_e2e.py`).

## 14. How to add a completely new product/category

Use `applies_to`/`applicability` on the relevant rules (e.g. `{"category":
["packaged_food"]}` or a condition on `context.category`), and/or write a
new small rule file scoped to that category. No engine code changes are
needed either way — this is the same mechanism as adding a regulation.

## 15. Complete test results

69/69 tests passing, run via a small dependency-free runner (see §17,
§18 — `pytest` itself is unavailable offline in this sandbox, but every
file is ordinary `assert`-based and will also run unmodified under
`pytest backend/engine/tests` wherever `pytest` is installed):

- `tests/test_core.py` — 30 tests: PASS/FAIL/UNCERTAIN/NOT_APPLICABLE/
  EXEMPTED, missing/low-confidence evidence, AND/OR/NOT incl. deep nesting
  and Kleene-logic dominance rules, numeric/range/cross-field/text/date/
  unit operators, config-error handling, explanations.
- `tests/test_advanced.py` — 23 tests: dependency resolution and ordering,
  circular-dependency detection, all rule-validation rejections (duplicate
  IDs, unknown operators, malformed conditions, empty rules, bad date
  ranges, bad regex, bad severity), versioning, aggregation policy
  (critical-fail dominance, uncertain-blocks-pass, engine-error
  precedence, all-not-applicable), full audit trail, evidence provenance,
  missing-evidence naming, explanation honesty.
- `tests/test_genericity_e2e.py` — 16 tests: full evaluation of the real
  11-rule LMPC ruleset (mandatory declarations, small-pack exemption,
  country-of-origin applicability, unit-price tolerance, numeral height)
  AND the unrelated 4-rule food-allergen ruleset, proving identical engine
  code handles both correctly.

**Not run in this delivery** (see §18): the pre-existing
`backend/tests/test_rule_engine.py` (1,137 lines) and the new
`lexmetra_adapter.py` — both require `pydantic`/FastAPI, which could not be
installed in this offline sandbox (no network egress; `pip`/`uv install`
both fail with no matching distribution). The adapter was written and
statically compiled (`python -m py_compile`) against the exact field names
and signatures found by inspecting `schema.py`, `exemption.py`, and
`unit_price.py`, but has not been executed end-to-end.

## 16. Exact commands to run the project

```bash
# The new, dependency-free generic engine + its full test suite:
cd LexMetra
python3 backend/engine/tests/run_tests.py
# (or, once pytest is installed:)
pip install pytest
pytest backend/engine/tests -v

# The existing project (unchanged), once its dependencies are installed:
pip install -r backend/requirements.txt
cd backend && uvicorn main:app --reload
# Legacy path (unchanged):      POST /inspect
# New generic-engine path:      POST /inspect/v2/engine

# Re-run the EXISTING regression suite to confirm no regressions from the
# additive FactStatus change before switching any default:
pytest backend/tests/test_rule_engine.py -v
```

## 17. Any remaining limitations

- **The legacy `run_inspection` was not replaced**, only supplemented. The
  brief's "complete rule engine ... inside this existing project" is
  satisfied in the sense that a complete, generic, tested engine is now
  built and reachable end-to-end via a real API endpoint — but a full
  cutover (retiring `rule_engine.py`'s hard-coded logic and repointing all
  three legacy call sites) is a follow-up, gated on being able to actually
  run the existing 1,137-line regression suite first, which this sandbox
  cannot do (no network).
- **Not every legacy rule has a generic-engine equivalent yet.** Converted:
  the 8 mandatory Rule 6(1) declarations, small-pack/export/wholesale
  exemption gating, Rule 6(11) unit-price tolerance, Rule 5 standard-pack
  matching, and numeral-height comparison. Not yet converted: PDP-area/
  font-size geometry rules (Rule 7), placement rules (Rule 8), returnable-
  bottle handling, e-commerce-specific Rule 6(10) nuances, registration
  (Rule 27), advertisement (Rule 31), and penalty schedule (Rule 32) — these
  remain legacy-only for now. Adding them is pure rule-data work (§13), not
  engine work.
- **`/inspect/v2/engine` does not persist to the database.** `db.save_inspection`
  was deliberately not called for the new path, since I could not verify
  its assumptions (e.g. status-column constraints) against the new
  `FactStatus.NOT_APPLICABLE`/`ENGINE_ERROR` values without a live Postgres
  instance and the actual dependency stack.
- **Numeral-height/geometry measurement itself is unconverted** — it
  remains a `calibration.py`/CV concern that produces a number the generic
  engine's `LMPC-7-NUMERAL-HEIGHT` rule then compares against a
  context-supplied threshold. This matches the brief's instruction that
  OCR/measurement systems provide evidence but never make the decision.
- **This delivery could not run any pydantic/FastAPI-dependent code** in
  its own execution sandbox (no network access to install dependencies).
  All engine-package testing (69 tests) is real and executed; the
  adapter/endpoint integration is code-complete and has been statically
  verified against the actual schema/module signatures found in the ZIP,
  but needs a first live run (`pytest backend/tests/`, then a manual
  `POST /inspect/v2/engine`) in an environment with dependencies installed
  before being trusted in production.
