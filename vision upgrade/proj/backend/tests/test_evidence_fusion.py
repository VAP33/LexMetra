"""
Regression tests for evidence_fusion.py: cross-engine agreement and the
scoped cross-image split-declaration reconstruction (master spec Parts 6, 9).

These tests use synthetic OcrLine fixtures (not real images) because the
logic under test is pure - given OCR lines, does the fusion/reconstruction
logic make the correct, honest decision. Real-image behaviour is exercised
separately in dataset/benchmark_real.py against the real photo set.
"""

from ocr_extraction import OcrLine
from evidence_fusion import classify_multi_engine, reconstruct_split_fields
from schema import EvidenceVerification


def _line(text, bbox=(10, 10, 100, 20), conf=0.9):
    return OcrLine(text=text, bbox=bbox, confidence=conf)


# ---------------------------------------------------------------------------
# classify_multi_engine: agreement / conflict
# ---------------------------------------------------------------------------

def test_two_engines_agree_on_mrp_is_corroborated():
    tesseract_lines = [_line("MRP Rs 149.00", bbox=(0, 0, 150, 20))]
    paddle_lines = [_line("MRP Rs 149.00", bbox=(0, 0, 150, 20), conf=0.95)]

    fused = classify_multi_engine({"tesseract": tesseract_lines, "paddleocr": paddle_lines})

    assert "mrp" in fused
    assert fused["mrp"]["verification"] == EvidenceVerification.CORROBORATED.value
    assert set(fused["mrp"]["ocr_engines"]) == {"tesseract", "paddleocr"}
    assert fused["mrp"]["numeric_value"] == 149.00


def test_two_engines_disagree_on_mrp_is_conflicting_not_silently_averaged():
    tesseract_lines = [_line("MRP Rs 149.00", bbox=(0, 0, 150, 20))]
    paddle_lines = [_line("MRP Rs 449.00", bbox=(0, 0, 150, 20), conf=0.95)]

    fused = classify_multi_engine({"tesseract": tesseract_lines, "paddleocr": paddle_lines})

    assert fused["mrp"]["verification"] == EvidenceVerification.CONFLICTING.value
    assert len(fused["mrp"]["conflicting_values"]) == 2


def test_single_engine_only_is_verified_not_corroborated():
    tesseract_lines = [_line("MRP Rs 149.00")]
    fused = classify_multi_engine({"tesseract": tesseract_lines})

    assert fused["mrp"]["verification"] == EvidenceVerification.VERIFIED.value
    assert fused["mrp"]["ocr_engines"] == ["tesseract"]


def test_agreement_capped_to_uncertain_under_low_quality_region():
    tesseract_lines = [_line("MRP Rs 149.00")]
    paddle_lines = [_line("MRP Rs 149.00", conf=0.95)]

    class _FakeQuality:
        status = "LOW_QUALITY"

    fused = classify_multi_engine(
        {"tesseract": tesseract_lines, "paddleocr": paddle_lines},
        region_quality_by_field={"mrp": _FakeQuality()},
    )

    # Corroborated by two engines, but glare over the region must still
    # reduce confidence/verification per the master spec's explicit example.
    assert fused["mrp"]["verification"] == EvidenceVerification.UNCERTAIN.value
    assert fused["mrp"]["confidence"] <= 0.55


# ---------------------------------------------------------------------------
# reconstruct_split_fields: scoped cross-image reconstruction
# ---------------------------------------------------------------------------

def test_split_mrp_label_and_value_reconstructed_across_two_images():
    # Image A: "MRP Rs" label only, no digits at all.
    session_state = {
        "mrp": {"value": "MRP Rs", "confidence": 0.8, "bbox": (0, 0, 60, 20), "source": "ocr_label_line"}
    }
    image_id_owning_label = {"mrp": "image_a"}
    # Image B: a bare value fragment with no label attached.
    other_lines = {"image_b": [_line("149.00", bbox=(5, 400, 80, 24), conf=0.85)]}

    result = reconstruct_split_fields(session_state, image_id_owning_label, other_lines)

    assert "mrp" in result
    assert result["mrp"]["numeric_value"] == 149.00
    assert result["mrp"]["spatial_relationship"] == "cross_image_continuation"
    assert result["mrp"]["verification"] == EvidenceVerification.UNCERTAIN.value
    assert result["mrp"]["review_required"] is True
    assert set(result["mrp"]["source_images"]) == {"image_a", "image_b"}


def test_split_mrp_not_reconstructed_when_label_already_has_a_number():
    # "MRP Rs 1" already contains a number - classify_fields would have set
    # numeric_value=1.0, so this entry is NOT label-only and must be left
    # untouched even if an unrelated numeric fragment exists elsewhere.
    session_state = {
        "mrp": {
            "value": "MRP Rs 1",
            "confidence": 0.8,
            "bbox": (0, 0, 60, 20),
            "numeric_value": 1.0,
            "source": "ocr_label_line",
        }
    }
    image_id_owning_label = {"mrp": "image_a"}
    other_lines = {"image_b": [_line("Best before 12 months", bbox=(5, 400, 120, 24))]}

    result = reconstruct_split_fields(session_state, image_id_owning_label, other_lines)

    assert "mrp" not in result


def test_split_mrp_rejected_when_multiple_ambiguous_fragments_exist():
    session_state = {
        "mrp": {"value": "MRP Rs", "confidence": 0.8, "bbox": (0, 0, 60, 20), "source": "ocr_label_line"}
    }
    image_id_owning_label = {"mrp": "image_a"}
    # Two DIFFERENT plausible fragments across two other images -> ambiguous.
    other_lines = {
        "image_b": [_line("149.00", bbox=(5, 400, 80, 24))],
        "image_c": [_line("199.00", bbox=(5, 10, 80, 24))],
    }

    result = reconstruct_split_fields(session_state, image_id_owning_label, other_lines)

    assert "mrp" not in result


def test_no_fragment_available_leaves_field_untouched():
    session_state = {
        "mrp": {"value": "MRP Rs", "confidence": 0.8, "bbox": (0, 0, 60, 20), "source": "ocr_label_line"}
    }
    image_id_owning_label = {"mrp": "image_a"}
    other_lines = {"image_b": [_line("Best before 12 months from mfg", bbox=(5, 400, 150, 24))]}

    result = reconstruct_split_fields(session_state, image_id_owning_label, other_lines)

    assert "mrp" not in result
