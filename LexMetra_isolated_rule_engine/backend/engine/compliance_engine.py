"""Stable facade for the isolated LexMetra-compatible rule engine.

This module adds a small product-input boundary around the existing generic
``RuleEngine``.  It deliberately does not know about OCR, CV, FastAPI, or UI.
The underlying RuleEngine and rule/evidence contracts remain available for
backward compatibility.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from .evidence import Evidence
from .evaluator import RuleEngine
from .rule_model import RuleSet, load_ruleset
from .results import EngineReport

DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parents[2] / "rules" / "generic" / "lmpc_rules.json"
)


def _flatten_scalars(value: Any, prefix: str = ""):
    """Yield dot-path scalar/list/object leaves without inventing facts."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_scalars(child, path)
    elif isinstance(value, list):
        # Keep lists intact as context; scalar indexed paths are also useful.
        if prefix:
            yield prefix, value
        for i, child in enumerate(value):
            yield from _flatten_scalars(child, f"{prefix}[{i}]")
    else:
        yield prefix, value


from .product_facts import CanonicalProductFacts, normalize_to_canonical_facts


def product_to_evidence(product_input: Union[Evidence, Mapping[str, Any], CanonicalProductFacts]) -> Evidence:
    """Convert a product mapping or CanonicalProductFacts to the generic Evidence contract.

    If an Evidence object is supplied it is returned unchanged. For mappings or
    CanonicalProductFacts, the single canonical normalization layer resolves KNOWN,
    EXPLICITLY_ABSENT, and UNKNOWN presence states without fabricating facts.
    """
    if isinstance(product_input, Evidence):
        return product_input
    return normalize_to_canonical_facts(product_input).to_evidence()


class ComplianceEngine:
    """Stable high-level entry point built on the current RuleEngine."""

    def __init__(
        self,
        ruleset: Optional[RuleSet] = None,
        *,
        rules_path: Optional[Union[str, Path]] = None,
        low_confidence_threshold: float = 0.55,
        validate_on_init: bool = True,
    ) -> None:
        if ruleset is not None and rules_path is not None:
            raise ValueError("provide either ruleset or rules_path, not both")
        if ruleset is None:
            ruleset = load_ruleset(Path(rules_path) if rules_path else DEFAULT_RULES_PATH)
        self.ruleset = ruleset
        self._engine = RuleEngine(
            ruleset,
            low_confidence_threshold=low_confidence_threshold,
            validate_on_init=validate_on_init,
        )

    def evaluate(
        self,
        product_input: Union[Evidence, Mapping[str, Any]],
        *,
        assessment_date: Optional[Union[str, date, datetime]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> EngineReport:
        evidence = product_to_evidence(product_input)
        evaluation_context = dict(context or {})
        if assessment_date is not None:
            evaluation_context["assessment_date"] = (
                assessment_date.isoformat() if hasattr(assessment_date, "isoformat") else str(assessment_date)
            )
        return self._engine.evaluate(evidence, evaluation_context)

    @property
    def rule_engine(self) -> RuleEngine:
        """Expose the underlying compatible engine for advanced callers."""
        return self._engine
