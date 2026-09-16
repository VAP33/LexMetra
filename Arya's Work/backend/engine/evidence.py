"""
Generic normalized-evidence contract (engine.md section 23).

The engine must not depend on any particular OCR provider, product schema,
or regulation. ``Evidence`` is a flat-addressable, dot-path-navigable bag of
``EvidenceValue`` objects (value + unit + confidence + provenance), backed by
plain dict/list data so any upstream system (LexMetra's OCR pipeline, a
manual form, another product's extraction pipeline) can populate it without
any engine-specific classes.

Field paths use dot notation with optional list indices, e.g.:
    "declared.net_quantity.value"
    "declared.ingredients[0].name"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional

_PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


@dataclass
class EvidenceValue:
    """
    One observed value plus everything needed to judge and explain it.

    ``value`` is the raw/normalized Python value (str, float, bool, list...).
    Everything else is optional context a rule condition or the explanation
    generator MAY use, but never fabricates if absent.
    """

    value: Any = None
    normalized_value: Any = None
    unit: Optional[str] = None
    confidence: Optional[float] = None
    present: Optional[bool] = None  # None = unknown, not "assume False"
    source_text: Optional[str] = None
    source_page: Optional[str] = None
    source_region: Optional[Any] = None
    image_id: Optional[str] = None
    bbox: Optional[Any] = None
    provenance: Optional[str] = None
    verification_status: Optional[str] = None
    usable: Optional[bool] = None
    quality_state: Optional[str] = None  # DETECTED, VERIFIED, USABLE, NOT_OBSERVED, CONFLICTING, AMBIGUOUS, INSUFFICIENT
    alternatives: Optional[List[Any]] = None
    notes: Optional[str] = None

    def is_present(self) -> bool:
        if self.present is not None:
            return self.present
        return self.value is not None

    def is_usable(self) -> bool:
        if self.usable is not None:
            return self.usable
        if self.quality_state in ("NOT_OBSERVED", "CONFLICTING", "AMBIGUOUS", "INSUFFICIENT"):
            return False
        return self.is_present()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "normalized_value": self.normalized_value,
            "unit": self.unit,
            "confidence": self.confidence,
            "present": self.is_present(),
            "usable": self.is_usable(),
            "source_text": self.source_text,
            "source_page": self.source_page,
            "image_id": self.image_id,
            "bbox": self.bbox,
            "provenance": self.provenance,
            "verification_status": self.verification_status,
            "quality_state": self.quality_state,
            "alternatives": self.alternatives,
            "notes": self.notes,
        }


def _split_path(path: str) -> List[Any]:
    tokens: List[Any] = []
    for m in _PATH_TOKEN.finditer(path):
        name, idx = m.group(1), m.group(2)
        if name is not None:
            tokens.append(name)
        elif idx is not None:
            tokens.append(int(idx))
    return tokens


class _Missing:
    """Sentinel distinct from None: 'field does not exist' vs 'field is null'."""

    def __repr__(self) -> str:
        return "<MISSING>"


MISSING = _Missing()


@dataclass
class Evidence:
    """
    A flat, hierarchical bag of evidence for one evaluation.

    Two kinds of entries are supported:
      - ``fields``: EvidenceValue objects, addressed by simple field name
        (this is the common case for declaration-style facts).
      - ``context``: arbitrary nested plain data (dict/list/scalar), addressed
        by dot-path, for anything that isn't itself "one observed fact"
        (e.g. product category, sale channel, computed aggregates).

    Conditions may reference either a bare field name (looked up in
    ``fields`` first, falling back to ``context``) or an explicit
    ``context.<path>`` / ``field.<name>.<attr>`` reference.
    """

    fields: Dict[str, EvidenceValue] = dc_field(default_factory=dict)
    context: Dict[str, Any] = dc_field(default_factory=dict)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    def set_field(self, name: str, value: Any, **kwargs: Any) -> "Evidence":
        if isinstance(value, EvidenceValue):
            self.fields[name] = value
        else:
            self.fields[name] = EvidenceValue(value=value, **kwargs)
        return self

    def set_context(self, path: str, value: Any) -> "Evidence":
        tokens = _split_path(path)
        target = self.context
        for tok in tokens[:-1]:
            if isinstance(tok, int):
                while len(target) <= tok:
                    target.append({})
                target = target[tok]
            else:
                target = target.setdefault(tok, {})
        last = tokens[-1]
        if isinstance(last, int):
            while len(target) <= last:
                target.append(None)
            target[last] = value
        else:
            target[last] = value
        return self

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def get_evidence_value(self, field_name: str) -> Optional[EvidenceValue]:
        return self.fields.get(field_name)

    def resolve(self, path: str) -> Any:
        """
        Resolve a dot-path reference against fields first, then context.

        Returns ``MISSING`` (not None) if nothing exists at that path, so
        callers can distinguish "explicitly null" from "not present".
        Supports referencing an EvidenceValue's own attribute (``.value``,
        ``.confidence``, ``.unit``, ``.present``) via a trailing segment.
        """
        if path in self.fields:
            return self.fields[path].value

        tokens = _split_path(path)
        if not tokens:
            return MISSING

        head = tokens[0]
        rest = tokens[1:]

        if isinstance(head, str) and head in self.fields:
            ev = self.fields[head]
            if not rest:
                return ev.value
            attr = rest[0]
            if attr in {"value", "normalized_value", "unit", "confidence", "present", "usable",
                        "source_text", "source_page", "source_region", "image_id", "bbox",
                        "provenance", "verification_status", "quality_state",
                        "alternatives", "notes"}:
                if attr == "present":
                    base = ev.is_present()
                elif attr == "usable":
                    base = ev.is_usable()
                else:
                    base = getattr(ev, attr)
                if len(rest) == 1:
                    return base
                return _walk(base, rest[1:])
            return _walk(ev.value, rest)

        if isinstance(head, str) and head == "context":
            return _walk(self.context, rest)

        if isinstance(head, str) and head in self.context:
            val = self.context[head]
            if not rest:
                return val
            return _walk(val, rest)

        return MISSING

    def has(self, path: str) -> bool:
        return self.resolve(path) is not MISSING

    def get(self, path: str, default: Any = None) -> Any:
        val = self.resolve(path)
        return default if val is MISSING else val


def _walk(node: Any, tokens: List[Any]) -> Any:
    current = node
    for tok in tokens:
        if current is MISSING or current is None:
            return MISSING
        if isinstance(tok, int):
            if isinstance(current, (list, tuple)) and 0 <= tok < len(current):
                current = current[tok]
            else:
                return MISSING
        else:
            if isinstance(current, dict) and tok in current:
                current = current[tok]
            elif hasattr(current, tok):
                current = getattr(current, tok)
            else:
                return MISSING
    return current
