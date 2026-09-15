"""OpenL RuleServices client for the LMPC Rule 3/26 exemption decision table.

This is the first, narrow slice of the future `RuleSet Resolver -> OpenL`
contract (docs/cdd/01-CONTRACTS.md §2). It is intentionally scoped to the
exemption rule so TEST-01 can build the differential harness against a real,
running OpenL service before the full resolver / feature-flag cutover.

Boundaries (see docs/cdd/agents/RULE-01/DECISIONS.md):
- Unit normalization + "quantity established" validation are DATA-CLEANING and
  are reused verbatim from `backend/exemption.py` helpers (not re-implemented),
  so the differential test isolates the *legal decision*, which is what moved
  into OpenL.
- OpenL owns the legal decision and returns the `exemption_type` string. This
  client maps that string back to the existing `ExemptionResult` shape. The
  mapping (is_exempt / rule_id / review_required) is a deterministic consequence
  of the type + rules.json `verification_status`; it is NOT an independent legal
  threshold, so it does not violate "do not silently change a threshold".
- `rule_engine.py` / `exemption.py` remain the source of truth until TEST-01
  proves parity and ARCH-01 signs off on cutover.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import httpx  # already a backend dependency (requirements.txt)

# Reuse the existing, tested normalization + the ExemptionInput/Result shapes.
from exemption import (  # type: ignore
    ExemptionInput,
    ExemptionResult,
    _normalise_sale_type,
    _normalise_text,
    _to_grams,
    _to_millilitres,
    quantity_is_established,
)

_RULES_PATH = Path(__file__).resolve().parents[1] / ".." / "rules" / "rules.json"

RULE3_ID = "LMPC-2011-R3-SCOPE"
RULE26_ID = "LMPC-2011-R26-SMALL-PACKS"

# Sentinel for "this quantity is not a mass / not a volume / not usable".
NA = -1.0


def _load_verification_status() -> dict[str, str]:
    data = json.loads(Path(_RULES_PATH).read_text(encoding="utf-8"))
    return {r["rule_id"]: r.get("verification_status", "") for r in data["rules"]}


def build_request(inp: ExemptionInput) -> dict:
    """Turn an ExemptionInput into the OpenL classifyExemption request payload.

    Mirrors the pre-decision normalization inside exemption.classify_exemption so
    the only thing that differs between the two engines is the decision itself.
    """
    sale_type = _normalise_sale_type(inp.sale_type)
    category = _normalise_text(inp.product_category)
    mass_g = _to_grams(inp.net_quantity_value, inp.net_quantity_unit)
    volume_ml = _to_millilitres(inp.net_quantity_value, inp.net_quantity_unit)
    return {
        "saleType": sale_type,
        "productCategory": category,
        "massG": NA if mass_g is None else float(mass_g),
        "volumeMl": NA if volume_ml is None else float(volume_ml),
        "quantityEstablished": quantity_is_established(
            inp.net_quantity_value, inp.net_quantity_unit
        ),
        "isPrepackagedFalse": inp.is_prepackaged is False,
        "directIndInst": inp.direct_to_industrial_or_institutional is True,
        "isExportOnly": bool(inp.is_export_only),
    }


class OpenLExemptionClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        service_path: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OPENL_BASE_URL", "http://localhost:8080")).rstrip("/")
        self.service_path = (
            service_path or os.environ.get("OPENL_EXEMPTION_PATH", "lexmetra/lexmetra")
        ).strip("/")
        self.timeout = timeout
        self._verification = _load_verification_status()

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/{self.service_path}/classifyExemption"

    def classify_type(self, inp: ExemptionInput) -> str:
        """Call OpenL and return the raw exemption_type string."""
        resp = httpx.post(self.endpoint, json=build_request(inp), timeout=self.timeout)
        resp.raise_for_status()
        # RESTFUL publisher returns a bare JSON string for a String return type.
        text = resp.text.strip()
        try:
            val = resp.json()
        except (ValueError, json.JSONDecodeError):
            val = text
        return str(val)

    def _review_required(self, rule_id: Optional[str], base: bool) -> bool:
        """review_required = base OR (rule's verification_status != 'verified')."""
        if base:
            return True
        if rule_id is None:
            return False
        return self._verification.get(rule_id, "") != "verified"

    def classify(self, inp: ExemptionInput) -> ExemptionResult:
        """Full mapping OpenL exemption_type -> ExemptionResult (verdict shape)."""
        etype = self.classify_type(inp)
        return self.map_type(etype, inp)

    def map_type(self, etype: str, inp: ExemptionInput) -> ExemptionResult:
        if etype == "none":
            return ExemptionResult(False, None, None, None, False)
        if etype == "not_prepackaged":
            return ExemptionResult(True, _reason(etype, inp), RULE3_ID, etype, False)
        if etype in ("industrial_or_institutional_direct_sale", "export_only_transaction"):
            return ExemptionResult(True, _reason(etype, inp), RULE3_ID, etype, False)
        if etype == "rule_3_quantity_exclusion":
            return ExemptionResult(
                True, _reason(etype, inp), RULE3_ID, etype,
                self._review_required(RULE3_ID, False),
            )
        if etype == "rule_26_small_pack":
            return ExemptionResult(
                True, _reason(etype, inp), RULE26_ID, etype,
                self._review_required(RULE26_ID, False),
            )
        if etype == "quantity_not_established":
            return ExemptionResult(False, _reason(etype, inp), None, etype, True)
        if etype == "different_declaration_regime":
            return ExemptionResult(False, _reason(etype, inp), None, etype, False)
        if etype == "unknown_sale_type":
            return ExemptionResult(False, _reason(etype, inp), None, etype, True)
        raise ValueError(f"Unknown exemption_type from OpenL: {etype!r}")


def _reason(etype: str, inp: ExemptionInput) -> str:
    """Human-readable reason regenerated from the type.

    NOTE: reason prose is descriptive text, not a legal threshold. Parity is
    asserted on (is_exempt, exemption_type, rule_id, review_required), NOT on the
    exact reason string (the legacy engine embeds dynamic values in its prose).
    """
    return f"OpenL classified this package as '{etype}'."
