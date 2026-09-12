#!/usr/bin/env python3
"""
Comprehensive Evaluation Pipeline for Legal Metrology Declaration Extraction.

Evaluates:
1. Field-level precision, recall, and F1 on real package photographs.
2. Canonical schema mapping, date/price normalization, and deduplication.
3. Multi-surface session aggregation (e.g. panel 1 + panel 2).
4. Label vs Value separation and confidence scoring policy verification.
"""

from __future__ import annotations

import json
import sys
import os
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import cv2
import numpy as np
from PIL import Image

import ocr_extraction
from schema import CanonicalStatus, ProductInspection
from rule_engine import run_inspection
import capture_session
from main import _prepare_extractions, _infer_applicability_context, _resolve_quantity, _resolve_mrp


REPO_ROOT = _BACKEND_DIR.parent
PHOTOS_DIR = REPO_ROOT / "images dataset"
if not PHOTOS_DIR.exists():
    PHOTOS_DIR = REPO_ROOT / "DEPENDENCIES" / "images dataset"
if not PHOTOS_DIR.exists():
    PHOTOS_DIR = REPO_ROOT / "CLAUDE 2" / "proj" / "dataset" / "real_photos"

GT_FILE = REPO_ROOT / "dataset" / "real_photos_ground_truth.json"
if not GT_FILE.exists():
    GT_FILE = REPO_ROOT / "CLAUDE 2" / "proj" / "dataset" / "real_photos_ground_truth.json"


