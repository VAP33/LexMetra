"""Compatibility package for the canonical regulatory domain models.

The canonical model definitions remain in ``backend/models.py``. This package
exists so the existing RAG modules can safely import ``regulatory.models``
without creating a second source of truth.
"""

from .models import (
    AmendmentChange, AmendmentDraft, ApplicabilityStatus, ApprovalState,
    EvidenceRequirement, EvidenceState, KnowledgeChunk, RAGGroundingStatus,
    RAGResponse, RAGSource, RegulatoryContext, RegulatoryFinding,
    RegulatoryModuleMetadata, RegulatoryStatus, RuleVersion,
)

__all__ = [
    "AmendmentChange", "AmendmentDraft", "ApplicabilityStatus", "ApprovalState",
    "EvidenceRequirement", "EvidenceState", "KnowledgeChunk", "RAGGroundingStatus",
    "RAGResponse", "RAGSource", "RegulatoryContext", "RegulatoryFinding",
    "RegulatoryModuleMetadata", "RegulatoryStatus", "RuleVersion",
]
