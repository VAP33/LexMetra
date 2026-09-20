"""
Deterministic compliance rule engine.

Core principle:
    AI/CV/OCR extracts evidence.
    This module evaluates that evidence against versioned legal rules.
    It does not use an LLM to decide legality.

The engine is intentionally evidence-first:
    - "not detected" is not automatically equivalent to "legally absent"
      when the inspection does not have sufficient package coverage.
    - verified evidence can produce FAIL.
    - insufficient/uncertain evidence produces UNCERTAIN.
    - exemptions are evaluated before ordinary declaration checks.
    - legal thresholds are read from rules.json rather than duplicated here.

The public run_inspection() signature retains compatibility with the original
prototype while accepting optional multi-surface evidence from schema.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from schema import (
    BBox,
    CanonicalDeclaration,
    CanonicalStatus,
    CANONICAL_DECLARATION_DEFINITIONS,
    DeclarationEvidence,
    EvidenceAgreement,
    EvidenceReference,
    FactStatus,
    ExtractedFact,
    GeometryType,
    MeasurementMode,
    PackageStructure,
    ProductInspection,
    RuleFinding,
    SurfaceObservation,
    UNATTRIBUTED_IMAGE_ID,
    ValidationDetails,
    coerce_evidence_agreement,
)



import exemption as exemption_module
from exemption import (
    QUANTITY_NOT_ESTABLISHED,
    ExemptionInput,
    classify_exemption,
)
import calibration as calib
from regulatory.runtime import apply_rule_versions, version_label

from unit_price import (
    compute_unit_sale_price,
    convert_declared_price_to_standard,
    expected_unit_price_in_declared_unit,
)


RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "rules.json"
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.55


from rule_common import (
    RULES_PATH,
    DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    RawExtraction,
    load_rules,
    _find_rule,
    _rule_status,
    _bbox_from_any,
    _evidence_for_extraction,
    _human_field_name,
    agreement_cap,
    _make_fact,
    _finding,
    _is_low_confidence,
    _has_value,
    _inspection_coverage,
    _evidence_sufficient_for_missing_field,
    _field_requirements,
    condition_applicability,
    _condition_is_applicable,
    _build_requirement_map,
    required_declaration_fields,
    APPLICABLE,
    NOT_APPLICABLE,
    APPLICABILITY_UNKNOWN,
)
def _min_numeral_height_mm(pdp_area_cm2: float, rule: dict) -> Optional[float]:
    threshold = rule.get("threshold", {})
    bands = threshold.get("min_height_bands_mm", [])
    for band in bands:
        maximum = band.get("pdp_area_cm2_max")
        if maximum is None or pdp_area_cm2 <= float(maximum):
            return float(band["min_numeral_height_mm"])
    return None


def _evaluate_font_height(
    *,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    pdp_area_cm2: Optional[float],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    rule = _find_rule(rules, "LMPC-2011-R7-2-FONT", "LMPC-2011-R7-2")
    if rule is None:
        return [], []

    if pdp_area_cm2 is None:
        reason = "PDP area is unavailable, so the applicable font-height threshold cannot be selected."
        return [
            _make_fact(
                field="mrp_numeral_height",
                extraction=extractions.get("mrp"),
                status=FactStatus.UNCERTAIN,
                rule=rule,
                reason=reason,
                review_required=True,
                measurement_mode=MeasurementMode.UNCERTAIN,
            )
        ], [
            _finding(
                rule=rule,
                status=FactStatus.UNCERTAIN,
                reason=reason,
                missing_evidence=["calibrated_pdp_area_cm2"],
                confidence=0.0,
                review_required=True,
            )
        ]

    minimum = _min_numeral_height_mm(float(pdp_area_cm2), rule)
    if minimum is None:
        reason = "No applicable PDP-area threshold was found in the loaded rule data."
        return [
            _make_fact(
                field="mrp_numeral_height",
                extraction=extractions.get("mrp"),
                status=FactStatus.UNCERTAIN,
                rule=rule,
                reason=reason,
                review_required=True,
                measurement_mode=MeasurementMode.UNCERTAIN,
            )
        ], [
            _finding(rule=rule, status=FactStatus.UNCERTAIN, reason=reason,
                     confidence=0.0, review_required=True)
        ]

    extraction = extractions.get("mrp")
    if extraction is None or extraction.measured_height_mm is None:
        reason = (
            "No declaration-height measurement was captured. The engine will "
            "not infer millimetres from an uncalibrated image."
        )
        return [
            _make_fact(
                field="mrp_numeral_height",
                extraction=extraction,
                status=FactStatus.UNCERTAIN,
                rule=rule,
                reason=reason,
                review_required=True,
                measurement_mode=MeasurementMode.UNCERTAIN,
            )
        ], [
            _finding(
                rule=rule,
                status=FactStatus.UNCERTAIN,
                reason=reason,
                missing_evidence=["measured_declaration_height_mm"],
                confidence=0.0,
                review_required=True,
            )
        ]

    mode = extraction.measurement_mode
    measured = float(extraction.measured_height_mm)

    if mode != MeasurementMode.VERIFIED:
        reason = (
            f"Measured height is {measured:.3f} mm, but the measurement mode "
            f"is {mode.value}. A non-verified measurement cannot produce a "
            "definitive legal PASS/FAIL."
        )
        status = FactStatus.UNCERTAIN
    elif measured >= minimum:
        reason = f"Verified height {measured:.3f} mm meets required minimum {minimum:.3f} mm."
        status = FactStatus.PASS
    else:
        reason = f"Verified height {measured:.3f} mm is below required minimum {minimum:.3f} mm."
        status = FactStatus.FAIL

    fact = _make_fact(
        field="mrp_numeral_height",
        extraction=extraction,
        status=status,
        rule=rule,
        reason=reason,
        review_required=status != FactStatus.PASS,
        measurement_mode=mode,
        measured_value=measured,
        measured_unit="mm",
    )

    return [fact], [
        _finding(
            rule=rule,
            status=status,
            reason=reason,
            evidence=fact.evidence,
            confidence=fact.confidence if mode == MeasurementMode.VERIFIED else 0.0,
            review_required=status != FactStatus.PASS,
            fact=fact,
        )
    ]


def _evaluate_unit_sale_price(
    *,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    net_quantity_value: Optional[float],
    net_quantity_unit: Optional[str],
    mrp: Optional[float],
    sale_type: str,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    package_structure: Any = PackageStructure.SINGLE_UNIT,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    rule = _find_rule(
        rules,
        "LMPC-2011-R6-11-UNIT-PRICE",
        "LMPC-2011-R12",
    )
    if rule is None or mrp is None:
        return [], []

    pkg_struct_str = str(
        package_structure.value if hasattr(package_structure, "value") else package_structure
    ).upper()

    # Wholesale packages follow a different declaration path. Do not run the
    # retail unit-price check over them.
    if sale_type.lower() == "wholesale" or pkg_struct_str == "WHOLESALE_PACKAGE":
        reason = "Unit-sale-price check is not applied to wholesale packages per Rule 24 / Rule 6(11)."
        fact = _make_fact(
            field="unit_sale_price",
            extraction=extractions.get("unit_sale_price"),
            status=FactStatus.EXEMPT,
            rule=rule,
            reason=reason,
            review_required=False,
            confidence_override=1.0,
        )
        return [fact], [
            _finding(rule=rule, status=FactStatus.EXEMPT, reason=reason, confidence=1.0)
        ]

    # Multi-piece / combination / group packages require constituent item basis
    if pkg_struct_str in ("COMBINATION_PACKAGE", "GROUP_PACKAGE", "MULTI_PIECE_PACKAGE"):
        extraction = extractions.get("unit_sale_price")
        if not _has_value(extraction):
            reason = (
                f"Package structure is '{pkg_struct_str}'. Unit sale price depends on constituent commodity "
                "declarations or piece breakdown. Human review required per Rule 6(11) multi-piece provisions."
            )
            fact = _make_fact(
                field="unit_sale_price",
                extraction=None,
                status=FactStatus.UNCERTAIN,
                rule=rule,
                reason=reason,
                review_required=True,
            )
            return [fact], [
                _finding(
                    rule=rule,
                    status=FactStatus.UNCERTAIN,
                    reason=reason,
                    missing_evidence=["constituent_piece_breakdown"],
                    confidence=0.0,
                    review_required=True,
                )
            ]

    if pkg_struct_str == "UNKNOWN":
        extraction = extractions.get("unit_sale_price")
        if not _has_value(extraction):
            reason = (
                "Package structure is UNKNOWN. Unit sale price applicability depends on package type "
                "(single unit vs multi-piece/wholesale). Human review required to confirm packaging classification."
            )
            fact = _make_fact(
                field="unit_sale_price",
                extraction=None,
                status=FactStatus.UNCERTAIN,
                rule=rule,
                reason=reason,
                review_required=True,
            )
            return [fact], [
                _finding(
                    rule=rule,
                    status=FactStatus.UNCERTAIN,
                    reason=reason,
                    missing_evidence=["package_structure_determination"],
                    confidence=0.0,
                    review_required=True,
                )
            ]


    # THE MRP SIDE OF THE SAME PROBLEM.
    #
    # `mrp` arrives as a plain float from the caller, but it originates in an OCR
    # reading, and `extractions['mrp']` is that reading. The unit-price check is
    # the only place in this module where the MRP becomes an ARITHMETIC INPUT
    # rather than a presence observation: it is the numerator of the expected
    # value. So a weak MRP corrupts `expected` even when the declared unit price
    # itself was read perfectly, and the mismatch branch below would blame the
    # package for the extractor's error.
    #
    # MEASURED. Dataset image 3 produced mrp numeric 11.68 at confidence 0.24
    # from 'tein 11.68 gins' — the protein row of the nutrition panel.
    #
    # Checked deliberately BEFORE `compute_unit_sale_price` so no expected value
    # is ever derived from a number this weak, and reported as UNCERTAIN with
    # review rather than PASS.
    mrp_extraction = extractions.get("mrp")
    if (
        mrp_extraction is not None
        and mrp_extraction.confidence < low_confidence_threshold
    ):
        reason = (
            f"The MRP used to calculate the expected unit sale price was read "
            f"with confidence {mrp_extraction.confidence:.2f}, below the "
            f"{low_confidence_threshold:.2f} threshold. The expected unit price "
            "is therefore not calculated, because an unreliable MRP would make "
            "any comparison meaningless and could contradict a correctly printed "
            "unit price. Confirm the MRP before assessing Rule 6(11)."
        )
        fact = _make_fact(
            field="unit_sale_price",
            extraction=extractions.get("unit_sale_price"),
            status=FactStatus.UNCERTAIN,
            rule=rule,
            reason=reason,
            review_required=True,
        )
        return [fact], [
            _finding(
                rule=rule,
                status=FactStatus.UNCERTAIN,
                reason=reason,
                missing_evidence=["valid_mrp"],
                confidence=mrp_extraction.confidence,
                review_required=True,
            )
        ]

    # Rule 6(11) is arithmetic on the net quantity, and its own exception —
    # no declaration is required where the pack contains exactly one standard
    # unit — is also a function of that quantity. With the quantity unestablished
    # neither can be evaluated.
    #
    # `compute_unit_sale_price` does not raise on a None quantity; it returns a
    # result carrying `declaration_required=True`. So the except-branch below
    # never fired and execution fell through, asserting that the declaration IS
    # required on the strength of a quantity nobody had read. It errs toward more
    # obligation rather than less, so it produced no false FAIL, but it is still
    # an applicability decision made on absent evidence. The honest answer is
    # UNCERTAIN, naming the quantity as the missing evidence.
    if not exemption_module.quantity_is_established(net_quantity_value,
                                                    net_quantity_unit):
        reason = (
            "The unit sale price could not be assessed because the net quantity "
            "was not established. Whether Rule 6(11) requires a unit-sale-price "
            "declaration at all depends on that quantity, so neither the "
            "requirement nor its exception has been decided."
        )
        fact = _make_fact(
            field="unit_sale_price",
            extraction=extractions.get("unit_sale_price"),
            status=FactStatus.UNCERTAIN,
            rule=rule,
            reason=reason,
            review_required=True,
        )
        return [fact], [
            _finding(
                rule=rule,
                status=FactStatus.UNCERTAIN,
                reason=reason,
                missing_evidence=["valid_net_quantity"],
                confidence=0.0,
                review_required=True,
            )
        ]

    try:
        calculation = compute_unit_sale_price(
            net_quantity_value,
            net_quantity_unit,
            mrp,
        )
    except (TypeError, ValueError, InvalidOperation, ZeroDivisionError) as exc:
        reason = f"Unit-sale-price calculation could not be completed: {exc}"
        fact = _make_fact(
            field="unit_sale_price",
            extraction=extractions.get("unit_sale_price"),
            status=FactStatus.UNCERTAIN,
            rule=rule,
            reason=reason,
            review_required=True,
        )
        return [fact], [
            _finding(
                rule=rule,
                status=FactStatus.UNCERTAIN,
                reason=reason,
                missing_evidence=["valid_net_quantity", "valid_mrp"],
                confidence=0.0,
                review_required=True,
            )
        ]

    if not getattr(calculation, "declaration_required", True):
        reason = getattr(calculation, "reason", "Unit sale price declaration is not required.")
        fact = _make_fact(
            field="unit_sale_price",
            extraction=extractions.get("unit_sale_price"),
            status=FactStatus.EXEMPT,
            rule=rule,
            reason=reason,
            review_required=False,
            confidence_override=1.0,
        )
        return [fact], [
            _finding(rule=rule, status=FactStatus.EXEMPT, reason=reason, confidence=1.0)
        ]

    extraction = extractions.get("unit_sale_price")
    if not _has_value(extraction):
        # Absence is FAIL only if the inspection had enough evidence to search
        # the relevant declaration area. At this layer, lack of a capture
        # coverage signal means uncertainty is safer.
        reason = (
            f"Unit sale price is required ({getattr(calculation, 'reason', '')}) "
            "but no declared value was supplied by OCR/CV."
        )
        fact = _make_fact(
            field="unit_sale_price",
            extraction=None,
            status=FactStatus.UNCERTAIN,
            rule=rule,
            reason=reason + " Confirm package evidence before treating it as absent.",
            review_required=True,
        )
        return [fact], [
            _finding(
                rule=rule,
                status=FactStatus.UNCERTAIN,
                reason=fact.reason,
                missing_evidence=["field:unit_sale_price"],
                confidence=0.0,
                review_required=True,
            )
        ]

    # Numeric extraction is required for a numerical correctness conclusion.
    if extraction.numeric_value is None or not extraction.numeric_unit:
        reason = (
            "Unit-sale-price text is present, but OCR/CV did not provide a "
            "structured numeric value and unit. Presence alone is not enough "
            "to verify the mathematical declaration."
        )
        fact = _make_fact(
            field="unit_sale_price",
            extraction=extraction,
            status=FactStatus.UNCERTAIN,
            rule=rule,
            reason=reason,
            review_required=True,
        )
        return [fact], [
            _finding(
                rule=rule,
                status=FactStatus.UNCERTAIN,
                reason=reason,
                evidence=fact.evidence,
                confidence=extraction.confidence,
                review_required=True,
            )
        ]

    # A NUMBER THE READER COULD BARELY SEE IS NOT A DECLARED AMOUNT.
    #
    # "Low OCR confidence must NEVER itself become legal non-compliance." The
    # declaration path already honours `low_confidence_threshold` (see the
    # `_is_low_confidence` branch above), but this arithmetic path did not: it
    # fell straight through to the equality test below, whose mismatch branch is
    # an unconditional FAIL. `extraction.confidence` was only ever *reported* in
    # the finding, never allowed to affect the verdict.
    #
    # MEASURED, NOT HYPOTHETICAL. On `images dataset` image 3 the extractor
    # returned unit_sale_price numeric 573.18 at confidence 0.31 from the line
    # 'Crates 573.18 op' — a CARBOHYDRATE mass out of the nutrition panel, whose
    # unit OCR had garbled beyond recognition — and mrp numeric 11.68 at
    # confidence 0.24 from 'tein 11.68 gins', a PROTEIN mass. Two such numbers
    # will essentially never satisfy the equality test, so the pre-fix engine
    # would have announced a Rule 6(11) FAIL on the strength of a reading it
    # could not read.
    #
    # WHY THE GATE BELONGS HERE AS WELL AS IN EXTRACTION. Extraction is being
    # tightened separately, but the deterministic engine is the component that
    # actually issues the verdict, and it must not be able to convict on weak
    # evidence regardless of which extractor feeds it. Defence in depth is
    # appropriate for the one operation in this module that can turn a misread
    # digit into a legal accusation.
    #
    # UNCERTAIN, NOT PASS. This deliberately does not exonerate the package
    # either: the finding is UNCERTAIN with review_required, so a genuinely wrong
    # unit price still reaches a human instead of being waved through.
    if extraction.confidence < low_confidence_threshold:
        reason = (
            f"Declared unit-sale-price text was read with confidence "
            f"{extraction.confidence:.2f}, below the {low_confidence_threshold:.2f} "
            "threshold required to treat a number as a declared amount. The "
            "arithmetic check is not performed, because a low-confidence reading "
            "cannot establish either agreement or disagreement with the "
            "calculated value. Re-capture the unit-price declaration or confirm "
            "it manually."
        )
        fact = _make_fact(
            field="unit_sale_price",
            extraction=extraction,
            status=FactStatus.UNCERTAIN,
            rule=rule,
            reason=reason,
            review_required=True,
        )
        return [fact], [
            _finding(
                rule=rule,
                status=FactStatus.UNCERTAIN,
                reason=reason,
                evidence=fact.evidence,
                confidence=extraction.confidence,
                review_required=True,
            )
        ]

    # BOTH SIDES MUST BE IN THE SAME UNIT. See the docstring of
    # `expected_unit_price_in_declared_unit` for the measured false-FAIL bug this
    # replaces: the expected value used to come from `calculation.unit_sale_price`,
    # which is per the Rule 6(11) DISPLAY unit (per gram for a 100 g pack), while
    # the declared value was scaled up to per kg — so a correctly declared
    # sub-kilogram package was compared as 500.00 against 0.50 and failed.
    #
    # The expected figure is now derived in the unit the package itself declares,
    # with a single division and a single rounding, so the comparison below is
    # between two like quantities.
    expected_in_declared_unit = expected_unit_price_in_declared_unit(
        net_quantity_value,
        net_quantity_unit,
        mrp,
        extraction.numeric_unit,
    )

    if expected_in_declared_unit is None:
        reason = (
            f"Declared unit '{extraction.numeric_unit}' cannot be compared "
            f"against a net quantity of {net_quantity_value} "
            f"{net_quantity_unit}: the unit is either unrecognized or belongs to "
            "a different quantity family, and no mass/volume conversion is ever "
            "assumed. The arithmetic check is not performed."
        )
        fact = _make_fact(
            field="unit_sale_price",
            extraction=extraction,
            status=FactStatus.UNCERTAIN,
            rule=rule,
            reason=reason,
            review_required=True,
        )
        return [fact], [
            _finding(rule=rule, status=FactStatus.UNCERTAIN, reason=reason,
                     evidence=fact.evidence, confidence=extraction.confidence,
                     review_required=True)
        ]

    # The legal declaration is rounded to two decimal places. Compare against
    # the legally rounded expected value rather than adding an arbitrary 2%
    # tolerance. A 2% tolerance can incorrectly accept materially wrong prices.
    expected_rounded = expected_in_declared_unit.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    declared_rounded = Decimal(str(extraction.numeric_value)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    unit_label = extraction.numeric_unit

    if declared_rounded == expected_rounded:
        status = FactStatus.PASS
        reason = (
            f"Declared unit price {declared_rounded} per {unit_label} matches the "
            f"deterministically calculated value {expected_rounded} per "
            f"{unit_label} after prescribed two-decimal rounding."
        )
        review = False
    else:
        status = FactStatus.FAIL
        reason = (
            f"Declared unit price {declared_rounded} per {unit_label} does not "
            f"match the calculated value {expected_rounded} per {unit_label} "
            "after two-decimal rounding."
        )
        review = True

    fact = _make_fact(
        field="unit_sale_price",
        extraction=extraction,
        status=status,
        rule=rule,
        reason=reason,
        review_required=review,
    )

    return [fact], [
        _finding(
            rule=rule,
            status=status,
            reason=reason,
            evidence=fact.evidence,
            confidence=extraction.confidence,
            review_required=review,
            fact=fact,
        )
    ]


def _evaluate_placement(
    *,
    rules: Mapping[str, dict],
    captures: Sequence[SurfaceObservation],
    extractions: Mapping[str, RawExtraction],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    rule = _find_rule(rules, "LMPC-2011-R8-PLACEMENT", "LMPC-2011-R8")
    if rule is None:
        return [], []

    if not captures:
        reason = (
            "No surface observations are available. Placement on the principal "
            "display panel cannot be established."
        )
        return [
            _make_fact(
                field="declaration_placement",
                extraction=None,
                status=FactStatus.UNCERTAIN,
                rule=rule,
                reason=reason,
                review_required=True,
            )
        ], [
            _finding(
                rule=rule,
                status=FactStatus.UNCERTAIN,
                reason=reason,
                missing_evidence=["declaration_bboxes", "pdp_boundary"],
                confidence=0.0,
                review_required=True,
            )
        ]

    # We intentionally do not require every declaration to share one rectangular
    # visual block. The legal test is represented as PDP presence plus the
    # specific quantity-declaration clearance checks where measurable.
    missing_pdp = [c.surface_id for c in captures if c.pdp_bbox is None]
    if len(missing_pdp) == len(captures):
        reason = (
            "Package surfaces were captured, but no PDP boundary was supplied. "
            "The engine cannot establish declaration placement from surface "
            "orientation alone."
        )
        status = FactStatus.UNCERTAIN
        confidence = 0.0
    else:
        reason = (
            "PDP evidence is available for at least one captured surface. "
            "Specific declaration-to-PDP placement still depends on declaration "
            "bounding boxes supplied by OCR/CV."
        )
        status = FactStatus.PASS
        confidence = 0.75

    fact = _make_fact(
        field="declaration_placement",
        extraction=None,
        status=status,
        rule=rule,
        reason=reason,
        review_required=status == FactStatus.UNCERTAIN,
        confidence_override=confidence,
    )

    return [fact], [
        _finding(
            rule=rule,
            status=status,
            reason=reason,
            missing_evidence=["pdp_boundary"] if status == FactStatus.UNCERTAIN else [],
            confidence=confidence,
            review_required=status == FactStatus.UNCERTAIN,
            fact=fact,
        )
    ]


def _evaluate_rule4_multipack(
    *,
    rules: Mapping[str, dict],
    retail_bundle_count: Optional[int],
    captures: Sequence[SurfaceObservation],
    extractions: Mapping[str, RawExtraction],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 4 — multi-piece, combination, or group packages.
    """
    rule = _find_rule(rules, "LMPC-2011-R4-MULTIPACK")
    if rule is None:
        return [], []

    is_multipack = retail_bundle_count is not None and retail_bundle_count > 1
    if not is_multipack:
        return [], []

    # Retail package containing multiple inner packages
    inner_labels_ext = extractions.get("inner_package_labels")
    if inner_labels_ext is not None and _has_value(inner_labels_ext):
        status = FactStatus.PASS
        reason = (
            f"Multi-pack bundle contains {retail_bundle_count} pieces; inner package "
            "declarations are evidenced."
        )
        review = False
    else:
        status = FactStatus.UNCERTAIN
        reason = (
            f"Multi-pack bundle contains {retail_bundle_count} pieces. Inner package "
            "declarations are not observed or package interior is not visible. "
            "Verification required."
        )
        review = True

    fact = _make_fact(
        field="multipack_inner_declarations",
        extraction=inner_labels_ext,
        status=status,
        rule=rule,
        reason=reason,
        review_required=review,
    )
    return [fact], [
        _finding(
            rule=rule,
            status=status,
            reason=reason,
            missing_evidence=["inner_package_labels"] if status == FactStatus.UNCERTAIN else [],
            confidence=fact.confidence,
            review_required=review,
            requirement_id="multipack.inner_declarations",
            fact=fact,
        )
    ]


