"""Differential harness: legacy exemption.py  vs  OpenL decision table.

For every input it runs BOTH engines and compares the legal decision:
    (is_exempt, exemption_type, rule_id, review_required)

`reason` prose is intentionally excluded from parity (the legacy engine embeds
dynamic values in its text; the decision is what matters legally).

This is the fixture format handed to TEST-01 (docs/cdd/agents/RULE-01 §Contract
you produce): same input -> {old_engine_result, openl_result} -> diff.

Usage:
    backend/.venv/bin/python backend/openl/scripts/differential_exemption.py
Exit code 0 = full parity; 1 = at least one mismatch (details printed + written
to backend/openl/dist/exemption_differential.json).
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

# Make `import exemption` and `import openl_client` work.
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "openl"))

from exemption import ExemptionInput, ExemptionResult, classify_exemption  # noqa: E402
from openl_client import OpenLExemptionClient  # noqa: E402

PARITY_KEYS = ("is_exempt", "exemption_type", "rule_id", "review_required")


def build_matrix() -> list[ExemptionInput]:
    sale_types = [
        "retail", "wholesale", "industrial", "institutional", "export",
        "ecommerce", "e-commerce", "gift-pack",
    ]
    categories = [
        "sugar", "cement", "fertilizer", "agricultural farm produce",
        "tobacco", "tobacco products", "pan masala", "biscuits",
    ]
    quantities = [
        (None, None), (0, "g"), (-5, "g"), (5, "number"),
        (5, "g"), (10, "g"), (11, "g"), (20, "g"),
        (5, "ml"), (10, "ml"), (11, "ml"),
        (24, "kg"), (25, "kg"), (26, "kg"),
        (49, "kg"), (50, "kg"), (51, "kg"),
        (24, "l"), (25, "l"), (26, "l"),
        (500, "g"), (2, "kg"), (1500, "ml"),
    ]
    cases: list[ExemptionInput] = []
    # Core cartesian over the common path (default flags).
    for st in sale_types:
        for cat in categories:
            for val, unit in quantities:
                cases.append(ExemptionInput(
                    sale_type=st, net_quantity_value=val, net_quantity_unit=unit,
                    product_category=cat,
                ))
    # Flag-driven branches (prepackaged / direct / export-only).
    for flag_kwargs in (
        {"is_prepackaged": False},
        {"is_prepackaged": True},
        {"direct_to_industrial_or_institutional": True},
        {"direct_to_industrial_or_institutional": False},
        {"is_export_only": True},
    ):
        for st in ("retail", "export", "wholesale", "industrial"):
            for val, unit in ((5, "g"), (30, "kg"), (None, None)):
                cases.append(ExemptionInput(
                    sale_type=st, net_quantity_value=val, net_quantity_unit=unit,
                    product_category="sugar", **flag_kwargs,
                ))
    return cases


def parity_view(r: ExemptionResult) -> dict:
    d = asdict(r)
    return {k: d[k] for k in PARITY_KEYS}


def main() -> int:
    client = OpenLExemptionClient()
    cases = build_matrix()
    fixtures = []
    mismatches = []
    for inp in cases:
        old = classify_exemption(inp)
        openl = client.classify(inp)
        old_v, openl_v = parity_view(old), parity_view(openl)
        rec = {
            "input": asdict(inp),
            "old_engine_result": old_v,
            "openl_result": openl_v,
            "match": old_v == openl_v,
        }
        fixtures.append(rec)
        if not rec["match"]:
            mismatches.append(rec)

    out = BACKEND / "openl" / "dist" / "exemption_differential.json"
    out.write_text(json.dumps(fixtures, indent=2), encoding="utf-8")

    total = len(fixtures)
    print(f"Differential cases: {total}")
    print(f"Parity matches:     {total - len(mismatches)}")
    print(f"Mismatches:         {len(mismatches)}")
    print(f"Fixtures written:   {out}")
    if mismatches:
        print("\n=== MISMATCHES (first 20) ===")
        for m in mismatches[:20]:
            i = m["input"]
            print(
                f"- sale={i['sale_type']!r} cat={i['product_category']!r} "
                f"qty={i['net_quantity_value']}{i['net_quantity_unit']} "
                f"prepack={i['is_prepackaged']} direct={i['direct_to_industrial_or_institutional']} "
                f"exportOnly={i['is_export_only']}\n"
                f"    old  = {m['old_engine_result']}\n"
                f"    openl= {m['openl_result']}"
            )
        return 1
    print("\nFULL PARITY: OpenL matches exemption.py on every case.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
