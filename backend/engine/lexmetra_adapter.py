"""
Integration adapter: wires the generic, data-driven ``engine`` package into
LexMetra's EXISTING contracts (``schema.ProductInspection`` /
``ExtractedFact`` / ``RuleFinding`` / ``InspectionSummary``) and existing
computation services (``exemption.classify_exemption``,
``unit_price.compute_unit_sale_price``).

Architectural boundary this file enforces (spec section 4/24):

    OCR / CV / measurement / exemption-classification / unit-price-math
        --> produce EVIDENCE (facts), never a compliance verdict
    engine.RuleEngine + rules/generic/lmpc_rules.json
        --> makes the deterministic compliance DECISION from that evidence
    this adapter
        --> translates between LexMetra's existing pydantic contract and the
            engine's regulation-agnostic Evidence/RuleResult objects, in
            both directions, so the rest of the application (main.py,
            report.py, the dashboard) needs no changes to consume it.

Entry point: ``run_inspection_v2(...)`` has deliberately the same
*category* of inputs as the legacy ``rule_engine.run_inspection`` (raw
extractions + a handful of context flags) and returns the same
``ProductInspection`` type, so it is a drop-in alternative decision path,
not an isolated demo. The legacy ``rule_engine.run_inspection`` is left
completely untouched -- both paths can run side by side (see
``main.py``'s ``/inspect`` vs ``/inspect/v2/engine``).
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from exemption import ExemptionInput, classify_exemption
from schema import (
    BBox,
    CANONICAL_DECLARATION_DEFINITIONS,
    EvidenceReference,
    ExtractedFact,
    FactStatus,
    GeometryType,
    InspectionSummary,
    ProductInspection,
    RuleFinding,
    UNATTRIBUTED_IMAGE_ID,
)
from unit_price import compute_unit_sale_price

from engine import Evidence, RuleEngine, load_ruleset
from engine.results import ApplicabilityStatus, ComplianceStatus, RuleResult

GENERIC_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "rules" / "generic" / "lmpc_rules.json"

# One process-lifetime cache: parsing + validating the ruleset is pure and
# side-effect-free, so re-doing it on every request would be wasted work
# (spec section 28) without changing correctness.
_ENGINE_CACHE: Dict[str, RuleEngine] = {}


def _get_engine(rules_path: Path = GENERIC_RULES_PATH) -> RuleEngine:
    key = str(rules_path)
    if key not in _ENGINE_CACHE:
        _ENGINE_CACHE[key] = RuleEngine(load_ruleset(rules_path))
    return _ENGINE_CACHE[key]


_STATUS_TO_FACT_STATUS = {
    ComplianceStatus.PASS: FactStatus.PASS,
    ComplianceStatus.FAIL: FactStatus.FAIL,
    ComplianceStatus.UNCERTAIN: FactStatus.UNCERTAIN,
    ComplianceStatus.EXEMPTED: FactStatus.EXEMPT,
    ComplianceStatus.NOT_APPLICABLE: FactStatus.NOT_APPLICABLE,
    ComplianceStatus.ENGINE_ERROR: FactStatus.ENGINE_ERROR,
    ComplianceStatus.NOT_CONSIDERED: FactStatus.NOT_CONSIDERED,
}


# ---------------------------------------------------------------------------
# 1. Build generic Evidence from LexMetra's existing extraction objects
# ---------------------------------------------------------------------------

def build_evidence(
    extractions: Dict[str, Any],
    *,
    net_quantity_value: Optional[float],
    net_quantity_unit: Optional[str],
    mrp: Optional[float],
    exemption_is_exempt: bool,
    is_imported: bool = False,
    category_requires_best_before: bool = True,
    commodity_has_standard_pack_schedule: bool = False,
    required_numeral_height_mm: Optional[float] = None,
    measured_numeral_height_mm: Optional[float] = None,
    expected_unit_sale_price: Optional[float] = None,
    declared_unit_sale_price: Optional[float] = None,
) -> Evidence:
    """
    Translate LexMetra's ``RawExtraction`` objects (see ``rule_engine.py``)
    plus a handful of already-computed context values into the engine's
    generic ``Evidence`` contract.

    This function does not decide anything -- it only carries evidence
    across the boundary. It never fabricates a value: a field with no
    corresponding extraction is left absent (``present=None``), which the
    engine treats as UNKNOWN, not as False.
    """
    ev = Evidence()

    for canonical_field in CANONICAL_DECLARATION_DEFINITIONS:
        extraction = extractions.get(canonical_field)
        if extraction is None:
            continue
        value = getattr(extraction, "normalized_value", None) or getattr(extraction, "value", None)
        confidence = getattr(extraction, "confidence", None)
        present = value is not None and str(value).strip() != ""

        image_id = getattr(extraction, "image_id", None)
        bbox = getattr(extraction, "bbox", None)
        ext_evidence = getattr(extraction, "evidence", None)
        if ext_evidence and len(ext_evidence) > 0:
            first_ref = ext_evidence[0]
            if not image_id and getattr(first_ref, "image_id", None):
                image_id = first_ref.image_id
            if not bbox and getattr(first_ref, "bbox", None):
                bbox = first_ref.bbox

        usable = getattr(extraction, "usable", True)
        if hasattr(extraction, "is_usable") and callable(getattr(extraction, "is_usable")):
            usable = extraction.is_usable()
        quality_state = getattr(extraction, "quality_state", None) or ("usable" if usable else "unusable")
        verification_status = getattr(extraction, "verification_status", None) or (
            "VERIFIED" if confidence is not None and confidence >= 0.7 else "DETECTED"
        )

        ev.set_field(
            f"declared.{canonical_field}",
            value,
            normalized_value=getattr(extraction, "normalized_value", None),
            confidence=confidence,
            present=present,
            source_text=getattr(extraction, "raw_text", None),
            provenance=getattr(extraction, "provenance", "ocr"),
            image_id=image_id,
            bbox=bbox,
            usable=usable,
            quality_state=quality_state,
            verification_status=verification_status,
        )

    # Net quantity gets first-class numeric + unit sub-fields, since several
    # rules compare it numerically or check its unit specifically.
    if net_quantity_value is not None:
        nq_ext = extractions.get("net_quantity")
        nq_img = getattr(nq_ext, "image_id", None) if nq_ext else None
        nq_bbox = getattr(nq_ext, "bbox", None) if nq_ext else None
        if nq_ext and getattr(nq_ext, "evidence", None) and len(nq_ext.evidence) > 0:
            nq_img = nq_img or getattr(nq_ext.evidence[0], "image_id", None)
            nq_bbox = nq_bbox or getattr(nq_ext.evidence[0], "bbox", None)
        ev.set_field("declared.net_quantity", net_quantity_value, unit=net_quantity_unit,
                     present=True, confidence=nq_ext and getattr(nq_ext, "confidence", None),
                     image_id=nq_img, bbox=nq_bbox)
    if net_quantity_unit:
        ev.set_field("declared.net_quantity.unit", net_quantity_unit, present=True)

    if mrp is not None:
        mrp_ext = extractions.get("mrp")
        mrp_img = getattr(mrp_ext, "image_id", None) if mrp_ext else None
        mrp_bbox = getattr(mrp_ext, "bbox", None) if mrp_ext else None
        if mrp_ext and getattr(mrp_ext, "evidence", None) and len(mrp_ext.evidence) > 0:
            mrp_img = mrp_img or getattr(mrp_ext.evidence[0], "image_id", None)
            mrp_bbox = mrp_bbox or getattr(mrp_ext.evidence[0], "bbox", None)
        ev.set_field("declared.mrp", mrp, present=True,
                     confidence=mrp_ext and getattr(mrp_ext, "confidence", None),
                     image_id=mrp_img, bbox=mrp_bbox)
    mrp_extraction = extractions.get("mrp")
    label_text = getattr(mrp_extraction, "raw_text", None) if mrp_extraction else None
    if label_text:
        ev.set_field("declared.mrp.label_text", label_text, present=True)

    if declared_unit_sale_price is not None:
        ev.set_field("declared.unit_sale_price", declared_unit_sale_price, present=True)
    if expected_unit_sale_price is not None:
        ev.set_field("computed.expected_unit_sale_price", expected_unit_sale_price, present=True)

    if measured_numeral_height_mm is not None:
        ev.set_field("measured.numeral_height_mm", measured_numeral_height_mm, present=True)
    if required_numeral_height_mm is not None:
        ev.set_context("required_numeral_height_mm", required_numeral_height_mm)

    # Context (not "one observed fact" -- scope/classification flags)
    ev.set_context("exemption.is_exempt", bool(exemption_is_exempt))
    ev.set_context("is_imported", bool(is_imported))
    ev.set_context("category_requires_best_before", bool(category_requires_best_before))
    ev.set_context("commodity_has_standard_pack_schedule", bool(commodity_has_standard_pack_schedule))

    return ev


# ---------------------------------------------------------------------------
# 2. Map an engine RuleResult back into LexMetra's RuleFinding/ExtractedFact
# ---------------------------------------------------------------------------

def _evidence_refs(result: RuleResult) -> List[EvidenceReference]:
    refs = []
    for citation in result.evidence:
        try:
            image_id = citation.image_id if citation.image_id else UNATTRIBUTED_IMAGE_ID
            bbox_obj = None
            if citation.bbox:
                if isinstance(citation.bbox, BBox):
                    bbox_obj = citation.bbox
                elif isinstance(citation.bbox, dict):
                    bbox_obj = BBox(**citation.bbox)
                elif isinstance(citation.bbox, (list, tuple)) and len(citation.bbox) == 4:
                    bbox_obj = BBox(x=citation.bbox[0], y=citation.bbox[1], width=citation.bbox[2], height=citation.bbox[3])
            
            note = f"{citation.field}={citation.normalized_value!r} (confidence={citation.confidence})" if citation.field else None
            refs.append(EvidenceReference(
                image_id=image_id,
                bbox=bbox_obj,
                evidence_note=note,
            ))
        except Exception:
            # If EvidenceReference's exact required fields differ across
            # schema versions, degrade to "no evidence ref" rather than
            # raise -- the RuleFinding.reason text still carries the
            # information textually.
            continue
    return refs


def result_to_finding(result: RuleResult) -> RuleFinding:
    return RuleFinding(
        rule_id=result.rule_id,
        rule_version=result.rule_version,
        status=_STATUS_TO_FACT_STATUS[result.status],
        requirement_id=None,
        requirement_description=result.name,
        reason=result.explanation,
        evidence=_evidence_refs(result),
        required_evidence=[],
        missing_evidence=result.missing_evidence,
        confidence=result.confidence or 0.0,
        review_required=result.status in (ComplianceStatus.UNCERTAIN, ComplianceStatus.ENGINE_ERROR),
        verification_status=result.applicability.value,
    )


def result_to_fact(result: RuleResult, field_name: str, extraction: Any) -> ExtractedFact:
    value = getattr(extraction, "normalized_value", None) or getattr(extraction, "value", None) if extraction else None
    confidence = getattr(extraction, "confidence", 0.0) if extraction else 0.0
    canonical = CANONICAL_DECLARATION_DEFINITIONS.get(field_name, {})
    return ExtractedFact(
        field=field_name,
        extracted_value=str(value) if value is not None else None,
        status=_STATUS_TO_FACT_STATUS[result.status],
        confidence=confidence or 0.0,
        rule_id=result.rule_id,
        rule_version=result.rule_version,
        raw_text=getattr(extraction, "raw_text", None) if extraction else None,
        canonical_field=field_name,
        canonical_name=canonical.get("canonical_name"),
        canonical_status=result.applicability.value,
        reason=result.explanation,
        review_required=result.status in (ComplianceStatus.UNCERTAIN, ComplianceStatus.ENGINE_ERROR),
    )


# Maps a subset of generic rule_ids to the canonical declaration field they
# primarily concern, so we can also populate ProductInspection.facts (the
# older, field-oriented view) alongside .findings (the rule-oriented view).
# This is presentation-layer convenience only; findings are authoritative.
_RULE_TO_CANONICAL_FIELD = {
    "LMPC-6-1-A-MANUFACTURER": "manufacturer_name_address",
    "LMPC-6-1-B-COMMON-NAME": "common_name",
    "LMPC-6-1-E-NET-QUANTITY": "net_quantity",
    "LMPC-6-1-D-MFG-DATE": "mfg_date",
    "LMPC-6-1-D-BEST-BEFORE": "best_before_use_by",
    "LMPC-6-1-DA-MRP": "mrp",
    "LMPC-6-1-DA-F-CONSUMER-CARE": "consumer_care",
    "LMPC-6-1-A-COUNTRY-OF-ORIGIN": "country_of_origin",
    "LMPC-5-STANDARD-PACK-SIZE": "standard_pack_size",
    "LMPC-6-11-UNIT-PRICE": "unit_sale_price",
}


# ---------------------------------------------------------------------------
# 3. Overall status / summary (delegates to the engine's own aggregation)
# ---------------------------------------------------------------------------

def _overall_status(results: List[RuleResult]) -> FactStatus:
    from engine.aggregate import aggregate
    agg = aggregate(results)
    return _STATUS_TO_FACT_STATUS[agg.overall_status]


def _summary(results: List[RuleResult]) -> InspectionSummary:
    counts = {
        "PASS": 0, "FAIL": 0, "UNCERTAIN": 0, "EXEMPTED": 0,
        "NOT_APPLICABLE": 0, "ENGINE_ERROR": 0, "NOT_CONSIDERED": 0,
    }
    review = 0
    for r in results:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
        if r.status in (ComplianceStatus.UNCERTAIN, ComplianceStatus.ENGINE_ERROR):
            review += 1
    applicable = [r for r in results if r.applicability is ApplicabilityStatus.APPLICABLE]
    evidence_complete = all(not r.missing_evidence for r in applicable)
    coverage = (len(applicable) - sum(1 for r in applicable if r.status is ComplianceStatus.UNCERTAIN)) / len(applicable) \
        if applicable else 1.0
    return InspectionSummary(
        total_rules_evaluated=len(results),
        passed=counts["PASS"],
        failed=counts["FAIL"],
        uncertain=counts["UNCERTAIN"],
        exempt=counts["EXEMPTED"],
        not_applicable=counts["NOT_APPLICABLE"],
        engine_error=counts["ENGINE_ERROR"],
        not_considered=counts["NOT_CONSIDERED"],
        review_required=review,
        evidence_complete=evidence_complete,
        coverage_score=round(max(0.0, min(1.0, coverage)), 4),
    )


# ---------------------------------------------------------------------------
# 4. Public entry point: same category of inputs as legacy run_inspection
# ---------------------------------------------------------------------------

def run_inspection_v2(
    inspection_id: str,
    sale_type: str,
    product_category: str,
    net_quantity_value: Optional[float],
    net_quantity_unit: Optional[str],
    mrp: Optional[float],
    extractions: Dict[str, Any],
    is_export_only: bool = False,
    retail_bundle_count: Optional[int] = None,
    is_imported: bool = False,
    geometry: GeometryType = GeometryType.UNKNOWN,
    category_requires_best_before: bool = True,
    commodity_has_standard_pack_schedule: bool = False,
    required_numeral_height_mm: Optional[float] = None,
    measured_numeral_height_mm: Optional[float] = None,
    declared_unit_sale_price: Optional[float] = None,
    rules_path: Path = GENERIC_RULES_PATH,
    inspection_date: Optional[str] = None,
    as_of_date: Optional[str] = None,
) -> ProductInspection:
    """
    Generic-engine-backed alternative to ``rule_engine.run_inspection``.

    Reuses the EXISTING, already-battle-tested exemption classifier and
    unit-price arithmetic as evidence providers (they still do the
    domain-specific computation), but the PASS/FAIL/UNCERTAIN/
    NOT_APPLICABLE/EXEMPTED decision for every declaration rule is made by
    the generic, data-driven ``engine.RuleEngine`` reading
    ``rules/generic/lmpc_rules.json`` -- not by bespoke per-field Python.
    """
    exemption = classify_exemption(ExemptionInput(
        sale_type=sale_type,
        net_quantity_value=net_quantity_value,
        net_quantity_unit=net_quantity_unit,
        product_category=product_category,
        is_export_only=is_export_only,
        retail_bundle_count=retail_bundle_count,
    ))

    expected_unit_price = None
    if mrp is not None and net_quantity_value and net_quantity_unit:
        try:
            computed = compute_unit_sale_price(net_quantity_value, net_quantity_unit, mrp)
            raw = getattr(computed, "unit_sale_price", None)
            expected_unit_price = float(raw) if raw is not None else None
        except Exception:
            expected_unit_price = None  # left absent -> engine reports UNCERTAIN, never guesses

    if declared_unit_sale_price is None and "unit_sale_price" in extractions:
        raw_usp = extractions["unit_sale_price"]
        num = getattr(raw_usp, "numeric_value", None)
        if num is not None:
            try:
                declared_unit_sale_price = float(num)
            except (TypeError, ValueError):
                pass
        else:
            val = getattr(raw_usp, "value", None)
            if val is not None:
                import re
                m = re.search(r"(\d+(?:\.\d+)?)", str(val))
                if m:
                    try:
                        declared_unit_sale_price = float(m.group(1))
                    except (TypeError, ValueError):
                        pass

    evidence = build_evidence(
        extractions,
        net_quantity_value=net_quantity_value,
        net_quantity_unit=net_quantity_unit,
        mrp=mrp,
        exemption_is_exempt=exemption.is_exempt,
        is_imported=is_imported,
        category_requires_best_before=category_requires_best_before,
        commodity_has_standard_pack_schedule=commodity_has_standard_pack_schedule,
        required_numeral_height_mm=required_numeral_height_mm,
        measured_numeral_height_mm=measured_numeral_height_mm,
        expected_unit_sale_price=expected_unit_price,
        declared_unit_sale_price=declared_unit_sale_price,
    )

    context = {
        "trade_type": sale_type,
        "inspection_id": inspection_id,
        "product_category": product_category,
        "is_imported": is_imported,
        "is_export_only": is_export_only,
        "retail_bundle_count": retail_bundle_count or 1,
        "is_multipack": bool(retail_bundle_count and retail_bundle_count > 1),
        "is_advertisement": False,
        "inspection_includes_registration": False,
    }
    eval_date = as_of_date or inspection_date
    if eval_date:
        context["inspection_date"] = eval_date
        context["as_of_date"] = eval_date

    engine = _get_engine(rules_path)
    report = engine.evaluate(evidence, context=context)

    findings = [result_to_finding(r) for r in report.results]
    facts = []
    for r in report.results:
        field_name = _RULE_TO_CANONICAL_FIELD.get(r.rule_id)
        if field_name:
            facts.append(result_to_fact(r, field_name, extractions.get(field_name)))

    decision_package_dict = report.decision_package.as_dict() if report.decision_package else None

    return ProductInspection(
        inspection_id=inspection_id,
        product_category=product_category,
        sale_type=sale_type,
        inspection_date=eval_date,
        applicable_rule_version=report.ruleset_version,
        package_weight_or_volume=net_quantity_value,
        package_weight_unit=net_quantity_unit,
        geometry=geometry,
        facts=facts,
        findings=findings,
        overall_status=_overall_status(report.results),
        exempt_reason=exemption.reason if exemption.is_exempt else None,
        summary=_summary(report.results),
        evidence_complete=_summary(report.results).evidence_complete,
        review_required=any(f.review_required for f in findings),
        decision_package=decision_package_dict,
    )
