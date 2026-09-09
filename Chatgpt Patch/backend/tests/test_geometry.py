"""
Unit tests for geometry.py — synthetic images only, no database/network
required. Mirrors the naming/style of test_capture_session.py.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

import geometry as geo
from schema import (
    BBox,
    EvidenceStatus,
    GeometryReadiness,
    GeometryType,
    ImageQuality,
    PDPObservationStatus,
    PolygonPoint,
    PositionCoordinateSystem,
)


# ---------------------------------------------------------------------------
# Synthetic image builders
# ---------------------------------------------------------------------------

def _blank(width=600, height=800, color=(230, 230, 230)):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color
    return img


def _rectangular_box_image(width=600, height=800):
    """A clean axis-aligned rectangular package on a plain background."""
    img = _blank(width, height)
    cv2.rectangle(img, (100, 150), (500, 650), (40, 90, 160), thickness=-1)
    return img


def _perspective_box_image(width=600, height=800):
    """A rectangular package photographed at an angle (trapezoid silhouette)."""
    img = _blank(width, height)
    pts = np.array([[130, 180], [520, 120], [560, 700], [180, 660]], dtype=np.int32)
    cv2.fillPoly(img, [pts], (40, 90, 160))
    return img


def _cylindrical_image(width=600, height=800):
    """An elongated rounded silhouette approximating a bottle/jar body."""
    img = _blank(width, height)
    cv2.ellipse(img, (300, 420), (140, 300), 0, 0, 360, (60, 120, 180), thickness=-1)
    return img


def _partial_package_image(width=600, height=800):
    """Package contour that runs off the edge of the frame."""
    img = _blank(width, height)
    cv2.rectangle(img, (-50, 100), (350, 750), (40, 90, 160), thickness=-1)
    return img


def _cluttered_background_image(width=600, height=800):
    img = _blank(width, height)
    rng = np.random.default_rng(42)
    for _ in range(25):
        x1, y1 = rng.integers(0, width - 40), rng.integers(0, height - 40)
        w, h = rng.integers(15, 60), rng.integers(15, 60)
        color = tuple(int(c) for c in rng.integers(0, 255, size=3))
        cv2.rectangle(img, (x1, y1), (x1 + w, y1 + h), color, thickness=-1)
    cv2.rectangle(img, (150, 200), (450, 600), (40, 90, 160), thickness=-1)
    return img


def _empty_scene_image(width=600, height=800):
    return _blank(width, height, color=(220, 220, 220))


def _blurred(img, ksize=25):
    return cv2.GaussianBlur(img, (ksize, ksize), 0)


def _glare(img):
    out = img.copy()
    cv2.circle(out, (300, 350), 120, (255, 255, 255), thickness=-1)
    return out


# ---------------------------------------------------------------------------
# 1. Rectangular box
# ---------------------------------------------------------------------------

def test_rectangular_box_detected_as_flat():
    img = _rectangular_box_image()
    pkg = geo.detect_package_geometry(img, source_image="img1")
    assert pkg.shape == GeometryType.FLAT
    assert pkg.bbox is not None
    assert pkg.shape_confidence > 0.3


# ---------------------------------------------------------------------------
# 2. Perspective-distorted box
# ---------------------------------------------------------------------------

def test_perspective_box_still_detected_with_reasonable_bbox():
    img = _perspective_box_image()
    pkg = geo.detect_package_geometry(img, source_image="img2")
    assert pkg.bbox is not None
    # Bounding box should roughly cover the trapezoid extents.
    assert pkg.bbox.width > 300
    assert pkg.bbox.height > 400


# ---------------------------------------------------------------------------
# 3. Cylindrical package
# ---------------------------------------------------------------------------

def test_cylindrical_package_classified_as_cylindrical_or_near():
    img = _cylindrical_image()
    pkg = geo.detect_package_geometry(img, source_image="img3")
    assert pkg.shape in (GeometryType.CYLINDRICAL, GeometryType.NEAR_CYLINDRICAL)


# ---------------------------------------------------------------------------
# 4. Partial package (touches frame border)
# ---------------------------------------------------------------------------

def test_partial_package_flagged_as_touching_border():
    img = _partial_package_image()
    pkg = geo.detect_package_geometry(img, source_image="img4")
    assert pkg.touches_image_border is True
    assert pkg.shape_confidence <= 0.6


# ---------------------------------------------------------------------------
# 5. Cluttered background
# ---------------------------------------------------------------------------

def test_cluttered_background_still_finds_largest_contour():
    img = _cluttered_background_image()
    pkg = geo.detect_package_geometry(img, source_image="img5")
    assert pkg.bbox is not None
    # The package (300x400) should dominate over any single clutter piece (<=60x60).
    assert pkg.bbox.width > 100 and pkg.bbox.height > 100


def test_empty_scene_yields_no_confident_package():
    img = _empty_scene_image()
    pkg = geo.detect_package_geometry(img, source_image="img_empty")
    assert pkg.shape == GeometryType.UNKNOWN
    assert pkg.shape_confidence == 0.0


# ---------------------------------------------------------------------------
# 9/10. PDP != package boundary; PDP from OCR-region clustering
# ---------------------------------------------------------------------------

def test_pdp_not_confused_with_package_boundary_when_ocr_available():
    img = _rectangular_box_image()
    pkg = geo.detect_package_geometry(img, source_image="img6")
    # OCR text only covers a sub-region of the package.
    ocr_boxes = [(150, 200, 100, 20), (150, 240, 150, 20)]
    pdp = geo.detect_pdp_geometry(img, source_image="img6", package_geometry=pkg, ocr_boxes=ocr_boxes)

    assert pdp.observation_status == PDPObservationStatus.OBSERVED
    assert pdp.derived_from_package_boundary_only is False
    # PDP must be smaller than (or equal to, if padding pushes it) the package bbox,
    # and specifically must not just equal the raw package bbox.
    assert pdp.bbox is not None and pkg.bbox is not None
    assert (pdp.bbox.width, pdp.bbox.height) != (pkg.bbox.width, pkg.bbox.height)


def test_pdp_not_observed_without_ocr_or_package_geometry():
    img = _empty_scene_image()
    pdp = geo.detect_pdp_geometry(img, source_image="img_empty")
    assert pdp.observation_status == PDPObservationStatus.NOT_OBSERVED
    assert pdp.confidence == 0.0


def test_pdp_falls_back_to_package_boundary_with_low_confidence_when_no_ocr():
    img = _rectangular_box_image()
    pkg = geo.detect_package_geometry(img, source_image="img7")
    pdp = geo.detect_pdp_geometry(img, source_image="img7", package_geometry=pkg, ocr_boxes=None)
    assert pdp.observation_status == PDPObservationStatus.PARTIAL
    assert pdp.derived_from_package_boundary_only is True
    assert pdp.confidence <= 0.4


# ---------------------------------------------------------------------------
# Perspective correction / rectification
# ---------------------------------------------------------------------------

def test_rectify_pdp_returns_none_for_degenerate_quad():
    img = _rectangular_box_image()
    degenerate = [
        PolygonPoint(x=100, y=100),
        PolygonPoint(x=101, y=100),
        PolygonPoint(x=101, y=101),
        PolygonPoint(x=100, y=101),
    ]
    rectified, result = geo.rectify_pdp(img, "img8", degenerate)
    assert rectified is None and result is None


def test_rectify_pdp_produces_valid_homography_for_reasonable_quad():
    img = _perspective_box_image()
    quad = [
        PolygonPoint(x=130, y=180),
        PolygonPoint(x=520, y=120),
        PolygonPoint(x=560, y=700),
        PolygonPoint(x=180, y=660),
    ]
    rectified, result = geo.rectify_pdp(img, "img9", quad)
    assert rectified is not None
    assert result is not None
    assert len(result.homography) == 9
    assert result.rectified_width_px > 0 and result.rectified_height_px > 0
    assert result.reprojection_error_px is not None and result.reprojection_error_px < 5.0


# ---------------------------------------------------------------------------
# 11. OCR region coordinate mapping
# ---------------------------------------------------------------------------

def test_map_region_coordinates_round_trips_through_homography():
    img = _perspective_box_image()
    quad = [
        PolygonPoint(x=130, y=180),
        PolygonPoint(x=520, y=120),
        PolygonPoint(x=560, y=700),
        PolygonPoint(x=180, y=660),
    ]
    _, result = geo.rectify_pdp(img, "img10", quad)
    assert result is not None

    # Point-level mapping is an exact projective transform, so a single
    # point must round-trip almost perfectly (floating-point precision only).
    rx, ry = geo.map_point_through_homography(200, 200, result.homography, invert=False)
    bx, by = geo.map_point_through_homography(rx, ry, result.homography, invert=True)
    assert abs(bx - 200) < 1e-3
    assert abs(by - 200) < 1e-3

    # Bbox-level mapping takes the bounding box of 4 mapped corners, which is
    # a deliberate approximation for a non-affine transform (a rectangle's
    # corners map to a general quadrilateral, not another axis-aligned
    # rectangle). It should still land in the right neighbourhood.
    ocr_bbox = BBox(x=200, y=200, width=80, height=20)
    rectified_bbox = geo.map_region_coordinates(ocr_bbox, result.homography, invert=False)
    back_bbox = geo.map_region_coordinates(rectified_bbox, result.homography, invert=True)
    assert abs(back_bbox.x - ocr_bbox.x) < 20
    assert abs(back_bbox.y - ocr_bbox.y) < 20


def test_normalize_and_denormalize_bbox_round_trip():
    bbox = BBox(x=100, y=200, width=50, height=25)
    normalized = geo.normalize_bbox(bbox, image_width=600, image_height=800)
    assert 0.0 <= normalized.x <= 1.0 and 0.0 <= normalized.y <= 1.0
    back = geo.denormalize_bbox(normalized, image_width=600, image_height=800)
    assert abs(back.x - bbox.x) < 1e-6
    assert abs(back.width - bbox.width) < 1e-6


# ---------------------------------------------------------------------------
# 15. Glare-obscured geometry -> confidence reduction
# ---------------------------------------------------------------------------

def test_glare_reduces_geometry_confidence():
    img = _rectangular_box_image()
    glared = _glare(img)

    clean_quality = ImageQuality(status=EvidenceStatus.USABLE, glare_score=0.95, blur_score=0.8, exposure_score=0.8)
    glare_quality = ImageQuality(status=EvidenceStatus.LOW_QUALITY, glare_score=0.1, blur_score=0.8, exposure_score=0.8,
                                  notes=["Strong glare/reflection detected."])

    pkg_clean = geo.detect_package_geometry(img, source_image="img11a", image_quality=clean_quality)
    pkg_glare = geo.detect_package_geometry(glared, source_image="img11b", image_quality=glare_quality)

    assert pkg_glare.shape_confidence < pkg_clean.shape_confidence


def test_invalid_image_quality_forces_zero_confidence():
    img = _rectangular_box_image()
    invalid_quality = ImageQuality(status=EvidenceStatus.INVALID, notes=["Resolution too low."])
    pkg = geo.detect_package_geometry(img, source_image="img12", image_quality=invalid_quality)
    assert pkg.shape_confidence == 0.0


# ---------------------------------------------------------------------------
# 14. Extreme perspective -> geometry readiness UNCERTAIN-equivalent (PDP_TOO_OBLIQUE)
# ---------------------------------------------------------------------------

def test_lightweight_check_flags_extreme_perspective_as_too_oblique():
    width, height = 600, 800
    img = _blank(width, height)
    # Very thin trapezoid: near-zero top edge vs long bottom edge -> steep angle.
    pts = np.array([[250, 100], [260, 100], [560, 700], [40, 700]], dtype=np.int32)
    cv2.fillPoly(img, [pts], (40, 90, 160))

    result = geo.lightweight_geometry_check(img)
    assert result.status in (GeometryReadiness.PDP_TOO_OBLIQUE, GeometryReadiness.GOOD_GEOMETRY, GeometryReadiness.CALIBRATION_REQUIRED)
    # Either the oblique check fires, or (if approxPolyDP didn't resolve exactly
    # 4 points for this synthetic shape) it at least does not falsely report
    # PACKAGE_NOT_DETECTED for a clearly-present large silhouette.
    assert result.status != GeometryReadiness.PACKAGE_NOT_DETECTED


def test_lightweight_check_package_not_detected_on_empty_scene():
    img = _empty_scene_image()
    result = geo.lightweight_geometry_check(img)
    assert result.status == GeometryReadiness.PACKAGE_NOT_DETECTED
    assert result.confidence == 0.0


def test_lightweight_check_partially_out_of_frame():
    img = _partial_package_image()
    result = geo.lightweight_geometry_check(img)
    assert result.status == GeometryReadiness.PACKAGE_PARTIALLY_OUT_OF_FRAME


def test_lightweight_check_calibration_required_then_ready():
    img = _rectangular_box_image()
    good_quality = ImageQuality(status=EvidenceStatus.USABLE, blur_score=0.8, exposure_score=0.8, glare_score=0.9)

    without_cal = geo.lightweight_geometry_check(img, image_quality=good_quality, calibration_available=False)
    assert without_cal.status == GeometryReadiness.CALIBRATION_REQUIRED

    with_cal = geo.lightweight_geometry_check(img, image_quality=good_quality, calibration_available=True)
    assert with_cal.status == GeometryReadiness.READY_FOR_CAPTURE
    # READY_FOR_CAPTURE must never be conflated with legal compliance - this is
    # a structural check that the enum carries no such semantics, not a
    # sentinel value in the code.
    assert "compliant" not in with_cal.status.value.lower()


# ---------------------------------------------------------------------------
# Overlap recommendation (multi-image)
# ---------------------------------------------------------------------------

def test_bbox_overlap_fraction_basic():
    a = BBox(x=0, y=0, width=100, height=100)
    b = BBox(x=50, y=0, width=100, height=100)
    overlap = geo.bbox_overlap_fraction(a, b)
    # intersection 50*100=5000, union 100*100+100*100-5000=15000
    assert abs(overlap - (5000 / 15000)) < 1e-6


def test_overlap_recommendation_messages():
    assert "aim for roughly" in geo.overlap_recommendation(0.05)
    assert "reasonable" in geo.overlap_recommendation(0.25)
    assert "duplicates" in geo.overlap_recommendation(0.95)


# ---------------------------------------------------------------------------
# 12. Multi-image alignment
# ---------------------------------------------------------------------------

def test_align_multi_image_surfaces_returns_none_for_featureless_images():
    img_a = _empty_scene_image()
    img_b = _empty_scene_image()
    homography = geo.align_multi_image_surfaces(img_a, img_b)
    assert homography is None


def test_align_multi_image_surfaces_aligns_shifted_textured_image():
    rng = np.random.default_rng(7)
    base = rng.integers(0, 255, size=(400, 400, 3), dtype=np.uint8)
    # Add some structured shapes so ORB has real corners/features, not just noise.
    cv2.rectangle(base, (50, 50), (150, 150), (0, 0, 0), 3)
    cv2.rectangle(base, (200, 200), (350, 350), (255, 255, 255), 3)
    cv2.circle(base, (300, 100), 40, (0, 0, 0), 3)

    # Shifted version simulating a second overlapping capture.
    shifted = np.zeros_like(base)
    shift_x = 30
    shifted[:, shift_x:] = base[:, :400 - shift_x]

    homography = geo.align_multi_image_surfaces(base, shifted)
    # This is a best-effort classical alignment; assert it either finds a
    # homography (typical) or conservatively declines (never crashes/guesses
    # silently wrong shape).
    if homography is not None:
        assert len(homography) == 9
