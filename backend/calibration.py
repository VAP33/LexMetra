"""
Calibration + physical measurement + uncertainty.

Scope and honesty:
- A photograph has pixels, not millimetres. Nothing in this module invents a
  pixels-per-mm scale; every PhysicalMeasurement traces back to an explicit
  CalibrationInfo record with a stated method, or it is NOT_OBSERVED/UNCERTAIN.
- This module NEVER decides legal compliance. It produces measurement
  evidence for rule_engine.py (specifically the Rule 7(2) font-height check
  and the Rule 7(1) PDP-area formula already encoded in rules.json) to
  consume. See PDP_AREA_FORMULA below, which mirrors
  rules/rules.json -> LMPC-2011-R7-PDP-AREA -> pdp_area_formula exactly, so
  the two never drift apart. If that rule's formula changes, update the
  mirror here and in rules.json together.
- MeasurementMode.VERIFIED is only ever produced when calibration.validated
  is True. An unvalidated (self-reported, uncross-checked) calibration can
  still produce ESTIMATED measurements for review, never VERIFIED.

Integration point for Claude 3:
- calibrate_from_reference_object / calibrate_from_known_dimension /
  calibrate_from_user_reference all return a schema.CalibrationInfo, which
  is the SAME model already embedded on SurfaceObservation.calibration. No
  new calibration schema was introduced.
- measure_bbox / measure_pdp_area return schema.PhysicalMeasurement records.
  main.py currently accepts a manually-entered `pdp_area_cm2` float; wiring
  estimate_pdp_area_cm2's `.value` in as an optional autofill (still subject
  to inspector confirmation) is a main.py change left for Claude 3, since
  this agent's brief is not to modify main.py/rule_engine.py.
"""

from __future__ import annotations

import math
from typing import List, Optional

from schema import (
    BBox,
    CalibrationInfo,
    CalibrationMethod,
    GeometryType,
    MeasurementMode,
    PDPGeometry,
    PhysicalMeasurement,
)

# Mirrors rules/rules.json -> LMPC-2011-R7-PDP-AREA -> pdp_area_formula.
# rectangular:                     height_cm * width_cm
# cylindrical / nearly cylindrical: 0.40 * height_cm * circumference_cm
# other shape:                      0.40 * total_surface_area_cm2 (or an
#                                    otherwise-applicable PDP area) -- this
#                                    module cannot responsibly estimate total
#                                    surface area for IRREGULAR/UNKNOWN
#                                    shapes from a single 2D image, so it
#                                    returns UNCERTAIN rather than guessing.
PDP_AREA_CYLINDRICAL_FACTOR = 0.40

MM_PER_CM = 10.0


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def _pixels_per_mm(pixel_length: float, reference_mm: float) -> Optional[float]:
    if pixel_length <= 0 or reference_mm <= 0:
        return None
    return pixel_length / reference_mm


def calibrate_from_reference_object(
    *,
    reference_pixel_length: float,
    reference_dimension_mm: float,
    source_image: str,
    scale_uncertainty_relative: float = 0.03,
    validated: bool = True,
) -> CalibrationInfo:
    """
    Calibrate using a known-size reference object (e.g. a printed calibration
    card, a coin, an ISO card) visible in the same image plane as the PDP.

    `scale_uncertainty_relative` defaults to 3%, a conservative allowance for
    corner-localization error on a well-defined printed reference; callers
    with a worse-localized reference should pass a larger value.
    """
    ppm = _pixels_per_mm(reference_pixel_length, reference_dimension_mm)
    if ppm is None:
        return CalibrationInfo(available=False, method=CalibrationMethod.REFERENCE_OBJECT, source_image=source_image)

    return CalibrationInfo(
        available=True,
        reference_type="reference_object",
        reference_dimension_mm=reference_dimension_mm,
        pixels_per_mm=ppm,
        validated=validated,
        validation_note="Reference-object calibration; accuracy depends on reference placement in the PDP plane.",
        method=CalibrationMethod.REFERENCE_OBJECT,
        source_image=source_image,
        scale_uncertainty_relative=scale_uncertainty_relative,
        confidence=0.85 if validated else 0.5,
    )


