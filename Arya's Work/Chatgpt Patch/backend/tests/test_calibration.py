"""
Unit tests for calibration.py — no database/network required.
"""

from __future__ import annotations

import json
from pathlib import Path

import calibration as cal
from schema import (
    BBox,
    CalibrationInfo,
    CalibrationMethod,
    GeometryType,
    MeasurementMode,
    PDPGeometry,
    PDPObservationStatus,
)

RULES_PATH = Path(__file__).resolve().parent.parent.parent / "rules" / "rules.json"


# ---------------------------------------------------------------------------
# 6/7. Calibration reference + known physical scale -> pixel-to-mm conversion
# ---------------------------------------------------------------------------

def test_calibrate_from_reference_object_computes_pixels_per_mm():
    # A 85.60mm-wide reference card rendered as 428px wide (5 px/mm).
    calibration = cal.calibrate_from_reference_object(
        reference_pixel_length=428.0,
        reference_dimension_mm=85.6,
        source_image="img1",
    )
    assert calibration.available is True
    assert calibration.validated is True
    assert calibration.pixels_per_mm is not None
    assert abs(calibration.pixels_per_mm - 5.0) < 0.01
    assert calibration.method == CalibrationMethod.REFERENCE_OBJECT


def test_calibrate_from_known_package_dimension_is_unvalidated():
    calibration = cal.calibrate_from_known_package_dimension(
        known_pixel_length=200.0,
        known_dimension_mm=100.0,
        source_image="img2",
        dimension_source_note="declared bottle height",
    )
    assert calibration.available is True
    assert calibration.validated is False
    assert calibration.pixels_per_mm == 2.0


def test_calibrate_from_user_reference_is_unvalidated():
    calibration = cal.calibrate_from_user_reference(
        reference_pixel_length=100.0,
        reference_dimension_mm=50.0,
        source_image="img3",
    )
    assert calibration.available is True
    assert calibration.validated is False
    assert calibration.pixels_per_mm == 2.0


def test_calibrate_from_depth_validated_only_above_confidence_threshold():
    high_conf = cal.calibrate_from_depth(pixels_per_mm=3.0, depth_confidence=0.9, source_image="img4")
    low_conf = cal.calibrate_from_depth(pixels_per_mm=3.0, depth_confidence=0.4, source_image="img4")
    assert high_conf.validated is True
    assert low_conf.validated is False


def test_calibrate_with_zero_reference_length_is_unavailable():
    calibration = cal.calibrate_from_reference_object(
        reference_pixel_length=0.0, reference_dimension_mm=85.6, source_image="img5",
    )
    assert calibration.available is False


# ---------------------------------------------------------------------------
# 8. Pixel -> mm conversion for an arbitrary measured region
# ---------------------------------------------------------------------------

def test_measure_length_px_converts_correctly():
    calibration = cal.calibrate_from_reference_object(
        reference_pixel_length=500.0, reference_dimension_mm=100.0, source_image="img6",
    )  # 5 px/mm
    measurement = cal.measure_length_px(250.0, calibration, quantity="test_length", source_image="img6")
    assert measurement.value == 50.0
    assert measurement.status == MeasurementMode.VERIFIED


def test_measure_length_px_without_calibration_is_uncertain():
    measurement = cal.measure_length_px(250.0, None, quantity="test_length")
    assert measurement.status == MeasurementMode.UNCERTAIN
    assert measurement.value is None


def test_measure_bbox_returns_width_and_height():
    calibration = cal.calibrate_from_reference_object(
        reference_pixel_length=200.0, reference_dimension_mm=100.0, source_image="img7",
    )  # 2 px/mm
    bbox = BBox(x=0, y=0, width=100, height=50)
    measurements = cal.measure_bbox(bbox, calibration, source_image="img7")
    by_quantity = {m.quantity: m for m in measurements}
    assert by_quantity["region_width"].value == 50.0
    assert by_quantity["region_height"].value == 25.0


# ---------------------------------------------------------------------------
# 9. Measurement uncertainty
# ---------------------------------------------------------------------------

def test_uncertainty_increases_as_pixel_length_shrinks():
    calibration = CalibrationInfo(
        available=True, pixels_per_mm=5.0, validated=True,
        method=CalibrationMethod.REFERENCE_OBJECT, scale_uncertainty_relative=0.03,
    )
    small = cal.estimate_measurement_uncertainty(10.0, calibration)
    large = cal.estimate_measurement_uncertainty(500.0, calibration)
    assert small is not None and large is not None
    # Relative uncertainty from pixel localization dominates for short lengths.
    assert (small / (10.0 / 5.0)) > (large / (500.0 / 5.0))


def test_uncertainty_none_without_pixels_per_mm():
    calibration = CalibrationInfo(available=False)
    assert cal.estimate_measurement_uncertainty(100.0, calibration) is None


def test_verified_measurement_carries_lower_relative_uncertainty_than_estimated():
    verified_cal = cal.calibrate_from_reference_object(
        reference_pixel_length=500.0, reference_dimension_mm=100.0, source_image="img8",
        scale_uncertainty_relative=0.03,
    )
    estimated_cal = cal.calibrate_from_user_reference(
        reference_pixel_length=500.0, reference_dimension_mm=100.0, source_image="img8",
        scale_uncertainty_relative=0.10,
    )
    verified_measurement = cal.measure_length_px(300.0, verified_cal, quantity="q")
    estimated_measurement = cal.measure_length_px(300.0, estimated_cal, quantity="q")
    assert verified_measurement.status == MeasurementMode.VERIFIED
    assert estimated_measurement.status == MeasurementMode.ESTIMATED
    assert verified_measurement.uncertainty < estimated_measurement.uncertainty


# ---------------------------------------------------------------------------
# 13. Insufficient calibration -> UNCERTAIN (never invented millimetres)
# ---------------------------------------------------------------------------

def test_pdp_area_uncertain_without_calibration():
    pdp = PDPGeometry(
        source_image="img9",
        observation_status=PDPObservationStatus.OBSERVED,
        confidence=0.7,
        bbox=BBox(x=0, y=0, width=200, height=100),
    )
    measurement = cal.measure_pdp_area(pdp, GeometryType.FLAT, calibration=None)
    assert measurement.status == MeasurementMode.UNCERTAIN
    assert measurement.value is None


def test_pdp_area_not_observed_without_bbox():
    pdp = PDPGeometry(source_image="img10", observation_status=PDPObservationStatus.NOT_OBSERVED, confidence=0.0)
    measurement = cal.measure_pdp_area(pdp, GeometryType.FLAT, calibration=None)
    assert measurement.status == MeasurementMode.NOT_OBSERVED


# ---------------------------------------------------------------------------
# PDP area formula: rectangular vs cylindrical, matching rules.json exactly
# ---------------------------------------------------------------------------

def test_rectangular_pdp_area_matches_height_times_width_formula():
    # 10 px/mm calibration; PDP is 500x300 px -> 50mm x 30mm -> 5cm x 3cm -> 15 cm2.
    calibration = cal.calibrate_from_reference_object(
        reference_pixel_length=1000.0, reference_dimension_mm=100.0, source_image="img11",
    )
    pdp = PDPGeometry(
        source_image="img11",
        observation_status=PDPObservationStatus.OBSERVED,
        confidence=0.8,
        bbox=BBox(x=0, y=0, width=500, height=300),
    )
    measurement = cal.measure_pdp_area(pdp, GeometryType.FLAT, calibration)
    assert measurement.status == MeasurementMode.VERIFIED
    assert abs(measurement.value - 15.0) < 1e-6


def test_cylindrical_pdp_area_matches_040_height_times_circumference_formula():
    calibration = cal.calibrate_from_reference_object(
        reference_pixel_length=1000.0, reference_dimension_mm=100.0, source_image="img12",
    )  # 10 px/mm
    # height 300px -> 30mm -> 3cm; circumference 800px -> 80mm -> 8cm
    pdp = PDPGeometry(
        source_image="img12",
        observation_status=PDPObservationStatus.OBSERVED,
        confidence=0.7,
        bbox=BBox(x=0, y=0, width=300, height=300),
    )
    circumference_bbox = BBox(x=0, y=0, width=800, height=1)
    measurement = cal.measure_pdp_area(
        pdp, GeometryType.CYLINDRICAL, calibration, circumference_bbox=circumference_bbox,
    )
    expected = 0.40 * 3.0 * 8.0
    assert abs(measurement.value - expected) < 1e-6


def test_cylindrical_pdp_area_uncertain_without_circumference_evidence():
    calibration = cal.calibrate_from_reference_object(
        reference_pixel_length=1000.0, reference_dimension_mm=100.0, source_image="img13",
    )
    pdp = PDPGeometry(
        source_image="img13",
        observation_status=PDPObservationStatus.OBSERVED,
        confidence=0.7,
        bbox=BBox(x=0, y=0, width=300, height=300),
    )
    measurement = cal.measure_pdp_area(pdp, GeometryType.CYLINDRICAL, calibration, circumference_bbox=None)
    assert measurement.status == MeasurementMode.UNCERTAIN


def test_irregular_shape_pdp_area_not_estimated():
    calibration = cal.calibrate_from_reference_object(
        reference_pixel_length=1000.0, reference_dimension_mm=100.0, source_image="img14",
    )
    pdp = PDPGeometry(
        source_image="img14",
        observation_status=PDPObservationStatus.OBSERVED,
        confidence=0.6,
        bbox=BBox(x=0, y=0, width=300, height=300),
    )
    measurement = cal.measure_pdp_area(pdp, GeometryType.IRREGULAR, calibration)
    assert measurement.status == MeasurementMode.UNCERTAIN
    assert measurement.value is None


def test_pdp_area_formula_constants_match_rules_json():
    """
    Regression guard: calibration.PDP_AREA_CYLINDRICAL_FACTOR must always
    equal the factor encoded in rules/rules.json, so the two definitions of
    the legal formula can never silently drift apart.
    """
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rule = next(r for r in data["rules"] if r["rule_id"] == "LMPC-2011-R7-PDP-AREA")
    formula = rule["pdp_area_formula"]["cylindrical_or_nearly_cylindrical"]
    assert "0.40" in formula
    assert cal.PDP_AREA_CYLINDRICAL_FACTOR == 0.40


# ---------------------------------------------------------------------------
# Non-VERIFIED calibration never produces a VERIFIED measurement
# ---------------------------------------------------------------------------

def test_unvalidated_calibration_never_yields_verified_status():
    calibration = cal.calibrate_from_user_reference(
        reference_pixel_length=500.0, reference_dimension_mm=100.0, source_image="img15",
    )
    measurement = cal.measure_length_px(250.0, calibration, quantity="q")
    assert measurement.status == MeasurementMode.ESTIMATED
    assert measurement.status != MeasurementMode.VERIFIED
