
from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

class ReviewStatus(str, Enum):
    AUTO_ACCEPTED="auto_accepted"; NEEDS_REVIEW="needs_review"; UNCERTAIN="uncertain"; REJECTED="rejected"

class ProvisionType(str, Enum):
    SHORT_TITLE="SHORT_TITLE"
    COMMENCEMENT="COMMENCEMENT"
    DEFINITION="DEFINITION"
    SCOPE="SCOPE"
    SUBSTANTIVE_AMENDMENT="SUBSTANTIVE_AMENDMENT"
    APPLICABILITY="APPLICABILITY"
    EXEMPTION="EXEMPTION"
    EXCEPTION="EXCEPTION"
    TRANSITIONAL="TRANSITIONAL"
    PROCEDURAL="PROCEDURAL"
    PENALTY="PENALTY"
    REPEAL="REPEAL"
    OTHER="OTHER"

class TextSource(str, Enum):
    NATIVE="native"; OCR="ocr"; NONE="none"
class SemanticRole(str, Enum):
    DEFINITION="DEFINITION"; OBLIGATION="OBLIGATION"; PROHIBITION="PROHIBITION"; PERMISSION="PERMISSION"; CONDITION="CONDITION"; EXCEPTION="EXCEPTION"; EXEMPTION="EXEMPTION"; SCOPE="SCOPE"; APPLICABILITY="APPLICABILITY"; THRESHOLD="THRESHOLD"; PROCEDURE="PROCEDURE"; EFFECTIVE_DATE="EFFECTIVE_DATE"; PENALTY="PENALTY"; EXPLANATION="EXPLANATION"; OTHER="OTHER"

class ClauseType(str, Enum):
    BODY="body"; SUBRULE="subrule"; SUBCLAUSE="subclause"; SUBSUBCLAUSE="subsubclause"; PROVISO="proviso"; EXPLANATION="explanation"; TABLE="table"; OBLIGATION="obligation"

class PageText(BaseModel):
    model_config=ConfigDict(extra="forbid")
    page_no:int=Field(ge=1); text:str=""; source:TextSource=TextSource.NONE; confidence:float=Field(default=0.0,ge=0.0,le=1.0); engine:Optional[str]=None; lang:Optional[str]=None; dpi:Optional[int]=None; psm:Optional[int]=None; warnings:List[str]=Field(default_factory=list)
class SourceLocation(BaseModel):
    model_config=ConfigDict(extra="forbid")
    document_id:str; page_start:int=Field(ge=1); page_end:int=Field(ge=1); section:Optional[str]=None; chapter:Optional[str]=None; clause:Optional[str]=None
class HeadingCandidate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    raw_number:str; page_no:int; line_index:int; line_text:str; accepted:bool; confidence:float=Field(ge=0.0,le=1.0); reasons:List[str]=Field(default_factory=list)

class ExtractionCondition(BaseModel):
    model_config=ConfigDict(extra="forbid")
    condition_text:str; condition_type:Optional[str]=None; source_text:str
class ExtractionRequirement(BaseModel):
    model_config=ConfigDict(extra="forbid")
    id:str; description:str; suggested_field:Optional[str]=None; condition_ref:Optional[str]=None; source_text:str
class ExtractionThreshold(BaseModel):
    model_config=ConfigDict(extra="forbid")
    value:float; unit:Optional[str]=None; operator:Optional[str]=None; label:Optional[str]=None; source_text:str
class ExtractionExemption(BaseModel):
    model_config=ConfigDict(extra="forbid")
    description:str; condition_text:Optional[str]=None; effective_from:Optional[str]=None; source_text:str
class EffectiveDates(BaseModel):
    model_config=ConfigDict(extra="forbid")
    effective_from:Optional[str]=None; effective_to:Optional[str]=None; effective_from_raw:Optional[str]=None; effective_to_raw:Optional[str]=None; effective_from_source_text:Optional[str]=None; effective_to_source_text:Optional[str]=None

class BoundThreshold(BaseModel):
    model_config=ConfigDict(extra="forbid")
    value:float; unit:Optional[str]=None; operator:Optional[str]=None; applies_to:Optional[str]=None; applies_to_confidence:float=Field(default=0.0,ge=0.0,le=1.0); clause_id:str; source_text:str; page:int
class ConditionInfo(BaseModel):
    model_config=ConfigDict(extra="forbid")
    subject:Optional[str]=None; condition_type:Optional[str]=None; condition_text:str; clause_id:str
class RequirementInfo(BaseModel):
    model_config=ConfigDict(extra="forbid")
    subject:Optional[str]=None; action:Optional[str]=None; object:Optional[str]=None; requirement_text:str; clause_id:str
class ExceptionInfo(BaseModel):
    model_config=ConfigDict(extra="forbid")
    modifies_clause_id:Optional[str]=None; description:str; condition_text:Optional[str]=None; is_exemption:bool=False; clause_id:str