def calibrate_from_known_package_dimension(
    *,
    known_pixel_length: float,
    known_dimension_mm: float,
    source_image: str,
    dimension_source_note: str,
    scale_uncertainty_relative: float = 0.08,
) -> CalibrationInfo:
    """
    Calibrate using a package dimension that is independently known (e.g. a
    declared bottle height, or a standard package size), measured in pixels
    in the current image. Higher default uncertainty than a purpose-built
    reference object, because the "known" dimension is usually a printed
    spec rather than something designed for calibration.
    """
    ppm = _pixels_per_mm(known_pixel_length, known_dimension_mm)
    if ppm is None:
        return CalibrationInfo(
            available=False, method=CalibrationMethod.KNOWN_PACKAGE_DIMENSION, source_image=source_image,
        )

    return CalibrationInfo(
        available=True,
        reference_type="known_package_dimension",
        reference_dimension_mm=known_dimension_mm,
        pixels_per_mm=ppm,
        validated=False,
        validation_note=f"Derived from a known package dimension ({dimension_source_note}); not independently cross-checked.",
        method=CalibrationMethod.KNOWN_PACKAGE_DIMENSION,
        source_image=source_image,
        scale_uncertainty_relative=scale_uncertainty_relative,
        confidence=0.55,
    )


def calibrate_from_user_reference(
    *,
    reference_pixel_length: float,
    reference_dimension_mm: float,
    source_image: str,
    scale_uncertainty_relative: float = 0.10,
) -> CalibrationInfo:
    """
    Calibrate from an inspector-entered reference length measured against a
    visible feature in the image (e.g. "this edge is 85 mm"). Treated as
    unvalidated by default -- an inspector's manual measurement is evidence,
    not an independently-verified reference.
    """
    ppm = _pixels_per_mm(reference_pixel_length, reference_dimension_mm)
    if ppm is None:
        return CalibrationInfo(
            available=False, method=CalibrationMethod.USER_ENTERED_REFERENCE, source_image=source_image,
        )

    return CalibrationInfo(
        available=True,
        reference_type="user_entered_reference",
        reference_dimension_mm=reference_dimension_mm,
        pixels_per_mm=ppm,
        validated=False,
        validation_note="Inspector-entered reference dimension; not independently cross-checked.",
        method=CalibrationMethod.USER_ENTERED_REFERENCE,
        source_image=source_image,
        scale_uncertainty_relative=scale_uncertainty_relative,
        confidence=0.5,
    )


def calibrate_from_depth(
    *,
    pixels_per_mm: float,
    depth_confidence: float,
    source_image: str,
) -> CalibrationInfo:
    """
    Calibrate from a camera/AR depth estimate (schema.CameraPose). Depth-derived
    scale is treated as VALIDATED only when the reported depth_confidence is
    high, and its uncertainty is derived from (1 - depth_confidence) rather
    than a fixed constant, since depth quality varies a lot by device/distance.
    """
    if pixels_per_mm <= 0:
        return CalibrationInfo(available=False, method=CalibrationMethod.DEPTH_SENSOR, source_image=source_image)

    depth_confidence = max(0.0, min(1.0, depth_confidence))
    validated = depth_confidence >= 0.75

    return CalibrationInfo(
        available=True,
        reference_type="depth_sensor",
        pixels_per_mm=pixels_per_mm,
        validated=validated,
        validation_note="Derived from device depth/AR tracking; accuracy varies by device and capture distance.",
        method=CalibrationMethod.DEPTH_SENSOR,
        source_image=source_image,
        scale_uncertainty_relative=round(max(0.05, 1.0 - depth_confidence), 3),
        confidence=depth_confidence,
    )


# ---------------------------------------------------------------------------
# Measurement + uncertainty
# ---------------------------------------------------------------------------

def estimate_measurement_uncertainty(
    pixel_length: float,
    calibration: CalibrationInfo,
    pixel_localization_uncertainty_px: float = 1.5,
) -> Optional[float]:
    """
    Propagate pixel-localization uncertainty and calibration-scale
    uncertainty into an absolute uncertainty (in mm) for a single measured
    length.

    Uses standard relative-error combination in quadrature:
        relative_uncertainty = sqrt(
            (pixel_localization_uncertainty_px / pixel_length)^2
            + (scale_uncertainty_relative)^2
        )
        absolute_uncertainty_mm = value_mm * relative_uncertainty

    `pixel_localization_uncertainty_px` defaults to 1.5 px, a conservative
    allowance for edge/corner localization noise on a typical phone-camera
    photo; callers with a noisier detector should pass a larger value.
    """
    if calibration.pixels_per_mm is None or calibration.pixels_per_mm <= 0 or pixel_length <= 0:
        return None

    value_mm = pixel_length / calibration.pixels_per_mm
    scale_rel = calibration.scale_uncertainty_relative
    if scale_rel is None:
        # No stated scale uncertainty: fall back to a conservative default
        # rather than pretending the scale is exact.
        scale_rel = 0.10

    pixel_rel = pixel_localization_uncertainty_px / pixel_length
    relative_uncertainty = math.sqrt(pixel_rel ** 2 + scale_rel ** 2)
    return round(value_mm * relative_uncertainty, 4)


