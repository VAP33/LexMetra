"""
Single shared vision pipeline used by BOTH /scan (single-image) and
/sessions/{id}/captures (multi-surface). Having one function here, instead
of duplicating this sequence inline in main.py twice, is what "do not create
parallel duplicate implementations" means in practice for this change.

Pipeline per captured image:

    image
      -> run_ocr()                      whole-image Tesseract pass (existing)
      -> run_orientation_aware_ocr()     per-region rotation-corrected pass,
                                          recovers sideways/rotated text the
                                          whole-image pass misses (see
                                          orientation_ocr.py)
      -> ocr_engines.run_paddleocr()    optional second engine (no-op unless
                                          OCR_ENABLE_PADDLE=true and the
                                          model is reachable)
      -> evidence_fusion.classify_multi_engine()   per-field agreement/
                                          conflict -> EvidenceVerification
      -> image_quality.assess_field_quality_map()  region-aware quality,
                                          used to cap verification (glare
                                          over a field must not be hidden by
                                          a fine global image score)
      -> product_identity.best_barcode() optional, advisory only
      -> image_quality.build_recapture_guidance()  actionable guidance text

This module does not touch persistence or the legal engine - it only
produces the evidence dict that _prepare_extractions()/bridge_classified_
fields() already know how to consume, so the rest of the request-handling
code in main.py is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

import image_quality as image_quality_module
import ocr_engines
import product_identity
from evidence_fusion import classify_multi_engine
from ocr_extraction import OcrLine, run_ocr
from orientation_ocr import run_orientation_aware_ocr


def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2, bx2, by2 = ax + aw, ay + ah, bx + bw, by + bh
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def _merge_orientation_lines_into_tesseract(
    base_lines: List[OcrLine], oriented_lines,
) -> List[OcrLine]:
    """
    Add orientation-recovered lines to the whole-image Tesseract lines,
    skipping any that clearly duplicate a line the whole-image pass already
    read correctly (same location, similar text) so fields are not
    double-counted as if two engines had read them.
    """
    merged = list(base_lines)
    for oline in oriented_lines:
        candidate = oline.as_ocr_line()
        is_duplicate = any(
            _iou(candidate.bbox, existing.bbox) > 0.5
            and existing.text.strip().lower() == candidate.text.strip().lower()
            for existing in base_lines
        )
        if not is_duplicate and candidate.text.strip():
            merged.append(candidate)
    return merged


@dataclass
class VisionPipelineResult:
    classified_fields: Dict[str, dict]
    ocr_lines: List[OcrLine]
    lines_by_engine: Dict[str, List[OcrLine]]
    field_quality: Dict[str, "image_quality_module.ImageQuality"] = field(default_factory=dict)
    barcode: Optional[product_identity.BarcodeResult] = None
    engine_status: List[ocr_engines.EngineAvailability] = field(default_factory=list)


def run_vision_pipeline(pil_img: Image.Image, img_bgr: np.ndarray) -> VisionPipelineResult:
    tesseract_lines = run_ocr(pil_img)

    try:
        oriented_lines = run_orientation_aware_ocr(pil_img)
    except Exception:
        oriented_lines = []
    tesseract_lines_augmented = _merge_orientation_lines_into_tesseract(
        tesseract_lines, oriented_lines,
    )

    lines_by_engine: Dict[str, List[OcrLine]] = {"tesseract": tesseract_lines_augmented}
    paddle_lines = ocr_engines.run_paddleocr(pil_img)
    if paddle_lines:
        lines_by_engine["paddleocr"] = [
            OcrLine(text=l.text, bbox=l.bbox, confidence=l.confidence) for l in paddle_lines
        ]

    fused = classify_multi_engine(lines_by_engine)

    field_bboxes = {
        f: entry["bbox"] for f, entry in fused.items()
        if entry.get("bbox") is not None
    }
    field_quality = image_quality_module.assess_field_quality_map(img_bgr, field_bboxes)

    # Re-run the low-quality verification cap now that we have REGION (not
    # just whole-image) quality - classify_multi_engine already applies this
    # when given region_quality_by_field up front, but bboxes are only known
    # after fusion has run once, so we do a second lightweight pass here.
    for f, q in field_quality.items():
        entry = fused.get(f)
        if not entry:
            continue
        if q.status == image_quality_module.EvidenceStatus.LOW_QUALITY and entry.get(
            "verification"
        ) in ("VERIFIED", "CORROBORATED"):
            entry["verification"] = "UNCERTAIN"
            entry["confidence"] = min(float(entry.get("confidence", 0.0)), 0.55)
            entry.setdefault("notes", []).extend(q.notes)

    barcode = product_identity.best_barcode(img_bgr)

    return VisionPipelineResult(
        classified_fields=fused,
        ocr_lines=tesseract_lines_augmented,
        lines_by_engine=lines_by_engine,
        field_quality=field_quality,
        barcode=barcode,
        engine_status=ocr_engines.engine_status_report(),
    )
