import pytest
from PIL import Image

from lexmetra_rules import config as config_module
from lexmetra_rules import ocr as ocr_module
from lexmetra_rules.config import MissingTesseractError


def test_require_tesseract_raises_clear_error_when_absent():
    config = config_module.OcrConfig(tesseract_cmd=None, lang="eng", dpi=300, psm=6)
    with pytest.raises(MissingTesseractError) as exc_info:
        config_module.require_tesseract(config)
    message = str(exc_info.value)
    assert "Tesseract" in message
    assert config_module.TESSERACT_ENV_VAR in message


def test_require_tesseract_returns_cmd_when_present():
    config = config_module.OcrConfig(tesseract_cmd="/usr/bin/tesseract", lang="eng", dpi=300, psm=6)
    assert config_module.require_tesseract(config) == "/usr/bin/tesseract"


def test_ocr_page_raises_missing_tesseract_when_unresolved():
    config = config_module.OcrConfig(tesseract_cmd=None, lang="eng", dpi=300, psm=6)
    image = Image.new("RGB", (100, 100), color="white")
    with pytest.raises(MissingTesseractError):
        ocr_module.ocr_page(image, config)


def test_available_languages_raises_when_tesseract_missing():
    config = config_module.OcrConfig(tesseract_cmd=None, lang="eng", dpi=300, psm=6)
    with pytest.raises(MissingTesseractError):
        ocr_module.available_languages(config)


def test_native_text_only_pipeline_never_needs_tesseract(monkeypatch, tmp_path):
    """A page with a usable native text layer must never invoke Tesseract,
    even if Tesseract is entirely unavailable in the environment."""
    from tests.fixtures.pdf_builder import build_native_text_pdf
    from lexmetra_rules.text_pipeline import build_pages

    monkeypatch.setattr(config_module, "locate_tesseract", lambda explicit_cmd=None: None)
    path = build_native_text_pdf(
        tmp_path / "native.pdf",
        ["3. A perfectly ordinary rule with a proper native text layer and plenty of characters."],
    )
    config = config_module.resolve_ocr_config()
    pages = build_pages(path, config)
    assert pages[0].source.value == "native"
    assert "A perfectly ordinary rule" in pages[0].text