def _measurement_status(calibration: Optional[CalibrationInfo]) -> MeasurementMode:
    if calibration is None or not calibration.available or calibration.pixels_per_mm is None:
        return MeasurementMode.UNCERTAIN
    return MeasurementMode.VERIFIED if calibration.validated else MeasurementMode.ESTIMATED


def measure_length_px(
    pixel_length: float,
    calibration: Optional[CalibrationInfo],
    *,
    quantity: str,
    source_image: Optional[str] = None,
    source_region: Optional[BBox] = None,
) -> PhysicalMeasurement:
    """Convert one pixel length into a PhysicalMeasurement in mm."""
    if calibration is None or not calibration.available or not calibration.pixels_per_mm:
        return PhysicalMeasurement(
            quantity=quantity,
            unit="mm",
            status=MeasurementMode.UNCERTAIN,
            confidence=0.0,
            source_image=source_image,
            source_region=source_region,
            reason="No calibration is available; pixel length cannot be converted to a physical measurement.",
        )

    if pixel_length <= 0:
        return PhysicalMeasurement(
            quantity=quantity,
            unit="mm",
            status=MeasurementMode.UNCERTAIN,
            confidence=0.0,
            source_image=source_image,
            source_region=source_region,
            reason="Non-positive pixel length; cannot measure.",
        )

    value_mm = round(pixel_length / calibration.pixels_per_mm, 4)
    uncertainty = estimate_measurement_uncertainty(pixel_length, calibration)
    status = _measurement_status(calibration)
    confidence = calibration.confidence if calibration.confidence is not None else (0.8 if status == MeasurementMode.VERIFIED else 0.5)

    reason = (
        f"Converted from {pixel_length:.1f}px using {calibration.pixels_per_mm:.3f} px/mm "
        f"({calibration.method.value if calibration.method else calibration.reference_type or 'unknown'} calibration)."
    )
    if status != MeasurementMode.VERIFIED:
        reason += " Calibration is not independently validated, so this measurement is an estimate, not a verified value."

    return PhysicalMeasurement(
        quantity=quantity,
        value=value_mm,
        unit="mm",
        uncertainty=uncertainty,
        confidence=round(float(confidence), 3),
        status=status,
        source_image=source_image,
        source_region=source_region,
        calibration_method=calibration.method,
        reason=reason,
    )


def measure_bbox(
    bbox: BBox,
    calibration: Optional[CalibrationInfo],
    *,
    source_image: Optional[str] = None,
) -> List[PhysicalMeasurement]:
    """Measure the width and height of a bbox in mm."""
    width_measurement = measure_length_px(
        bbox.width, calibration, quantity="region_width", source_image=source_image, source_region=bbox,
    )
    height_measurement = measure_length_px(
        bbox.height, calibration, quantity="region_height", source_image=source_image, source_region=bbox,
    )
    return [width_measurement, height_measurement]


