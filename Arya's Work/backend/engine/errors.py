"""
Error types for the generic rule engine.

A configuration/validation problem is never allowed to silently become a
PASS or FAIL. It is always raised (during validation, ahead of evaluation) or
surfaced as an explicit ``ComplianceStatus.ENGINE_ERROR`` result (during
evaluation of a single rule, so that one broken rule does not abort an entire
inspection).
"""

from __future__ import annotations

from typing import List, Optional


class RuleEngineError(Exception):
    """Base class for all engine errors."""


class RuleValidationError(RuleEngineError):
    """
    Raised when a rule (or a full ruleset) is structurally invalid.

    Carries every problem found, not just the first, so a rule author gets a
    complete report in one pass.
    """

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        message = "Rule validation failed:\n- " + "\n- ".join(self.problems)
        super().__init__(message)


class CircularDependencyError(RuleEngineError):
    """Raised when rule dependencies form a cycle."""

    def __init__(self, cycle: List[str]):
        self.cycle = list(cycle)
        super().__init__(
            "Circular rule dependency detected: " + " -> ".join(cycle)
        )


class RuleConfigurationError(RuleEngineError):
    """
    Raised (and, in evaluation, captured as a result rather than propagated)
    when a *specific* rule cannot be evaluated because of a data/config
    problem discovered at evaluation time (e.g. an unresolvable field
    reference, a malformed operator argument). This is distinct from FAIL:
    the rule itself is broken, not the product.
    """

    def __init__(self, rule_id: Optional[str], message: str):
        self.rule_id = rule_id
        super().__init__(f"[{rule_id}] {message}" if rule_id else message)
