"""
LexMetra: Cross-Package Preprocessing Validation Runner.
Processes GEMS (Face 1, Face 2, Face 3) and PRINGLES (Face 1, Face 2, Face 3)
using the current implementation in backend/package_preprocessor.py.

Generates:
  backend/debug/preprocessing/gems/face_1/ ... face_3/
  backend/debug/preprocessing/pringles/face_1/ ... face_3/
  backend/debug/preprocessing/preprocessing_validation_summary.json

NO external API/LLM calls.
"""

import json
import sys
import time
from pathlib import Path

import cv2

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))

from package_preprocessor import run_preprocessing_pipeline

def main():
    print("==================================================")
    print("LEXMETRA: CROSS-PACKAGE PREPROCESSING VALIDATION")
    print("GEMS + PRINGLES, ALL FACES")
    print("==================================================")

    debug_root = project_root / "backend" / "debug" / "preprocessing"
    gems_debug = debug_root / "gems"
    pringles_debug = debug_root / "pringles"

    # Input definitions
    # GEMS canonical images
    gems_inputs = [
        ("Face 1", project_root / "images new" / "GEMS.jpg", gems_debug / "face_1"),
        ("Face 2", project_root / "images new" / "GEMS 1.jpg", gems_debug / "face_2"),
        ("Face 3", project_root / "images new" / "GEMS 2.jpg", gems_debug / "face_3"),
    ]

    # PRINGLES canonical images
    pringles_dir = project_root / "DEPENDENCIES" / "images dataset"
    pringles_inputs = [
        ("Face 1", pringles_dir / "Screenshot_2026-09-06-22-07-11-58_92460851df6f172a4592fca41cc2d2e6.jpg", pringles_debug / "face_1"),
        ("Face 2", pringles_dir / "Screenshot_2026-09-06-22-06-55-06_92460851df6f172a4592fca41cc2d2e6.jpg", pringles_debug / "face_2"),
        ("Face 3", pringles_dir / "Screenshot_2026-09-06-22-07-02-74_92460851df6f172a4592fca41cc2d2e6.jpg", pringles_debug / "face_3"),
    ]

    summary = {
        "GEMS": {},
        "PRINGLES": {},
    }

    products = [
        ("GEMS", gems_inputs),
        ("PRINGLES", pringles_inputs),
    ]

    for product_name, faces in products:
        print(f"\nProcessing Product: {product_name}")
        for face_name, img_path, out_dir in faces:
            print(f"\n--- {product_name} {face_name} ---")
            print(f"Input path: {img_path}")
            print(f"Output directory: {out_dir}")

            if not img_path.exists():
                print(f"ERROR: Input image {img_path} not found!")
                continue

            img_bgr = cv2.imread(str(img_path))
            if img_bgr is None:
                print(f"ERROR: Failed to read {img_path}")
                continue

            t_start = time.perf_counter()
            res = run_preprocessing_pipeline(
                img_bgr=img_bgr,
                source_name=img_path.name,
                product=product_name,
                face=face_name,
                debug_dir=out_dir,
                margin_pct=0.06,
            )
            elapsed_ms = round((time.perf_counter() - t_start) * 1000, 1)

            meta = res.metadata
            print(f"Done in {elapsed_ms} ms")
            print(f"  Boundary detected: {meta['boundary_detected']} ({meta['boundary_method']}, conf={meta['physical_boundary_confidence']})")
            print(f"  Evidence-safe boundary used: {meta['evidence_safe_boundary_used']} (margin: {meta['boundary_margin_percent']}%)")
            print(f"  Original: {meta['original_dimensions']} ({meta['original_file_size_bytes']} bytes)")
            print(f"  Final:    {meta['final_dimensions']} ({meta['final_file_size_bytes']} bytes)")
            print(f"  Fallback: {meta['fallback_used']} (reason: {meta['failure_reason']})")

            # Warnings check
            warnings = []
            if not meta["boundary_detected"]:
                warnings.append("Physical boundary was NOT detected.")
            if meta["physical_boundary_confidence"] < 0.70:
                warnings.append(f"Low boundary confidence ({meta['physical_boundary_confidence']}).")
            if meta["fallback_used"]:
                warnings.append(f"Fallback was triggered: {meta['failure_reason']}")

            # Check aspect ratio change or extreme area reduction
            orig_area = meta['original_dimensions'][0] * meta['original_dimensions'][1]
            final_area = meta['final_dimensions'][0] * meta['final_dimensions'][1]

            summary_record = {
                "product": product_name,
                "face": face_name,
                "input_file": str(img_path.name),
                "boundary_success": meta["boundary_detected"],
                "boundary_method": meta["boundary_method"],
                "confidence": meta["physical_boundary_confidence"],
                "evidence_safe_margin": meta["boundary_margin_percent"],
                "evidence_safe_boundary_used": meta["evidence_safe_boundary_used"],
                "perspective_corrected": meta["perspective_corrected"],
                "background_normalized": meta["background_normalized"],
                "glare_detected": meta["glare_detected"],
                "glare_reduced": meta["glare_reduced"],
                "illumination_corrected": meta["illumination_corrected"],
                "text_enhanced": meta["text_enhanced"],
                "original_dimensions": meta["original_dimensions"],
                "original_size": meta["original_file_size_bytes"],
                "final_dimensions": meta["final_dimensions"],
                "final_size": meta["final_file_size_bytes"],
                "preprocessing_latency_ms": meta["preprocessing_latency_ms"],
                "fallback": meta["fallback_used"],
                "failure_reason": meta["failure_reason"],
                "warnings": warnings,
                "output_dir": str(out_dir.relative_to(project_root)).replace("\\", "/"),
            }

            summary[product_name][face_name] = summary_record

    summary_file = debug_root / "preprocessing_validation_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved cross-package summary to: {summary_file}")

if __name__ == "__main__":
    main()
