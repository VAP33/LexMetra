"""
backend/localization/sanskruti/__init__.py
Exposes ported Sanskruti CV modules under a clean namespace.
"""

from localization.sanskruti.paddle_detector import DetectedPolygon, PaddleTextDetector
from localization.sanskruti.region_proposer import RegionProposal, propose_text_regions
from localization.sanskruti.orientation import Orientation, rotate_crop, estimate_text_axis
from localization.sanskruti.matching import (
    compute_iou,
    score_candidate,
    project_polygon,
    polygon_to_xywh,
)

__all__ = [
    "DetectedPolygon",
    "PaddleTextDetector",
    "RegionProposal",
    "propose_text_regions",
    "Orientation",
    "rotate_crop",
    "estimate_text_axis",
    "compute_iou",
    "score_candidate",
    "project_polygon",
    "polygon_to_xywh",
]
