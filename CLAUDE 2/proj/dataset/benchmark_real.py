"""
Real-photo benchmark: measures the vision pipeline against a small, honestly
hand-annotated ground-truth set (real_photos_ground_truth.json) - NOT the
synthetic dataset. See that file's "_notes" for exactly what is and is not
being claimed.

Usage:
    cd backend && python3 ../dataset/benchmark_real.py

This script does not require a database - it exercises vision_pipeline.py
directly, which is the same function main.py's endpoints call.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from vision_pipeline import run_vision_pipeline  # noqa: E402

DATASET_DIR = Path(__file__).resolve().parent
PHOTOS_DIR = DATASET_DIR / "real_photos"
GROUND_TRUTH_PATH = DATASET_DIR / "real_photos_ground_truth.json"


def _field_matches(field: str, gt: dict, extracted: dict) -> str:
    """Returns 'correct', 'incorrect', 'not_observed_correct',
    'not_observed_incorrect', or 'skipped'."""
    if gt.get("ambiguous_do_not_score"):
        return "skipped"

    entry = extracted.get(field)
    is_not_on_surface = gt.get("not_on_this_surface", False)

    if entry is None:
        return "not_observed_correct" if is_not_on_surface else "not_observed_incorrect"

    if is_not_on_surface:
        # Vision found SOMETHING for a field that shouldn't be on this panel
        # at all - a false positive, exactly the "barcode noise -> net
        # quantity" failure mode this benchmark exists to catch.
        return "incorrect"

    value = str(entry.get("value", ""))
    numeric = entry.get("numeric_value")

    if "value" in gt and isinstance(gt["value"], (int, float)):
        if numeric is not None and abs(float(numeric) - float(gt["value"])) < 0.01:
            return "correct"
        return "incorrect"

    if "value_contains" in gt:
        needle = gt["value_contains"].lower()
        return "correct" if needle.lower() in value.lower() else "incorrect"

    return "skipped"


def run_benchmark() -> dict:
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text())["images"]

    results = []
    tally = {"correct": 0, "incorrect": 0, "not_observed_correct": 0,
             "not_observed_incorrect": 0, "skipped": 0}
    barcode_tally = {"correct": 0, "incorrect": 0, "not_found": 0, "skipped": 0}

    for item in ground_truth:
        photo_path = PHOTOS_DIR / item["file"]
        if not photo_path.exists():
            print(f"MISSING PHOTO, skipping: {item['file']}")
            continue

        pil_img = Image.open(photo_path)
        img_bgr = cv2.imread(str(photo_path))

        vision = run_vision_pipeline(pil_img, img_bgr)
        extracted = vision.classified_fields

        per_image = {"image_id": item["image_id"], "fields": {}}

        for field, gt in item["ground_truth"].items():
            if field == "barcode":
                if gt.get("ambiguous_do_not_score"):
                    barcode_tally["skipped"] += 1
                    continue
                if vision.barcode is None:
                    barcode_tally["not_found"] += 1
                    per_image["fields"]["barcode"] = "not_found"
                elif vision.barcode.data == gt.get("value"):
                    barcode_tally["correct"] += 1
                    per_image["fields"]["barcode"] = "correct"
                else:
                    barcode_tally["incorrect"] += 1
                    per_image["fields"]["barcode"] = f"incorrect (got {vision.barcode.data})"
                continue

            outcome = _field_matches(field, gt, extracted)
            tally[outcome] += 1
            per_image["fields"][field] = outcome

        results.append(per_image)

    return {"per_image": results, "field_tally": tally, "barcode_tally": barcode_tally}


if __name__ == "__main__":
    report = run_benchmark()
    print(json.dumps(report, indent=2))

    t = report["field_tally"]
    scored = t["correct"] + t["incorrect"] + t["not_observed_correct"] + t["not_observed_incorrect"]
    print("\n--- SUMMARY (small, hand-annotated real-photo spot check - not a statistical benchmark) ---")
    print(f"Fields scored: {scored} (skipped as ambiguous/unscoreable: {t['skipped']})")
    print(f"  Correct value extracted:            {t['correct']}")
    print(f"  Incorrect value extracted:          {t['incorrect']}  <- vision errors that could mislead the legal engine")
    print(f"  Correctly reported NOT_OBSERVED:    {t['not_observed_correct']}")
    print(f"  Incorrectly reported NOT_OBSERVED:  {t['not_observed_incorrect']}  <- missed a field that WAS on the panel")
    b = report["barcode_tally"]
    print(f"Barcode: correct={b['correct']} incorrect={b['incorrect']} not_found={b['not_found']} skipped={b['skipped']}")
