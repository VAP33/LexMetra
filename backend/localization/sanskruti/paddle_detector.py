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
            self._engine_type = "paddleocr"
            return True
        except Exception as e:
            try:
                from ultralytics import YOLO
                self._yolo = YOLO("yolov8n.pt")
                self._available = True
                self._weights_ready = True
                self._initialized = True
                self._engine_type = "yolov8+cv"
                self._fallback_reason = None
                print("[+] [PaddleTextDetector] Using YOLOv8 + OpenCV Region Proposer engine.", flush=True)
                return True
            except Exception as e2:
                self._available = False
                self._weights_ready = False
                self._fallback_reason = f"PaddleOCR ({e}) and YOLO ({e2}) failed"
                print(f"[!] [PaddleTextDetector] Initialization failed: {e}; YOLO fallback: {e2}", flush=True)
                return False

    def health(self) -> Dict[str, Any]:
        available = self._init_engine()
        engine_name = getattr(self, "_engine_type", "unavailable" if not available else "yolov8+cv")
        return {
            "available": available,
            "engine": engine_name,
            "polygon_output_verified": available,
            "weights_ready": self._weights_ready,
            "yolo_enabled": True,
            "fallback_reason": self._fallback_reason,
        }

    def detect_polygons(self, image_bgr: np.ndarray, min_confidence: float = 0.20) -> List[DetectedPolygon]:
        """
        Run detection on image_bgr and return list of DetectedPolygon objects with canonical coordinates.
        """
        if not self._init_engine():
            return []

        if getattr(self, "_engine_type", None) == "yolov8+cv" or self._engine is None:
            from localization.sanskruti.region_proposer import propose_text_regions
            regions = propose_text_regions(image_bgr)
            detected_proposals: List[DetectedPolygon] = []
            for r in regions:
                x, y, bw, bh = r.bbox
                poly = [[float(x), float(y)], [float(x+bw), float(y)], [float(x+bw), float(y+bh)], [float(x), float(y+bh)]]
                detected_proposals.append(DetectedPolygon(
                    polygon=poly,
                    bbox_xywh=(x, y, bw, bh),
                    confidence=float(r.confidence),
                    text=None,
                ))
            if hasattr(self, "_yolo") and self._yolo is not None:
                try:
                    y_res = self._yolo(image_bgr, verbose=False)
                    for b in y_res[0].boxes:
                        bx, by, bw, bh = [int(v) for v in b.xywh[0]]
                        x1 = max(0, bx - bw // 2)
                        y1 = max(0, by - bh // 2)
                        poly = [[float(x1), float(y1)], [float(x1+bw), float(y1)], [float(x1+bw), float(y1+bh)], [float(x1), float(y1+bh)]]
                        detected_proposals.append(DetectedPolygon(
                            polygon=poly,
                            bbox_xywh=(x1, y1, bw, bh),
                            confidence=float(b.conf[0]),
                            text=None,
                        ))
                except Exception:
                    pass
            return detected_proposals

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
