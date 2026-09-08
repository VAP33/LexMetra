"""
Shared contract every module (OCR/CV, rule engine, backend, frontend) must honor.

Design goals:
- One stable contract for parallel development.
- Multi-image / multi-surface inspections.
- Evidence-first compliance: absence from one image is not automatically "missing".
- Explicit measurement confidence.
- Versioned legal-rule references.
- Backward-compatible core fields from the original prototype.

This schema describes evidence and decisions. It does not contain legal policy.
Legal requirements belong in rules/rules.json and are evaluated by the rule engine.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FactStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"
    EXEMPT = "EXEMPT"


class MeasurementMode(str, Enum):
    VERIFIED = "VERIFIED"
    ESTIMATED = "ESTIMATED"
    UNCERTAIN = "UNCERTAIN"
    # Added for the geometry/calibration subsystem: distinguishes "we looked
    # and there is nothing to measure yet" (NOT_OBSERVED) from "we attempted
    # a measurement but cannot trust it" (UNCERTAIN). Existing callers that
    # compare `mode != MeasurementMode.VERIFIED` are unaffected.
    NOT_OBSERVED = "NOT_OBSERVED"


class PackageShapeHint(str, Enum):
    """
    Descriptive package-shape classification (geometry subsystem).

    This is informational/descriptive only. It is NOT the legally
    load-bearing shape category — that remains `GeometryType`, which is what
    the Rule 7(1) PDP-area formula keys off (rectangular vs
    cylindrical/nearly-cylindrical vs other). `PackageShapeHint` gives a
    finer-grained, human-readable guess (e.g. "BOTTLE" vs "JAR") without
    inventing a second legal-geometry taxonomy.
    """

    RECTANGULAR = "RECTANGULAR"
    CYLINDRICAL = "CYLINDRICAL"
    NEAR_CYLINDRICAL = "NEAR_CYLINDRICAL"
    POUCH = "POUCH"
    BOTTLE = "BOTTLE"
    JAR = "JAR"
    BOX = "BOX"
    IRREGULAR = "IRREGULAR"
    UNKNOWN = "UNKNOWN"


class CalibrationMethod(str, Enum):
    """How pixels-per-mm was established for a piece of calibration evidence."""

    REFERENCE_OBJECT = "REFERENCE_OBJECT"          # e.g. calibration card / coin of known size
    KNOWN_PACKAGE_DIMENSION = "KNOWN_PACKAGE_DIMENSION"  # declared net-content dimension used as a ruler
    USER_ENTERED_REFERENCE = "USER_ENTERED_REFERENCE"    # inspector typed in a reference length
    DEPTH_SENSOR = "DEPTH_SENSOR"                  # phone AR/depth-derived scale
    NONE = "NONE"


class PDPObservationStatus(str, Enum):
    """
    Whether a Principal Display Panel was actually seen in a capture.

    Mirrors the project-wide "NOT VISIBLE != MISSING" rule: absence of a PDP
    sighting is NOT_OBSERVED (keep capturing), never an implicit legal
    finding.
    """

    OBSERVED = "OBSERVED"
    PARTIAL = "PARTIAL"
    NOT_OBSERVED = "NOT_OBSERVED"


class GeometryReadiness(str, Enum):
    """
    Lightweight, live-capture-facing geometry signal.

    IMPORTANT: `READY_FOR_CAPTURE` means "geometry is suitable to capture
    evidence from", and NEVER means "legally compliant". Legal compliance is
    decided exclusively by rule_engine.py.
    """

    PACKAGE_NOT_DETECTED = "PACKAGE_NOT_DETECTED"
    PACKAGE_PARTIALLY_OUT_OF_FRAME = "PACKAGE_PARTIALLY_OUT_OF_FRAME"
    PDP_TOO_OBLIQUE = "PDP_TOO_OBLIQUE"
    INSUFFICIENT_SURFACE_VISIBLE = "INSUFFICIENT_SURFACE_VISIBLE"
    CALIBRATION_REQUIRED = "CALIBRATION_REQUIRED"
    GOOD_GEOMETRY = "GOOD_GEOMETRY"
    READY_FOR_CAPTURE = "READY_FOR_CAPTURE"


class GeometryType(str, Enum):
    FLAT = "FLAT"
    CYLINDRICAL = "CYLINDRICAL"
    NEAR_CYLINDRICAL = "NEAR_CYLINDRICAL"
    IRREGULAR = "IRREGULAR"
    UNKNOWN = "UNKNOWN"


class SurfaceType(str, Enum):
    FRONT = "FRONT"
    BACK = "BACK"
    SIDE = "SIDE"
    LABEL = "LABEL"
    NECK = "NECK"
    CAP = "CAP"
    CRIMP = "CRIMP"
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    WRAPAROUND = "WRAPAROUND"
    UNKNOWN = "UNKNOWN"


class EvidenceStatus(str, Enum):
    USABLE = "USABLE"
    LOW_QUALITY = "LOW_QUALITY"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"


class CaptureMode(str, Enum):
    SINGLE_IMAGE = "SINGLE_IMAGE"
    GUIDED = "GUIDED"
    CALIBRATED = "CALIBRATED"
    MANUAL = "MANUAL"


class PositionCoordinateSystem(str, Enum):
    IMAGE_PIXELS = "IMAGE_PIXELS"
    NORMALIZED_0_1 = "NORMALIZED_0_1"


# ---------------------------------------------------------------------------
# Basic geometry / evidence models
# ---------------------------------------------------------------------------

class BBox(BaseModel):
    """Bounding box in the coordinate system declared by the parent evidence."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0)
    y: float = Field(ge=0.0)
    width: float = Field(gt=0.0)
    height: float = Field(gt=0.0)

    def right(self) -> float:
        return self.x + self.width

    def bottom(self) -> float:
        return self.y + self.height


class PolygonPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class ImageQuality(BaseModel):
    """
    Objective image-quality metadata.

    Scores are normalized to [0, 1] where produced by the vision pipeline.
    None means that the corresponding metric was not calculated.
    """

    model_config = ConfigDict(extra="forbid")

    status: EvidenceStatus = EvidenceStatus.USABLE
    blur_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    glare_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    exposure_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    perspective_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ocr_quality_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)


class CameraPose(BaseModel):
    """
    Optional camera/AR metadata.

    This is deliberately descriptive, not a certified metrology record.
    """

    model_config = ConfigDict(extra="forbid")

    tracking_available: bool = False
    position_x_m: Optional[float] = None
    position_y_m: Optional[float] = None
    position_z_m: Optional[float] = None
    rotation_quaternion: Optional[List[float]] = Field(
        default=None,
        min_length=4,
        max_length=4,
    )
    depth_available: bool = False
    depth_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CalibrationInfo(BaseModel):
    """
    Calibration evidence for physical measurement.

    A measurement must not be marked VERIFIED merely because a pixel-to-mm
    conversion was guessed. The calibration source and validation state must
    be explicit.
    """

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    reference_type: Optional[str] = None
    reference_dimension_mm: Optional[float] = Field(default=None, gt=0.0)
    pixels_per_mm: Optional[float] = Field(default=None, gt=0.0)
    validated: bool = False
    validation_note: Optional[str] = None

    # --- Geometry-subsystem additions (all optional / backward compatible) ---
    method: Optional[CalibrationMethod] = None
    source_image: Optional[str] = None
    # Relative uncertainty of pixels_per_mm, e.g. 0.05 == +/-5%. Kept separate
    # from per-measurement uncertainty because one calibration is reused
    # across many measurements on the same image.
    scale_uncertainty_relative: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SurfaceObservation(BaseModel):
    """
    One captured package surface.

    An inspection may contain any number of these. Do not assume a package
    has six faces, or that "front/back" covers all legally relevant evidence.
    """

    model_config = ConfigDict(extra="forbid")

    surface_id: str
    image_id: str
    image_uri: Optional[str] = None
    surface_type: SurfaceType = SurfaceType.UNKNOWN
    geometry: GeometryType = GeometryType.UNKNOWN

    # Position data for the detected declaration/PDP region.
    coordinate_system: PositionCoordinateSystem = (
        PositionCoordinateSystem.IMAGE_PIXELS
    )
    pdp_bbox: Optional[BBox] = None
    pdp_polygon: Optional[List[PolygonPoint]] = None

    # 0..1 estimate of how much relevant package information this observation
    # covers. This is evidence coverage, not physical surface-area coverage.
    evidence_coverage: float = Field(default=0.0, ge=0.0, le=1.0)

    image_quality: ImageQuality = Field(default_factory=ImageQuality)
    camera_pose: Optional[CameraPose] = None
    calibration: Optional[CalibrationInfo] = None

    capture_mode: CaptureMode = CaptureMode.SINGLE_IMAGE
    rotation_index: Optional[int] = Field(default=None, ge=0)
    notes: List[str] = Field(default_factory=list)


class EvidenceReference(BaseModel):
    """
    Precise pointer to visual evidence supporting a fact or rule finding.
    """

    model_config = ConfigDict(extra="forbid")

    image_id: str
    surface_id: Optional[str] = None
    bbox: Optional[BBox] = None
    polygon: Optional[List[PolygonPoint]] = None
    coordinate_system: PositionCoordinateSystem = (
        PositionCoordinateSystem.IMAGE_PIXELS
    )
    evidence_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Geometry / PDP / calibration / physical-measurement evidence
