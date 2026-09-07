"""
Barcode / QR product-identity hook (master spec Part 14).

Deliberately small and isolated:
- Decoding a barcode is cheap, reliable, classical CV (zbar) - a good fit for
  "pragmatic production-grade" scope.
- Product identity is explicitly OPTIONAL supporting context. Nothing in the
  rule engine may require a barcode match before evaluating LMPC compliance
  (master spec Part 14/15) - this module only ever POPULATES
  schema.ProductIdentity.barcode; it never gates a legal decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class BarcodeResult:
    data: str
    symbology: str
    bbox: tuple  # x, y, w, h in image pixels


def decode_barcodes(img_bgr: np.ndarray) -> List[BarcodeResult]:
    """
    Decode any barcodes/QR codes visible in the image.

    Returns [] (never raises) if the pyzbar/zbar native library is
    unavailable in the deployment environment, so a missing optional
    dependency degrades to "no barcode found", not a crash - consistent with
    how the rest of this codebase treats optional CV dependencies
    (see vlm_verifier.py, ocr_engines.py).
    """
    try:
        from pyzbar.pyzbar import decode
    except Exception:
        return []

    try:
        results = decode(img_bgr)
    except Exception:
        return []

    out: List[BarcodeResult] = []
    for r in results:
        try:
            data = r.data.decode("utf-8", errors="replace")
        except Exception:
            continue
        rect = r.rect
        out.append(
            BarcodeResult(
                data=data,
                symbology=str(r.type),
                bbox=(rect.left, rect.top, rect.width, rect.height),
            )
        )
    return out


def best_barcode(img_bgr: np.ndarray) -> Optional[BarcodeResult]:
    """Convenience helper: the largest (most likely primary) barcode found."""
    results = decode_barcodes(img_bgr)
    if not results:
        return None
    return max(results, key=lambda b: b.bbox[2] * b.bbox[3])
