from visual_recovery import merge_visual_candidates


def test_vlm_recovers_missing_field_without_overwriting_ocr():
    classified = {"mrp": {"value": None, "confidence": 0.0}}
    out = merge_visual_candidates(classified, [{"field": "mrp", "value": "₹125", "confidence": 0.88}])
    assert out["mrp"]["value"] == "₹125"
    assert out["mrp"]["source"] == "vlm_visual_recovery"


def test_vlm_conflict_is_preserved_for_review():
    classified = {"mrp": {"value": "₹100", "confidence": 0.91}}
    out = merge_visual_candidates(classified, [{"field": "mrp", "value": "₹125", "confidence": 0.88}])
    assert out["mrp"]["value"] == "₹100"
    assert out["mrp"]["agreement"] == "CONFLICTING"
    assert out["mrp"]["review_required"] is True
    assert "₹125" in out["mrp"]["alternative_values"]
