"""
Deterministic unit-sale-price calculator.

No ML, OCR or LLM logic belongs here.

The calculator implements the unit-price forms introduced in Rule 6(11):
- weight: per g below 1 kg, per kg at/above 1 kg
- length: per cm below 1 m, per m at/above 1 m
- volume: per ml below 1 litre, per litre at/above 1 litre
- number: per number/unit

All legal policy is kept explicit and versioned at the rule-data layer. This
module performs arithmetic only.

Important:
- Do not convert mass <-> volume without supplied density. This module never
  assumes that 1 litre == 1 kg.
- The "retail price equals unit sale price" exception is handled by comparing
  the package quantity with exactly one applicable standard unit.
- Monetary values use Decimal, not binary floating-point arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, Optional, Tuple


MONEY_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class UnitDefinition:
    family: str
    standard_label: str
    standard_quantity: Decimal
    input_to_standard_factor: Decimal


@dataclass(frozen=True)
class UnitPriceResult:
    unit_sale_price: Optional[Decimal]
    standard_unit_label: Optional[str]
    declaration_required: bool
    reason: str
    quantity_family: Optional[str] = None
    normalized_quantity: Optional[Decimal] = None


# These are unit-conversion facts, not legal thresholds.
#
# The legal boundary between the smaller and larger standard unit is one
# standard unit, and the Rule 6(11) representation is:
#   <1 kg  -> per g
#   >=1 kg -> per kg
#   <1 m   -> per cm
#   >=1 m  -> per metre
#   <1 L   -> per ml
#   >=1 L  -> per litre
#
# "number" is represented as per number/unit.
_UNIT_ALIASES: Dict[str, str] = {
    "g": "g",
    "gram": "g",
    "grams": "g",
    "gm": "g",
    "gms": "g",

    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "kgs": "kg",

    "ml": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "milliliter": "ml",
    "milliliters": "ml",

    "l": "l",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",

    "cm": "cm",
    "centimeter": "cm",
    "centimeters": "cm",
    "centimetre": "cm",
    "centimetres": "cm",

    "m": "m",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",

    "number": "number",
    "numbers": "number",
    "no": "number",
    "nos": "number",
    "piece": "number",
    "pieces": "number",
    "pc": "number",
    "pcs": "number",
    "unit": "number",
    "units": "number",

    # Common count-based package declarations.
    "capsule": "number",
    "capsules": "number",
    "tablet": "number",
    "tablets": "number",
}


def _canonical_unit(unit: str) -> Optional[str]:
    if unit is None:
        return None
    normalized = " ".join(str(unit).strip().lower().split())
    return _UNIT_ALIASES.get(normalized)


def _decimal(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {name}: {value!r}") from exc

    if not result.is_finite():
        raise ValueError(f"Invalid {name}: must be finite")
    return result


def _unit_definition(unit: str) -> Optional[UnitDefinition]:
    canonical = _canonical_unit(unit)
    if canonical is None:
        return None

    definitions = {
        "g": UnitDefinition(
            family="weight",
            standard_label="kg",
            standard_quantity=Decimal("1"),
            input_to_standard_factor=Decimal("0.001"),
        ),
        "kg": UnitDefinition(
            family="weight",
            standard_label="kg",
            standard_quantity=Decimal("1"),
            input_to_standard_factor=Decimal("1"),
        ),
        "ml": UnitDefinition(
            family="volume",
            standard_label="litre",
            standard_quantity=Decimal("1"),
            input_to_standard_factor=Decimal("0.001"),
        ),
        "l": UnitDefinition(
            family="volume",
            standard_label="litre",
            standard_quantity=Decimal("1"),
            input_to_standard_factor=Decimal("1"),
        ),
        "cm": UnitDefinition(
            family="length",
            standard_label="metre",
            standard_quantity=Decimal("1"),
            input_to_standard_factor=Decimal("0.01"),
        ),
        "m": UnitDefinition(
            family="length",
            standard_label="metre",
            standard_quantity=Decimal("1"),
            input_to_standard_factor=Decimal("1"),
        ),
        "number": UnitDefinition(
            family="number",
            standard_label="number",
            standard_quantity=Decimal("1"),
            input_to_standard_factor=Decimal("1"),
        ),
    }

    return definitions[canonical]


def _normalize_quantity(
    value: Decimal,
    definition: UnitDefinition,
) -> Decimal:
    """Return quantity in the family base unit: kg, litre, metre or number."""
    return value * definition.input_to_standard_factor


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _selected_sale_unit(
    quantity_in_base_unit: Decimal,
    family: str,
) -> Tuple[str, Decimal]:
    """
    Select the Rule 6(11) declaration unit.

    Returns:
        (display label, number of selected units contained in the package)

    Example:
        0.016 kg -> ("g", 16)
        1.25 kg  -> ("kg", 1.25)
    """
    if family == "weight":
        if quantity_in_base_unit < Decimal("1"):
            return "g", quantity_in_base_unit * Decimal("1000")
        return "kg", quantity_in_base_unit

    if family == "volume":
        if quantity_in_base_unit < Decimal("1"):
            return "ml", quantity_in_base_unit * Decimal("1000")
        return "litre", quantity_in_base_unit

    if family == "length":
        if quantity_in_base_unit < Decimal("1"):
            return "cm", quantity_in_base_unit * Decimal("100")
        return "metre", quantity_in_base_unit

    if family == "number":
        return "number", quantity_in_base_unit

    raise ValueError(f"Unsupported quantity family: {family}")


def _standard_unit_quantity_in_input_units(
    definition: UnitDefinition,
) -> Decimal:
    """
    Quantity corresponding to one kg/litre/metre/number in the caller's
    original unit.

    Used only for the single-standard-unit exception.
    """
    return Decimal("1") / definition.input_to_standard_factor


def convert_declared_price_to_standard(
    declared_value: float | Decimal,
    declared_unit: str,
) -> Optional[Decimal]:
    """
    Convert a declared unit price into the canonical comparable unit for its
    quantity family.

    Examples:
        2.50 per g     -> 2500.00 per kg
        0.50 per ml    -> 500.00 per litre
        12.00 per cm   -> 1200.00 per metre
        15.67 per piece -> 15.67 per number

    Returns None for unknown units. Never guess.
    """
    definition = _unit_definition(declared_unit)
    if definition is None:
        return None

    value = _decimal(declared_value, "declared unit price")
    if value < 0:
        return None

    canonical = _canonical_unit(declared_unit)

    # For comparison we always convert to the larger standard unit for
    # weight/volume/length, while count remains per number.
    if definition.family == "weight":
        factor = Decimal("1000") if canonical == "g" else Decimal("1")
    elif definition.family == "volume":
        factor = Decimal("1000") if canonical == "ml" else Decimal("1")
    elif definition.family == "length":
        factor = Decimal("100") if canonical == "cm" else Decimal("1")
    else:
        factor = Decimal("1")

    return _money(value * factor)


def compute_unit_sale_price(
    net_quantity_value: float | Decimal,
    net_quantity_unit: str,
    mrp: float | Decimal,
) -> UnitPriceResult:
    """
    Compute the Rule 6(11) unit sale price.

    The returned `unit_sale_price` is already rounded to two decimal places.

    `declaration_required=False` is used only for the explicit exception where
    the retail sale price equals the unit sale price because the package
    contains exactly one applicable standard unit.
    """
    definition = _unit_definition(net_quantity_unit)

    if definition is None:
        return UnitPriceResult(
            unit_sale_price=None,
            standard_unit_label=None,
            declaration_required=True,
            reason=(
                f"Unrecognized quantity unit '{net_quantity_unit}'. "
                "No unit conversion or legal conclusion was guessed."
            ),
        )

    try:
        quantity = _decimal(net_quantity_value, "net quantity")
        price = _decimal(mrp, "MRP")
    except ValueError as exc:
        return UnitPriceResult(
            unit_sale_price=None,
            standard_unit_label=definition.standard_label,
            declaration_required=True,
            reason=str(exc),
            quantity_family=definition.family,
        )

    if quantity <= 0:
        return UnitPriceResult(
            unit_sale_price=None,
            standard_unit_label=definition.standard_label,
            declaration_required=True,
            reason="Net quantity must be greater than zero.",
            quantity_family=definition.family,
        )

    if price < 0:
        return UnitPriceResult(
            unit_sale_price=None,
            standard_unit_label=definition.standard_label,
            declaration_required=True,
            reason="MRP cannot be negative.",
            quantity_family=definition.family,
        )

    normalized_quantity = _normalize_quantity(quantity, definition)

    # Rule 6(11) chooses the declaration unit based on the quantity threshold.
    display_unit, quantity_in_display_units = _selected_sale_unit(
        normalized_quantity,
        definition.family,
    )

    if quantity_in_display_units <= 0:
        return UnitPriceResult(
            unit_sale_price=None,
            standard_unit_label=display_unit,
            declaration_required=True,
            reason="Normalized quantity is not positive.",
            quantity_family=definition.family,
            normalized_quantity=normalized_quantity,
        )

    unit_price = _money(price / quantity_in_display_units)

    # One standard unit means:
    #   1 kg, 1 litre, 1 metre, or 1 number.
    #
    # This is the narrow arithmetic condition under which retail price and unit
    # sale price are the same by construction. It is not a blanket exemption
    # for arbitrary package sizes.
    standard_quantity_in_input_units = _standard_unit_quantity_in_input_units(
        definition
    )

    is_single_standard_unit = quantity == standard_quantity_in_input_units

    if is_single_standard_unit:
        return UnitPriceResult(
            unit_sale_price=unit_price,
            standard_unit_label=display_unit,
            declaration_required=False,
            reason=(
                "The package contains exactly one applicable standard unit, "
                "so retail sale price equals unit sale price; a separate unit "
                "sale price declaration is not obligatory under the applicable "
                "Rule 6(11) exception."
            ),
            quantity_family=definition.family,
            normalized_quantity=normalized_quantity,
        )

    return UnitPriceResult(
        unit_sale_price=unit_price,
        standard_unit_label=display_unit,
        declaration_required=True,
        reason=(
            f"Computed from MRP {price} divided by {quantity_in_display_units} "
            f"{display_unit} to yield the unit sale price of {unit_price} per "
            f"{display_unit}."
        ),
        quantity_family=definition.family,
        normalized_quantity=normalized_quantity,
    )
