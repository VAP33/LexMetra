"""
Ultra-Fast OCR Service for Legal Metrology Packaged Commodities.

Provides high-performance, deep-learning based Optical Character Recognition:
- Primary: RapidOCR (ONNXRuntime-accelerated PP-OCR v4 DBNet + SVTR / CRNN)
  Sub-second inference (~0.2-0.5s) without CPU bottleneck or heavy DLL dependencies.
- Fallback: PaddleOCR / Pytesseract.

Replaces slow/unstable legacy pipelines with production-grade speed and accuracy
for curved packaging surfaces, fine-print declarations (MRP, Net Qty), mixed fonts,
and multi-surface packages.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np
from PIL import Image

try:
    from ocr_extraction import OcrLine
except ImportError:
    @dataclass
    class OcrLine:
        text: str
        bbox: Tuple[int, int, int, int]  # x, y, w, h
        confidence: float                 # 0..1


@dataclass
class PaddleOcrResult:
    """Detailed observation from the OCR engine."""
    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    polygon: List[List[float]]       # 4 corner points [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    source_crop_id: Optional[str] = None

    @property
    def x1(self) -> int:
        return self.bbox[0]

    @property
    def y1(self) -> int:
        return self.bbox[1]

    @property
    def x2(self) -> int:
        return self.bbox[0] + self.bbox[2]

    @property
    def y2(self) -> int:
        return self.bbox[1] + self.bbox[3]

    def to_ocr_line(self) -> OcrLine:
        """Convert to standard OcrLine consumed by field classification."""
        return OcrLine(
            text=self.text,
            bbox=self.bbox,
            confidence=self.confidence,
        )


class PaddleOCRService:
    """
    Singleton-friendly wrapper providing high-speed OCR (RapidOCR / PaddleOCR).
    """

    _instance: Optional["PaddleOCRService"] = None

    def __init__(
        self,
        lang: str = "en",
        use_angle_cls: bool = True,
        use_gpu: bool = False,
    ):
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self.use_gpu = use_gpu
        self._rapid_engine: Optional[Any] = None
        self._paddle_engine: Optional[Any] = None
        self._engine_type: Optional[str] = None  # "rapidocr" | "paddleocr" | "tesseract"
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "PaddleOCRService":
        if cls._instance is None:
            gpu_flag = os.environ.get("LMPC_OCR_USE_GPU", "").strip().lower() in ("1", "true", "yes")
            cls._instance = cls(lang="en", use_angle_cls=True, use_gpu=gpu_flag)
        return cls._instance

    def _ensure_engine(self) -> bool:
        """Lazy load OCR model into memory with fast-fail fallback."""
        if self._initialized and (self._rapid_engine or self._paddle_engine):
            return True

        # 1. Try RapidOCR (fastest ONNX backend)
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._rapid_engine = RapidOCR()
            self._engine_type = "rapidocr"
            self._initialized = True
            return True
        except Exception:
            self._rapid_engine = None

        # 2. Try PaddleOCR fallback
        try:
            os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            os.environ.setdefault("FLAGS_enable_pir_api", "0")
            os.environ.setdefault("FLAGS_use_mkldnn", "0")

            from paddleocr import PaddleOCR
            try:
                self._paddle_engine = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    lang=self.lang,
                )
            except TypeError:
                self._paddle_engine = PaddleOCR(lang=self.lang)

            self._engine_type = "paddleocr"
            self._initialized = True
            return True
        except Exception:
            self._paddle_engine = None

        # 3. Fallback to pytesseract
        try:
            import pytesseract
            self._engine_type = "tesseract"
            self._initialized = True
            return True
        except Exception:
            self._initialized = False
            return False

    def warmup(self) -> bool:
        """Pre-warm the OCR engine on a blank image so the first user scan is fast."""
        if self._ensure_engine():
            try:
                dummy = np.full((100, 300, 3), 255, dtype=np.uint8)
                cv2.putText(dummy, "MRP Rs 100.00", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
                self.read_text(dummy)
                return True
            except Exception:
                return False
        return False

    @property
    def is_available(self) -> bool:
        try:
            return self._ensure_engine()
        except Exception:
            return False

    @property
    def engine_type(self) -> str:
        self._ensure_engine()
        return self._engine_type or "unavailable"

    def read_text(
        self,
        image: Union[np.ndarray, Image.Image, str, Path],
        min_confidence: float = 0.20,
        offset: Tuple[int, int] = (0, 0),
    ) -> List[PaddleOcrResult]:
        """
        Run OCR on an image or region crop. Returns structured PaddleOcrResult list.
        """
        if not self._ensure_engine():
            return []

        # Convert input to numpy BGR array
        if isinstance(image, (str, Path)):
            img_bgr = cv2.imread(str(image))
            if img_bgr is None:
                return []
        elif isinstance(image, Image.Image):
            rgb = np.array(image.convert("RGB"))
            img_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        elif isinstance(image, np.ndarray):
            if image.ndim == 2:
                img_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            elif image.shape[2] == 4:
                img_bgr = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
            else:
                img_bgr = image
        else:
            return []

        if img_bgr.size == 0 or img_bgr.shape[0] < 6 or img_bgr.shape[1] < 6:
            return []

        dx, dy = offset
        results: List[PaddleOcrResult] = []

        # -------------------------------------------------------------------
        # Path 1: RapidOCR Engine (Ultra Fast ~0.2-0.5s)
        # -------------------------------------------------------------------
        if self._rapid_engine is not None:
            try:
                raw_results, _ = self._rapid_engine(img_bgr)
                if raw_results:
                    for item in raw_results:
                        try:
                            # Format: [dt_boxes, rec_res, score]
                            pts = np.array(item[0], dtype=np.float32)
                            text = str(item[1]).strip()
                            conf = float(item[2])

                            if not text or conf < min_confidence:
                                continue

                            x_min = int(np.min(pts[:, 0])) + dx
                            x_max = int(np.max(pts[:, 0])) + dx
                            y_min = int(np.min(pts[:, 1])) + dy
                            y_max = int(np.max(pts[:, 1])) + dy

                            bw = max(1, x_max - x_min)
                            bh = max(1, y_max - y_min)
                            poly_adj = [[float(p[0] + dx), float(p[1] + dy)] for p in pts]

                            results.append(
                                PaddleOcrResult(
                                    text=text,
                                    confidence=conf,
                                    bbox=(x_min, y_min, bw, bh),
                                    polygon=poly_adj,
                                )
                            )
                        except Exception:
                            continue

                    results.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
                    return results
            except Exception:
                pass  # Fall through to other engines if RapidOCR fails on specific image

        # -------------------------------------------------------------------
        # Path 2: PaddleOCR Fallback
        # -------------------------------------------------------------------
        if self._paddle_engine is not None:
            try:
                ocr_output = self._paddle_engine.ocr(img_bgr)
                if ocr_output:
                    # Format 1: PaddleOCR 3.x dict
                    first_item = ocr_output[0] if isinstance(ocr_output, list) and len(ocr_output) > 0 else None
                    if isinstance(first_item, dict) and "rec_texts" in first_item:
                        rec_texts = first_item.get("rec_texts", [])
                        rec_scores = first_item.get("rec_scores", [])
                        rec_polys = first_item.get("rec_polys", []) or first_item.get("dt_polys", [])

                        for idx, text in enumerate(rec_texts):
                            clean_text = str(text).strip()
                            conf = float(rec_scores[idx]) if idx < len(rec_scores) else 0.8
                            if not clean_text or conf < min_confidence:
                                continue

                            if idx < len(rec_polys):
                                pts = np.array(rec_polys[idx], dtype=np.float32)
                                x_min = int(np.min(pts[:, 0])) + dx
                                x_max = int(np.max(pts[:, 0])) + dx
                                y_min = int(np.min(pts[:, 1])) + dy
                                y_max = int(np.max(pts[:, 1])) + dy
                                poly_adj = [[float(p[0] + dx), float(p[1] + dy)] for p in pts]
                            else:
                                x_min, y_min = dx, dy
                                x_max, y_max = img_bgr.shape[1] + dx, img_bgr.shape[0] + dy
                                poly_adj = []

                            results.append(
                                PaddleOcrResult(
                                    text=clean_text,
                                    confidence=conf,
                                    bbox=(x_min, y_min, max(1, x_max - x_min), max(1, y_max - y_min)),
                                    polygon=poly_adj,
                                )
                            )
                        results.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
                        return results

                    # Format 2: PaddleOCR 2.x nested list
                    page_results = ocr_output[0] if isinstance(ocr_output, list) and len(ocr_output) > 0 else []
                    if isinstance(page_results, list):
                        for item in page_results:
                            try:
                                poly, (text, conf) = item
                                text_clean = str(text).strip()
                                confidence = float(conf)
                                if not text_clean or confidence < min_confidence:
                                    continue

                                pts = np.array(poly, dtype=np.float32)
                                x_min = int(np.min(pts[:, 0])) + dx
                                x_max = int(np.max(pts[:, 0])) + dx
                                y_min = int(np.min(pts[:, 1])) + dy
                                y_max = int(np.max(pts[:, 1])) + dy

                                results.append(
                                    PaddleOcrResult(
                                        text=text_clean,
                                        confidence=confidence,
                                        bbox=(x_min, y_min, max(1, x_max - x_min), max(1, y_max - y_min)),
                                        polygon=[[float(p[0] + dx), float(p[1] + dy)] for p in poly],
                                    )
                                )
                            except Exception:
                                continue
                        results.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
                        return results
            except Exception:
                pass

        # -------------------------------------------------------------------
        # Path 3: Pytesseract Fallback
        # -------------------------------------------------------------------
        try:
            import pytesseract
            pil_img = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
            data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT, config="--psm 6")
            for i, raw_text in enumerate(data.get("text", [])):
                t = str(raw_text).strip()
                if not t:
                    continue
                try:
                    c = float(data["conf"][i]) / 100.0
                except (ValueError, TypeError):
                    c = 0.5
                if c < min_confidence:
                    continue
                x = int(data["left"][i]) + dx
                y = int(data["top"][i]) + dy
                w = int(data["width"][i])
                h = int(data["height"][i])
                results.append(
                    PaddleOcrResult(
                        text=t,
                        confidence=c,
                        bbox=(x, y, w, h),
                        polygon=[[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
                    )
                )
            results.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
            return results
        except Exception:
            return results

    def read_crop_variants(
        self,
        variants: Sequence[np.ndarray],
        offset: Tuple[int, int] = (0, 0),
        min_confidence: float = 0.30,
    ) -> List[PaddleOcrResult]:
        """
        Run OCR on multiple preprocessed variants of the SAME crop,
        keeping the highest-confidence reading for each line.
        """
        all_readings: List[PaddleOcrResult] = []

        for variant in variants:
            res = self.read_text(variant, min_confidence=min_confidence, offset=offset)
            all_readings.extend(res)

        if not all_readings:
            return []

        # Deduplicate readings: group by approximate line height
        deduped: List[PaddleOcrResult] = []
        for r in sorted(all_readings, key=lambda x: x.confidence, reverse=True):
            overlap = False
            for d in deduped:
                rc_y = r.bbox[1] + (r.bbox[3] / 2)
                dc_y = d.bbox[1] + (d.bbox[3] / 2)
                if abs(rc_y - dc_y) < max(d.bbox[3], r.bbox[3]) * 0.5:
                    rc_x = r.bbox[0] + (r.bbox[2] / 2)
                    dc_x = d.bbox[0] + (d.bbox[2] / 2)
                    if abs(rc_x - dc_x) < max(d.bbox[2], r.bbox[2]) * 0.4:
                        overlap = True
                        break
            if not overlap:
                deduped.append(r)

        deduped.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
        return deduped


def get_paddle_ocr() -> PaddleOCRService:
    """Helper to retrieve standard fast OCR service instance."""
    return PaddleOCRService.get_instance()
