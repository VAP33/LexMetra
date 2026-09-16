"""Canonical Product Facts normalization layer.

This module provides the single canonical normalization layer between arbitrary
upstream product input (JSON/dict/objects) and the engine's Evidence contract.

It strictly enforces the three-way state distinction required by the LMPC engine:
  - KNOWN: The fact is supplied, present, and usable.
  - EXPLICITLY ABSENT: The source/inspector explicitly establishes that the fact is absent
    (e.g., {"present": False} or an explicit absence record).
  - UNKNOWN / UNINSPECTED: The fact has not been established or was omitted from input.
    A missing JSON key is NEVER inferred as absent.

It normalizes nested structures (such as product.quantity.value and product.quantity.unit)
while maintaining complete backward compatibility with existing flat representations
(such as declared.net_quantity and declared.net_quantity.unit).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, Union

from .evidence import Evidence, EvidenceValue, MISSING


class FactState(str, Enum):
    """Tri-state presence status for a product fact."""
    KNOWN = "KNOWN"
    EXPLICITLY_ABSENT = "EXPLICITLY_ABSENT"
    UNKNOWN = "UNKNOWN"


@dataclass
class CanonicalFact:
    """A single normalized product fact with explicit presence and provenance."""
    name: str
    value: Any = None
    state: FactState = FactState.KNOWN
    unit: Optional[str] = None
    confidence: Optional[float] = None
    provenance: Optional[str] = "structured_input"
    source_text: Optional[str] = None
    source_page: Optional[str] = None
    metadata: Dict[str, Any] = dc_field(default_factory=dict)

    def is_present(self) -> Optional[bool]:
        if self.state == FactState.KNOWN:
            return True
        if self.state == FactState.EXPLICITLY_ABSENT:
            return False
        return None  # UNKNOWN

    def to_evidence_value(self) -> EvidenceValue:
        present_bool = self.is_present()
        return EvidenceValue(
            value=self.value,
            normalized_value=self.value,
            unit=self.unit,
            confidence=self.confidence,
            present=present_bool,
            usable=True if present_bool is True else (False if present_bool is False else None),
            source_text=self.source_text,
            source_page=self.source_page,
            provenance=self.provenance,
        )


def _is_explicit_absence_dict(d: Mapping[str, Any]) -> bool:
    """Detect if a dict represents an explicit absence record."""
    if d.get("present") is False:
        return True
    if d.get("absent") is True:
        return True
    state = str(d.get("state", "")).upper()
    if state in ("EXPLICITLY_ABSENT", "ABSENT", "NOT_OBSERVED", "NOT_PRESENT"):
        return True
    return False


def _extract_fact_from_value(
    path: str, value: Any, default_provenance: str = "structured_input"
) -> Optional[CanonicalFact]:
    """Parse a scalar or dict node into a CanonicalFact if applicable."""
    if isinstance(value, EvidenceValue):
        if value.present is False:
            state = FactState.EXPLICITLY_ABSENT
        elif value.present is True or (value.value is not None and value.present is None):
            state = FactState.KNOWN
        else:
            state = FactState.UNKNOWN
        return CanonicalFact(
            name=path,
            value=value.value,
            state=state,
            unit=value.unit,
            confidence=value.confidence,
            provenance=value.provenance or default_provenance,
            source_text=value.source_text,
            source_page=value.source_page,
        )

    if isinstance(value, Mapping):
        # Check for explicit absence descriptor
        if _is_explicit_absence_dict(value):
            return CanonicalFact(
                name=path,
                value=value.get("value"),
                state=FactState.EXPLICITLY_ABSENT,
                unit=value.get("unit"),
                confidence=value.get("confidence"),
                provenance=value.get("provenance", default_provenance),
                source_text=value.get("source_text"),
                source_page=value.get("source_page"),
            )

        # Check for structured evidence descriptor: {"value": ..., "unit": ..., "confidence": ...}
        if "value" in value and ("unit" in value or "confidence" in value or "present" in value or "provenance" in value):
            present_flag = value.get("present")
            if present_flag is False:
                state = FactState.EXPLICITLY_ABSENT
            elif present_flag is True or value["value"] is not None:
                state = FactState.KNOWN
            else:
                state = FactState.UNKNOWN

            return CanonicalFact(
                name=path,
                value=value["value"],
                state=state,
                unit=value.get("unit"),
                confidence=value.get("confidence"),
                provenance=value.get("provenance", default_provenance),
                source_text=value.get("source_text"),
                source_page=value.get("source_page"),
            )

    return None


def _walk_product_tree(value: Any, prefix: str = "") -> Iterator[Tuple[str, Any]]:
    """Walk product dict/lists yielding (path, value) leaves."""
    if isinstance(value, Mapping):
        for k, v in value.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, Mapping):
                if _extract_fact_from_value(path, v) is not None:
                    yield path, v
                yield from _walk_product_tree(v, path)
            elif isinstance(v, list):
                yield from _walk_product_tree(v, path)
            else:
                yield path, v
    elif isinstance(value, list):
        if prefix:
            yield prefix, value
        for i, item in enumerate(value):
            yield from _walk_product_tree(item, f"{prefix}[{i}]")
    else:
        yield prefix, value


class CanonicalProductFacts:
    """Canonical bag of normalized product facts with presence semantics."""

    def __init__(self, raw_input: Optional[Mapping[str, Any]] = None) -> None:
        self.facts: Dict[str, CanonicalFact] = {}
        self.raw_data: Dict[str, Any] = dict(raw_input or {})
        if raw_input:
            self._normalize(raw_input)

    def set_fact(
        self,
        name: str,
        value: Any = None,
        *,
        state: FactState = FactState.KNOWN,
        unit: Optional[str] = None,
        confidence: Optional[float] = None,
        provenance: str = "structured_input",
        source_text: Optional[str] = None,
        source_page: Optional[str] = None,
    ) -> "CanonicalProductFacts":
        self.facts[name] = CanonicalFact(
            name=name,
            value=value,
            state=state,
            unit=unit,
            confidence=confidence,
            provenance=provenance,
            source_text=source_text,
            source_page=source_page,
        )
        return self

    def get_fact(self, name: str) -> Optional[CanonicalFact]:
        return self.facts.get(name)

    def _normalize(self, data: Mapping[str, Any]) -> None:
        """Extract facts and canonical aliases from input mapping."""
        raw = dict(data)
        product = raw.get("product") if isinstance(raw.get("product"), Mapping) else raw

        # Walk product fields
        for path, leaf in _walk_product_tree(product):
            if not path:
                continue
            fact = _extract_fact_from_value(path, leaf)
            if fact:
                self.facts[path] = fact
            else:
                self.facts[path] = CanonicalFact(
                    name=path,
                    value=leaf,
                    state=FactState.KNOWN,
                )

        # Walk raw root-level fields (e.g. trade_type, assessment_date, category)
        for path, leaf in _walk_product_tree(raw):
            if not path or path in self.facts:
                continue
            fact = _extract_fact_from_value(path, leaf)
            if fact:
                self.facts[path] = fact
            else:
                self.facts[path] = CanonicalFact(
                    name=path,
                    value=leaf,
                    state=FactState.KNOWN,
                )

        # Canonical aliases: bridge nested and flat representations
        self._bridge_quantity_aliases()
        self._bridge_declaration_aliases()

    def _bridge_quantity_aliases(self) -> None:
        """Bridge product.quantity / net_quantity nested representations."""
        # Find quantity candidates across common paths
        quantity_val = None
        quantity_unit = None
        quantity_fact = None

        candidate_roots = ["product.quantity", "product.net_quantity", "quantity", "net_quantity", "declared.net_quantity"]
        for root in candidate_roots:
            val_key = f"{root}.value"
            unit_key = f"{root}.unit"
            if val_key in self.facts:
                quantity_val = self.facts[val_key].value
                quantity_fact = self.facts[val_key]
                if unit_key in self.facts:
                    quantity_unit = self.facts[unit_key].value or self.facts[unit_key].unit
                elif self.facts[val_key].unit:
                    quantity_unit = self.facts[val_key].unit
                break
            elif root in self.facts:
                fact = self.facts[root]
                if fact.value is not None:
                    quantity_val = fact.value
                    quantity_unit = fact.unit
                    quantity_fact = fact
                    break

        if quantity_fact is not None:
            # Propagate to standard flat paths required by LMPC rules if not already set
            flat_target = "declared.net_quantity"
            if flat_target not in self.facts:
                self.facts[flat_target] = CanonicalFact(
                    name=flat_target,
                    value=quantity_val,
                    state=quantity_fact.state,
                    unit=quantity_unit,
                    confidence=quantity_fact.confidence,
                    provenance=quantity_fact.provenance,
                )
            flat_unit_target = "declared.net_quantity.unit"
            if quantity_unit is not None and flat_unit_target not in self.facts:
                self.facts[flat_unit_target] = CanonicalFact(
                    name=flat_unit_target,
                    value=quantity_unit,
                    state=quantity_fact.state,
                    unit=quantity_unit,
                    confidence=quantity_fact.confidence,
                    provenance=quantity_fact.provenance,
                )

    def _bridge_declaration_aliases(self) -> None:
        """Ensure standard declared.* aliases exist for root-level product fields."""
        alias_map = {
            "mrp": "declared.mrp",
            "manufacturer": "declared.manufacturer_name_address",
            "manufacturer_name_address": "declared.manufacturer_name_address",
            "common_name": "declared.common_name",
            "generic_name": "declared.common_name",
            "mfg_date": "declared.mfg_date",
            "manufacturing_date": "declared.mfg_date",
            "best_before": "declared.best_before_use_by",
            "expiry_date": "declared.best_before_use_by",
            "consumer_care": "declared.consumer_care",
            "country_of_origin": "declared.country_of_origin",
            "unit_sale_price": "declared.unit_sale_price",
        }

        for source_stem, target in alias_map.items():
            for prefix in ["", "product.", "declared."]:
                source_path = f"{prefix}{source_stem}"
                if source_path in self.facts and target not in self.facts:
                    src = self.facts[source_path]
                    self.facts[target] = CanonicalFact(
                        name=target,
                        value=src.value,
                        state=src.state,
                        unit=src.unit,
                        confidence=src.confidence,
                        provenance=src.provenance,
                    )
                    break

    def to_evidence(self) -> Evidence:
        """Export normalized facts into the engine Evidence contract."""
        ev = Evidence()
        ev.context.update(self.raw_data)

        product = self.raw_data.get("product") if isinstance(self.raw_data.get("product"), Mapping) else self.raw_data
        if isinstance(product, Mapping):
            ev.context.setdefault("product", dict(product))
            for k, v in product.items():
                ev.context.setdefault(str(k), v)

        for name, fact in self.facts.items():
            ev.fields[name] = fact.to_evidence_value()

        return ev


def normalize_to_canonical_facts(
    product_input: Union[Evidence, Mapping[str, Any], CanonicalProductFacts]
) -> CanonicalProductFacts:
    """Normalize arbitrary product inputs into CanonicalProductFacts."""
    if isinstance(product_input, CanonicalProductFacts):
        return product_input
    if isinstance(product_input, Evidence):
        facts = CanonicalProductFacts(product_input.context)
        for k, ev_val in product_input.fields.items():
            facts.facts[k] = _extract_fact_from_value(k, ev_val) or CanonicalFact(
                name=k,
                value=ev_val.value,
                state=FactState.KNOWN if ev_val.is_present() else (FactState.EXPLICITLY_ABSENT if ev_val.present is False else FactState.UNKNOWN),
                unit=ev_val.unit,
                confidence=ev_val.confidence,
                provenance=ev_val.provenance,
                source_text=ev_val.source_text,
                source_page=ev_val.source_page,
            )
        return facts
    if isinstance(product_input, Mapping):
        return CanonicalProductFacts(product_input)

    raise TypeError(f"Expected Evidence, Mapping, or CanonicalProductFacts, got {type(product_input).__name__}")