class Clause(BaseModel):
    model_config=ConfigDict(extra="forbid")
    clause_id:str; rule_id:str; parent_clause_id:Optional[str]=None; clause_type:ClauseType; page_start:int; page_end:int; source_text:str
    provision_type:Optional[ProvisionType]=None; provision_confidence:float=Field(default=0.0,ge=0.0,le=1.0); is_substantive:bool=True
    semantic_role:SemanticRole=SemanticRole.OTHER; role_confidence:float=Field(default=0.0,ge=0.0,le=1.0); role_signals:List[str]=Field(default_factory=list)
    condition:Optional[ConditionInfo]=None; requirement:Optional[RequirementInfo]=None; thresholds:List[BoundThreshold]=Field(default_factory=list); exception:Optional[ExceptionInfo]=None; effective_date:Optional[EffectiveDates]=None; applies_to:List[str]=Field(default_factory=list)
    ocr_quality_flag:bool=False; ocr_quality_score:float=Field(default=1.0,ge=0.0,le=1.0); validation_errors:List[str]=Field(default_factory=list); validation_warnings:List[str]=Field(default_factory=list); confidence:float=Field(default=0.0,ge=0.0,le=1.0); review_status:ReviewStatus=ReviewStatus.NEEDS_REVIEW; llm_assist:Optional[Dict[str,Any]]=None

class ClassificationResult(BaseModel):
    model_config=ConfigDict(extra="forbid")
    categories:List[str]=Field(default_factory=list); confidence:float=Field(default=0.0,ge=0.0,le=1.0); signals:Dict[str,List[str]]=Field(default_factory=dict); review_status:ReviewStatus=ReviewStatus.NEEDS_REVIEW

class ExtractedRule(BaseModel):
    model_config=ConfigDict(extra="forbid")
    rule_id:Optional[str]=None; rule_id_confidence:float=Field(default=0.0,ge=0.0,le=1.0); title:Optional[str]=None
    source:str; document_id:str; version:Optional[str]=None
    classification:ClassificationResult=Field(default_factory=ClassificationResult); subcategory:Optional[str]=None
    source_provision:Optional[str]=None; provision_type:Optional[ProvisionType]=None; is_substantive:bool=True; metadata_sources:Dict[str,Any]=Field(default_factory=dict)
    scope:Optional[str]=None; conditions:List[ExtractionCondition]=Field(default_factory=list); requirements:List[ExtractionRequirement]=Field(default_factory=list); thresholds:List[ExtractionThreshold]=Field(default_factory=list); exemptions:List[ExtractionExemption]=Field(default_factory=list)
    effective_dates:EffectiveDates=Field(default_factory=EffectiveDates); evidence_required:List[str]=Field(default_factory=list); clauses:List[Clause]=Field(default_factory=list); validation_errors:List[str]=Field(default_factory=list); validation_warnings:List[str]=Field(default_factory=list)
    text:str; source_location:SourceLocation; raw_ocr_text:Optional[str]=None; extraction_confidence:float=Field(default=0.0,ge=0.0,le=1.0); review_status:ReviewStatus=ReviewStatus.NEEDS_REVIEW; review_reasons:List[str]=Field(default_factory=list)
    amendment_target:Optional[str]=None  # canonical target rule, e.g. "Rule 6(1)(a)"
    amendment_item:Optional[str]=None    # positional id in the amending document, e.g. "(i)"


class ReviewRecord(BaseModel):
    model_config=ConfigDict(extra="forbid")
    rule_key:str; system_extraction:ExtractedRule; reviewer_correction:Dict[str,Any]=Field(default_factory=dict); corrected_fields:List[str]=Field(default_factory=list); corrected_rule:Optional[ExtractedRule]=None; corrected_by:Optional[str]=None; corrected_at:Optional[str]=None
class PipelineResult(BaseModel):
    model_config=ConfigDict(extra="forbid")
    document_id:str; source:str; page_range:Optional[List[int]]=None; pages:List[PageText]=Field(default_factory=list); candidates:List[HeadingCandidate]=Field(default_factory=list); rules:List[ExtractedRule]=Field(default_factory=list); rejected_count:int=0; warnings:List[str]=Field(default_factory=list); metadata:Dict[str,Any]=Field(default_factory=dict)

# ---------------------------------------------------------------------------
# Regulatory-domain models retained by the main LexMetra application
# ---------------------------------------------------------------------------

class ApplicabilityStatus(str, Enum):
    APPLICABLE="APPLICABLE"
    NOT_APPLICABLE="NOT_APPLICABLE"
    CONDITIONAL="CONDITIONAL"
    UNKNOWN="UNKNOWN"
    REVIEW_REQUIRED="REVIEW_REQUIRED"

class RegulatoryStatus(str, Enum):
    COMPLIANT="COMPLIANT"
    NON_COMPLIANT="NON_COMPLIANT"
    UNCERTAIN="UNCERTAIN"
    NOT_APPLICABLE="NOT_APPLICABLE"
    REVIEW_REQUIRED="REVIEW_REQUIRED"

class EvidenceState(str, Enum):
    VERIFIED="VERIFIED"
    CORROBORATED="CORROBORATED"
    CONFLICTING="CONFLICTING"
    UNCERTAIN="UNCERTAIN"
    NOT_OBSERVED="NOT_OBSERVED"
    ESTIMATED="ESTIMATED"
    REVIEW_REQUIRED="REVIEW_REQUIRED"

