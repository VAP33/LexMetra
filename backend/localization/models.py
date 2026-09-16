from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class LocalizationStatus(str, Enum):
    VERIFIED_MATCH = "VERIFIED_MATCH"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    UNLOCALIZED = "UNLOCALIZED"
    LOCALIZER_UNAVAILABLE = "LOCALIZER_UNAVAILABLE"


@dataclass(frozen=True)
class LocalizationSurface:
    face_id: str
    image_id: str
    canonical_image: Any
    canonical_width: int
    canonical_height: int
    original_width: int
    original_height: int
    forward_transform: Any
    inverse_transform: Any


@dataclass
class BoundingBoxCanonical:
    space: str = "CANONICAL_PIXEL"
    format: str = "XYWH"
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    image_width: int = 0
    image_height: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "space": self.space,
            "format": self.format,
            "x": round(float(self.x), 2),
            "y": round(float(self.y), 2),
            "width": round(float(self.width), 2),
            "height": round(float(self.height), 2),
            "image_width": int(self.image_width),
            "image_height": int(self.image_height),
        }


@dataclass
class LocalizedEvidence:
    evidence_id: str
    field: str
    face_id: str
    image_id: str
    value_source: str = "QWEN_3_8_27B"
    localization_source: str = "PADDLE_POLYGON_MATCH"
    localization_status: LocalizationStatus = LocalizationStatus.UNLOCALIZED
    localization_confidence: float = 0.0
    coarse_bbox_canonical: Optional[Dict[str, Any]] = None
    bbox_canonical: Optional[Dict[str, Any]] = None
    polygon_canonical: List[List[float]] = field(default_factory=list)
    bbox_original: Optional[Dict[str, Any]] = None
    polygon_original: List[List[float]] = field(default_factory=list)
    candidate_regions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "field": self.field,
            "face_id": self.face_id,
            "image_id": self.image_id,
            "value_source": self.value_source,
            "localization_source": self.localization_source,
            "localization_status": self.localization_status.value if isinstance(self.localization_status, LocalizationStatus) else str(self.localization_status),
            "localization_confidence": round(float(self.localization_confidence), 4),
            "coarse_bbox_canonical": self.coarse_bbox_canonical,
            "bbox_canonical": self.bbox_canonical,
            "polygon_canonical": self.polygon_canonical,
            "bbox_original": self.bbox_original,
            "polygon_original": self.polygon_original,
            "candidate_regions": self.candidate_regions,
        }
