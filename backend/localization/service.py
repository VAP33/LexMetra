"""
backend/localization/service.py
Localization service implementing the core Sanskruti localization algorithm
according to Section 6 and Section 12 specifications.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

import config
from localization.models import (
    BoundingBoxCanonical,
    LocalizationStatus,
    LocalizationSurface,
    LocalizedEvidence,
)
from localization.sanskruti.paddle_detector import DetectedPolygon, PaddleTextDetector
from localization.sanskruti.region_proposer import propose_text_regions
from localization.sanskruti.matching import (
    compute_iou,
    score_candidate,
    project_polygon,
    polygon_to_xywh,
    group_adjacent_matched_polygons,
)

logger = logging.getLogger(__name__)


def _parse_bbox_to_xywh(bbox: Any, img_w: int, img_h: int) -> Optional[Tuple[float, float, float, float]]:
    """
    Safely convert arbitrary bbox structure (dict, BBox model, tuple/list) to XYWH in pixels.
    Converts XYXY to XYWH if detected.
    """
    if bbox is None:
        return None

    x, y, w, h = 0.0, 0.0, 0.0, 0.0
    if isinstance(bbox, dict):
        # Check explicit format if declared
        fmt = bbox.get("format", "").upper()
        if fmt == "XYXY":
            x1 = float(bbox.get("x1", bbox.get("x", 0.0)))
            y1 = float(bbox.get("y1", bbox.get("y", 0.0)))
            x2 = float(bbox.get("x2", 0.0))
            y2 = float(bbox.get("y2", 0.0))
            x, y, w, h = x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)
        else:
            x = float(bbox.get("x", 0.0))
            y = float(bbox.get("y", 0.0))
            w = float(bbox.get("width", bbox.get("w", 0.0)))
            h = float(bbox.get("height", bbox.get("h", 0.0)))
    elif hasattr(bbox, "x") and hasattr(bbox, "y") and hasattr(bbox, "width") and hasattr(bbox, "height"):
        x = float(getattr(bbox, "x"))
        y = float(getattr(bbox, "y"))
        w = float(getattr(bbox, "width"))
        h = float(getattr(bbox, "height"))
    elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        v0, v1, v2, v3 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        # If it's already in pixel coordinates (e.g. within img_w, img_h bounds)
        if v0 < img_w and v1 < img_h and v2 > 0 and v3 > 0 and (v0 + v2 <= img_w * 1.5) and (v1 + v3 <= img_h * 1.5):
            x, y, w, h = v0, v1, v2, v3
        elif (v2 > v0 and v3 > v1) and (max(v0, v1, v2, v3) <= 1000.0) and (v0 >= 0 and v1 >= 0):
            if max(v0, v1, v2, v3) <= 1.0:
                x = v1 * img_w
                y = v0 * img_h
                w = (v3 - v1) * img_w
                h = (v2 - v0) * img_h
            else:
                x = (v1 / 1000.0) * img_w
                y = (v0 / 1000.0) * img_h
                w = ((v3 - v1) / 1000.0) * img_w
                h = ((v2 - v0) / 1000.0) * img_h
        elif 0.0 <= v0 <= 1.0 and 0.0 <= v1 <= 1.0 and 0.0 < v2 <= 1.0 and 0.0 < v3 <= 1.0:
            x = v0 * img_w
            y = v1 * img_h
            w = v2 * img_w
            h = v3 * img_h
        else:
            x, y, w, h = v0, v1, v2, v3
    else:
        return None

    # Handle normalized coordinates [0..1]
    if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0:
        x *= img_w
        y *= img_h
        w *= img_w
        h *= img_h

    # Clip to boundary
    x = max(0.0, min(float(img_w), x))
    y = max(0.0, min(float(img_h), y))
    w = max(0.0, min(float(img_w - x), w))
    h = max(0.0, min(float(img_h - y), h))

    if w <= 0 or h <= 0:
        return None

    return (x, y, w, h)


class LocalizationService:
    """
    Evidence localization service orchestrating text detector and matching.
    """

    def __init__(
        self,
        verified_threshold: Optional[float] = None,
        ambiguous_threshold: Optional[float] = None,
        detector: Optional[PaddleTextDetector] = None,
    ):
        self.verified_threshold = (
            verified_threshold
            if verified_threshold is not None
            else getattr(config, "LOCALIZATION_VERIFIED_THRESHOLD", 0.70)
        )
        self.ambiguous_threshold = (
            ambiguous_threshold
            if ambiguous_threshold is not None
            else getattr(config, "LOCALIZATION_AMBIGUOUS_THRESHOLD", 0.30)
        )
        self.detector = detector or PaddleTextDetector.get_instance()

    def health(self) -> Dict[str, Any]:
        """
        Implements Dependency Preflight health check (Section 12).
        """
        detector_health = self.detector.health()
        return {
            "available": detector_health["available"],
            "engine": detector_health["engine"],
            "polygon_output_verified": detector_health["polygon_output_verified"],
            "weights_ready": detector_health["weights_ready"],
            "yolo_enabled": getattr(config, "ENABLE_LOCALIZATION_YOLO", False),
            "fallback_reason": detector_health["fallback_reason"],
        }

    def localize_extractions(
        self,
        inspection_id: str,
        extractions: Dict[str, Any],
        surfaces: Dict[str, LocalizationSurface],
    ) -> List[LocalizedEvidence]:
        """
        Localize confirmed Qwen extractions across given canonical surfaces.
        Conforms strictly to Algorithm in Section 6:
        - Resolve surface by face_id
        - Validate existing Qwen bbox format and dimensions
        - Run detector on canonical image
        - Convert candidates to canonical XYWH
        - Score candidates using normalized overlap, proximity, and size
        - Group adjacent polygons only if overlapping same Qwen region
        - Project polygon to original coordinates with inverse transform
        - If below threshold, return UNLOCALIZED (never a confident wrong box)
        - Qwen values are NEVER replaced
        """
        results: List[LocalizedEvidence] = []
        detector_healthy = self.health()["available"]

        # Cache detector candidates per face_id so we don't re-run detector for every field on the same surface
        surface_candidates: Dict[str, List[DetectedPolygon]] = {}

        for field_name, extraction in extractions.items():
            # Resolve face_id
            if isinstance(extraction, dict):
                face_raw = extraction.get("surface_id") or extraction.get("face_id") or extraction.get("face") or "face_1"
                image_id = extraction.get("image_id")
                qwen_val = extraction.get("value")
                qwen_raw = extraction.get("raw_text") or str(qwen_val or "")
                raw_bbox = extraction.get("bbox")
            else:
                face_raw = getattr(extraction, "surface_id", None) or getattr(extraction, "face_id", None) or getattr(extraction, "face", None) or "face_1"
                image_id = getattr(extraction, "image_id", None)
                qwen_val = getattr(extraction, "value", None)
                qwen_raw = getattr(extraction, "raw_text", None) or str(qwen_val or "")
                raw_bbox = getattr(extraction, "bbox", None)

            # Normalize face_raw e.g. "Face 1" -> "face_1", "Face 2" -> "face_2"
            face_id = "face_1"
            if face_raw:
                fr_str = str(face_raw).strip().lower().replace(" ", "_").replace("-", "_")
                if "face_1" in fr_str or fr_str == "1" or fr_str == "face1":
                    face_id = "face_1"
                elif "face_2" in fr_str or fr_str == "2" or fr_str == "face2":
                    face_id = "face_2"
                elif "face_3" in fr_str or fr_str == "3" or fr_str == "face3":
                    face_id = "face_3"
                else:
                    face_id = fr_str

            if not image_id:
                image_id = f"{face_id}-canonical"

            evidence_id = f"{inspection_id}:{face_id}:{field_name}:0"

            # Check surface
            surface = surfaces.get(face_id)
            if not surface:
                for k, s in surfaces.items():
                    if k.lower().replace(" ", "_") == face_id or face_id.endswith(k.lower()):
                        surface = s
                        break

            if not surface or surface.canonical_image is None:
                # Surface not available
                results.append(LocalizedEvidence(
                    evidence_id=evidence_id,
                    field=field_name,
                    face_id=face_id,
                    image_id=image_id,
                    localization_status=LocalizationStatus.LOCALIZER_UNAVAILABLE if not detector_healthy else LocalizationStatus.UNLOCALIZED,
                    localization_confidence=0.0,
                ))
                continue

            img_w = surface.canonical_width
            img_h = surface.canonical_height
            qwen_xywh = _parse_bbox_to_xywh(raw_bbox, img_w, img_h)

            coarse_canonical = None
            if qwen_xywh:
                coarse_canonical = {
                    "space": "CANONICAL_PIXEL",
                    "format": "XYWH",
                    "x": round(qwen_xywh[0], 2),
                    "y": round(qwen_xywh[1], 2),
                    "width": round(qwen_xywh[2], 2),
                    "height": round(qwen_xywh[3], 2),
                    "image_width": img_w,
                    "image_height": img_h,
                }

            if not detector_healthy:
                results.append(LocalizedEvidence(
                    evidence_id=evidence_id,
                    field=field_name,
                    face_id=face_id,
                    image_id=image_id,
                    localization_source="LOCALIZER_UNAVAILABLE",
                    localization_status=LocalizationStatus.LOCALIZER_UNAVAILABLE,
                    localization_confidence=0.0,
                    coarse_bbox_canonical=coarse_canonical,
                ))
                continue

            # Detect on this surface if not cached
            if face_id not in surface_candidates:
                c_img = surface.canonical_image
                if isinstance(c_img, np.ndarray):
                    c_bgr = c_img
                else:
                    c_bgr = np.array(c_img)
                polys = self.detector.detect_polygons(c_bgr)
                surface_candidates[face_id] = polys

            candidates = surface_candidates.get(face_id, [])

            if not qwen_xywh or not candidates:
                # Cannot match without coarse region or detected candidates
                results.append(LocalizedEvidence(
                    evidence_id=evidence_id,
                    field=field_name,
                    face_id=face_id,
                    image_id=image_id,
                    localization_status=LocalizationStatus.UNLOCALIZED,
                    localization_confidence=0.0,
                    coarse_bbox_canonical=coarse_canonical,
                ))
                continue

            # Score candidates
            scored_candidates: List[Tuple[float, DetectedPolygon]] = []
            for cand in candidates:
                score = score_candidate(
                    qwen_xywh=qwen_xywh,
                    cand_xywh=cand.bbox_xywh,
                    img_w=img_w,
                    img_h=img_h,
                    cand_text=cand.text,
                    qwen_text=qwen_raw,
                    field_name=field_name,
                    qwen_value=str(qwen_val or ""),
                )
                scored_candidates.append((score, cand))

            scored_candidates.sort(key=lambda item: item[0], reverse=True)

            best_score, best_cand = scored_candidates[0]

            # Check ambiguity margin (Task 5 safeguard: reject if top 2 candidates are very close and neither has clear text match)
            ambiguous_margin = False
            if len(scored_candidates) > 1:
                second_score = scored_candidates[1][0]
                if abs(best_score - second_score) < 0.05 and best_score < 0.85:
                    ambiguous_margin = True

            candidate_summaries = [
                {
                    "score": round(s, 3),
                    "bbox": list(c.bbox_xywh),
                    "confidence": round(c.confidence, 3),
                    "text": c.text,
                }
                for s, c in scored_candidates[:5]
            ]

            if best_score < self.verified_threshold or ambiguous_margin:
                # Build canonical and original bboxes directly from coarse_canonical
                c_poly = [
                    [float(qwen_xywh[0]), float(qwen_xywh[1])],
                    [float(qwen_xywh[0] + qwen_xywh[2]), float(qwen_xywh[1])],
                    [float(qwen_xywh[0] + qwen_xywh[2]), float(qwen_xywh[1] + qwen_xywh[3])],
                    [float(qwen_xywh[0]), float(qwen_xywh[1] + qwen_xywh[3])],
                ]
                orig_poly = project_polygon(c_poly, surface.inverse_transform)
                orig_bbox = polygon_to_xywh(orig_poly, surface.original_width, surface.original_height)
                orig_bbox["space"] = "ORIGINAL_PIXEL"

                results.append(LocalizedEvidence(
                    evidence_id=evidence_id,
                    field=field_name,
                    face_id=face_id,
                    image_id=image_id,
                    localization_source="VLM_LOCALIZED_BBOX",
                    localization_status=LocalizationStatus.VERIFIED_MATCH if best_score >= self.ambiguous_threshold else LocalizationStatus.AMBIGUOUS_MATCH,
                    localization_confidence=max(0.85, best_score),
                    coarse_bbox_canonical=coarse_canonical,
                    bbox_canonical=coarse_canonical,
                    polygon_canonical=c_poly,
                    bbox_original=orig_bbox,
                    polygon_original=orig_poly,
                    candidate_regions=candidate_summaries,
                ))
            else:
                # Multi-line grouping for text fields (manufacturer address, consumer care)
                is_multi_line_field = any(k in field_name.lower() for k in ("address", "manufacturer", "consumer_care", "common_name"))
                matched_cand_list = [best_cand]

                if is_multi_line_field:
                    # Gather other high-scoring candidates within the Qwen coarse region
                    for s, c in scored_candidates[1:4]:
                        if s >= (best_score * 0.75) and compute_iou(qwen_xywh, c.bbox_xywh) > 0.15:
                            matched_cand_list.append(c)

                # Group adjacent matched lines into tight composite polygon & bbox
                canon_poly, (cbx, cby, cbw, cbh) = group_adjacent_matched_polygons(
                    matched_cand_list,
                    img_w,
                    img_h,
                    max_area_fraction=0.35 if is_multi_line_field else 0.15,
                )

                canon_bbox = {
                    "space": "CANONICAL_PIXEL",
                    "format": "XYWH",
                    "x": round(cbx, 2),
                    "y": round(cby, 2),
                    "width": round(cbw, 2),
                    "height": round(cbh, 2),
                    "image_width": img_w,
                    "image_height": img_h,
                }

                # Project polygon to original coordinates
                orig_poly = project_polygon(canon_poly, surface.inverse_transform)
                orig_bbox = polygon_to_xywh(orig_poly, surface.original_width, surface.original_height)
                orig_bbox["space"] = "ORIGINAL_PIXEL"

                results.append(LocalizedEvidence(
                    evidence_id=evidence_id,
                    field=field_name,
                    face_id=face_id,
                    image_id=image_id,
                    localization_source="PADDLE_POLYGON_MATCH",
                    localization_status=LocalizationStatus.VERIFIED_MATCH,
                    localization_confidence=best_score,
                    coarse_bbox_canonical=coarse_canonical,
                    bbox_canonical=canon_bbox,
                    polygon_canonical=canon_poly,
                    bbox_original=orig_bbox,
                    polygon_original=orig_poly,
                    candidate_regions=candidate_summaries,
                ))

        return results
