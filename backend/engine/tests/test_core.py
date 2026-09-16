"""
Core generic-engine tests: PASS/FAIL/UNCERTAIN/NOT_APPLICABLE/EXEMPTED,
missing/ambiguous/conflicting evidence, AND/OR/NOT + nesting, numeric
comparisons, ranges, dates, cross-field comparisons.

None of these tests reference any real-world regulation: they exist to prove
the engine is generic, i.e. that identical evaluation code produces correct
results for arbitrary made-up rules and fields.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from engine import Evidence, RuleEngine, load_ruleset_from_dict
from engine.results import ApplicabilityStatus, ComplianceStatus


def make_engine(rules, **kwargs):
    return RuleEngine(load_ruleset_from_dict({"rules": rules}), **kwargs)


def run_one(rule, evidence, context=None):
    engine = make_engine([rule])
    report = engine.evaluate(evidence, context or {})
    return report.results[0]


# ---------------------------------------------------------------------------
# Basic statuses
# ---------------------------------------------------------------------------

def test_pass_when_condition_true():
    r = run_one(
        {"rule_id": "R1", "condition": {"op": "eq", "field": "color", "value": "red"}},
        Evidence().set_field("color", "red"),
    )
    assert r.status is ComplianceStatus.PASS
    assert r.applicability is ApplicabilityStatus.APPLICABLE


def test_fail_when_condition_false():
    r = run_one(
        {"rule_id": "R1", "condition": {"op": "eq", "field": "color", "value": "red"}},
        Evidence().set_field("color", "blue"),
    )
    assert r.status is ComplianceStatus.FAIL


def test_uncertain_when_evidence_missing():
    r = run_one(
        {"rule_id": "R1", "condition": {"op": "eq", "field": "color", "value": "red"}},
        Evidence(),
    )
    assert r.status is ComplianceStatus.UNCERTAIN
    assert "color" in r.missing_evidence


def test_uncertain_when_confidence_below_threshold():
    r = run_one(
        {"rule_id": "R1", "condition": {"op": "eq", "field": "color", "value": "red"}},
        Evidence().set_field("color", "red", confidence=0.1),
    )
    assert r.status is ComplianceStatus.UNCERTAIN


def test_uncertain_never_silently_becomes_pass_or_fail():
    """The single most important legal-safety invariant of the whole engine."""
    for _ in range(5):
        r = run_one(
            {"rule_id": "R1", "condition": {"op": "gt", "field": "x", "value": 5}},
            Evidence(),
        )
        assert r.status not in (ComplianceStatus.PASS, ComplianceStatus.FAIL)
        assert r.status is ComplianceStatus.UNCERTAIN


def test_not_applicable_when_applicability_false():
    r = run_one(
        {
            "rule_id": "R1",
            "applicability": {"op": "eq", "field": "category", "value": "food"},
            "condition": {"op": "exists", "field": "allergen_list"},
        },
        Evidence().set_field("category", "electronics"),
    )
    assert r.applicability is ApplicabilityStatus.NOT_APPLICABLE
    assert r.status is ComplianceStatus.NOT_APPLICABLE


def test_not_applicable_is_never_reported_as_fail():
    r = run_one(
        {
            "rule_id": "R1",
            "applicability": {"op": "eq", "field": "category", "value": "food"},
            "condition": {"op": "exists", "field": "allergen_list"},
        },
        Evidence().set_field("category", "electronics"),
    )
    assert r.status is not ComplianceStatus.FAIL


def test_uncertain_applicability_when_applicability_condition_unresolvable():
    """
    Applicability that depends on a VALUE comparison (not mere presence)
    against missing evidence must be UNCERTAIN, not silently NOT_APPLICABLE.
    """
    r = run_one(
        {
            "rule_id": "R1",
            "applicability": {"op": "eq", "field": "category", "value": "food"},
            "condition": {"op": "exists", "field": "x"},
        },
        Evidence(),
    )
    assert r.applicability is ApplicabilityStatus.UNCERTAIN
    assert r.status is ComplianceStatus.UNCERTAIN


def test_uncertain_applicability_when_declared_scope_context_missing():
    """
    ``applies_to`` scope-matching (section 24 compatibility mechanism) must
    also fail safe to UNCERTAIN, not NOT_APPLICABLE, when the context needed
    to judge scope was never supplied by the caller.
    """
    r = run_one(
        {"rule_id": "R1", "applies_to": {"sale_type": ["retail"]},
         "condition": {"op": "exists", "field": "x"}},
        Evidence(), context={},  # sale_type not supplied at all
    )
    assert r.applicability is ApplicabilityStatus.UNCERTAIN
    assert r.status is ComplianceStatus.UNCERTAIN


def test_exemption_short_circuits_before_ordinary_requirements():
    r = run_one(
        {
            "rule_id": "R1",
            "exemptions": [{"id": "small_pack", "condition": {"op": "lte", "field": "qty", "value": 5}}],
            "condition": {"op": "exists", "field": "nutrition_panel"},  # would otherwise FAIL (missing)
        },
        Evidence().set_field("qty", 3),
    )
    assert r.applicability is ApplicabilityStatus.EXEMPTED
    assert r.status is ComplianceStatus.EXEMPTED


def test_exempted_is_distinct_from_not_applicable():
    exempt = run_one(
        {"rule_id": "R1",
         "exemptions": [{"id": "e1", "condition": {"op": "always"}}],
         "condition": {"op": "exists", "field": "x"}},
        Evidence(),
    )
    not_applicable = run_one(
        {"rule_id": "R1", "applicability": {"op": "never"}, "condition": {"op": "exists", "field": "x"}},
        Evidence(),
    )
    assert exempt.status is ComplianceStatus.EXEMPTED
    assert not_applicable.status is ComplianceStatus.NOT_APPLICABLE
    assert exempt.status != not_applicable.status


def test_uncertain_is_distinct_from_both():
    uncertain = run_one(
        {"rule_id": "R1", "condition": {"op": "exists", "field": "unset_field"},
         "applicability": {"op": "eq", "field": "always_true_but_missing_conf", "value": "x"}},
        Evidence(),
    )
    # applicability itself unresolvable -> UNCERTAIN, not EXEMPTED/NOT_APPLICABLE
    assert uncertain.status is ComplianceStatus.UNCERTAIN


# ---------------------------------------------------------------------------
# Ambiguous / conflicting evidence
# ---------------------------------------------------------------------------

def test_conflicting_evidence_marked_not_present_is_uncertain():
    ev = Evidence()
    ev.set_field("mrp", None, present=False, notes="two OCR readings disagreed: 50 vs 90")
    r = run_one({"rule_id": "R1", "condition": {"op": "exists", "field": "mrp"}}, ev)
    # exists is a determinate check even when the underlying value is unusable...
    assert r.status is ComplianceStatus.FAIL  # field genuinely not present/usable
    # ...but a rule that needs the VALUE must be UNCERTAIN, not guess one side.
    r2 = run_one({"rule_id": "R2", "condition": {"op": "eq", "field": "mrp", "value": 50}}, ev)
    assert r2.status is ComplianceStatus.UNCERTAIN


# ---------------------------------------------------------------------------
# Boolean combinators, including deep nesting
# ---------------------------------------------------------------------------

def test_and_or_not_nested():
    condition = {
        "op": "and",
        "args": [
            {"op": "or", "args": [
                {"op": "eq", "field": "a", "value": 1},
                {"op": "eq", "field": "b", "value": 2},
            ]},
            {"op": "not", "args": [{"op": "eq", "field": "c", "value": 3}]},
        ],
    }
    ev = Evidence().set_field("a", 1).set_field("b", 99).set_field("c", 4)
    r = run_one({"rule_id": "R1", "condition": condition}, ev)
    assert r.status is ComplianceStatus.PASS


def test_and_false_dominates_over_unknown():
    condition = {"op": "and", "args": [
        {"op": "eq", "field": "known_false", "value": "x"},
        {"op": "eq", "field": "unknown_field", "value": "y"},
    ]}
    ev = Evidence().set_field("known_false", "not-x")
    r = run_one({"rule_id": "R1", "condition": condition}, ev)
    assert r.status is ComplianceStatus.FAIL  # not UNCERTAIN: FALSE dominates


def test_or_true_dominates_over_unknown():
    condition = {"op": "or", "args": [
        {"op": "eq", "field": "known_true", "value": "x"},
        {"op": "eq", "field": "unknown_field", "value": "y"},
    ]}
    ev = Evidence().set_field("known_true", "x")
    r = run_one({"rule_id": "R1", "condition": condition}, ev)
    assert r.status is ComplianceStatus.PASS


def test_and_of_unknown_and_true_is_unknown():
    condition = {"op": "and", "args": [
        {"op": "eq", "field": "known_true", "value": "x"},
        {"op": "eq", "field": "unknown_field", "value": "y"},
    ]}
    ev = Evidence().set_field("known_true", "x")
    r = run_one({"rule_id": "R1", "condition": condition}, ev)
    assert r.status is ComplianceStatus.UNCERTAIN


def test_deeply_nested_conditions():
    def nest(depth):
        if depth == 0:
            return {"op": "eq", "field": "leaf", "value": 1}
        return {"op": "and", "args": [nest(depth - 1)]}
    r = run_one({"rule_id": "R1", "condition": nest(20)}, Evidence().set_field("leaf", 1))
    assert r.status is ComplianceStatus.PASS


# ---------------------------------------------------------------------------
# Numeric / range / cross-field
# ---------------------------------------------------------------------------

def test_numeric_operators():
    cases = [
        ("gt", 5, 3, ComplianceStatus.PASS),
        ("gt", 3, 5, ComplianceStatus.FAIL),
        ("gte", 5, 5, ComplianceStatus.PASS),
        ("lt", 3, 5, ComplianceStatus.PASS),
        ("lte", 5, 5, ComplianceStatus.PASS),
    ]
    for op, a, b, expected in cases:
        r = run_one({"rule_id": "R1", "condition": {"op": op, "field": "x", "value": b}},
                    Evidence().set_field("x", a))
        assert r.status is expected, f"{op}({a},{b}) expected {expected}, got {r.status}"


def test_between_inclusive():
    r = run_one({"rule_id": "R1", "condition": {"op": "between", "field": "x", "min": 1, "max": 10}},
                Evidence().set_field("x", 10))
    assert r.status is ComplianceStatus.PASS


def test_between_exclusive():
    r = run_one({"rule_id": "R1", "condition": {"op": "between", "field": "x", "min": 1, "max": 10,
                                                 "max_inclusive": False}},
                Evidence().set_field("x", 10))
    assert r.status is ComplianceStatus.FAIL


def test_cross_field_comparison():
    r = run_one(
        {"rule_id": "R1", "condition": {"op": "eq", "field": "declared_weight", "value_field": "measured_weight",
                                         "tolerance": 0.5}},
        Evidence().set_field("declared_weight", 100.2).set_field("measured_weight", 100.0),
    )
    assert r.status is ComplianceStatus.PASS


def test_cross_field_out_of_tolerance_fails():
    r = run_one(
        {"rule_id": "R1", "condition": {"op": "eq", "field": "declared_weight", "value_field": "measured_weight",
                                         "tolerance": 0.1}},
        Evidence().set_field("declared_weight", 100.2).set_field("measured_weight", 100.0),
    )
    assert r.status is ComplianceStatus.FAIL


# ---------------------------------------------------------------------------
# Text operators
# ---------------------------------------------------------------------------

def test_contains_and_regex():
    ev = Evidence().set_field("care", "Call 1800-000-000 for help")
    r1 = run_one({"rule_id": "R1", "condition": {"op": "contains", "field": "care", "value": "1800"}}, ev)
    r2 = run_one({"rule_id": "R2", "condition": {"op": "regex", "field": "care", "pattern": r"\d{4}-\d{3}-\d{3}"}}, ev)
    assert r1.status is ComplianceStatus.PASS
    assert r2.status is ComplianceStatus.PASS


def test_in_list_and_not_in_list():
    ev = Evidence().set_field("category", "food")
    r1 = run_one({"rule_id": "R1", "condition": {"op": "in_list", "field": "category",
                                                  "values": ["food", "cosmetics"]}}, ev)
    r2 = run_one({"rule_id": "R2", "condition": {"op": "not_in_list", "field": "category",
                                                  "values": ["electronics"]}}, ev)
    assert r1.status is ComplianceStatus.PASS
    assert r2.status is ComplianceStatus.PASS


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def test_date_comparison():
    ev = Evidence().set_field("mfg_date", "2026-01-15")
    r = run_one({"rule_id": "R1", "condition": {"op": "date_before", "field": "mfg_date", "value": "2026-06-01"}}, ev)
    assert r.status is ComplianceStatus.PASS


def test_unparseable_date_is_engine_error_not_fail():
    ev = Evidence().set_field("mfg_date", "not-a-date")
    r = run_one({"rule_id": "R1", "condition": {"op": "date_before", "field": "mfg_date", "value": "2026-06-01"}}, ev)
    assert r.status is ComplianceStatus.ENGINE_ERROR
    assert r.error


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

def test_unit_conversion_in_comparison():
    r = run_one(
        {"rule_id": "R1", "condition": {"op": "gt", "field": "weight", "value": 0.5, "value_unit": "kg"}},
        Evidence().set_field("weight", 600, unit="g"),
    )
    assert r.status is ComplianceStatus.PASS  # 600g > 0.5kg


def test_incompatible_units_raise_engine_error():
    r = run_one(
        {"rule_id": "R1", "condition": {"op": "gt", "field": "weight", "value": 1, "value_unit": "ml"}},
        Evidence().set_field("weight", 600, unit="g"),
    )
    assert r.status is ComplianceStatus.ENGINE_ERROR


# ---------------------------------------------------------------------------
# Explanations
# ---------------------------------------------------------------------------

def test_explanation_reflects_actual_result():
    r = run_one({"rule_id": "R1", "name": "Test Rule",
                 "condition": {"op": "eq", "field": "x", "value": 1}},
                Evidence().set_field("x", 2))
    assert "R1" in r.explanation
    assert "FAIL" in r.explanation
    assert r.status is ComplianceStatus.FAIL
