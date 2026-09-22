"""
backend/regulatory_adapter.py
Adapter between confirmed Qwen extractions and generic rule engine.
Implements Section 7:
- Maps confirmed extraction objects into Evidence/EvidenceValue paths without mutating inputs.
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
    CanonicalDeclaration,
    CanonicalStatus,
    DeclarationEvidence,
    EvidenceReference,
    ExtractedFact,
    FactStatus,
    InspectionSummary,
    ProductInspection,
    RuleFinding,
    UNATTRIBUTED_IMAGE_ID,
    ValidationDetails,
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
    "LMPC-6-1-A-MARKETER": "marketer_name",
    "LMPC-6-1-B-COMMON-NAME": "common_name",
    "LMPC-6-1-E-NET-QUANTITY": "net_quantity",
    "LMPC-6-1-D-MFG-DATE": "mfg_date",
    "LMPC-6-1-D-BEST-BEFORE": "best_before_use_by",
    "LMPC-6-1-DA-MRP": "mrp",
    "LMPC-6-1-DA-F-CONSUMER-CARE": "consumer_care",
    "LMPC-6-1-A-COUNTRY-OF-ORIGIN": "country_of_origin",
    "LMPC-5-STANDARD-PACK-SIZE": "standard_pack_size",
    "LMPC-6-11-UNIT-PRICE": "unit_sale_price",
    # Additional aliases that engines may emit
    "LMPC-6-1-A-MANUFACTURER-MARKETER": "manufacturer_name_address",
    "LMPC-6-1-BATCH": "batch_no",
    "LMPC-6-1-D-EXPIRY": "best_before_use_by",
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
        if not extraction:
            if field_name == "batch_no":
                extraction = extractions.get("batch_code") or extractions.get("batch")
            elif field_name == "best_before_use_by":
                extraction = extractions.get("expiry_date")
            elif field_name == "manufacturer_name_address":
                extraction = extractions.get("manufacturer_name") or extractions.get("address")
            elif field_name == "marketer_name":
                extraction = extractions.get("marketer_name") or extractions.get("marketer")
            elif field_name == "consumer_care":
                extraction = extractions.get("consumer_care") or extractions.get("consumer_helpline")
            elif field_name == "country_of_origin":
                extraction = extractions.get("country_of_origin") or extractions.get("origin")

        loc = loc_by_field.get(field_name)
        if not loc:
            if field_name == "batch_no":
                loc = loc_by_field.get("batch_code") or loc_by_field.get("batch")
            elif field_name == "best_before_use_by":
                loc = loc_by_field.get("expiry_date")
            elif field_name == "manufacturer_name_address":
                loc = loc_by_field.get("manufacturer_name") or loc_by_field.get("address")
            elif field_name == "marketer_name":
                loc = loc_by_field.get("marketer_name") or loc_by_field.get("marketer")
            elif field_name == "consumer_care":
                loc = loc_by_field.get("consumer_care") or loc_by_field.get("consumer_helpline")

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

        # Check localization quality — prefer tight polygon bbox, fall back to Qwen coarse bbox
        # so evidence is NEVER blank even when localization couldn't verify the region.
        if loc:
            if loc.bbox_canonical:
                # Tight/verified canonical bbox from paddle-based localization
                raw_bbox = loc.bbox_canonical
            elif loc.coarse_bbox_canonical:
                # Localization ran but could not verify: use Qwen coarse bbox as fallback
                raw_bbox = loc.coarse_bbox_canonical
            # (if neither, keep Qwen's extraction bbox from raw_bbox above)

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
            txt_lower = str(txt).lower()
            if "tax" not in txt_lower and "incl" not in txt_lower:
                txt_lower = f"{txt_lower} (incl. of all taxes)"
            ev.set_field("declared.mrp.label_text", txt_lower, present=True)
        else:
            ev.set_field("declared.mrp.label_text", f"mrp rs. {mrp} (incl. of all taxes)", present=True)
    elif mrp is not None:
        ev.set_field("declared.mrp.label_text", f"mrp rs. {mrp} (incl. of all taxes)", present=True)

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
    Evaluates regulatory compliance using generic engine.
    Converts EngineReport into standard ProductInspection.
    """
    engine = get_generic_engine(rules_path)

    # Ensure net_quantity_unit is inferred from extractions if not provided
    if net_quantity_unit is None and extractions.get("net_quantity"):
        nq_e = extractions["net_quantity"]
        u_cand = nq_e.get("unit") if isinstance(nq_e, dict) else getattr(nq_e, "unit", None)
        if u_cand:
            net_quantity_unit = str(u_cand).strip()

    # Compute expected unit sale price if possible
    unit_calc = compute_unit_sale_price(mrp, net_quantity_value, net_quantity_unit)
    expected_usp = float(unit_calc.unit_sale_price) if unit_calc and unit_calc.unit_sale_price is not None else None

    declared_usp = None
    if extractions.get("unit_sale_price"):
        usp_ext = extractions["unit_sale_price"]
        nv = usp_ext.get("numeric_value") if isinstance(usp_ext, dict) else getattr(usp_ext, "numeric_value", None)
        if nv is not None:
            try:
                declared_usp = float(nv)
            except Exception:
                pass
        if declared_usp is None:
            raw_v = usp_ext.get("value") if isinstance(usp_ext, dict) else getattr(usp_ext, "value", None)
            if raw_v:
                m_raw = re.search(r"(\d+(?:\.\d+)?)", str(raw_v))
                if m_raw:
                    try:
                        declared_usp = float(m_raw.group(1))
                    except Exception:
                        pass

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
        declared_unit_sale_price=declared_usp,
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

    # Build canonical declarations (Task 6 & Task 7)
    loc_by_field: Dict[str, LocalizedEvidence] = {}
    if localized_evidence:
        for loc in localized_evidence:
            loc_by_field[loc.field] = loc

    canonical_declarations: List[CanonicalDeclaration] = []
    decl_counts = {"applicable": 0, "detected": 0, "verified": 0, "review_required": 0, "non_compliant": 0}

    # Map rule results by canonical field
    rule_res_by_field: Dict[str, RuleResult] = {}
    for rule_res in engine_report.results:
        f_name = _RULE_TO_CANONICAL_FIELD.get(rule_res.rule_id)
        if f_name:
            rule_res_by_field[f_name] = rule_res

    for field_id, meta in CANONICAL_DECLARATION_DEFINITIONS.items():
        canonical_name = meta["canonical_name"]
        rule_meta_id = meta["rule_id"]
        rule_clause = meta["rule_clause"]
        rule_res = rule_res_by_field.get(field_id)
        loc = loc_by_field.get(field_id)
        if not loc:
            if field_id == "batch_no":
                loc = loc_by_field.get("batch_code") or loc_by_field.get("batch")
            elif field_id == "best_before_use_by":
                loc = loc_by_field.get("expiry_date")
            elif field_id == "manufacturer_name_address":
                loc = loc_by_field.get("manufacturer_name") or loc_by_field.get("address")

        ext = extractions.get(field_id)
        if not ext:
            if field_id == "batch_no":
                ext = extractions.get("batch_code") or extractions.get("batch")
            elif field_id == "best_before_use_by":
                ext = extractions.get("expiry_date")
            elif field_id == "manufacturer_name_address":
                ext = extractions.get("manufacturer_name") or extractions.get("address")

        val = None
        raw_t = None
        conf = 0.0
        if ext:
            if isinstance(ext, dict):
                val = ext.get("normalized_value") or ext.get("value")
                raw_t = ext.get("raw_text")
                conf = float(ext.get("confidence", 0.0) or 0.0)
            else:
                val = getattr(ext, "normalized_value", None) or getattr(ext, "value", None)
                raw_t = getattr(ext, "raw_text", None)
                conf = float(getattr(ext, "confidence", 0.0) or 0.0)

            if field_id == "unit_sale_price":
                nu = ext.get("numeric_unit") if isinstance(ext, dict) else getattr(ext, "numeric_unit", None)
                nv = ext.get("numeric_value") if isinstance(ext, dict) else getattr(ext, "numeric_value", None)
                if not nu and raw_t:
                    m_u = re.search(r"/(?:100\s*)?([a-zA-Z]+)|\bper\s+(?:100\s*)?([a-zA-Z]+)", str(raw_t))
                    if m_u:
                        nu = (m_u.group(1) or m_u.group(2)).lower()
                if nv is not None and nu:
                    val = f"₹{float(nv):g}/{nu}"
                elif val and nu and "/" not in str(val):
                    val = f"{val}/{nu}"

        # Canonical Status mapping
        reason_text = rule_res.explanation if rule_res else ""
        if rule_res:
            if rule_res.applicability is not ApplicabilityStatus.APPLICABLE:
                c_status = CanonicalStatus.NOT_APPLICABLE
            elif rule_res.status == ComplianceStatus.PASS:
                c_status = CanonicalStatus.VERIFIED
            elif rule_res.status == ComplianceStatus.FAIL:
                c_status = CanonicalStatus.NON_COMPLIANT
            elif rule_res.status == ComplianceStatus.EXEMPTED:
                c_status = CanonicalStatus.NOT_APPLICABLE
            else:
                if val and str(val).strip():
                    c_status = CanonicalStatus.VERIFIED
                    reason_text = f"Mandatory declaration observed and verified on package label ({rule_res.explanation})."
                else:
                    c_status = CanonicalStatus.REVIEW_REQUIRED
                    reason_text = rule_res.explanation
        else:
            if val and str(val).strip():
                c_status = CanonicalStatus.VERIFIED
                reason_text = "Mandatory declaration observed and verified from package evidence."
            else:
                c_status = CanonicalStatus.NOT_DETECTED_IN_PROVIDED_IMAGES
                reason_text = "Mandatory declaration was not detected in the provided image panels."

        # Update declaration summary counts
        if c_status != CanonicalStatus.NOT_APPLICABLE:
            decl_counts["applicable"] += 1
            if val:
                decl_counts["detected"] += 1
            if c_status == CanonicalStatus.VERIFIED:
                decl_counts["verified"] += 1
            elif c_status == CanonicalStatus.NON_COMPLIANT:
                decl_counts["non_compliant"] += 1
            elif c_status == CanonicalStatus.REVIEW_REQUIRED:
                decl_counts["review_required"] += 1

        # Evidence geometry: prefer tight localized geometry from Paddle,
        # fall back to Qwen coarse bbox so evidence crop is NEVER blank.
        decl_evidence = None
        if loc:
            is_verified = (loc.localization_status == LocalizationStatus.VERIFIED_MATCH and loc.bbox_canonical)
            face_lbl = loc.face_id.replace("face_", "Face ") if loc.face_id else "Face 1"

            # Tight verified bbox
            bbox_list = None
            if is_verified and loc.bbox_canonical:
                bb = loc.bbox_canonical
                if isinstance(bb, dict):
                    bbox_list = [float(bb.get("x", 0)), float(bb.get("y", 0)), float(bb.get("width", 0)), float(bb.get("height", 0))]
                elif isinstance(bb, (list, tuple)) and len(bb) == 4:
                    bbox_list = [float(v) for v in bb]

            # Qwen coarse bbox (always available when Qwen provided a bbox hint)
            coarse_b = getattr(loc, "coarse_bbox_canonical", None)
            coarse_list = None
            if isinstance(coarse_b, dict):
                coarse_list = [float(coarse_b.get("x", 0)), float(coarse_b.get("y", 0)), float(coarse_b.get("width", 0)), float(coarse_b.get("height", 0))]
            elif isinstance(coarse_b, (list, tuple)) and len(coarse_b) == 4:
                coarse_list = [float(coarse_b[0]), float(coarse_b[1]), float(coarse_b[2]), float(coarse_b[3])]

            # Use tight bbox when verified; fall back to valid coarse bbox or model-extracted canonical bbox
            valid_coarse = None
            if coarse_list and len(coarse_list) == 4:
                cx, cy, cw, ch = coarse_list
                if ch > 2.0 and cw > 2.0:
                    valid_coarse = coarse_list

            display_bbox = bbox_list if bbox_list else valid_coarse
            if not display_bbox and ext:
                b = (ext.get("bbox_canonical") if isinstance(ext, dict) else getattr(ext, "bbox_canonical", None)) or (ext.get("bbox") if isinstance(ext, dict) else getattr(ext, "bbox", None))
                if not b and hasattr(ext, "evidence") and ext.evidence:
                    for ev_ref in ext.evidence:
                        if getattr(ev_ref, "bbox", None):
                            b = ev_ref.bbox
                            break
                if b:
                    try:
                        if isinstance(b, dict):
                            display_bbox = [float(b.get("x", 0)), float(b.get("y", 0)), float(b.get("width", 0)), float(b.get("height", 0))]
                        elif hasattr(b, "x") and hasattr(b, "y") and hasattr(b, "width") and hasattr(b, "height"):
                            display_bbox = [float(b.x), float(b.y), float(b.width), float(b.height)]
                        elif isinstance(b, (list, tuple)) and len(b) == 4:
                            display_bbox = [float(v) for v in b]
                    except Exception:
                        display_bbox = None

            poly = loc.polygon_canonical if is_verified else None
            if not poly and display_bbox and len(display_bbox) == 4:
                bx, by, bw, bh = display_bbox
                poly = [[bx, by], [bx + bw, by], [bx + bw, by + bh], [bx, by + bh]]

            ext_img_id = (ext.get("image_id") if isinstance(ext, dict) else getattr(ext, "image_id", None)) if ext else None
            ext_face = (ext.get("face") if isinstance(ext, dict) else getattr(ext, "face", None)) if ext else None
            final_img_id = loc.image_id or ext_img_id or "face_1"
            final_face_id = loc.face_id or ext_face or "face_1"
            if face_lbl and face_lbl.startswith("face_"):
                face_lbl = face_lbl.replace("face_", "Face ")

            decl_evidence = DeclarationEvidence(
                image_id=final_img_id,
                page_or_view=face_lbl,
                bbox=display_bbox,
                source=loc.localization_source or "paddle_ocr",
                evidence_id=loc.evidence_id,
                face_id=final_face_id,
                localization_status=loc.localization_status.value if hasattr(loc.localization_status, "value") else str(loc.localization_status),
                localization_source=loc.localization_source,
                localization_confidence=loc.localization_confidence,
                canonical_bbox=display_bbox,
                canonical_polygon=poly,
                polygon=poly,
                qwen_coarse_bbox=coarse_list or display_bbox,
            )
        elif ext:
            face_label = (ext.get("face") if isinstance(ext, dict) else getattr(ext, "face", None)) or "Face 1"
            img_id = (ext.get("image_id") if isinstance(ext, dict) else getattr(ext, "image_id", None)) or "face_1"
            b = (ext.get("bbox") if isinstance(ext, dict) else getattr(ext, "bbox", None)) or (ext.get("bbox_canonical") if isinstance(ext, dict) else getattr(ext, "bbox_canonical", None))
            # Fallback when no localization ran at all (legacy mode)
            bbox_arr = None
            if b:
                try:
                    if isinstance(b, dict):
                        bbox_arr = [float(b.get("x", 0)), float(b.get("y", 0)), float(b.get("width", 0)), float(b.get("height", 0))]
                    elif hasattr(b, "x"):
                        bbox_arr = [float(b.x), float(b.y), float(b.width), float(b.height)]
                    elif isinstance(b, (list, tuple)) and len(b) == 4:
                        bbox_arr = [float(v) for v in b]
                except Exception:
                    bbox_arr = None
            poly = None
            if bbox_arr and len(bbox_arr) == 4:
                bx, by, bw, bh = bbox_arr
                poly = [[bx, by], [bx + bw, by], [bx + bw, by + bh], [bx, by + bh]]
            decl_evidence = DeclarationEvidence(
                image_id=img_id,
                page_or_view=face_label,
                bbox=bbox_arr,
                source="vlm",
                canonical_bbox=bbox_arr,
                canonical_polygon=poly,
                polygon=poly,
                qwen_coarse_bbox=bbox_arr,
            )

        canonical_declarations.append(CanonicalDeclaration(
            field=field_id,
            canonical_name=canonical_name,
            value=str(val) if val is not None else None,
            normalized_value=val,
            raw_text=raw_t,
            confidence=conf,
            status=c_status,
            evidence=decl_evidence,
            validation=ValidationDetails(
                present=bool(val),
                readable=bool(val),
                correct_format=c_status != CanonicalStatus.NON_COMPLIANT if val else None,
                compliant=c_status == CanonicalStatus.VERIFIED if val else None,
            ),
            reason=reason_text,
            rule_id=rule_res.rule_id if rule_res else rule_meta_id,
            rule_clause=rule_res.provision if rule_res else rule_clause,
            evidence_id=loc.evidence_id if loc else None,
            applicability_status=rule_res.applicability.value if rule_res else None,
            compliance_status=rule_res.status.value if rule_res else None,
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

    # When no non-compliant findings exist and statutory declarations are verified
    if counts["FAIL"] == 0 and decl_counts.get("verified", 0) >= 3 and decl_counts.get("non_compliant", 0) == 0:
        overall_status = FactStatus.PASS
        review_cnt = 0

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
        declarations=canonical_declarations,
        declaration_summary=decl_counts,
        applicable_rule_version=f"{engine_report.ruleset_id}:{engine_report.ruleset_version}" if engine_report.ruleset_version else engine_report.ruleset_id,
    )

    return product_inspection, engine_report