def _evaluate_rule5_standard_pack(
    *,
    rules: Mapping[str, dict],
    product_category: str,
    #: Currently unused by this evaluator: Rule 5 / Second Schedule membership is
    #: not yet implemented (LMPC-2011-R5-STANDARD-PACK carries a null threshold in
    #: rules.json), so the outcome is driven by category and the non-standard-pack
    #: declaration alone. Kept in the signature because a real Second Schedule
    #: check is a function of exactly this quantity, and Optional because it may
    #: legitimately be unestablished when it arrives.
    net_quantity_value: Optional[float],
    net_quantity_unit: Optional[str],
    extractions: Mapping[str, RawExtraction],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 5 & Second Schedule — Standard package quantities.
    """
    rule5 = _find_rule(rules, "LMPC-2011-R5-STANDARD-PACK")
    sched2 = _find_rule(rules, "LMPC-2011-SCHEDULE-II")
    target_rule = rule5 or sched2
    if target_rule is None:
        return [], []

    # Check if standard_pack_size declaration is evidenced (e.g. 17 mL standard pack / print marking)
    std_pack_decl = extractions.get("standard_pack_size")
    if std_pack_decl is not None and _has_value(std_pack_decl):
        status = FactStatus.PASS
        val_str = str(std_pack_decl.value)
        reason = f"Standard pack size / container capacity of '{val_str}' declared and verified under Rule 5 / Second Schedule."
        review = False
        fact = _make_fact(
            field="standard_pack_size",
            extraction=std_pack_decl,
            status=status,
            rule=target_rule,
            reason=reason,
            review_required=review,
        )
        return [fact], [
            _finding(
                rule=target_rule,
                status=status,
                reason=reason,
                confidence=std_pack_decl.confidence,
                review_required=review,
                requirement_id="standard_pack_size",
                fact=fact,
            )
        ]

    norm_cat = product_category.strip().lower()
    nonstandard_decl = extractions.get("nonstandard_pack_declaration")
    if nonstandard_decl is not None and _has_value(nonstandard_decl):
        status = FactStatus.PASS
        reason = "Prominent non-standard pack size declaration is evidenced."
        review = False
        fact = _make_fact(
            field="standard_pack_size",
            extraction=nonstandard_decl,
            status=status,
            rule=target_rule,
            reason=reason,
            review_required=review,
        )
        return [fact], [
            _finding(
                rule=target_rule,
                status=status,
                reason=reason,
                confidence=fact.confidence,
                review_required=review,
                requirement_id="standard_pack_size",
                fact=fact,
            )
        ]

    # For general commodities not asserted to be in Second Schedule:
    # Schedule membership is uncertain unless specified.
    status = FactStatus.UNCERTAIN
    reason = (
        f"Second Schedule standard quantity applicability for '{product_category}' "
        "requires verification against the current consolidated Second Schedule."
    )
    fact = _make_fact(
        field="standard_pack_size",
        extraction=extractions.get("net_quantity"),
        status=status,
        rule=target_rule,
        reason=reason,
        review_required=True,
    )
    return [fact], [
        _finding(
            rule=target_rule,
            status=status,
            reason=reason,
            confidence=0.0,
            review_required=True,
            missing_evidence=["second_schedule_membership"],
            requirement_id="standard_pack_size",
            fact=fact,
        )
    ]


def _evaluate_rule25_export_package(
    *,
    rules: Mapping[str, dict],
    sale_type: str,
    is_export_only: bool,
    extractions: Mapping[str, RawExtraction],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 25 — Export packages sold domestically in India.
    """
    rule = _find_rule(rules, "LMPC-2011-R25-EXPORT")
    if rule is None:
        return [], []

    # Only triggers when package is designated for export but offered in domestic channels
    if not (is_export_only and sale_type.lower() in {"retail", "wholesale", "ecommerce"}):
        return [], []

    repack_ext = extractions.get("repack_or_relabel_evidence")
    if repack_ext is not None and _has_value(repack_ext):
        status = FactStatus.PASS
        reason = "Export package sold in India carries verified repack/relabel compliance declarations."
        review = False
    else:
        status = FactStatus.FAIL
        reason = (
            "Export package is offered for domestic sale in India without verified "
            "re-packing or relabelling per Rule 25."
        )
        review = True

    fact = _make_fact(
        field="repack_or_relabel_before_india_sale",
        extraction=repack_ext,
        status=status,
        rule=rule,
        reason=reason,
        review_required=review,
    )
    return [fact], [
        _finding(
            rule=rule,
            status=status,
            reason=reason,
            missing_evidence=["repack_or_relabel_evidence"] if status == FactStatus.FAIL else [],
            confidence=fact.confidence if status == FactStatus.PASS else 1.0,
            review_required=review,
            requirement_id="repack_or_relabel_before_india_sale",
            fact=fact,
        )
    ]


def _evaluate_rule26_bc_exemptions(
    *,
    rules: Mapping[str, dict],
    product_category: str,
    context: Mapping[str, Any],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 26(b) Fast Food and Rule 26(c) Drug Formulation exemptions.
    """
    facts: List[ExtractedFact] = []
    findings: List[RuleFinding] = []
    norm_cat = product_category.strip().lower()

    if norm_cat in {"fast_food", "restaurant_pack", "hotel_pack"}:
        r26b = _find_rule(rules, "LMPC-2011-R26-B-FAST-FOOD")
        if r26b:
            is_hotel_packed = bool(context.get("packed_by_restaurant_or_hotel"))
            if is_hotel_packed:
                status = FactStatus.EXEMPT
                reason = "Fast food item packed by restaurant/hotel is exempt under Rule 26(b)."
                review = False
            else:
                status = FactStatus.UNCERTAIN
                reason = "Product category is fast food, but packer establishment type requires verification."
                review = True

            fact = _make_fact(
                field="fast_food_exemption",
                extraction=None,
                status=status,
                rule=r26b,
                reason=reason,
                review_required=review,
                confidence_override=1.0 if status == FactStatus.EXEMPT else 0.0,
            )
            facts.append(fact)
            findings.append(_finding(
                rule=r26b,
                status=status,
                reason=reason,
                confidence=fact.confidence,
                review_required=review,
                requirement_id="fast_food_exemption",
                fact=fact,
            ))

    if norm_cat in {"drug", "drug_formulation", "pharmaceutical"}:
        r26c = _find_rule(rules, "LMPC-2011-R26-C-DRUG-FORMULATIONS")
        if r26c:
            covered_by_dpco = bool(context.get("covered_by_drug_price_control"))
            if covered_by_dpco:
                status = FactStatus.EXEMPT
                reason = "Drug formulation covered by Drug Price Control Order is exempt under Rule 26(c)."
                review = False
            else:
                status = FactStatus.UNCERTAIN
                reason = "Drug formulation price-control coverage requires regulatory verification."
                review = True

            fact = _make_fact(
                field="drug_formulation_exemption",
                extraction=None,
                status=status,
                rule=r26c,
                reason=reason,
                review_required=review,
                confidence_override=1.0 if status == FactStatus.EXEMPT else 0.0,
            )
            facts.append(fact)
            findings.append(_finding(
                rule=r26c,
                status=status,
                reason=reason,
                confidence=fact.confidence,
                review_required=review,
                requirement_id="drug_formulation_exemption",
                fact=fact,
            ))

    return facts, findings


def _evaluate_rule27_registration(
    *,
    rules: Mapping[str, dict],
    context: Mapping[str, Any],
    extractions: Mapping[str, RawExtraction],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 27 — Manufacturer/Packer/Importer registration reference.
    """
    rule = _find_rule(rules, "LMPC-2011-R27-REGISTRATION")
    if rule is None:
        return [], []

    reg_ext = extractions.get("registration_number")
    if reg_ext is not None and _has_value(reg_ext):
        status = FactStatus.PASS
        reason = f"Entity registration reference '{reg_ext.value}' is evidenced."
        review = False
    elif context.get("check_registration"):
        status = FactStatus.UNCERTAIN
        reason = "Registration reference is not evidenced in the package observation dataset."
        review = True
    else:
        # Rule 27 registration check is not in package inspection scope unless requested
        return [], []

    fact = _make_fact(
        field="registration_number",
        extraction=reg_ext,
        status=status,
        rule=rule,
        reason=reason,
        review_required=review,
    )
    return [fact], [
        _finding(
            rule=rule,
            status=status,
            reason=reason,
            confidence=fact.confidence,
            review_required=review,
            requirement_id="manufacturer_packer_importer_registration",
            fact=fact,
        )
    ]


def _evaluate_rule31_advertisement(
    *,
    rules: Mapping[str, dict],
    sale_type: str,
    extractions: Mapping[str, RawExtraction],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 31 — Advertisement mentioning retail sale price must also declare net quantity.
    """
    rule = _find_rule(rules, "LMPC-2011-R31-ADVERTISEMENT")
    if rule is None:
        return [], []

    # Applies when inspecting ecommerce or advertisement media mentioning price
    if sale_type.lower() not in {"ecommerce", "advertisement"}:
        return [], []

    mrp_ext = extractions.get("mrp")
    qty_ext = extractions.get("net_quantity")

    if mrp_ext and _has_value(mrp_ext):
        if qty_ext and _has_value(qty_ext):
            status = FactStatus.PASS
            reason = "E-commerce/advertisement listing displays both retail price and net quantity."
            review = False
        else:
            status = FactStatus.FAIL
            reason = "E-commerce/advertisement displays retail price without mandatory net quantity declaration."
            review = True

        fact = _make_fact(
            field="advertisement_net_quantity",
            extraction=qty_ext,
            status=status,
            rule=rule,
            reason=reason,
            review_required=review,
        )
        return [fact], [
            _finding(
                rule=rule,
                status=status,
                reason=reason,
                missing_evidence=["net_quantity"] if status == FactStatus.FAIL else [],
                confidence=fact.confidence,
                review_required=review,
                requirement_id="advertisement_net_quantity",
                fact=fact,
            )
        ]

    return [], []


def _infer_pdp_area_from_captures(
    captures: Sequence[SurfaceObservation],
    shape: GeometryType,
) -> Optional[float]:
    """
    Optional PDP area inference using calibration.measure_pdp_area().
    Only infers when a calibrated capture with a PDP bbox is present.
    """
    for c in captures:
        if c.calibration and c.calibration.available and c.pdp_bbox:
            pdp_geom = calib.PDPGeometry(
                source_image=c.image_id,
                bbox=c.pdp_bbox,
            )
            measurement = calib.measure_pdp_area(pdp_geom, shape or c.geometry, c.calibration)
            if measurement.value is not None and measurement.value > 0:
                return measurement.value
    return None


def _infer_numeral_height_from_captures(
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
) -> None:
    """
    Optional numeral height inference for MRP bounding box if calibrated.
    Updates measured_height_mm and measurement_mode in place if not already set.
    """
    mrp_ext = extractions.get("mrp")
    if mrp_ext is None or mrp_ext.measured_height_mm is not None:
        return

    bbox = _bbox_from_any(mrp_ext.bbox)
    if bbox is None:
        return

    for c in captures:
        if c.calibration and c.calibration.available:
            measurements = calib.measure_bbox(bbox, c.calibration, source_image=c.image_id)
            # measurements[1] is region_height
            height_m = measurements[1]
            if height_m.value is not None:
                mrp_ext.measured_height_mm = height_m.value
                mrp_ext.measurement_mode = height_m.status
                break




__all__ = [
    '_min_numeral_height_mm', '_evaluate_font_height', '_evaluate_unit_sale_price',
    '_evaluate_placement', '_evaluate_rule4_multipack', '_evaluate_rule5_standard_pack',
    '_evaluate_rule25_export_package', '_evaluate_rule26_bc_exemptions',
    '_evaluate_rule27_registration', '_evaluate_rule31_advertisement',
    '_infer_pdp_area_from_captures', '_infer_numeral_height_from_captures'
]
