"""
Builds small real PDF files for tests that need to exercise the actual
PDF/OCR pipeline (pdf_intake, ocr, text_pipeline, cli), as opposed to the
synthetic-text fixtures used by most unit tests.

INTEGRATION NOTE: rewritten to use reportlab (already a module1 dev
dependency) instead of PyMuPDF, which is unavailable offline in this
backend's test environment (see lexmetra_rules/pdf_intake.py's own
integration note). Public API (function names/signatures/return types)
is unchanged.

Two kinds of page are supported:
  - a native-text page (reportlab draws real, selectable text)
  - a "scanned" page (text is rendered into a bitmap and placed as a
    full-page IMAGE with no text layer at all, forcing the OCR fallback path)
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _find_unicode_font() -> str | None:
    candidates = [
        "C:/Windows/Fonts/ARIALUNI.ttf",
        "C:/Windows/Fonts/mangal.ttf",
        "C:/Windows/Fonts/Nirmala.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/local/lib/python3.12/dist-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    return None


def build_native_text_pdf(path: str | Path, page_texts: List[str]) -> Path:
    """
    Build a PDF with a real, selectable text layer using a full-Unicode
    TrueType font (not the base-14 Helvetica), so characters like the
    em-dash used in Indian legal drafting ("Short title.\u2014These
    rules...") survive round-trip extraction faithfully.

    Uses simple word-wrapping within a margin, mirroring the original
    PyMuPDF `insert_textbox` behaviour (a real regulation PDF from a word
    processor or LaTeX always wraps long lines).
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_path = _find_unicode_font()
    font_name = "helv"
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("F0", font_path))
            font_name = "F0"
        except Exception:
            font_name = "Helvetica"
    else:
        font_name = "Helvetica"

    margin = 54
    page_width, page_height = letter  # 612 x 792
    max_width = page_width - 2 * margin
    font_size = 11
    line_height = 14

    c = canvas.Canvas(str(path), pagesize=letter)
    for text in page_texts:
        c.setFont(font_name, font_size)
        lines = _wrap_text(text, font_name, font_size, max_width)
        y = page_height - margin
        for line in lines:
            if y < margin:
                break
            c.drawString(margin, y, line)
            y -= line_height
        c.showPage()
    c.save()
    return Path(path)


def _wrap_text(text: str, font_name: str, font_size: int, max_width: float) -> List[str]:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lines: List[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if stringWidth(candidate, font_name, font_size) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _render_text_image(text: str, size=(1700, 2200)) -> Image.Image:
    image = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(image)
    font_path = _find_unicode_font()
    try:
        font = ImageFont.truetype(font_path, 34) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    margin = 100
    y = margin
    for line in text.splitlines():
        draw.text((margin, y), line, fill="black", font=font)
        y += 46
    return image


def build_scanned_pdf(path: str | Path, page_texts: List[str]) -> Path:
    """Build a PDF whose pages contain ONLY a rendered image of the given
    text (no selectable text layer at all) -- simulating a scanned document."""
    c = canvas.Canvas(str(path), pagesize=letter)
    for i, text in enumerate(page_texts):
        image = _render_text_image(text)
        img_path = f"{path}.tmp_page_{i}.png"
        image.save(img_path)
        c.drawImage(img_path, 0, 0, width=612, height=792)
        c.showPage()
        Path(img_path).unlink(missing_ok=True)
    c.save()
    return Path(path)