class ApprovalState(str, Enum):
    DRAFT="DRAFT"
    EXTRACTED="EXTRACTED"
    AI_PARSED="AI_PARSED"
    PENDING_REVIEW="PENDING_REVIEW"
    APPROVED="APPROVED"
    SCHEDULED="SCHEDULED"
    ACTIVE="ACTIVE"
    SUPERSEDED="SUPERSEDED"
    REJECTED="REJECTED"

class RAGGroundingStatus(str, Enum):
    GROUNDED="GROUNDED"
    NOT_FOUND="NOT_FOUND"
    CONFLICTING_SOURCES="CONFLICTING_SOURCES"
    REVIEW_REQUIRED="REVIEW_REQUIRED"

class RegulatoryContext(BaseModel):
    model_config=ConfigDict(extra="allow")
    product_category:Optional[str]=None
    commodity_type:Optional[str]=None
    package_type:Optional[str]=None
    net_quantity:Optional[float]=None
    unit:Optional[str]=None
    sale_type:Optional[str]=None
    consumer_type:Optional[str]=None
    is_imported:Optional[bool]=None
    country:Optional[str]=None
    manufacturer:Optional[str]=None
    packer:Optional[str]=None
    department:Optional[str]=None
    regulatory_modules:List[str]=Field(default_factory=list)
    inspection_date:date
    jurisdiction:Optional[str]="IN"
    special_conditions:Dict[str,Any]=Field(default_factory=dict)

class EvidenceRequirement(BaseModel):
    id:str
    field:Optional[str]=None
    description:str
    condition:Optional[str]=None
    required:bool=True

class RuleVersion(BaseModel):
    id:str
    module:str
    regulation:str
    rule_id:str
    version:str
    effective_from:date
    effective_to:Optional[date]=None
    approval_state:ApprovalState
    source_document_id:Optional[str]=None
    source_url:Optional[str]=None
    conditions:Dict[str,Any]=Field(default_factory=dict)
    thresholds:List[Dict[str,Any]]=Field(default_factory=list)
    evidence_requirements:List[EvidenceRequirement]=Field(default_factory=list)
    text:Optional[str]=None
    extraction_metadata:Dict[str,Any]=Field(default_factory=dict)

class RegulatoryFinding(BaseModel):
    rule_id:str
    requirement_id:Optional[str]=None
    module:str
    department:str
    regulation:str
    rule_version:Optional[str]=None
    status:RegulatoryStatus
    reason:str
    applicability:ApplicabilityStatus
    evidence_state:EvidenceState
    evidence:List[Dict[str,Any]]=Field(default_factory=list)
    confidence:Optional[float]=Field(default=None,ge=0,le=1)
    review_required:bool=False
    source:Optional[str]=None

class RegulatoryModuleMetadata(BaseModel):
    id:str
    name:str
    department:str
    regulation:str
    jurisdiction:str="IN"
    status:str="experimental"

class AmendmentChange(BaseModel):
    rule_id:str
    change_type:str
    old_text:Optional[str]=None
    new_text:Optional[str]=None
    effective_from:Optional[date]=None
    threshold_changes:List[Dict[str,Any]]=Field(default_factory=list)
    applicability_changes:List[Dict[str,Any]]=Field(default_factory=list)
    changed_fields:List[str]=Field(default_factory=list)

class AmendmentDraft(BaseModel):
    id:str
    module:str
    source_document_id:str
    approval_state:ApprovalState=ApprovalState.DRAFT
    extracted_at:datetime
    changes:List[AmendmentChange]=Field(default_factory=list)
    proposed_rule_versions:List[RuleVersion]=Field(default_factory=list)
    impact:Dict[str,Any]=Field(default_factory=dict)

class KnowledgeChunk(BaseModel):
    id:str
    module:str
    department:str
    regulation:str
    document_id:str
    document_version:str
    rule_version:Optional[str]=None
    rule_id:Optional[str]=None
    effective_from:date
    effective_to:Optional[date]=None
    index_version:str
    page:Optional[int]=None
    section:Optional[str]=None
    clause:Optional[str]=None
    language:str="en"
    commodity:Optional[str]=None
    jurisdiction:str="IN"
    text:str
    source_url:Optional[str]=None
    source_reference:Optional[str]=None
    metadata:Dict[str,Any]=Field(default_factory=dict)

class RAGSource(BaseModel):
    chunk_id:str
    document_id:str
    rule_id:Optional[str]=None
    page:Optional[int]=None
    effective_from:date
    effective_to:Optional[date]=None
    score:float
    retrieval_method:str
    source_reference:Optional[str]=None

class RAGResponse(BaseModel):
    answer:str
    query_type:str
    sources:List[RAGSource]=Field(default_factory=list)
    rule_ids:List[str]=Field(default_factory=list)
    module:Optional[str]=None
    effective_date:date
    retrieval_hits:int=0
    confidence:float=Field(default=0,ge=0,le=1)
    grounding_status:RAGGroundingStatus
    citation:List[str]=Field(default_factory=list)
    warning:Optional[str]=None
