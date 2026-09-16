"""
Generic, machine-readable rule schema (spec section 5).

Every field is optional except the handful needed to identify and evaluate a
rule at all (``rule_id``, ``requirements`` or a bare pass condition). Nothing
here mentions a regulation, product category, or module name -- those are
*values* a rule instance carries, never part of the schema shape.

A rule is intentionally NOT "one field check". It can:
  - gate its own relevance with ``applicability``
  - short-circuit to EXEMPTED via ``exemptions``
  - compute intermediate values via ``derived``
  - evaluate one or more ``requirements``, each with its own condition
  - depend on other rules' results via ``depends_on``
  - carry versioning / effective-date metadata for regulatory evolution

Implemented with plain stdlib dataclasses (not pydantic) so the engine core
has zero required third-party dependencies and can be embedded in, or unit
tested independently of, any host project -- including one (like this one)
that uses pydantic elsewhere for its own, unrelated API contracts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

_ALLOWED_SEVERITIES = {"critical", "major", "normal", "minor", "advisory"}


def _as_list_of(cls, items: Any) -> List[Any]:
    if not items:
        return []
    out = []
    for item in items:
        if isinstance(item, cls):
            out.append(item)
        elif isinstance(item, dict):
            out.append(cls.from_dict(item))
        else:
            raise TypeError(f"expected dict or {cls.__name__}, got {type(item)}")
    return out


@dataclass
class Requirement:
    id: Optional[str] = None
    description: Optional[str] = None
    condition: Optional[Dict[str, Any]] = None
    severity: Optional[str] = None
    evidence_required: List[str] = dc_field(default_factory=list)
    message_pass: Optional[str] = None
    message_fail: Optional[str] = None
    message_uncertain: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Requirement":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ExemptionSpec:
    condition: Dict[str, Any]
    id: Optional[str] = None
    description: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExemptionSpec":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    def model_dump(self) -> Dict[str, Any]:
        return {"id": self.id, "description": self.description, "condition": self.condition}


@dataclass
class DerivedSpec:
    name: str
    expr: Dict[str, Any]
    description: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DerivedSpec":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    def model_dump(self) -> Dict[str, Any]:
        return {"name": self.name, "expr": self.expr, "description": self.description}


@dataclass
class Rule:
    """A single compliance rule as structured data."""

    rule_id: str
    name: Optional[str] = None
    description: Optional[str] = None

    # Legal provenance
    legal_source: Optional[str] = None
    regulation: Optional[str] = None
    provision: Optional[str] = None
    source_document: Optional[str] = None
    source_page: Optional[str] = None

    # Versioning / regulatory evolution
    version: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    supersedes: Optional[str] = None
    verification_status: Optional[str] = None
    status: Optional[str] = None

    # Scope
    applies_to: Dict[str, Any] = dc_field(default_factory=dict)
    applicability: Optional[Dict[str, Any]] = None

    # Exemptions / derived calcs
    exemptions: List[ExemptionSpec] = dc_field(default_factory=list)
    derived: List[DerivedSpec] = dc_field(default_factory=list)

    # The actual compliance check(s)
    condition: Optional[Dict[str, Any]] = None
    requirements: List[Requirement] = dc_field(default_factory=list)

    evidence_required: List[str] = dc_field(default_factory=list)
    depends_on: List[str] = dc_field(default_factory=list)

    severity: str = "normal"
    priority: int = 0

    message_pass: Optional[str] = None
    message_fail: Optional[str] = None
    message_uncertain: Optional[str] = None
    message_not_applicable: Optional[str] = None
    message_exempt: Optional[str] = None

    #: any keys present in the source JSON not recognised above (kept, never
    #: silently dropped, so round-tripping/tooling can still see them)
    extra: Dict[str, Any] = dc_field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in _ALLOWED_SEVERITIES:
            raise ValueError(
                f"{self.rule_id}: severity must be one of {sorted(_ALLOWED_SEVERITIES)}, "
                f"got {self.severity!r}"
            )
        if not isinstance(self.priority, int):
            raise ValueError(f"{self.rule_id}: priority must be an integer")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rule":
        data = dict(data)
        known = {f.name for f in cls.__dataclass_fields__.values() if f.name != "extra"}
        kwargs = {k: v for k, v in data.items() if k in known}
        extra = {k: v for k, v in data.items() if k not in known}
        kwargs["exemptions"] = _as_list_of(ExemptionSpec, data.get("exemptions"))
        kwargs["derived"] = _as_list_of(DerivedSpec, data.get("derived"))
        kwargs["requirements"] = _as_list_of(Requirement, data.get("requirements"))
        kwargs["extra"] = extra
        return cls(**kwargs)


@dataclass
class RuleSet:
    """A named, versioned collection of rules -- one regulation/module's worth."""

    rules: List[Rule] = dc_field(default_factory=list)
    ruleset_id: Optional[str] = None
    ruleset_version: Optional[str] = None
    description: Optional[str] = None

    def by_id(self, rule_id: str) -> Optional[Rule]:
        for r in self.rules:
            if r.rule_id == rule_id:
                return r
        return None


def load_ruleset_from_dict(data: Dict[str, Any]) -> RuleSet:
    rules = [Rule.from_dict(r) for r in data.get("rules", [])]
    return RuleSet(
        rules=rules,
        ruleset_id=data.get("ruleset_id"),
        ruleset_version=data.get("ruleset_version"),
        description=data.get("description"),
    )


def load_ruleset(path: Union[str, Path]) -> RuleSet:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return load_ruleset_from_dict(data)


def merge_rulesets(*rulesets: RuleSet, ruleset_id: str = "merged",
                    ruleset_version: str = "merged") -> RuleSet:
    """
    Combine multiple rulesets (e.g. several regulations, or a base module
    plus a jurisdiction-specific overlay) into one for a single evaluation
    run. Duplicate rule_ids across inputs are a validation error (caught by
    ``validate.py`` before evaluation) -- this function does not silently
    de-duplicate.
    """
    all_rules: List[Rule] = []
    for rs in rulesets:
        all_rules.extend(rs.rules)
    return RuleSet(ruleset_id=ruleset_id, ruleset_version=ruleset_version, rules=all_rules)
