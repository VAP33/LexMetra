"""
Exemption and scope classification for LMPC inspection.

This module runs before ordinary package-declaration checks.

Important:
- An exemption is NOT the same thing as a different declaration regime.
- Wholesale is therefore not treated as an exemption merely because it has
  a different declaration set.
- Weight and volume are never mixed. 1 litre is not "1 kg-equivalent".
- Unknown / ambiguous facts do not produce an exemption.
- Legal thresholds live in rules/rules.json. This module reads them rather than
  duplicating policy constants in Python.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "rules.json"


#: `exemption_type` used when the quantity-threshold rules could not be reached
#: because the net quantity itself was never established. See
#: `quantity_is_established` for why this is a THIRD outcome and not a False.
QUANTITY_NOT_ESTABLISHED = "quantity_not_established"


def quantity_is_established(value: Optional[float],
                           unit: Optional[str]) -> bool:
    """
    Whether a net quantity is usable as the input to a threshold rule.

    A zero or negative quantity counts as NOT established rather than as a small
    package. It is an invalid assertion, not an observation, and letting it flow
    into the Rule 26(a) small-pack comparison would grant an exemption on the
    strength of a broken reading.
    """
    if value is None or unit is None or not str(unit).strip():
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class ExemptionInput:
    sale_type: str
    #: Optional because the net quantity is itself one of the declarations the
    #: pipeline READS from the package. Requiring it up front forced an inspector
    #: to type the very value under inspection before any image was analysed.
    net_quantity_value: Optional[float]
    net_quantity_unit: Optional[str]
    product_category: str
    is_export_only: bool = False
    retail_bundle_count: Optional[int] = None

    # Optional context. These default to False so the existing backend call
    # remains compatible.
    is_prepackaged: Optional[bool] = None
    direct_to_industrial_or_institutional: Optional[bool] = None


@dataclass(frozen=True)
class ExemptionResult:
    is_exempt: bool
    reason: Optional[str]
    rule_id: Optional[str]
    exemption_type: Optional[str] = None
    review_required: bool = False


def _load_rules() -> Dict[str, dict]:
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    return {rule["rule_id"]: rule for rule in data["rules"]}


def _normalise_text(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def _normalise_sale_type(value: str) -> str:
    value = _normalise_text(value)
    aliases = {
        "e commerce": "ecommerce",
        "e-commerce": "ecommerce",
    }
    return aliases.get(value, value)


def _normalise_unit(unit: str) -> str:
    unit = _normalise_text(unit)

    aliases = {
        "gram": "g",
        "grams": "g",
        "gms": "g",
        "gm": "g",
        "kilogram": "kg",
        "kilograms": "kg",
        "kgs": "kg",
        "millilitre": "ml",
        "millilitres": "ml",
        "milliliter": "ml",
        "milliliters": "ml",
        "litre": "l",
        "litres": "l",
        "liter": "l",
        "liters": "l",
        "pieces": "number",
        "piece": "number",
        "pcs": "number",
        "count": "number",
        "nos": "number",
    }
    return aliases.get(unit, unit)


def _to_grams(value: Optional[float], unit: Optional[str]) -> Optional[float]:
    """Convert MASS only. Volume is deliberately rejected."""
    if value is None or unit is None:
        return None
    unit = _normalise_unit(unit)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if value < 0:
        return None
    if unit == "g":
        return value
    if unit == "kg":
        return value * 1000.0
    return None


def _to_millilitres(value: Optional[float], unit: Optional[str]) -> Optional[float]:
    """Convert VOLUME only. Mass is deliberately rejected."""
    if value is None or unit is None:
        return None
    unit = _normalise_unit(unit)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if value < 0:
        return None
    if unit == "ml":
        return value
    if unit == "l":
        return value * 1000.0
    return None


def _quantity_exceeds_rule3_limit(
    value: float,
    unit: str,
    product_category: str,
    rule3: dict,
) -> Optional[bool]:
    """
    Return:
      True  -> quantity definitely exceeds the applicable limit
      False -> quantity definitely does not exceed it
      None  -> rule cannot be evaluated from this unit/category
    """
    category = _normalise_text(product_category)

    # Rule 3 is expressed separately for kg and litre. Never convert between
    # mass and volume without a legally/physically supplied density.
    mass_g = _to_grams(value, unit)
    volume_ml = _to_millilitres(value, unit)

    threshold = rule3.get("threshold", {})
    general = threshold.get("general_package_quantity_exemption", {})
    cement_fertilizer = threshold.get("cement_fertilizer_exception", {})

    if mass_g is not None:
        if category in {"cement", "fertilizer", "agricultural farm produce"}:
            limit_kg = float(cement_fertilizer.get("weight_kg_gt", 50))
        else:
            limit_kg = float(general.get("weight_kg_gt", 25))
        return mass_g > limit_kg * 1000.0

    if volume_ml is not None:
        # Rule 3's litre exclusion is 25 litre for the general case.
        limit_l = float(general.get("volume_l_gt", 25))
        return volume_ml > limit_l * 1000.0

    return None


def _rule26_small_pack_status(
    value: float,
    unit: str,
    product_category: str,
    rules: Dict[str, dict],
) -> Optional[ExemptionResult]:
    """
    Handle Rule 26(a) small-package treatment.

    This is deliberately conservative:
      - <= 10 g/ml can be exempt when the applicable exclusion does not apply.
      - 10-20 g/ml is NOT treated as wholly exempt.
      - for 10-20 g/ml the ordinary declaration engine must use the applicable
        reduced/partial requirement set from the legal rule data.
    """
    rule = rules.get("LMPC-2011-R26-SMALL-PACKS")
    if not rule:
        return None

    unit = _normalise_unit(unit)
    category = _normalise_text(product_category)

    mass_g = _to_grams(value, unit)
    volume_ml = _to_millilitres(value, unit)

    quantity = mass_g if mass_g is not None else volume_ml
    quantity_unit = "g" if mass_g is not None else "ml"

    if quantity is None:
        return None

    excluded_categories = {
        "tobacco",
        "tobacco product",
        "tobacco products",
        "pan masala",
    }

    if category in excluded_categories:
        return None

    upper = rule.get("threshold", {}).get("small_pack_upper_bound", {})
    if quantity_unit == "g":
        exempt_at_or_below = float(upper.get("weight_g_lte", 10))
    else:
        exempt_at_or_below = float(upper.get("volume_ml_lte", 10))

    if quantity <= exempt_at_or_below:
        return ExemptionResult(
            is_exempt=True,
            reason=(
                f"Package quantity {quantity:g}{quantity_unit} falls within the "
                "Rule 26(a) small-package exemption threshold, and no configured "
                "Rule 26 exclusion was identified."
            ),
            rule_id=rule["rule_id"],
            exemption_type="rule_26_small_pack",
            review_required=rule.get("verification_status") != "verified",
        )

    # 10-20 g/ml is not a full exemption. Return None so the ordinary rule
    # engine can apply the partial declaration requirements once those
    # requirements are represented explicitly in rules.json.
    return None


def classify_exemption(inp: ExemptionInput) -> ExemptionResult:
    """
    Classify only genuine scope/exemption conditions.

    Wholesale is deliberately NOT returned as exempt. It is a different
    declaration path and is handled by Rule 24 in the rule engine.
    """
    rules = _load_rules()

    sale_type = _normalise_sale_type(inp.sale_type)
    category = _normalise_text(inp.product_category)

    rule3 = rules.get("LMPC-2011-R3-SCOPE")
    if rule3 is None:
        raise RuntimeError("LMPC-2011-R3-SCOPE is missing from rules.json")

    # 1. The package must be pre-packaged for the LMPC packaged-commodity
    # chapter to be relevant. If the caller explicitly establishes that it is
    # not pre-packaged, do not run retail packaged-commodity checks.
    if inp.is_prepackaged is False:
        return ExemptionResult(
            is_exempt=True,
            reason="Commodity is explicitly classified as not pre-packaged.",
            rule_id=rule3["rule_id"],
            exemption_type="not_prepackaged",
        )

    # 2. Direct industrial/institutional consumer.
    if inp.direct_to_industrial_or_institutional is True:
        return ExemptionResult(
            is_exempt=True,
            reason=(
                "Package is explicitly classified as a direct sale to an "
                "industrial/institutional consumer."
            ),
            rule_id=rule3["rule_id"],
            exemption_type="industrial_or_institutional_direct_sale",
        )

    if sale_type in {"industrial", "institutional"}:
        return ExemptionResult(
            is_exempt=True,
            reason=(
                "Sale type is industrial/institutional. Rule 3 excludes "
                "packages meant for industrial or institutional consumers "
                "from the retail chapter."
            ),
            rule_id=rule3["rule_id"],
            exemption_type="industrial_or_institutional_direct_sale",
        )

    # 3. Export-only status is not, by itself, a blanket domestic "LMPC
    # exemption" in every context. It changes the applicable sale pathway.
    # Do not claim exemption merely because an export flag is present.
    #
    # Rule 25 governs an export package that is subsequently sold in India.
    # Therefore, if is_export_only=True and sale_type is genuinely export,
    # there is no domestic retail-package declaration evaluation here.
    if inp.is_export_only and sale_type == "export":
        return ExemptionResult(
            is_exempt=True,
            reason=(
                "Package is classified as export-only and the transaction is "
                "classified as export, so the domestic retail declaration "
                "path is not being evaluated."
            ),
            rule_id=rule3["rule_id"],
            exemption_type="export_only_transaction",
        )

    # If a package is marked export-only but the sale type is domestic retail
    # or wholesale, do NOT silently exempt it. Rule 25 needs to be evaluated.
    # That evaluation belongs in the main rule engine.

    # 4. Rule 3 quantity exclusion.
    #
    # Both remaining threshold rules (Rule 3's quantity exclusion and Rule 26(a)'s
    # small-package relaxation) are functions of the net quantity. If the quantity
    # was never established, neither can be evaluated, and the honest answer is
    # neither "exempt" nor "confirmed not exempt" but "not determined".
    #
    # Previously this fell through to the final `is_exempt=False,
    # review_required=False` result, which asserted that the package is NOT
    # exempt on the strength of a quantity nobody had read. That is the worse
    # direction of the two: a small pack lawfully entitled to the Rule 26(a)
    # relaxation would have the full declaration set enforced against it, and
    # nothing in the output told a reviewer the exemption question had gone
    # unanswered. The helpers already distinguish "cannot evaluate" by returning
    # None; only this function was discarding it.
    if not quantity_is_established(inp.net_quantity_value, inp.net_quantity_unit):
        return ExemptionResult(
            is_exempt=False,
            reason=(
                "The net quantity was not established, so the Rule 3 quantity "
                "exclusion and the Rule 26(a) small-package relaxation could "
                "not be evaluated. This package is NOT being asserted to be "
                "non-exempt; the question is undetermined and requires either a "
                "readable net-quantity declaration or a reviewer's confirmation."
            ),
            rule_id=None,
            exemption_type=QUANTITY_NOT_ESTABLISHED,
            review_required=True,
        )

    exceeds = _quantity_exceeds_rule3_limit(
        inp.net_quantity_value,
        inp.net_quantity_unit,
        inp.product_category,
        rule3,
    )

    if exceeds is True:
        unit = _normalise_unit(inp.net_quantity_unit)
        return ExemptionResult(
            is_exempt=True,
            reason=(
                f"Package quantity {inp.net_quantity_value:g}{unit} exceeds "
                "the applicable Rule 3 Chapter-II quantity threshold."
            ),
            rule_id=rule3["rule_id"],
            exemption_type="rule_3_quantity_exclusion",
            review_required=rule3.get("verification_status") != "verified",
        )

    # 5. Rule 26(a) small-package exemption.
    small_pack = _rule26_small_pack_status(
        inp.net_quantity_value,
        inp.net_quantity_unit,
        inp.product_category,
        rules,
    )
    if small_pack is not None:
        return small_pack

    # 6. Wholesale is a different declaration regime, NOT an exemption.
    # The bundle count is retained as context for Rule 24/definition logic.
    if sale_type == "wholesale":
        return ExemptionResult(
            is_exempt=False,
            reason=(
                "Wholesale package is not treated as exempt. Apply the "
                "wholesale-package declaration pathway separately."
            ),
            rule_id=None,
            exemption_type="different_declaration_regime",
        )

    # 7. Unsupported/ambiguous sale types do not create an exemption.
    if sale_type not in {"retail", "ecommerce", "export"}:
        return ExemptionResult(
            is_exempt=False,
            reason=(
                f"Sale type '{inp.sale_type}' is not recognized as a verified "
                "LMPC exemption condition. Human review may be required."
            ),
            rule_id=None,
            exemption_type="unknown_sale_type",
            review_required=True,
        )

    return ExemptionResult(
        is_exempt=False,
        reason=None,
        rule_id=None,
        exemption_type=None,
        review_required=False,
    )
