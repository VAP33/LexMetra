"""
Result types produced by the generic rule engine.

Applicability and compliance are DISTINCT axes (section 7/9): a rule can be
APPLICABLE and still PASS/FAIL/UNCERTAIN; a rule that is NOT_APPLICABLE or
EXEMPTED never proceeds to a compliance verdict at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any, Dict, List, Optional


class ApplicabilityStatus(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXEMPTED = "EXEMPTED"
    UNCERTAIN = "UNCERTAIN"


class ComplianceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXEMPTED = "EXEMPTED"
    ENGINE_ERROR = "ENGINE_ERROR"  # rule/config problem, never a legal verdict
    NOT_CONSIDERED = "NOT_CONSIDERED"  # defined in regulatory data but not implemented or outside scope


@dataclass
class EvidenceCitation:
    field: Optional[str] = None
    observed_value: Any = None
    normalized_value: Any = None
    confidence: Optional[float] = None
    source_text: Optional[str] = None
    source_page: Optional[str] = None
    provenance: Optional[str] = None
    image_id: Optional[str] = None
    bbox: Optional[Any] = None
    verification_status: Optional[str] = None
    usable: Optional[bool] = None
    quality_state: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field, "observed_value": _safe(self.observed_value),
            "normalized_value": _safe(self.normalized_value), "confidence": self.confidence,
            "source_text": self.source_text, "source_page": self.source_page,
            "provenance": self.provenance, "image_id": self.image_id,
            "bbox": self.bbox, "verification_status": self.verification_status,
            "usable": self.usable, "quality_state": self.quality_state,
        }


def _safe(v: Any) -> Any:
    try:
        import datetime as _dt
        if isinstance(v, (_dt.date, _dt.datetime)):
            return v.isoformat()
    except Exception:
        pass
    return v


@dataclass
class RequirementResult:
    requirement_id: Optional[str]
    description: Optional[str]
    status: ComplianceStatus
    reason: str
    evidence: List[EvidenceCitation] = dc_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "description": self.description,
            "status": self.status.value,
            "reason": self.reason,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass
class RuleResult:
    """The complete, explainable outcome of evaluating one rule."""

    rule_id: str
    rule_version: Optional[str]
    name: Optional[str]

    applicability: ApplicabilityStatus
    applicability_reason: str

    status: ComplianceStatus
    reason: str

    severity: str = "normal"
    priority: int = 0

    requirement_results: List[RequirementResult] = dc_field(default_factory=list)
    evidence: List[EvidenceCitation] = dc_field(default_factory=list)
    missing_evidence: List[str] = dc_field(default_factory=list)
    calculations: List[Dict[str, Any]] = dc_field(default_factory=list)
    dependencies: List[str] = dc_field(default_factory=list)
    cross_references: List[str] = dc_field(default_factory=list)
    rule_type: str = "requirement"

    legal_source: Optional[str] = None
    provision: Optional[str] = None

    confidence: Optional[float] = None
    explanation: str = ""
    review_required: bool = False
    trace: Dict[str, Any] = dc_field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id, "rule_version": self.rule_version, "name": self.name,
            "applicability": self.applicability.value, "applicability_reason": self.applicability_reason,
            "status": self.status.value, "reason": self.reason,
            "severity": self.severity, "priority": self.priority,
            "requirement_results": [r.to_dict() for r in self.requirement_results],
            "evidence": [e.to_dict() for e in self.evidence],
            "missing_evidence": self.missing_evidence,
            "calculations": self.calculations,
            "dependencies": self.dependencies,
            "cross_references": self.cross_references,
            "rule_type": self.rule_type,
            "legal_source": self.legal_source, "provision": self.provision,
            "confidence": self.confidence, "explanation": self.explanation,
            "review_required": self.review_required,
            "trace": self.trace, "error": self.error,
        }


@dataclass
class AggregationExplanation:
    overall_status: ComplianceStatus
    reason: str
    counts: Dict[str, int] = dc_field(default_factory=dict)
    critical_failures: List[str] = dc_field(default_factory=list)
    policy: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status.value, "reason": self.reason,
            "counts": self.counts, "critical_failures": self.critical_failures,
            "policy": self.policy,
        }


@dataclass
class ComplianceDecisionPackage:
    """Canonical top-level compliance decision package (spec section 16)."""

    inspection_id: str
    legal_basis: Dict[str, Any]
    overall_result: str
    summary: Dict[str, int]
    rules: List[Dict[str, Any]]
    rules_not_considered: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    calculations: List[Dict[str, Any]]
    dependencies: List[str]
    audit: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inspection_id": self.inspection_id,
            "legal_basis": self.legal_basis,
            "overall_result": self.overall_result,
            "summary": self.summary,
            "rules": self.rules,
            "rules_not_considered": self.rules_not_considered,
            "evidence": self.evidence,
            "calculations": self.calculations,
            "dependencies": self.dependencies,
            "audit": self.audit,
        }

    def as_dict(self) -> Dict[str, Any]:
        return self.to_dict()


@dataclass
class EngineReport:
    """Everything produced by one full evaluation run."""

    results: List[RuleResult]
    aggregation: AggregationExplanation
    dependency_order: List[str] = dc_field(default_factory=list)
    ruleset_id: Optional[str] = None
    ruleset_version: Optional[str] = None
    decision_package: Optional[ComplianceDecisionPackage] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ruleset_id": self.ruleset_id, "ruleset_version": self.ruleset_version,
            "dependency_order": self.dependency_order,
            "results": [r.to_dict() for r in self.results],
            "aggregation": self.aggregation.to_dict(),
            "decision_package": self.decision_package.to_dict() if self.decision_package else None,
        }

    def by_id(self, rule_id: str) -> Optional[RuleResult]:
        for r in self.results:
            if r.rule_id == rule_id:
                return r
        return None
