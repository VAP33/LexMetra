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

import datetime as _dt
import json
import re
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

try:
    from engine.conditions import Tri, evaluate_condition
    from engine.evidence import Evidence, EvidenceValue
except ImportError:
    try:
        from backend.engine.conditions import Tri, evaluate_condition
        from backend.engine.evidence import Evidence, EvidenceValue
    except ImportError:
        Tri = None
        evaluate_condition = None
        Evidence = None
        EvidenceValue = None


_local_rules = Path(__file__).resolve().parent / "rules" / "rules.json"
_parent_rules = Path(__file__).resolve().parent.parent / "rules" / "rules.json"
RULES_PATH = _local_rules if _local_rules.exists() else _parent_rules
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
    #: Additional units named in the same declaration alongside `numeric_unit`
    #: (e.g. a label printed "per kg or litre" to cover more than one SKU
    #: variant on a shared template). The rule engine -- never the extractor
    #: -- decides which alternative, if any, is applicable to THIS package's
    #: quantity family and Rule 6(11) display-unit band. `None`/empty means
    #: only one unit was named.
    numeric_unit_alternatives: Optional[List[str]] = None
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
    # EXTRACTOR's opinion about readability, never a legal status. The rule
    # engine decides compliance; this field only reports what the reader saw.
    detection_status: Optional[str] = None

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


#: rule-level ``status`` values that mean "not part of current runtime
#: evaluation", regardless of what effective_from/effective_to happen to say.
#: A rule that has been omitted/repealed by a later amendment may not have
#: had its effective_to backfilled precisely yet, so this is checked
#: independently of the date filter below, not instead of it.
_INACTIVE_RULE_STATUSES = {"superseded", "repealed", "withdrawn", "omitted", "inactive"}


def _parse_rule_date(value: Any) -> Optional["_dt.date"]:
    if value in (None, ""):
        return None
    if isinstance(value, _dt.date):
        return value
    try:
        return _dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def filter_active_rules(
    rules: Mapping[str, dict],
    as_of: "_dt.date",
) -> Dict[str, dict]:
    """
    Return only the rules that are ACTUALLY part of current runtime
    evaluation as of ``as_of``: this is a GENERIC, data-driven filter over
    every rule's own ``status``/``effective_from``/``effective_to`` metadata
    in rules.json -- it does not name, special-case, or hard-code any
    specific rule_id, regulation clause, or product category.

    A rule is excluded when:
      - its ``status`` is one of ``_INACTIVE_RULE_STATUSES`` (e.g. a
        Second-Schedule-style provision omitted by a later amendment), or
      - its ``effective_from`` is in the future relative to ``as_of``
        (a rule must not execute prematurely), or
      - its ``effective_to`` is on or before ``as_of`` (a rule that has
        lapsed/been superseded must not execute after that date).

    This is the ONLY place that decides whether a catalogue rule
    participates in an *undated* (implicitly "as of today") inspection.
    Dated inspections additionally go through the stricter, approval-gated
    ``regulatory.runtime.apply_rule_versions`` registry (see
    ``run_inspection``), which this filter runs ahead of so that a
    rule already known to be retired never needs a RuleVersion record at
    all -- it is simply not offered up for versioned resolution either.

    Rules with neither field set are unaffected (always considered active),
    preserving today's behaviour for the majority of the catalogue that has
    no retirement/future-effective metadata yet.
    """
    active: Dict[str, dict] = {}
    for rule_id, rule in rules.items():
        status = str(rule.get("status") or "").strip().lower()
        if status in _INACTIVE_RULE_STATUSES:
            continue
        effective_from = _parse_rule_date(rule.get("effective_from"))
        if effective_from is not None and effective_from > as_of:
            continue
        effective_to = _parse_rule_date(rule.get("effective_to"))
        if effective_to is not None and effective_to <= as_of:
            continue
        active[rule_id] = rule
    return active


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
    raw = rule.get("requirements", [])
    res: List[dict] = []
    for item in raw:
        if isinstance(item, str):
            res.append({"field": item, "description": item})
        elif isinstance(item, dict):
            res.append(item)
    return res


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


#: A postal/PIN code (5-6 digits) is the single strongest, purely-structural
#: signal that an address string is a real postal address rather than just a
#: company/brand name -- it works the same way regardless of which company,
#: country, or product is on the label.
_POSTAL_CODE_PATTERN = re.compile(r"\b\d{5,6}\b")


def _name_and_address_completeness(raw_text: Optional[str]) -> str:
    """
    Generic, field-content sufficiency check for a declared
    "name and address" string (manufacturer/packer/importer, or country of
    origin context). Returns one of:

      "sufficient"    - reads like an actual postal address (multiple
                         address segments, and/or a postal code)
      "insufficient"  - reads like a bare name (optionally + country),
                         with nothing address-like at all
      "uncertain"     - has some address-like structure, but not enough to
                         be confident it is legally complete

    This is a structural heuristic over ANY text (segment count + presence
    of a postal code) -- it never references a specific company, country, or
    product, so it applies identically to every label the engine ever sees.
    Detecting presence of a company name plus a bare country name (e.g.
    "Acme Pvt Ltd, India") must NOT be treated as a complete address: that is
    exactly the gap this function closes.
    """
    if not raw_text or not raw_text.strip():
        return "insufficient"

    segments = [s.strip() for s in re.split(r"[,\n]", raw_text) if s.strip()]
    has_postal_code = bool(_POSTAL_CODE_PATTERN.search(raw_text))

    if has_postal_code:
        # A 5-6 digit postal/PIN code is, on its own, strong structural
        # evidence of a real postal address -- it is not a number that
        # appears in a bare company name or a bare country name.
        return "sufficient"
    if len(segments) <= 2:
        # e.g. "Acme Pvt Ltd" (1 segment), or "Acme Pvt Ltd, India" /
        # "Acme Pvt Ltd, Pune" (2 segments: a name and a single bare
        # city/country token, with no street/locality/postal detail).
        return "insufficient"
    return "uncertain"


