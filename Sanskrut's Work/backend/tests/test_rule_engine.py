"""
Unit tests for rule_engine.py — no database required.

These tests exercise the core legal-engine principle directly:
    sufficient positive evidence -> PASS
    sufficient evidence of absence -> FAIL
    insufficient evidence -> UNCERTAIN
    scope exemption -> EXEMPT

The second half of this file is the LEGAL-SAFETY INVARIANT suite. Those tests
encode the non-negotiable rules of the whole system:

    NOT VISIBLE          != MISSING
    NOT_OBSERVED         != MISSING
    UNCERTAIN evidence   must NEVER directly become FAIL
    low OCR confidence   must NEVER itself become legal non-compliance
    poor image quality   must NEVER itself become legal non-compliance
    AI                   must NEVER directly decide legal compliance

A failure in that half is not a quality regression. It means the system is
capable of accusing a compliant package of breaking the law, which is the single
worst thing this project can do.
"""

from schema import (
    EvidenceStatus,
    FactStatus,
    ImageQuality,
    MeasurementMode,
    SurfaceObservation,
)
from rule_engine import RawExtraction, run_inspection


def _extraction(value, confidence=0.9):
    return RawExtraction(field="x", value=value, confidence=confidence)


def test_export_only_package_is_exempt():
    result = run_inspection(
        inspection_id="t-exempt-1",
        sale_type="export",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions={},
        is_export_only=True,
    )
    assert result.overall_status == FactStatus.EXEMPT
    assert result.exempt_reason


def test_well_evidenced_retail_declarations_pass():
    extractions = {
        "manufacturer_name_address": _extraction("ACME Pvt Ltd, Pune"),
        "common_name": _extraction("Refined Wheat Flour"),
        "net_quantity": _extraction("100 g"),
        "mrp": _extraction("MRP Rs 50"),
        "mfg_date": _extraction("08/2026"),
        "consumer_care": _extraction("1800-000-000"),
        "unit_sale_price": _extraction("Rs 50 per 100 g"),
    }
    result = run_inspection(
        inspection_id="t-pass-1",
        sale_type="retail",
        product_category="household",  # not perishable -> best_before not required
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions=extractions,
    )
    statuses = {f.field: f.status for f in result.facts}
    assert statuses.get("manufacturer_name_address") == FactStatus.PASS
    assert statuses.get("common_name") == FactStatus.PASS


def test_missing_declaration_without_sufficient_coverage_is_uncertain_not_fail():
    """
    Critical legal-safety invariant: absence of OCR evidence with no capture
    coverage information must NOT be treated as proof of non-compliance.
    """
    result = run_inspection(
        inspection_id="t-uncertain-1",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions={},  # nothing extracted, no captures supplied
    )
    statuses = {f.field: f.status for f in result.facts}
    # Every required Rule 6 field should be UNCERTAIN, never FAIL, when there
    # is no capture-coverage evidence to justify a FAIL.
    assert FactStatus.FAIL not in statuses.values()
    assert FactStatus.UNCERTAIN in statuses.values()
    assert result.overall_status == FactStatus.UNCERTAIN


def test_low_confidence_extraction_is_uncertain_not_pass():
    extractions = {
        "common_name": _extraction("possibly flour??", confidence=0.1),
    }
    result = run_inspection(
        inspection_id="t-lowconf-1",
        sale_type="retail",
        product_category="household",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions=extractions,
    )
    common_name_facts = [f for f in result.facts if f.field == "common_name"]
    assert common_name_facts
    assert common_name_facts[0].status == FactStatus.UNCERTAIN


def test_wholesale_sale_type_evaluates_rule24_not_rule6():
    extractions = {
        "manufacturer_name": _extraction("ACME Foods Pvt Ltd, Pune"),
        "common_name": _extraction("Refined Wheat Flour"),
        "wholesale_count_or_net_quantity": _extraction("5000 g"),
    }
    result = run_inspection(
        inspection_id="t-wholesale-1",
        sale_type="wholesale",
        product_category="food",
        net_quantity_value=5000,
        net_quantity_unit="g",
        mrp=None,
        extractions=extractions,
    )
    rule_ids = {f.rule_id for f in result.facts if f.rule_id}
    assert "LMPC-2011-R24-WHOLESALE" in rule_ids
    assert "LMPC-2011-R6-DECLARATIONS" not in rule_ids


def test_invalid_net_quantity_raises():
    import pytest

    with pytest.raises(ValueError):
        run_inspection(
            inspection_id="t-invalid-1",
            sale_type="retail",
            product_category="food",
            net_quantity_value=0,
            net_quantity_unit="g",
            mrp=50,
            extractions={},
        )


# ===========================================================================
# LEGAL-SAFETY INVARIANTS
# ===========================================================================

import rule_engine as engine  # noqa: E402


def _capture(
    *,
    coverage: float = 1.0,
    status: EvidenceStatus = EvidenceStatus.USABLE,
    surface_id: str = "s1",
) -> SurfaceObservation:
    """A capture with explicit, fully-specified coverage and quality."""
    return SurfaceObservation(
        surface_id=surface_id,
        image_id=f"img-{surface_id}",
        evidence_coverage=coverage,
        image_quality=ImageQuality(status=status),
    )


def _retail(**kwargs):
    """run_inspection for a plain retail household package, with overrides."""
    params = dict(
        inspection_id="t-inv",
        sale_type="retail",
        product_category="household",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions={},
    )
    params.update(kwargs)
    return run_inspection(**params)


# --- applicability: the fail-open regression --------------------------------


def test_condition_applicability_is_a_tri_state():
    """
    An unrecognised condition must resolve to APPLICABILITY_UNKNOWN, never to a
    silent yes or no.

    THE BUG THIS GUARDS. `_condition_is_applicable` used to end in a bare
    `return True`, so any condition string the engine did not implement made its
    requirement unconditionally MANDATORY. rules.json already ships three such
    strings (`pan_masala`, `tobacco_or_tobacco_product`,
    `package_is_within_the_partial_relaxation_range`), so this was one edit away
    from requiring a tobacco health warning on a packet of biscuits.
    """
    cases = {
        engine.APPLICABLE: [
            ({"condition": None}, {}),
            ({}, {}),
            ({"condition": "imported_product"}, {"is_imported": True}),
            ({"condition": "tobacco_or_tobacco_product"}, {"is_tobacco": True}),
            # Rule 6(11) has a defensible default: it applies unless narrowed.
            ({"condition": "rule_6_subrule_11_applies"}, {}),
        ],
        engine.NOT_APPLICABLE: [
            ({"condition": "imported_product"}, {"is_imported": False}),
            ({"condition": "tobacco_or_tobacco_product"}, {"is_tobacco": False}),
            (
                {"condition": "rule_6_subrule_11_applies"},
                {"unit_price_rule_applies": False},
            ),
        ],
        engine.APPLICABILITY_UNKNOWN: [
            # Recognised, but the caller never supplied the deciding key.
            ({"condition": "tobacco_or_tobacco_product"}, {}),
            ({"condition": "pan_masala"}, {}),
            # Not implemented by this engine version at all.
            ({"condition": "a_condition_added_to_rules_json_in_2027"}, {}),
            # A structured condition object this version cannot interpret.
            ({"condition": {"all_of": ["a", "b"]}}, {}),
        ],
    }
    for expected, requirements in cases.items():
        for requirement, context in requirements:
            actual = engine.condition_applicability(requirement, context)
            assert actual == expected, (
                f"{requirement.get('condition')!r} with context {context} "
                f"resolved to {actual}, expected {expected}"
            )


def test_undetermined_applicability_never_becomes_fail_even_at_full_coverage():
    """
    THE CORE OF THE FIX. Full, usable package coverage plus an absent declaration
    normally justifies FAIL. It must NOT when the engine cannot establish that
    the declaration applies to this package in the first place.
    """
    rule = {
        "rule_id": "TEST-UNKNOWN-CONDITION",
        "version": "test",
        "requirements": [
            {
                "id": "req-1",
                "field": "tobacco_health_warning",
                "description": "warning",
                "condition": "tobacco_or_tobacco_product",
            }
        ],
    }
    facts, findings = engine._evaluate_declaration_rule(
        rule=rule,
        extractions={},
        captures=[_capture(coverage=1.0)],
        context={},  # says nothing about tobacco
        low_confidence_threshold=0.55,
    )
    assert [f.status for f in facts] == [FactStatus.UNCERTAIN]
    assert facts[0].review_required is True
    assert "could not be determined" in facts[0].reason
    assert all(f.status is not FactStatus.FAIL for f in findings)


def test_the_engine_can_still_fail_so_the_fix_is_not_vacuous():
    """
    A guard that never permits FAIL would be useless. When applicability is
    DETERMINED and the declaration is absent under sufficient coverage, FAIL is
    the correct answer and must still be reachable.
    """
    rule = {
        "rule_id": "TEST-KNOWN-CONDITION",
        "version": "test",
        "requirements": [
            {
                "id": "req-1",
                "field": "tobacco_health_warning",
                "description": "warning",
                "condition": "tobacco_or_tobacco_product",
            }
        ],
    }
    facts, _findings = engine._evaluate_declaration_rule(
        rule=rule,
        extractions={},
        captures=[_capture(coverage=1.0)],
        context={"is_tobacco": True},  # applicability is now established
        low_confidence_threshold=0.55,
    )
    assert [f.status for f in facts] == [FactStatus.FAIL]


def test_not_applicable_requirements_are_dropped_entirely():
    rule = {
        "rule_id": "TEST-NA",
        "version": "test",
        "requirements": [
            {"id": "r", "field": "importer_address", "condition": "imported_product"}
        ],
    }
    assert engine._build_requirement_map(rule, {"is_imported": False}) == {}
    assert "importer_address" in engine._build_requirement_map(
        rule, {"is_imported": True}
    )


def test_requirement_map_never_mutates_the_loaded_rules():
    """
    `load_rules()` returns the parsed rules.json objects. Tagging applicability
    onto them in place would leak one inspection's context into the next, which
    for a legal engine means one product's exemptions silently applying to
    another.
    """
    requirement = {
        "id": "r",
        "field": "pan_masala_warning",
        "condition": "pan_masala",
    }
    rule = {"rule_id": "TEST-PURITY", "version": "test", "requirements": [requirement]}
    before = dict(requirement)

    mapped = engine._build_requirement_map(rule, {})
    assert mapped["pan_masala_warning"].get("_applicability_uncertain") is True
    assert requirement == before, "the rules.json requirement object was mutated"
    assert "_applicability_uncertain" not in requirement


# --- NOT_OBSERVED and image quality ----------------------------------------


def test_poor_image_quality_never_itself_becomes_non_compliance():
    """
    "Poor image quality must NEVER itself become legal non-compliance."

    An INVALID capture claiming full coverage must not authorise a FAIL. A blurry
    photograph is a statement about the photograph, not about the package.
    """
    result = _retail(
        inspection_id="t-badquality",
        captures=[_capture(coverage=1.0, status=EvidenceStatus.INVALID)],
    )
    statuses = [f.status for f in result.facts]
    assert FactStatus.FAIL not in statuses, (
        "an unusable image was allowed to prove a declaration absent"
    )
    assert result.overall_status == FactStatus.UNCERTAIN


def test_no_captures_at_all_can_never_produce_fail():
    """"NOT_OBSERVED != MISSING" at the coarsest possible granularity."""
    result = _retail(inspection_id="t-nocaptures", captures=None)
    assert FactStatus.FAIL not in [f.status for f in result.facts]
    assert result.overall_status == FactStatus.UNCERTAIN


def test_partial_coverage_below_threshold_cannot_prove_absence():
    """
    Coverage strictly below the absence threshold is not evidence of absence.
    Asserted against the engine's own constant so the test tracks the config.
    """
    assert not engine._evidence_sufficient_for_missing_field(
        [_capture(coverage=0.69)]
    )
    assert engine._evidence_sufficient_for_missing_field([_capture(coverage=0.70)])
    result = _retail(
        inspection_id="t-partial", captures=[_capture(coverage=0.69)]
    )
    assert FactStatus.FAIL not in [f.status for f in result.facts]


def test_overlapping_captures_do_not_sum_into_false_certainty():
    """
    Three 40%-coverage photographs of the same face are not 120% coverage. The
    engine must take the strongest single observation, not the sum, or a handful
    of partial photos would manufacture authority to FAIL.
    """
    captures = [_capture(coverage=0.4, surface_id=f"s{i}") for i in range(3)]
    assert engine._inspection_coverage(captures) == 0.4
    assert not engine._evidence_sufficient_for_missing_field(captures)


# --- confidence is not legality --------------------------------------------


def test_low_ocr_confidence_never_becomes_fail():
    """
    "Low OCR confidence must NEVER itself become legal non-compliance."

    The declaration was READ — so it is present on the package. A weak read makes
    the FINDING uncertain; it cannot make the package illegal. Full coverage is
    supplied so that the only remaining reason to FAIL would be the low
    confidence itself.
    """
    extractions = {
        "common_name": RawExtraction(
            field="common_name", value="Refined Wheat Flour", confidence=0.01
        )
    }
    result = _retail(
        inspection_id="t-lowconf-nofail",
        extractions=extractions,
        captures=[_capture(coverage=1.0)],
    )
    common = [f for f in result.facts if f.field == "common_name"]
    assert common and common[0].status == FactStatus.UNCERTAIN
    assert common[0].review_required is True


def test_extraction_confidence_is_never_reported_as_legal_certainty():
    """
    "AI must NEVER directly decide legal compliance."

    A near-perfect OCR score must not present itself as near-perfect legal
    certainty on a fact still awaiting review, so the two confidences are kept in
    separate fields.
    """
    extractions = {
        "common_name": RawExtraction(
            field="common_name", value="Refined Wheat Flour", confidence=0.99
        )
    }
    result = _retail(inspection_id="t-provenance", extractions=extractions)
    common = [f for f in result.facts if f.field == "common_name"][0]
    assert hasattr(common, "extraction_confidence")
    assert hasattr(common, "decision_confidence")
    assert common.rule_id, "a fact must cite the rule it was judged against"
    assert common.rule_version, (
        "a legal finding without a rule VERSION is not auditable"
    )


def test_uncertain_is_never_aggregated_away_into_pass():
    """
    One unresolved declaration must hold the whole inspection at UNCERTAIN. If
    UNCERTAIN could be outvoted by PASSes, an inspection could be reported clean
    while a mandatory declaration was still unread.
    """
    from schema import ExtractedFact

    def fact(status):
        return ExtractedFact(field="f", status=status, confidence=0.9)

    passes = [fact(FactStatus.PASS)] * 8
    assert engine._aggregate_status(passes) == FactStatus.PASS
    assert (
        engine._aggregate_status(passes + [fact(FactStatus.UNCERTAIN)])
        == FactStatus.UNCERTAIN
    )
    # FAIL outranks UNCERTAIN; an established breach is not softened by doubt
    # elsewhere on the package.
    assert (
        engine._aggregate_status(
            passes + [fact(FactStatus.UNCERTAIN), fact(FactStatus.FAIL)]
        )
        == FactStatus.FAIL
    )
    assert engine._aggregate_status([]) == FactStatus.UNCERTAIN


def test_condition_defaults_match_the_public_api():
    """
    Every entry in `_CONDITION_DEFAULTS` must mirror the corresponding
    `run_inspection()` keyword default.

    That table is only defensible because the engine PUBLISHES those defaults; a
    default that has silently drifted from the signature is just a guess wearing
    a comment. This test reads the real signature so the two cannot diverge.
    """
    import inspect

    signature = inspect.signature(run_inspection)
    published = {
        "imported_product": "is_imported",
        "commodity_dimensions_are_relevant": "dimensions_relevant",
        "commodity_may_become_unfit_for_human_consumption": "best_before_applicable",
    }
    for condition, parameter in published.items():
        assert parameter in signature.parameters, (
            f"run_inspection lost the {parameter!r} parameter that "
            f"_CONDITION_DEFAULTS[{condition!r}] claims to mirror"
        )
        assert engine._CONDITION_DEFAULTS[condition] is bool(
            signature.parameters[parameter].default
        ), f"{condition!r} default drifted from run_inspection({parameter}=...)"

    # rule_6_subrule_11_applies has no parameter; its default comes from the rule
    # itself (6(11) applies to retail packages unless narrowed by the caller).
    assert engine._CONDITION_DEFAULTS["rule_6_subrule_11_applies"] is True

    # The conditions with NO published default must stay absent, or the engine
    # would be guessing about tobacco and pan masala.
    for condition in (
        "pan_masala",
        "tobacco_or_tobacco_product",
        "package_is_within_the_partial_relaxation_range",
    ):
        assert condition not in engine._CONDITION_DEFAULTS, (
            f"{condition!r} acquired a default the engine does not publish"
        )
        assert condition in engine._CONDITION_CONTEXT_KEYS, (
            f"{condition!r} must still be recognised so it can be resolved when "
            "the caller does supply the flag"
        )


def test_every_condition_in_rules_json_is_recognised_or_explicitly_unknown():
    """
    A condition string that reaches a requirement without being recognised is the
    fail-open bug. This walks the REAL rules.json so adding a new condition
    without teaching the engine about it is caught here rather than in the field.
    """
    rules = engine.load_rules()
    unrecognised = []
    for rule_id, rule in rules.items():
        for req in rule.get("requirements", []) or []:
            condition = req.get("condition")
            if not isinstance(condition, str):
                continue
            if condition not in engine._CONDITION_CONTEXT_KEYS:
                unrecognised.append((rule_id, req.get("field"), condition))

    assert not unrecognised, (
        "rules.json contains condition strings this engine does not implement: "
        f"{unrecognised}. They would resolve to APPLICABILITY_UNKNOWN, so no "
        "false FAIL can result, but the requirement can never reach a definite "
        "verdict either. Add them to _CONDITION_CONTEXT_KEYS."
    )


def test_the_engine_is_deterministic():
    """
    The rule engine is the deterministic half of the system. Identical input must
    produce an identical decision, or the audit trail means nothing.
    """
    extractions = {
        "common_name": RawExtraction(
            field="common_name", value="Refined Wheat Flour", confidence=0.9
        )
    }
    runs = [
        _retail(
            inspection_id="t-determinism",
            extractions=extractions,
            captures=[_capture(coverage=0.8)],
        )
        for _ in range(3)
    ]
    signatures = [
        [(f.field, f.status, f.reason) for f in r.facts] for r in runs
    ]
    assert signatures[0] == signatures[1] == signatures[2]
    assert len({r.overall_status for r in runs}) == 1


# --- Rule 6(11) unit price: the unit-basis false-FAIL regression -------------
#
# MEASURED BUG. `compute_unit_sale_price` returns the price per the Rule 6(11)
# DISPLAY unit (0.50 per GRAM for a 100 g pack at MRP 50), while the declared
# price was converted to the larger standard unit (500.00 per KG). The engine
# compared the two directly, so a CORRECTLY declared sub-kilogram package was
# tested as 500.00 == 0.50 and reported as a Rule 6(11) FAIL. Every retail pack
# below 1 kg / 1 litre / 1 metre that declares a unit price was affected.
#
# A false FAIL against a compliant package is the worst output this system can
# produce, so these tests assert both halves: correct declarations pass on
# either basis, and a genuinely wrong price still fails.


def _unit_price_finding(
    *,
    net_quantity_value,
    net_quantity_unit,
    mrp,
    declared_value,
    declared_unit,
    confidence=0.95,
    mrp_confidence=0.95,
):
    """Return the Rule 6(11) finding for one declared unit price, or None."""
    result = run_inspection(
        inspection_id="t-usp",
        sale_type="retail",
        product_category="household",
        net_quantity_value=net_quantity_value,
        net_quantity_unit=net_quantity_unit,
        mrp=mrp,
        extractions={
            "mrp": RawExtraction(
                field="mrp",
                value=f"MRP Rs {mrp}",
                confidence=mrp_confidence,
                numeric_value=float(mrp),
            ),
            "unit_sale_price": RawExtraction(
                field="unit_sale_price",
                value=f"{declared_value} per {declared_unit}",
                confidence=confidence,
                numeric_value=declared_value,
                numeric_unit=declared_unit,
            ),
        },
    )
    for finding in result.findings:
        if finding.rule_id == "LMPC-2011-R6-11-UNIT-PRICE":
            return finding
    return None


def test_a_correct_unit_price_passes_on_either_unit_basis():
    """
    THE UNIT-BASIS REGRESSION. 100 g at MRP 50 is Rs 0.50/g and Rs 500/kg —
    the same declaration expressed two lawful ways. Both must PASS.
    """
    for declared_value, declared_unit in (
        (500, "kg"),
        (0.50, "g"),
    ):
        finding = _unit_price_finding(
            net_quantity_value=100,
            net_quantity_unit="g",
            mrp=50,
            declared_value=declared_value,
            declared_unit=declared_unit,
        )
        assert finding is not None
        assert finding.status == FactStatus.PASS, (
            f"a correct declaration of {declared_value} per {declared_unit} was "
            f"reported {finding.status}: {finding.reason}"
        )


def test_correct_unit_prices_pass_across_families_and_magnitudes():
    """The guard must not be narrow to one worked example."""
    cases = (
        (500, "ml", 20, 40, "l"),
        (500, "ml", 20, 0.04, "ml"),
        (250, "g", 75, 300, "kg"),
        (1.5, "kg", 120, 80, "kg"),
        (30, "g", 10, 333.33, "kg"),  # single-rounding case, see below
    )
    for nqv, nqu, mrp, declared, unit in cases:
        finding = _unit_price_finding(
            net_quantity_value=nqv,
            net_quantity_unit=nqu,
            mrp=mrp,
            declared_value=declared,
            declared_unit=unit,
        )
        assert finding is not None, f"no finding for {nqv}{nqu} @ {mrp}"
        assert finding.status == FactStatus.PASS, (
            f"{nqv}{nqu} at MRP {mrp} correctly declared as {declared}/{unit} "
            f"was reported {finding.status}: {finding.reason}"
        )


def test_the_unit_price_check_can_still_fail_so_the_fix_is_not_vacuous():
    """
    The repair must not have been "make Rule 6(11) always pass". A materially
    wrong declared price must still FAIL.
    """
    for declared_value, declared_unit in ((999, "kg"), (0.75, "g")):
        finding = _unit_price_finding(
            net_quantity_value=100,
            net_quantity_unit="g",
            mrp=50,
            declared_value=declared_value,
            declared_unit=declared_unit,
        )
        assert finding is not None
        assert finding.status == FactStatus.FAIL, (
            f"a wrong price of {declared_value} per {declared_unit} was not "
            f"caught; got {finding.status}"
        )


def test_a_low_confidence_unit_price_reading_is_uncertain_not_fail():
    """
    "Low OCR confidence must NEVER itself become legal non-compliance."

    The declaration path already honoured the threshold; this arithmetic path
    did not, and its mismatch branch is an unconditional FAIL. Measured on
    dataset image 3, extraction produced unit_sale_price 573.18 at confidence
    0.31 out of the nutrition panel — a number that would never satisfy the
    equality test, so the engine would have announced a FAIL on a reading it
    could not read.
    """
    finding = _unit_price_finding(
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        declared_value=999,
        declared_unit="kg",
        confidence=0.30,
    )
    assert finding is not None
    assert finding.status == FactStatus.UNCERTAIN
    assert finding.review_required is True


def test_a_low_confidence_mrp_never_produces_a_unit_price_verdict():
    """
    The MRP is the NUMERATOR of the expected value, so a weak MRP corrupts the
    comparison even when the declared unit price was read perfectly. Measured on
    dataset image 3: mrp numeric 11.68 at confidence 0.24, read from the protein
    row of the nutrition panel.

    Asserted with a CORRECT declared price, so the only thing that can move the
    verdict away from PASS is the MRP gate itself.
    """
    finding = _unit_price_finding(
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        declared_value=500,
        declared_unit="kg",
        mrp_confidence=0.24,
    )
    assert finding is not None
    assert finding.status == FactStatus.UNCERTAIN
    assert finding.review_required is True
    assert finding.status != FactStatus.FAIL


def test_a_declaration_from_another_quantity_family_is_uncertain_not_fail():
    """
    "Do not convert mass <-> volume without supplied density." A per-kilogram
    price on a 500 ml pack cannot be verified arithmetically, and an
    unverifiable declaration is UNCERTAIN — never a FAIL, and never a PASS.
    """
    finding = _unit_price_finding(
        net_quantity_value=500,
        net_quantity_unit="ml",
        mrp=20,
        declared_value=40,
        declared_unit="kg",
    )
    assert finding is not None
    assert finding.status == FactStatus.UNCERTAIN
    assert finding.review_required is True


def test_expected_unit_price_rounds_once_not_twice():
    """
    WHY THE OBVIOUS REPAIR WOULD HAVE BEEN A SECOND BUG.

    Scaling the display-unit price up to the standard unit looks like the natural
    one-line fix, but `compute_unit_sale_price` has already quantized to paise in
    the SMALL unit, so multiplying by 1000 multiplies the rounding error by 1000.

    30 g at MRP 10:
        true per-kg value      10 / 0.030 = 333.333... -> 333.33
        display-unit price     10 / 30    = 0.333...   -> 0.33
        naive scale-up         0.33 * 1000            =  330.00   <- wrong by 3.33

    A pack correctly declaring Rs 333.33/kg would then have been failed. This
    test pins the single-division, single-quantization behaviour so that repair
    cannot be reintroduced.
    """
    from decimal import Decimal

    from unit_price import (
        compute_unit_sale_price,
        expected_unit_price_in_declared_unit,
    )

    assert expected_unit_price_in_declared_unit(30, "g", 10, "kg") == Decimal("333.33")

    naive = compute_unit_sale_price(30, "g", 10).unit_sale_price * 1000
    assert naive == Decimal("330.000"), "the naive path changed; update this guard"
    assert expected_unit_price_in_declared_unit(30, "g", 10, "kg") != naive

    # The small-unit basis is still exact on its own terms.
    assert expected_unit_price_in_declared_unit(30, "g", 10, "g") == Decimal("0.33")


def test_expected_unit_price_never_guesses_across_unit_families():
    """None means "not comparable" and must never be coerced into a number."""
    from unit_price import expected_unit_price_in_declared_unit

    assert expected_unit_price_in_declared_unit(500, "ml", 20, "kg") is None
    assert expected_unit_price_in_declared_unit(100, "g", 50, "litre") is None
    assert expected_unit_price_in_declared_unit(100, "g", 50, "furlong") is None
    assert expected_unit_price_in_declared_unit(0, "g", 50, "kg") is None
    assert expected_unit_price_in_declared_unit(-5, "g", 50, "kg") is None
