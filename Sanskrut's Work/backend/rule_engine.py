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
    EvidenceReference,
    FactStatus,
    ExtractedFact,
    GeometryType,
    MeasurementMode,
    ProductInspection,
    RuleFinding,
    SurfaceObservation,
)

from exemption import ExemptionInput, classify_exemption
from unit_price import (
    compute_unit_sale_price,
    convert_declared_price_to_standard,
    expected_unit_price_in_declared_unit,
)


RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "rules.json"
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.55


@dataclass
class RawExtraction:
    """
    Compatibility adapter for OCR/CV output.

    OCR/CV should progressively populate:
      - value/raw_text
      - confidence
      - numeric_value/numeric_unit
      - bbox
      - evidence
      - measured_height_mm + measurement_mode

    The rule engine never performs OCR or fuzzy text extraction.
    """

    field: str
    value: Optional[str]
    confidence: float
    bbox: Optional[Any] = None
    measured_height_mm: Optional[float] = None
    measurement_mode: MeasurementMode = MeasurementMode.UNCERTAIN
    numeric_value: Optional[float] = None
    numeric_unit: Optional[str] = None
    raw_text: Optional[str] = None
    normalized_value: Optional[str] = None
    evidence: Optional[List[EvidenceReference]] = None
    evidence_complete: bool = True

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if self.raw_text is None:
            self.raw_text = self.value