def _evaluate_declaration_rule(
    *,
    rule: dict,
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
    exclude_fields: Optional[set[str]] = None,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Generic mandatory-declaration evaluator.

    Shared by Rule 6 (retail mandatory declarations) and Rule 24 (wholesale
    package declarations).
    """
    facts: List[ExtractedFact] = []
    findings: List[RuleFinding] = []
    requirements = _build_requirement_map(rule, context)
    exclude_fields = exclude_fields or set()

    for field, req in requirements.items():
        if field in exclude_fields:
            continue

        extraction = extractions.get(field)

        if _has_value(extraction):
            # Strict field value validation:
            if field == "mrp" and getattr(extraction, "numeric_value", None) is None:
                status = FactStatus.UNCERTAIN
                reason = (
                    getattr(extraction, "reason", "")
                    or f"MRP text '{extraction.value}' does not contain a verified positive monetary amount."
                )
                review = True
            elif field == "manufacturer_name_address":
                # A company name is not, by itself, "the name and address" the
                # rule requires. Presence of text plus a plausible confidence
                # score is not sufficient for THIS field the way it is for a
                # simple date or a common name -- the content itself must
                # actually look like a postal address. See
                # `_name_and_address_completeness` (a generic structural
                # check: no specific company or country is ever referenced).
                raw_for_check = (
                    getattr(extraction, "normalized_value", None)
                    or getattr(extraction, "raw_text", None)
                    or extraction.value
                )
                completeness = _name_and_address_completeness(raw_for_check)
                if completeness == "insufficient":
                    status = FactStatus.FAIL
                    reason = (
                        f"'{field}' text ('{raw_for_check}') identifies a name but does "
                        "not contain a legally sufficient address (no locality/street "
                        "detail or postal code beyond a bare country name). A company "
                        "name plus a country name alone does not satisfy the complete "
                        "name-and-address declaration requirement."
                    )
                    review = True
                elif completeness == "uncertain":
                    status = FactStatus.UNCERTAIN
                    reason = (
                        f"'{field}' text ('{raw_for_check}') contains some address-like "
                        "detail, but not enough (e.g. no postal code and few address "
                        "segments) to confirm it is a legally complete address without "
                        "review."
                    )
                    review = True
                elif extraction.confidence < low_confidence_threshold:
                    status = FactStatus.UNCERTAIN
                    reason = (
                        f"'{field}' was detected, but extraction confidence "
                        f"{extraction.confidence:.2f} is below the configured "
                        f"threshold {low_confidence_threshold:.2f}."
                    )
                    review = True
                else:
                    status = FactStatus.PASS
                    reason = (
                        f"'{field}' is evidenced by the OCR/CV pipeline and its content "
                        "structurally resembles a complete postal address (multiple "
                        "address segments and/or a postal code)."
                    )
                    review = False
            elif field in {"best_before_use_by", "mfg_date"} and getattr(extraction, "date_value", None) is None and getattr(extraction, "normalized_value", None) is None:
                status = FactStatus.UNCERTAIN
                reason = (
                    getattr(extraction, "reason", "")
                    or f"Declaration label '{extraction.value}' was detected, but no valid date value could be established."
                )
                review = True
            elif extraction.confidence < low_confidence_threshold:
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
                fact=fact,
            ))
            continue

        if extraction is not None and (getattr(extraction, "raw_text", None) or getattr(extraction, "label", None)):
            # Label was observed, but value is missing/unresolved
            status = FactStatus.UNCERTAIN
            reason = (
                getattr(extraction, "reason", "")
                or f"Declaration label for '{field}' was observed, but corresponding value was not reliably detected."
            )
            review = True
        elif req.get("_applicability_uncertain"):
            status = FactStatus.UNCERTAIN
            reason = (
                f"Required declaration '{field}' was not observed, and whether "
                f"it applies to this package could not be determined from "
                f"condition '{req.get('condition')}'. Absence cannot be "
                "assessed until applicability is resolved by a reviewer."
            )
            review = True
        elif _evidence_sufficient_for_missing_field(captures):
            status = FactStatus.FAIL
            reason = (
                f"Required declaration '{field}' was not evidenced after "
                "sufficient package coverage."
            )
            review = True
        else:
            status = FactStatus.UNCERTAIN
            reason = (
                f"Required declaration '{field}' was not observed in the provided image(s). "
                "Available package evidence is insufficient to conclude that the declaration is absent."
            )
            review = True

        fact = _make_fact(
            field=field,
            extraction=extraction if extraction else None,
            status=status,
            rule=rule,
            reason=reason,
            review_required=review,
            confidence_override=1.0 if status == FactStatus.FAIL else (extraction.confidence if extraction else 0.0),
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
            fact=fact,
        ))

    return facts, findings


def _build_evidence_bag(
    extractions: Mapping[str, RawExtraction],
    context: Mapping[str, Any],
) -> Any:
    if Evidence is None:
        return None
    ev = Evidence()
    for field, ext in extractions.items():
        if ext is None:
            continue
        val = getattr(ext, "normalized_value", None) or getattr(ext, "value", None)
        has_val = _has_value(ext)
        conf = getattr(ext, "confidence", 1.0)
        ev.set_field(field, val, confidence=conf, present=has_val)
        ev.set_field(f"declared.{field}", val, confidence=conf, present=has_val)
        if getattr(ext, "numeric_value", None) is not None:
            ev.set_field(f"{field}.numeric_value", ext.numeric_value, confidence=conf, present=True)
            ev.set_field(f"declared.{field}.numeric_value", ext.numeric_value, confidence=conf, present=True)
        if getattr(ext, "numeric_unit", None) is not None:
            ev.set_field(f"{field}.unit", ext.numeric_unit, confidence=conf, present=True)
            ev.set_field(f"declared.{field}.unit", ext.numeric_unit, confidence=conf, present=True)

    for k, v in context.items():
        ev.set_field(f"context.{k}", v, present=(v is not None))
        ev.set_field(k, v, present=(v is not None))
    return ev


def evaluate_rule(
    *,
    rule: dict,
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
    exclude_fields: Optional[set[str]] = None,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Data-driven generic rule evaluator.

    Evaluates ordinary compliance rules generically from structured rule data
    (applies_to, applicability, exemptions, requirements, and conditions).
    Specialized rules (e.g. font height, unit price math, standard pack schedules)
    are routed through SPECIALIZED_EVALUATORS rather than here.
    """
    rule_id = rule.get("rule_id", "")
    rule_type = rule.get("rule_type", "")

    # 1. Scope / Applicability gating (applies_to)
    applies_to = rule.get("applies_to") or {}
    if applies_to:
        # Check sale_type
        allowed_st = applies_to.get("sale_type")
        if allowed_st:
            if isinstance(allowed_st, str):
                allowed_st = [allowed_st]
            allowed_st_norm = [s.strip().lower() for s in allowed_st]
            if "all" not in allowed_st_norm:
                curr_st = str(context.get("sale_type", "")).strip().lower()
                if curr_st not in allowed_st_norm:
                    return [], []

        # Check product_category
        allowed_pc = applies_to.get("product_category")
        if allowed_pc:
            if isinstance(allowed_pc, str):
                allowed_pc = [allowed_pc]
            allowed_pc_norm = [c.strip().lower() for c in allowed_pc]
            if "all" not in allowed_pc_norm:
                curr_pc = str(context.get("product_category", "")).strip().lower()
                if curr_pc not in allowed_pc_norm:
                    return [], []

        # Check is_export_only
        if "is_export_only" in applies_to:
            req_export = bool(applies_to["is_export_only"])
            curr_export = bool(context.get("is_export_only"))
            if curr_export != req_export:
                return [], []

        # Check other applies_to attributes
        for attr, expected in applies_to.items():
            if attr in ("sale_type", "product_category", "is_export_only"):
                continue
            curr_val = context.get(attr)
            if curr_val is None and isinstance(context.get("custom_attributes"), dict):
                curr_val = context["custom_attributes"].get(attr)
            if curr_val is not None:
                if isinstance(expected, list):
                    if curr_val not in expected:
                        return [], []
                elif curr_val != expected:
                    return [], []
            else:
                # Specified requirement not met in context
                return [], []

    # 2. Applicability condition check
    appl_cond = rule.get("applicability")
    if isinstance(appl_cond, dict) and evaluate_condition is not None:
        ev_bag = _build_evidence_bag(extractions, context)
        try:
            res_trace = evaluate_condition(appl_cond, ev_bag, low_confidence_threshold, rule_id)
            if res_trace.result is Tri.FALSE:
                return [], []
            elif res_trace.result is Tri.UNKNOWN:
                f = _make_fact(
                    field="__applicability__",
                    extraction=None,
                    status=FactStatus.UNCERTAIN,
                    rule=rule,
                    reason=f"Applicability condition for rule '{rule_id}' could not be established from evidence.",
                    review_required=True,
                )
                return [f], [_finding(rule=rule, status=FactStatus.UNCERTAIN, reason=f.reason, review_required=True, fact=f)]
        except Exception:
            pass

    # 3. Specific rule migrations preserving exact legal logic:
    if rule_id == "LMPC-2011-R25-EXPORT":
        is_export = bool(context.get("is_export_only"))
        st = str(context.get("sale_type", "")).lower()
        if not (is_export and st in {"retail", "wholesale", "ecommerce"}):
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

    if rule_id == "LMPC-2011-R26-B-FAST-FOOD":
        norm_cat = str(context.get("product_category", "")).strip().lower()
        if norm_cat in {"fast_food", "restaurant_pack", "hotel_pack"}:
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
                rule=rule,
                reason=reason,
                review_required=review,
                confidence_override=1.0 if status == FactStatus.EXEMPT else 0.0,
            )
            return [fact], [
                _finding(
                    rule=rule,
                    status=status,
                    reason=reason,
                    confidence=fact.confidence,
                    review_required=review,
                    requirement_id="fast_food_exemption",
                    fact=fact,
                )
            ]
        return [], []

    if rule_id == "LMPC-2011-R26-C-DRUG-FORMULATIONS":
        norm_cat = str(context.get("product_category", "")).strip().lower()
        if norm_cat in {"drug", "drug_formulation", "pharmaceutical"}:
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
                rule=rule,
                reason=reason,
                review_required=review,
                confidence_override=1.0 if status == FactStatus.EXEMPT else 0.0,
            )
            return [fact], [
                _finding(
                    rule=rule,
                    status=status,
                    reason=reason,
                    confidence=fact.confidence,
                    review_required=review,
                    requirement_id="drug_formulation_exemption",
                    fact=fact,
                )
            ]
        return [], []

    if rule_id == "LMPC-2011-R27-REGISTRATION":
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

    if rule_id == "LMPC-2011-R31-ADVERTISEMENT":
        st = str(context.get("sale_type", "")).lower()
        if st not in {"ecommerce", "advertisement"}:
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

    # 4. Exemption checks from rule["exemptions"]
    exemptions = rule.get("exemptions")
    if isinstance(exemptions, dict):
        exemptions = [exemptions]
    if isinstance(exemptions, list) and evaluate_condition is not None:
        ev_bag = _build_evidence_bag(extractions, context)
        for ex in exemptions:
            cond_dict = ex.get("condition") if (isinstance(ex, dict) and "condition" in ex) else ex
            if isinstance(cond_dict, dict) and "op" in cond_dict:
                try:
                    ex_trace = evaluate_condition(cond_dict, ev_bag, low_confidence_threshold, rule_id)
                    if ex_trace.result is Tri.TRUE:
                        reason = (ex.get("description") if isinstance(ex, dict) else None) or f"Exemption '{ex.get('id', 'rule-exemption') if isinstance(ex, dict) else 'rule-exemption'}' applies."
                        f = _make_fact(
                            field="__exemption__",
                            extraction=None,
                            status=FactStatus.EXEMPT,
                            rule=rule,
                            reason=reason,
                            review_required=False,
                            confidence_override=1.0,
                        )
                        return [f], [_finding(rule=rule, status=FactStatus.EXEMPT, reason=reason, confidence=1.0, review_required=False, fact=f)]
                except Exception:
                    pass

    # 5. Field requirements evaluation
    raw_reqs = _field_requirements(rule)
    if raw_reqs:
        exclude = set(exclude_fields or set())
        if rule_id in ("LMPC-2011-R6-DECLARATIONS", "LMPC-2011-R6"):
            exclude.add("unit_sale_price")
        return _evaluate_declaration_rule(
            rule=rule,
            extractions=extractions,
            captures=captures,
            context=context,
            low_confidence_threshold=low_confidence_threshold,
            exclude_fields=exclude,
        )

    # 6. Generic declarative condition evaluation (for synthetic/data-driven rules)
    cond = rule.get("condition") or rule.get("conditions")
    if isinstance(cond, dict) and "op" in cond and evaluate_condition is not None:
        ev_bag = _build_evidence_bag(extractions, context)
        cond_trace = evaluate_condition(cond, ev_bag, low_confidence_threshold, rule_id)
        field_target = cond.get("field", rule_id)
        ext = extractions.get(field_target)

        if cond_trace.result is Tri.TRUE:
            status = FactStatus.PASS
            reason = rule.get("message_pass") or f"Condition satisfied for rule '{rule_id}'."
            review = False
        elif cond_trace.result is Tri.FALSE:
            if ext and _has_value(ext):
                status = FactStatus.FAIL
                reason = rule.get("message_fail") or f"Condition violated for rule '{rule_id}'."
                review = True
            elif _evidence_sufficient_for_missing_field(captures):
                status = FactStatus.FAIL
                reason = rule.get("message_fail") or f"Required evidence for rule '{rule_id}' is absent under sufficient coverage."
                review = True
            else:
                status = FactStatus.UNCERTAIN
                reason = f"Evidence for rule '{rule_id}' was not observed and coverage is insufficient to confirm absence."
                review = True
        else:
            status = FactStatus.UNCERTAIN
            reason = rule.get("message_uncertain") or f"Insufficient evidence to evaluate condition for rule '{rule_id}'."
            review = True

        fact = _make_fact(
            field=field_target,
            extraction=ext,
            status=status,
            rule=rule,
            reason=reason,
            review_required=review,
            confidence_override=1.0 if (status == FactStatus.FAIL and not ext) else (ext.confidence if ext else 0.0),
        )
        return [fact], [
            _finding(
                rule=rule,
                status=status,
                reason=reason,
                confidence=fact.confidence,
                review_required=review,
                missing_evidence=[field_target] if status in (FactStatus.FAIL, FactStatus.UNCERTAIN) and not ext else [],
                fact=fact,
            )
        ]

    return [], []


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

    return evaluate_rule(
        rule=rule,
        extractions=extractions,
        captures=captures,
        context=context,
        low_confidence_threshold=low_confidence_threshold,
        exclude_fields={"unit_sale_price"},
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
    """
    rule = _find_rule(rules, "LMPC-2011-R24-WHOLESALE")
    if rule is None:
        return [], []

    return evaluate_rule(
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

    # ------------------------------------------------------------------
    # Classify the evidence itself BEFORE any rule-compliance judgement.
    #
    # The engine must distinguish:
    #   A. OCR/evidence extraction failure  -> no usable number/unit at all
    #   B. Semantic parsing failure         -> a unit was named but it does
    #                                          not belong to this package's
    #                                          quantity family (mass vs volume)
    #   C. Mathematical/rule-compliance     -> wrong unit REPRESENTATION
    #      failure                             (Rule 6(11) prescribes a
    #                                          specific display unit for this
    #                                          quantity band) or wrong AMOUNT
    #   D. Genuine uncertainty              -> low-confidence reading
    #
    # A declared unit-price line may legitimately name more than one unit
    # (e.g. a shared label template printed "per kg or litre" so it covers
    # both a by-weight and a by-volume SKU); `numeric_unit_alternatives`
    # carries any additional units the extractor found alongside the primary
    # `numeric_unit`. Presence of *a* unit is therefore evaluated against
    # ALL named units, not only the first one, before concluding text was
    # present without a usable unit.
    candidate_units: List[str] = []
    if extraction.numeric_unit:
        candidate_units.append(extraction.numeric_unit)
    for alt in getattr(extraction, "numeric_unit_alternatives", None) or []:
        if alt and alt not in candidate_units:
            candidate_units.append(alt)

    # A. Genuine OCR/extraction failure: no parseable number, or no unit at
    # all could be identified from the text (not even a wrong one).
    if extraction.numeric_value is None or not candidate_units:
        reason = (
            "Unit-sale-price text is present, but OCR/CV could not identify "
            "a usable declared numeric amount and unit from it. This is an "
            "evidence/extraction gap: presence of text alone is not enough "
            "to verify the declaration."
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

    # B. Semantic parsing failure: a unit (or units) WAS identified, but none
    # of them belongs to the same quantity family (mass vs. volume vs.
    # length vs. count) as this package's net quantity. No mass<->volume
    # conversion is ever guessed, so this cannot be resolved arithmetically.
    compatible_unit = next(
        (
            u for u in candidate_units
            if expected_unit_price_in_declared_unit(
                net_quantity_value, net_quantity_unit, mrp, u
            ) is not None
        ),
        None,
    )
    if compatible_unit is None:
        named = ", ".join(candidate_units)
        reason = (
            f"Unit-sale-price text names a unit ({named}) that does not belong "
            f"to the same quantity family as the net quantity ({net_quantity_value} "
            f"{net_quantity_unit}). No mass/volume/length conversion is ever "
            "assumed, so the declaration cannot be verified arithmetically "
            "against this package."
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
                missing_evidence=["compatible_unit_sale_price_unit"],
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

    # RIGHT FAMILY: now check the AMOUNT. Rule 6(11) does not mandate one
    # single prescribed display unit for a given quantity band -- a 100 g
    # pack may lawfully declare its unit price per gram OR per kilogram (see
    # `test_a_correct_unit_price_passes_on_either_unit_basis`); what matters
    # is that the declared unit belongs to the correct quantity family (B,
    # above) and that the AMOUNT is arithmetically consistent with MRP and
    # net quantity in whichever unit was actually declared.
    #
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
        compatible_unit,
    )

    if expected_in_declared_unit is None:
        reason = (
            f"Declared unit '{compatible_unit}' cannot be compared "
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
    unit_label = compatible_unit

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

    # Check if category is a known Second Schedule commodity
    # Standard Schedule commodities include: baby food, biscuits, bread, cereals/pulses, tea, coffee, etc.
    # When schedule membership or current schedule text is unverified, safe status is UNCERTAIN or PASS if non-standard declaration is present.
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
    Delegates to evaluate_rule().
    """
    rule = _find_rule(rules, "LMPC-2011-R25-EXPORT")
    if rule is None:
        return [], []

    return evaluate_rule(
        rule=rule,
        extractions=extractions,
        captures=[],
        context={"sale_type": sale_type, "is_export_only": is_export_only},
        low_confidence_threshold=0.55,
    )


def _evaluate_rule26_bc_exemptions(
    *,
    rules: Mapping[str, dict],
    product_category: str,
    context: Mapping[str, Any],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 26(b) Fast Food and Rule 26(c) Drug Formulation exemptions.
    Delegates to evaluate_rule().
    """
    ctx = dict(context)
    ctx["product_category"] = product_category
    facts: List[ExtractedFact] = []
    findings: List[RuleFinding] = []

    r26b = _find_rule(rules, "LMPC-2011-R26-B-FAST-FOOD")
    if r26b:
        f_b, find_b = evaluate_rule(
            rule=r26b,
            extractions={},
            captures=[],
            context=ctx,
            low_confidence_threshold=0.55,
        )
        facts.extend(f_b)
        findings.extend(find_b)

    r26c = _find_rule(rules, "LMPC-2011-R26-C-DRUG-FORMULATIONS")
    if r26c:
        f_c, find_c = evaluate_rule(
            rule=r26c,
            extractions={},
            captures=[],
            context=ctx,
            low_confidence_threshold=0.55,
        )
        facts.extend(f_c)
        findings.extend(find_c)

    return facts, findings


def _evaluate_rule27_registration(
    *,
    rules: Mapping[str, dict],
    context: Mapping[str, Any],
    extractions: Mapping[str, RawExtraction],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 27 — Manufacturer/Packer/Importer registration reference.
    Delegates to evaluate_rule().
    """
    rule = _find_rule(rules, "LMPC-2011-R27-REGISTRATION")
    if rule is None:
        return [], []

    return evaluate_rule(
        rule=rule,
        extractions=extractions,
        captures=[],
        context=context,
        low_confidence_threshold=0.55,
    )


def _evaluate_rule31_advertisement(
    *,
    rules: Mapping[str, dict],
    sale_type: str,
    extractions: Mapping[str, RawExtraction],
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 31 — Advertisement mentioning retail sale price must also declare net quantity.
    Delegates to evaluate_rule().
    """
    rule = _find_rule(rules, "LMPC-2011-R31-ADVERTISEMENT")
    if rule is None:
        return [], []

    return evaluate_rule(
        rule=rule,
        extractions=extractions,
        captures=[],
        context={"sale_type": sale_type},
        low_confidence_threshold=0.55,
    )


# ---------------------------------------------------------------------------
# Specialized Evaluators Registry & Adapters
# ---------------------------------------------------------------------------
# Evaluators are retained here ONLY when they encode genuinely complex legal
# or technical calculations (e.g. geometric step functions, multi-unit tolerance
# math, statutory schedule lookups) that cannot be cleanly captured in ordinary
# declarative rule conditions.

def _evaluate_font_height_specialized(
    *,
    rule: dict,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    if context.get("sale_type", "").lower() == "retail":
        return _evaluate_font_height(
            rules=rules,
            extractions=extractions,
            pdp_area_cm2=context.get("pdp_area_cm2"),
        )
    return [], []


def _evaluate_unit_sale_price_specialized(
    *,
    rule: dict,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    if context.get("sale_type", "").lower() == "retail":
        return _evaluate_unit_sale_price(
            rules=rules,
            extractions=extractions,
            net_quantity_value=context.get("net_quantity_value"),
            net_quantity_unit=context.get("net_quantity_unit"),
            mrp=context.get("mrp"),
            sale_type=context.get("sale_type", "retail"),
            low_confidence_threshold=low_confidence_threshold,
        )
    return [], []


def _evaluate_rule5_standard_pack_specialized(
    *,
    rule: dict,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    if context.get("sale_type", "").lower() in {"retail", "wholesale"}:
        return _evaluate_rule5_standard_pack(
            rules=rules,
            product_category=context.get("product_category", ""),
            net_quantity_value=context.get("net_quantity_value"),
            net_quantity_unit=context.get("net_quantity_unit"),
            extractions=extractions,
        )
    return [], []


def _evaluate_rule4_multipack_specialized(
    *,
    rule: dict,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    bundle_count = context.get("retail_bundle_count")
    if context.get("sale_type", "").lower() == "retail" and bundle_count and bundle_count > 1:
        return _evaluate_rule4_multipack(
            rules=rules,
            retail_bundle_count=bundle_count,
            captures=captures,
            extractions=extractions,
        )
    return [], []


def _evaluate_placement_specialized(
    *,
    rule: dict,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    if context.get("sale_type", "").lower() == "retail":
        return _evaluate_placement(
            rules=rules,
            captures=captures,
            extractions=extractions,
        )
    return [], []


SPECIALIZED_EVALUATORS: Dict[str, Any] = {
    "LMPC-2011-R7-2-FONT": _evaluate_font_height_specialized,
    "LMPC-2011-R6-11-UNIT-PRICE": _evaluate_unit_sale_price_specialized,
    "LMPC-2011-R5-STANDARD-PACK": _evaluate_rule5_standard_pack_specialized,
    "LMPC-2011-R4-MULTIPACK": _evaluate_rule4_multipack_specialized,
    "LMPC-2011-R8-PLACEMENT": _evaluate_placement_specialized,
}



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
    net_quantity_value: Optional[float],
    net_quantity_unit: Optional[str],
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
    inspection_date: Optional[Any] = None,
    rule_versions: Optional[Iterable[Any]] = None,
    regulatory_module: str = "lmpc",
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

    # A net quantity of None means "not established yet" and is legitimate: the
    # net quantity is one of the declarations this engine READS from the package,
    # so requiring it as an input forced an inspector to type the very value
    # under inspection before any image had been analysed. An asserted zero or
    # negative quantity is a different thing entirely — a broken value rather
    # than an absent one — and is still rejected.
    if net_quantity_value is not None and float(net_quantity_value) <= 0:
        raise ValueError("net_quantity_value must be greater than zero")

    quantity_established = exemption_module.quantity_is_established(
        net_quantity_value, net_quantity_unit
    )

    captures = captures or []
    rules = load_rules()

    # Regardless of whether a full versioned RuleVersion registry is supplied
    # (see below), the catalogue's OWN status/effective_from/effective_to
    # metadata must always be respected: a rule marked superseded/omitted, a
    # rule whose effective_to has passed, or a rule not yet in force must
    # never participate in a CURRENT (or any dated) inspection. This is a
    # generic, data-driven filter -- see filter_active_rules() -- not a
    # special case for any specific rule or regulation clause.
    from regulatory.runtime import coerce_inspection_date as _coerce_inspection_date
    as_of_for_status = (
        _coerce_inspection_date(inspection_date)
        if inspection_date is not None
        else _dt.date.today()
    )
    rules = filter_active_rules(rules, as_of_for_status)

    # A dated inspection MUST resolve against the authoritative RuleVersion
    # registry. Falling back to today's rules.json for a historical date would
    # make an otherwise correct inspection legally time-travelling. Conversely,
    # the legacy undated API path remains unchanged for existing callers.
    selected_versions = {}
    inspection_date_value = None
    if inspection_date is not None:
        if rule_versions is None:
            from regulatory.versions import RuleVersionSelectionError
            raise RuleVersionSelectionError(
                "A dated inspection requires an explicit RuleVersion registry; "
                "the engine will not fall back to rules.json."
            )
        rules, selected_versions = apply_rule_versions(
            rules,
            rule_versions,
            module=regulatory_module,
            inspection_date=inspection_date,
        )
        from regulatory.runtime import coerce_inspection_date
        inspection_date_value = coerce_inspection_date(inspection_date).isoformat()

    applicable_rule_version = version_label(selected_versions)
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
            inspection_date=inspection_date_value,
            applicable_rule_version=applicable_rule_version,
        )

    # An undetermined exemption is not an exemption, but it is also not a clean
    # "in scope". Rule 3's quantity exclusion and Rule 26(a)'s small-package
    # relaxation both depend on the net quantity, so when that quantity was never
    # established the applicability question is genuinely open. It is recorded as
    # an UNCERTAIN scope fact and carried into `review_required` so the
    # indeterminacy appears in the report instead of being silently resolved
    # against the package. Declaration checks still run: the pack's own
    # net-quantity declaration may well be readable, and this engine's absence
    # handling already resolves unreadable declarations to UNCERTAIN.
    quantity_scope_uncertain = (
        not exemption.is_exempt
        and exemption.exemption_type == QUANTITY_NOT_ESTABLISHED
    )
    if quantity_scope_uncertain:
        scope_rule = _find_rule(rules, exemption.rule_id, "LMPC-2011-R3-SCOPE")
        facts.append(_make_fact(
            field="__scope__",
            extraction=None,
            status=FactStatus.UNCERTAIN,
            rule=scope_rule,
            reason=exemption.reason,
            review_required=True,
            confidence_override=0.0,
        ))
        if scope_rule:
            findings.append(_finding(
                rule=scope_rule,
                status=FactStatus.UNCERTAIN,
                reason=exemption.reason,
                confidence=0.0,
                review_required=True,
                missing_evidence=["net_quantity"],
            ))

    # ------------------------------------------------------------------
    # 2. Build contextual applicability facts & calibration inference.
    # ------------------------------------------------------------------
    if pdp_area_cm2 is None and captures:
        inferred_area = _infer_pdp_area_from_captures(captures, geometry)
        if inferred_area is not None:
            pdp_area_cm2 = inferred_area

    _infer_numeral_height_from_captures(extractions, captures)

    context = {
        "is_imported": is_imported,
        "dimensions_relevant": dimensions_relevant,
        "best_before_applicable": best_before_applicable,
        "unit_price_rule_applies": True,
        "sale_type": sale_type,
        "product_category": product_category,
        "is_export_only": is_export_only,
        "retail_bundle_count": retail_bundle_count,
        "pdp_area_cm2": pdp_area_cm2,
        "net_quantity_value": net_quantity_value,
        "net_quantity_unit": net_quantity_unit,
        "mrp": mrp,
    }

    # ------------------------------------------------------------------
    # 3. Dynamic Data-Driven Rule Evaluation
    # ------------------------------------------------------------------
    # All rules are evaluated dynamically from loaded active rules.
    # Specialized rules (e.g. font height, unit price math, standard pack
    # schedules, multipack bundles) are routed through SPECIALIZED_EVALUATORS.
    # All ordinary rules (mandatory declarations, wholesale declarations, export
    # sales, category exemptions, advertisements, and any synthetic rules) are
    # evaluated generically through evaluate_rule().
    handled_rule_ids = set()
    sorted_rules = sorted(
        rules.values(),
        key=lambda r: (-r.get("priority", 0), r.get("rule_id", "")),
    )

    for rule in sorted_rules:
        r_id = rule.get("rule_id")
        if not r_id or r_id in handled_rule_ids:
            continue
        if r_id == "LMPC-2011-R3-SCOPE":
            # Handled at step 1
            continue
        if r_id in ("LMPC-2011-R7-PDP-AREA", "LMPC-2011-SCHEDULE-II", "LMPC-2011-R32-PENALTY"):
            # Informational / schedule reference rules
            continue

        if r_id in SPECIALIZED_EVALUATORS:
            eval_fn = SPECIALIZED_EVALUATORS[r_id]
            r_facts, r_findings = eval_fn(
                rule=rule,
                rules=rules,
                extractions=extractions,
                captures=captures,
                context=context,
                low_confidence_threshold=low_confidence_threshold,
            )
        else:
            r_facts, r_findings = evaluate_rule(
                rule=rule,
                extractions=extractions,
                captures=captures,
                context=context,
                low_confidence_threshold=low_confidence_threshold,
            )

        facts.extend(r_facts)
        findings.extend(r_findings)
        handled_rule_ids.add(r_id)

    # ------------------------------------------------------------------
    # 4. Advisory sticker/alteration evidence.
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
    # 8. Canonical declarations & deduplicated summary.
    # ------------------------------------------------------------------
    declarations, decl_summary = _build_canonical_declarations(
        facts=facts,
        extractions=extractions,
        context=context,
        captures=captures,
        rules=rules,
    )

    # ------------------------------------------------------------------
    # 9. Final status and summary.
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
        declarations=declarations,
        declaration_summary=decl_summary,
        findings=findings,
        overall_status=overall,
        summary=summary_data,
        evidence_complete=summary_data["evidence_complete"],
        review_required=(
            summary_data["review_required"] > 0
            or overall == FactStatus.UNCERTAIN
        ),
        inspection_date=inspection_date_value,
        applicable_rule_version=applicable_rule_version,
    )


def _build_canonical_declarations(
    facts: List[ExtractedFact],
    extractions: Mapping[str, RawExtraction],
    context: Mapping[str, Any],
    captures: Sequence[SurfaceObservation],
    rules: Optional[Mapping[str, dict]] = None,
) -> tuple[List[CanonicalDeclaration], Dict[str, int]]:
    declarations: List[CanonicalDeclaration] = []

    # Map facts by field name (taking primary non-auxiliary fact)
    fact_map: Dict[str, ExtractedFact] = {}
    for f in facts:
        if f.field.startswith("__") or f.field in ("mrp_numeral_height", "declaration_placement"):
            continue
        if f.field not in fact_map or f.status == FactStatus.PASS:
            fact_map[f.field] = f

    for field_id, meta in CANONICAL_DECLARATION_DEFINITIONS.items():
        canonical_name = meta["canonical_name"]
        rule_id = meta["rule_id"]
        rule_clause = meta["rule_clause"]
        rule_meta = rules.get(rule_id) if rules is not None else None
        rule_version = rule_meta.get("version") if rule_meta else None

        # A canonical field whose governing rule has been filtered out of the
        # CURRENT active ruleset (superseded/repealed/not-yet-effective; see
        # `filter_active_rules`) must never be reported as a missing/failed
        # declaration merely because no fact was produced for it -- that
        # would resurrect exactly the "current inspection still shows an
        # obsolete requirement" problem one level downstream of the rule
        # evaluators themselves. This check is generic over ANY rule_id, not
        # specific to any one field/regulation clause.
        if rules is not None and rule_id not in rules:
            declarations.append(CanonicalDeclaration(
                field=field_id,
                canonical_name=canonical_name,
                value=None,
                status=CanonicalStatus.NOT_APPLICABLE,
                confidence=1.0,
                validation=ValidationDetails(present=False, readable=None, correct_format=None, compliant=True),
                reason=(
                    f"The rule governing '{canonical_name}' ({rule_id}) is not part of the "
                    "current active ruleset (superseded, repealed, or not yet effective) and "
                    "is therefore excluded from current compliance evaluation."
                ),
                rule_id=rule_id,
                rule_clause=rule_clause,
                rule_version=rule_version,
            ))
            continue

        # Check applicability
        is_applicable = True
        if field_id == "best_before_use_by" and not context.get("best_before_applicable", False):
            is_applicable = False
        elif field_id == "country_of_origin" and not context.get("is_imported", False):
            is_applicable = False

        if not is_applicable:
            declarations.append(CanonicalDeclaration(
                field=field_id,
                canonical_name=canonical_name,
                value=None,
                status=CanonicalStatus.NOT_APPLICABLE,
                confidence=1.0,
                validation=ValidationDetails(present=False, readable=None, correct_format=None, compliant=True),
                reason="Declaration is outside statutory scope for this product category and origin.",
                rule_id=rule_id,
                rule_clause=rule_clause,
                rule_version=rule_version,
            ))
            continue

        fact = fact_map.get(field_id)
        ext = extractions.get(field_id)

        extracted_val = fact.extracted_value if fact else (ext.value if ext else None)
        raw_text = fact.raw_text if fact else (ext.raw_text if ext else None)
        norm_val = fact.normalized_value if fact else (ext.normalized_value if ext else None)
        confidence = fact.confidence if fact else (ext.confidence if ext else 0.0)

        # Primary evidence reference
        primary_evidence = None
        if fact and fact.evidence:
            ev = next((e for e in fact.evidence if e.is_attributed()), fact.evidence[0])
            bbox_coords = [ev.bbox.x, ev.bbox.y, ev.bbox.width, ev.bbox.height] if ev.bbox else None
            primary_evidence = DeclarationEvidence(
                image_id=ev.image_id,
                bbox=bbox_coords,
                source="ocr",
            )
        elif ext and ext.bbox:
            primary_evidence = DeclarationEvidence(
                image_id=UNATTRIBUTED_IMAGE_ID,
                bbox=list(ext.bbox) if isinstance(ext.bbox, (list, tuple)) else None,
                source="ocr",
            )

        if fact and fact.status == FactStatus.PASS and extracted_val:
            status = CanonicalStatus.VERIFIED
            reason = fact.reason or f"'{canonical_name}' verified compliant."
            validation = ValidationDetails(present=True, readable=True, correct_format=True, compliant=True)
        elif fact and fact.status == FactStatus.FAIL:
            reason = fact.reason or f"'{canonical_name}' violates statutory requirement."
            if extracted_val:
                # Something WAS extracted, and IT is what fails the rule (e.g. format/amount)
                status = CanonicalStatus.NEEDS_REVIEW
                validation = ValidationDetails(present=True, readable=True, correct_format=False, compliant=False)
            else:
                if _evidence_sufficient_for_missing_field(captures):
                    status = CanonicalStatus.ABSENT
                    reason = f"Required declaration '{canonical_name}' was confirmed absent after comprehensive package coverage."
                    validation = ValidationDetails(present=False, readable=None, correct_format=None, compliant=False)
                else:
                    status = CanonicalStatus.NOT_ASSESSABLE
                    reason = f"Declaration not observed in the provided view(s). Package evidence is insufficient to conclude absence."
                    validation = ValidationDetails(present=False, readable=None, correct_format=None, compliant=None)
        elif extracted_val is not None:
            status = CanonicalStatus.NEEDS_REVIEW
            # NOTE: `fact`/`ext` being truthy does not guarantee `.reason` is set
            # (e.g. a fact with status UNCERTAIN carrying no explanatory text) --
            # must fall back on an empty/None reason, not just a missing object.
            reason = (
                (fact.reason if fact else None)
                or (ext.reason if ext else None)
                or f"'{canonical_name}' detected but requires human review."
            )
            validation = ValidationDetails(present=True, readable=confidence >= 0.4, correct_format=None, compliant=None)
        elif ext is not None and (getattr(ext, "label", None) or getattr(ext, "raw_text", None)):
            status = CanonicalStatus.NEEDS_REVIEW
            reason = getattr(ext, "reason", "") or f"Declaration label detected, but value was not reliably detected."
            validation = ValidationDetails(present=False, readable=None, correct_format=False, compliant=None)
        else:
            if _evidence_sufficient_for_missing_field(captures):
                status = CanonicalStatus.ABSENT
                reason = f"Required declaration '{canonical_name}' was confirmed absent after comprehensive package coverage."
                validation = ValidationDetails(present=False, readable=None, correct_format=None, compliant=False)
            else:
                status = CanonicalStatus.NOT_ASSESSABLE
                reason = f"Declaration not observed in the provided view(s). Package evidence is insufficient to conclude absence."
                validation = ValidationDetails(present=False, readable=None, correct_format=None, compliant=None)

        declarations.append(CanonicalDeclaration(
            field=field_id,
            canonical_name=canonical_name,
            label=getattr(ext, "label", None) if ext else None,
            value=extracted_val,
            normalized_value=norm_val,
            raw_text=raw_text,
            confidence=confidence,
            status=status,
            evidence=primary_evidence,
            validation=validation,
            reason=reason,
            rule_id=rule_id,
            rule_clause=rule_clause,
            rule_version=rule_version,
        ))

    # Assert that no duplicates exist in the canonical declarations list
    assert len(declarations) == len(set(d.field for d in declarations)), "Duplicate canonical declaration IDs detected!"

    verified_cnt = sum(1 for d in declarations if d.status == CanonicalStatus.VERIFIED)
    needs_review_cnt = sum(1 for d in declarations if d.status == CanonicalStatus.NEEDS_REVIEW)
    absent_cnt = sum(1 for d in declarations if d.status == CanonicalStatus.ABSENT)
    not_assessable_cnt = sum(1 for d in declarations if d.status == CanonicalStatus.NOT_ASSESSABLE)
    not_applicable_cnt = sum(1 for d in declarations if d.status == CanonicalStatus.NOT_APPLICABLE)
    applicable_cnt = len(declarations) - not_applicable_cnt
    assessed_cnt = verified_cnt + needs_review_cnt + absent_cnt

    summary = {
        "applicable": applicable_cnt,
        "assessed": assessed_cnt,
        "verified": verified_cnt,
        "needs_review": needs_review_cnt,
        "review_required": needs_review_cnt,
        "absent": absent_cnt,
        "non_compliant": absent_cnt,
        "not_assessable": not_assessable_cnt,
        "not_applicable": not_applicable_cnt,
        "detected": sum(1 for d in declarations if d.validation.present),
    }
    return declarations, summary

