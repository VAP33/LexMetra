from tests.fixtures.pdf_builder import build_native_text_pdf, build_scanned_pdf

from lexmetra_rules import pdf_intake
from lexmetra_rules.config import resolve_ocr_config
from lexmetra_rules.models import TextSource
from lexmetra_rules.text_pipeline import build_pages


def test_native_pdf_page_count(tmp_path):
    path = build_native_text_pdf(tmp_path / "native.pdf", ["Page one text.", "Page two text."])
    info = pdf_intake.get_pdf_info(path)
    assert info.page_count == 2


def test_native_text_extraction_used_when_usable(tmp_path):
    path = build_native_text_pdf(
        tmp_path / "native.pdf",
        ["3. Exemption in respect of certain packages shall apply to small packs."],
    )
    config = resolve_ocr_config()
    pages = build_pages(path, config)
    assert len(pages) == 1
    assert pages[0].source == TextSource.NATIVE
    assert "Exemption in respect of certain packages" in pages[0].text
    assert pages[0].confidence == 1.0


def test_scanned_pdf_falls_back_to_ocr(tmp_path):
    path = build_scanned_pdf(tmp_path / "scanned.pdf", ["DECLARATION REQUIREMENTS FOR PACKAGES"])
    config = resolve_ocr_config(dpi=300)
    pages = build_pages(path, config)
    assert len(pages) == 1
    assert pages[0].source == TextSource.OCR
    assert pages[0].engine.startswith("tesseract")
    # Real OCR on a clean rendered image should recover most of the text.
    assert "DECLARATION" in pages[0].text.upper() or "PACKAGES" in pages[0].text.upper()


def test_page_range_resolution_defaults_to_whole_document(tmp_path):
    path = build_native_text_pdf(tmp_path / "native.pdf", ["p1", "p2", "p3"])
    start, end = pdf_intake.resolve_page_range(3, None, None)
    assert (start, end) == (1, 3)


def test_page_range_resolution_clamps_out_of_bounds():
    start, end = pdf_intake.resolve_page_range(10, 0, 500)
    assert (start, end) == (1, 10)


def test_page_range_resolution_rejects_inverted_range():
    import pytest
    with pytest.raises(ValueError):
        pdf_intake.resolve_page_range(10, 8, 3)


def test_build_pages_respects_requested_range(tmp_path):
    path = build_native_text_pdf(
        tmp_path / "native.pdf", ["First page.", "Second page.", "Third page."]
    )
    config = resolve_ocr_config()
    pages = build_pages(path, config, start=2, end=2)
    assert len(pages) == 1
    assert pages[0].page_no == 2
    assert "Second page" in pages[0].text
