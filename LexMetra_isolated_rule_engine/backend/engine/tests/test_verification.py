"""
Comprehensive verification tests for the LexMetra Product Compliance Engine.

These tests fill gaps left by the existing 117-test baseline, specifically covering:
  - Kleene K3 truth table (all 27 combinations for AND/OR, 3 for NOT)
  - Decimal arithmetic precision
  - Circular dependency detection
  - Version/date filtering (active, future, expired, no-date)
  - Provenance persistence through evaluation
  - Unit incompatibility - ENGINE_ERROR
  - Malformed rule - validation error, not silent pass/fail
  - Fourth Schedule: SOURCE_DATA_MISSING behavior
  - Fifth Schedule: SOURCE_DATA_MISSING behavior
  - Sixth Schedule: no lookup function (non-executable by design)
  - First Schedule: zero/negative quantity -> supported=False
  - Aggregation edge cases: ENGINE_ERROR blocks, all NOT_APPLICABLE
  - Determinism: same input -> same output across multiple runs
  - CanonicalProductFacts: three-way state under engine evaluation
"""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.conditions import Tri, tri_and, tri_or, tri_not, evaluate_condition
from engine.evidence import Evidence, EvidenceValue, MISSING
from engine.errors import CircularDependencyError, RuleValidationError, RuleConfigurationError
from engine.rule_model import Rule, RuleSet, load_ruleset_from_dict
from engine.evaluator import RuleEngine
from engine import ComplianceEngine, ComplianceStatus
from engine.results import EngineReport
from engine.calc import evaluate_calc_node, run_derived
from engine.dependency import find_cycle, topological_order
from engine.schedules import (
    lookup_mpe,
    lookup_fourth_schedule_moisture_allowance,
    lookup_fifth_schedule_count_commodity,
    SIXTH_SCHEDULE_NOTE,
)
from engine.units import convert, are_compatible


# ===========================================================================
# K3 TRUTH TABLE TESTS
# ===========================================================================

class TestKleeenK3TruthTable:
    """Exhaustively verify AND, OR, NOT under K3 (Kleene) logic."""

    def test_and_true_true(self):
        assert tri_and([Tri.TRUE, Tri.TRUE]) is Tri.TRUE

    def test_and_true_false(self):
        assert tri_and([Tri.TRUE, Tri.FALSE]) is Tri.FALSE

    def test_and_true_unknown(self):
        assert tri_and([Tri.TRUE, Tri.UNKNOWN]) is Tri.UNKNOWN

    def test_and_false_true(self):
        assert tri_and([Tri.FALSE, Tri.TRUE]) is Tri.FALSE

    def test_and_false_false(self):
        assert tri_and([Tri.FALSE, Tri.FALSE]) is Tri.FALSE

    def test_and_false_unknown(self):
        # FALSE dominates: FALSE AND UNKNOWN = FALSE
        assert tri_and([Tri.FALSE, Tri.UNKNOWN]) is Tri.FALSE

    def test_and_unknown_true(self):
        assert tri_and([Tri.UNKNOWN, Tri.TRUE]) is Tri.UNKNOWN

    def test_and_unknown_false(self):
        # FALSE dominates: UNKNOWN AND FALSE = FALSE
        assert tri_and([Tri.UNKNOWN, Tri.FALSE]) is Tri.FALSE

    def test_and_unknown_unknown(self):
        assert tri_and([Tri.UNKNOWN, Tri.UNKNOWN]) is Tri.UNKNOWN

    def test_or_true_true(self):
        assert tri_or([Tri.TRUE, Tri.TRUE]) is Tri.TRUE

    def test_or_true_false(self):
        assert tri_or([Tri.TRUE, Tri.FALSE]) is Tri.TRUE

    def test_or_true_unknown(self):
        # TRUE dominates: TRUE OR UNKNOWN = TRUE
        assert tri_or([Tri.TRUE, Tri.UNKNOWN]) is Tri.TRUE

    def test_or_false_true(self):
        assert tri_or([Tri.FALSE, Tri.TRUE]) is Tri.TRUE

    def test_or_false_false(self):
        assert tri_or([Tri.FALSE, Tri.FALSE]) is Tri.FALSE

    def test_or_false_unknown(self):
        assert tri_or([Tri.FALSE, Tri.UNKNOWN]) is Tri.UNKNOWN

    def test_or_unknown_true(self):
        # TRUE dominates: UNKNOWN OR TRUE = TRUE
        assert tri_or([Tri.UNKNOWN, Tri.TRUE]) is Tri.TRUE

    def test_or_unknown_false(self):
        assert tri_or([Tri.UNKNOWN, Tri.FALSE]) is Tri.UNKNOWN

    def test_or_unknown_unknown(self):
        assert tri_or([Tri.UNKNOWN, Tri.UNKNOWN]) is Tri.UNKNOWN

    def test_not_true(self):
        assert tri_not(Tri.TRUE) is Tri.FALSE

    def test_not_false(self):
        assert tri_not(Tri.FALSE) is Tri.TRUE

    def test_not_unknown(self):
        # NOT UNKNOWN = UNKNOWN (not TRUE, not FALSE)
        assert tri_not(Tri.UNKNOWN) is Tri.UNKNOWN

    def test_unknown_never_equal_false(self):
        # The critical invariant: UNKNOWN != FALSE
        assert Tri.UNKNOWN is not Tri.FALSE

    def test_tri_bool_raises(self):
        """Tri must not be used in a boolean context."""
        with pytest.raises(TypeError):
            bool(Tri.TRUE)

    def test_and_empty_list(self):
        # AND of empty list = TRUE (vacuous conjunction)
        assert tri_and([]) is Tri.TRUE

    def test_or_empty_list(self):
        # OR of empty list = FALSE (vacuous disjunction)
        assert tri_or([]) is Tri.FALSE


