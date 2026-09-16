"""Inspector evidence-chain aggregator (EVID-01).

Consumes persisted inspection rows, facts, findings, and stored image paths.
Does not change ExtractedFact / ProductInspection. The response is a *new*
read-model published as GET /inspections/{id}/evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EvidenceBBox(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float
    y: float
    width: float
    height: float


class EvidenceRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    extracted_value: Optional[str] = None
    raw_text: Optional[str] = None
    bbox: Optional[EvidenceBBox] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source_engine: Optional[str] = None
    fusion_state: Optional[str] = None
    image_id: Optional[str] = None
    status: Optional[str] = None
    review_required: bool = False
    reason: str = ""


class EvidenceFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str
    rule_version: Optional[str] = None
    status: str
    reason: str = ""
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    review_required: bool = False
    verification_status: Optional[str] = None
    required_evidence: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    image_ids: List[str] = Field(default_factory=list)


class EvidenceHonesty(BaseModel):
    """UI copy that must be shown; these are legal-safety invariants, not styling."""

    model_config = ConfigDict(extra="forbid")
    not_observed_is_not_missing: str = (
        "NOT_OBSERVED / not detected in the provided images is a statement "
        "about coverage, not a finding that the declaration is absent."
    )
    low_confidence_is_not_noncompliance: str = (
        "OCR/CV confidence is about readability. Low confidence must never be "
        "shown as a violation."
    )
    conflicting_readings_cap_uncertain: str = (
        "Conflicting readings of the same pixels cap the finding at UNCERTAIN; "
        "they are not a breach."
    )
    verification_status_note: str = (
        "Rules currently carry verification_status=needs_official_verification. "
        "A migrated or displayed rule is not a legal verification."
    )


class EvidenceChainResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inspection_id: str
    overall_status: str
    review_required: bool = False
    reviewed: bool = False
    disclaimer: str
    image_url: Optional[str] = None
    image_path_present: bool = False
    regions: List[EvidenceRegion] = Field(default_factory=list)
    findings: List[EvidenceFinding] = Field(default_factory=list)
    honesty: EvidenceHonesty = Field(default_factory=EvidenceHonesty)


def _bbox_from_any(value: Any) -> Optional[EvidenceBBox]:
    if value is None:
        return None
    if isinstance(value, dict):
        try:
            width = float(value.get("width", 0))
            height = float(value.get("height", 0))
            if width <= 0 or height <= 0:
                return None
            return EvidenceBBox(
                x=float(value.get("x", 0)),
                y=float(value.get("y", 0)),
                width=width,
                height=height,
            )
        except (TypeError, ValueError):
            return None
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        try:
            width = float(value[2])
            height = float(value[3])
            if width <= 0 or height <= 0:
                return None
            return EvidenceBBox(
                x=float(value[0]), y=float(value[1]), width=width, height=height
            )
        except (TypeError, ValueError):
            return None
    return None


def _confidence(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0.0 or number > 1.0:
        return max(0.0, min(1.0, number))
    return number


def build_evidence_chain(detail: Dict[str, Any]) -> EvidenceChainResponse:
    inspection_id = str(detail.get("inspection_id") or "")
    image_path = detail.get("image_path")
    image_present = bool(image_path and Path(str(image_path)).is_file())

    regions: List[EvidenceRegion] = []
    for fact in detail.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        evidence = fact.get("evidence") or []
        first = evidence[0] if evidence and isinstance(evidence[0], dict) else {}
        bbox = _bbox_from_any(first.get("bbox") or fact.get("bbox"))
        image_id = first.get("image_id") or fact.get("evidence_image")
        regions.append(
            EvidenceRegion(
                field=str(fact.get("field") or ""),
                extracted_value=fact.get("extracted_value"),
                raw_text=fact.get("raw_text") or fact.get("reason"),
                bbox=bbox,
                confidence=_confidence(fact.get("confidence")),
                ocr_confidence=_confidence(fact.get("ocr_confidence")),
                source_engine=(
                    (fact.get("validation") or {}).get("source_engine")
                    if isinstance(fact.get("validation"), dict)
                    else None
                ),
                fusion_state=(
                    (fact.get("validation") or {}).get("fusion_state")
                    if isinstance(fact.get("validation"), dict)
                    else None
                ),
                image_id=str(image_id) if image_id else None,
                status=str(fact.get("status") or "") or None,
                review_required=bool(fact.get("review_required")),
                reason=str(fact.get("reason") or ""),
            )
        )

    findings: List[EvidenceFinding] = []
    for finding in detail.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        image_ids = []
        for ref in finding.get("evidence") or []:
            if isinstance(ref, dict) and ref.get("image_id"):
                image_ids.append(str(ref["image_id"]))
        findings.append(
            EvidenceFinding(
                rule_id=str(finding.get("rule_id") or ""),
                rule_version=finding.get("rule_version"),
                status=str(finding.get("status") or "UNCERTAIN"),
                reason=str(finding.get("reason") or ""),
                confidence=_confidence(finding.get("confidence")),
                review_required=bool(finding.get("review_required")),
                verification_status=finding.get("verification_status"),
                required_evidence=list(finding.get("required_evidence") or []),
                missing_evidence=list(finding.get("missing_evidence") or []),
                image_ids=image_ids,
            )
        )

    disclaimer = str(
        detail.get("disclaimer")
        or (
            "This is an automated screening / pre-inspection aid, not a legal "
            "determination. Findings must be reviewed by an authorized Legal "
            "Metrology officer before any action."
        )
    )
    return EvidenceChainResponse(
        inspection_id=inspection_id,
        overall_status=str(detail.get("overall_status") or "UNCERTAIN"),
        review_required=bool(detail.get("review_required")),
        reviewed=bool(detail.get("reviewed")),
        disclaimer=disclaimer,
        image_url=f"/inspections/{inspection_id}/image" if image_present else None,
        image_path_present=image_present,
        regions=regions,
        findings=findings,
    )
