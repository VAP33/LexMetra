"""
Deterministic, explicit unit normalization.

Only conversions between units of the SAME physical dimension are ever
performed. Mass is never converted to volume, currency is never converted
between currencies, and an unrecognised unit never silently falls through to
"assume it's the same". Ambiguity here becomes ``UNCERTAIN`` /
``RuleConfigurationError`` in the caller, never a guess.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# dimension -> {unit: multiplier to the dimension's base unit}
_DIMENSIONS: Dict[str, Dict[str, float]] = {
    "mass": {
        "mg": 0.001,
        "g": 1.0,
        "gram": 1.0,
        "grams": 1.0,
        "gm": 1.0,
        "gms": 1.0,
        "kg": 1000.0,
        "kilogram": 1000.0,
        "kilograms": 1000.0,
        "kgs": 1000.0,
        "lb": 453.59237,
        "lbs": 453.59237,
        "oz": 28.349523125,
    },
    "volume": {
        "ml": 1.0,
        "millilitre": 1.0,
        "millilitres": 1.0,
        "milliliter": 1.0,
        "milliliters": 1.0,
        "cl": 10.0,
        "l": 1000.0,
        "litre": 1000.0,
        "litres": 1000.0,
        "liter": 1000.0,
        "liters": 1000.0,
        "fl_oz": 29.5735295625,
        "gal": 3785.411784,
    },
    "length": {
        "mm": 1.0,
        "cm": 10.0,
        "m": 1000.0,
        "in": 25.4,
        "inch": 25.4,
        "inches": 25.4,
        "ft": 304.8,
    },
    "count": {
        "number": 1.0,
        "unit": 1.0,
        "units": 1.0,
        "piece": 1.0,
        "pieces": 1.0,
        "pcs": 1.0,
        "nos": 1.0,
        "count": 1.0,
    },
    "time": {
        "s": 1.0,
        "sec": 1.0,
        "second": 1.0,
        "seconds": 1.0,
        "min": 60.0,
        "minute": 60.0,
        "minutes": 60.0,
        "h": 3600.0,
        "hour": 3600.0,
        "hours": 3600.0,
        "day": 86400.0,
        "days": 86400.0,
    },
    "ratio": {
        "%": 0.01,
        "percent": 0.01,
        "fraction": 1.0,
        "ratio": 1.0,
    },
}

_UNIT_TO_DIMENSION: Dict[str, str] = {}
for _dim, _units in _DIMENSIONS.items():
    for _u in _units:
        _UNIT_TO_DIMENSION[_u] = _dim


def normalize_unit_token(unit: Optional[str]) -> Optional[str]:
    if unit is None:
        return None
    return str(unit).strip().lower().replace("-", "_")


def dimension_of(unit: Optional[str]) -> Optional[str]:
    token = normalize_unit_token(unit)
    if token is None:
        return None
    return _UNIT_TO_DIMENSION.get(token)


def are_compatible(unit_a: Optional[str], unit_b: Optional[str]) -> bool:
    da, db = dimension_of(unit_a), dimension_of(unit_b)
    return da is not None and da == db


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """
    Convert ``value`` from ``from_unit`` to ``to_unit``.

    Raises ValueError if the units are not registered or not dimensionally
    compatible. Callers in the evaluator translate that into an explicit
    RuleConfigurationError / UNCERTAIN result rather than letting an
    exception escape to the user as a stack trace.
    """
    fu, tu = normalize_unit_token(from_unit), normalize_unit_token(to_unit)
    da, db = dimension_of(fu), dimension_of(tu)
    if da is None:
        raise ValueError(f"Unknown unit: {from_unit!r}")
    if db is None:
        raise ValueError(f"Unknown unit: {to_unit!r}")
    if da != db:
        raise ValueError(
            f"Cannot convert between incompatible dimensions: "
            f"{from_unit!r} ({da}) -> {to_unit!r} ({db})"
        )
    base = value * _DIMENSIONS[da][fu]
    return base / _DIMENSIONS[db][tu]


def to_base(value: float, unit: str) -> Tuple[float, str]:
    """Convert to the dimension's base unit, returning (value, dimension)."""
    dim = dimension_of(unit)
    if dim is None:
        raise ValueError(f"Unknown unit: {unit!r}")
    token = normalize_unit_token(unit)
    return value * _DIMENSIONS[dim][token], dim


def register_unit(dimension: str, unit: str, multiplier_to_base: float) -> None:
    """
    Allow a new regulation's rule data (or an adapter) to register a unit the
    core engine doesn't ship with, without modifying engine code.
    """
    token = normalize_unit_token(unit)
    _DIMENSIONS.setdefault(dimension, {})[token] = multiplier_to_base
    _UNIT_TO_DIMENSION[token] = dimension
