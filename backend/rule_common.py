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

    # How well the independent readings of THIS field agreed with one another.
    #
    # The OCR engine already computes this per observation and records the
    # competing readings, but the value used to stop at the OCR boundary: the
    # adapter from classified fields to this contract had nowhere to put it. A
    # field the engine had read as both "Rs. 50.00" and "Rs. 90.00" therefore
    # reached the legal evaluation looking exactly like an undisputed reading,
    # and could produce a definitive PASS.
    #
    # SINGLE_SOURCE is the default because it is the honest description of a
    # lone reading with no cross-check: it asserts no corroboration and reports
    # no conflict. It is NOT a claim that the readings agreed.
    agreement: EvidenceAgreement = EvidenceAgreement.SINGLE_SOURCE

    # The competing readings, when `agreement` is CONFLICTING. Kept so that a
    # reviewer is shown what the disagreement actually was instead of merely
    # being told one exists — the same reason evidence carries a bbox rather
    # than the word "somewhere".
    alternative_values: Optional[List[str]] = None

    # THE LABEL, SEPARATE FROM THE VALUE.
    #
    # `ocr_extraction.classify_fields()` distinguishes the printed caption
    # ("M.R.P.", "USE BY") from the datum beside it, because a caption proves a
    # declaration was ATTEMPTED while saying nothing about whether its value is
    # present or readable. That distinction is the whole basis of the
    # PARTIALLY_DETECTED outcome: "the pack says MRP but we could not read the
    # amount" is a materially different report to a reviewer than "no MRP
    # anywhere on the pack", and only one of them can ever justify an absence
    # finding.
    #
    # The distinction previously stopped at this boundary. `classify_fields`
    # computed `label`, `status` and `reason`; `build_raw_extraction` did not
    # forward them; every downstream `getattr(ext, "label", None)` therefore
    # returned None in production, so the PARTIALLY_DETECTED branch was
    # unreachable and label-only observations were indistinguishable from
    # nothing-observed. Same class of defect as the dropped bbox: a value
    # computed correctly upstream with nowhere to land.
    label: Optional[str] = None

    # The extractor's own account of WHY this reading is in the state it is in
    # ("label matched but no adjacent value line"). Carried so the explanation
    # shown to a reviewer is the one the extractor actually formed, rather than
    # a generic sentence reconstructed after the fact.
    reason: Optional[str] = None

    # `classify_fields`' own status string (e.g. "DETECTED",
    # "REVIEW_REQUIRED"). Deliberately NOT named `status`: this is the
    detection_status: Optional[str] = None
    source: Optional[str] = None

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if self.raw_text is None:
            self.raw_text = self.value
        # Accept a plain string from an upstream layer without letting an
        # unrecognised one quietly become "no conflict".
        self.agreement = coerce_evidence_agreement(self.agreement)


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

    # An extraction that carries a region but no provenance is a defect in the
    # caller, not a legitimate state. It is recorded with an unmistakable
    # sentinel rather than the old "unknown", which was indistinguishable from a
    # real filename once persisted, and the note says plainly that the chain is
    # incomplete. Callers should supply `evidence` built by
    # `capture_session.build_raw_extraction()`, which stamps the real image id.
    return [
        EvidenceReference(
            image_id=UNATTRIBUTED_IMAGE_ID,
            bbox=bbox,
            evidence_note=(
                "Region supplied by OCR/CV extraction, but no source image was "
                "recorded for this observation. Provenance is incomplete and "
                "this finding cannot be shown to a reviewer in context."
            ),
        )
    ]


def _human_field_name(field: str) -> str:
    """Format raw field identifier into clear, formal, natural text without raw snake_case."""
    mapping = {
        "common_name": "Generic / Product Name",
        "product_name": "Product Name",
        "product_id": "Product ID / SKU",
        "mrp": "Maximum Retail Price (MRP)",
        "net_quantity": "Net Quantity",
        "unit_sale_price": "Unit Sale Price",
        "batch_no": "Batch / Lot Number",
        "mfg_date": "Date of Manufacture",
        "best_before_use_by": "Best Before / Expiry Date",
        "manufacturer_name_address": "Manufacturer Name & Address",
        "manufacturer_name": "Manufacturer Name & Address",
        "marketer_name": "Marketer Name & Address",
        "consumer_care": "Consumer Care Details",
        "country_of_origin": "Country of Origin",
        "standard_pack_size": "Standard Pack Size",
    }
    if field in mapping:
        return mapping[field]
    return field.replace("_", " ").title()