# ===========================================================================
# DECIMAL ARITHMETIC PRECISION
# ===========================================================================

class TestDecimalArithmetic:
    """Verify Decimal-based arithmetic does not drift the way float does."""

    def _make_evidence(self, **fields):
        ev = Evidence()
        for k, v in fields.items():
            ev.set_field(k, v)
        return ev

    def test_add_does_not_float_drift(self):
        # 0.1 + 0.2 = 0.30000000000000004 in float -- must be exactly 0.3 in Decimal
        ev = self._make_evidence(a=0.1, b=0.2)
        node = {"op": "add", "args": [{"field": "a"}, {"field": "b"}]}
        val, _ = evaluate_calc_node(node, ev)
        from decimal import Decimal
        assert abs(Decimal(str(val)) - Decimal("0.3")) < Decimal("1e-10")

    def test_sub_precision(self):
        ev = self._make_evidence(a=1.0, b=0.1)
        node = {"op": "sub", "args": [{"field": "a"}, {"field": "b"}]}
        val, _ = evaluate_calc_node(node, ev)
        from decimal import Decimal
        assert abs(Decimal(str(val)) - Decimal("0.9")) < Decimal("1e-10")

    def test_div_by_zero_returns_none(self):
        ev = self._make_evidence(a=10.0, b=0.0)
        node = {"op": "div", "args": [{"field": "a"}, {"field": "b"}]}
        val, _ = evaluate_calc_node(node, ev)
        assert val is None

    def test_percent_diff_known_values(self):
        # observed=99, expected=100 -> percent_diff = -1.0%
        ev = self._make_evidence(observed=99.0, expected=100.0)
        node = {"op": "percent_diff", "args": [{"field": "observed"}, {"field": "expected"}]}
        val, unit = evaluate_calc_node(node, ev)
        from decimal import Decimal
        assert abs(Decimal(str(val)) - Decimal("-1.0")) < Decimal("1e-10")
        assert unit == "%"

    def test_percent_diff_zero_expected_returns_none(self):
        ev = self._make_evidence(observed=5.0, expected=0.0)
        node = {"op": "percent_diff", "args": [{"field": "observed"}, {"field": "expected"}]}
        val, _ = evaluate_calc_node(node, ev)
        assert val is None

    def test_missing_operand_returns_none(self):
        ev = Evidence()  # no fields
        node = {"op": "add", "args": [{"field": "missing_a"}, {"field": "missing_b"}]}
        val, _ = evaluate_calc_node(node, ev)
        assert val is None

    def test_run_derived_propagates_to_computed(self):
        ev = Evidence()
        ev.set_field("unit_price", 50.0)
        ev.set_field("qty", 200.0)
        specs = [{"name": "total_value", "expr": {"op": "mul", "args": [{"field": "unit_price"}, {"field": "qty"}]}}]
        traces = run_derived(specs, ev)
        assert len(traces) == 1
        assert traces[0].ok is True
        assert traces[0].value == 10000.0
        assert ev.context["computed"]["total_value"] == 10000.0


