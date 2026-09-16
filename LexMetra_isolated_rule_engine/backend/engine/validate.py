"""
Rule validation, run BEFORE any evaluation (section 22).

An invalid rule must never silently execute. ``validate_ruleset`` collects
every problem it can find (not just the first) and raises
``RuleValidationError`` if there are any. Callers that want a report instead
of an exception can call ``find_problems`` directly.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Set

from .conditions import KNOWN_OPERATORS
from .errors import RuleValidationError
from .rule_model import Rule, RuleSet

_COMBINATORS = {"and", "or", "not"}


def _validate_condition_tree(node: Any, path: str, problems: List[str]) -> None:
    if node is None:
        return
    if not isinstance(node, dict):
        problems.append(f"{path}: condition must be an object, got {type(node).__name__}")
        return
    op = node.get("op")
    if op is None:
        problems.append(f"{path}: condition missing 'op'")
        return
    if op in _COMBINATORS:
        args = node.get("args")
        if not isinstance(args, list) or (op != "not" and len(args) < 1) or (op == "not" and len(args) != 1):
            problems.append(f"{path}: '{op}' requires a non-empty 'args' list "
                             f"({'exactly 1' if op == 'not' else 'at least 1'})")
            return
        for i, child in enumerate(args):
            _validate_condition_tree(child, f"{path}.args[{i}]", problems)
        return
    if op not in KNOWN_OPERATORS:
        problems.append(f"{path}: unsupported operator '{op}'. Known operators: {KNOWN_OPERATORS}")
        return
    if op not in ("always", "never") and "field" not in node and "literal" not in node:
        problems.append(f"{path}: operator '{op}' requires a 'field' (or 'literal')")
    if op == "regex":
        pattern = node.get("pattern")
        if not isinstance(pattern, str):
            problems.append(f"{path}: 'regex' requires a string 'pattern'")
        else:
            import re
            try:
                re.compile(pattern)
            except re.error as exc:
                problems.append(f"{path}: invalid regex pattern {pattern!r}: {exc}")
    if op == "between":
        if node.get("min") is None and node.get("max") is None:
            problems.append(f"{path}: 'between' requires at least one of 'min'/'max'")


def _validate_dates(rule: Rule, problems: List[str]) -> None:
    def _parse(val, label):
        if val is None:
            return None
        try:
            return _dt.date.fromisoformat(str(val)[:10])
        except ValueError:
            problems.append(f"{rule.rule_id}: invalid {label} date {val!r} (expected YYYY-MM-DD)")
            return None

    ef = _parse(rule.effective_from, "effective_from")
    et = _parse(rule.effective_to, "effective_to")
    if ef and et and ef > et:
        problems.append(f"{rule.rule_id}: effective_from ({rule.effective_from}) is after "
                         f"effective_to ({rule.effective_to})")


def find_problems(ruleset: RuleSet) -> List[str]:
    problems: List[str] = []

    seen_ids: Set[str] = set()
    for rule in ruleset.rules:
        if not rule.rule_id or not rule.rule_id.strip():
            problems.append("a rule has an empty rule_id")
            continue
        if rule.rule_id in seen_ids:
            problems.append(f"duplicate rule_id: {rule.rule_id}")
        seen_ids.add(rule.rule_id)

    known_ids = seen_ids

    for rule in ruleset.rules:
        rid = rule.rule_id or "<unknown>"

        _non_exec_types = {
            "administrative", "definitions", "repeal_savings", "repeal_savings_provisions",
            "penalties_procedural_provisions", "procedural", "informational",
            "inspection_sampling_provisions", "registration_obligations"
        }
        if (
            not rule.requirements
            and rule.condition is None
            and getattr(rule, "rule_type", "") not in _non_exec_types
            and getattr(rule, "status", "") not in ("not_executable", "informational")
        ):
            problems.append(f"{rid}: must have either a top-level 'condition' or at least one requirement")

        _validate_condition_tree(rule.applicability, f"{rid}.applicability", problems)
        _validate_condition_tree(rule.condition, f"{rid}.condition", problems)
        for i, req in enumerate(rule.requirements):
            if req.condition is None:
                problems.append(f"{rid}.requirements[{i}]: missing 'condition'")
            else:
                _validate_condition_tree(req.condition, f"{rid}.requirements[{i}].condition", problems)
        for i, exemption in enumerate(rule.exemptions):
            _validate_condition_tree(exemption.condition, f"{rid}.exemptions[{i}].condition", problems)

        for i, derived in enumerate(rule.derived):
            if not derived.name:
                problems.append(f"{rid}.derived[{i}]: missing 'name'")
            if not derived.expr or "op" not in derived.expr:
                problems.append(f"{rid}.derived[{i}]: 'expr' must be an object with 'op'")

        for dep in rule.depends_on:
            if dep not in known_ids:
                problems.append(f"{rid}: depends_on references unknown rule_id '{dep}'")
            if dep == rid:
                problems.append(f"{rid}: cannot depend on itself")

        if rule.priority is not None and not isinstance(rule.priority, int):
            problems.append(f"{rid}: priority must be an integer")

        _validate_dates(rule, problems)

    # Circular dependency detection (report as a validation problem too, in
    # addition to the harder failure raised by dependency.topological_order).
    from .dependency import find_cycle
    cycle = find_cycle(ruleset)
    if cycle:
        problems.append(f"circular dependency: {' -> '.join(cycle)}")

    return problems


def validate_ruleset(ruleset: RuleSet) -> None:
    problems = find_problems(ruleset)
    if problems:
        raise RuleValidationError(problems)
