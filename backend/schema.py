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


class CanonicalStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_DETECTED_IN_PROVIDED_IMAGES = "NOT_DETECTED_IN_PROVIDED_IMAGES"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    PARTIALLY_DETECTED = "PARTIALLY_DETECTED"
    DETECTED = "DETECTED"
    VERIFIED = "VERIFIED"
    NON_COMPLIANT = "NON_COMPLIANT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class CanonicalDeclarationField(str, Enum):
    MANUFACTURER_NAME_ADDRESS = "manufacturer_name_address"
    COMMON_NAME = "common_name"
    NET_QUANTITY = "net_quantity"
    MFG_DATE = "mfg_date"
    BEST_BEFORE_USE_BY = "best_before_use_by"
    MRP = "mrp"
    CONSUMER_CARE = "consumer_care"
    UNIT_SALE_PRICE = "unit_sale_price"
    BATCH_NO = "batch_no"
    STANDARD_PACK_SIZE = "standard_pack_size"
    COUNTRY_OF_ORIGIN = "country_of_origin"


class DeclarationEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    image_id: str
    page_or_view: Optional[str] = "other"  # "front", "back", "other"
    bbox: Optional[List[float]] = None     # [x1, y1, x2, y2]
    source: str = "ocr"                    # "ocr", "vlm", "both"


class ValidationDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")
    present: Optional[bool] = None
    readable: Optional[bool] = None
    correct_format: Optional[bool] = None
    compliant: Optional[bool] = None


