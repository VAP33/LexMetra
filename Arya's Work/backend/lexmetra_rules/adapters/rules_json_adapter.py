"""
Adapter: ``ExtractedRule`` -> a dict shaped like the existing LexMetra
``rules/rules.json`` entries.

This is a PREVIEW / export projection, not the primary integration target
(see ``regulatory_model_adapter.py`` for that, and the project README for
why). It exists so a reviewer can see, side by side, what a fully-approved
version of this rule would look like in the existing flat schema — but it
deliberately leaves several fields empty/None rather than guessing values
the existing rule engine actually depends on (see inline comments), because
guessing here would be worse than an honest gap:

  - ``condition.expression`` is NOT populated. The existing engine's
    condition vocabulary (``_CONDITION_CONTEXT_KEYS`` in
    ``backend/rule_engine.py``) is a small, closed, hand-maintained table.
    Auto-writing an expression string risks silently colliding with or
    duplicating that table. We surface ``condition_text``/``condition_type``
    instead, for a human to wire in deliberately.
  - ``threshold`` is NOT populated with the existing rule-specific nested
    key names (e.g. ``small_pack_upper_bound.weight_g_lte``) because those
    names are rule-specific, not a formula from (value, unit, operator).
    We surface the uniform ``thresholds_extracted`` list instead.
  - ``applies_to.product_category`` is NOT set from ``category`` directly:
    the existing field's vocabulary
    ({"all","soft_drink","drug_formulation","scheduled_commodities",
    "like_commodity","ready_to_serve_fruit_beverage","fast_food"}) is a
    narrower exemption-scoping vocabulary, not the
    GENERAL/FOOD/COSMETICS/... domain taxonomy this module produces. A
    best-effort lowercased mapping is offered in
    ``suggested_applies_to_product_category``, clearly marked as
    non-authoritative.
"""

from __future__ import annotations

from typing import Any, Dict

from ..models import ExtractedRule

#: Best-effort, NON-authoritative lowercase mapping hint only — never
#: written into `applies_to.product_category` directly.
_CATEGORY_TO_EXISTING_HINT = {
    "SOFT_DRINK": "soft_drink",
    "DRUGS": "drug_formulation",
}


def to_rules_json_dict(rule: ExtractedRule) -> Dict[str, Any]:
    suggested_category_hints = [
        _CATEGORY_TO_EXISTING_HINT[c]
        for c in rule.classification.categories
        if c in _CATEGORY_TO_EXISTING_HINT
    ]

    return {
        "rule_id": rule.rule_id,
        "source": rule.source,
        "clause": rule.rule_id,
        "version": rule.version,
        "effective_from": rule.effective_dates.effective_from,
        "effective_to": rule.effective_dates.effective_to,
        "rule_type": None,  # existing engine's rule_type -> evaluator dispatch key; not inferable here
        "category": rule.classification.categories,          # NEW field, additive (see module docstring)
        "subcategory": rule.subcategory,
        "applies_to": {
            "product_category": [],  # left empty deliberately; see module docstring
            "sale_type": [],
        },
        "suggested_applies_to_product_category_hints": suggested_category_hints,
        "scope": rule.scope,
        "condition": None,  # left empty deliberately; see module docstring
        "condition_text_extracted": [c.condition_text for c in rule.conditions],
        "requirements": [
            {
                "id": r.id,
                "description": r.description,
                "suggested_field": r.suggested_field,
            }
            for r in rule.requirements
        ],
        "threshold": None,  # left empty deliberately; see module docstring
        "thresholds_extracted": [
            {
                "value": t.value, "unit": t.unit, "operator": t.operator,
                "applies_to": t.label, "source_text": t.source_text,
            }
            for t in rule.thresholds
        ],
        "evidence_required": rule.evidence_required,
        "exemptions": [e.description for e in rule.exemptions],
        "exclusions": [],
        "decision": {"pass_when": None, "exempt_when": None, "uncertain_when": None},
        "verification_status": "needs_official_verification",
        "legal_note": None,
        "source_location": {
            "page_start": rule.source_location.page_start,
            "page_end": rule.source_location.page_end,
        },
        # NEW (semantic extraction v2): the full clause-level breakdown,
        # for consumers that want relationship-bound detail rather than
        # just the flattened legacy lists above.
        "clauses": [
            {
                "clause_id": c.clause_id,
                "parent_clause_id": c.parent_clause_id,
                "clause_type": c.clause_type.value,
                "semantic_role": c.semantic_role.value,
                "role_confidence": c.role_confidence,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "source_text": c.source_text,
                "thresholds": [
                    {
                        "value": t.value, "unit": t.unit, "operator": t.operator,
                        "applies_to": t.applies_to, "source_text": t.source_text,
                    }
                    for t in c.thresholds
                ],
                "confidence": c.confidence,
                "review_status": c.review_status.value,
                "validation_errors": c.validation_errors,
                "validation_warnings": c.validation_warnings,
            }
            for c in rule.clauses
        ],
        "validation_errors": rule.validation_errors,
        "validation_warnings": rule.validation_warnings,
        "extraction_confidence": rule.extraction_confidence,
        "review_status": rule.review_status.value,
        "review_reasons": rule.review_reasons,
        # Amendment identity — kept strictly separate from rule_id
        # (rule_id = positional id in amending document, e.g. "Rule 2(a)(i)")
        # amendment_target = canonical rule being amended, e.g. "Rule 6(1)(a)"
        # amendment_item   = ordinal marker in amending document, e.g. "(i)"
        "amendment_target": rule.amendment_target,
        "amendment_item": rule.amendment_item,
    }
