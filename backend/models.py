"""Common, evidence-safe regulatory domain models.

The models in this package deliberately separate legal knowledge, applicability,
and compliance results. They are shared by LMPC and future FSSAI/CDSCO modules.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ApplicabilityStatus(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN = "UNKNOWN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class RegulatoryStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    UNCERTAIN = "UNCERTAIN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class EvidenceState(str, Enum):
    VERIFIED = "VERIFIED"
    CORROBORATED = "CORROBORATED"
    CONFLICTING = "CONFLICTING"
    UNCERTAIN = "UNCERTAIN"
    NOT_OBSERVED = "NOT_OBSERVED"
    ESTIMATED = "ESTIMATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ApprovalState(str, Enum):
    DRAFT = "DRAFT"
    EXTRACTED = "EXTRACTED"
    AI_PARSED = "AI_PARSED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class RAGGroundingStatus(str, Enum):
    GROUNDED = "GROUNDED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class RegulatoryContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_category: Optional[str] = None
    commodity_type: Optional[str] = None
    package_type: Optional[str] = None
    net_quantity: Optional[float] = None
    unit: Optional[str] = None
    sale_type: Optional[str] = None
    consumer_type: Optional[str] = None
    is_imported: Optional[bool] = None
    country: Optional[str] = None
    manufacturer: Optional[str] = None
    packer: Optional[str] = None
    department: Optional[str] = None
    regulatory_modules: List[str] = Field(default_factory=list)
    inspection_date: date
    jurisdiction: Optional[str] = "IN"
    special_conditions: Dict[str, Any] = Field(default_factory=dict)


class EvidenceRequirement(BaseModel):
    id: str
    field: Optional[str] = None
    description: str
    condition: Optional[str] = None
    required: bool = True


class RuleVersion(BaseModel):
    id: str
    module: str
    regulation: str
    rule_id: str
    version: str
    effective_from: date
    effective_to: Optional[date] = None
    approval_state: ApprovalState
    source_document_id: Optional[str] = None
    source_url: Optional[str] = None
    conditions: Dict[str, Any] = Field(default_factory=dict)
    thresholds: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_requirements: List[EvidenceRequirement] = Field(default_factory=list)
    text: Optional[str] = None


class RegulatoryFinding(BaseModel):
    rule_id: str
    requirement_id: Optional[str] = None
    module: str
    department: str
    regulation: str
    rule_version: Optional[str] = None
    status: RegulatoryStatus
    reason: str
    applicability: ApplicabilityStatus
    evidence_state: EvidenceState
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    review_required: bool = False
    source: Optional[str] = None


class RegulatoryModuleMetadata(BaseModel):
    id: str
    name: str
    department: str
    regulation: str
    jurisdiction: str = "IN"
    status: str = "experimental"


class AmendmentChange(BaseModel):
    rule_id: str
    change_type: str
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    effective_from: Optional[date] = None
    threshold_changes: List[Dict[str, Any]] = Field(default_factory=list)
    applicability_changes: List[Dict[str, Any]] = Field(default_factory=list)
    changed_fields: List[str] = Field(default_factory=list)


class AmendmentDraft(BaseModel):
    id: str
    module: str
    source_document_id: str
    approval_state: ApprovalState = ApprovalState.DRAFT
    extracted_at: datetime
    changes: List[AmendmentChange] = Field(default_factory=list)
    proposed_rule_versions: List[RuleVersion] = Field(default_factory=list)
    impact: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeChunk(BaseModel):
    id: str
    module: str
    department: str
    regulation: str
    document_id: str
    document_version: str
    rule_version: Optional[str] = None
    rule_id: Optional[str] = None
    effective_from: date
    effective_to: Optional[date] = None
    index_version: str
    page: Optional[int] = None
    section: Optional[str] = None
    clause: Optional[str] = None
    language: str = "en"
    commodity: Optional[str] = None
    jurisdiction: str = "IN"
    text: str
    source_url: Optional[str] = None
    source_reference: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RAGSource(BaseModel):
    chunk_id: str
    document_id: str
    rule_id: Optional[str] = None
    page: Optional[int] = None
    effective_from: date
    effective_to: Optional[date] = None
    score: float
    retrieval_method: str
    source_reference: Optional[str] = None


class RAGResponse(BaseModel):
    answer: str
    query_type: str
    sources: List[RAGSource] = Field(default_factory=list)
    rule_ids: List[str] = Field(default_factory=list)
    module: Optional[str] = None
    effective_date: date
    retrieval_hits: int = 0
    confidence: float = Field(default=0, ge=0, le=1)
    grounding_status: RAGGroundingStatus
    citation: List[str] = Field(default_factory=list)
    warning: Optional[str] = None
