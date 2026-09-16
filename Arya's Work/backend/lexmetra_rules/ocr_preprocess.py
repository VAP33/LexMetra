"""
OCR image preprocessing: deskew, denoise, contrast enhancement, adaptive
thresholding — applied to a rendered page image BEFORE it goes to
Tesseract, to improve recognition on real scanned regulations.

Uses OpenCV when available for real deskew (minAreaRect on text-pixel
contours) and adaptive thresholding; falls back to a PIL-only pipeline
(grayscale + autocontrast + sharpen) when OpenCV isn't installed, so the
OCR path keeps working either way — consistent with this module's
"optional dependency, graceful degradation" pattern for Tesseract itself.

This module never edits the ORIGINAL page image used for the "view source
page" UI feature — it only affects the copy that is handed to Tesseract.
The un-preprocessed original remains available for human visual review.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter, ImageOps

try:
    import cv2
    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore
    _HAS_CV2 = False


def _deskew_angle(gray: "np.ndarray") -> float:
    """Estimate the skew angle (degrees) of a grayscale page image using
    the minimum-area bounding rectangle of dark (text) pixels."""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(binary > 0))
    if coords.shape[0] < 20:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    # A real scanned regulation is rarely skewed more than a few degrees;
    # guard against wildly wrong estimates on sparse/odd pages.
    if abs(angle) > 15:
        return 0.0
    return float(angle)


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """
    Return a NEW image suitable for OCR. The input `image` is never
    mutated in place.
    """
    if not _HAS_CV2:
        return _preprocess_pil_fallback(image)

    try:
        arr = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

        angle = _deskew_angle(gray)
        if abs(angle) > 0.1:
            (h, w) = gray.shape
            center = (w // 2, h // 2)
            matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
            gray = cv2.warpAffine(
                gray, matrix, (w, h),
                flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
            )

        denoised = cv2.fastNlMeansDenoising(gray, h=10)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast_enhanced = clahe.apply(denoised)

        binary = cv2.adaptiveThreshold(
            contrast_enhanced, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
            blockSize=31, C=15,
        )

        return Image.fromarray(binary)
    except Exception:
        # Preprocessing must never be the reason OCR fails outright — fall
        # back to the original image untouched.
        return image


def _preprocess_pil_fallback(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    contrast = ImageOps.autocontrast(gray, cutoff=1)
    sharpened = contrast.filter(ImageFilter.SHARPEN)
    return sharpened


def preprocessing_backend() -> str:
    """For diagnostics/UI display: which preprocessing path is active."""
    return "opencv" if _HAS_CV2 else "pil_fallback"
