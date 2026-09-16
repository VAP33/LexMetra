"""
Evidence-required derivation.

Deliberately NOT independent extraction: evidence_required is derived only
from what conditions.py / requirements.py already found in this rule, in
the same "field:<name>" token style already used by the existing LexMetra
``rules.json`` (e.g. "field:net_quantity"). This avoids the trap called out
in the brief: confusing "what the regulation requires" (this module) with
"what product evidence is currently available" (Module 4's job, not
Module 1's).
"""

from __future__ import annotations

from typing import List

from ..models import ExtractionCondition, ExtractionRequirement


def derive_evidence_required(
    requirements: List[ExtractionRequirement],
    conditions: List[ExtractionCondition],
) -> List[str]:
    tokens: List[str] = []
    seen = set()

    for req in requirements:
        if req.suggested_field:
            token = f"field:{req.suggested_field}"
            if token not in seen:
                seen.add(token)
                tokens.append(token)

    for cond in conditions:
        if cond.condition_type and cond.condition_type not in seen:
            seen.add(cond.condition_type)
            tokens.append(cond.condition_type)

    return tokens
