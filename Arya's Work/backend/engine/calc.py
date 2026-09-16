"""
Deterministic calculations (section 13: arithmetic, percentages, ratios,
thresholds, tolerances, derived values, unit conversions).

Like ``conditions.py``, calculation trees are plain dicts evaluated by a
fixed table of named operators -- never ``eval()``.  A rule's ``derived``
list runs before its ``applicability``/``requirements`` conditions and
writes results into ``evidence.context['computed'][name]`` (and returns a
CalcTrace for the audit trail), so a condition elsewhere in the same rule
(or a dependent rule) can reference ``computed.<name>``.

If any input to a calculation is missing, the calculation result is
``None`` with ``ok=False`` -- never a guessed/defaulted number.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional

from .errors import RuleConfigurationError
from .evidence import MISSING, Evidence
from . import units as unit_lib


@dataclass
class CalcTrace:
    name: str
    ok: bool
    value: Optional[float]
    unit: Optional[str] = None
    detail: str = ""
    expression: Optional[Dict[str, Any]] = None
    inputs: Dict[str, Any] = dc_field(default_factory=dict)
    normalized_values: Dict[str, Any] = dc_field(default_factory=dict)
    output: Optional[float] = None
    status: str = "OK"
    explanation: str = ""
    steps: List[Dict[str, Any]] = dc_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "value": self.value,
            "output": self.output if self.output is not None else self.value,
            "unit": self.unit,
            "status": self.status,
            "expression": self.expression,
            "inputs": self.inputs,
            "normalized_values": self.normalized_values,
            "explanation": self.explanation or self.detail,
            "detail": self.detail,
            "steps": self.steps,
        }


def _resolve_numeric(node: Dict[str, Any], evidence: Evidence):
    """Resolve one operand of a calc expression -> (value, unit) or (None, None)."""
    if "field" in node:
        path = node["field"]
        ev = evidence.get_evidence_value(path)
        if ev is not None:
            if not ev.is_present():
                return None, None
            try:
                return float(ev.value), ev.unit
            except (TypeError, ValueError):
                return None, None
        raw = evidence.resolve(path)
        if raw is MISSING or raw is None:
            return None, None
        try:
            return float(raw), node.get("unit")
        except (TypeError, ValueError):
            return None, None
    if "literal" in node:
        try:
            return float(node["literal"]), node.get("unit")
        except (TypeError, ValueError):
            return None, None
    if "op" in node:
        result = evaluate_calc_node(node, evidence)
        return result[0], result[1]
    return None, None


def evaluate_calc_node(node: Dict[str, Any], evidence: Evidence):
    """Returns (value_or_None, unit_or_None)."""
    op = node.get("op")
    unit_out = node.get("unit")

    if op in ("add", "sub", "mul", "div"):
        args = node.get("args", [])
        if len(args) != 2:
            raise RuleConfigurationError(None, f"'{op}' requires exactly 2 args")
        a_val, a_unit = _resolve_numeric(args[0], evidence)
        b_val, b_unit = _resolve_numeric(args[1], evidence)
        if a_val is None or b_val is None:
            return None, unit_out

        if op in ("add", "sub") and a_unit and b_unit:
            try:
                b_val = unit_lib.convert(b_val, b_unit, a_unit)
            except ValueError as exc:
                raise RuleConfigurationError(None, str(exc)) from exc
            unit_out = unit_out or a_unit

        if op == "add":
            return a_val + b_val, unit_out
        if op == "sub":
            return a_val - b_val, unit_out
        if op == "mul":
            return a_val * b_val, unit_out
        if op == "div":
            if b_val == 0:
                return None, unit_out
            return a_val / b_val, unit_out

    if op == "percent_diff":
        # (observed - expected) / expected * 100
        args = node.get("args", [])
        if len(args) != 2:
            raise RuleConfigurationError(None, "'percent_diff' requires exactly 2 args")
        observed, o_unit = _resolve_numeric(args[0], evidence)
        expected, e_unit = _resolve_numeric(args[1], evidence)
        if observed is None or expected is None or expected == 0:
            return None, "%"
        if o_unit and e_unit:
            try:
                observed = unit_lib.convert(observed, o_unit, e_unit)
            except ValueError as exc:
                raise RuleConfigurationError(None, str(exc)) from exc
        return (observed - expected) / expected * 100.0, "%"

    if op == "abs":
        args = node.get("args", [])
        val, u = _resolve_numeric(args[0], evidence)
        if val is None:
            return None, u
        return abs(val), u

    if op == "convert_unit":
        args = node.get("args", [])
        val, u = _resolve_numeric(args[0], evidence)
        target = node.get("to")
        if val is None:
            return None, target
        try:
            return unit_lib.convert(val, u or node.get("from"), target), target
        except ValueError as exc:
            raise RuleConfigurationError(None, str(exc)) from exc

    if op == "const":
        return _resolve_numeric(node, evidence)

    if op == "field":
        return _resolve_numeric(node, evidence)

    raise RuleConfigurationError(None, f"unknown calc operator '{op}'")


def _collect_calc_inputs(node: Any, evidence: Evidence, target: Dict[str, Any]) -> None:
    if not isinstance(node, dict):
        return
    if "field" in node:
        path = node["field"]
        target[path] = evidence.resolve(path)
    for arg in node.get("args", []):
        _collect_calc_inputs(arg, evidence, target)


def run_derived(derived_specs: List[Dict[str, Any]], evidence: Evidence,
                 rule_id: Optional[str] = None) -> List[CalcTrace]:
    """
    Execute a rule's ``derived`` list in order (each may reference an
    earlier one via ``computed.<name>``) and write results into
    ``evidence.context['computed']``.
    """
    traces: List[CalcTrace] = []
    computed = evidence.context.setdefault("computed", {})
    for spec in derived_specs:
        name = spec.get("name")
        if not name:
            raise RuleConfigurationError(rule_id, "derived entry missing 'name'")
        expr = spec.get("expr")
        inputs_collected: Dict[str, Any] = {}
        _collect_calc_inputs(expr, evidence, inputs_collected)
        try:
            value, unit = evaluate_calc_node(expr, evidence)
        except RuleConfigurationError as exc:
            exc.rule_id = exc.rule_id or rule_id
            raise
        computed[name] = value
        status = "OK" if value is not None else "UNCERTAIN"
        explanation = (
            f"Derived {name} = {value} {unit or ''}".strip()
            if value is not None
            else f"Derived {name} could not be computed: missing or insufficient inputs"
        )
        traces.append(CalcTrace(
            name=name, ok=value is not None, value=value, unit=unit,
            expression=expr, inputs=inputs_collected, normalized_values=inputs_collected,
            output=value, status=status, explanation=explanation,
            detail="computed" if value is not None else "inputs missing/insufficient",
        ))
    return traces