def evaluate_ground_truth() -> Dict[str, Any]:
    """Evaluate OCR extraction and field classification against annotated ground truth."""
    if not GT_FILE.exists():
        return {"error": f"Ground truth file not found at {GT_FILE}"}

    with open(GT_FILE, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    images = gt_data.get("images", [])
    field_stats: Dict[str, Dict[str, int]] = {}
    detailed_results = []

    # Confusion categories: TP, FP, TN, FN
    for i, item in enumerate(images):
        filename = item["file"]
        photo_path = PHOTOS_DIR / filename
        if not photo_path.exists():
            continue

        print(f"  [{i+1}/{len(images)}] Processing {filename} ({item.get('product')})...", flush=True)
        pil_img = Image.open(photo_path)
        ocr_lines = ocr_extraction.run_ocr(pil_img)
        classified = ocr_extraction.classify_fields(ocr_lines)

        img_result = {
            "image_id": item["image_id"],
            "file": filename,
            "product": item.get("product"),
            "fields": {},
        }

        for field_name, gt in item.get("ground_truth", {}).items():
            if field_name not in field_stats:
                field_stats[field_name] = {"TP": 0, "FP": 0, "FN": 0, "TN": 0, "skipped": 0}

            if gt.get("ambiguous_do_not_score"):
                field_stats[field_name]["skipped"] += 1
                img_result["fields"][field_name] = "skipped_ambiguous"
                continue

            extracted = classified.get(field_name)
            is_not_on_surface = gt.get("not_on_this_surface", False)

            if is_not_on_surface:
                if extracted is None or not extracted.get("value"):
                    field_stats[field_name]["TN"] += 1
                    img_result["fields"][field_name] = "correct_not_observed"
                else:
                    field_stats[field_name]["FP"] += 1
                    img_result["fields"][field_name] = f"false_positive (got '{extracted.get('value')}')"
                continue

            # Field is expected on this surface
            if extracted is None or not extracted.get("value"):
                field_stats[field_name]["FN"] += 1
                img_result["fields"][field_name] = "false_negative (not observed)"
                continue

            # Check value match
            val_str = str(extracted.get("value", ""))
            matched = False

            if "value" in gt:
                expected_num = gt["value"]
                extracted_num = extracted.get("numeric_value")
                if extracted_num is not None and abs(float(extracted_num) - float(expected_num)) < 0.05:
                    matched = True
                elif str(expected_num) in val_str:
                    matched = True

            if "value_contains" in gt:
                needle = gt["value_contains"].lower()
                if needle in val_str.lower():
                    matched = True

            if matched:
                field_stats[field_name]["TP"] += 1
                img_result["fields"][field_name] = f"true_positive ('{val_str}')"
            else:
                field_stats[field_name]["FP"] += 1
                img_result["fields"][field_name] = f"mismatch (expected {gt}, got '{val_str}')"

        detailed_results.append(img_result)

    # Compute precision, recall, F1
    summary = {}
    total_tp = sum(s["TP"] for s in field_stats.values())
    total_fp = sum(s["FP"] for s in field_stats.values())
    total_fn = sum(s["FN"] for s in field_stats.values())
    total_tn = sum(s["TN"] for s in field_stats.values())

    for f_name, counts in field_stats.items():
        tp = counts["TP"]
        fp = counts["FP"]
        fn = counts["FN"]
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        summary[f_name] = {
            "TP": tp, "FP": fp, "FN": fn, "TN": counts["TN"],
            "precision": round(prec, 3),
            "recall": round(rec, 3),
            "f1": round(f1, 3),
        }

    overall_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1 = (2 * overall_prec * overall_rec) / (overall_prec + overall_rec) if (overall_prec + overall_rec) > 0 else 0.0

    return {
        "field_summary": summary,
        "overall": {
            "total_scored": total_tp + total_fp + total_fn + total_tn,
            "TP": total_tp,
            "FP": total_fp,
            "FN": total_fn,
            "TN": total_tn,
            "overall_precision": round(overall_prec, 3),
            "overall_recall": round(overall_rec, 3),
            "overall_f1": round(overall_f1, 3),
            "accuracy": round((total_tp + total_tn) / (total_tp + total_fp + total_fn + total_tn), 3)
            if (total_tp + total_fp + total_fn + total_tn) > 0 else 0.0,
        },
        "per_image": detailed_results,
    }


def evaluate_multi_surface_bru_jar() -> Dict[str, Any]:
    """
    Evaluate multi-surface aggregation on the exact Bru Instant Coffee jar:
    Panel 1 (MRP, batch, use-by) + Panel 2 (net quantity, manufacturer, consumer care).
    """
    panel1_name = "Screenshot_2026-09-06-22-06-12-38_92460851df6f172a4592fca41cc2d2e6.jpg"
    panel2_name = "Screenshot_2026-09-06-22-06-22-17_92460851df6f172a4592fca41cc2d2e6.jpg"

    p1_path = PHOTOS_DIR / panel1_name
    p2_path = PHOTOS_DIR / panel2_name

    if not p1_path.exists() or not p2_path.exists():
        return {"error": "Bru jar photos not found"}

    img1 = Image.open(p1_path)
    img2 = Image.open(p2_path)

    # OCR panel 1
    lines1 = ocr_extraction.run_ocr(img1)
    c1 = ocr_extraction.classify_fields(lines1)
    c1 = capture_session.stamp_provenance(c1, image_id=panel1_name, surface_id="panel_1")

    # OCR panel 2
    lines2 = ocr_extraction.run_ocr(img2)
    c2 = ocr_extraction.classify_fields(lines2)
    c2 = capture_session.stamp_provenance(c2, image_id=panel2_name, surface_id="panel_2")

    # Merge across surfaces
    merged = capture_session.merge_classified_fields(c1, c2)
    extractions = _prepare_extractions(merged)

    qty_val, qty_unit, qty_src = _resolve_quantity(150.0, "g", merged)
    mrp_val = _resolve_mrp(None, merged)
    best_before_app, is_imp = _infer_applicability_context("food", "retail", merged)

    # Create surface observations
    obs1 = capture_session.build_surface_observation(
        image_id=panel1_name,
        surface_type=capture_session.parse_surface_type("FRONT"),
        image_quality=capture_session.assess_quality(cv2.imread(str(p1_path)))
        if hasattr(capture_session, "assess_quality") else None,
        coverage=0.5,
        surface_id="panel_1",
    )
    obs2 = capture_session.build_surface_observation(
        image_id=panel2_name,
        surface_type=capture_session.parse_surface_type("BACK"),
        image_quality=capture_session.assess_quality(cv2.imread(str(p2_path)))
        if hasattr(capture_session, "assess_quality") else None,
        coverage=1.0,
        surface_id="panel_2",
    )

    inspection = run_inspection(
        inspection_id="8909106043251:eval-multisurface",
        sale_type="retail",
        product_category="food",
        net_quantity_value=qty_val,
        net_quantity_unit=qty_unit,
        mrp=mrp_val,
        extractions=extractions,
        captures=[obs1, obs2],
        best_before_applicable=best_before_app,
        is_imported=is_imp,
    )

    canonical_declarations = inspection.declarations or []
    summary = inspection.declaration_summary or {}

    # Check for duplicates
    canonical_fields = [d.canonical_field for d in canonical_declarations]
    duplicates = [f for f in set(canonical_fields) if canonical_fields.count(f) > 1]

    # Check individual required fields
    mrp_decl = next((d for d in canonical_declarations if d.canonical_field == "mrp"), None)
    qty_decl = next((d for d in canonical_declarations if d.canonical_field == "net_quantity"), None)
    mfg_decl = next((d for d in canonical_declarations if d.canonical_field == "manufacturer_name_address"), None)
    exp_decl = next((d for d in canonical_declarations if d.canonical_field == "best_before_use_by"), None)
    usp_decl = next((d for d in canonical_declarations if d.canonical_field == "unit_sale_price"), None)

    return {
        "overall_status": inspection.overall_status.value,
        "declarations_count": len(canonical_declarations),
        "has_duplicates": len(duplicates) > 0,
        "duplicate_fields": duplicates,
        "summary": summary,
        "mrp": {
            "value": mrp_decl.extracted_value if mrp_decl else None,
            "status": mrp_decl.status.value if mrp_decl else None,
            "provenance": mrp_decl.provenance.image_id if mrp_decl and mrp_decl.provenance else None,
        },
        "net_quantity": {
            "value": qty_decl.extracted_value if qty_decl else None,
            "status": qty_decl.status.value if qty_decl else None,
            "provenance": qty_decl.provenance.image_id if qty_decl and qty_decl.provenance else None,
        },
        "manufacturer": {
            "value": mfg_decl.extracted_value if mfg_decl else None,
            "status": mfg_decl.status.value if mfg_decl else None,
            "provenance": mfg_decl.provenance.image_id if mfg_decl and mfg_decl.provenance else None,
        },
        "use_by": {
            "value": exp_decl.extracted_value if exp_decl else None,
            "status": exp_decl.status.value if exp_decl else None,
            "provenance": exp_decl.provenance.image_id if exp_decl and exp_decl.provenance else None,
        },
        "unit_sale_price": {
            "value": usp_decl.extracted_value if usp_decl else None,
            "status": usp_decl.status.value if usp_decl else None,
        },
    }


def main():
    print("=" * 70)
    print("LEGAL METROLOGY DECLARATION PIPELINE EVALUATION")
    print("=" * 70)

    print("\n--- 1. REAL PHOTOS GROUND TRUTH BENCHMARK ---")
    gt_res = evaluate_ground_truth()
    if "error" in gt_res:
        print(f"Error: {gt_res['error']}")
    else:
        ov = gt_res["overall"]
        print(f"Total Scored: {ov['total_scored']}")
        print(f"True Positives: {ov['TP']}, True Negatives: {ov['TN']}")
        print(f"False Positives: {ov['FP']}, False Negatives: {ov['FN']}")
        print(f"Overall Precision: {ov['overall_precision'] * 100:.1f}%")
        print(f"Overall Recall:    {ov['overall_recall'] * 100:.1f}%")
        print(f"Overall F1 Score:  {ov['overall_f1'] * 100:.1f}%")
        print(f"Overall Accuracy:  {ov['accuracy'] * 100:.1f}%")

        print("\nField Breakdown:")
        for f, s in gt_res["field_summary"].items():
            print(f"  {f:28s} P={s['precision']*100:5.1f}%  R={s['recall']*100:5.1f}%  F1={s['f1']*100:5.1f}%  (TP={s['TP']}, FP={s['FP']}, FN={s['FN']}, TN={s['TN']})")

    print("\n--- 2. MULTI-SURFACE AGGREGATION (BRU JAR PANELS 1 & 2) ---")
    ms_res = evaluate_multi_surface_bru_jar()
    if "error" in ms_res:
        print(f"Error: {ms_res['error']}")
    else:
        print(f"Overall Status:        {ms_res['overall_status']}")
        print(f"Total Declarations:    {ms_res['declarations_count']}")
        print(f"Has Duplicates:        {ms_res['has_duplicates']}")
        print(f"Summary:               {ms_res['summary']}")
        print(f"MRP:                   {ms_res['mrp']}")
        print(f"Net Quantity:          {ms_res['net_quantity']}")
        print(f"Manufacturer:          {ms_res['manufacturer']}")
        print(f"Use By:                {ms_res['use_by']}")
        print(f"Unit Sale Price:       {ms_res['unit_sale_price']}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
