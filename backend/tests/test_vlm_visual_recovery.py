import json

import pytest

import vlm_verifier


def test_visual_field_coercion_preserves_evidence_provenance():
    result = vlm_verifier._coerce_visual_field(
        {
            "field": "net_quantity",
            "value": "150 g",
            "raw_text": "NET WT 150 g",
            "numeric_value": 150,
            "numeric_unit": "g",
            "bbox": [10, 20, 100, 30],
            "confidence": 0.91,
            "explanation": "Clearly printed on the front label.",
        },
        image_id="front.jpg",
        surface_id="surface-1",
    )
    assert result["source"] == "vlm_visual_recovery"
    assert result["image_id"] == "front.jpg"
    assert result["surface_id"] == "surface-1"
    assert result["bbox"] == (10, 20, 100, 30)
    assert result["numeric_value"] == 150.0


def test_visual_json_parser_rejects_non_object():
    assert vlm_verifier._extract_json_object('[1,2,3]') is None


def test_visual_json_parser_accepts_fenced_json():
    data = vlm_verifier._extract_json_object('```json\n{"fields": []}\n```')
    assert data == {"fields": []}


def test_visual_recovery_never_fabricates_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        vlm_verifier.recover_fields_from_image(object(), {"mrp": {}})
