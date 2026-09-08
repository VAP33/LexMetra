"""
Regression tests for orientation_ocr.py.

The Vaseline body-lotion photo (dataset/real_photos) is a REAL, user-supplied
image with genuinely mixed text orientation: a sideways "NET VOL. WHEN
PACKED" column printed at 90 degrees to the rest of the (horizontal) label,
right next to normal horizontal text. Baseline whole-image OCR (verified
separately, see IMPLEMENTATION_STATUS.md) cannot read the sideways text at
all. This file locks in the fix as a permanent regression fixture.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from orientation_ocr import (
    detect_text_blocks,
    run_orientation_aware_ocr,
    _map_bbox_to_original,
)

REAL_PHOTOS_DIR = Path(__file__).parent.parent.parent / "dataset" / "real_photos"
VASELINE_PHOTO = REAL_PHOTOS_DIR / "Screenshot_2026-09-06-22-07-38-18_92460851df6f172a4592fca41cc2d2e6.jpg"


def _require_photo():
    if not VASELINE_PHOTO.exists():
        pytest.skip("real photo fixture not present in this checkout")


def test_vaseline_mixed_orientation_finds_sideways_net_volume_text():
    _require_photo()
    img = Image.open(VASELINE_PHOTO)
    lines = run_orientation_aware_ocr(img)

    assert len(lines) > 0, "orientation-aware pass found no text blocks at all"

    sideways_hits = [
        l for l in lines
        if l.orientation_degrees in (90, 270)
        and "NET VOL" in l.text.upper()
    ]
    assert sideways_hits, (
        "Expected the sideways 'NET VOL. WHEN PACKED' text to be recovered "
        "at a non-zero orientation; got orientations: "
        f"{[l.orientation_degrees for l in lines]}"
    )
    assert sideways_hits[0].confidence > 0.5


def test_original_bbox_coordinates_preserved_within_image_bounds():
    """
    Every mapped bbox must land inside the ORIGINAL image's pixel bounds -
    proof that rotation was undone correctly and coordinates were not
    silently left in the rotated crop's coordinate system.
    """
    _require_photo()
    img = Image.open(VASELINE_PHOTO).convert("RGB")
    w, h = img.size
    lines = run_orientation_aware_ocr(img)
    assert lines

    for line in lines:
        x, y, bw, bh = line.bbox
        assert -2 <= x <= w, f"x={x} outside image width {w}"
        assert -2 <= y <= h, f"y={y} outside image height {h}"
        assert x + bw <= w + 5, "bbox extends past right edge of original image"
        assert y + bh <= h + 5, "bbox extends past bottom edge of original image"


def test_every_line_retains_orientation_and_source_block_provenance():
    _require_photo()
    img = Image.open(VASELINE_PHOTO)
    lines = run_orientation_aware_ocr(img)
    assert lines
    for line in lines:
        assert line.orientation_degrees in (0, 90, 180, 270)
        assert line.source_block_bbox is not None
        assert line.engine == "tesseract"


def test_bbox_roundtrip_mapping_is_reversible_synthetic():
    """
    Pure-math check (no image dependency): rotating a bbox forward and then
    mapping it back with _map_bbox_to_original must return the original
    unrotated bbox, for all four supported angles.
    """
    crop_w, crop_h = 100, 300  # a tall/narrow crop, like a vertical column
    original_bbox = (10, 20, 30, 40)  # x, y, w, h within the unrotated crop

    def rotate_bbox_forward(bbox, angle, w, h):
        x, y, bw, bh = bbox
        if angle == 0:
            return bbox, (w, h)
        if angle == 90:
            # matches cv2.ROTATE_90_CLOCKWISE geometry
            return (h - (y + bh), x, bh, bw), (h, w)
        if angle == 180:
            return (w - (x + bw), h - (y + bh), bw, bh), (w, h)
        if angle == 270:
            return (y, w - (x + bw), bh, bw), (h, w)
        raise ValueError(angle)

    for angle in (0, 90, 180, 270):
        rotated_bbox, (rw, rh) = rotate_bbox_forward(original_bbox, angle, crop_w, crop_h)
        recovered = _map_bbox_to_original(rotated_bbox, angle, (rw, rh), block_origin=(0, 0))
        assert recovered == original_bbox, f"angle={angle} failed: {recovered} != {original_bbox}"
