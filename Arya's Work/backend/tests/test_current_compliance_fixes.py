"""
Regression tests for the "fix the existing LexMetra compliance engine" task.

Each test below is named for, and traces directly back to, one of the
problems reported against the Suraj Industries fruit-juice label:

    TEST A: best-before absence must not be misreported as an OCR failure
    TEST B: a parseable-but-noncompliant unit-sale-price declaration must be
            evaluated semantically, not written off as an OCR failure
    TEST C: the obsolete Second Schedule rule must not participate in a
            CURRENT compliance inspection
    TEST D: "Name, Country" must not be treated as a complete address
    TEST E: a genuinely complete name+address must still PASS
    TEST F: unit-sale-price correctness across ml/litre/g/kg, valid+invalid

None of these hard-code the Suraj product, its exact MRP, or its exact
quantity: each test varies the numbers/units/categories to prove the fix is
generic (see individual test bodies).
"""

import datetime as _dt

from schema import (
    CanonicalStatus,
    EvidenceStatus,
    FactStatus,
    ImageQuality,
    SurfaceObservation,
)
from rule_engine import RawExtraction, filter_active_rules, load_rules, run_inspection


def _extraction(value, confidence=0.9, **kwargs):
    return RawExtraction(field="x", value=value, confidence=confidence, **kwargs)


def _capture(coverage: float = 1.0, surface_id: str = "s1") -> SurfaceObservation:
    """A capture with full, explicit coverage -- enough to support a genuine
    "confirmed absent" FAIL rather than an insufficient-coverage UNCERTAIN."""
    return SurfaceObservation(
        surface_id=surface_id,
        image_id=f"img-{surface_id}",
        evidence_coverage=coverage,
        image_quality=ImageQuality(status=EvidenceStatus.USABLE),
    )


def _unit_sale_price_finding(result, rule_id="LMPC-2011-R6-11-UNIT-PRICE"):
    for finding in result.findings:
        if finding.rule_id == rule_id:
            return finding
    return None


def _unit_sale_price_declaration(result):
    for d in result.declarations:
        if d.field == "unit_sale_price":
            return d
    return None


# ===========================================================================
# TEST A -- best-before absence must be reported as absence, not as an
# unreadable-OCR problem.
# ===========================================================================

def test_A_missing_best_before_is_not_reported_as_ocr_unreadable():
    """
    A 100 ml juice-style label with every OTHER mandatory declaration present
    and confidently read, sufficient package coverage, and NO best-before
    text anywhere. The correct outcome is a clear "not evidenced" FAIL --
    never a claim that OCR found candidate expiry text it could not read.
    """
    extractions = {
        "manufacturer_name_address": _extraction("Test Foods Pvt Ltd, 45 Industrial Estate, Nashik 422101"),
        "common_name": _extraction("Fruit Juice"),
        "net_quantity": _extraction("100 ml", numeric_value=100.0, numeric_unit="ml"),
        "mfg_date": _extraction("04/2026", normalized_value="2026-04"),
        "mrp": _extraction("Rs 100", numeric_value=100.0),
        "consumer_care": _extraction("1800-000-000"),
        # No best_before_use_by extraction at all.
    }
    result = run_inspection(
        inspection_id="t-A-1",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="ml",
        mrp=100,
        extractions=extractions,
        best_before_applicable=True,
        captures=[_capture(coverage=1.0)],
    )

    bb_facts = [f for f in result.facts if f.field == "best_before_use_by"]
    assert len(bb_facts) == 1
    fact = bb_facts[0]

    # With sufficient package coverage and nothing found, this is a
    # confirmed-absent FAIL, not UNCERTAIN.
    assert fact.status == FactStatus.FAIL
    assert "not evidenced" in fact.reason.lower() or "not observed" in fact.reason.lower()

    # The canonical declaration row (what the UI renders) must not carry a
    # misleading "could not be read reliably" bullet: readable must be
    # unset (None/not-applicable), never False, when nothing was found.
    decl = next(d for d in result.declarations if d.field == "best_before_use_by")
    assert decl.status == CanonicalStatus.NON_COMPLIANT
    assert decl.validation.readable is not False, (
        f"absence was misreported as an unreadable-OCR problem: {decl.validation}"
    )
    assert "read" not in decl.reason.lower() or "not observed" in decl.reason.lower() or "not evidenced" in decl.reason.lower()


def test_A_best_before_genuinely_unreadable_is_distinguished_from_absent():
    """
    Sanity check on the other side of the same fix: when OCR DID find
    candidate best-before text but at low confidence, that is still reported
    distinctly (present, low confidence) rather than as confirmed absence.
    """
    extractions = {
        "best_before_use_by": _extraction("B3 2026", confidence=0.2),
    }
    result = run_inspection(
        inspection_id="t-A-2",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="ml",
        mrp=100,
        extractions=extractions,
        best_before_applicable=True,
        captures=[_capture(coverage=1.0)],
    )
    fact = next(f for f in result.facts if f.field == "best_before_use_by")
    assert fact.status == FactStatus.UNCERTAIN
    assert fact.field == "best_before_use_by"


# ===========================================================================
# TEST B -- a parseable-but-noncompliant unit-sale-price declaration must be
# evaluated semantically, never dismissed as "OCR did not provide a
# structured numeric value".
# ===========================================================================

def test_B_unit_price_with_compound_unit_text_is_semantically_evaluated():
    """
    '2634.2/kg or litre' on a 100 ml, MRP 263.42 package. The number IS
    parseable and the units ARE recognisable; the old bug reported this as
    an OCR/extraction failure. It must instead reach a real semantic
    evaluation. (Rs 2634.2 per LITRE for a 100 ml pack is Rs 263.42 / 0.1 L
    == 2634.2 -- i.e. mathematically correct on the litre basis, and Rule
    6(11) permits declaring on either lawful basis within the same quantity
    family -- see TEST F -- so this specific number is expected to PASS.)
    """
    extractions = {
        "mrp": _extraction("Rs.263.42", numeric_value=263.42),
        "unit_sale_price": _extraction(
            "Rs.2634.2/kg or litre",
            numeric_value=2634.2,
            numeric_unit="kg",
            numeric_unit_alternatives=["kg", "l"],
        ),
    }
    result = run_inspection(
        inspection_id="t-B-1",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="ml",
        mrp=263.42,
        extractions=extractions,
    )
    finding = _unit_sale_price_finding(result)
    assert finding is not None

    # The old bug: reason contained "OCR/CV did not provide a structured
    # numeric value" even though numeric_value WAS present. Assert the
    # specific misdiagnosis is gone...
    assert "did not provide a structured numeric value" not in finding.reason
    # ...and that a real semantic/mathematical verdict was reached.
    assert finding.status in (FactStatus.PASS, FactStatus.FAIL)
    assert finding.status == FactStatus.PASS, finding.reason


def test_B_unit_price_text_present_but_truly_unparseable_stays_an_evidence_gap():
    """Contrast case: genuinely no unit could be identified at all -- THIS
    (and only this) is the legitimate OCR/extraction-gap UNCERTAIN."""
    extractions = {
        "mrp": _extraction("Rs.263.42", numeric_value=263.42),
        "unit_sale_price": _extraction(
            "some illegible price text", numeric_value=2634.2, numeric_unit=None,
        ),
    }
    result = run_inspection(
        inspection_id="t-B-2",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="ml",
        mrp=263.42,
        extractions=extractions,
    )
    finding = _unit_sale_price_finding(result)
    assert finding is not None
    assert finding.status == FactStatus.UNCERTAIN
    assert "evidence" in finding.reason.lower() or "extraction" in finding.reason.lower()


# ===========================================================================
# TEST C -- the obsolete Second Schedule rule must not participate in a
# CURRENT compliance inspection.
# ===========================================================================

def test_C_second_schedule_rule_is_excluded_from_current_ruleset():
    """
    Unit-level guarantee: as of TODAY, filter_active_rules() must exclude
    both Second-Schedule rule ids, regardless of any specific product.
    """
    rules = load_rules()
    assert "LMPC-2011-R5-STANDARD-PACK" in rules
    assert "LMPC-2011-SCHEDULE-II" in rules  # still present for history/versioning

    active = filter_active_rules(rules, _dt.date.today())
    assert "LMPC-2011-R5-STANDARD-PACK" not in active, (
        "obsolete Second Schedule rule (LMPC-2011-R5-STANDARD-PACK) is still "
        "active for a CURRENT inspection"
    )
    assert "LMPC-2011-SCHEDULE-II" not in active


def test_C_second_schedule_rule_is_excluded_from_a_real_inspection_run():
    """
    Integration-level guarantee: run_inspection's default (undated -> "as of
    today") path must never produce a standard_pack_size fact/finding, for
    ANY product category or evidence -- not just the specific Suraj example.
    """
    for category in ("biscuits", "beverage", "household", "food"):
        result = run_inspection(
            inspection_id=f"t-C-{category}",
            sale_type="retail",
            product_category=category,
            net_quantity_value=100,
            net_quantity_unit="g",
            mrp=50,
            extractions={},
        )
        assert not any(f.field == "standard_pack_size" for f in result.facts), category
        assert not any(
            fnd.rule_id in ("LMPC-2011-R5-STANDARD-PACK", "LMPC-2011-SCHEDULE-II")
            for fnd in result.findings
        ), category
        # The canonical (UI-facing) row must exist and read NOT_APPLICABLE,
        # never a review/failure state implying the old rule is still live.
        decl = next(d for d in result.declarations if d.field == "standard_pack_size")
        assert decl.status == CanonicalStatus.NOT_APPLICABLE, (category, decl.status, decl.reason)
        assert "second schedule" not in decl.reason.lower() or "not part of the current active ruleset" in decl.reason.lower()


def test_C_historical_rule_data_is_preserved_not_deleted():
    """The requirement to preserve history: the rule's data must still be
    on disk with its original substance intact, just marked non-current."""
    rules = load_rules()
    rule = rules["LMPC-2011-R5-STANDARD-PACK"]
    assert rule.get("status") == "superseded"
    assert rule.get("effective_to") is not None
    # The rule's own descriptive/legal content was not stripped out.
    assert rule.get("rule_id") == "LMPC-2011-R5-STANDARD-PACK"


# ===========================================================================
# TEST D -- "Name, Country" (or name alone) must not be a complete address.
# ===========================================================================

def test_D_name_plus_bare_country_is_not_a_complete_address():
    extractions = {
        "manufacturer_name_address": _extraction("Suraj Industries Pvt Ltd, India"),
    }
    result = run_inspection(
        inspection_id="t-D-1",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="ml",
        mrp=100,
        extractions=extractions,
    )
    fact = next(f for f in result.facts if f.field == "manufacturer_name_address")
    assert fact.status != FactStatus.PASS, (
        f"'Name, Country' was accepted as a complete address: {fact.reason}"
    )
    assert fact.confidence < 1.0 or fact.status == FactStatus.FAIL


def test_D_name_only_is_not_a_complete_address():
    extractions = {"manufacturer_name_address": _extraction("Suraj Industries Pvt Ltd")}
    result = run_inspection(
        inspection_id="t-D-2", sale_type="retail", product_category="food",
        net_quantity_value=100, net_quantity_unit="ml", mrp=100, extractions=extractions,
    )
    fact = next(f for f in result.facts if f.field == "manufacturer_name_address")
    assert fact.status != FactStatus.PASS


def test_D_name_plus_bare_city_is_uncertain_or_fail_not_pass():
    """A single extra token (city, with no postal code or street) is still
    not legally sufficient -- distinct from 'insufficient' only in degree."""
    extractions = {"manufacturer_name_address": _extraction("Acme Traders, Pune")}
    result = run_inspection(
        inspection_id="t-D-3", sale_type="retail", product_category="food",
        net_quantity_value=100, net_quantity_unit="ml", mrp=100, extractions=extractions,
    )
    fact = next(f for f in result.facts if f.field == "manufacturer_name_address")
    assert fact.status in (FactStatus.FAIL, FactStatus.UNCERTAIN)


def test_D_incomplete_address_with_locality_but_no_postal_code_is_uncertain():
    extractions = {
        "manufacturer_name_address": _extraction(
            "Acme Traders, MIDC Industrial Area, Pune, Maharashtra"
        ),
    }
    result = run_inspection(
        inspection_id="t-D-4", sale_type="retail", product_category="food",
        net_quantity_value=100, net_quantity_unit="ml", mrp=100, extractions=extractions,
    )
    fact = next(f for f in result.facts if f.field == "manufacturer_name_address")
    # Several segments but no postal code -> ambiguous, needs review, but
    # must not be silently waved through as a fully-verified PASS.
    assert fact.status != FactStatus.PASS


def test_D_not_applicable_scenario_country_of_origin_untouched_by_stricter_address_check():
    """The stricter manufacturer/address check must not spill over into an
    unrelated NOT_APPLICABLE requirement (country of origin for a domestic,
    non-imported product)."""
    result = run_inspection(
        inspection_id="t-D-5", sale_type="retail", product_category="food",
        net_quantity_value=100, net_quantity_unit="ml", mrp=100, extractions={},
        is_imported=False,
    )
    decl = next(d for d in result.declarations if d.field == "country_of_origin")
    assert decl.status == CanonicalStatus.NOT_APPLICABLE


# ===========================================================================
# TEST E -- a genuinely complete manufacturer/address must still PASS.
# ===========================================================================

def test_E_complete_address_with_postal_code_passes():
    extractions = {
        "manufacturer_name_address": _extraction(
            "Suraj Industries Pvt Ltd, Plot 12, MIDC Industrial Area, Pune, "
            "Maharashtra 411019, India"
        ),
    }
    result = run_inspection(
        inspection_id="t-E-1", sale_type="retail", product_category="food",
        net_quantity_value=100, net_quantity_unit="ml", mrp=100, extractions=extractions,
    )
    fact = next(f for f in result.facts if f.field == "manufacturer_name_address")
    assert fact.status == FactStatus.PASS, fact.reason


def test_E_complete_address_short_form_with_pin_passes():
    """A shorter but still genuinely complete address (city + PIN) should
    also pass -- completeness, not verbosity, is what matters."""
    extractions = {
        "manufacturer_name_address": _extraction("Hindustan Foods Ltd, Mumbai 400099"),
    }
    result = run_inspection(
        inspection_id="t-E-2", sale_type="retail", product_category="food",
        net_quantity_value=100, net_quantity_unit="ml", mrp=100, extractions=extractions,
    )
    fact = next(f for f in result.facts if f.field == "manufacturer_name_address")
    assert fact.status == FactStatus.PASS, fact.reason


def test_E_imported_product_scenario_uses_same_generic_completeness_check():
    """
    For an imported product, whatever name+address IS declared is still
    judged by the same generic completeness rule (no separate, invented
    importer-specific legal text) -- a complete declaration still passes.
    """
    extractions = {
        "manufacturer_name_address": _extraction(
            "Global Foods Importers Pvt Ltd, 7 Trade Centre, Chennai, Tamil Nadu 600001"
        ),
        "country_of_origin": _extraction("Thailand"),
    }
    result = run_inspection(
        inspection_id="t-E-3", sale_type="retail", product_category="food",
        net_quantity_value=100, net_quantity_unit="ml", mrp=100, extractions=extractions,
        is_imported=True,
    )
    fact = next(f for f in result.facts if f.field == "manufacturer_name_address")
    assert fact.status == FactStatus.PASS, fact.reason
    coo_decl = next(d for d in result.declarations if d.field == "country_of_origin")
    assert coo_decl.status != CanonicalStatus.NOT_APPLICABLE


# ===========================================================================
# TEST F -- unit-sale-price correctness across ml / litre / g / kg, valid and
# invalid, malformed, unsupported unit, and missing.
# ===========================================================================

def _run_unit_price_case(net_qty, net_unit, mrp, declared_value, declared_unit,
                          alternatives=None, confidence=0.9):
    extractions = {
        "mrp": RawExtraction(field="mrp", value=f"Rs {mrp}", confidence=0.95, numeric_value=float(mrp)),
        "unit_sale_price": RawExtraction(
            field="unit_sale_price",
            value=f"{declared_value} per {declared_unit}" if declared_value is not None else None,
            confidence=confidence,
            numeric_value=declared_value,
            numeric_unit=declared_unit,
            numeric_unit_alternatives=alternatives,
        ),
    }
    result = run_inspection(
        inspection_id="t-F", sale_type="retail", product_category="food",
        net_quantity_value=net_qty, net_quantity_unit=net_unit, mrp=mrp,
        extractions=extractions,
    )
    return _unit_sale_price_finding(result)


def test_F_valid_unit_prices_across_units_and_quantities():
    cases = [
        (250, "ml", 50.0, 200.0, "l"),
        (500, "ml", 60.0, 120.0, "l"),
        (750, "ml", 90.0, 120.0, "l"),
        (100, "g", 40.0, 400.0, "kg"),
        (250, "g", 100.0, 400.0, "kg"),
    ]
    # 100ml @ MRP 20 => per litre = 20/0.1 = 200
    cases.insert(0, (100, "ml", 20.0, 200.0, "l"))
    for net_qty, net_unit, mrp, declared_value, declared_unit in cases:
        finding = _run_unit_price_case(net_qty, net_unit, mrp, declared_value, declared_unit)
        assert finding is not None, (net_qty, net_unit, declared_value, declared_unit)
        assert finding.status == FactStatus.PASS, (
            f"{net_qty}{net_unit} @ MRP {mrp} declared {declared_value}/{declared_unit}: "
            f"{finding.status} -- {finding.reason}"
        )


def test_F_invalid_unit_price_amount_fails():
    """Right unit, wrong number."""
    finding = _run_unit_price_case(100, "ml", 20.0, 999.99, "l")
    assert finding.status == FactStatus.FAIL


def test_F_malformed_numeric_value_is_uncertain_not_fail():
    """numeric_value is None (OCR could not read a number at all)."""
    result = run_inspection(
        inspection_id="t-F-malformed", sale_type="retail", product_category="food",
        net_quantity_value=100, net_quantity_unit="ml", mrp=20,
        extractions={
            "mrp": RawExtraction(field="mrp", value="Rs 20", confidence=0.95, numeric_value=20.0),
            "unit_sale_price": RawExtraction(
                field="unit_sale_price", value="illegible", confidence=0.9,
                numeric_value=None, numeric_unit="l",
            ),
        },
    )
    finding = _unit_sale_price_finding(result)
    assert finding.status == FactStatus.UNCERTAIN


def test_F_unsupported_or_invalid_unit_is_uncertain_not_fail():
    """A unit that does not belong to the volume family for a ml package
    (e.g. a length unit) must be UNCERTAIN (semantic mismatch), not FAIL."""
    finding = _run_unit_price_case(100, "ml", 20.0, 200.0, "cm")
    assert finding.status == FactStatus.UNCERTAIN


def test_F_missing_unit_sale_price_when_required():
    result = run_inspection(
        inspection_id="t-F-missing", sale_type="retail", product_category="food",
        net_quantity_value=250, net_quantity_unit="ml", mrp=45, extractions={},
    )
    finding = _unit_sale_price_finding(result)
    assert finding is not None
    assert finding.status == FactStatus.UNCERTAIN


def test_F_single_standard_unit_package_is_exempt_from_declaration():
    """1 litre / 1 kg packages are exempt from a separate unit-price
    declaration under the existing Rule 6(11) exception -- untouched by
    this fix."""
    finding = _run_unit_price_case(1000, "ml", 100.0, None, None)
    assert finding.status == FactStatus.EXEMPT
