"""
Advanced generic-engine tests: rule dependencies, circular-dependency
detection, versioning/effective-dates, rule validation (invalid rules must
never silently execute), aggregation policy, audit trail completeness, and
evidence/provenance tracking.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from engine import (
    CircularDependencyError,
    Evidence,
    RuleEngine,
    RuleValidationError,
    load_ruleset_from_dict,
)
from engine.dependency import topological_order
from engine.results import ApplicabilityStatus, ComplianceStatus
from engine.validate import find_problems


def make_engine(rules, **kwargs):
    return RuleEngine(load_ruleset_from_dict({"rules": rules}), **kwargs)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def test_dependency_result_is_addressable_by_dependent_rule():
    rules = [
        {"rule_id": "classify", "condition": {"op": "eq", "field": "material", "value": "glass"}},
        {"rule_id": "needs_fragile_label", "depends_on": ["classify"],
         "condition": {"op": "eq", "field": "context.rule_results.classify.status", "value": "PASS"}},
    ]
    engine = make_engine(rules)
    report = engine.evaluate(Evidence().set_field("material", "glass"), {})
    assert report.by_id("classify").status is ComplianceStatus.PASS
    assert report.by_id("needs_fragile_label").status is ComplianceStatus.PASS


def test_dependency_chain_evaluated_in_correct_order():
    rules = [
        {"rule_id": "C", "depends_on": ["B"], "condition": {"op": "always"}},
        {"rule_id": "B", "depends_on": ["A"], "condition": {"op": "always"}},
        {"rule_id": "A", "condition": {"op": "always"}},
    ]
    ruleset = load_ruleset_from_dict({"rules": rules})
    order = topological_order(ruleset)
    assert order.index("A") < order.index("B") < order.index("C")


def test_circular_dependency_detected():
    rules = [
        {"rule_id": "A", "depends_on": ["B"], "condition": {"op": "always"}},
        {"rule_id": "B", "depends_on": ["A"], "condition": {"op": "always"}},
    ]
    try:
        make_engine(rules)
        assert False, "expected RuleValidationError for circular dependency"
    except RuleValidationError as exc:
        assert any("circular" in p.lower() for p in exc.problems)


def test_topological_order_raises_on_cycle_directly():
    rules = [
        {"rule_id": "A", "depends_on": ["B"], "condition": {"op": "always"}},
        {"rule_id": "B", "depends_on": ["A"], "condition": {"op": "always"}},
    ]
    ruleset = load_ruleset_from_dict({"rules": rules})
    try:
        topological_order(ruleset)
        assert False, "expected CircularDependencyError"
    except CircularDependencyError as exc:
        assert "A" in exc.cycle and "B" in exc.cycle


def test_dependency_on_unknown_rule_is_a_validation_problem():
    rules = [{"rule_id": "A", "depends_on": ["ghost"], "condition": {"op": "always"}}]
    ruleset = load_ruleset_from_dict({"rules": rules})
    problems = find_problems(ruleset)
    assert any("unknown rule_id" in p for p in problems)


# ---------------------------------------------------------------------------
# Rule validation -- invalid rules must never silently execute
# ---------------------------------------------------------------------------

def test_duplicate_rule_ids_rejected():
    rules = [
        {"rule_id": "X", "condition": {"op": "always"}},
        {"rule_id": "X", "condition": {"op": "never"}},
    ]
    try:
        make_engine(rules)
        assert False, "expected RuleValidationError for duplicate rule_id"
    except RuleValidationError as exc:
        assert any("duplicate" in p.lower() for p in exc.problems)


def test_unknown_operator_rejected():
    rules = [{"rule_id": "X", "condition": {"op": "definitely_not_a_real_operator", "field": "a"}}]
    try:
        make_engine(rules)
        assert False, "expected RuleValidationError for unknown operator"
    except RuleValidationError as exc:
        assert any("unsupported operator" in p.lower() for p in exc.problems)


def test_malformed_condition_rejected():
    rules = [{"rule_id": "X", "condition": {"op": "and", "args": "not-a-list"}}]
    try:
        make_engine(rules)
        assert False, "expected RuleValidationError for malformed 'and'"
    except RuleValidationError:
        pass


def test_rule_with_neither_condition_nor_requirements_rejected():
    rules = [{"rule_id": "X", "name": "empty rule"}]
    try:
        make_engine(rules)
        assert False, "expected RuleValidationError"
    except RuleValidationError as exc:
        assert any("must have either" in p for p in exc.problems)


def test_invalid_effective_date_range_rejected():
    rules = [{"rule_id": "X", "condition": {"op": "always"},
              "effective_from": "2026-06-01", "effective_to": "2025-01-01"}]
    try:
        make_engine(rules)
        assert False, "expected RuleValidationError for bad date range"
    except RuleValidationError as exc:
        assert any("after" in p for p in exc.problems)


def test_invalid_regex_pattern_rejected():
    rules = [{"rule_id": "X", "condition": {"op": "regex", "field": "a", "pattern": "("}}]
    try:
        make_engine(rules)
        assert False, "expected RuleValidationError for invalid regex"
    except RuleValidationError:
        pass


def test_invalid_severity_rejected():
    from engine.rule_model import Rule
    try:
        Rule(rule_id="X", condition={"op": "always"}, severity="super-mega-critical")
        assert False, "expected ValueError for invalid severity"
    except ValueError:
        pass


def test_valid_ruleset_passes_validation_with_no_problems():
    rules = [
        {"rule_id": "A", "condition": {"op": "always"}},
        {"rule_id": "B", "depends_on": ["A"], "condition": {"op": "exists", "field": "x"}},
    ]
    ruleset = load_ruleset_from_dict({"rules": rules})
    assert find_problems(ruleset) == []


# ---------------------------------------------------------------------------
# Versioning / effective dates
# ---------------------------------------------------------------------------

def test_rule_carries_version_metadata_into_result():
    rules = [{"rule_id": "X", "version": "2.1", "effective_from": "2024-01-01",
              "condition": {"op": "always"}}]
    engine = make_engine(rules)
    report = engine.evaluate(Evidence(), {})
    assert report.by_id("X").rule_version == "2.1"


def test_two_versions_of_same_regulation_can_coexist_as_distinct_rule_ids():
    """
    The engine has no built-in notion of 'pick the version active on date D'
    -- that selection is the ruleset LOADER's job (e.g. filtering by
    effective_from/effective_to before constructing the RuleSet). This test
    documents/locks that boundary: both versions can be loaded and evaluated
    side by side without the engine treating them specially.
    """
    rules = [
        {"rule_id": "R-v1", "version": "1", "effective_to": "2025-12-31",
         "condition": {"op": "eq", "field": "x", "value": 1}},
        {"rule_id": "R-v2", "version": "2", "effective_from": "2026-01-01", "supersedes": "R-v1",
         "condition": {"op": "eq", "field": "x", "value": 2}},
    ]
    engine = make_engine(rules)
    report = engine.evaluate(Evidence().set_field("x", 2), {})
    assert report.by_id("R-v1").status is ComplianceStatus.FAIL
    assert report.by_id("R-v2").status is ComplianceStatus.PASS


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def test_aggregation_is_not_a_naive_pass_fail_count():
    """One critical FAIL must dominate nine PASSes."""
    rules = [{"rule_id": f"ok{i}", "condition": {"op": "always"}} for i in range(9)]
    rules.append({"rule_id": "critical_fail", "severity": "critical", "condition": {"op": "never"}})
    engine = make_engine(rules)
    report = engine.evaluate(Evidence(), {})
    assert report.aggregation.overall_status is ComplianceStatus.FAIL
    assert "critical_fail" in report.aggregation.critical_failures


def test_aggregation_uncertain_blocks_pass_even_with_no_failures():
    rules = [
        {"rule_id": "ok", "condition": {"op": "always"}},
        {"rule_id": "unknown", "condition": {"op": "eq", "field": "never_set", "value": 1}},
    ]
    # A value-comparison operator against a field that was never supplied
    # returns UNKNOWN (insufficient evidence), which blocks an overall PASS.
    engine = make_engine(rules)
    report = engine.evaluate(Evidence(), {})
    assert report.aggregation.overall_status is ComplianceStatus.UNCERTAIN


def test_aggregation_engine_error_takes_precedence_over_everything():
    rules = [
        {"rule_id": "broken", "condition": {"op": "date_before", "field": "d", "value": "2026-01-01"}},
        {"rule_id": "fine", "condition": {"op": "always"}},
    ]
    engine = make_engine(rules)
    report = engine.evaluate(Evidence().set_field("d", "not-a-date"), {})
    assert report.aggregation.overall_status is ComplianceStatus.ENGINE_ERROR


def test_all_not_applicable_or_exempted_yields_not_applicable_overall():
    rules = [
        {"rule_id": "na", "applicability": {"op": "never"}, "condition": {"op": "always"}},
        {"rule_id": "ex", "exemptions": [{"id": "e", "condition": {"op": "always"}}],
         "condition": {"op": "always"}},
    ]
    engine = make_engine(rules)
    report = engine.evaluate(Evidence(), {})
    assert report.aggregation.overall_status is ComplianceStatus.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# Audit trail / evidence
# ---------------------------------------------------------------------------

def test_audit_trail_contains_full_pipeline_stages():
    rules = [{"rule_id": "X",
              "exemptions": [{"id": "e", "condition": {"op": "never"}}],
              "derived": [{"name": "total", "expr": {"op": "add",
                                                       "args": [{"field": "a"}, {"field": "b"}]}}],
              "condition": {"op": "gt", "field": "context.computed.total", "value": 0}}]
    engine = make_engine(rules)
    ev = Evidence().set_field("a", 1).set_field("b", 2)
    report = engine.evaluate(ev, {})
    stages = [s["stage"] for s in report.by_id("X").trace["stages"]]
    assert "rule_selected" in stages
    assert "applicability" in stages
    assert "exemption_check" in stages
    assert "calculation" in stages
    assert "condition_evaluation" in stages
    assert "evidence" in stages
    assert "rule_result" in stages


def test_evidence_citation_includes_provenance():
    rules = [{"rule_id": "X", "condition": {"op": "eq", "field": "mrp", "value": "50"}}]
    engine = make_engine(rules)
    ev = Evidence().set_field("mrp", "50", confidence=0.87, source_page="p1",
                              provenance="ocr:tesseract", source_text="MRP Rs.50/-")
    report = engine.evaluate(ev, {})
    result = report.by_id("X")
    assert result.status is ComplianceStatus.PASS
    citation = next(c for c in result.evidence if c.field == "mrp")
    assert citation.confidence == 0.87
    assert citation.source_page == "p1"
    assert citation.provenance == "ocr:tesseract"


def test_missing_evidence_is_named_explicitly():
    rules = [{"rule_id": "X", "condition": {"op": "and", "args": [
        {"op": "eq", "field": "a", "value": 1},
        {"op": "eq", "field": "b", "value": 2},
    ]}}]
    engine = make_engine(rules)
    report = engine.evaluate(Evidence().set_field("a", 1), {})  # b missing
    result = report.by_id("X")
    assert result.status is ComplianceStatus.UNCERTAIN
    assert "b" in result.missing_evidence


def test_explanation_never_claims_a_check_that_did_not_run():
    """Rule scoped out by applies_to must not mention condition-level checks."""
    rules = [{"rule_id": "X", "applies_to": {"category": ["food"]},
              "condition": {"op": "exists", "field": "allergen_list"}}]
    engine = make_engine(rules)
    report = engine.evaluate(Evidence(), {"category": "electronics"})
    result = report.by_id("X")
    assert result.applicability is ApplicabilityStatus.NOT_APPLICABLE
    assert "allergen_list" not in result.explanation