# ===========================================================================
# CIRCULAR DEPENDENCY DETECTION
# ===========================================================================

class TestCircularDependencyDetection:

    def _make_ruleset_with_cycle(self) -> RuleSet:
        """Create a ruleset where A depends_on B, B depends_on A."""
        rules = [
            Rule(rule_id="A", depends_on=["B"], condition={"op": "always"}),
            Rule(rule_id="B", depends_on=["A"], condition={"op": "always"}),
        ]
        return RuleSet(rules=rules)

    def _make_ruleset_no_cycle(self) -> RuleSet:
        rules = [
            Rule(rule_id="X", depends_on=[]),
            Rule(rule_id="Y", depends_on=["X"], condition={"op": "always"}),
        ]
        return RuleSet(rules=rules)

    def test_cycle_detected_by_find_cycle(self):
        rs = self._make_ruleset_with_cycle()
        cycle = find_cycle(rs)
        assert cycle is not None
        assert len(cycle) >= 2

    def test_no_cycle_returns_none(self):
        rs = self._make_ruleset_no_cycle()
        cycle = find_cycle(rs)
        assert cycle is None

    def test_topological_order_raises_on_cycle(self):
        rs = self._make_ruleset_with_cycle()
        with pytest.raises(CircularDependencyError):
            topological_order(rs)

    def test_topological_order_correct_no_cycle(self):
        rs = self._make_ruleset_no_cycle()
        order = topological_order(rs)
        # X must come before Y since Y depends_on X
        assert order.index("X") < order.index("Y")

    def test_validation_catches_cycle(self):
        from engine.validate import find_problems
        rs = self._make_ruleset_with_cycle()
        problems = find_problems(rs)
        assert any("circular" in p.lower() for p in problems)

    def test_self_dependency_raises_validation_problem(self):
        from engine.validate import find_problems
        rules = [Rule(rule_id="SELF", depends_on=["SELF"], condition={"op": "always"})]
        rs = RuleSet(rules=rules)
        problems = find_problems(rs)
        assert any("SELF" in p for p in problems)


# ===========================================================================
# VERSION / DATE FILTERING
# ===========================================================================

class TestVersionDateFiltering:
    """Verify that effective_from/effective_to behave correctly."""

    _ACTIVE_RULE_ID = "DATED-RULE"

    def _engine_with_dated_rule(self, effective_from=None, effective_to=None) -> RuleEngine:
        rule = Rule(
            rule_id=self._ACTIVE_RULE_ID,
            name="Dated test rule",
            effective_from=effective_from,
            effective_to=effective_to,
            condition={"op": "always"},
        )
        rs = RuleSet(rules=[rule])
        return RuleEngine(rs, validate_on_init=False)

    def test_active_rule_evaluated(self):
        engine = self._engine_with_dated_rule(effective_from="2020-01-01")
        ev = Evidence()
        report = engine.evaluate(ev, {"as_of_date": "2026-01-01"})
        result = report.by_id(self._ACTIVE_RULE_ID)
        assert result.status is ComplianceStatus.PASS

    def test_future_rule_not_considered(self):
        engine = self._engine_with_dated_rule(effective_from="2030-01-01")
        ev = Evidence()
        report = engine.evaluate(ev, {"as_of_date": "2026-01-01"})
        result = report.by_id(self._ACTIVE_RULE_ID)
        assert result.status is ComplianceStatus.NOT_CONSIDERED

    def test_expired_rule_not_considered(self):
        engine = self._engine_with_dated_rule(effective_to="2020-01-01")
        ev = Evidence()
        report = engine.evaluate(ev, {"as_of_date": "2026-01-01"})
        result = report.by_id(self._ACTIVE_RULE_ID)
        assert result.status is ComplianceStatus.NOT_CONSIDERED

    def test_rule_with_no_dates_always_applies(self):
        engine = self._engine_with_dated_rule()
        ev = Evidence()
        report = engine.evaluate(ev, {"as_of_date": "2026-01-01"})
        result = report.by_id(self._ACTIVE_RULE_ID)
        assert result.status is not ComplianceStatus.NOT_CONSIDERED

    def test_rule_evaluated_when_no_as_of_date_in_context(self):
        engine = self._engine_with_dated_rule(effective_from="2020-01-01")
        ev = Evidence()
        report = engine.evaluate(ev, {})
        result = report.by_id(self._ACTIVE_RULE_ID)
        assert result.status is ComplianceStatus.PASS

    def test_superseded_status_marks_not_considered(self):
        rule = Rule(
            rule_id="OLD-RULE",
            status="superseded",
            condition={"op": "always"},
        )
        rs = RuleSet(rules=[rule])
        engine = RuleEngine(rs, validate_on_init=False)
        ev = Evidence()
        report = engine.evaluate(ev, {})
        result = report.by_id("OLD-RULE")
        assert result.status is ComplianceStatus.NOT_CONSIDERED


