"""
PDF intake: page counting, sequential/batched page access, native text-layer
extraction, and page-to-image rendering for OCR.

INTEGRATION NOTE (LexMetra backend integration): the original Module 1
implementation used ``pymupdf`` (fitz). The target deployment environment
this file is integrated into could not install ``pymupdf`` (no network
egress to PyPI), so this is a drop-in reimplementation using ``pypdf``
(native text layer) + ``pdf2image``/poppler (page rasterization for OCR) --
both already available. The public API (function names, signatures, return
types, `PdfInfo`, `MIN_NATIVE_TEXT_CHARS`, `resolve_page_range`,
`iter_page_images_and_text`) is UNCHANGED, so nothing downstream in this
package (text_pipeline.py, cli.py, ui/app.py) needed to change.

If pymupdf becomes available in a given deployment, it can be swapped back
in without touching any other file in this package -- this module is the
sole PDF-backend boundary.

Performance note (per the original brief): the real test document is ~83
scanned pages. This module never loads every page's image into memory at
once. ``iter_page_images_and_text`` is a generator; each page is opened,
processed, and released before the next is touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Tuple

from PIL import Image
from pypdf import PdfReader

try:
    from pdf2image import convert_from_path
except ImportError:  # pragma: no cover - exercised only in environments without poppler
    convert_from_path = None  # type: ignore[assignment]


#: A page counts as having a "usable" native text layer if it has at least
#: this many non-whitespace characters. Below this, we treat it as scanned
#: (or blank) and fall back to OCR rather than accepting a near-empty
#: native extraction as "the text of the page".
MIN_NATIVE_TEXT_CHARS = 40


@dataclass(frozen=True)
class PdfInfo:
    path: str
    page_count: int
    title: Optional[str] = None


def get_pdf_info(path: str | Path) -> PdfInfo:
    reader = PdfReader(str(path))
    meta = reader.metadata or {}
    title = getattr(meta, "title", None) or (meta.get("/Title") if hasattr(meta, "get") else None)
    return PdfInfo(path=str(path), page_count=len(reader.pages), title=title or None)


def extract_native_text(doc: PdfReader, page_no: int) -> str:
    """page_no is 1-based."""
    page = doc.pages[page_no - 1]
    return page.extract_text() or ""


def page_has_usable_text(text: str, min_chars: int = MIN_NATIVE_TEXT_CHARS) -> bool:
    stripped = "".join(text.split())
    return len(stripped) >= min_chars


def render_page_image(doc: PdfReader, page_no: int, dpi: int = 300, *, path: Optional[str] = None) -> Image.Image:
    """
    Render one page to a PIL image at the given DPI. page_no is 1-based.

    Requires ``path`` (the PDF's own file path) because pdf2image/poppler
    render from the file, not from an already-open reader object; ``doc``
    is accepted (and unused) to keep this function's signature compatible
    with the pymupdf-backed version, whose callers pass the same open
    document handle both for text and image extraction.
    """
    if convert_from_path is None:
        raise RuntimeError(
            "pdf2image (and the poppler-utils binaries pdftoppm/pdftocairo) "
            "are required to rasterize scanned PDF pages for OCR, but are not "
            "installed. Install poppler-utils and `pip install pdf2image`."
        )
    if path is None:
        raise RuntimeError("render_page_image requires `path` in the pypdf/pdf2image backend.")
    images = convert_from_path(str(path), dpi=dpi, first_page=page_no, last_page=page_no)
    if not images:
        raise RuntimeError(f"pdf2image produced no image for page {page_no} of {path}")
    return images[0].convert("RGB")


def resolve_page_range(
    page_count: int, start: Optional[int], end: Optional[int]
) -> Tuple[int, int]:
    """
    Clamp a requested 1-based [start, end] inclusive range to the document.
    Defaults to the whole document when start/end are not given.
    """
    resolved_start = start if start is not None else 1
    resolved_end = end if end is not None else page_count

    if resolved_start < 1:
        resolved_start = 1
    if resolved_end > page_count:
        resolved_end = page_count
    if resolved_start > resolved_end:
        raise ValueError(
            f"Invalid page range: start={resolved_start} > end={resolved_end} "
            f"(document has {page_count} pages)"
        )
    return resolved_start, resolved_end


def iter_page_images_and_text(
    path: str | Path,
    start: Optional[int] = None,
    end: Optional[int] = None,
    dpi: int = 300,
) -> Iterator[Tuple[int, str, Optional[Image.Image]]]:
    """
    Sequentially yield (page_no, native_text, image_or_None) for each page in
    the resolved range. The image is only rendered (on access) when the
    native text is not usable -- to avoid rendering images for pages that
    already have a good text layer.

    Yields one page at a time; nothing beyond the current page is held in
    memory by this generator.
    """
    doc = PdfReader(str(path))
    page_count = len(doc.pages)
    resolved_start, resolved_end = resolve_page_range(page_count, start, end)
    for page_no in range(resolved_start, resolved_end + 1):
        native_text = extract_native_text(doc, page_no)
        if page_has_usable_text(native_text):
            yield page_no, native_text, None
        else:
            image = render_page_image(doc, page_no, dpi=dpi, path=path)
            yield page_no, native_text, image