def agreement_cap(
    extraction: Optional[RawExtraction],
    status: FactStatus,
    reason: str,
) -> tuple[FactStatus, str, bool]:
    """
    Refuse a definitive verdict when the readings of that field disagreed.

    Invariant 4: "CONFLICTING evidence cannot automatically produce a definitive
    compliance finding." Two readings of the same pixels that cannot both be
    true mean we do not yet know what the package declares. That is a reason to
    ask a human, and never in itself a reason to pass or fail a package.

    Returns `(status, reason, review_required)`. Only PASS and FAIL are capped,
    and only ever downgraded to UNCERTAIN:

      - PASS is capped because a conflicted reading is not proof of a compliant
        declaration.
      - FAIL is capped for the more important reason. "UNCERTAIN evidence must
        NEVER directly become FAIL": accusing a package of a legal breach on the
        strength of a reading the pipeline itself could not settle is the worst
        available outcome, worse than the false PASS.
      - UNCERTAIN, EXEMPT and anything else are returned untouched. Nothing here
        may ever raise a status; a cap that could promote a verdict would be a
        route to manufacturing certainty.

    EXEMPT is deliberately left alone: exemption follows from product category
    and context, not from the disputed value of a declaration, so a conflicted
    reading of one field is not evidence about the exemption. Where an exemption
    does depend on a value, invariant 9's review state carries that separately.

    Kept as a module-level function, not a private helper, so the tests can
    address the rule directly rather than only through a full inspection.
    """
    if extraction is None:
        return status, reason, False

    agreement = coerce_evidence_agreement(extraction.agreement)
    if agreement.permits_definitive_finding():
        return status, reason, False

    if status not in (FactStatus.PASS, FactStatus.FAIL):
        return status, reason, False

    if agreement == EvidenceAgreement.CONFLICTING:
        detail = (
            f"Independent readings of '{extraction.field}' disagreed, so its "
            "declared value is not established."
        )
        alternatives = [str(a) for a in (extraction.alternative_values or []) if str(a).strip()]
        if alternatives:
            readings = ", ".join(
                repr(v) for v in ([str(extraction.value)] if extraction.value else []) + alternatives
            )
            detail = (
                f"Independent readings of '{extraction.field}' disagreed "
                f"({readings}), so its declared value is not established."
            )
    else:
        detail = (
            f"Whether the readings of '{extraction.field}' agreed could not be "
            "determined, so its declared value is not established."
        )

    withheld = (
        f" A {status.value} finding was withheld: conflicting extraction evidence "
        "cannot decide legal compliance either way. A reviewer must resolve the "
        "reading before this requirement can be assessed."
    )

    return FactStatus.UNCERTAIN, f"{detail}{withheld} Original assessment: {reason}", True


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
    # Applied here rather than at each evaluator because every fact in the
    # system is built through this function, so the invariant holds for
    # evaluators not yet written. The low-confidence check by contrast is
    # repeated at roughly ten call sites, which is exactly how a rule like this
    # comes to be enforced in nine places and forgotten in the tenth.
    status, reason, conflict_review = agreement_cap(extraction, status, reason)
    review_required = review_required or conflict_review

    confidence = (
        confidence_override
        if confidence_override is not None
        else (extraction.confidence if extraction else 0.0)
    )

    evidence_refs = (
        evidence if evidence is not None else _evidence_for_extraction(extraction)
    )

    # Keep the fact's top-level pointers consistent with its evidence list.
    # `evidence_image` used to be hardcoded to None even when the evidence
    # carried a perfectly good image id, which meant the field that reviewers
    # and the report layer read first was always empty. The first ATTRIBUTED
    # reference wins: an unattributed sentinel must not be copied up here, or it
    # would look like a real image name at the top level of the fact.
    primary = next((ref for ref in evidence_refs if ref.is_attributed()), None)

    fact_bbox = _bbox_from_any(extraction.bbox) if extraction else None
    if fact_bbox is None and primary is not None:
        fact_bbox = primary.bbox

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
        evidence_image=primary.image_id if primary is not None else None,
        bbox=fact_bbox,
        evidence=evidence_refs,
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
    fact: Optional[ExtractedFact] = None,
) -> RuleFinding:
    """
    Build a rule finding.

    When `fact` is supplied, the finding's status, reason and review flag are
    taken FROM the fact rather than from the caller's local variables. This
    matters because `_make_fact` may downgrade a definitive verdict — see
    `agreement_cap` — and the evaluators compute `status` once and then pass it
    to both constructors. Without this, a capped fact would sit next to a
    finding still claiming PASS: a split verdict for the same requirement, which
    is worse than either answer alone, because the report renders findings while
    the reviewer queue reads facts.

    `fact` is not merely accepted here, it is required at every call site that
    has one; `tests/test_agreement_cap.py` walks this module's syntax tree and
    fails if a new `_finding(...)` call is added without it.
    """
    if fact is not None:
        status = fact.status
        reason = fact.reason
        review_required = review_required or fact.review_required

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




__all__ = [
    'RULES_PATH', 'DEFAULT_LOW_CONFIDENCE_THRESHOLD', 'RawExtraction', 'load_rules',
    '_find_rule', '_rule_status', '_bbox_from_any', '_evidence_for_extraction',
    '_human_field_name', 'agreement_cap', '_make_fact', '_finding', '_is_low_confidence',
    '_has_value', '_inspection_coverage', '_evidence_sufficient_for_missing_field',
    '_field_requirements', 'APPLICABLE', 'NOT_APPLICABLE', 'APPLICABILITY_UNKNOWN',
    'condition_applicability', '_condition_is_applicable', '_build_requirement_map',
    'required_declaration_fields', '_CONDITION_CONTEXT_KEYS', '_CONDITION_DEFAULTS'
]
