import numpy as np
from PIL import Image

from lexmetra_rules import ocr_preprocess


def _make_skewed_text_image(angle_degrees=8):
    """Render a simple synthetic 'page' with horizontal black bars on a
    white background (stands in for text lines) and rotate it, to give
    the deskew step something real to correct."""
    from PIL import ImageDraw

    img = Image.new("L", (600, 800), color=255)
    draw = ImageDraw.Draw(img)
    for y in range(100, 700, 40):
        draw.rectangle([80, y, 500, y + 12], fill=0)
    return img.convert("RGB").rotate(angle_degrees, fillcolor=(255, 255, 255), expand=False)


def test_preprocessing_backend_reports_opencv_in_this_environment():
    # This environment has opencv-python-headless installed — confirms the
    # real preprocessing path (not the PIL-only fallback) is what's under
    # test below.
    assert ocr_preprocess.preprocessing_backend() == "opencv"


def test_preprocess_for_ocr_returns_new_image_without_mutating_input():
    original = Image.new("RGB", (200, 200), color="white")
    original_bytes = original.tobytes()
    result = ocr_preprocess.preprocess_for_ocr(original)
    assert original.tobytes() == original_bytes
    assert result is not original


def test_preprocess_for_ocr_returns_a_valid_image():
    img = _make_skewed_text_image()
    result = ocr_preprocess.preprocess_for_ocr(img)
    assert isinstance(result, Image.Image)
    assert result.size[0] > 0 and result.size[1] > 0


def test_deskew_reduces_measured_skew_angle():
    import cv2

    skewed = _make_skewed_text_image(angle_degrees=8)
    processed = ocr_preprocess.preprocess_for_ocr(skewed)

    gray_before = cv2.cvtColor(np.array(skewed.convert("RGB")), cv2.COLOR_RGB2GRAY)
    angle_before = abs(ocr_preprocess._deskew_angle(gray_before))

    gray_after = np.array(processed.convert("L"))
    angle_after = abs(ocr_preprocess._deskew_angle(gray_after))

    assert angle_after < angle_before


def test_preprocessing_never_raises_on_a_blank_image():
    blank = Image.new("RGB", (100, 100), color="white")
    result = ocr_preprocess.preprocess_for_ocr(blank)
    assert isinstance(result, Image.Image)


def test_pil_fallback_path_used_when_opencv_unavailable(monkeypatch):
    monkeypatch.setattr(ocr_preprocess, "_HAS_CV2", False)
    img = _make_skewed_text_image()
    result = ocr_preprocess.preprocess_for_ocr(img)
    assert isinstance(result, Image.Image)
    assert ocr_preprocess.preprocessing_backend() == "pil_fallback"