#
# Produced by geometry.py and calibration.py. This is evidence, exactly like
# ImageQuality or CalibrationInfo above: it never contains a legal
# PASS/FAIL/EXEMPT decision. The rule engine remains the only place that
# decides compliance; these models only carry what was observed/measured and
# how confident/uncertain that observation is.
# ---------------------------------------------------------------------------

class PackageGeometry(BaseModel):
    """Package-boundary evidence for one captured image."""

    model_config = ConfigDict(extra="forbid")

    source_image: str
    shape: GeometryType = GeometryType.UNKNOWN
    shape_hint: PackageShapeHint = PackageShapeHint.UNKNOWN
    shape_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    coordinate_system: PositionCoordinateSystem = (
        PositionCoordinateSystem.IMAGE_PIXELS
    )
    bbox: Optional[BBox] = None
    polygon: Optional[List[PolygonPoint]] = None

    # Fraction of the full image frame occupied by the detected package
    # contour. Useful for "partially out of frame" / "too far away" checks.
    contour_area_fraction: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    touches_image_border: bool = False

    notes: List[str] = Field(default_factory=list)


class PDPGeometry(BaseModel):
    """
    Principal Display Panel candidate geometry for one captured image.

    Distinct from PackageGeometry: a package boundary is not a PDP, and a
    PDP is not automatically planar (see `is_planar`).
    """

    model_config = ConfigDict(extra="forbid")

    source_image: str
    observation_status: PDPObservationStatus = PDPObservationStatus.NOT_OBSERVED
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    coordinate_system: PositionCoordinateSystem = (
        PositionCoordinateSystem.IMAGE_PIXELS
    )
    bbox: Optional[BBox] = None
    polygon: Optional[List[PolygonPoint]] = None

    is_planar: bool = False
    orientation_deg: Optional[float] = None
    surface_hint: SurfaceType = SurfaceType.UNKNOWN

    # True only when this PDPGeometry was derived purely from package
    # geometry (i.e. no OCR/text evidence contributed), which callers may
    # want to weight differently.
    derived_from_package_boundary_only: bool = False

    notes: List[str] = Field(default_factory=list)


class RectificationResult(BaseModel):
    """
    Perspective-rectification provenance for a planar PDP candidate.

    The rectified image is a DERIVED artifact. The original image and
    coordinates are never overwritten or discarded.
    """

    model_config = ConfigDict(extra="forbid")

    source_image: str
    source_polygon: List[PolygonPoint] = Field(min_length=4, max_length=4)
    # Row-major 3x3 homography (9 values) mapping source-image pixel
    # coordinates -> rectified-image pixel coordinates.
    homography: List[float] = Field(min_length=9, max_length=9)
    rectified_width_px: int = Field(gt=0)
    rectified_height_px: int = Field(gt=0)
    # Mean corner reprojection error in source-image pixels; a rough
    # rectification-quality indicator, not a legal precision claim.
    reprojection_error_px: Optional[float] = Field(default=None, ge=0.0)
    notes: List[str] = Field(default_factory=list)