def load_rules(path: Path = RULES_PATH) -> Dict[str, dict]:
    """Load the machine-readable legal rule dataset."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise ValueError("rules.json must contain a top-level 'rules' array")

    rules: Dict[str, dict] = {}
    for rule in data["rules"]:
        rule_id = rule.get("rule_id")
        if not rule_id:
            raise ValueError("Every legal rule must have a rule_id")
        if rule_id in rules:
            raise ValueError(f"Duplicate rule_id in rules.json: {rule_id}")
        rules[rule_id] = rule
    return rules


def _find_rule(rules: Mapping[str, dict], *rule_ids: str) -> Optional[dict]:
    for rule_id in rule_ids:
        if rule_id in rules:
            return rules[rule_id]
    return None


def _rule_status(rule: Optional[dict]) -> Optional[str]:
    if not rule:
        return None
    return rule.get("verification_status")


def _bbox_from_any(value: Any) -> Optional[BBox]:
    if value is None:
        return None
    if isinstance(value, BBox):
        return value
    if isinstance(value, Mapping):
        try:
            return BBox(
                x=float(value["x"]),
                y=float(value["y"]),
                width=float(value["width"]),
                height=float(value["height"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) == 4:
            try:
                return BBox(
                    x=float(value[0]),
                    y=float(value[1]),
                    width=float(value[2]),
                    height=float(value[3]),
                )
            except (TypeError, ValueError):
                return None
    return None


def _evidence_for_extraction(extraction: Optional[RawExtraction]) -> List[EvidenceReference]:
    if extraction is None:
        return []

    if extraction.evidence:
        return extraction.evidence

    bbox = _bbox_from_any(extraction.bbox)
    if bbox is None:
        return []

    return [
        EvidenceReference(
            image_id="unknown",
            bbox=bbox,
            evidence_note="Evidence supplied by OCR/CV extraction."
        )
    ]


def _make_fact(
    *,
    field: str,
    extraction: Optional[RawExtraction],
    status: FactStatus,
    rule: Optional[dict],
    reason: str,
    review_required: bool,
    extracted_value: Optional[str] = None,
    measurement_mode: Optional[MeasurementMode] = None,
    measured_value: Optional[float] = None,
    measured_unit: Optional[str] = None,
    evidence: Optional[List[EvidenceReference]] = None,
    confidence_override: Optional[float] = None,
) -> ExtractedFact:
    confidence = (
        confidence_override
        if confidence_override is not None
        else (extraction.confidence if extraction else 0.0)
    )

    return ExtractedFact(
        field=field,
        extracted_value=(
            extracted_value
            if extracted_value is not None
            else (extraction.value if extraction else None)
        ),
        status=status,
        confidence=max(0.0, min(1.0, float(confidence))),
        rule_id=rule.get("rule_id") if rule else None,
        rule_version=rule.get("version") if rule else None,
        evidence_image=None,
        bbox=_bbox_from_any(extraction.bbox) if extraction else None,
        evidence=evidence if evidence is not None else _evidence_for_extraction(extraction),
        measurement_mode=measurement_mode,
        measured_value=measured_value,
        measured_unit=measured_unit,
        raw_text=extraction.raw_text if extraction else None,
        normalized_value=extraction.normalized_value if extraction else None,
        reason=reason,
        review_required=review_required,
        extraction_confidence=extraction.confidence if extraction else None,
        decision_confidence=confidence,
    )


def _finding(
    *,
    rule: dict,
    status: FactStatus,
    reason: str,
    evidence: Optional[List[EvidenceReference]] = None,
    missing_evidence: Optional[List[str]] = None,
    requirement_id: Optional[str] = None,
    requirement_description: Optional[str] = None,
    confidence: float = 0.0,
    review_required: bool = False,
) -> RuleFinding:
    return RuleFinding(
        rule_id=rule["rule_id"],
        rule_version=rule.get("version"),
        status=status,
        requirement_id=requirement_id,
        requirement_description=requirement_description,
        reason=reason,
        evidence=evidence or [],
        required_evidence=rule.get("evidence_required", []),
        missing_evidence=missing_evidence or [],
        confidence=max(0.0, min(1.0, confidence)),
        review_required=review_required,
        verification_status=rule.get("verification_status"),
    )


def _is_low_confidence(extraction: Optional[RawExtraction], threshold: float) -> bool:
    return extraction is None or extraction.confidence < threshold


def _has_value(extraction: Optional[RawExtraction]) -> bool:
    return bool(extraction and extraction.value and str(extraction.value).strip())


def _inspection_coverage(captures: Sequence[SurfaceObservation]) -> float:
    if not captures:
        return 0.0
    # Multiple captures are evidence observations. We use the strongest observed
    # coverage rather than summing percentages, because overlapping photos should
    # not magically create >100% evidence.
    return max(float(c.evidence_coverage) for c in captures)


def _evidence_sufficient_for_missing_field(
    captures: Sequence[SurfaceObservation],
    *,
    required_coverage: float = 0.70,
) -> bool:
    """
    Conservative absence rule.

    A declaration can be called FAIL for absence only when the available
    observations provide substantial package evidence. Otherwise the result is
    UNCERTAIN because "not seen" is not equivalent to "not present".
    """
    if not captures:
        return False

    usable = [
        c for c in captures
        if c.image_quality.status.value in {"USABLE", "PARTIAL"}
    ]
    if not usable:
        return False

    return _inspection_coverage(usable) >= required_coverage


def _field_requirements(rule: dict) -> List[dict]:
    return list(rule.get("requirements", []))


#: Condition string in rules.json -> the context key that decides it.
#: A condition that is NOT in this table is not understood by this engine
#: version, and its applicability is UNKNOWN rather than assumed either way.
_CONDITION_CONTEXT_KEYS: Dict[str, str] = {
    "imported_product": "is_imported",
    "commodity_dimensions_are_relevant": "dimensions_relevant",
    "commodity_may_become_unfit_for_human_consumption": "best_before_applicable",
    "rule_6_subrule_11_applies": "unit_price_rule_applies",
    "pan_masala": "is_pan_masala",
    "tobacco_or_tobacco_product": "is_tobacco",
    "package_is_within_the_partial_relaxation_range": (
        "small_pack_relaxation_applies"
    ),
}

#: Conditions whose absence from the context has a default DECLARED BY THIS
#: ENGINE'S OWN PUBLIC API, and which may therefore be resolved without a guess.
#: Each entry mirrors the corresponding `run_inspection()` keyword default, and
#: the two must be kept in step — `test_condition_defaults_match_the_public_api`
#: fails if they drift.
#:
#: The distinction being drawn is deliberate. A default is legitimate when the
#: engine publishes it as part of its contract, so a caller who omits the flag is
#: accepting a documented answer. A default is NOT legitimate when it is invented
#: at the point of use. `pan_masala`, `tobacco_or_tobacco_product` and
#: `package_is_within_the_partial_relaxation_range` appear in rules.json but have
#: no `run_inspection` parameter and therefore no published default, so this
#: engine refuses to assume them in either direction.
#:
#: RESIDUAL RISK, STATED PLAINLY: because `best_before_applicable` defaults to
#: False, a caller that forgets the flag on a perishable commodity will not have
#: the best-before declaration checked. That is a caller responsibility inherited
#: from the existing public signature, not something this table introduced, and
#: it errs toward UNCERTAIN/no-finding rather than toward a false FAIL.
_CONDITION_DEFAULTS: Dict[str, bool] = {
    "imported_product": False,                              # is_imported=False
    "commodity_dimensions_are_relevant": False,             # dimensions_relevant=False
    "commodity_may_become_unfit_for_human_consumption": False,  # best_before_applicable=False
    "rule_6_subrule_11_applies": True,   # Rule 6(11) applies unless narrowed
}

APPLICABLE = "APPLICABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"
APPLICABILITY_UNKNOWN = "APPLICABILITY_UNKNOWN"


def condition_applicability(
    requirement: Mapping[str, Any], context: Mapping[str, Any]
) -> str:
    """
    Whether a conditional requirement applies: APPLICABLE, NOT_APPLICABLE, or
    APPLICABILITY_UNKNOWN.

    WHY THIS IS A TRI-STATE AND NOT A BOOLEAN
    -----------------------------------------
    This function used to end in a bare `return True`, so any condition string
    the engine did not recognise was treated as unconditionally applicable. That
    is a legal-safety bug in the one direction the design forbids: an
    unrecognised condition made a declaration MANDATORY for a package it never
    applied to, and once package coverage was sufficient that absence hardened
    into FAIL. Verified before fixing — a requirement conditioned on
    `tobacco_or_tobacco_product` was returned as mandatory for a package whose
    context said nothing about tobacco.

    Returning False instead would trade a false FAIL for a false PASS: the
    requirement would be silently dropped and never evaluated at all. Neither
    guess is honest, so the third answer is explicit. An UNKNOWN requirement is
    still evaluated and still reported, but its absence can only ever produce
    UNCERTAIN, never FAIL. "Never average. Never silently choose."

    A condition is only decided when it is recognised by this engine version AND
    either resolvable from the supplied context or covered by a default this
    engine publishes in `run_inspection()` (see `_CONDITION_DEFAULTS`). A
    recognised condition with neither is UNKNOWN, because a caller that forgot to
    pass `is_tobacco` must not thereby get a silent pass on a mandatory tobacco
    warning.
    """
    condition = requirement.get("condition")
    if not condition:
        return APPLICABLE
    if not isinstance(condition, str):
        # A structured condition object is a rules.json feature this engine
        # version does not interpret. Unknown, not assumed.
        return APPLICABILITY_UNKNOWN

    key = _CONDITION_CONTEXT_KEYS.get(condition)
    if key is None:
        return APPLICABILITY_UNKNOWN

    if key in context:
        return APPLICABLE if bool(context.get(key)) else NOT_APPLICABLE
    if condition in _CONDITION_DEFAULTS:
        return APPLICABLE if _CONDITION_DEFAULTS[condition] else NOT_APPLICABLE
    return APPLICABILITY_UNKNOWN


def _condition_is_applicable(requirement: dict, context: Mapping[str, Any]) -> bool:
    """
    Backward-compatible boolean view: is this requirement in scope at all?

    UNKNOWN counts as in-scope so the requirement is still evaluated and
    reported. What UNKNOWN changes is the WORST status it may reach, which is
    enforced in `_evaluate_declaration_rule`, not here.
    """
    return condition_applicability(requirement, context) != NOT_APPLICABLE


def _build_requirement_map(rule: dict, context: Mapping[str, Any]) -> Dict[str, dict]:
    """
    Applicable requirements, keyed by field name.

    Requirements whose applicability could not be determined are INCLUDED and
    tagged with `_applicability_uncertain`, so they are still evidenced and
    still reported, but cannot be failed for absence. The tag is written onto a
    shallow COPY — `load_rules()` hands back the parsed rules.json objects, and
    mutating them would let one inspection's context leak into the next.
    """
    result: Dict[str, dict] = {}
    for req in _field_requirements(rule):
        field = req.get("field")
        if not field:
            continue
        applicability = condition_applicability(req, context)
        if applicability == NOT_APPLICABLE:
            continue
        if applicability == APPLICABILITY_UNKNOWN:
            req = {**req, "_applicability_uncertain": True}
        result[field] = req
    return result


def required_declaration_fields(
    rules: Mapping[str, dict],
    sale_type: str,
    context: Mapping[str, Any],
) -> List[str]:
    """
    Public helper: the list of mandatory-declaration field names applicable
    right now, given sale_type and applicability context (is_imported,
    best_before_applicable, etc.).

    Used by the multi-surface capture-session layer to compute genuine
    evidence coverage (how many of the *actually applicable* declarations
    have been evidenced across all captures so far) rather than guessing.
    Returns [] if the corresponding rule record is not present.
    """
    if sale_type.lower() == "wholesale":
        rule = _find_rule(rules, "LMPC-2011-R24-WHOLESALE")
    else:
        rule = _find_rule(rules, "LMPC-2011-R6-DECLARATIONS", "LMPC-2011-R6")

    if rule is None:
        return []

    return list(_build_requirement_map(rule, context).keys())


def _evaluate_declaration_rule(
    *,
    rule: dict,
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Generic mandatory-declaration evaluator.

    Shared by Rule 6 (retail mandatory declarations) and Rule 24 (wholesale
    package declarations) — both rules have the same shape in rules.json:
    a list of {id, field, description} requirements that must each be
    evidenced, with conservative FAIL-only-when-evidence-is-sufficient
    semantics for absence.
    """

    facts: List[ExtractedFact] = []
    findings: List[RuleFinding] = []
    requirements = _build_requirement_map(rule, context)

    for field, req in requirements.items():
        extraction = extractions.get(field)

        if _has_value(extraction):
            if extraction.confidence < low_confidence_threshold:
                status = FactStatus.UNCERTAIN
                reason = (
                    f"'{field}' was detected, but extraction confidence "
                    f"{extraction.confidence:.2f} is below the configured "
                    f"threshold {low_confidence_threshold:.2f}."
                )
                review = True
            else:
                status = FactStatus.PASS
                reason = f"'{field}' is evidenced by the OCR/CV pipeline."
                review = False

            fact = _make_fact(
                field=field,
                extraction=extraction,
                status=status,
                rule=rule,
                reason=reason,
                review_required=review,
            )
            facts.append(fact)
            findings.append(_finding(
                rule=rule,
                status=status,
                reason=reason,
                evidence=fact.evidence,
                requirement_id=req.get("id"),
                requirement_description=req.get("description"),
                confidence=fact.confidence,
                review_required=review,
            ))
            continue

        if req.get("_applicability_uncertain"):
            # This engine version could not determine whether the requirement
            # applies to this package (unrecognised condition, or a context key
            # the caller never supplied). An undetermined requirement must never
            # be failed for absence — that would accuse a package of breaching a
            # declaration that may not apply to it at all.
            status = FactStatus.UNCERTAIN
            reason = (
                f"Required declaration '{field}' was not observed, and whether "
                f"it applies to this package could not be determined from "
                f"condition '{req.get('condition')}'. Absence cannot be "
                "assessed until applicability is resolved by a reviewer."
            )
        elif _evidence_sufficient_for_missing_field(captures):
            status = FactStatus.FAIL
            reason = (
                f"Required declaration '{field}' was not evidenced after "
                "sufficient package coverage."
            )
        else:
            status = FactStatus.UNCERTAIN
            reason = (
                f"Required declaration '{field}' was not observed, but the "
                "available package evidence is insufficient to conclude that "
                "the declaration is absent."
            )

        fact = _make_fact(
            field=field,
            extraction=None,
            status=status,
            rule=rule,
            reason=reason,
            review_required=True,
            confidence_override=1.0 if status == FactStatus.FAIL else 0.0,
        )
        facts.append(fact)
        findings.append(_finding(
            rule=rule,
            status=status,
            reason=reason,
            missing_evidence=[f"field:{field}"],
            requirement_id=req.get("id"),
            requirement_description=req.get("description"),
            confidence=fact.confidence,
            review_required=True,
        ))

    return facts, findings


