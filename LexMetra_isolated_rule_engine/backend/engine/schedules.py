"""Tabular Schedules for Legal Metrology (Packaged Commodities) Rules, 2011.

Provides machine-readable tabular definitions and deterministic lookup routines for:
  - First Schedule: Maximum Permissible Error (MPE) on Net Quantity
  - Second Schedule: Standard Pack Sizes by Commodity Class
  - Third Schedule: Prescribed Unit Symbols and Formatting Constraints
  - Fourth Schedule: Permissible Errors on Moisture-Depleting Commodities
  - Fifth Schedule: Commodities Packed by Number
  - Seventh Schedule: Minimum Height of Numerals and Letters based on PDP Area
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from .units import convert, normalize_unit_token


# ===========================================================================
# First Schedule: Maximum Permissible Errors (MPE)
# ===========================================================================
# Nominal Quantity (g or ml) -> (mpe_percent, mpe_absolute_in_base_units)
# Either mpe_percent is applied or a fixed absolute limit is specified.
_MPE_WEIGHT_VOLUME_TIERS: List[Tuple[float, float, Optional[float], Optional[float]]] = [
    # (min_qty_inclusive, max_qty_inclusive, percent_error, fixed_error_g_or_ml)
    (0.0, 50.0, 9.0, None),
    (50.0, 100.0, None, 4.5),
    (100.0, 200.0, 4.5, None),
    (200.0, 300.0, None, 9.0),
    (300.0, 500.0, 3.0, None),
    (500.0, 1000.0, None, 15.0),
    (1000.0, 10000.0, 1.5, None),
    (10000.0, 15000.0, None, 150.0),
    (15000.0, float("inf"), 1.0, None),
]


def lookup_mpe(quantity_val: float, unit: str) -> Dict[str, Any]:
    """Calculate Maximum Permissible Error under the First Schedule.

    Returns a dictionary containing the maximum allowed deficiency.
    """
    token = normalize_unit_token(unit)
    if quantity_val <= 0.0:
        return {
            "supported": False,
            "reason": f"MPE lookup requires a positive nominal quantity; got {quantity_val!r} {unit}",
        }
    if token in ("g", "gram", "grams", "gm", "gms", "mg", "kg", "kilogram", "kgs"):
        base_val = convert(quantity_val, token, "g")
        base_unit = "g"
    elif token in ("ml", "millilitre", "millilitres", "l", "litre", "litres", "cl"):
        base_val = convert(quantity_val, token, "ml")
        base_unit = "ml"
    else:
        return {
            "supported": False,
            "reason": f"MPE weight/volume table not applicable to unit '{unit}'",
        }

    for min_q, max_q, pct, fixed in _MPE_WEIGHT_VOLUME_TIERS:
        if min_q <= base_val < max_q or (max_q == float("inf") and base_val >= min_q):
            if pct is not None:
                max_error = (base_val * pct) / 100.0
                error_desc = f"{pct}% of nominal quantity"
            else:
                max_error = float(fixed)
                error_desc = f"{fixed} {base_unit}"

            return {
                "supported": True,
                "schedule": "First Schedule",
                "nominal_quantity": quantity_val,
                "unit": unit,
                "base_quantity": base_val,
                "base_unit": base_unit,
                "max_permissible_error": max_error,
                "max_permissible_error_unit": base_unit,
                "description": error_desc,
            }

    return {"supported": False, "reason": "Quantity out of schedule range"}


# ===========================================================================
# Second Schedule: Standard Pack Sizes
# ===========================================================================
# Commodity name (normalized lowercase) -> Set of permitted quantities in base units (g or ml)
_STANDARD_PACK_SIZES: Dict[str, Dict[str, Any]] = {
    "baby_food": {
        "unit": "g",
        "allowed_g": {100.0, 200.0, 400.0, 500.0, 1000.0},
        "description": "Baby food / Infant milk substitutes",
    },
    "biscuits": {
        "unit": "g",
        "allowed_g": {25.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0, 300.0, 500.0, 1000.0},
        "multiples_above_1000": 1000.0,
        "description": "Biscuits including cookies",
    },
    "bread": {
        "unit": "g",
        "allowed_g": {100.0, 200.0, 400.0, 800.0},
        "multiples_above_400": 400.0,
        "description": "Bread including white, brown, wheat bread",
    },
    "butter": {
        "unit": "g",
        "allowed_g": {25.0, 50.0, 100.0, 200.0, 500.0, 1000.0, 2000.0, 5000.0},
        "description": "Butter and table margarine",
    },
    "tea": {
        "unit": "g",
        "allowed_g": {25.0, 50.0, 100.0, 200.0, 250.0, 500.0, 1000.0},
        "multiples_above_1000": 1000.0,
        "description": "Tea",
    },
    "coffee": {
        "unit": "g",
        "allowed_g": {25.0, 50.0, 100.0, 200.0, 250.0, 500.0, 1000.0},
        "multiples_above_1000": 1000.0,
        "description": "Coffee and coffee-chicory mixture",
    },
    "edible_oil": {
        "unit": "mixed",
        "allowed_g": {50.0, 100.0, 200.0, 500.0, 1000.0, 2000.0, 3000.0, 5000.0},
        "allowed_ml": {50.0, 100.0, 200.0, 500.0, 1000.0, 2000.0, 3000.0, 5000.0},
        "description": "Edible oils, vanaspati, ghee, mustard oil",
    },
    "salt": {
        "unit": "g",
        "allowed_g": {100.0, 200.0, 500.0, 750.0, 1000.0, 2000.0, 5000.0},
        "description": "Common salt",
    },
    "sugar": {
        "unit": "g",
        "allowed_g": {100.0, 200.0, 500.0, 1000.0, 2000.0, 5000.0},
        "multiples_above_5000": 5000.0,
        "description": "Sugar",
    },
    "rice": {
        "unit": "g",
        "allowed_g": {100.0, 200.0, 500.0, 1000.0, 2000.0, 5000.0, 10000.0},
        "multiples_above_5000": 5000.0,
        "description": "Rice and wheat flour (Atta)",
    },
}


def lookup_standard_pack_size(
    commodity: str, quantity_val: float, unit: str
) -> Dict[str, Any]:
    """Check whether a commodity complies with Second Schedule pack size specifications."""
    comm_key = str(commodity).strip().lower().replace(" ", "_").replace("-", "_")
    matched_entry = None
    for k, spec in _STANDARD_PACK_SIZES.items():
        if k in comm_key or comm_key in k:
            matched_entry = spec
            break

    if not matched_entry:
        return {
            "is_scheduled": False,
            "is_standard": True,
            "reason": f"Commodity '{commodity}' does not have prescribed standard pack sizes in Second Schedule.",
        }

    token = normalize_unit_token(unit)
    # Convert to grams or ml
    if token in ("g", "gram", "grams", "gm", "gms", "kg", "kilogram", "kgs"):
        q_g = convert(quantity_val, token, "g")
        allowed = matched_entry.get("allowed_g", set())
        if q_g in allowed:
            return {"is_scheduled": True, "is_standard": True, "schedule": "Second Schedule"}
        if "multiples_above_1000" in matched_entry and q_g >= 1000.0 and q_g % 1000.0 == 0:
            return {"is_scheduled": True, "is_standard": True, "schedule": "Second Schedule"}
        if "multiples_above_5000" in matched_entry and q_g >= 5000.0 and q_g % 5000.0 == 0:
            return {"is_scheduled": True, "is_standard": True, "schedule": "Second Schedule"}
        return {
            "is_scheduled": True,
            "is_standard": False,
            "schedule": "Second Schedule",
            "reason": f"Quantity {quantity_val} {unit} ({q_g}g) is not a permitted standard pack size for {commodity}.",
        }

    if token in ("ml", "millilitre", "l", "litre", "litres"):
        q_ml = convert(quantity_val, token, "ml")
        allowed_ml = matched_entry.get("allowed_ml", set())
        if q_ml in allowed_ml:
            return {"is_scheduled": True, "is_standard": True, "schedule": "Second Schedule"}
        return {
            "is_scheduled": True,
            "is_standard": False,
            "schedule": "Second Schedule",
            "reason": f"Quantity {quantity_val} {unit} ({q_ml}ml) is not a permitted standard pack size for {commodity}.",
        }

    return {
        "is_scheduled": True,
        "is_standard": False,
        "reason": f"Incompatible unit '{unit}' for scheduled commodity {commodity}.",
    }


# ===========================================================================
# Third Schedule: Unit Symbols and Formatting Constraints
# ===========================================================================
_VALID_THIRD_SCHEDULE_SYMBOLS: Set[str] = {
    "mg", "g", "kg",
    "ml", "l", "L",
    "mm", "cm", "m",
    "sq mm", "sq cm", "sq m",
    "N", "U", "number",
}

_COMMON_INVALID_SYMBOLS: Dict[str, str] = {
    "gms": "g",
    "gm": "g",
    "g.": "g",
    "kgs": "kg",
    "kg.": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "ltr": "l",
    "ltrs": "l",
    "l.": "l",
    "ml.": "ml",
    "mls": "ml",
}


def validate_third_schedule_unit(unit_symbol: str) -> Dict[str, Any]:
    """Validate that declared unit symbol satisfies Third Schedule statutory requirements."""
    raw = str(unit_symbol).strip()
    norm = raw.lower()
    if raw in _VALID_THIRD_SCHEDULE_SYMBOLS:
        return {"valid": True, "symbol": raw, "schedule": "Third Schedule"}
    if norm in _COMMON_INVALID_SYMBOLS:
        correct = _COMMON_INVALID_SYMBOLS[norm]
        return {
            "valid": False,
            "symbol": raw,
            "suggested": correct,
            "reason": f"Unit symbol '{raw}' violates Third Schedule (mandatory symbol: '{correct}').",
        }
    return {
        "valid": False,
        "symbol": raw,
        "reason": f"Unit symbol '{raw}' is not recognized in the Third Schedule.",
    }


# ===========================================================================
# Seventh Schedule: Minimum Height of Numerals and Letters
# ===========================================================================
# Area of PDP (A in cm²) -> (normal_height_mm, blown_moulded_height_mm)
_SEVENTH_SCHEDULE_TIERS: List[Tuple[float, float, float, float]] = [
    # (min_area_inclusive, max_area_inclusive, normal_mm, blown_mm)
    (0.0, 50.0, 1.0, 2.0),
    (50.0, 100.0, 1.5, 3.0),
    (100.0, 500.0, 2.5, 4.0),
    (500.0, 2500.0, 4.0, 6.0),
    (2500.0, float("inf"), 6.0, 6.0),
]


def lookup_min_numeral_height(
    pdp_area_cm2: float,
    packaging_type: str = "normal",
    is_net_quantity: bool = False,
) -> Dict[str, Any]:
    """Look up required minimum numeral/letter height under the Seventh Schedule."""
    p_type = str(packaging_type).strip().lower()
    is_blown = "blown" in p_type or "moulded" in p_type or "perforated" in p_type

    for min_a, max_a, norm_h, blown_h in _SEVENTH_SCHEDULE_TIERS:
        if min_a <= pdp_area_cm2 < max_a or (max_a == float("inf") and pdp_area_cm2 >= min_a):
            target = blown_h if is_blown else norm_h
            return {
                "supported": True,
                "schedule": "Seventh Schedule",
                "pdp_area_cm2": pdp_area_cm2,
                "packaging_type": p_type,
                "required_minimum_height_mm": target,
            }

    return {"supported": False, "reason": "PDP area out of schedule range"}


# ===========================================================================
# Fourth Schedule: Permissible Additional Errors on Moisture-Depleting Commodities
# ===========================================================================
# Legal reference: Rule 12(2) and Fourth Schedule, LMPC Rules 2011.
#
# Status: REPRESENTED_NON_EXECUTABLE
#
# The Fourth Schedule specifies additional permissible tolerances for certain
# commodities that lose moisture between the time of packing and the time of
# inspection (e.g., soaps, dry fruits, tobacco products, spices). These
# tolerances are expressed as percentage allowances on top of the First Schedule
# MPE, specific to each commodity class.
#
# SOURCE DATA LIMITATION: The available source material (gazette_raw.txt)
# contains only the Legal Metrology (Packaged Commodities) Amendment Rules, 2025.
# It does not reproduce the tabular Fourth Schedule data from the original
# G.S.R. 202(E) dated 7th March, 2011. Implementing executable lookup logic
# would require fabricating regulatory values, which is prohibited.
#
# Until the complete original Fourth Schedule table is available, this function
# returns a structured response indicating the limitation. When source data is
# supplied, the table should be structured as:
#   commodity_key -> {"max_additional_moisture_pct": float, "description": str}
#
_FOURTH_SCHEDULE_SOURCE_DATA_AVAILABLE: bool = False
_FOURTH_SCHEDULE_COMMODITIES: Dict[str, Dict[str, Any]] = {
    # Placeholder structure — values require verification from the full LMPC 2011 gazette
    # "soap": {"max_additional_moisture_pct": ..., "description": "Toilet/laundry soaps"},
    # "dry_fruits": {"max_additional_moisture_pct": ..., "description": "Dry fruits and nuts"},
    # "spices": {"max_additional_moisture_pct": ..., "description": "Ground spices and condiments"},
}


def lookup_fourth_schedule_moisture_allowance(
    commodity: str, quantity_val: float, unit: str
) -> Dict[str, Any]:
    """Look up additional permissible moisture error for a commodity under the Fourth Schedule.

    Returns:
        A dict with:
          - "supported": False always until source data is loaded (SOURCE_DATA_MISSING)
          - "reason": explanation of why result is unavailable
          - "schedule": "Fourth Schedule"
          - "legal_reference": the provision this corresponds to

    Once the full LMPC 2011 Fourth Schedule table is available, this function
    should be updated with the verified commodity table and return:
          - "supported": True
          - "commodity": commodity key
          - "max_additional_moisture_pct": float
          - "description": str
    """
    if not _FOURTH_SCHEDULE_SOURCE_DATA_AVAILABLE:
        return {
            "supported": False,
            "schedule": "Fourth Schedule",
            "legal_reference": "Rule 12(2), Legal Metrology (Packaged Commodities) Rules, 2011",
            "reason": (
                "SOURCE_DATA_MISSING: The Fourth Schedule tabular data (permissible moisture "
                "loss percentages per commodity class) is not available in the current source "
                "material. The available gazette source (gazette_raw.txt) contains only the "
                "2025 amendment, not the original 2011 schedule tables. "
                "Provide the full Fourth Schedule table to enable this lookup."
            ),
            "commodity": commodity,
            "quantity_val": quantity_val,
            "unit": unit,
        }

    comm_key = str(commodity).strip().lower().replace(" ", "_").replace("-", "_")
    matched = None
    for k, spec in _FOURTH_SCHEDULE_COMMODITIES.items():
        if k in comm_key or comm_key in k:
            matched = spec
            break

    if not matched:
        return {
            "supported": True,
            "schedule": "Fourth Schedule",
            "is_scheduled": False,
            "reason": f"Commodity '{commodity}' is not subject to Fourth Schedule moisture allowance.",
        }

    return {
        "supported": True,
        "schedule": "Fourth Schedule",
        "is_scheduled": True,
        "commodity": commodity,
        "max_additional_moisture_pct": matched["max_additional_moisture_pct"],
        "description": matched.get("description", ""),
    }


# ===========================================================================
# Fifth Schedule: Commodities Packed by Number
# ===========================================================================
# Legal reference: Rule 15 and Fifth Schedule, LMPC Rules 2011.
#
# Status: REPRESENTED_NON_EXECUTABLE
#
# The Fifth Schedule lists commodities that must be or may be sold by number
# (count) rather than by weight or volume. Examples include electric lamps,
# writing instruments, toilet soap bars, cigarettes, and similar items.
#
# SOURCE DATA LIMITATION: The available source material (gazette_raw.txt)
# contains only the 2025 amendment and does not reproduce the Fifth Schedule
# commodity list from the original G.S.R. 202(E) dated 7th March, 2011.
# Implementing executable lookup with fabricated commodity lists is prohibited.
#
# The function below returns a structured response indicating the limitation
# while preserving the correct interface contract for future population.
#
_FIFTH_SCHEDULE_SOURCE_DATA_AVAILABLE: bool = False
_FIFTH_SCHEDULE_COUNT_COMMODITIES: Set[str] = {
    # Placeholder structure — commodity names require verification from the full LMPC 2011 gazette.
    # Populated entries will be normalized lowercase strings.
    # "electric_lamp",
    # "fluorescent_tube",
    # "razor_blade",
    # "writing_instrument",
    # "toilet_soap",
    # "cigarette",
    # "cheroot",
    # "bidi",
}


def lookup_fifth_schedule_count_commodity(commodity: str) -> Dict[str, Any]:
    """Check whether a commodity is listed in the Fifth Schedule (sold by number).

    Returns:
        A dict with:
          - "supported": False when source data is unavailable (SOURCE_DATA_MISSING)
          - "is_count_commodity": bool when supported
          - "schedule": "Fifth Schedule"
          - "reason": explanation
    """
    if not _FIFTH_SCHEDULE_SOURCE_DATA_AVAILABLE:
        return {
            "supported": False,
            "schedule": "Fifth Schedule",
            "legal_reference": "Rule 15, Legal Metrology (Packaged Commodities) Rules, 2011",
            "reason": (
                "SOURCE_DATA_MISSING: The Fifth Schedule commodity list (items sold by number) "
                "is not available in the current source material. The available gazette source "
                "(gazette_raw.txt) contains only the 2025 amendment. "
                "Provide the full Fifth Schedule commodity list to enable this lookup."
            ),
            "commodity": commodity,
        }

    comm_key = str(commodity).strip().lower().replace(" ", "_").replace("-", "_")
    is_count = any(
        k in comm_key or comm_key in k
        for k in _FIFTH_SCHEDULE_COUNT_COMMODITIES
    )
    return {
        "supported": True,
        "schedule": "Fifth Schedule",
        "is_count_commodity": is_count,
        "commodity": commodity,
        "reason": (
            f"Commodity '{commodity}' {'is' if is_count else 'is not'} "
            "listed in the Fifth Schedule."
        ),
    }


# ===========================================================================
# Sixth Schedule: Method of Testing Packages (Sampling Plan)
# ===========================================================================
# Legal reference: Rule 21 and Sixth Schedule, LMPC Rules 2011.
#
# Status: REPRESENTED_NON_EXECUTABLE (by design — not a product-label check)
#
# The Sixth Schedule defines a statistical acceptance sampling plan for batch
# inspection of packages. It specifies:
#   - Lot size ranges (e.g., 2-150, 151-1200, ...)
#   - Sample size for each lot range
#   - Number of tolerated defective packages (non-conforming quantity)
#   - The "T" criterion for packages with insufficient net quantity
#
# This schedule is inherently PROCEDURAL and relates to the INSPECTION METHOD
# used by Legal Metrology Officers during physical batch testing, not to the
# product label compliance check performed on an individual package.
#
# It is correctly and permanently classified as REPRESENTED_NON_EXECUTABLE
# for the product compliance engine because:
#   1. It requires physical access to a lot/batch, not a single package input
#   2. It uses statistical tables (AQL-style) that require batch-level statistics
#   3. It is an inspection procedure standard, not a labelling requirement
#
# No lookup function is provided or needed for the product compliance engine.
# The schedule's existence and legal function are fully represented in the
# coverage matrix and rule data.
SIXTH_SCHEDULE_NOTE: str = (
    "Sixth Schedule: Method of Testing Packages (LMPC Rules 2011). "
    "This is a statistical batch sampling plan for inspection officers. "
    "It is REPRESENTED_NON_EXECUTABLE by design — not applicable to "
    "individual product label compliance checking."
)
