from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Sequence
import numpy as np

from integrity_matching import *
from integrity_matching import (
    FieldComparisonItem,
    STATUS_MATCH,
    STATUS_EXPECTED_TO_VARY,
    STATUS_POTENTIAL_DISCREPANCY,
    STATUS_REVIEW_REQUIRED,
    STATUS_REF_NOT_OBS,
    STATUS_INSP_NOT_OBS,
    FINDING_OCR_UNCERTAINTY,
    FINDING_ACTUAL_DIFFERENCE,
    FINDING_LEGITIMATE_VARIATION,
    FINDING_INSUFFICIENT_IMAGE_QUALITY,
    FIELD_CLASS_STATIC,
    FIELD_CLASS_VARIABLE,
    FIELD_CLASS_VERSION_SENSITIVE,
    parse_commodity_date,
    corroborate_unit_sale_price,
    detect_sticker_overlay,
    compute_ocr_similarity,
    assess_region_quality,
    _make_evidence_crop,
    _parse_mrp_amount,
    _is_manufacturer_match,
    _parse_net_quantity,
    _barcode_normalize,
    _fssai_normalize,
    _token_set,
    _semantic_consumer_care_match,
    _digits_only,
)

def compare_canonical_fields(
    ref_declarations: Dict[str, Any],
    insp_declarations: List[Dict[str, Any]],
    insp_image_bgr: Optional[np.ndarray] = None,
    ref_image_bgr: Optional[np.ndarray] = None,
    ref_bboxes: Optional[Dict[str, List[int]]] = None,
    ref_crops: Optional[Dict[str, str]] = None,
    ref_polygons: Optional[Dict[str, List[List[float]]]] = None,
    insp_polygons: Optional[Dict[str, List[List[float]]]] = None,
    ref_surface_ids: Optional[Dict[str, str]] = None,
    insp_surface_ids: Optional[Dict[str, str]] = None,
    ref_image_ids: Optional[Dict[str, str]] = None,
    insp_image_ids: Optional[Dict[str, str]] = None,
    ref_image_urls: Optional[Dict[str, str]] = None,
    insp_image_urls: Optional[Dict[str, str]] = None,
    ref_confs: Optional[Dict[str, float]] = None,
    insp_confs: Optional[Dict[str, float]] = None,
    ref_imgs: Optional[List[Tuple[Path, np.ndarray]]] = None,
    insp_imgs: Optional[List[Tuple[Path, np.ndarray]]] = None,
    insp_raw: Optional[Dict[str, Any]] = None,
    ref_raw: Optional[Dict[str, Any]] = None,
) -> Tuple[List[FieldComparisonItem], List[Dict[str, Any]]]:
    """
    Compares declarations between reference standard and inspected package at the canonical field level.
    Preserves all Priority 1 visual evidence: exact localized bboxes, DBNet polygons, crops, image IDs, and surface IDs.
    Returns:
      (canonical_comparisons, differences)
    """
    canonical_items: List[FieldComparisonItem] = []
    differences: List[Dict[str, Any]] = []

    # Build lookup map of inspected declarations
    insp_map: Dict[str, Dict[str, Any]] = {}
    for item in insp_declarations:
        if isinstance(item, dict):
            fld = (item.get("field") or item.get("name") or "").lower().strip()
            if fld:
                insp_map[fld] = item

    def get_bbox(matched: Optional[Dict[str, Any]]) -> Optional[List[int]]:
        if not matched:
            return None
        raw_box = matched.get("bounding_box") or matched.get("bbox")
        if isinstance(raw_box, dict):
            return [
                int(raw_box.get("x", 0)),
                int(raw_box.get("y", 0)),
                int(raw_box.get("width", 50)),
                int(raw_box.get("height", 30)),
            ]
        if isinstance(raw_box, (list, tuple)) and len(raw_box) >= 4:
            return [int(v) for v in raw_box[:4]]
        return None

    def find_insp_match(aliases: List[str]) -> Optional[Dict[str, Any]]:
        for alias in aliases:
            if alias in insp_map:
                return insp_map[alias]
        return None

    # Pre-extract dates for chronology check
    mfg_insp_match = find_insp_match(["manufacturing_date", "mfd_date", "mfg_date", "date_of_manufacture", "mfd"])
    exp_insp_match = find_insp_match(["expiry_date", "best_before", "use_by_date", "exp_date", "expiry"])
    insp_mfg_val = (mfg_insp_match.get("value") or mfg_insp_match.get("extracted_value") or "") if mfg_insp_match else ""
    insp_exp_val = (exp_insp_match.get("value") or exp_insp_match.get("extracted_value") or "") if exp_insp_match else ""
    mfg_parsed = parse_commodity_date(insp_mfg_val) if insp_mfg_val else None
    exp_parsed = parse_commodity_date(insp_exp_val) if insp_exp_val else None
    chronology_invalid = bool(mfg_parsed and exp_parsed and mfg_parsed > exp_parsed)

    # Pre-extract MRP and Net Quantity for USP arithmetic corroboration
    mrp_insp_match = find_insp_match(["mrp", "maximum_retail_price", "retail_price", "price"])
    insp_mrp_val = (mrp_insp_match.get("value") or mrp_insp_match.get("extracted_value") or "") if mrp_insp_match else (ref_declarations.get("mrp") or "")
    nq_insp_match = find_insp_match(["net_quantity", "net_weight", "net_volume", "quantity", "weight"])
    insp_nq_val = (nq_insp_match.get("value") or nq_insp_match.get("extracted_value") or "") if nq_insp_match else (ref_declarations.get("net_quantity") or "")

    specs = [
        ("mrp", "MRP", FIELD_CLASS_VERSION_SENSITIVE, ["mrp", "maximum_retail_price", "retail_price", "price"]),
        ("unit_sale_price", "Unit Sale Price", FIELD_CLASS_VERSION_SENSITIVE, ["unit_sale_price", "usp"]),
        ("batch_number", "Batch Number", FIELD_CLASS_VARIABLE, ["batch_number", "lot_number", "batch_no", "lot_no", "batch"]),
        ("manufacturing_date", "Date of Manufacture", FIELD_CLASS_VARIABLE, ["manufacturing_date", "mfd_date", "mfg_date", "date_of_manufacture", "mfd"]),
        ("expiry_date", "Expiry Date", FIELD_CLASS_VARIABLE, ["expiry_date", "best_before", "use_by_date", "exp_date", "expiry"]),
        ("manufacturer_name", "Manufacturer", FIELD_CLASS_STATIC, ["manufacturer_name", "manufacturer", "mfg_by", "packer_name", "marketer_name"]),
        ("net_quantity", "Net Quantity", FIELD_CLASS_STATIC, ["net_quantity", "net_weight", "net_volume", "quantity", "weight"]),
        ("barcode", "Barcode / GTIN", FIELD_CLASS_STATIC, ["barcode", "gtin", "ean", "upc"]),
        ("fssai_license_number", "FSSAI License", FIELD_CLASS_STATIC, ["fssai_license_number", "fssai_no", "fssai_license", "fssai"]),
        ("product_name", "Product Identity", FIELD_CLASS_STATIC, ["product_name", "product_identity", "brand"]),
        ("consumer_care", "Consumer Care", FIELD_CLASS_STATIC, ["consumer_care", "customer_care", "care_details", "helpline"]),
    ]

    for ref_key, display_name, field_class, aliases in specs:
        ref_val = ref_declarations.get(ref_key)
        matched_insp = find_insp_match(aliases)
        insp_val = (matched_insp.get("value") or matched_insp.get("extracted_value") or "") if matched_insp else ""

        ref_str = str(ref_val).strip() if ref_val is not None else ""
        insp_str = str(insp_val).strip() if insp_val else ""

        # If NEITHER side has observed this field, skip (nothing to compare).
        if not ref_str and not insp_str:
            continue

        ref_bbox = (ref_bboxes or {}).get(ref_key)
        ref_polygon = (ref_polygons or {}).get(ref_key)
        ref_surf = (ref_surface_ids or {}).get(ref_key)
        ref_img_id = (ref_image_ids or {}).get(ref_key)
        ref_img_url = (ref_image_urls or {}).get(ref_key)
        ref_c = float((ref_confs or {}).get(ref_key) or 0.90)

        insp_bbox = get_bbox(matched_insp)
        insp_polygon = (matched_insp.get("polygon") if isinstance(matched_insp, dict) else None) or (insp_polygons or {}).get(ref_key)
        insp_surf = (matched_insp.get("surface_id") or matched_insp.get("face") if isinstance(matched_insp, dict) else None) or (insp_surface_ids or {}).get(ref_key)
        insp_img_id = (matched_insp.get("image_id") if isinstance(matched_insp, dict) else None) or (insp_image_ids or {}).get(ref_key)
        insp_img_url = (matched_insp.get("image_url") if isinstance(matched_insp, dict) else None) or (insp_image_urls or {}).get(ref_key)
        insp_c = float(
            (matched_insp.get("confidence") if isinstance(matched_insp, dict) and matched_insp.get("confidence") is not None else None)
            or (0.92 if matched_insp and (matched_insp.get("value") or matched_insp.get("extracted_value")) else None)
            or (insp_confs or {}).get(ref_key)
            or 0.85
        )

        # Use pre-made crop if available, otherwise generate on-the-fly with polygon and padding
        insp_crop_premade = (matched_insp.get("evidence_crop_base64") if isinstance(matched_insp, dict) else None) or None
        insp_crop: Optional[str] = insp_crop_premade
        if not insp_crop and insp_image_bgr is not None and insp_bbox:
            insp_crop = _make_evidence_crop(insp_image_bgr, insp_bbox, polygon=insp_polygon)
        ocr_conf = insp_c
        quality = assess_region_quality(insp_image_bgr, insp_bbox) if (insp_image_bgr is not None and insp_bbox) else {"sharpness": 1.0, "is_degraded": False, "quality_note": "Normal quality"}

        ref_crop = (ref_crops or {}).get(ref_key)
        if not ref_crop and ref_image_bgr is not None and ref_bbox:
            ref_crop = _make_evidence_crop(ref_image_bgr, ref_bbox, polygon=ref_polygon)

        raw_sim, norm_sim, sim_reason = compute_ocr_similarity(ref_str, insp_str)

        # ============================================================
        # EVIDENCE GATES FIRST -- NO MATCH WITHOUT REFERENCE EVIDENCE
        # ============================================================
        status = STATUS_REVIEW_REQUIRED
        is_susp = False
        finding_cat = FINDING_OCR_UNCERTAINTY
        reason = "Classification in progress."
        obs = "Classification in progress."
        diff_type = "Awaiting evidence rule classification"
        sev = "LOW"

        has_ref_evidence = bool(ref_str and ref_str.lower() not in ("not specified", "none", "null", "not available", "unspecified", "n/a", "not detected"))
        has_insp_evidence = bool(insp_str and insp_str.lower() not in ("not specified", "none", "null", "not available", "unspecified", "n/a", "not detected"))
        low_quality_issue = bool(ocr_conf < 0.60 or (quality.get("is_degraded") and ocr_conf < 0.65))

        # ------------------------------------------------------------
        # GATE 1: Missing reference evidence (no OCR observed on ref)
        # ------------------------------------------------------------
        if not has_ref_evidence and has_insp_evidence:
            if ref_key == "unit_sale_price":
                usp_agrees, p_amt, exp_amt, usp_math_note = corroborate_unit_sale_price(insp_str, insp_mrp_val, insp_nq_val)
                has_loc = bool(insp_bbox or insp_polygon)
                if usp_agrees and has_loc:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "USP verified via arithmetic & localized packaging evidence"
                    reason = f"Unit Sale Price ({insp_str}) verified by arithmetic consistency: {usp_math_note}"
                    obs = f"Statutory USP corroborated with declared MRP ({insp_mrp_val}) and Net Quantity ({insp_nq_val}). Calculation agrees with printed packaging declaration."
                    sev = "LOW"
                elif p_amt is not None and exp_amt is not None and not usp_agrees:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "USP arithmetic conflict"
                    reason = f"Unit Sale Price ({insp_str}) conflicts with declared MRP ({insp_mrp_val}) and Net Quantity ({insp_nq_val}). Expected USP: Rs.{exp_amt:.2f}. Manual review required."
                    obs = f"Printed USP fails mathematical corroboration: {usp_math_note}. Potential pricing declaration miscalculation."
                    sev = "MEDIUM"
                else:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "USP verification pending"
                    reason = f"Unit Sale Price ({insp_str}) could not be fully corroborated (MRP={insp_mrp_val}, Net Qty={insp_nq_val})."
                    obs = f"Manual inspection recommended for USP: {usp_math_note}"
                    sev = "MEDIUM"
            else:
                status = STATUS_REF_NOT_OBS
                finding_cat = FINDING_OCR_UNCERTAINTY
                is_susp = False
                reason = (
                    f"{display_name} declaration was not extracted from any reference face. "
                    f"Inspected value: {insp_str}. "
                    f"Cannot verify without reference evidence."
                )
                obs = (
                    f"Inspection shows {insp_str} but reference OCR did not extract this field "
                    f"from any of the {len(ref_declarations) if hasattr(ref_declarations, '__len__') else 0} reference-declared fields. "
                    f"Review of reference imagery is advised."
                )
                diff_type = f"Reference evidence missing: {ref_key}"
                sev = "MEDIUM"

        # ------------------------------------------------------------
        # GATE 2: Missing inspection evidence (no OCR observed on insp)
        # ------------------------------------------------------------
        elif has_ref_evidence and not has_insp_evidence:
            status = STATUS_INSP_NOT_OBS
            finding_cat = FINDING_OCR_UNCERTAINTY
            is_susp = False
            reason = (
                f"{display_name} was not observed on any scanned panel. "
                f"Reference specification requires: {ref_str}."
            )
            obs = (
                f"Reference declares '{ref_str}' but inspected panels show no OCR match. "
                f"This could indicate an omitted declaration, glare, or a panel not captured."
            )
            diff_type = f"Inspection evidence missing: {ref_key}"
            sev = "MEDIUM"

        # ------------------------------------------------------------
        # GATE 3: Both sides have evidence -> dispatch field-specific rule
        # ------------------------------------------------------------
        else:
            # ========================================================
            # FIELD-SPECIFIC RULES -- each decides from ref_str, insp_str,
            # bbox, quality, and overlays. NEVER default to MATCH.
            # ========================================================

            # --------------------------------------------------------
            # MRP (VERSION-SENSITIVE) -- numeric amount equality + sticker detection
            # --------------------------------------------------------
            if ref_key == "mrp":
                r_amt = _parse_mrp_amount(ref_str)
                i_amt = _parse_mrp_amount(insp_str)
                if r_amt is None or i_amt is None:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "MRP OCR parse ambiguous"
                    reason = f"Price values could not be parsed numerically (ref={ref_str}, insp={insp_str})."
                    obs = "OCR quality insufficient for reliable price parsing. Manual MRP review recommended."
                    sev = "MEDIUM"
                elif abs(r_amt - i_amt) < 1e-6:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Identical statutory declaration (MRP)"
                    reason = f"MRP amount matches: Rs.{r_amt:g} both on reference and inspected packaging."
                    obs = f"Printed retail price (Rs.{r_amt:g}) numerically matches reference standard after OCR normalization."
                    sev = "LOW"
                else:
                    has_overlay, overlay_conf, overlay_reason = detect_sticker_overlay(insp_image_bgr, insp_bbox) if insp_bbox else (False, 0.0, "")
                    if has_overlay:
                        status = STATUS_POTENTIAL_DISCREPANCY
                        is_susp = True
                        finding_cat = FINDING_ACTUAL_DIFFERENCE
                        diff_type = "Suspected MRP sticker overlay / price tampering"
                        reason = f"MRP differs (Rs.{r_amt:g} reference vs Rs.{i_amt:g} inspected) and PHYSICAL STICKER OVERLAY detected over the price region."
                        obs = f"Physical overlay sticker detected over printed price marking: {overlay_reason}. Confidence {overlay_conf:.0%}."
                        sev = "HIGH"
                    else:
                        status = STATUS_REVIEW_REQUIRED
                        is_susp = False
                        finding_cat = FINDING_LEGITIMATE_VARIATION
                        diff_type = "MRP packaging-version difference (packaging price update)"
                        reason = f"MRP differs between packaging runs (ref Rs.{r_amt:g} vs insp Rs.{i_amt:g}). Direct packaging print, no sticker overlay detected."
                        obs = f"Printed retail price differs from reference catalog but clean direct print. Consistent with a packaging / pricing version revision."
                        sev = "MEDIUM"

            # --------------------------------------------------------
            # UNIT SALE PRICE (VERSION-SENSITIVE) -- similar to MRP
            # --------------------------------------------------------
            elif ref_key == "unit_sale_price":
                usp_agrees, p_amt, exp_amt, usp_math_note = corroborate_unit_sale_price(insp_str, insp_mrp_val, insp_nq_val)
                r_amt = _parse_mrp_amount(ref_str)
                i_amt = _parse_mrp_amount(insp_str)
                has_loc = bool(insp_bbox or insp_polygon)

                if usp_agrees and has_loc:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "USP verified via arithmetic & localized packaging evidence"
                    reason = f"Unit Sale Price ({insp_str}) verified by arithmetic consistency: {usp_math_note}"
                    obs = f"Statutory USP corroborated with declared MRP ({insp_mrp_val}) and Net Quantity ({insp_nq_val}). Calculation agrees with printed packaging declaration."
                    sev = "LOW"
                elif p_amt is not None and exp_amt is not None and not usp_agrees:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "USP arithmetic conflict"
                    reason = f"Unit Sale Price ({insp_str}) conflicts with declared MRP ({insp_mrp_val}) and Net Quantity ({insp_nq_val}). Expected USP: Rs.{exp_amt:.2f}. Manual review required."
                    obs = f"Printed USP fails mathematical corroboration: {usp_math_note}. Potential pricing declaration miscalculation."
                    sev = "MEDIUM"
                elif r_amt is not None and i_amt is not None and abs(r_amt - i_amt) < 1e-4:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "USP matches reference"
                    reason = f"Unit sale price matches reference ({ref_str} == {insp_str})."
                    obs = "Unit sale price numerically matches reference packaging."
                    sev = "LOW"
                else:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "USP verification pending"
                    reason = f"Unit Sale Price ({insp_str}) could not be fully corroborated (ref={ref_str}, insp={insp_str})."
                    obs = f"Manual inspection recommended for USP: {usp_math_note}"
                    sev = "MEDIUM"

            # --------------------------------------------------------
            # BATCH NUMBER (VARIABLE) -- always EXPECTED_TO_VARY unless identical
            # --------------------------------------------------------
            elif ref_key == "batch_number":
                if ref_str == insp_str or norm_sim >= 0.99:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Identical batch code (same production lot)"
                    reason = f"Batch code matches reference: {insp_str}."
                    obs = f"Batch '{insp_str}' is identical to reference -- same production lot sampled."
                    sev = "LOW"
                else:
                    status = STATUS_EXPECTED_TO_VARY
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    is_susp = False
                    diff_type = "Legitimate batch update across production lots"
                    reason = f"Batch code legitimately varies (reference {ref_str} -> inspected {insp_str})."
                    obs = f"Batch code differs between reference and inspected lots -- expected across production runs."
                    sev = "LOW"

            # --------------------------------------------------------
            # MANUFACTURING DATE (VARIABLE) -- EXPECTED_TO_VARY unless chronology invalid
            # --------------------------------------------------------
            elif ref_key == "manufacturing_date":
                if chronology_invalid:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Impossible date chronology (MFD later than Expiry)"
                    reason = f"Manufacturing date ({insp_str}) is later than the declared expiry ({insp_exp_val})."
                    obs = f"Chronology violation: MFD ({insp_str}) > EXP ({insp_exp_val}). This is statistically impossible unless date coding was altered."
                    sev = "HIGH"
                elif ref_str == insp_str or norm_sim >= 0.99:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Identical manufacturing date"
                    reason = f"Manufacturing date matches reference ({insp_str}). Same production run sampled."
                    obs = f"MFD date identical to reference -- same production run."
                    sev = "LOW"
                else:
                    status = STATUS_EXPECTED_TO_VARY
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    is_susp = False
                    diff_type = "Legitimate manufacturing-date update"
                    reason = f"Manufacturing date updated from reference ({ref_str} -> {insp_str}). Valid calendar chronology."
                    obs = f"MFD date differs across runs; chronology verified (MFD before Expiry where both are present)."
                    sev = "LOW"

            # --------------------------------------------------------
            # EXPIRY DATE (VARIABLE) -- EXPECTED_TO_VARY, chronology guard
            # --------------------------------------------------------
            elif ref_key == "expiry_date":
                if chronology_invalid:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Impossible date chronology (Expiry earlier than MFD)"
                    reason = f"Expiry date ({insp_str}) precedes manufacturing date ({insp_mfg_val}). Impossible chronological sequence."
                    obs = f"Chronology violation: EXP ({insp_str}) < MFD ({insp_mfg_val}). Indicates altered date coding."
                    sev = "HIGH"
                elif ref_str == insp_str or norm_sim >= 0.99:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Identical expiry date"
                    reason = f"Expiry date matches reference ({insp_str}). Same shelf-life run."
                    obs = f"Expiry date identical to reference."
                    sev = "LOW"
                else:
                    status = STATUS_EXPECTED_TO_VARY
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    is_susp = False
                    diff_type = "Legitimate expiry-date update"
                    reason = f"Expiry date updated from reference ({ref_str} -> {insp_str}). Valid calendar chronology."
                    obs = f"Expiry date differs across runs; chronology valid where both dates present."
                    sev = "LOW"

            # --------------------------------------------------------
            # MANUFACTURER / MARKETER (STATIC) -- token-set containment
            # --------------------------------------------------------
            elif ref_key == "manufacturer_name":
                mfg_match, mfg_rationale = _is_manufacturer_match(ref_str, insp_str)
                if mfg_match:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION if ref_str == insp_str else FINDING_OCR_UNCERTAINTY
                    diff_type = "Manufacturer entity matches reference"
                    reason = f"Manufacturer declaration ({insp_str}) consistent with reference ({ref_str}). {mfg_rationale}."
                    obs = f"Manufacturer name matches reference specification after OCR token normalization ({mfg_rationale})."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.65:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "Manufacturer reading uncertain (low image quality)"
                    reason = f"Manufacturer OCR uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = f"Manufacturer OCR unclear; raw normalized similarity {norm_sim*100:.0f}%. Manual visual inspection recommended."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Manufacturer mismatch (static declaration)"
                    reason = f"Manufacturer does not match reference (ref: {ref_str} vs insp: {insp_str}). {mfg_rationale}."
                    obs = f"High-confidence manufacturer mismatch after token analysis ({mfg_rationale}). Static-field discrepancy."
                    sev = "HIGH"

            # --------------------------------------------------------
            # NET QUANTITY (STATIC) -- numeric amount + unit match
            # --------------------------------------------------------
            elif ref_key == "net_quantity":
                r_nq = _parse_net_quantity(ref_str)
                i_nq = _parse_net_quantity(insp_str)
                if r_nq is None or i_nq is None:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "Net quantity OCR parse ambiguous"
                    reason = f"Net quantity could not be parsed numerically (ref={ref_str}, insp={insp_str})."
                    obs = "Net quantity declaration OCR ambiguous. Manual review recommended."
                    sev = "MEDIUM"
                elif abs(r_nq[0] - i_nq[0]) < 1e-6 and r_nq[1] == i_nq[1]:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Identical net quantity"
                    reason = f"Net quantity matches: {r_nq[0]:g} {r_nq[1]} on both reference and inspected packaging."
                    obs = f"Declared net quantity ({r_nq[0]:g} {r_nq[1]}) numerically matches reference after unit normalization."
                    sev = "LOW"
                elif ocr_conf < 0.35:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "Net quantity unverified due to image quality"
                    reason = f"Net quantity reading uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = "Net quantity OCR below confidence threshold. Manual weigh-scale verification recommended."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Net quantity mismatch (static declaration)"
                    reason = f"Declared net quantity differs from reference (ref: {ref_str} vs insp: {insp_str})."
                    obs = f"Net quantity mismatch after numeric+unit normalization (ref {r_nq[0]:g}{r_nq[1]} vs insp {i_nq[0]:g}{i_nq[1]})."
                    sev = "HIGH"

            # --------------------------------------------------------
            # BARCODE / GTIN (STATIC) -- digit-sequence equality
            # --------------------------------------------------------
            elif ref_key == "barcode":
                b_meta = (insp_raw or {}).get("barcode") or (matched_insp.get("raw") if isinstance(matched_insp, dict) else {})
                decoded_val = b_meta.get("decoded_value") if isinstance(b_meta, dict) else None
                observed_val = b_meta.get("observed_value") if isinstance(b_meta, dict) else None
                bc_status = b_meta.get("barcode_verification_status") if isinstance(b_meta, dict) else None

                if not decoded_val and insp_str:
                    decoded_val = insp_str

                ref_digits = _barcode_normalize(ref_str)
                insp_digits = _barcode_normalize(insp_str)

                # Cross-check both values:
                # VERIFIED = printed digits observed and match decoder.
                # REVIEW_REQUIRED = partial/unclear/disagreeing digits.
                # NOT_OBSERVED = barcode decoded but printed digits are not visually observable.
                # Never fabricate printed digits from the decoder.
                if bc_status == "VERIFIED":
                    if not ref_digits or ref_digits == insp_digits or ref_digits in insp_digits or insp_digits in ref_digits:
                        status = STATUS_MATCH
                        finding_cat = FINDING_LEGITIMATE_VARIATION
                        diff_type = "Barcode verified (printed digits match decoder)"
                        reason = f"Barcode verified: machine decoder ({decoded_val}) matches human-readable printed digits ({observed_val})."
                        obs = f"Barcode dual-verification passed. Decoded GTIN matches printed HRI digits."
                        sev = "LOW"
                    else:
                        status = STATUS_POTENTIAL_DISCREPANCY
                        is_susp = True
                        finding_cat = FINDING_ACTUAL_DIFFERENCE
                        diff_type = "Barcode mismatch with reference standard"
                        reason = f"Verified barcode ({insp_digits}) does not match authorized reference GTIN ({ref_digits})."
                        obs = f"Inspected barcode {insp_digits} differs from reference standard {ref_digits}."
                        sev = "HIGH"
                elif bc_status == "NOT_OBSERVED":
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "Barcode printed digits NOT_OBSERVED"
                    reason = f"Barcode decoded ({decoded_val}) but printed digits are not visually observable."
                    obs = f"Barcode symbol decoded ({decoded_val}) but human-readable printed digits are not visually observable near symbol. Review required."
                    sev = "MEDIUM"
                elif bc_status == "REVIEW_REQUIRED":
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "Barcode printed digits / decoder conflict"
                    reason = f"Barcode review required: machine decoder ({decoded_val}) vs printed digits ({observed_val})."
                    obs = f"Printed digits unclear, partial, or disagreeing with machine decoder. Manual review required."
                    sev = "MEDIUM"
                elif not ref_digits or not insp_digits:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "Barcode OCR missing digits"
                    reason = f"Barcode digit extraction incomplete (ref={ref_str}, insp={insp_str})."
                    obs = "Barcode scanner or OCR failed to extract valid digit sequence."
                    sev = "MEDIUM"
                elif ref_digits == insp_digits:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION if ref_str == insp_str else FINDING_OCR_UNCERTAINTY
                    diff_type = "Barcode matches reference GTIN"
                    reason = f"Barcode ({insp_digits}) matches authorized reference GTIN."
                    obs = f"GTIN digit sequence identical ({ref_digits})."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.70:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "Barcode unverified due to image/OCR quality"
                    reason = f"Barcode verification uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = f"Barcode OCR below 70% confidence (ref={ref_digits} vs insp={insp_digits}). Physical barcode scan recommended."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Barcode / GTIN mismatch (static declaration)"
                    reason = f"Barcode does not match authorized reference (ref: {ref_str} / {ref_digits} vs insp: {insp_str} / {insp_digits})."
                    obs = f"High-confidence barcode mismatch ({len(ref_digits)} ref digits vs {len(insp_digits)} insp digits, sequences differ)."
                    sev = "HIGH"

            # --------------------------------------------------------
            # FSSAI LICENSE (STATIC) -- 14-digit license equality
            # --------------------------------------------------------
            elif ref_key == "fssai_license_number":
                ref_f = _fssai_normalize(ref_str)
                insp_f = _fssai_normalize(insp_str)
                if (not ref_f and not insp_f) or (ref_str.upper() == "NOT_APPLICABLE" and insp_str.upper() == "NOT_APPLICABLE"):
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "FSSAI license OCR ambiguous"
                    reason = f"FSSAI license number could not be reliably extracted (ref={ref_str}, insp={insp_str})."
                    obs = "FSSAI license OCR failed to yield valid digit sequence."
                    sev = "MEDIUM"
                elif ref_f == insp_f:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION if ref_str == insp_str else FINDING_OCR_UNCERTAINTY
                    diff_type = "FSSAI license matches reference"
                    reason = f"FSSAI license number ({insp_f}) matches reference master after digit normalization."
                    obs = f"FSSAI license number identical ({ref_f}) after glyph substitution normalization (0/O, 1/I, 5/S, 8/B)."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.65:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "FSSAI unverified due to image quality"
                    reason = f"FSSAI license uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = f"FSSAI OCR below 65% confidence (ref={ref_f} vs insp={insp_f})."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "FSSAI license mismatch (static declaration)"
                    reason = f"FSSAI license does not match authorized reference (ref: {ref_str} / {ref_f} vs insp: {insp_str} / {insp_f})."
                    obs = f"High-confidence FSSAI license mismatch -- digit sequences differ ({ref_f} vs {insp_f})."
                    sev = "HIGH"

            # --------------------------------------------------------
            # PRODUCT NAME / BRAND (STATIC) -- token-set 80%+ normalized similarity
            # --------------------------------------------------------
            elif ref_key == "product_name":
                ref_tok = _token_set(ref_str)
                insp_tok = _token_set(insp_str)
                brand_match = bool(ref_tok and insp_tok and (ref_tok <= insp_tok or insp_tok <= ref_tok or len(ref_tok & insp_tok) >= max(1, min(2, min(len(ref_tok), len(insp_tok))))))
                if norm_sim >= 0.80 or brand_match:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Product identity matches reference"
                    reason = f"Product identity ({insp_str}) matches authorized reference ({ref_str})."
                    obs = f"Product name normalized similarity {norm_sim*100:.0f}%. Brand-token containment verified."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.60:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "Product name uncertain (image quality)"
                    reason = f"Product identity reading uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = f"Product-identity OCR below confidence threshold. Similarity {norm_sim*100:.0f}%."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Product identity mismatch (static declaration)"
                    reason = f"Product identity mismatch (ref: {ref_str} vs insp: {insp_str})."
                    obs = f"Product identity below similarity threshold ({norm_sim*100:.0f}%) and no brand-token containment."
                    sev = "HIGH"

            # --------------------------------------------------------
            # CONSUMER CARE (STATIC) -- semantic digit/email/token match
            # --------------------------------------------------------
            elif ref_key == "consumer_care":
                care_match, care_rationale = _semantic_consumer_care_match(ref_str, insp_str)
                if care_match:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION if (norm_sim >= 0.95 or ref_str == insp_str) else FINDING_OCR_UNCERTAINTY
                    diff_type = "Consumer care contact semantically consistent"
                    reason = f"Consumer care declaration consistent with reference ({care_rationale})."
                    obs = f"Consumer care semantically verified ({care_rationale}). Raw strings: ref='{ref_str}', insp='{insp_str}'."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.60:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "Consumer care uncertain (image quality)"
                    reason = f"Consumer care reading uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = f"Consumer care OCR below 60% confidence. Normalized similarity {norm_sim*100:.0f}%."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Consumer care mismatch (static declaration)"
                    reason = f"Consumer care differs from reference (ref: {ref_str} vs insp: {insp_str}). {care_rationale}."
                    obs = f"Consumer care semantic check failed ({care_rationale}). Static-field discrepancy."
                    sev = "HIGH"

            # --------------------------------------------------------
            # FALLBACK -- unknown field (shouldn't happen since specs list is closed)
            # --------------------------------------------------------
            else:
                if norm_sim >= 0.95:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Declaration matches"
                    reason = f"{display_name} matches reference (OCR normalized similarity {norm_sim*100:.0f}%)."
                    obs = f"{display_name} matches after OCR normalization."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.65:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = f"{display_name} declaration uncertain"
                    reason = f"{display_name} comparison uncertain due to OCR/image quality (norm_sim={norm_sim*100:.0f}%)."
                    obs = f"Manual review of {display_name} recommended."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = f"{display_name} mismatch"
                    reason = f"{display_name} does not match reference (ref={ref_str} vs insp={insp_str}, sim={norm_sim*100:.0f}%)."
                    obs = f"{display_name} similarity below auto-match threshold."
                    sev = "HIGH"

        item_decoded = None
        item_observed = None
        item_bc_status = None
        if ref_key == "barcode":
            b_meta = (insp_raw or {}).get("barcode") or (matched_insp.get("raw") if isinstance(matched_insp, dict) else {})
            if isinstance(b_meta, dict):
                item_decoded = b_meta.get("decoded_value")
                item_observed = b_meta.get("observed_value")
                item_bc_status = b_meta.get("barcode_verification_status")
            if not item_decoded and insp_str:
                item_decoded = insp_str

        item = FieldComparisonItem(
            field_name=display_name,
            field_key=ref_key,
            field_classification=field_class,
            reference_value=ref_str,
            inspection_value=insp_str,
            status=status,
            is_suspicious=is_susp,
            finding_category=finding_cat,
            reason=reason,
            observation_note=obs,
            reference_crop_base64=ref_crop,
            inspection_crop_base64=insp_crop,
            reference_bbox=ref_bbox,
            inspection_bbox=insp_bbox,
            # Priority 1: Real Visual Evidence fields
            field=ref_key,
            reference_image_id=ref_img_id,
            inspection_image_id=insp_img_id,
            reference_image_url=ref_img_url,
            inspection_image_url=insp_img_url,
            reference_surface_id=ref_surf,
            inspection_surface_id=insp_surf,
            reference_polygon=ref_polygon,
            inspection_polygon=insp_polygon,
            reference_confidence=round(ref_c, 2),
            inspection_confidence=round(insp_c, 2),
            comparison_status=status,
            comparison_reason=reason,
            confidence=round(ocr_conf, 2),
            image_quality_score=round(quality.get("sharpness", 1.0), 2),
            normalized_similarity=round(norm_sim, 2),
            severity=sev,
            decoded_value=item_decoded,
            observed_value=item_observed,
            barcode_verification_status=item_bc_status,
        )
        canonical_items.append(item)

        if status not in (STATUS_INSP_NOT_OBS, STATUS_REF_NOT_OBS) and (status != "MATCH" or finding_cat == FINDING_OCR_UNCERTAINTY or is_susp):
            differences.append({
                "field": ref_key,
                "field_name": display_name.upper(),
                "reference_value": ref_str,
                "inspection_value": insp_str,
                "difference_type": diff_type,
                "bbox": insp_bbox,
                "confidence": ocr_conf,
                "field_classification": field_class,
                "is_suspicious": is_susp,
                "finding_category": finding_cat,
                "ocr_confidence": ocr_conf,
                "image_quality_score": quality.get("sharpness", 1.0),
                "normalized_similarity": norm_sim,
                "observation_note": obs,
                "severity": sev,
                "evidence_crop_base64": insp_crop,
                "inspection_crop_base64": insp_crop,
                "reference_crop_base64": ref_crop,
                "reference_bbox": ref_bbox,
                "inspection_bbox": insp_bbox,
                "reference_polygon": ref_polygon,
                "inspection_polygon": insp_polygon,
                "reference_image_id": ref_img_id,
                "inspection_image_id": insp_img_id,
                "reference_image_url": ref_img_url,
                "inspection_image_url": insp_img_url,
                "reference_surface_id": ref_surf,
                "inspection_surface_id": insp_surf,
                "reference_confidence": round(ref_c, 2),
                "inspection_confidence": round(insp_c, 2),
                "comparison_status": status,
                "comparison_reason": reason,
            })

    return canonical_items, differences


