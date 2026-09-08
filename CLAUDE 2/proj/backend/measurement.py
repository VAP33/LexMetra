"""
Measurement/calibration stub (master spec Part 14).

HONEST SCOPE: this module does NOT implement calibration-marker detection,
scale estimation, or any physical-measurement CV. No calibration reference
exists anywhere in this codebase's real photo set or capture flow. Building
real calibration (fiducial/ArUco detection, homography-based scale recovery)
is out of scope for this pass and is NOT claimed here.

What this module DOES do: provide the single, explicit gate that every
measurement-consuming caller (e.g. a future Rule 7 evaluator) must go
through, so "no calibration available" always and only produces
UNCERTAIN/ESTIMATED - never a fabricated confident millimetre value. This
exists so that if/when real calibration is added later, it plugs into one
place instead of every caller inventing its own "trust this pixel count"
logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MeasurementConfidence(str, Enum):
    UNCERTAIN = "UNCERTAIN"    # no calibration reference at all
    ESTIMATED = "ESTIMATED"    # a rough scale assumption was used (e.g. a
                                # typical object size) - never legally binding
    VERIFIED = "VERIFIED"      # a real calibration reference was detected
                                # and used - NOT IMPLEMENTED in this build


@dataclass
class MeasurementResult:
    value_mm: Optional[float]
    confidence: MeasurementConfidence
    calibration_source: Optional[str]
    note: str


def measure_with_calibration(
    pixel_length: float,
    calibration_reference_mm_per_pixel: Optional[float] = None,
) -> MeasurementResult:
    """
    The only supported entry point for turning a pixel measurement into a
    physical one. `calibration_reference_mm_per_pixel` must come from an
    actual detected calibration reference (e.g. a card of known size) -
    nothing in this codebase currently produces that value, so every real
    caller today gets UNCERTAIN back. This is intentional, not a bug.
    """
    if calibration_reference_mm_per_pixel is None:
        return MeasurementResult(
            value_mm=None,
            confidence=MeasurementConfidence.UNCERTAIN,
            calibration_source=None,
            note=(
                "No calibration reference available. Pixel measurements alone "
                "cannot establish physical size - this must remain UNCERTAIN, "
                "never a fabricated millimetre value. Provide a calibration "
                "reference (e.g. a card of known size in frame) to measure."
            ),
        )

    return MeasurementResult(
        value_mm=round(pixel_length * calibration_reference_mm_per_pixel, 2),
        confidence=MeasurementConfidence.VERIFIED,
        calibration_source="provided_reference",
        note="Computed from an explicitly provided calibration reference.",
    )
