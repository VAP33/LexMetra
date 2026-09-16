"""
Demonstration script for the 10-Stage Legal Metrology Computer Vision Pipeline.
Runs on compliant and violation packages and prints the full structured report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import cv2
from cv_pipeline import run_cv_pipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = PROJECT_ROOT / "dataset" / "images"
OUTPUT_DIR = PROJECT_ROOT / "backend" / "uploads" / "cv_demo_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def test_sample(image_path: Path, label: str):
    print("=" * 70)
    print(f"RUNNING CV PIPELINE ON: {image_path.name} ({label})")
    print("=" * 70)

    result = run_cv_pipeline(image_path, product_category="beverage")

    print("\n--- Pipeline Execution Notes ---")
    for note in result.execution_notes:
        print(f"  * {note}")

    print(f"\n--- Detected Regions ({len(result.detected_regions)}) ---")
    for r in result.detected_regions[:6]:
        print(f"  * Class: {r.class_name:<18} Conf: {r.confidence:.2f}  BBox: {r.bbox}")

    print("\n--- Extracted Structured Declarations (Stage 8 JSON) ---")
    print(json.dumps(result.structured_data.to_dict(), indent=2))

    print(f"\n--- Legal Metrology Verdict (Stage 9): {result.compliance_verdict} ---")
    for fact in result.compliance_facts:
        status_sym = "[PASS]" if fact["status"] == "PASS" else "[FAIL]"
        print(f"  {status_sym:<7} {fact['rule']:<14} {fact['field']:<16}: {fact['description']}")

    # Save visual overlay
    if result.visual_overlay_bgr is not None:
        out_path = OUTPUT_DIR / f"overlay_{image_path.stem}.jpg"
        cv2.imwrite(str(out_path), result.visual_overlay_bgr)
        print(f"\n[OK] Visual Compliance Overlay saved to: {out_path}")


if __name__ == "__main__":
    compliant_img = IMAGES_DIR / "prod001_compliant.png"
    violation_img = IMAGES_DIR / "prod001_violation_missing_mfg_date.png"

    if compliant_img.exists():
        test_sample(compliant_img, "COMPLIANT PACKAGE")
    if violation_img.exists():
        test_sample(violation_img, "VIOLATION PACKAGE")
