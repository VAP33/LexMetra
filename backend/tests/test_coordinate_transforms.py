"""
Tests for CoordinateTransform and normalize_package_surface in geometry.py.
Verifies explicit coordinate spaces, forward/inverse mappings, and boundary normalization.
"""

import numpy as np
import pytest
from geometry import (
    CoordinateSpace,
    CoordinateTransform,
    normalize_package_surface,
    strip_letterbox_borders,
)


def test_coordinate_transform_point_and_invert():
    # 2x scaling and (10, 20) translation
    matrix = [
        [2.0, 0.0, 10.0],
        [0.0, 2.0, 20.0],
        [0.0, 0.0, 1.0],
    ]
    fwd = CoordinateTransform(
        source_space=CoordinateSpace.ORIGINAL_PIXEL,
        target_space=CoordinateSpace.CANONICAL_PIXEL,
        matrix=matrix,
        matrix_direction="FORWARD",
        source_dims=(100, 100),
        target_dims=(210, 220),
    )

    # Transform (15, 25)
    tx, ty = fwd.transform_point(15.0, 25.0)
    assert tx == pytest.approx(15.0 * 2.0 + 10.0)  # 40.0
    assert ty == pytest.approx(25.0 * 2.0 + 20.0)  # 70.0

    # Invert
    inv = fwd.invert()
    assert inv.matrix_direction == "INVERSE"
    assert inv.source_space == CoordinateSpace.CANONICAL_PIXEL
    assert inv.target_space == CoordinateSpace.ORIGINAL_PIXEL

    # Round trip back
    rx, ry = inv.transform_point(tx, ty)
    assert rx == pytest.approx(15.0, abs=1e-4)
    assert ry == pytest.approx(25.0, abs=1e-4)


def test_coordinate_transform_bbox():
    matrix = [
        [1.5, 0.0, 5.0],
        [0.0, 1.5, 10.0],
        [0.0, 0.0, 1.0],
    ]
    fwd = CoordinateTransform(
        source_space=CoordinateSpace.ORIGINAL_PIXEL,
        target_space=CoordinateSpace.CANONICAL_PIXEL,
        matrix=matrix,
    )
    bbox = (20.0, 30.0, 40.0, 50.0)
    tb = fwd.transform_bbox(bbox)
    assert tb[0] == pytest.approx(20.0 * 1.5 + 5.0)   # 35.0
    assert tb[1] == pytest.approx(30.0 * 1.5 + 10.0)  # 55.0
    assert tb[2] == pytest.approx(40.0 * 1.5)         # 60.0
    assert tb[3] == pytest.approx(50.0 * 1.5)         # 75.0


def test_strip_letterbox_borders():
    # Create image with black top and bottom letterbox bars
    img = np.zeros((300, 200, 3), dtype=np.uint8)
    # Put bright content in middle (rows 50 to 250)
    img[50:250, 10:190] = 200

    cropped, (cx, cy, cw, ch) = strip_letterbox_borders(img)
    assert cy >= 45 and cy <= 55
    assert ch <= 210


def test_normalize_package_surface_pipeline():
    # Synthetic test image
    img = np.zeros((400, 300, 3), dtype=np.uint8)
    img[20:380, 20:280] = 180

    result = normalize_package_surface(img, source_name="test_pkg")
    assert result is not None
    assert result.canonical_bgr is not None
    assert len(result.provenance_steps) >= 1
    assert result.forward_transform.source_space == CoordinateSpace.ORIGINAL_PIXEL
    assert result.forward_transform.target_space == CoordinateSpace.CANONICAL_PIXEL
