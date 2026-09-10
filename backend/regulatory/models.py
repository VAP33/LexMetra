"""Compatibility facade for the canonical regulatory models.

Do not define duplicate regulatory models here. ``backend/models.py`` remains
the single source of truth. The fallback supports both package imports and the
existing backend runtime where ``backend`` is on ``PYTHONPATH``.
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

__all__ = [
    "AmendmentChange", "AmendmentDraft", "ApplicabilityStatus", "ApprovalState",
    "EvidenceRequirement", "EvidenceState", "KnowledgeChunk", "RAGGroundingStatus",
    "RAGResponse", "RAGSource", "RegulatoryContext", "RegulatoryFinding",
    "RegulatoryModuleMetadata", "RegulatoryStatus", "RuleVersion",
]
