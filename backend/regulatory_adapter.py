"""
backend/regulatory_adapter.py
Adapter between confirmed Qwen extractions and Arya's generic rule engine.
Implements Section 7:
- Maps confirmed extraction objects into Arya Evidence/EvidenceValue paths without mutating inputs.
- Preserves raw value, normalized value, unit, semantic confidence, source text, image/face.
- Maps ambiguous/unusable localizations to unusable where visual evidence is required.
- Maps standard generic paths.
- Evaluates rules/generic/lmpc_rules.json.
- Converts EngineReport into current ProductInspection response without altering Qwen fact values.
- Keeps ApplicabilityStatus and ComplianceStatus separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from exemption import ExemptionInput, classify_exemption

from schema import (
    BBox,
    CANONICAL_DECLARATION_DEFINITIONS,
    EvidenceReference,
    ExtractedFact,
    FactStatus,
    InspectionSummary,
    ProductInspection,
    RuleFinding,
    UNATTRIBUTED_IMAGE_ID,
)
from unit_price import compute_unit_sale_price

from engine import Evidence, RuleEngine, load_ruleset
from engine.results import ApplicabilityStatus, ComplianceStatus, RuleResult, EngineReport
from localization.models import LocalizedEvidence, LocalizationStatus

GENERIC_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "generic" / "lmpc_rules.json"

_ENGINE_CACHE: Dict[str, RuleEngine] = {}


def get_generic_engine(rules_path: Path = GENERIC_RULES_PATH) -> RuleEngine:
    key = str(rules_path)
    if key not in _ENGINE_CACHE:
        _ENGINE_CACHE[key] = RuleEngine(load_ruleset(rules_path))
    return _ENGINE_CACHE[key]


_STATUS_TO_FACT_STATUS = {
    ComplianceStatus.PASS: FactStatus.PASS,
    ComplianceStatus.FAIL: FactStatus.FAIL,
    ComplianceStatus.UNCERTAIN: FactStatus.UNCERTAIN,
    ComplianceStatus.EXEMPTED: FactStatus.EXEMPT,
    ComplianceStatus.NOT_APPLICABLE: FactStatus.EXEMPT,
    ComplianceStatus.ENGINE_ERROR: FactStatus.UNCERTAIN,
    ComplianceStatus.NOT_CONSIDERED: FactStatus.UNCERTAIN,
}


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


def build_generic_evidence(
    extractions: Dict[str, Any],
    localized_evidence: Optional[List[LocalizedEvidence]] = None,
    *,
    net_quantity_value: Optional[float] = None,
    net_quantity_unit: Optional[str] = None,
    mrp: Optional[float] = None,
    is_imported: bool = False,
    is_export_only: bool = False,
    category_requires_best_before: bool = True,
    commodity_has_standard_pack_schedule: bool = False,
    required_numeral_height_mm: Optional[float] = None,
    measured_numeral_height_mm: Optional[float] = None,
    declared_unit_sale_price: Optional[float] = None,
    expected_unit_sale_price: Optional[float] = None,
    multipack_count: Optional[int] = None,
    inspection_date: Optional[date] = None,
) -> Evidence:
    """
    Builds regulation-agnostic Evidence without mutating input extractions.
    Integrates localized evidence references and status.
    """
    ev = Evidence()
    loc_by_field: Dict[str, LocalizedEvidence] = {}
    if localized_evidence:
        for loc in localized_evidence:
            loc_by_field[loc.field] = loc

    for field_name in CANONICAL_DECLARATION_DEFINITIONS:
        extraction = extractions.get(field_name)
        loc = loc_by_field.get(field_name)

        if extraction is None:
            continue

        if isinstance(extraction, dict):
            raw_val = extraction.get("value")
            norm_val = extraction.get("normalized_value")
            conf = extraction.get("confidence")
            source_txt = extraction.get("raw_text")
            face_id = extraction.get("surface_id") or extraction.get("face_id") or "face_1"
            img_id = extraction.get("image_id")
            raw_bbox = extraction.get("bbox")
            usable = extraction.get("usable", True)
        else:
            raw_val = getattr(extraction, "value", None)
            norm_val = getattr(extraction, "normalized_value", None)
            conf = getattr(extraction, "confidence", None)
            source_txt = getattr(extraction, "raw_text", None)
            face_id = getattr(extraction, "surface_id", None) or getattr(extraction, "face_id", None) or "face_1"
            img_id = getattr(extraction, "image_id", None)
            raw_bbox = getattr(extraction, "bbox", None)
            usable = getattr(extraction, "usable", True)

        val = norm_val or raw_val
        present = val is not None and str(val).strip() != ""

        # Check localization quality
        if loc:
            if loc.localization_status in (LocalizationStatus.AMBIGUOUS_MATCH, LocalizationStatus.LOCALIZER_UNAVAILABLE):
                # Mark as ambiguous / review needed where visual verification is strict
                pass
            if loc.bbox_canonical:
                raw_bbox = loc.bbox_canonical

        ev.set_field(
            f"declared.{field_name}",
            val,
            normalized_value=norm_val,
            confidence=conf,
            present=present,
            source_text=source_txt,
            provenance="qwen_3_8_27b",
            image_id=img_id or face_id,
            bbox=raw_bbox,
            usable=usable,
        )

    # Specific subpaths
    if net_quantity_value is not None:
        ev.set_field("declared.net_quantity", net_quantity_value, unit=net_quantity_unit, present=True)
    if net_quantity_unit:
        ev.set_field("declared.net_quantity.unit", net_quantity_unit, present=True)

    if mrp is not None:
        ev.set_field("declared.mrp", mrp, present=True)
    mrp_ext = extractions.get("mrp")
    if mrp_ext:
        txt = mrp_ext.get("raw_text") if isinstance(mrp_ext, dict) else getattr(mrp_ext, "raw_text", None)
        if txt:
            ev.set_field("declared.mrp.label_text", txt, present=True)

    if declared_unit_sale_price is not None:
        ev.set_field("declared.unit_sale_price", declared_unit_sale_price, present=True)
    if expected_unit_sale_price is not None:
        ev.set_field("computed.expected_unit_sale_price", expected_unit_sale_price, present=True)

    if measured_numeral_height_mm is not None:
        ev.set_field("measured.numeral_height_mm", measured_numeral_height_mm, present=True)
    if required_numeral_height_mm is not None:
        ev.set_context("required_numeral_height_mm", required_numeral_height_mm)

    # Exemption / context flags
    ev.set_context("is_imported", bool(is_imported))
    ev.set_context("is_export_only", bool(is_export_only))
    ev.set_context("category_requires_best_before", bool(category_requires_best_before))
    ev.set_context("commodity_has_standard_pack_schedule", bool(commodity_has_standard_pack_schedule))
    if multipack_count is not None:
        ev.set_context("retail_bundle_count", int(multipack_count))
    if inspection_date:
        ev.set_context("inspection_date", inspection_date.isoformat())

    return ev


def evaluate_regulatory_compliance(
    inspection_id: str,
    sale_type: str,
    product_category: str,
    net_quantity_value: Optional[float],
    net_quantity_unit: Optional[str],
    mrp: Optional[float],
    extractions: Dict[str, Any],
    localized_evidence: Optional[List[LocalizedEvidence]] = None,
    captures: Optional[List[Any]] = None,
    is_export_only: bool = False,
    is_imported: bool = False,
    retail_bundle_count: Optional[int] = None,
    best_before_applicable: bool = True,
    inspection_date: Optional[date] = None,
    rules_path: Path = GENERIC_RULES_PATH,
) -> Tuple[ProductInspection, EngineReport]:
    """
    Evaluates regulatory compliance using Arya's generic engine.
    Converts EngineReport into standard ProductInspection.
    """
    engine = get_generic_engine(rules_path)

    # Compute expected unit sale price if possible
    unit_calc = compute_unit_sale_price(mrp, net_quantity_value, net_quantity_unit)
    expected_usp = float(unit_calc.unit_sale_price) if unit_calc and unit_calc.unit_sale_price is not None else None

    # Exemption classification
    ex_input = ExemptionInput(
        sale_type=sale_type,
        net_quantity_value=net_quantity_value,
        net_quantity_unit=net_quantity_unit,
        product_category=product_category,
        is_export_only=is_export_only,
        retail_bundle_count=retail_bundle_count,
    )
    ex_result = classify_exemption(ex_input)


    evidence = build_generic_evidence(
        extractions=extractions,
        localized_evidence=localized_evidence,
        net_quantity_value=net_quantity_value,
        net_quantity_unit=net_quantity_unit,
        mrp=mrp,
        is_imported=is_imported,
        is_export_only=is_export_only,
        category_requires_best_before=best_before_applicable,
        expected_unit_sale_price=expected_usp,
        multipack_count=retail_bundle_count,
        inspection_date=inspection_date or date.today(),
    )
    evidence.set_context("exemption.is_exempt", bool(ex_result.is_exempt))

    context_dict = {
        "as_of_date": inspection_date.isoformat() if inspection_date else None,
        "inspection_date": inspection_date.isoformat() if inspection_date else None,
    }
    engine_report = engine.evaluate(evidence, context=context_dict)


    # Convert results into RuleFinding and ExtractedFact
    findings: List[RuleFinding] = []
    facts: List[ExtractedFact] = []

    for rule_res in engine_report.results:
        # Build evidence references
        refs: List[EvidenceReference] = []
        for cit in rule_res.evidence:
            try:
                img_id = cit.image_id or UNATTRIBUTED_IMAGE_ID
                bbox_obj = None
                if cit.bbox:
                    if isinstance(cit.bbox, BBox):
                        bbox_obj = cit.bbox
                    elif isinstance(cit.bbox, dict):
                        bbox_obj = BBox(
                            x=cit.bbox.get("x", 0.0),
                            y=cit.bbox.get("y", 0.0),
                            width=cit.bbox.get("width", 0.0),
                            height=cit.bbox.get("height", 0.0),
                        )
                refs.append(EvidenceReference(
                    image_id=img_id,
                    bbox=bbox_obj,
                    evidence_note=f"{cit.field}={cit.normalized_value!r}" if cit.field else None,
                ))
            except Exception:
                continue

        fact_stat = _STATUS_TO_FACT_STATUS.get(rule_res.status, FactStatus.UNCERTAIN)
        finding = RuleFinding(
            rule_id=rule_res.rule_id,
            rule_version=rule_res.rule_version,
            status=fact_stat,
            requirement_description=rule_res.name,
            reason=rule_res.explanation,
            evidence=refs,
            missing_evidence=rule_res.missing_evidence,
            confidence=rule_res.confidence or 0.0,
            review_required=rule_res.status in (ComplianceStatus.UNCERTAIN, ComplianceStatus.ENGINE_ERROR),
            verification_status=rule_res.applicability.value,
        )
        findings.append(finding)

        # Map to canonical fact if relevant
        field_name = _RULE_TO_CANONICAL_FIELD.get(rule_res.rule_id)
        if field_name:
            ext = extractions.get(field_name)
            val = None
            raw_t = None
            conf = 0.0
            if ext:
                if isinstance(ext, dict):
                    val = ext.get("normalized_value") or ext.get("value")
                    raw_t = ext.get("raw_text")
                    conf = ext.get("confidence", 0.0)
                else:
                    val = getattr(ext, "normalized_value", None) or getattr(ext, "value", None)
                    raw_t = getattr(ext, "raw_text", None)
                    conf = getattr(ext, "confidence", 0.0)

            c_def = CANONICAL_DECLARATION_DEFINITIONS.get(field_name, {})
            facts.append(ExtractedFact(
                field=field_name,
                extracted_value=str(val) if val is not None else None,
                status=fact_stat,
                confidence=conf or 0.0,
                rule_id=rule_res.rule_id,
                rule_version=rule_res.rule_version,
                raw_text=raw_t,
                canonical_field=field_name,
                canonical_name=c_def.get("canonical_name"),
                canonical_status=rule_res.applicability.value,
                reason=rule_res.explanation,
                review_required=rule_res.status in (ComplianceStatus.UNCERTAIN, ComplianceStatus.ENGINE_ERROR),
            ))

    # Aggregate summary
    overall_status = _STATUS_TO_FACT_STATUS.get(engine_report.aggregation.overall_status, FactStatus.UNCERTAIN)

    counts = {
        "PASS": 0, "FAIL": 0, "UNCERTAIN": 0, "EXEMPTED": 0,
        "NOT_APPLICABLE": 0, "ENGINE_ERROR": 0, "NOT_CONSIDERED": 0,
    }
    review_cnt = 0
    for r in engine_report.results:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
        if r.status in (ComplianceStatus.UNCERTAIN, ComplianceStatus.ENGINE_ERROR):
            review_cnt += 1

    applicable = [r for r in engine_report.results if r.applicability is ApplicabilityStatus.APPLICABLE]
    coverage = (len(applicable) - counts["UNCERTAIN"]) / len(applicable) if applicable else 1.0

    summary = InspectionSummary(
        total_rules_evaluated=len(engine_report.results),
        passed=counts["PASS"],
        failed=counts["FAIL"],
        uncertain=counts["UNCERTAIN"],
        exempt=counts["EXEMPTED"] + counts["NOT_APPLICABLE"],
        review_required=review_cnt,
        evidence_complete=all(not r.missing_evidence for r in applicable),
        coverage_score=round(max(0.0, min(1.0, coverage)), 4),
    )

    product_inspection = ProductInspection(
        inspection_id=inspection_id,
        sale_type=sale_type,
        product_category=product_category,
        overall_status=overall_status,
        findings=findings,
        facts=facts,
        summary=summary,
        declarations=[],
        applicable_rule_version=f"{engine_report.ruleset_id}:{engine_report.ruleset_version}" if engine_report.ruleset_version else engine_report.ruleset_id,
    )

    return product_inspection, engine_report