class PhysicalMeasurement(BaseModel):
    """
    One physical-unit measurement derived from pixels + calibration.

    `status` reuses MeasurementMode so downstream evaluators (e.g.
    rule_engine._evaluate_font_height) can keep comparing against
    MeasurementMode.VERIFIED without a second parallel status type.
    """

    model_config = ConfigDict(extra="forbid")

    quantity: str  # e.g. "pdp_width", "pdp_height", "pdp_area", "numeral_height"
    value: Optional[float] = None
    unit: str = "mm"
    uncertainty: Optional[float] = Field(default=None, ge=0.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: MeasurementMode = MeasurementMode.NOT_OBSERVED

    source_image: Optional[str] = None
    source_region: Optional[BBox] = None
    calibration_method: Optional[CalibrationMethod] = None

    reason: str = ""
    notes: List[str] = Field(default_factory=list)


class GeometryReadinessResult(BaseModel):
    """Live-capture-facing geometry signal. Never a compliance signal."""

    model_config = ConfigDict(extra="forbid")

    status: GeometryReadiness = GeometryReadiness.PACKAGE_NOT_DETECTED
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Extracted facts
# ---------------------------------------------------------------------------

class ExtractedFact(BaseModel):
    """
    One declaration field extracted by OCR/CV and evaluated by the rule engine.

    Important distinction:
    - extracted_value = what the system observed
    - status = the legal/evidence evaluation of that field
    - confidence = model/evidence confidence, not legal certainty
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    extracted_value: Optional[str] = None

    status: FactStatus = FactStatus.UNCERTAIN
    confidence: float = Field(ge=0.0, le=1.0)

    # Rule references are authoritative only when they point to a rule record
    # loaded from the versioned legal rule dataset.
    rule_id: Optional[str] = None
    rule_version: Optional[str] = None

    # Backward-compatible single-image evidence pointer.
    evidence_image: Optional[str] = None
    bbox: Optional[BBox] = None

    # Preferred multi-capture evidence representation.
    evidence: List[EvidenceReference] = Field(default_factory=list)

    measurement_mode: Optional[MeasurementMode] = None
    measured_value: Optional[float] = None
    measured_unit: Optional[str] = None

    # Useful when an extracted value was normalized from OCR text.
    raw_text: Optional[str] = None
    normalized_value: Optional[str] = None

    reason: str = ""
    review_required: bool = False

    # Keeps extraction confidence and legal decision confidence separate.
    extraction_confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    decision_confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )


# ---------------------------------------------------------------------------
# Rule findings / inspection-level evidence
# ---------------------------------------------------------------------------

class RuleFinding(BaseModel):
    """
    Result of evaluating one legal rule.

    The engine should create findings even when the final inspection status
    is UNCERTAIN, because the user needs to know what evidence was missing.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    rule_version: Optional[str] = None
    status: FactStatus = FactStatus.UNCERTAIN

    requirement_id: Optional[str] = None
    requirement_description: Optional[str] = None

    reason: str = ""
    evidence: List[EvidenceReference] = Field(default_factory=list)

    required_evidence: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    review_required: bool = False

    verification_status: Optional[str] = None


class InspectionSummary(BaseModel):
    """
    Machine-readable summary for dashboards and reports.
    """

    model_config = ConfigDict(extra="forbid")

    total_rules_evaluated: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    uncertain: int = Field(default=0, ge=0)
    exempt: int = Field(default=0, ge=0)
    review_required: int = Field(default=0, ge=0)

    evidence_complete: bool = False
    coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ProductIdentity(BaseModel):
    """
    Optional product identity information used for history/similarity.

    Similarity is never itself a compliance decision.
    """

    model_config = ConfigDict(extra="forbid")

    product_id: Optional[str] = None
    product_name: Optional[str] = None
    brand: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    similarity_match_id: Optional[str] = None
    similarity_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Main inspection contract
# ---------------------------------------------------------------------------

class ProductInspection(BaseModel):
    """
    Complete inspection contract shared by backend, OCR/CV, rule engine and UI.

    Existing prototype fields are retained where practical so the refactor
    does not force every module to change at once.
    """

    model_config = ConfigDict(extra="forbid")

    inspection_id: str

    # Product / legal context
    product_category: str
    sale_type: str  # retail | wholesale | industrial | institutional | ecommerce
    inspection_date: Optional[str] = None
    applicable_rule_version: Optional[str] = None

    # Package context
    package_weight_or_volume: Optional[float] = Field(default=None, ge=0.0)
    package_weight_unit: Optional[str] = None
    geometry: GeometryType = GeometryType.UNKNOWN

    # New multi-surface evidence model
    captures: List[SurfaceObservation] = Field(default_factory=list)

    # Extracted declaration facts
    facts: List[ExtractedFact] = Field(default_factory=list)

    # Rule-level results
    findings: List[RuleFinding] = Field(default_factory=list)

    # Optional identity/history metadata
    product_identity: Optional[ProductIdentity] = None

    # High-level result
    overall_status: FactStatus = FactStatus.UNCERTAIN
    exempt_reason: Optional[str] = None

    summary: InspectionSummary = Field(default_factory=InspectionSummary)

    # Whether the current evidence is enough to make all intended checks.
    evidence_complete: bool = False
    review_required: bool = False

    disclaimer: str = (
        "This is an automated screening / pre-inspection aid, not a legal "
        "determination. Findings must be reviewed by an authorized Legal "
        "Metrology officer before any action."
    )


# ---------------------------------------------------------------------------
# Utility response models for API boundaries
# ---------------------------------------------------------------------------

class CaptureRequest(BaseModel):
    """Metadata accompanying one uploaded/captured image."""

    model_config = ConfigDict(extra="forbid")

    image_id: str
    surface_id: Optional[str] = None
    surface_type: SurfaceType = SurfaceType.UNKNOWN
    capture_mode: CaptureMode = CaptureMode.SINGLE_IMAGE
    geometry: GeometryType = GeometryType.UNKNOWN


class InspectionCreateRequest(BaseModel):
    """Minimal request for creating an inspection before image processing."""

    model_config = ConfigDict(extra="forbid")

    inspection_id: str
    product_category: str
    sale_type: str = "retail"
    geometry: GeometryType = GeometryType.UNKNOWN


class InspectionResponse(BaseModel):
    """Stable top-level API response."""

    model_config = ConfigDict(extra="forbid")

    inspection: ProductInspection
    api_version: str = "1.0"
