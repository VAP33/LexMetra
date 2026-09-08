"""
Multi-engine OCR abstraction.

Design goals (see PROJECT_STATE.md / master spec Part 5-6):
- Tesseract remains the default, always-on OCR source (ocr_extraction.py).
- PaddleOCR is an OPTIONAL second engine, enabled only via the
  OCR_ENABLE_PADDLE=true environment variable. It is loaded lazily so
  importing this module (or starting the backend) never requires PaddleOCR
  to be installed.
- PaddleOCR fails CLOSED: any import error, model-download failure, or
  inference exception is caught, logged into `EngineAvailability.reason`,
  and the pipeline falls back to Tesseract-only. A vision engine must never
  crash an inspection because an optional dependency is missing.

Honest limitation, verified in this build environment: PaddleOCR's model
weights are fetched at first use from paddleocr.bj.bcebos.com. In any
network-restricted deployment (this development sandbox included - verified
via a direct HTTPS probe, which returned a proxy-level 403) that download
will fail even though `pip install paddleocr` itself succeeds. This module
is written and tested against that reality: the adapter is real code, not a
stub, but PADDLE AVAILABILITY MUST BE VERIFIED IN YOUR ACTUAL DEPLOYMENT
TARGET before you rely on it. Nothing in this codebase claims PaddleOCR
results without having actually produced them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image

from ocr_extraction import OcrLine, run_ocr as _run_tesseract

TESSERACT = "tesseract"
PADDLEOCR = "paddleocr"


@dataclass
class EngineTextLine:
    text: str
    bbox: Tuple[int, int, int, int]  # x, y, w, h in original-image pixels
    confidence: float  # 0..1
    engine: str


@dataclass
class EngineAvailability:
    engine: str
    enabled: bool
    available: bool
    reason: str = ""


_paddle_singleton = None
_paddle_init_failed_reason: Optional[str] = None


def _paddle_enabled() -> bool:
    return os.environ.get("OCR_ENABLE_PADDLE", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _get_paddle_engine():
    """
    Lazily construct and cache a PaddleOCR instance. Returns None (and
    records the reason) on any failure - import missing, model download
    blocked, unsupported platform, etc. Never raises.
    """
    global _paddle_singleton, _paddle_init_failed_reason

    if _paddle_singleton is not None:
        return _paddle_singleton
    if _paddle_init_failed_reason is not None:
        return None

    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised only when installed
        _paddle_init_failed_reason = f"paddleocr not importable: {exc}"
        return None

    try:
        _paddle_singleton = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        return _paddle_singleton
    except Exception as exc:  # pragma: no cover - network/model dependent
        _paddle_init_failed_reason = f"PaddleOCR init failed (model download/runtime): {exc}"
        return None


def paddle_availability() -> EngineAvailability:
    enabled = _paddle_enabled()
    if not enabled:
        return EngineAvailability(
            engine=PADDLEOCR, enabled=False, available=False,
            reason="OCR_ENABLE_PADDLE is not set - Tesseract-only mode.",
        )
    engine = _get_paddle_engine()
    if engine is None:
        return EngineAvailability(
            engine=PADDLEOCR, enabled=True, available=False,
            reason=_paddle_init_failed_reason or "unknown initialization failure",
        )
    return EngineAvailability(engine=PADDLEOCR, enabled=True, available=True)


def run_tesseract(image: Image.Image) -> List[EngineTextLine]:
    lines: List[OcrLine] = _run_tesseract(image)
    return [
        EngineTextLine(text=l.text, bbox=l.bbox, confidence=l.confidence, engine=TESSERACT)
        for l in lines
    ]


def run_paddleocr(image: Image.Image) -> List[EngineTextLine]:
    """
    Returns [] (never raises) if PaddleOCR is disabled or unavailable. Callers
    must treat an empty PaddleOCR result as "no second-engine corroboration
    available", not as "PaddleOCR found no text" - those are different facts
    and must not be confused when computing agreement/confidence.
    """
    engine = _get_paddle_engine()
    if engine is None:
        return []

    try:
        import numpy as np
        arr = np.array(image.convert("RGB"))
        raw = engine.ocr(arr, cls=True)
    except Exception:
        return []

    out: List[EngineTextLine] = []
    try:
        for block in (raw or []):
            for entry in (block or []):
                try:
                    poly, (text, conf) = entry
                    xs = [p[0] for p in poly]
                    ys = [p[1] for p in poly]
                    x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
                    bbox = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))
                    out.append(
                        EngineTextLine(
                            text=str(text).strip(),
                            bbox=bbox,
                            confidence=max(0.0, min(1.0, float(conf))),
                            engine=PADDLEOCR,
                        )
                    )
                except Exception:
                    continue
    except Exception:
        return []

    return [l for l in out if l.text]


def run_all_engines(image: Image.Image) -> dict[str, List[EngineTextLine]]:
    """Run every enabled/available engine. Tesseract always runs."""
    result = {TESSERACT: run_tesseract(image)}
    if _paddle_enabled():
        result[PADDLEOCR] = run_paddleocr(image)
    return result


def engine_status_report() -> List[EngineAvailability]:
    return [
        EngineAvailability(engine=TESSERACT, enabled=True, available=True),
        paddle_availability(),
    ]