def _evaluate_rule6_declarations(
    *,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    rule = _find_rule(rules, "LMPC-2011-R6-DECLARATIONS", "LMPC-2011-R6")
    if rule is None:
        raise ValueError("rules.json does not contain a Rule 6 declaration record")

    return _evaluate_declaration_rule(
        rule=rule,
        extractions=extractions,
        captures=captures,
        context=context,
        low_confidence_threshold=low_confidence_threshold,
    )


def _evaluate_rule24_wholesale_declarations(
    *,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 24 — wholesale package declarations.

    Applies only when sale_type == "wholesale". Uses the same evidence-first,
    conservative-absence logic as Rule 6. Requirement fields per rules.json:
    manufacturer_name_address, common_name, wholesale_count_or_net_quantity.

    Note: 'wholesale_count_or_net_quantity' is not produced by the current
    OCR field classifier (ocr_extraction.py only emits 'net_quantity'). Until
    that alias/extraction is added, this requirement will correctly surface
    as UNCERTAIN (insufficient evidence) rather than a fabricated PASS/FAIL.
    """
    rule = _find_rule(rules, "LMPC-2011-R24-WHOLESALE")
    if rule is None:
        # Rule not present in this rules.json build — skip rather than crash,
        # but do not silently claim wholesale compliance.
        return [], []

    return _evaluate_declaration_rule(
        rule=rule,
        extractions=extractions,
        captures=captures,
        context=context,
        low_confidence_threshold=low_confidence_threshold,
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
        )
    ]


def _evaluate_unit_sale_price(
    *,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    net_quantity_value: float,
    net_quantity_unit: str,
    mrp: Optional[float],
    sale_type: str,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    rule = _find_rule(
        rules,
        "LMPC-2011-R6-11-UNIT-PRICE",
        "LMPC-2011-R12",
    )
    if rule is None or mrp is None:
        return [], []

    # Wholesale packages follow a different declaration path. Do not run the
    # retail unit-price check over them.
    if sale_type.lower() == "wholesale":
        reason = "Retail unit-sale-price check is not applied to wholesale packages."
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
        )
    ]


def _aggregate_status(facts: Iterable[ExtractedFact]) -> FactStatus:
    statuses = [fact.status for fact in facts]
    if not statuses:
        return FactStatus.UNCERTAIN

    if FactStatus.FAIL in statuses:
        return FactStatus.FAIL
    if FactStatus.UNCERTAIN in statuses:
        return FactStatus.UNCERTAIN
    if all(status == FactStatus.EXEMPT for status in statuses):
        return FactStatus.EXEMPT
    return FactStatus.PASS


def _summary(
    facts: Sequence[ExtractedFact],
    findings: Sequence[RuleFinding],
    captures: Sequence[SurfaceObservation],
) -> Dict[str, Any]:
    counts = {
        FactStatus.PASS: 0,
        FactStatus.FAIL: 0,
        FactStatus.UNCERTAIN: 0,
        FactStatus.EXEMPT: 0,
    }
    for finding in findings:
        counts[finding.status] += 1

    review_count = sum(
        1 for finding in findings if finding.review_required
    )

    coverage = _inspection_coverage(captures)
    evidence_complete = (
        bool(captures)
        and coverage >= 0.70
        and all(
            c.image_quality.status.value in {"USABLE", "PARTIAL"}
            for c in captures
        )
    )

    return {
        "total_rules_evaluated": len(findings),
        "passed": counts[FactStatus.PASS],
        "failed": counts[FactStatus.FAIL],
        "uncertain": counts[FactStatus.UNCERTAIN],
        "exempt": counts[FactStatus.EXEMPT],
        "review_required": review_count,
        "evidence_complete": evidence_complete,
        "coverage_score": coverage,
    }


def run_inspection(
    inspection_id: str,
    sale_type: str,
    product_category: str,
    net_quantity_value: float,
    net_quantity_unit: str,
    mrp: Optional[float],
    extractions: Dict[str, RawExtraction],
    pdp_area_cm2: Optional[float] = None,
    is_export_only: bool = False,
    retail_bundle_count: Optional[int] = None,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    sticker_suspects: Optional[List[Any]] = None,
    captures: Optional[List[SurfaceObservation]] = None,
    is_imported: bool = False,
    dimensions_relevant: bool = False,
    best_before_applicable: bool = False,
    geometry: GeometryType = GeometryType.UNKNOWN,
) -> ProductInspection:
    """
    Main inspection entry point.

    Backward-compatible with the original prototype while adding:
      - multi-surface captures
      - evidence-aware absence handling
      - rule-level findings
      - versioned rule references
      - correct Rule 6(11) unit-price handling
    """

    if not 0.0 <= low_confidence_threshold <= 1.0:
        raise ValueError("low_confidence_threshold must be between 0 and 1")

    if net_quantity_value is None or float(net_quantity_value) <= 0:
        raise ValueError("net_quantity_value must be greater than zero")

    captures = captures or []
    rules = load_rules()
    facts: List[ExtractedFact] = []
    findings: List[RuleFinding] = []

    # ------------------------------------------------------------------
    # 1. Scope / exemption comes first.
    # ------------------------------------------------------------------
    exemption = classify_exemption(ExemptionInput(
        sale_type=sale_type,
        net_quantity_value=net_quantity_value,
        net_quantity_unit=net_quantity_unit,
        product_category=product_category,
        is_export_only=is_export_only,
        retail_bundle_count=retail_bundle_count,
    ))

    if exemption.is_exempt:
        scope_rule = _find_rule(
            rules,
            exemption.rule_id,
            "LMPC-2011-R3-SCOPE",
        )
        scope_fact = _make_fact(
            field="__scope__",
            extraction=None,
            status=FactStatus.EXEMPT,
            rule=scope_rule,
            reason=exemption.reason,
            review_required=False,
            confidence_override=1.0,
        )
        facts.append(scope_fact)

        if scope_rule:
            findings.append(_finding(
                rule=scope_rule,
                status=FactStatus.EXEMPT,
                reason=exemption.reason,
                confidence=1.0,
                review_required=False,
            ))

        return ProductInspection(
            inspection_id=inspection_id,
            product_category=product_category,
            sale_type=sale_type,
            package_weight_or_volume=net_quantity_value,
            package_weight_unit=net_quantity_unit,
            geometry=geometry,
            captures=captures,
            facts=facts,
            findings=findings,
            overall_status=FactStatus.EXEMPT,
            exempt_reason=exemption.reason,
            evidence_complete=bool(captures),
            review_required=False,
        )

    # ------------------------------------------------------------------
    # 2. Build contextual applicability facts.
    # ------------------------------------------------------------------
    context = {
        "is_imported": is_imported,
        "dimensions_relevant": dimensions_relevant,
        "best_before_applicable": best_before_applicable,
        "unit_price_rule_applies": True,
    }

    # ------------------------------------------------------------------
    # 3. Rule 6 mandatory declarations.
    # ------------------------------------------------------------------
    if sale_type.lower() == "retail":
        r6_facts, r6_findings = _evaluate_rule6_declarations(
            rules=rules,
            extractions=extractions,
            captures=captures,
            context=context,
            low_confidence_threshold=low_confidence_threshold,
        )
        facts.extend(r6_facts)
        findings.extend(r6_findings)

    # ------------------------------------------------------------------
    # 3b. Rule 24 wholesale package declarations.
    # ------------------------------------------------------------------
    if sale_type.lower() == "wholesale":
        r24_facts, r24_findings = _evaluate_rule24_wholesale_declarations(
            rules=rules,
            extractions=extractions,
            captures=captures,
            context=context,
            low_confidence_threshold=low_confidence_threshold,
        )
        facts.extend(r24_facts)
        findings.extend(r24_findings)

    # ------------------------------------------------------------------
    # 4. Rule 7 font height / PDP evidence.
    # ------------------------------------------------------------------
    if sale_type.lower() == "retail":
        r7_facts, r7_findings = _evaluate_font_height(
            rules=rules,
            extractions=extractions,
            pdp_area_cm2=pdp_area_cm2,
        )
        facts.extend(r7_facts)
        findings.extend(r7_findings)

    # ------------------------------------------------------------------
    # 5. Rule 6(11) unit sale price.
    # ------------------------------------------------------------------
    if sale_type.lower() == "retail":
        usp_facts, usp_findings = _evaluate_unit_sale_price(
            rules=rules,
            extractions=extractions,
            net_quantity_value=net_quantity_value,
            net_quantity_unit=net_quantity_unit,
            mrp=mrp,
            sale_type=sale_type,
            low_confidence_threshold=low_confidence_threshold,
        )
        facts.extend(usp_facts)
        findings.extend(usp_findings)

    # ------------------------------------------------------------------
    # 6. Rule 8 placement.
    # ------------------------------------------------------------------
    if sale_type.lower() == "retail":
        placement_facts, placement_findings = _evaluate_placement(
            rules=rules,
            captures=captures,
            extractions=extractions,
        )
        facts.extend(placement_facts)
        findings.extend(placement_findings)

    # ------------------------------------------------------------------
    # 7. Advisory sticker/alteration evidence.
    # ------------------------------------------------------------------
    if sticker_suspects:
        for region in sticker_suspects:
            bbox = getattr(region, "bbox", None)
            confidence = float(getattr(region, "confidence", 0.0))
            reason = str(getattr(region, "reason", "possible alteration"))
            facts.append(ExtractedFact(
                field="__possible_alteration__",
                extracted_value=str(bbox),
                status=FactStatus.UNCERTAIN,
                confidence=max(0.0, min(1.0, confidence)),
                rule_id=None,
                reason=(
                    "Vision heuristic flagged a possible sticker/alteration "
                    f"region ({reason}). This is advisory evidence only."
                ),
                review_required=True,
            ))

    # ------------------------------------------------------------------
    # 8. Final status and summary.
    # ------------------------------------------------------------------
    overall = _aggregate_status(facts)
    summary_data = _summary(facts, findings, captures)

    return ProductInspection(
        inspection_id=inspection_id,
        product_category=product_category,
        sale_type=sale_type,
        package_weight_or_volume=net_quantity_value,
        package_weight_unit=net_quantity_unit,
        geometry=geometry,
        captures=captures,
        facts=facts,
        findings=findings,
        overall_status=overall,
        summary=summary_data,
        evidence_complete=summary_data["evidence_complete"],
        review_required=(
            summary_data["review_required"] > 0
            or overall == FactStatus.UNCERTAIN
        ),
    )
