"""
Safe, declarative condition language.

Conditions are plain JSON-serialisable dicts, e.g.:

    {"op": "and", "args": [
        {"op": "exists", "field": "mrp"},
        {"op": "gt", "field": "mrp.value", "value": 0}
    ]}

    {"op": "between", "field": "computed.numeral_height_mm",
     "min": 4, "max": null, "min_inclusive": true}

    {"op": "eq", "field": "declared.net_quantity.unit",
     "value_field": "package.net_quantity.unit"}     # cross-field comparison

No ``eval()``/``exec()`` or arbitrary code execution is ever used: every
operator is an explicit, named Python function in ``_OPERATORS`` below, and
unknown operators are rejected during validation (see ``validate.py``).

Three-valued (Kleene K3) logic is used throughout, because compliance
evaluation must distinguish "definitely false" from "cannot be determined
from available evidence":

    TRUE    - definitively true
    FALSE   - definitively false
    UNKNOWN - cannot be determined (missing/insufficiently-confident evidence)

    AND: FALSE dominates, then UNKNOWN, else TRUE
    OR:  TRUE dominates, then UNKNOWN, else FALSE
    NOT: TRUE<->FALSE, UNKNOWN stays UNKNOWN

This is what prevents "insufficient evidence" from ever silently becoming
"compliant" (or "non-compliant").
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .errors import RuleConfigurationError
from .evidence import MISSING, Evidence
from . import units as unit_lib


class Tri(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"

    def __bool__(self) -> bool:  # pragma: no cover - defensive; use is-compare
        raise TypeError(
            "Tri is three-valued; compare with is Tri.TRUE/.FALSE/.UNKNOWN"
        )


def tri_and(values: List[Tri]) -> Tri:
    if any(v is Tri.FALSE for v in values):
        return Tri.FALSE

    if any(v is Tri.UNKNOWN for v in values):
        return Tri.UNKNOWN

    return Tri.TRUE


def tri_or(values: List[Tri]) -> Tri:
    if any(v is Tri.TRUE for v in values):
        return Tri.TRUE

    if any(v is Tri.UNKNOWN for v in values):
        return Tri.UNKNOWN

    return Tri.FALSE


def tri_not(value: Tri) -> Tri:
    if value is Tri.UNKNOWN:
        return Tri.UNKNOWN

    return (
        Tri.FALSE
        if value is Tri.TRUE
        else Tri.TRUE
    )


@dataclass
class ConditionTrace:
    """One node of the condition-evaluation trace, for the audit trail."""

    op: str
    result: Tri
    detail: str = ""
    field: Optional[str] = None
    observed: Any = None
    expected: Any = None
    children: List["ConditionTrace"] = dc_field(default_factory=list)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Tri):
            return self.result == other

        if isinstance(other, ConditionTrace):
            return (
                self.op == other.op
                and self.result == other.result
                and self.field == other.field
                and self.observed == other.observed
                and self.expected == other.expected
                and self.children == other.children
            )

        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op": self.op,
            "result": self.result.value,
            "detail": self.detail,
            "field": self.field,
            "observed": _jsonable(self.observed),
            "expected": _jsonable(self.expected),
            "children": [
                c.to_dict()
                for c in self.children
            ],
        }


def _jsonable(value: Any) -> Any:
    if isinstance(
        value,
        (_dt.date, _dt.datetime),
    ):
        return value.isoformat()

    if value is MISSING:
        return None

    return value


MIN_CONFIDENCE_DEFAULT = 0.0


def _resolve_operand(
    node: Dict[str, Any],
    evidence: Evidence,
    low_conf: float,
):
    """
    Resolve the "observed" side of a leaf condition.

    Returns:
        (tri_presence, python_value, unit, trace_observed)

    tri_presence is Tri.UNKNOWN if the value is missing, below the
    confidence floor, or marked unusable, else Tri.TRUE (value usable).

    IMPORTANT:
    Explicitly absent evidence is treated as unavailable for value
    comparisons and therefore remains UNKNOWN here. The separate ``exists``
    operator handles explicit presence/absence deterministically.
    """

    if "field" in node:
        path = node["field"]
        min_conf = float(
            node.get(
                "min_confidence",
                low_conf,
            )
        )

        ev = evidence.get_evidence_value(path)

        if ev is not None:
            if hasattr(ev, "is_usable") and not ev.is_usable():
                return (
                    Tri.UNKNOWN,
                    None,
                    ev.unit,
                    ev.value,
                )

            if not ev.is_present():
                return (
                    Tri.UNKNOWN,
                    None,
                    ev.unit,
                    None,
                )

            if (
                ev.confidence is not None
                and ev.confidence < min_conf
            ):
                return (
                    Tri.UNKNOWN,
                    None,
                    ev.unit,
                    ev.value,
                )

            return (
                Tri.TRUE,
                ev.value,
                ev.unit,
                ev.value,
            )

        raw = evidence.resolve(path)

        if raw is MISSING or raw is None:
            return (
                Tri.UNKNOWN,
                None,
                None,
                None,
            )

        return (
            Tri.TRUE,
            raw,
            node.get("unit"),
            raw,
        )

    if "literal" in node:
        return (
            Tri.TRUE,
            node["literal"],
            node.get("unit"),
            node["literal"],
        )

    return (
        Tri.UNKNOWN,
        None,
        None,
        None,
    )


def _resolve_comparison_value(
    node: Dict[str, Any],
    evidence: Evidence,
    low_conf: float,
):
    """Resolve the "expected" side: a literal ``value``/``min``/``max``/etc,
    or a cross-field ``value_field``."""

    if "value_field" in node:
        return _resolve_operand(
            {
                "field": node["value_field"]
            },
            evidence,
            low_conf,
        )

    if "value" in node:
        return (
            Tri.TRUE,
            node["value"],
            node.get("value_unit"),
            node["value"],
        )

    return (
        Tri.UNKNOWN,
        None,
        None,
        None,
    )


def _coerce_numeric(value: Any) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_date(value: Any) -> Optional[_dt.date]:
    if isinstance(value, _dt.datetime):
        return value.date()

    if isinstance(value, _dt.date):
        return value

    if isinstance(value, str):
        for fmt in (
            "%Y-%m-%d",
            "%Y-%m",
            "%d/%m/%Y",
            "%m/%Y",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                parsed = _dt.datetime.strptime(
                    value,
                    fmt,
                )
                return parsed.date()
            except ValueError:
                continue

    return None


def _align_units(
    a_val: float,
    a_unit: Optional[str],
    b_val: float,
    b_unit: Optional[str],
) -> tuple[float, float]:
    """
    If both sides carry units, convert b into a's unit deterministically.

    Raises ValueError on an incompatible/unrecognised unit pair.
    If either side has no unit, values are compared as-is.
    """
    if a_unit and b_unit:
        normalized_a = unit_lib.normalize_unit_token(a_unit)
        normalized_b = unit_lib.normalize_unit_token(b_unit)

        if normalized_a != normalized_b:
            converted = unit_lib.convert(
                b_val,
                b_unit,
                a_unit,
            )

            if converted is None:
                raise ValueError(
                    f"cannot convert {b_val!r} {b_unit!r} "
                    f"to {a_unit!r}"
                )

            b_val = float(converted)

    return a_val, b_val
# ---------------------------------------------------------------------------
# Operators.
# ---------------------------------------------------------------------------

def _leaf(op_name: str):
    def wrap(fn: Callable[..., ConditionTrace]) -> Callable[..., ConditionTrace]:
        _OPERATORS[op_name] = fn
        return fn

    return wrap


_OPERATORS: Dict[str, Callable] = {}

def _op_exists(node, evidence, low_conf) -> ConditionTrace:
    path = node["field"]
    ev = evidence.get_evidence_value(path)

    if ev is not None:
        # Explicitly absent is a deterministic FALSE for exists().
        if not ev.is_present():
            return ConditionTrace(
                op="exists",
                result=Tri.FALSE,
                field=path,
                observed=False,
                detail="field is explicitly marked not present",
            )

        # Present but unusable means we know the field exists,
        # but cannot reliably use its value.
        if hasattr(ev, "is_usable") and not ev.is_usable():
            return ConditionTrace(
                op="exists",
                result=Tri.UNKNOWN,
                field=path,
                observed=ev.value,
                detail="field is present but marked unusable",
            )

        return ConditionTrace(
            op="exists",
            result=Tri.TRUE,
            field=path,
            observed=True,
            detail="field is present",
        )

    # No EvidenceValue exists.
    present = evidence.has(path)

    return ConditionTrace(
        op="exists",
        result=Tri.TRUE if present else Tri.FALSE,
        field=path,
        observed=present,
        detail=(
            "field is present"
            if present
            else "field is not present"
        ),
    )


_OPERATORS["exists"] = _op_exists

def _op_missing(
    node,
    evidence,
    low_conf,
) -> ConditionTrace:
    inner = _op_exists(
        node,
        evidence,
        low_conf,
    )

    if inner.result is Tri.UNKNOWN:
        result = Tri.UNKNOWN
    else:
        result = (
            Tri.FALSE
            if inner.result is Tri.TRUE
            else Tri.TRUE
        )

    return ConditionTrace(
        op="missing",
        result=result,
        field=node["field"],
        observed=inner.observed,
        detail=(
            "field is missing"
            if result is Tri.TRUE
            else "field is present"
        ),
    )


_OPERATORS["missing"] = _op_missing


def _op_null(
    node,
    evidence,
    low_conf,
) -> ConditionTrace:
    path = node["field"]

    raw = (
        evidence.resolve(path)
        if path not in evidence.fields
        else evidence.fields[path].value
    )

    is_null = (
        raw is None
        or raw is MISSING
    )

    return ConditionTrace(
        op="null",
        result=(
            Tri.TRUE
            if is_null
            else Tri.FALSE
        ),
        field=path,
        observed=raw,
    )


_OPERATORS["null"] = _op_null


def _op_not_null(
    node,
    evidence,
    low_conf,
) -> ConditionTrace:
    inner = _op_null(
        node,
        evidence,
        low_conf,
    )

    result = (
        Tri.FALSE
        if inner.result is Tri.TRUE
        else Tri.TRUE
    )

    return ConditionTrace(
        op="not_null",
        result=result,
        field=node["field"],
        observed=inner.observed,
    )


_OPERATORS["not_null"] = _op_not_null


def _numeric_compare(
    op_symbol: str,
    cmp: Callable[[float, float], bool],
):
    def _op(node, evidence, low_conf) -> ConditionTrace:
        presence, a_raw, a_unit, a_obs = _resolve_operand(
            node,
            evidence,
            low_conf,
        )

        exp_presence, b_raw, b_unit, b_obs = (
            _resolve_comparison_value(
                node,
                evidence,
                low_conf,
            )
        )

        if (
            presence is Tri.UNKNOWN
            or exp_presence is Tri.UNKNOWN
        ):
            return ConditionTrace(
                op=op_symbol,
                result=Tri.UNKNOWN,
                field=node.get("field"),
                observed=a_obs,
                expected=b_obs,
                detail="insufficient evidence for comparison",
            )

        a_num = _coerce_numeric(a_raw)
        b_num = _coerce_numeric(b_raw)

        if a_num is None:
            raise RuleConfigurationError(
                node.get("_rule_id"),
                f"{op_symbol}: non-numeric observed operand "
                f"({a_raw!r})",
            )

        if b_num is None:
            raise RuleConfigurationError(
                node.get("_rule_id"),
                f"{op_symbol}: non-numeric expected operand "
                f"({b_raw!r})",
            )

        try:
            a_num, b_num = _align_units(
                a_num,
                a_unit,
                b_num,
                b_unit,
            )
        except ValueError as exc:
            raise RuleConfigurationError(
                node.get("_rule_id"),
                str(exc),
            ) from exc

        result = (
            Tri.TRUE
            if cmp(a_num, b_num)
            else Tri.FALSE
        )

        return ConditionTrace(
            op=op_symbol,
            result=result,
            field=node.get("field"),
            observed=a_obs,
            expected=b_obs,
            detail=(
                f"{a_num} {op_symbol} {b_num} "
                f"-> {result.value}"
            ),
        )

    return _op

_OPERATORS["gt"] = _numeric_compare(
    "gt",
    lambda a, b: a > b,
)

_OPERATORS[">"] = _OPERATORS["gt"]

_OPERATORS["gte"] = _numeric_compare(
    "gte",
    lambda a, b: a >= b,
)

_OPERATORS[">="] = _OPERATORS["gte"]

_OPERATORS["lt"] = _numeric_compare(
    "lt",
    lambda a, b: a < b,
)

_OPERATORS["<"] = _OPERATORS["lt"]

_OPERATORS["lte"] = _numeric_compare(
    "lte",
    lambda a, b: a <= b,
)

_OPERATORS["<="] = _OPERATORS["lte"]


def _op_between(node, evidence, low_conf) -> ConditionTrace:
    presence, raw, a_unit, obs = _resolve_operand(
        node, evidence, low_conf
    )

    if presence is Tri.UNKNOWN:
        return ConditionTrace(
            op="between",
            result=Tri.UNKNOWN,
            field=node.get("field"),
            observed=obs,
            detail="insufficient evidence",
        )

    value = _coerce_numeric(raw)

    if value is None:
        raise RuleConfigurationError(
            node.get("_rule_id"),
            f"between: non-numeric value {raw!r}",
        )

    lo_raw = node.get("min")
    hi_raw = node.get("max")

    lo_inclusive = bool(node.get("min_inclusive", True))
    hi_inclusive = bool(node.get("max_inclusive", True))

    target_unit = node.get("unit")

    # Convert observed value to the rule unit.
    if target_unit and a_unit:
        try:
            normalized_a = unit_lib.normalize_unit_token(a_unit)
            normalized_target = unit_lib.normalize_unit_token(target_unit)

            if normalized_a != normalized_target:
                converted = unit_lib.convert(
                    value,
                    a_unit,
                    target_unit,
                )

                if converted is None:
                    raise RuleConfigurationError(
                        node.get("_rule_id"),
                        f"between: failed to convert "
                        f"{value!r} {a_unit!r} to {target_unit!r}",
                    )

                value = float(converted)

        except ValueError as exc:
            raise RuleConfigurationError(
                node.get("_rule_id"),
                str(exc),
            ) from exc

    lo: Optional[float] = None
    hi: Optional[float] = None

    if lo_raw is not None:
        lo = _coerce_numeric(lo_raw)

        if lo is None:
            raise RuleConfigurationError(
                node.get("_rule_id"),
                f"between: non-numeric minimum {lo_raw!r}",
            )

    if hi_raw is not None:
        hi = _coerce_numeric(hi_raw)

        if hi is None:
            raise RuleConfigurationError(
                node.get("_rule_id"),
                f"between: non-numeric maximum {hi_raw!r}",
            )

    if lo is not None:
        lower_ok = (
            value >= lo
            if lo_inclusive
            else value > lo
        )
    else:
        lower_ok = True

    if hi is not None:
        upper_ok = (
            value <= hi
            if hi_inclusive
            else value < hi
        )
    else:
        upper_ok = True

    ok = lower_ok and upper_ok

    return ConditionTrace(
        op="between",
        result=Tri.TRUE if ok else Tri.FALSE,
        field=node.get("field"),
        observed=value,
        expected=(lo, hi),
        detail=f"{value} in [{lo},{hi}] -> {ok}",
    )


_OPERATORS["between"] = _op_between

def _equality(
    op_symbol: str,
    expect_equal: bool,
):
    def _op(
        node,
        evidence,
        low_conf,
    ) -> ConditionTrace:
        presence, a_raw, a_unit, a_obs = _resolve_operand(
            node,
            evidence,
            low_conf,
        )

        exp_presence, b_raw, b_unit, b_obs = (
            _resolve_comparison_value(
                node,
                evidence,
                low_conf,
            )
        )

        if (
            presence is Tri.UNKNOWN
            or exp_presence is Tri.UNKNOWN
        ):
            return ConditionTrace(
                op=op_symbol,
                result=Tri.UNKNOWN,
                field=node.get("field"),
                observed=a_obs,
                expected=b_obs,
                detail="insufficient evidence",
            )

        a_num = _coerce_numeric(a_raw)
        b_num = _coerce_numeric(b_raw)

        if (
            a_num is not None
            and b_num is not None
        ):
            try:
                a_num, b_num = _align_units(
                    a_num,
                    a_unit,
                    b_num,
                    b_unit,
                )

            except ValueError as exc:
                raise RuleConfigurationError(
                    node.get("_rule_id"),
                    str(exc),
                ) from exc

            equal = (
                abs(a_num - b_num)
                <= node.get("tolerance", 0.0)
            )

        else:
            a_cmp = (
                str(a_raw).strip().lower()
                if not node.get("case_sensitive")
                else str(a_raw)
            )

            b_cmp = (
                str(b_raw).strip().lower()
                if not node.get("case_sensitive")
                else str(b_raw)
            )

            equal = a_cmp == b_cmp

        result = (
            Tri.TRUE
            if (equal == expect_equal)
            else Tri.FALSE
        )

        return ConditionTrace(
            op=op_symbol,
            result=result,
            field=node.get("field"),
            observed=a_obs,
            expected=b_obs,
        )

    return _op


_OPERATORS["eq"] = _equality(
    "eq",
    True,
)

_OPERATORS["=="] = _OPERATORS["eq"]
_OPERATORS["="] = _OPERATORS["eq"]

_OPERATORS["neq"] = _equality(
    "neq",
    False,
)

_OPERATORS["!="] = _OPERATORS["neq"]


def _text_predicate(
    op_symbol: str,
    fn: Callable[[str, str], bool],
):
    def _op(
        node,
        evidence,
        low_conf,
    ) -> ConditionTrace:
        presence, a_raw, _, a_obs = _resolve_operand(
            node,
            evidence,
            low_conf,
        )

        if presence is Tri.UNKNOWN:
            return ConditionTrace(
                op=op_symbol,
                result=Tri.UNKNOWN,
                field=node.get("field"),
                detail="insufficient evidence",
            )

        needle = node.get(
            "value",
            "",
        )

        haystack = str(a_raw)

        if not node.get("case_sensitive"):
            haystack = haystack.lower()
            needle = str(needle).lower()

        result = (
            Tri.TRUE
            if fn(haystack, needle)
            else Tri.FALSE
        )

        return ConditionTrace(
            op=op_symbol,
            result=result,
            field=node.get("field"),
            observed=a_obs,
            expected=node.get("value"),
        )

    return _op


_OPERATORS["contains"] = _text_predicate(
    "contains",
    lambda h, n: n in h,
)

_OPERATORS["not_contains"] = _text_predicate(
    "not_contains",
    lambda h, n: n not in h,
)

_OPERATORS["starts_with"] = _text_predicate(
    "starts_with",
    lambda h, n: h.startswith(n),
)

_OPERATORS["ends_with"] = _text_predicate(
    "ends_with",
    lambda h, n: h.endswith(n),
)


def _op_regex(
    node,
    evidence,
    low_conf,
) -> ConditionTrace:
    presence, a_raw, _, a_obs = _resolve_operand(
        node,
        evidence,
        low_conf,
    )

    if presence is Tri.UNKNOWN:
        return ConditionTrace(
            op="regex",
            result=Tri.UNKNOWN,
            field=node.get("field"),
            detail="insufficient evidence",
        )

    pattern = node.get(
        "pattern",
        "",
    )

    try:
        matched = (
            re.search(
                pattern,
                str(a_raw),
            )
            is not None
        )

    except re.error as exc:
        raise RuleConfigurationError(
            node.get("_rule_id"),
            f"invalid regex {pattern!r}: {exc}",
        ) from exc

    return ConditionTrace(
        op="regex",
        result=(
            Tri.TRUE
            if matched
            else Tri.FALSE
        ),
        field=node.get("field"),
        observed=a_obs,
        expected=pattern,
    )


_OPERATORS["regex"] = _op_regex


def _resolve_value_list(
    node: Dict[str, Any],
    evidence: Evidence,
):
    """
    Resolve the comparison list for in_list/not_in_list: either a literal
    ``values`` array, or a ``values_field`` reference to a list stored in
    evidence/context.
    """

    if "values_field" in node:
        raw = evidence.resolve(
            node["values_field"]
        )

        if raw is MISSING or raw is None:
            return Tri.UNKNOWN, []

        if not isinstance(
            raw,
            (list, tuple),
        ):
            raise RuleConfigurationError(
                node.get("_rule_id"),
                (
                    f"values_field "
                    f"'{node['values_field']}' "
                    "did not resolve to a list"
                ),
            )

        return Tri.TRUE, list(raw)

    values = (
        node.get("values")
        if "values" in node
        else node.get("value", [])
    )

    if not isinstance(
        values,
        (list, tuple, set),
    ):
        values = [values]

    return Tri.TRUE, list(values)


def _op_in_list(
    node,
    evidence,
    low_conf,
) -> ConditionTrace:
    presence, a_raw, _, a_obs = _resolve_operand(
        node,
        evidence,
        low_conf,
    )

    if presence is Tri.UNKNOWN:
        return ConditionTrace(
            op="in_list",
            result=Tri.UNKNOWN,
            field=node.get("field"),
            detail="insufficient evidence",
        )

    values_presence, values = _resolve_value_list(
        node,
        evidence,
    )

    if values_presence is Tri.UNKNOWN:
        return ConditionTrace(
            op="in_list",
            result=Tri.UNKNOWN,
            field=node.get("field"),
            detail="comparison list not available",
        )

    cmp_val = (
        str(a_raw).strip().lower()
        if not node.get("case_sensitive")
        else str(a_raw)
    )

    normalized = [
        (
            str(v).strip().lower()
            if not node.get("case_sensitive")
            else str(v)
        )
        for v in values
    ]

    result = (
        Tri.TRUE
        if cmp_val in normalized
        else Tri.FALSE
    )

    return ConditionTrace(
        op="in_list",
        result=result,
        field=node.get("field"),
        observed=a_obs,
        expected=values,
    )


_OPERATORS["in_list"] = _op_in_list
_OPERATORS["in"] = _op_in_list


def _op_not_in_list(
    node,
    evidence,
    low_conf,
) -> ConditionTrace:
    inner = _op_in_list(
        node,
        evidence,
        low_conf,
    )

    if inner.result is Tri.UNKNOWN:
        return ConditionTrace(
            op="not_in_list",
            result=Tri.UNKNOWN,
            field=node.get("field"),
        )

    result = (
        Tri.FALSE
        if inner.result is Tri.TRUE
        else Tri.TRUE
    )

    return ConditionTrace(
        op="not_in_list",
        result=result,
        field=node.get("field"),
        observed=inner.observed,
        expected=inner.expected,
    )


_OPERATORS["not_in_list"] = _op_not_in_list
_OPERATORS["not_in"] = _op_not_in_list


def _op_boolean(
    node,
    evidence,
    low_conf,
) -> ConditionTrace:
    presence, a_raw, _, a_obs = _resolve_operand(
        node,
        evidence,
        low_conf,
    )

    if presence is Tri.UNKNOWN:
        return ConditionTrace(
            op="boolean",
            result=Tri.UNKNOWN,
            field=node.get("field"),
        )

    expected = node.get(
        "value",
        True,
    )

    result = (
        Tri.TRUE
        if bool(a_raw) == bool(expected)
        else Tri.FALSE
    )

    return ConditionTrace(
        op="boolean",
        result=result,
        field=node.get("field"),
        observed=a_obs,
        expected=expected,
    )


_OPERATORS["boolean"] = _op_boolean


def _date_compare(
    op_symbol: str,
    cmp: Callable[[_dt.date, _dt.date], bool],
):
    def _op(
        node,
        evidence,
        low_conf,
    ) -> ConditionTrace:
        presence, a_raw, _, a_obs = _resolve_operand(
            node,
            evidence,
            low_conf,
        )

        exp_presence, b_raw, _, b_obs = (
            _resolve_comparison_value(
                node,
                evidence,
                low_conf,
            )
        )

        if (
            presence is Tri.UNKNOWN
            or exp_presence is Tri.UNKNOWN
        ):
            return ConditionTrace(
                op=op_symbol,
                result=Tri.UNKNOWN,
                field=node.get("field"),
                detail="insufficient evidence",
            )

        a_date = _coerce_date(a_raw)
        b_date = _coerce_date(b_raw)

        if (
            a_date is None
            or b_date is None
        ):
            raise RuleConfigurationError(
                node.get("_rule_id"),
                (
                    f"{op_symbol}: unparseable date "
                    f"({a_raw!r} / {b_raw!r})"
                ),
            )

        result = (
            Tri.TRUE
            if cmp(a_date, b_date)
            else Tri.FALSE
        )

        return ConditionTrace(
            op=op_symbol,
            result=result,
            field=node.get("field"),
            observed=a_obs,
            expected=b_obs,
        )

    return _op


_OPERATORS["date_before"] = _date_compare(
    "date_before",
    lambda a, b: a < b,
)

_OPERATORS["date_after"] = _date_compare(
    "date_after",
    lambda a, b: a > b,
)

_OPERATORS["date_on_or_before"] = _date_compare(
    "date_on_or_before",
    lambda a, b: a <= b,
)

_OPERATORS["date_on_or_after"] = _date_compare(
    "date_on_or_after",
    lambda a, b: a >= b,
)


def _op_always(
    node,
    evidence,
    low_conf,
) -> ConditionTrace:
    return ConditionTrace(
        op="always",
        result=Tri.TRUE,
        detail="unconditional",
    )


_OPERATORS["always"] = _op_always


def _op_never(
    node,
    evidence,
    low_conf,
) -> ConditionTrace:
    return ConditionTrace(
        op="never",
        result=Tri.FALSE,
        detail="unconditional",
    )


_OPERATORS["never"] = _op_never


# ---------------------------------------------------------------------------
# Boolean combinators.
# ---------------------------------------------------------------------------

def evaluate_condition(
    node: Optional[Dict[str, Any]],
    evidence: Evidence,
    low_conf: float = MIN_CONFIDENCE_DEFAULT,
    rule_id: Optional[str] = None,
) -> ConditionTrace:
    """
    Evaluate one condition node (leaf or combinator) against evidence.

    Returns a ConditionTrace whose result is a three-valued Tri.

    Raises RuleConfigurationError if the node is malformed.
    """

    if node is None:
        return ConditionTrace(
            op="always",
            result=Tri.TRUE,
            detail="no condition (always applicable)",
        )

    op = node.get("op")

    if op is None:
        raise RuleConfigurationError(
            rule_id,
            "condition node missing 'op'",
        )

    if op == "and":
        raw_args = node.get("args")

        if raw_args is None:
            raw_args = node.get("conditions", [])

        if not isinstance(raw_args, list):
            raise RuleConfigurationError(
                rule_id,
                "'and' requires a list in 'args' or 'conditions'",
            )

        children = [
            evaluate_condition(
                child,
                evidence,
                low_conf,
                rule_id,
            )
            for child in raw_args
        ]

        return ConditionTrace(
            op="and",
            result=tri_and(
                [child.result for child in children]
            ),
            children=children,
        )

    if op == "or":
        raw_args = node.get("args")

        if raw_args is None:
            raw_args = node.get("conditions", [])

        if not isinstance(raw_args, list):
            raise RuleConfigurationError(
                rule_id,
                "'or' requires a list in 'args' or 'conditions'",
            )

        children = [
            evaluate_condition(
                child,
                evidence,
                low_conf,
                rule_id,
            )
            for child in raw_args
        ]

        return ConditionTrace(
            op="or",
            result=tri_or(
                [child.result for child in children]
            ),
            children=children,
        )

    if op == "not":
        raw_args = node.get("args")

        if raw_args is None:
            if "condition" in node:
                raw_args = [node["condition"]]
            else:
                raw_args = []

        if not isinstance(raw_args, list):
            raise RuleConfigurationError(
                rule_id,
                "'not' requires a list in 'args'",
            )

        if len(raw_args) != 1:
            raise RuleConfigurationError(
                rule_id,
                "'not' requires exactly one argument",
            )

        child = evaluate_condition(
            raw_args[0],
            evidence,
            low_conf,
            rule_id,
        )

        return ConditionTrace(
            op="not",
            result=tri_not(child.result),
            children=[child],
        )

    fn = _OPERATORS.get(op)

    if fn is None:
        raise RuleConfigurationError(
            rule_id,
            f"unknown operator '{op}'",
        )

    tagged = dict(node)
    tagged["_rule_id"] = rule_id

    return fn(
        tagged,
        evidence,
        low_conf,
    )


KNOWN_OPERATORS = sorted(
    set(_OPERATORS.keys()) | {"and", "or", "not"}
)