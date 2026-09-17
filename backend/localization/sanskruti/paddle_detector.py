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
        if self._initialized and self._available and self._engine is not None:
            return True

        try:
            # Ensure torch loads its C-libraries cleanly before paddle/paddleocr on Windows
            try:
                import torch
            except Exception:
                pass

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
            self._initialized = True
            self._fallback_reason = None
            return True
        except Exception as e:
            self._available = False
            self._weights_ready = False
            self._fallback_reason = f"PaddleOCR initialization failed: {e}"
            print(f"[!] [PaddleTextDetector] Initialization failed: {e}", flush=True)
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
            h, w = image_bgr.shape[:2]
            scale = 1.0
            max_side = 960
            if max(h, w) > max_side:
                scale = max_side / float(max(h, w))
                new_w = max(1, int(round(w * scale)))
                new_h = max(1, int(round(h * scale)))
                img_for_det = cv2.resize(image_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
            else:
                img_for_det = image_bgr

            ocr_output = self._engine.ocr(img_for_det)
            if not ocr_output:
                return []

            inv_scale = 1.0 / scale if scale > 0 else 1.0

            # Format 1: PaddleOCR 3.x dict
            first_item = ocr_output[0] if isinstance(ocr_output, list) and len(ocr_output) > 0 else None
            if isinstance(first_item, dict) and ("rec_polys" in first_item or "dt_polys" in first_item):
                rec_polys = first_item.get("rec_polys", []) or first_item.get("dt_polys", [])
                rec_scores = first_item.get("rec_scores", [])
                rec_texts = first_item.get("rec_texts", [])

                for idx, poly in enumerate(rec_polys):
                    pts = np.array(poly, dtype=np.float32) * inv_scale
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

                        pts = np.array(poly, dtype=np.float32) * inv_scale
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