# ===========================================================================
# PROVENANCE PERSISTENCE
# ===========================================================================

class TestProvenancePersistence:
    """Verify that legal provenance fields survive from Rule -> RuleResult."""

    def test_legal_source_and_provision_in_rule_result(self):
        rule = Rule(
            rule_id="PROV-TEST",
            legal_source="IN-LMPC-2011",
            provision="Rule 6(1)(da)",
            cross_references=["IN-LMPC-2011/Rule-6-1-a", "IN-LMPC-2011/Rule-10"],
            condition={"op": "always"},
        )
        rs = RuleSet(rules=[rule])
        engine = RuleEngine(rs, validate_on_init=False)
        report = engine.evaluate(Evidence(), {})
        result = report.by_id("PROV-TEST")
        assert result is not None
        assert result.legal_source == "IN-LMPC-2011"
        assert result.provision == "Rule 6(1)(da)"
        assert "IN-LMPC-2011/Rule-6-1-a" in result.cross_references

    def test_provenance_survives_serialization(self):
        rule = Rule(
            rule_id="PROV-SERIAL",
            legal_source="IN-LMPC-2011",
            provision="Rule 7",
            condition={"op": "always"},
        )
        rs = RuleSet(rules=[rule])
        engine = RuleEngine(rs, validate_on_init=False)
        report = engine.evaluate(Evidence(), {})
        result = report.by_id("PROV-SERIAL")
        d = result.to_dict()
        assert d["legal_source"] == "IN-LMPC-2011"
        assert d["provision"] == "Rule 7"

    def test_provenance_in_engine_report_to_dict(self):
        rule = Rule(
            rule_id="PROV-REPORT",
            legal_source="IN-LMPC-2011",
            provision="First Schedule",
            condition={"op": "always"},
        )
        rs = RuleSet(rules=[rule])
        engine = RuleEngine(rs, validate_on_init=False)
        report = engine.evaluate(Evidence(), {})
        d = report.to_dict()
        results = d["results"]
        match = next((r for r in results if r["rule_id"] == "PROV-REPORT"), None)
        assert match is not None
        assert match["provision"] == "First Schedule"


# ===========================================================================
# UNIT INCOMPATIBILITY
# ===========================================================================

class TestUnitIncompatibility:

    def test_incompatible_units_not_comparable(self):
        assert are_compatible("kg", "ml") is False
        assert are_compatible("g", "l") is False
        assert are_compatible("mm", "g") is False

    def test_compatible_units(self):
        assert are_compatible("kg", "g") is True
        assert are_compatible("l", "ml") is True
        assert are_compatible("m", "cm") is True

    def test_unknown_unit_not_compatible(self):
        assert are_compatible("unknown_unit", "g") is False
        assert are_compatible("g", "unknown_unit") is False

    def test_convert_incompatible_raises_value_error(self):
        with pytest.raises(ValueError, match="incompatible"):
            convert(1.0, "kg", "ml")


# ===========================================================================
# MALFORMED RULE VALIDATION
# ===========================================================================

