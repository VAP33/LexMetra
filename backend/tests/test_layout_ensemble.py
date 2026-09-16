from layout_ensemble import detect_layout, yolo_readiness
import numpy as np


def test_yolo_is_data_constrained_and_not_shipped():
    info = yolo_readiness()
    assert info["ship_trained_model"] is False
    assert info["yolo_weights_present"] is False
    assert "inventory" in info
    assert info["inventory"]["annotation_records"] >= 1 or info["inventory"]["synthetic_image_files"] >= 0


def test_detect_layout_returns_classical_regions():
    img = np.full((120, 160, 3), 240, np.uint8)
    result = detect_layout(img)
    assert result is not None
    assert any("classical CV retained" in n or "YOLO not applied" in n for n in result.notes)
