"""
Generic, data-driven compliance rule engine.

This package is deliberately regulation-agnostic: it contains no reference to
"Legal Metrology", "LMPC", "MRP" or any other domain vocabulary. It knows how
to evaluate *rules* (data) against *evidence* (data) and produce an
explainable, auditable compliance result.

    LEGAL REQUIREMENTS
            |
    STRUCTURED RULE DATA        (engine.rule_model.Rule, loaded from JSON)
            |
    GENERIC RULE ENGINE         (this package)
            |
    EVIDENCE + PRODUCT DATA     (engine.evidence.Evidence)
            |
    DETERMINISTIC EVALUATION    (engine.evaluator.RuleEngine)
            |
    EXPLAINABLE COMPLIANCE RESULT (engine.results.RuleResult / EngineReport)

Adding a new regulation or a new product category never requires touching
this package's evaluation code -- only adding rule data (see
``rules/generic/``) and, where genuinely new physical measurements are
involved, an evidence provider that populates ``Evidence`` fields.

Public entry points:

    from engine import RuleEngine, load_ruleset
    ruleset = load_ruleset(Path("rules/generic/lmpc_rules.json"))
    report = RuleEngine(ruleset).evaluate(evidence, context)
"""

from .compliance_engine import ComplianceEngine, product_to_evidence
from .errors import (
    CircularDependencyError,
    RuleConfigurationError,
    RuleValidationError,
)
from .evidence import Evidence, EvidenceValue
from .evaluator import RuleEngine
from .product_facts import (
    CanonicalFact,
    CanonicalProductFacts,
    FactState,
    normalize_to_canonical_facts,
)
from .rule_model import Rule, RuleSet, load_ruleset, load_ruleset_from_dict
from .results import (
    ApplicabilityStatus,
    ComplianceStatus,
    EngineReport,
    RuleResult,
)

__all__ = [
    "ComplianceEngine",
    "product_to_evidence",
    "CanonicalProductFacts",
    "CanonicalFact",
    "FactState",
    "normalize_to_canonical_facts",
    "RuleEngine",
    "Rule",
    "RuleSet",
    "load_ruleset",
    "load_ruleset_from_dict",
    "Evidence",
    "EvidenceValue",
    "RuleResult",
    "EngineReport",
    "ApplicabilityStatus",
    "ComplianceStatus",
    "RuleConfigurationError",
    "RuleValidationError",
    "CircularDependencyError",
]