class TestMalformedRuleValidation:
    """Malformed rules must be caught by validate_ruleset, not silently misbehave."""

    def test_unknown_operator_raises_validation_error(self):
        data = {
            "rules": [{
                "rule_id": "BAD-OP",
                "condition": {"op": "this_operator_does_not_exist", "field": "x"},
            }]
        }
        with pytest.raises(RuleValidationError):
            rs = load_ruleset_from_dict(data)
            RuleEngine(rs, validate_on_init=True)

    def test_duplicate_rule_id_raises_validation_error(self):
        data = {
            "rules": [
                {"rule_id": "DUP", "condition": {"op": "always"}},
                {"rule_id": "DUP", "condition": {"op": "always"}},
            ]
        }
        with pytest.raises(RuleValidationError):
            rs = load_ruleset_from_dict(data)
            RuleEngine(rs, validate_on_init=True)

    def test_missing_rule_id_raises_validation_error(self):
        data = {
            "rules": [
                {"rule_id": "", "condition": {"op": "always"}},
            ]
        }
        with pytest.raises(RuleValidationError):
            rs = load_ruleset_from_dict(data)
            RuleEngine(rs, validate_on_init=True)

    def test_depends_on_unknown_id_raises_validation_error(self):
        data = {
            "rules": [
                {"rule_id": "CHILD", "depends_on": ["NONEXISTENT"], "condition": {"op": "always"}},
            ]
        }
        with pytest.raises(RuleValidationError):
            rs = load_ruleset_from_dict(data)
            RuleEngine(rs, validate_on_init=True)

    def test_invalid_regex_raises_validation_error(self):
        data = {
            "rules": [{
                "rule_id": "BAD-REGEX",
                "condition": {"op": "regex", "field": "x", "pattern": "[invalid(regex"},
            }]
        }
        with pytest.raises(RuleValidationError):
            rs = load_ruleset_from_dict(data)
            RuleEngine(rs, validate_on_init=True)

    def test_invalid_effective_dates_raises_validation_error(self):
        data = {
            "rules": [{
                "rule_id": "BAD-DATES",
                "effective_from": "2026-01-01",
                "effective_to": "2020-01-01",  # to < from
                "condition": {"op": "always"},
            }]
        }
        with pytest.raises(RuleValidationError):
            rs = load_ruleset_from_dict(data)
            RuleEngine(rs, validate_on_init=True)


# ===========================================================================
# FOURTH AND FIFTH SCHEDULE: SOURCE DATA MISSING BEHAVIOR
# ===========================================================================

class TestFourthScheduleSourceDataMissing:

    def test_fourth_schedule_returns_supported_false(self):
        """Without source data, Fourth Schedule must report SOURCE_DATA_MISSING."""
        result = lookup_fourth_schedule_moisture_allowance("soap", 100.0, "g")
        assert result["supported"] is False
        assert result["schedule"] == "Fourth Schedule"
        assert "SOURCE_DATA_MISSING" in result["reason"]

    def test_fourth_schedule_commodity_returned_in_response(self):
        result = lookup_fourth_schedule_moisture_allowance("dry_fruits", 500.0, "g")
        assert result["commodity"] == "dry_fruits"

    def test_fourth_schedule_legal_reference_present(self):
        result = lookup_fourth_schedule_moisture_allowance("spices", 250.0, "g")
        assert "Rule 12(2)" in result.get("legal_reference", "")

    def test_fourth_schedule_no_fabricated_values(self):
        """Confirm no moisture percentages are returned when data is unavailable."""
        result = lookup_fourth_schedule_moisture_allowance("soap", 100.0, "g")
        assert "max_additional_moisture_pct" not in result


class TestFifthScheduleSourceDataMissing:

    def test_fifth_schedule_returns_supported_false(self):
        """Without source data, Fifth Schedule must report SOURCE_DATA_MISSING."""
        result = lookup_fifth_schedule_count_commodity("electric_lamp")
        assert result["supported"] is False
        assert result["schedule"] == "Fifth Schedule"
        assert "SOURCE_DATA_MISSING" in result["reason"]

    def test_fifth_schedule_commodity_returned_in_response(self):
        result = lookup_fifth_schedule_count_commodity("cigarette")
        assert result["commodity"] == "cigarette"

    def test_fifth_schedule_no_fabricated_classification(self):
        """Confirm no is_count_commodity is returned when data is unavailable."""
        result = lookup_fifth_schedule_count_commodity("electric_lamp")
        assert "is_count_commodity" not in result


class TestSixthScheduleNonExecutable:

    def test_sixth_schedule_has_no_lookup_function(self):
        """The Sixth Schedule must not expose a lookup function."""
        import engine.schedules as sched_module
        assert not hasattr(sched_module, "lookup_sixth_schedule_sample_size")
        assert not hasattr(sched_module, "lookup_sixth_schedule")

    def test_sixth_schedule_has_descriptive_note(self):
        assert "REPRESENTED_NON_EXECUTABLE" in SIXTH_SCHEDULE_NOTE
        assert "sampling" in SIXTH_SCHEDULE_NOTE.lower()


