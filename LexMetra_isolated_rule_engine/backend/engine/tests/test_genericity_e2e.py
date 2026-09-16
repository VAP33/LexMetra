"""
Proves the "no module bias" requirement empirically: the SAME RuleEngine
class, with NO code changes, correctly evaluates two structurally unrelated
rule-data files -- one real regulation (Indian Legal Metrology packaged
commodities) and one illustrative, unrelated regulation (food allergen
labeling) -- against different evidence shapes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2]),
)

from engine import (
    Evidence,
    RuleEngine,
    load_ruleset,
)

from engine.results import (
    ApplicabilityStatus,
    ComplianceStatus,
)


RULES_DIR = (
    Path(__file__).resolve().parents[3]
    / "rules"
    / "generic"
)


def _lmpc_engine():
    return RuleEngine(
        load_ruleset(
            RULES_DIR / "lmpc_rules.json"
        )
    )


def _food_engine():
    return RuleEngine(
        load_ruleset(
            RULES_DIR
            / "example_food_labeling_rules.json"
        )
    )


# ---------------------------------------------------------------------------
# LMPC
# ---------------------------------------------------------------------------

def _lmpc_baseline_evidence() -> Evidence:
    ev = Evidence()

    ev.set_field(
        "declared.manufacturer_name_address",
        "Acme Foods Pvt Ltd, Pune, India",
        confidence=0.95,
    )

    ev.set_field(
        "declared.common_name",
        "Refined Sunflower Oil",
        confidence=0.95,
    )

    ev.set_field(
        "declared.net_quantity",
        1.0,
        unit="l",
        confidence=0.9,
    )

    ev.set_field(
        "declared.net_quantity.unit",
        "l",
        confidence=0.9,
    )

    ev.set_field(
        "declared.mfg_date",
        "2026-02-01",
        confidence=0.9,
    )

    ev.set_field(
        "declared.mrp",
        180.0,
        confidence=0.9,
    )

    ev.set_field(
        "declared.mrp.label_text",
        "MRP Rs.180/- (Inclusive of all taxes)",
        confidence=0.9,
    )

    ev.set_field(
        "declared.consumer_care",
        "1800-000-000",
        confidence=0.9,
    )

    ev.set_context(
        "exemption.is_exempt",
        False,
    )

    ev.set_context(
        "category_requires_best_before",
        True,
    )

    ev.set_context(
        "is_imported",
        False,
    )

    ev.set_context(
        "commodity_has_standard_pack_schedule",
        False,
    )

    return ev


def test_lmpc_full_pass_when_all_mandatory_declarations_present():
    ev = _lmpc_baseline_evidence()

    ev.set_field(
        "declared.best_before_use_by",
        "2026-08-01",
        confidence=0.9,
    )

    report = _lmpc_engine().evaluate(
        ev,
        {},
    )

    mandatory = [
        "LMPC-6-1-A-MANUFACTURER",
        "LMPC-6-1-B-COMMON-NAME",
        "LMPC-6-1-E-NET-QUANTITY",
        "LMPC-6-1-D-MFG-DATE",
        "LMPC-6-1-D-BEST-BEFORE",
        "LMPC-6-1-DA-MRP",
        "LMPC-6-1-DA-F-CONSUMER-CARE",
    ]

    for rid in mandatory:
        result = report.by_id(rid)

        assert result.status is ComplianceStatus.PASS, (
            f"{rid}: {result.status} -- "
            f"{result.reason}"
        )


def test_lmpc_missing_mrp_fails_and_dominates_aggregation():
    """
    When the upstream extraction system has examined the label and explicitly
    confirmed that MRP is absent (present=False), the exists() check must
    return FALSE → the requirement FAILs deterministically.

    A field that was simply never looked up (no EvidenceValue at all) would
    yield UNKNOWN, not FAIL — that is the correct invariant: missing evidence
    is not a violation, but evidence of absence is.
    """
    ev = _lmpc_baseline_evidence()

    # Replace the baseline MRP fields with explicit "confirmed absent" markers.
    # This is the correct way to signal "upstream searched the label and found
    # no MRP declaration", which is a deterministic FAIL for exists().
    ev.set_field(
        "declared.mrp",
        None,
        present=False,
    )

    ev.set_field(
        "declared.mrp.label_text",
        None,
        present=False,
    )

    ev.set_field(
        "declared.best_before_use_by",
        "2026-08-01",
    )

    report = _lmpc_engine().evaluate(
        ev,
        {},
    )

    assert (
        report.by_id(
            "LMPC-6-1-DA-MRP"
        ).status
        is ComplianceStatus.FAIL
    )

    assert (
        report.aggregation.overall_status
        is ComplianceStatus.FAIL
    )

    assert (
        "LMPC-6-1-DA-MRP"
        in report.aggregation.critical_failures
    )


def test_lmpc_small_pack_exemption_exempts_all_declaration_rules():
    """
    The small-pack exemption must exempt the declaration rules.

    The overall report may still be UNCERTAIN because this ruleset also
    contains unrelated rules whose applicability cannot be determined from
    the supplied context. That is intentional conservative behavior.

    This test therefore verifies:
      1. declaration rules are EXEMPTED;
      2. unrelated unresolved applicability is not silently treated as N/A.
    """

    ev = Evidence()

    # No declarations deliberately supplied.
    ev.set_context(
        "exemption.is_exempt",
        True,
    )

    ev.set_context(
        "category_requires_best_before",
        False,
    )

    ev.set_context(
        "is_imported",
        False,
    )

    ev.set_context(
        "commodity_has_standard_pack_schedule",
        False,
    )

    report = _lmpc_engine().evaluate(
        ev,
        {},
    )

    declaration_rule_ids = [
        "LMPC-6-1-A-MANUFACTURER",
        "LMPC-6-1-DA-MRP",
        "LMPC-6-1-E-NET-QUANTITY",
    ]

    for rid in declaration_rule_ids:
        result = report.by_id(rid)

        assert result.status is ComplianceStatus.EXEMPTED, (
            f"{rid}: {result.status}"
        )

        assert (
            result.applicability
            is ApplicabilityStatus.EXEMPTED
        )

    # These rules cannot determine applicability from the supplied evidence.
    # The conservative aggregation policy therefore correctly produces
    # UNCERTAIN rather than pretending that the entire ruleset is N/A.
    unresolved_rules = [
        "LMPC-4-MULTIPACK",
        "LMPC-25-EXPORT",
        "LMPC-26-B-FAST-FOOD",
        "LMPC-26-C-DRUG-FORMULATIONS",
        "LMPC-27-REGISTRATION",
        "LMPC-31-ADVERTISEMENT",
    ]

    for rid in unresolved_rules:
        result = report.by_id(rid)

        assert result.status is ComplianceStatus.UNCERTAIN, (
            f"{rid}: expected UNCERTAIN, got {result.status}"
        )

        assert (
            result.applicability
            is ApplicabilityStatus.UNCERTAIN
        )

    assert (
        report.aggregation.overall_status
        is ComplianceStatus.UNCERTAIN
    )


def test_lmpc_country_of_origin_not_applicable_for_domestic_product():
    ev = _lmpc_baseline_evidence()

    ev.set_field(
        "declared.best_before_use_by",
        "2026-08-01",
    )

    report = _lmpc_engine().evaluate(
        ev,
        {},
    )

    result = report.by_id(
        "LMPC-6-1-A-COUNTRY-OF-ORIGIN"
    )

    assert (
        result.applicability
        is ApplicabilityStatus.NOT_APPLICABLE
    )


def test_lmpc_country_of_origin_required_and_failing_when_imported_and_missing():
    """
    For an imported product the country-of-origin rule is applicable.
    When the upstream extraction system has examined the label and explicitly
    confirmed that country-of-origin is absent (present=False), the exists()
    check returns FALSE → FAIL.

    A field that was simply never looked up (no EvidenceValue at all) would
    yield UNKNOWN, preserving the invariant: missing evidence ≠ violation.
    """
    ev = _lmpc_baseline_evidence()

    ev.set_field(
        "declared.best_before_use_by",
        "2026-08-01",
    )

    ev.set_context(
        "is_imported",
        True,
    )

    # Upstream confirmed country-of-origin is absent from the label.
    ev.set_field(
        "declared.country_of_origin",
        None,
        present=False,
    )

    report = _lmpc_engine().evaluate(
        ev,
        {},
    )

    result = report.by_id(
        "LMPC-6-1-A-COUNTRY-OF-ORIGIN"
    )

    assert (
        result.applicability
        is ApplicabilityStatus.APPLICABLE
    )

    assert (
        result.status
        is ComplianceStatus.FAIL
    )


def test_lmpc_unit_price_within_tolerance_passes():
    ev = _lmpc_baseline_evidence()

    ev.set_field(
        "declared.best_before_use_by",
        "2026-08-01",
    )

    ev.set_field(
        "declared.unit_sale_price",
        180.0,
    )

    ev.set_field(
        "computed.expected_unit_sale_price",
        178.0,
    )

    report = _lmpc_engine().evaluate(
        ev,
        {},
    )

    result = report.by_id(
        "LMPC-6-11-UNIT-PRICE"
    )

    assert (
        result.status
        is ComplianceStatus.PASS
    )


def test_lmpc_unit_price_out_of_tolerance_fails():
    ev = _lmpc_baseline_evidence()

    ev.set_field(
        "declared.best_before_use_by",
        "2026-08-01",
    )

    ev.set_field(
        "declared.unit_sale_price",
        200.0,
    )

    ev.set_field(
        "computed.expected_unit_sale_price",
        178.0,
    )

    report = _lmpc_engine().evaluate(
        ev,
        {},
    )

    result = report.by_id(
        "LMPC-6-11-UNIT-PRICE"
    )

    assert (
        result.status
        is ComplianceStatus.FAIL
    )


def test_lmpc_unit_price_rule_not_applicable_when_not_declared():
    """
    When the upstream extraction system has explicitly confirmed that no unit
    sale price appears on the label (present=False), the applicability
    condition (exists declared.unit_sale_price) resolves to FALSE and the
    rule is NOT_APPLICABLE.

    Without any EvidenceValue for the field the result would be UNCERTAIN
    (we have not yet looked), which is the correct conservative behaviour:
    the rule may or may not apply — we do not know yet.
    """
    ev = _lmpc_baseline_evidence()

    ev.set_field(
        "declared.best_before_use_by",
        "2026-08-01",
    )

    # Upstream confirmed no unit sale price on the label.
    ev.set_field(
        "declared.unit_sale_price",
        None,
        present=False,
    )

    report = _lmpc_engine().evaluate(
        ev,
        {},
    )

    result = report.by_id(
        "LMPC-6-11-UNIT-PRICE"
    )

    assert (
        result.applicability
        is ApplicabilityStatus.NOT_APPLICABLE
    )


def test_lmpc_numeral_height_uses_context_supplied_threshold():
    ev = _lmpc_baseline_evidence()

    ev.set_field(
        "declared.best_before_use_by",
        "2026-08-01",
    )

    ev.set_field(
        "measured.numeral_height_mm",
        3.5,
        confidence=0.8,
    )

    ev.set_context(
        "required_numeral_height_mm",
        4.0,
    )

    report = _lmpc_engine().evaluate(
        ev,
        {},
    )

    result = report.by_id(
        "LMPC-7-NUMERAL-HEIGHT"
    )

    assert (
        result.status
        is ComplianceStatus.FAIL
    )


def test_lmpc_ruleset_produces_full_audit_trail_for_every_rule():
    ev = _lmpc_baseline_evidence()

    ev.set_field(
        "declared.best_before_use_by",
        "2026-08-01",
    )

    report = _lmpc_engine().evaluate(
        ev,
        {},
    )

    expected_rule_ids = {
        "LMPC-6-1-A-MANUFACTURER",
        "LMPC-6-1-B-COMMON-NAME",
        "LMPC-6-1-E-NET-QUANTITY",
        "LMPC-6-1-D-MFG-DATE",
        "LMPC-6-1-D-BEST-BEFORE",
        "LMPC-6-1-DA-MRP",
        "LMPC-6-1-DA-F-CONSUMER-CARE",
        "LMPC-6-1-A-COUNTRY-OF-ORIGIN",
        "LMPC-5-STANDARD-PACK-SIZE",
        "LMPC-6-11-UNIT-PRICE",
        "LMPC-7-NUMERAL-HEIGHT",
        "LMPC-4-MULTIPACK",
        "LMPC-25-EXPORT",
        "LMPC-26-B-FAST-FOOD",
        "LMPC-26-C-DRUG-FORMULATIONS",
        "LMPC-27-REGISTRATION",
        "LMPC-31-ADVERTISEMENT",
    }

    actual_rule_ids = {
        r.rule_id
        for r in report.results
    }

    assert actual_rule_ids == expected_rule_ids

    assert len(report.results) == len(
        expected_rule_ids
    )

    for r in report.results:
        assert r.trace["stages"], (
            f"{r.rule_id} has an empty audit trail"
        )


# ---------------------------------------------------------------------------
# Illustrative food-allergen regulation.
# ---------------------------------------------------------------------------

def test_food_allergen_rule_fails_when_allergen_present_but_not_declared():
    """
    Applicability: ingredients_text contains a recognised allergen → APPLICABLE.
    Requirement: allergen_statement exists → upstream confirmed absent (present=False)
    → exists() returns FALSE → FAIL.

    Without an explicit present=False the engine cannot distinguish "upstream
    never looked for this field" from "upstream found no allergen statement",
    so it would conservatively return UNCERTAIN.  The correct signal for
    "we searched the label and found no allergen statement" is present=False.
    """
    ev = Evidence()

    ev.set_field(
        "ingredients_text",
        "wheat flour, sugar, milk solids, salt",
    )

    # Upstream confirmed: no allergen statement found on the label.
    ev.set_field(
        "allergen_statement",
        None,
        present=False,
    )

    report = _food_engine().evaluate(
        ev,
        {
            "category": "packaged_food"
        },
    )

    result = report.by_id(
        "FOOD-ALLERGEN-DECLARED"
    )

    assert (
        result.applicability
        is ApplicabilityStatus.APPLICABLE
    )

    assert (
        result.status
        is ComplianceStatus.FAIL
    )


def test_food_allergen_rule_not_applicable_when_no_allergen_present():
    ev = Evidence()

    ev.set_field(
        "ingredients_text",
        "rice, water, salt",
    )

    report = _food_engine().evaluate(
        ev,
        {
            "category": "packaged_food"
        },
    )

    result = report.by_id(
        "FOOD-ALLERGEN-DECLARED"
    )

    assert (
        result.applicability
        is ApplicabilityStatus.NOT_APPLICABLE
    )


def test_food_ruleset_out_of_scope_for_non_food_category():
    ev = Evidence()

    ev.set_field(
        "ingredients_text",
        "milk",
    )

    report = _food_engine().evaluate(
        ev,
        {
            "category": "electronics"
        },
    )

    result = report.by_id(
        "FOOD-ALLERGEN-DECLARED"
    )

    assert (
        result.applicability
        is ApplicabilityStatus.NOT_APPLICABLE
    )


def test_food_serving_size_cross_check_dependency_chain():
    ev = Evidence()

    ev.set_field(
        "net_weight",
        200,
        unit="g",
    )

    ev.set_field(
        "net_weight.unit",
        "g",
    )

    ev.set_field(
        "serving_size",
        50,
    )

    ev.set_field(
        "servings_per_package",
        4,
    )

    report = _food_engine().evaluate(
        ev,
        {
            "category": "packaged_food"
        },
    )

    assert (
        report.by_id(
            "FOOD-NET-WEIGHT-METRIC"
        ).status
        is ComplianceStatus.PASS
    )

    assert (
        report.by_id(
            "FOOD-SERVING-SIZE-CROSS-CHECK"
        ).status
        is ComplianceStatus.PASS
    )


def test_food_serving_size_cross_check_skipped_when_dependency_fails():
    ev = Evidence()

    ev.set_field(
        "net_weight.unit",
        "lb",
    )

    ev.set_field(
        "serving_size",
        50,
    )

    ev.set_field(
        "servings_per_package",
        4,
    )

    report = _food_engine().evaluate(
        ev,
        {
            "category": "packaged_food"
        },
    )

    assert (
        report.by_id(
            "FOOD-NET-WEIGHT-METRIC"
        ).status
        is ComplianceStatus.FAIL
    )

    dependent = report.by_id(
        "FOOD-SERVING-SIZE-CROSS-CHECK"
    )

    assert (
        dependent.applicability
        is ApplicabilityStatus.NOT_APPLICABLE
    )


def test_two_unrelated_regulations_share_identical_engine_class():
    """
    Literal proof of "no module bias": same class, same code path.
    """

    assert (
        type(_lmpc_engine())
        is type(_food_engine())
        is RuleEngine
    )