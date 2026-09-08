import numpy as np
import cv2

from live_capture import analyze_live_frame, LiveReadiness
from package_boundary import estimate_package_boundary, framing_guidance
from measurement import measure_with_calibration, MeasurementConfidence


def _blank(w=800, h=600, val=200):
    return np.ones((h, w, 3), dtype="uint8") * val


def test_blank_frame_is_not_ready_no_package():
    r = analyze_live_frame(_blank())
    assert r.readiness == LiveReadiness.NOT_READY
    assert r.package_detected is False


def test_real_photo_with_clear_package_reaches_ready_or_almost():
    img = cv2.imread(
        "/home/claude/proj/dataset/real_photos/"
        "Screenshot_2026-09-06-22-06-12-38_92460851df6f172a4592fca41cc2d2e6.jpg"
    )
    r = analyze_live_frame(img)
    assert r.package_detected is True
    assert r.readiness in (LiveReadiness.READY, LiveReadiness.ALMOST_READY)
    # Never a legal claim leaking into live guidance text.
    joined = " ".join(g.message.lower() for g in r.guidance)
    for banned in ("pass", "fail", "compliant", "violation"):
        assert banned not in joined


def test_guidance_never_uses_legal_language_on_blank_frame():
    r = analyze_live_frame(_blank())
    joined = " ".join(g.message.lower() for g in r.guidance)
    for banned in ("pass", "fail", "compliant", "violation"):
        assert banned not in joined


def test_most_severe_guidance_is_first():
    r = analyze_live_frame(_blank())
    severities = [g.severity for g in r.guidance]
    rank = {"high": 0, "medium": 1, "low": 2}
    assert severities == sorted(severities, key=lambda s: rank[s])


def test_package_boundary_vs_pdp_are_independent_concepts():
    """
    package_boundary only ever returns a bbox/confidence/fill-ratio - it must
    not know anything about text/OCR, keeping it structurally distinct from
    PDP estimation (image_quality.estimate_pdp_bbox, which is driven by OCR
    line bboxes).
    """
    import inspect
    from package_boundary import estimate_package_boundary as f
    source = inspect.getsource(f)
    assert "ocr" not in source.lower()
    assert "tesseract" not in source.lower()


def test_framing_guidance_flags_off_center_package():
    boundary_result = type("B", (), {"bbox": (10, 10, 50, 50), "confidence": 0.9, "frame_fill_ratio": 0.3})()
    msg = framing_guidance(boundary_result, (600, 800))
    assert msg is not None
    assert "center" in msg.lower()


def test_measurement_without_calibration_is_always_uncertain():
    result = measure_with_calibration(pixel_length=250.0)
    assert result.confidence == MeasurementConfidence.UNCERTAIN
    assert result.value_mm is None


def test_measurement_with_explicit_calibration_is_verified():
    result = measure_with_calibration(pixel_length=100.0, calibration_reference_mm_per_pixel=0.5)
    assert result.confidence == MeasurementConfidence.VERIFIED
    assert result.value_mm == 50.0