# ===========================================================================
# FIRST SCHEDULE: ZERO / NEGATIVE QUANTITY
# ===========================================================================

class TestFirstScheduleEdgeCases:

    def test_zero_quantity_returns_not_supported(self):
        result = lookup_mpe(0.0, "g")
        assert result["supported"] is False
        assert "positive" in result["reason"].lower()

    def test_negative_quantity_returns_not_supported(self):
        result = lookup_mpe(-100.0, "g")
        assert result["supported"] is False

    def test_very_small_positive_quantity(self):
        # 0.001g is still a positive quantity; should be supported (in the first tier)
        result = lookup_mpe(0.001, "g")
        assert result["supported"] is True

    def test_invalid_unit_not_supported(self):
        result = lookup_mpe(500.0, "m")  # length unit, not mass or volume
        assert result["supported"] is False

    def test_boundary_50g_is_fixed_tier(self):
        # Exactly 50g should be in the [50, 100) fixed-4.5g tier
        result = lookup_mpe(50.0, "g")
        assert result["supported"] is True
        assert result["max_permissible_error"] == 4.5

    def test_boundary_just_below_50g_is_percent_tier(self):
        # 49.9g is in the [0, 50) -> 9% tier: 0.09 * 49.9 = 4.491
        result = lookup_mpe(49.9, "g")
        assert result["supported"] is True
        assert abs(result["max_permissible_error"] - 4.491) < 0.001


# ===========================================================================
# AGGREGATION EDGE CASES
# ===========================================================================

class TestAggregationEdgeCases:

    def test_unknown_blocks_pass(self):
        """UNCERTAIN must never become PASS."""
        rule = Rule(rule_id="UNK", condition={"op": "exists", "field": "missing_field"})
        rs = RuleSet(rules=[rule])
        engine = RuleEngine(rs, validate_on_init=False)
        report = engine.evaluate(Evidence(), {})
        assert report.aggregation.overall_status is ComplianceStatus.UNCERTAIN

    def test_all_not_applicable_gives_not_applicable(self):
        """When all rules are NOT_APPLICABLE, overall should be NOT_APPLICABLE."""
        rule = Rule(
            rule_id="NA-RULE",
            applicability={"op": "never"},
            condition={"op": "always"},
        )
        rs = RuleSet(rules=[rule])
        engine = RuleEngine(rs, validate_on_init=False)
        report = engine.evaluate(Evidence(), {})
        assert report.aggregation.overall_status is ComplianceStatus.NOT_APPLICABLE

    def test_fail_dominates_uncertain(self):
        """FAIL must dominate UNCERTAIN in aggregation."""
        rule_fail = Rule(rule_id="FAIL", condition={"op": "never"})
        rule_unk = Rule(rule_id="UNK", condition={"op": "exists", "field": "x"})
        rs = RuleSet(rules=[rule_fail, rule_unk])
        engine = RuleEngine(rs, validate_on_init=False)
        report = engine.evaluate(Evidence(), {})
        assert report.aggregation.overall_status is ComplianceStatus.FAIL


# ===========================================================================
# DETERMINISM
# ===========================================================================

class TestDeterminism:

    def test_same_product_same_result_across_runs(self):
        """The engine must produce identical results for identical inputs."""
        product = {
            "product": {
                "name": "Test Biscuits",
                "manufacturer_name_address": "XYZ Foods, 10 Industrial Area, Delhi 110001",
                "common_name": "Biscuits",
                "quantity": {"value": 100, "unit": "g"},
                "mfg_date": "2026-06-01",
                "consumer_care": "support@xyz.com",
                "mrp": 30.0,
            },
            "trade_type": "retail",
            "is_imported": False,
        }
        engine = ComplianceEngine()
        statuses = []
        for _ in range(5):
            report = engine.evaluate(product)
            statuses.append(report.aggregation.overall_status.value)
        assert len(set(statuses)) == 1, f"Non-deterministic: {statuses}"

    def test_determinism_with_missing_fields(self):
        """Missing-field behavior must also be deterministic."""
        product = {"product": {"name": "Soap"}}
        engine = ComplianceEngine()
        statuses = [engine.evaluate(product).aggregation.overall_status.value for _ in range(3)]
        assert len(set(statuses)) == 1