class CanonicalDeclaration(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str
    canonical_name: str
    label: Optional[str] = None
    value: Optional[str] = None
    normalized_value: Optional[Any] = None
    raw_text: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    extraction_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: CanonicalStatus = CanonicalStatus.INSUFFICIENT_EVIDENCE
    evidence: Optional[DeclarationEvidence] = None
    validation: ValidationDetails = Field(default_factory=ValidationDetails)
    reason: str = ""
    rule_id: Optional[str] = None
    rule_clause: Optional[str] = None

    @property
    def canonical_field(self) -> str:
        return self.field

    @property
    def extracted_value(self) -> Optional[str]:
        return self.value

    @property
    def label_present(self) -> bool:
        return bool(self.label)

    @property
    def value_present(self) -> bool:
        return bool(self.value)

    @property
    def provenance(self) -> Optional[DeclarationEvidence]:
        return self.evidence

    @property
    def statutory_rule(self) -> Optional[str]:
        return self.rule_clause or self.rule_id

    @property
    def rule_description(self) -> Optional[str]:
        return self.reason


CANONICAL_DECLARATION_DEFINITIONS: Dict[str, Dict[str, str]] = {
    "manufacturer_name_address": {
        "canonical_name": "Manufacturer / Packer / Importer Name & Address",
        "rule_id": "LMPC-2011-R6-DECLARATIONS",
        "rule_clause": "Rule 6(1)(a)/(b)/(c)",
    },
    "common_name": {
        "canonical_name": "Common / Generic Name of Commodity",
        "rule_id": "LMPC-2011-R6-DECLARATIONS",
        "rule_clause": "Rule 6(1)(b)",
    },
    "net_quantity": {
        "canonical_name": "Net Quantity",
        "rule_id": "LMPC-2011-R6-DECLARATIONS",
        "rule_clause": "Rule 6(1)(e)",
    },
    "mfg_date": {
        "canonical_name": "Manufacturing / Packing Date",
        "rule_id": "LMPC-2011-R6-DECLARATIONS",
        "rule_clause": "Rule 6(1)(d)",
    },
    "best_before_use_by": {
        "canonical_name": "Best Before / Use By / Expiry Date",
        "rule_id": "LMPC-2011-R6-DECLARATIONS",
        "rule_clause": "Rule 6(1)(d) proviso",
    },
    "mrp": {
        "canonical_name": "Maximum Retail Price (MRP)",
        "rule_id": "LMPC-2011-R6-DECLARATIONS",
        "rule_clause": "Rule 6(1)(da)",
    },
    "consumer_care": {
        "canonical_name": "Consumer Care Details",
        "rule_id": "LMPC-2011-R6-DECLARATIONS",
        "rule_clause": "Rule 6(1)(da)/(f)",
    },
    "unit_sale_price": {
        "canonical_name": "Unit Sale Price",
        "rule_id": "LMPC-2011-R6-11-UNIT-PRICE",
        "rule_clause": "Rule 6(11)",
    },
    "batch_no": {
        "canonical_name": "Batch / Lot / Code Number",
        "rule_id": "LMPC-2011-R6-DECLARATIONS",
        "rule_clause": "Rule 6(1) / FSSAI 2.2.2",
    },
    "standard_pack_size": {
        "canonical_name": "Standard Pack Size (Second Schedule)",
        "rule_id": "LMPC-2011-R5-STANDARD-PACK",
        "rule_clause": "Rule 5 / Second Schedule",
    },
    "country_of_origin": {
        "canonical_name": "Country of Origin (Imported)",
        "rule_id": "LMPC-2011-R6-DECLARATIONS",
        "rule_clause": "Rule 6(1)(a) proviso",
    },
}

CANONICAL_FIELD_ALIASES: Dict[str, str] = {
    "mrp": "mrp",
    "maximum retail price": "mrp",
    "m.r.p.": "mrp",
    "mrp:": "mrp",
    "mrp rs.": "mrp",
    "mrp ₹": "mrp",
    "retail price": "mrp",
    "retail sale price": "mrp",
    "use by": "best_before_use_by",
    "use before": "best_before_use_by",
    "best before": "best_before_use_by",
    "best before/use by": "best_before_use_by",
    "best before / use by": "best_before_use_by",
    "expiry": "best_before_use_by",
    "expiry_date": "best_before_use_by",
    "exp date": "best_before_use_by",
    "consume before": "best_before_use_by",
    "mfg date": "mfg_date",
    "mfd": "mfg_date",
    "mfg_date": "mfg_date",
    "date of manufacture": "mfg_date",
    "date of packing": "mfg_date",
    "packed date": "mfg_date",
    "pkd": "mfg_date",
    "pkd.": "mfg_date",
    "manufacturer": "manufacturer_name_address",
    "manufacturer_name": "manufacturer_name_address",
    "manufacturer_name_address": "manufacturer_name_address",
    "manufactured by": "manufacturer_name_address",
    "packed by": "manufacturer_name_address",
    "packer_name": "manufacturer_name_address",
    "imported by": "manufacturer_name_address",
    "importer_name": "manufacturer_name_address",
    "marketer": "manufacturer_name_address",
    "marketed by": "manufacturer_name_address",
    "net quantity": "net_quantity",
    "net_quantity": "net_quantity",
    "net qty": "net_quantity",
    "net weight": "net_quantity",
    "net wt": "net_quantity",
    "net vol": "net_quantity",
    "net volume": "net_quantity",
    "common name": "common_name",
    "common_name": "common_name",
    "generic name": "common_name",
    "consumer care": "consumer_care",
    "consumer_care": "consumer_care",
    "customer care": "consumer_care",
    "helpline": "consumer_care",
    "unit sale price": "unit_sale_price",
    "unit_sale_price": "unit_sale_price",
    "unit price": "unit_sale_price",
    "usp": "unit_sale_price",
    "batch no": "batch_no",
    "batch_no": "batch_no",
    "batch number": "batch_no",
    "batch": "batch_no",
    "lot no": "batch_no",
    "lot number": "batch_no",
    "lot code": "batch_no",
    "standard pack size": "standard_pack_size",
    "standard_pack_size": "standard_pack_size",
    "country of origin": "country_of_origin",
    "country_of_origin": "country_of_origin",
}


def normalize_declaration_field(field_name: str) -> Optional[str]:
    clean = field_name.strip().lower().replace("-", "_")
    if clean in CANONICAL_FIELD_ALIASES:
        return CANONICAL_FIELD_ALIASES[clean]
    clean_spaces = clean.replace("_", " ")
    if clean_spaces in CANONICAL_FIELD_ALIASES:
        return CANONICAL_FIELD_ALIASES[clean_spaces]
    return clean if clean in CANONICAL_DECLARATION_DEFINITIONS else None



class MeasurementMode(str, Enum):
    VERIFIED = "VERIFIED"
    ESTIMATED = "ESTIMATED"
    UNCERTAIN = "UNCERTAIN"
    NOT_OBSERVED = "NOT_OBSERVED"


class PackageShapeHint(str, Enum):
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
    REFERENCE_OBJECT = "REFERENCE_OBJECT"
    KNOWN_PACKAGE_DIMENSION = "KNOWN_PACKAGE_DIMENSION"
    USER_ENTERED_REFERENCE = "USER_ENTERED_REFERENCE"
    DEPTH_SENSOR = "DEPTH_SENSOR"
    NONE = "NONE"


class PDPObservationStatus(str, Enum):
    OBSERVED = "OBSERVED"
    PARTIAL = "PARTIAL"
    NOT_OBSERVED = "NOT_OBSERVED"


class GeometryReadiness(str, Enum):
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


class EvidenceAgreement(str, Enum):
    """
    How well the independent readings of ONE declaration agree with each other.

    This is the contract-level projection of the OCR layer's fusion state
    (`ocr_engine.FusionState`). The member names and values are deliberately
    IDENTICAL so that there is one vocabulary for "do the readings agree?"
    across the whole system rather than two that must be kept in step.

    Why this exists at all: the OCR engine reads the same region several times
    (different preprocessing variants, orientations, engines) and already
    detects when two readings of the same pixels disagree — `MRP Rs. 50.00`
    versus `MRP Rs. 90.00`. That determination used to be computed and then
    discarded before the rule engine ever saw it, so a disputed reading arrived
    at the legal evaluation indistinguishable from an undisputed one.

    Semantics, and the distinction that matters legally:
      - CORROBORATED      two or more independent readings agreed.
      - SINGLE_SOURCE     one reading, no cross-check performed. This is an
                          honest default: it claims no corroboration, and it
                          reports no conflict.
      - CONFLICTING       independent readings of the same region disagreed.
                          The package is NOT thereby non-compliant — we simply
                          do not yet know what it declares. See invariant 4.
      - AGREEMENT_UNKNOWN the agreement state could not be determined (for
                          example an unrecognised value arrived from an upstream
                          component). Reserved for genuine indeterminacy; it
                          must never be used as a stand-in for SINGLE_SOURCE,
                          because that would silently assert "no conflict".

    CONFLICTING is a statement about the READING, never about the package, in
    exactly the way low OCR confidence is. Low confidence means "hard to read".
    CONFLICTING means "read two ways that cannot both be true". Neither is
    evidence of a legal breach, and neither may become one.
    """

    CORROBORATED = "CORROBORATED"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    CONFLICTING = "CONFLICTING"
    AGREEMENT_UNKNOWN = "AGREEMENT_UNKNOWN"

    def permits_definitive_finding(self) -> bool:
        """
        False when this agreement state forbids a definitive PASS/FAIL.

        Mirrors the tri-state applicability precedent already in the rule
        engine: an UNKNOWN state is still evaluated and still reported, but it
        can only reach UNCERTAIN. Expressed as a method on the enum so that the
        rule engine cannot disagree with the contract about which states are
        safe, and so a member added later must decide this question explicitly.
        """
        return self in (EvidenceAgreement.CORROBORATED, EvidenceAgreement.SINGLE_SOURCE)


def coerce_evidence_agreement(value: Any) -> EvidenceAgreement:
    """
    Interpret an agreement state arriving from another layer.

    An unrecognised value becomes AGREEMENT_UNKNOWN, never SINGLE_SOURCE.
    Defaulting to SINGLE_SOURCE would convert "we could not tell whether the
    readings agreed" into the positive claim "there was no disagreement" — the
    plausible-placeholder pattern that has already produced several silent
    defects in this codebase. AGREEMENT_UNKNOWN is conspicuous and, because it
    does not permit a definitive finding, it fails safe.
    """
    if isinstance(value, EvidenceAgreement):
        return value
    if value is None:
        return EvidenceAgreement.SINGLE_SOURCE
    try:
        return EvidenceAgreement(str(getattr(value, "value", value)))
    except ValueError:
        return EvidenceAgreement.AGREEMENT_UNKNOWN


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

    # Geometry subsystem additions (all optional / backward compatible)
    method: Optional[CalibrationMethod] = None
    source_image: Optional[str] = None
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


#: Recorded as `EvidenceReference.image_id` when an observation reaches the
#: legal engine with no known source image.
#:
#: This is deliberately not a plausible filename. Earlier code used the string
#: "unknown", which is indistinguishable from a photograph actually named
#: unknown.jpg once it is sitting in a database row or a printed report — so a
#: missing provenance record looked exactly like a real one. Every legal finding
#: must be traceable to its evidence, which means a break in that chain has to
#: be conspicuous rather than merely quiet.
UNATTRIBUTED_IMAGE_ID = "UNATTRIBUTED-NO-SOURCE-IMAGE"


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

    def is_attributed(self) -> bool:
        """True when this reference names a real source image."""
        return self.image_id != UNATTRIBUTED_IMAGE_ID

    def is_locatable(self) -> bool:
        """
        True when a reviewer could actually be shown this evidence: a named
        source image AND a region within it.
        """
        return self.is_attributed() and (
            self.bbox is not None or bool(self.polygon)
        )


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
    label: Optional[str] = None
    canonical_field: Optional[str] = None
    canonical_name: Optional[str] = None
    canonical_status: Optional[str] = None
    validation: Optional[Dict[str, Optional[bool]]] = None
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

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

    # Canonical declaration list & summary (deduplicated, typed, evidence-backed)
    declarations: List[CanonicalDeclaration] = Field(default_factory=list)
    declaration_summary: Dict[str, int] = Field(default_factory=dict)

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
