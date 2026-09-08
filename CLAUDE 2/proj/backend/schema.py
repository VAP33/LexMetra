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


class EvidenceVerification(str, Enum):
    """
    How trustworthy the *extraction itself* is, independent of legal outcome.

    This is deliberately separate from FactStatus (PASS/FAIL/UNCERTAIN/EXEMPT),
    which is a legal conclusion. EvidenceVerification never appears in a legal
    disclaimer or PDF verdict; it explains WHY a fact carries the confidence
    it does, e.g. for an inspector/reviewer UI or audit trail.

    NOT_OBSERVED   - no OCR engine / capture produced this field at all.
    UNCERTAIN      - some evidence exists but is weak, unresolved, or a single
                     low-confidence source with no corroboration.
    CORROBORATED   - two or more independent sources (OCR engines, and/or
                     separate images) agree on the same value.
    CONFLICTING    - independent sources disagree; both are retained, neither
                     is silently preferred.
    VERIFIED       - a single strong, unambiguous, pattern-valid source. Not
                     as strong as CORROBORATED, but not merely UNCERTAIN.
    """

    NOT_OBSERVED = "NOT_OBSERVED"
    UNCERTAIN = "UNCERTAIN"
    VERIFIED = "VERIFIED"
    CORROBORATED = "CORROBORATED"
    CONFLICTING = "CONFLICTING"


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

    # --- Provenance / multi-source evidence (additive, all optional) -------
    # Every image that contributed to this field's final value. May contain
    # more than one entry only when spatial_relationship is set (see below).
    source_images: List[str] = Field(default_factory=list)
    # Every OCR/CV engine that reported this field, e.g. ["tesseract"] or
    # ["tesseract", "paddleocr"]. Used to compute `verification` below.
    ocr_engines: List[str] = Field(default_factory=list)
    preprocessing_variant: Optional[str] = None
    # Set only when this value was assembled from more than one image, e.g.
    # "cross_image_continuation" for a split declaration reconstructed across
    # two captures of the same surface. None for an ordinary single-image read.
    spatial_relationship: Optional[str] = None
    # Extraction trustworthiness, independent of legal status - see
    # EvidenceVerification docstring. Defaults to NOT_OBSERVED because a fact
    # should only claim a stronger verification state when something actually
    # produced and corroborated a value.
    verification: EvidenceVerification = EvidenceVerification.NOT_OBSERVED
    # When engines/images disagree, both raw readings are kept here instead of
    # silently picking one. Never invented; only populated on real conflict.
    conflicting_values: List[str] = Field(default_factory=list)


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