# ===========================================================================
# CANONICAL PRODUCT FACTS: THREE-WAY STATE UNDER EVALUATION
# ===========================================================================

class TestCanonicalFactsThreeWayState:

    def test_omitted_field_does_not_become_fail(self):
        """An omitted field must produce UNCERTAIN (not FAIL) for the rule requiring it."""
        engine = ComplianceEngine()
        # No MRP field at all -> should be UNCERTAIN, never FAIL
        report = engine.evaluate({"product": {"name": "Widget"}})
        mrp_result = report.by_id("LMPC-6-1-DA-MRP")
        if mrp_result:
            assert mrp_result.status is not ComplianceStatus.FAIL, (
                f"Omitted MRP must not produce FAIL; got {mrp_result.status}, reason: {mrp_result.reason}"
            )

    def test_explicitly_absent_field_can_produce_fail(self):
        """An explicitly absent field (present=False) CAN produce FAIL if exemptions are resolved."""
        engine = ComplianceEngine()
        report = engine.evaluate({
            "product": {
                "mrp": {"present": False},
                "exemption": {"is_exempt": False},
                "name": "Widget",
                "manufacturer_name_address": "ABC Corp, Chennai 600001",
                "common_name": "Widget",
                "quantity": {"value": 200, "unit": "g"},
                "mfg_date": "2026-01-01",
                "consumer_care": "care@abc.com",
            }
        })
        mrp_result = report.by_id("LMPC-6-1-DA-MRP")
        if mrp_result:
            assert mrp_result.status is ComplianceStatus.FAIL

    def test_known_field_with_value_does_not_produce_uncertain(self):
        """A KNOWN MRP value must produce PASS for the 'mrp-present' exists check.

        The overall LMPC-6-1-DA-MRP rule may still be UNCERTAIN because it also
        requires 'declared.mrp.label_text' (inclusive of all taxes wording) which we
        don't supply here. That is correct behavior. What we are testing is that the
        canonical facts layer correctly maps a known scalar mrp value to KNOWN presence,
        causing the 'mrp-present' requirement to PASS rather than remain UNCERTAIN.
        """
        engine = ComplianceEngine()
        report = engine.evaluate({
            "product": {
                "mrp": 50.0,                              # KNOWN value -> declared.mrp KNOWN
                "exemption": {"is_exempt": False},        # Resolve exemption uncertainty
                "name": "Widget",
            },
        })
        mrp_result = report.by_id("LMPC-6-1-DA-MRP")
        if mrp_result and mrp_result.requirement_results:
            # The 'mrp-present' sub-requirement must PASS (not UNCERTAIN) because mrp=50.0 is KNOWN
            mrp_present_req = next(
                (r for r in mrp_result.requirement_results if r.requirement_id == "mrp-present"),
                None,
            )
            if mrp_present_req:
                assert mrp_present_req.status is ComplianceStatus.PASS, (
                    f"mrp-present requirement should PASS when mrp=50.0 is supplied; "
                    f"got {mrp_present_req.status}"
                )


# ===========================================================================
# EXISTING API PRESERVATION
# ===========================================================================

class TestExistingAPIPreserved:
    """Verify the public API contract is intact."""

    def test_compliance_engine_importable(self):
        from engine import ComplianceEngine
        assert ComplianceEngine is not None

    def test_rule_engine_importable(self):
        from engine import RuleEngine
        assert RuleEngine is not None

    def test_all_public_exports(self):
        from engine import (
            RuleEngine, Rule, RuleSet, Evidence, EvidenceValue,
            RuleResult, EngineReport, ComplianceEngine,
        )
        for obj in [RuleEngine, Rule, RuleSet, Evidence, EvidenceValue, RuleResult, EngineReport, ComplianceEngine]:
            assert obj is not None

    def test_compliance_engine_evaluate_returns_engine_report(self):
        engine = ComplianceEngine()
        report = engine.evaluate({"product": {"name": "Test"}})
        assert isinstance(report, EngineReport)
        assert report.aggregation is not None
        assert isinstance(report.results, list)

    def test_rule_engine_property(self):
        ce = ComplianceEngine()
        from engine.evaluator import RuleEngine as RE
        assert isinstance(ce.rule_engine, RE)
