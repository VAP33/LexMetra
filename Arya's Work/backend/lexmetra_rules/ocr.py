"""
Tesseract OCR wrapper.

The rule engine downstream must never receive text silently produced by a
failed/absent OCR step. If Tesseract is required and unavailable, this
module raises ``config.MissingTesseractError`` rather than returning "".
"""

from __future__ import annotations

from typing import List, Tuple

import pytesseract
from PIL import Image

from .config import MissingTesseractError, OcrConfig, require_tesseract


def configure_pytesseract(config: OcrConfig) -> str:
    """Point pytesseract at the resolved binary. Raises if unresolved."""
    cmd = require_tesseract(config)
    pytesseract.pytesseract.tesseract_cmd = cmd
    return cmd


def available_languages(config: OcrConfig) -> List[str]:
    """Best-effort list of installed language packs. Never raises; an
    empty list means "could not determine", not "no languages"."""
    try:
        configure_pytesseract(config)
        return list(pytesseract.get_languages(config="") or [])
    except MissingTesseractError:
        raise
    except Exception:
        return []


def ocr_page(image: Image.Image, config: OcrConfig) -> Tuple[str, float]:
    """
    Run OCR on one page image.

    Returns (text, mean_confidence in [0, 1]). Confidence is derived from
    Tesseract's own per-word confidence scores (image_to_data), not
    invented: a page Tesseract itself is unsure about gets a low reported
    confidence rather than looking identical to a confidently-read page.
    """
    configure_pytesseract(config)

    tess_config = f"--psm {config.psm}"
    if config.tessdata_dir:
        tess_config += f' --tessdata-dir "{config.tessdata_dir}"'

    text = pytesseract.image_to_string(image, lang=config.lang, config=tess_config)

    try:
        data = pytesseract.image_to_data(
            image, lang=config.lang, config=tess_config,
            output_type=pytesseract.Output.DICT,
        )
        confidences = [
            float(c) for c in data.get("conf", [])
            if _is_valid_conf(c)
        ]
        mean_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
    except Exception:
        mean_conf = 0.0

    return text, max(0.0, min(1.0, mean_conf))


def _is_valid_conf(value) -> bool:
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return False