def measure_pdp_area(
    pdp: PDPGeometry,
    shape: GeometryType,
    calibration: Optional[CalibrationInfo],
    *,
    circumference_bbox: Optional[BBox] = None,
) -> PhysicalMeasurement:
    """
    Compute PDP area in cm^2 using the SAME shape-dependent formula encoded
    in rules/rules.json (LMPC-2011-R7-PDP-AREA), so this module's output is
    directly usable as the rule engine's `pdp_area_cm2` input:

        rectangular:              height_cm * width_cm
        cylindrical/near-cyl.:    0.40 * height_cm * circumference_cm
        other shape:              not estimated here -> UNCERTAIN

    This function does NOT decide compliance and does NOT itself feed
    rule_engine.py; it produces the evidence Claude 3 can choose to wire in
    as an optional autofill for the inspector-supplied `pdp_area_cm2` field.
    """
    if pdp.bbox is None:
        return PhysicalMeasurement(
            quantity="pdp_area",
            unit="cm2",
            status=MeasurementMode.NOT_OBSERVED,
            confidence=0.0,
            source_image=pdp.source_image,
            reason="No PDP region has been observed yet.",
        )

    if calibration is None or not calibration.available or not calibration.pixels_per_mm:
        return PhysicalMeasurement(
            quantity="pdp_area",
            unit="cm2",
            status=MeasurementMode.UNCERTAIN,
            confidence=0.0,
            source_image=pdp.source_image,
            source_region=pdp.bbox,
            reason="PDP region is observed, but no calibration is available to convert pixels to physical area.",
        )

    width_m = measure_length_px(pdp.bbox.width, calibration, quantity="pdp_width", source_image=pdp.source_image, source_region=pdp.bbox)
    height_m = measure_length_px(pdp.bbox.height, calibration, quantity="pdp_height", source_image=pdp.source_image, source_region=pdp.bbox)

    if width_m.value is None or height_m.value is None:
        return PhysicalMeasurement(
            quantity="pdp_area",
            unit="cm2",
            status=MeasurementMode.UNCERTAIN,
            confidence=0.0,
            source_image=pdp.source_image,
            source_region=pdp.bbox,
            reason="Width/height measurement failed; area cannot be computed.",
        )

    status = MeasurementMode.VERIFIED if (width_m.status == MeasurementMode.VERIFIED and height_m.status == MeasurementMode.VERIFIED) else MeasurementMode.ESTIMATED
    confidence = min(width_m.confidence, height_m.confidence)

    if shape == GeometryType.FLAT:
        height_cm = height_m.value / MM_PER_CM
        width_cm = width_m.value / MM_PER_CM
        area_cm2 = height_cm * width_cm
        reason = f"Rectangular PDP area = height_cm * width_cm = {height_cm:.2f} * {width_cm:.2f} cm2."

    elif shape in (GeometryType.CYLINDRICAL, GeometryType.NEAR_CYLINDRICAL):
        if circumference_bbox is None:
            return PhysicalMeasurement(
                quantity="pdp_area",
                unit="cm2",
                status=MeasurementMode.UNCERTAIN,
                confidence=0.0,
                source_image=pdp.source_image,
                source_region=pdp.bbox,
                reason=(
                    "Package is cylindrical/near-cylindrical, which requires a measured "
                    "circumference (not just a single flat width) per the Rule 7(1) "
                    "formula; no circumference evidence was supplied."
                ),
            )
        circumference_m = measure_length_px(
            circumference_bbox.width, calibration, quantity="pdp_circumference", source_image=pdp.source_image, source_region=circumference_bbox,
        )
        if circumference_m.value is None:
            return PhysicalMeasurement(
                quantity="pdp_area",
                unit="cm2",
                status=MeasurementMode.UNCERTAIN,
                confidence=0.0,
                source_image=pdp.source_image,
                source_region=pdp.bbox,
                reason="Circumference measurement failed; cylindrical PDP area cannot be computed.",
            )
        height_cm = height_m.value / MM_PER_CM
        circumference_cm = circumference_m.value / MM_PER_CM
        area_cm2 = PDP_AREA_CYLINDRICAL_FACTOR * height_cm * circumference_cm
        confidence = min(confidence, circumference_m.confidence)
        status = MeasurementMode.VERIFIED if status == MeasurementMode.VERIFIED and circumference_m.status == MeasurementMode.VERIFIED else MeasurementMode.ESTIMATED
        reason = (
            f"Cylindrical PDP area = 0.40 * height_cm * circumference_cm = "
            f"0.40 * {height_cm:.2f} * {circumference_cm:.2f} cm2."
        )

    else:
        return PhysicalMeasurement(
            quantity="pdp_area",
            unit="cm2",
            status=MeasurementMode.UNCERTAIN,
            confidence=0.0,
            source_image=pdp.source_image,
            source_region=pdp.bbox,
            reason=(
                f"Package shape '{shape.value}' does not have a reliable single-image "
                "area formula in this module (Rule 7(1) 'other shape' requires total "
                "surface area or an alternative applicable PDP area). Not estimated."
            ),
        )

    # Area uncertainty via relative-error combination in quadrature.
    rel_w = (width_m.uncertainty / width_m.value) if width_m.uncertainty else 0.0
    rel_h = (height_m.uncertainty / height_m.value) if height_m.uncertainty else 0.0
    rel_area = math.sqrt(rel_w ** 2 + rel_h ** 2)
    uncertainty_cm2 = round(area_cm2 * rel_area, 4) if area_cm2 else None

    return PhysicalMeasurement(
        quantity="pdp_area",
        value=round(area_cm2, 4),
        unit="cm2",
        uncertainty=uncertainty_cm2,
        confidence=round(float(confidence), 3),
        status=status,
        source_image=pdp.source_image,
        source_region=pdp.bbox,
        calibration_method=calibration.method,
        reason=reason,
    )
