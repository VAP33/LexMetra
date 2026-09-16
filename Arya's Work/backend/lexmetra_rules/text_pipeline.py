"""
Per-page text pipeline: native text layer when usable, OCR fallback when not.

This is the seam that satisfies "must not assume every regulation PDF
contains machine-readable text": each page independently decides whether it
has a usable native layer (``pdf_intake.page_has_usable_text``), and only
falls back to OCR when it doesn't (or when ``force_ocr`` is set, for
testing/debugging a specific page).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from . import ocr as ocr_module
from . import ocr_normalize
from . import ocr_preprocess
from . import pdf_intake
from .config import OcrConfig
from .models import PageText, TextSource


def build_pages(
    path: str | Path,
    ocr_config: OcrConfig,
    start: Optional[int] = None,
    end: Optional[int] = None,
    force_ocr: bool = False,
    preprocess: bool = True,
) -> List[PageText]:
    """
    Sequentially process the resolved page range and return one PageText per
    page. Pages are processed and their images released one at a time (see
    ``pdf_intake.iter_page_images_and_text``); nothing about this function
    loads the whole document's images into memory simultaneously.

    When OCR is used, `preprocess` (default True) runs the rendered page
    image through ``ocr_preprocess.preprocess_for_ocr`` (deskew, denoise,
    contrast enhancement, adaptive thresholding) before handing it to
    Tesseract. The original, un-preprocessed rendering remains what the UI
    shows for "view source page" — only the OCR input is affected.
    """
    pages: List[PageText] = []

    for page_no, native_text, image in pdf_intake.iter_page_images_and_text(
        path, start=start, end=end, dpi=ocr_config.dpi
    ):
        use_ocr = force_ocr or image is not None

        if not use_ocr:
            pages.append(
                PageText(
                    page_no=page_no,
                    text=native_text,
                    source=TextSource.NATIVE,
                    confidence=1.0,
                    engine="native_text_layer",
                )
            )
            continue

        # Need an image even if force_ocr was requested on a page whose
        # native layer looked usable (debugging use case).
        if image is None:
            doc = pdf_intake.PdfReader(str(path))
            image = pdf_intake.render_page_image(doc, page_no, dpi=ocr_config.dpi, path=path)

        ocr_input = ocr_preprocess.preprocess_for_ocr(image) if preprocess else image
        raw_ocr_text, ocr_confidence = ocr_module.ocr_page(ocr_input, ocr_config)
        # Normalize intra-word spaces introduced by Tesseract character
        # mis-segmentation (e.g. "manufac tured" -> "manufactured").
        # The raw string is preserved; only the canonical PageText.text
        # is normalized so downstream display and extraction are clean.
        ocr_text = ocr_normalize.normalize_ocr_text(raw_ocr_text)
        warnings = []
        if not ocr_text.strip():
            warnings.append("OCR produced no text for this page.")

        pages.append(
            PageText(
                page_no=page_no,
                text=ocr_text,
                source=TextSource.OCR,
                confidence=ocr_confidence,
                engine="tesseract" + ("+" + ocr_preprocess.preprocessing_backend() if preprocess else ""),
                lang=ocr_config.lang,
                dpi=ocr_config.dpi,
                psm=ocr_config.psm,
                warnings=warnings,
            )
        )

    return pages
