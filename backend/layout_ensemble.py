"""Layout detection ensemble (CV-01).

Default production path remains classical OpenCV in region_detection.py.
A trained YOLO model is NOT shipped: available labels are synthetic-heavy and
real photos are too few for an honest accuracy claim.

detect_layout() is the additive seam. When LMPC_ENABLE_YOLO_LAYOUT is true AND
a weights file exists, a future detector can be called as a validator. Until
then the classical result is returned unchanged.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np

from dataset_paths import dataset_inventory
from region_detection import DetectionResult, detect_regions

YOLO_WEIGHTS = Path(__file__).resolve().parent / "models" / "layout_yolov8n.pt"


def yolo_readiness() -> dict[str, Any]:
    inventory = dataset_inventory()
    enough = (
        inventory["real_image_files"] >= 200
        and inventory["annotation_records"] >= 200
        and not inventory["annotations_marked_synthetic"]
    )
    return {
        "status": "data_constrained_classical_cv_retained",
        "yolo_weights_present": YOLO_WEIGHTS.is_file(),
        "ship_trained_model": False,
        "reason": (
            "Synthetic annotations plus a handful of real photos are not enough "
            "to claim a trained detector beats classical CV on the Traya photos. "
            "No undertrained weights are shipped."
        ),
        "inventory": inventory,
        "enough_for_honest_finetune": enough,
    }


def detect_layout(
    image: np.ndarray,
    *,
    include_stickers: bool = False,
    yolo_result: Optional[DetectionResult] = None,
) -> DetectionResult:
    """Classical CV plus optional YOLO validator. YOLO never replaces fallback."""
    classical = detect_regions(image, include_stickers=include_stickers)
    if yolo_result is None or not yolo_result.regions:
        classical.notes.append(
            "CV-01: YOLO not applied; classical CV retained (data-constrained)."
        )
        return classical
    seen = {(tuple(r.bbox), r.region_type) for r in classical.regions}
    for region in yolo_result.regions:
        key = (tuple(region.bbox), region.region_type)
        if key not in seen:
            classical.regions.append(region)
            seen.add(key)
    classical.notes.append("CV-01: classical CV plus YOLO validator regions.")
    return classical
