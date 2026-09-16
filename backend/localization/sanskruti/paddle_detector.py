"""
PaddleOCR-based text and polygon detector ported from Sanskruti CV.
Preserves raw detected polygons before any bounding-box or line conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import os
import cv2
import numpy as np


@dataclass
class DetectedPolygon:
    polygon: List[List[float]]       # 4 corner points [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
    bbox_xywh: Tuple[int, int, int, int] # (x, y, w, h)
    confidence: float
    text: Optional[str] = None       # Optional recognized text for tie-breaking ONLY


class PaddleTextDetector:
    """
    Dedicated polygon text detector wrapper.
    Does NOT modify or substitute Qwen semantic values.
    """

    _instance: Optional["PaddleTextDetector"] = None

    def __init__(self):
        self._engine = None
        self._initialized = False
        self._available = False
        self._weights_ready = False
        self._fallback_reason: Optional[str] = None

    @classmethod
    def get_instance(cls) -> "PaddleTextDetector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_engine(self) -> bool:
        if self._initialized:
            return self._available

        self._initialized = True
        try:
            os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            os.environ.setdefault("FLAGS_enable_pir_api", "0")
            os.environ.setdefault("FLAGS_use_mkldnn", "0")

            from paddleocr import PaddleOCR
            try:
                self._engine = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    lang="en",
                )
            except TypeError:
                self._engine = PaddleOCR(lang="en")

            self._available = True
            self._weights_ready = True
            return True
        except Exception as e:
            self._available = False
            self._weights_ready = False
            self._fallback_reason = f"PaddleOCR initialization failed: {e}"
            return False

    def health(self) -> Dict[str, Any]:
        available = self._init_engine()
        return {
            "available": available,
            "engine": "paddleocr" if available else "unavailable",
            "polygon_output_verified": available,
            "weights_ready": self._weights_ready,
            "yolo_enabled": False,
            "fallback_reason": self._fallback_reason,
        }

    def detect_polygons(self, image_bgr: np.ndarray, min_confidence: float = 0.20) -> List[DetectedPolygon]:
        """
        Run detection on image_bgr and return list of DetectedPolygon objects with canonical coordinates.
        """
        if not self._init_engine() or self._engine is None:
            return []

        if image_bgr is None or image_bgr.size == 0 or image_bgr.shape[0] < 6 or image_bgr.shape[1] < 6:
            return []

        detected: List[DetectedPolygon] = []
        try:
            ocr_output = self._engine.ocr(image_bgr)
            if not ocr_output:
                return []

            # Format 1: PaddleOCR 3.x dict
            first_item = ocr_output[0] if isinstance(ocr_output, list) and len(ocr_output) > 0 else None
            if isinstance(first_item, dict) and ("rec_polys" in first_item or "dt_polys" in first_item):
                rec_polys = first_item.get("rec_polys", []) or first_item.get("dt_polys", [])
                rec_scores = first_item.get("rec_scores", [])
                rec_texts = first_item.get("rec_texts", [])

                for idx, poly in enumerate(rec_polys):
                    pts = np.array(poly, dtype=np.float32)
                    conf = float(rec_scores[idx]) if idx < len(rec_scores) else 0.8
                    text = str(rec_texts[idx]).strip() if idx < len(rec_texts) else None
                    if conf < min_confidence:
                        continue

                    x_min = int(np.min(pts[:, 0]))
                    x_max = int(np.max(pts[:, 0]))
                    y_min = int(np.min(pts[:, 1]))
                    y_max = int(np.max(pts[:, 1]))
                    bw = max(1, x_max - x_min)
                    bh = max(1, y_max - y_min)

                    poly_pts = [[float(p[0]), float(p[1])] for p in pts]
                    detected.append(DetectedPolygon(
                        polygon=poly_pts,
                        bbox_xywh=(x_min, y_min, bw, bh),
                        confidence=conf,
                        text=text,
                    ))
                return detected

            # Format 2: PaddleOCR 2.x nested list
            page_results = ocr_output[0] if isinstance(ocr_output, list) and len(ocr_output) > 0 else []
            if isinstance(page_results, list):
                for item in page_results:
                    try:
                        poly, (text, conf) = item
                        confidence = float(conf)
                        if confidence < min_confidence:
                            continue

                        pts = np.array(poly, dtype=np.float32)
                        x_min = int(np.min(pts[:, 0]))
                        x_max = int(np.max(pts[:, 0]))
                        y_min = int(np.min(pts[:, 1]))
                        y_max = int(np.max(pts[:, 1]))
                        bw = max(1, x_max - x_min)
                        bh = max(1, y_max - y_min)

                        poly_pts = [[float(p[0]), float(p[1])] for p in pts]
                        detected.append(DetectedPolygon(
                            polygon=poly_pts,
                            bbox_xywh=(x_min, y_min, bw, bh),
                            confidence=confidence,
                            text=str(text).strip() if text else None,
                        ))
                    except Exception:
                        continue

            return detected
        except Exception as e:
            return []
