"""Compatibility facade for the canonical regulatory models.

Do not define duplicate regulatory models here. ``backend/models.py`` remains
the single source of truth.
"""
try:
    from ..models import (
        AmendmentChange, AmendmentDraft, ApplicabilityStatus, ApprovalState,
        EvidenceRequirement, EvidenceState, KnowledgeChunk, RAGGroundingStatus,
        RAGResponse, RAGSource, RegulatoryContext, RegulatoryFinding,
        RegulatoryModuleMetadata, RegulatoryStatus, RuleVersion,
    )
except ImportError:
    from models import (
        AmendmentChange, AmendmentDraft, ApplicabilityStatus, ApprovalState,
        EvidenceRequirement, EvidenceState, KnowledgeChunk, RAGGroundingStatus,
        RAGResponse, RAGSource, RegulatoryContext, RegulatoryFinding,
        RegulatoryModuleMetadata, RegulatoryStatus, RuleVersion,
    )
