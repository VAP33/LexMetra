"""Offline contract tests for Gemini OCR response handling."""

import importlib
import json

from PIL import Image


class _Response:
    def __init__(self, payload):
        self.text = payload


class _Model:
    def __init__(self, payload):
        self.payload = payload

    def generate_content(self, *_args, **_kwargs):
        return _Response(self.payload)


class _Client:
    def __init__(self, payload):
        self.models = _Model(payload)


def _module(monkeypatch):
    monkeypatch.setenv("LMPC_DEV_MODE", "true")
    import ocr_extraction
    return importlib.reload(ocr_extraction)


def test_gemini_ocr_preserves_complete_json_and_valid_geometry(monkeypatch):
    ocr = _module(monkeypatch)
    payload = json.dumps([
        {"text": "Batch No AB-123", "x": 8, "y": 12, "w": 90, "h": 16},
        {"text": "MFD 08/2026", "x": 8, "y": 36, "w": 84, "h": 16},
    ])
    monkeypatch.setattr(ocr, "_gemini_client", _Client(payload))

    lines = ocr._ocr_gemini(Image.new("RGB", (200, 100), "white"))

    assert [line.text for line in lines] == ["Batch No AB-123", "MFD 08/2026"]
    assert lines[0].bbox == (8, 12, 90, 16)
    assert lines[0].confidence == 0.72


def test_gemini_ocr_rejects_truncation_and_off_image_boxes(monkeypatch):
    ocr = _module(monkeypatch)
    image = Image.new("RGB", (100, 100), "white")

    monkeypatch.setattr(ocr, "_gemini_client", _Client('[{"text":"MRP ₹10","x":1'))
    assert ocr._ocr_gemini(image) == []

    monkeypatch.setattr(
        ocr,
        "_gemini_client",
        _Client('[{"text":"MRP ₹10","x":80,"y":1,"w":30,"h":10}]'),
    )
    assert ocr._ocr_gemini(image) == []


def test_qwen_parser_refuses_truncated_json():
    from qwen_perception import deterministic_json_parse

    assert deterministic_json_parse('prefix {"declarations": []} suffix') == {"declarations": []}
    try:
        deterministic_json_parse('{"declarations": [{"field": "MRP"}')
    except ValueError:
        pass
    else:
        raise AssertionError("Truncated perception output must not be repaired")
