"""
Adapter: a list of ``ExtractedRule`` -> a dict shaped like
``backend/models.py``'s ``AmendmentDraft`` (containing ``RuleVersion``-shaped
proposed versions).

This is the PRIMARY integration target (see README "Compatibility"): the
existing LexMetra project already has an approval-gated pipeline built for
exactly this handoff (``ApprovalState.DRAFT -> EXTRACTED -> AI_PARSED ->
PENDING_REVIEW -> APPROVED -> SCHEDULED -> ACTIVE``). Module 1's job ends at
producing a draft in the ``EXTRACTED`` state; it never proposes ``APPROVED``
or ``ACTIVE`` — that transition is a human decision made through the
existing review workflow, not something this module can or should do.

The returned dict is plain data (dicts/lists/strings), matching the field
names of ``RuleVersion`` / ``AmendmentDraft`` / ``AmendmentChange`` closely
enough that integration code can construct those Pydantic models directly
via ``RuleVersion(**version_dict)`` with no further transformation for the
fields that exist in both. Fields unique to this module's richer extraction
(classification signals, confidence, review reasons, source location) are
carried alongside under ``extraction_metadata`` rather than invented into
the existing model, since ``RuleVersion`` has no such fields today.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from ..models import ExtractedRule
from ..provision_classification import classify_amendment_operation


def _rule_to_version_dict(
    rule: ExtractedRule,
    module: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta = metadata or {}
    reg = meta.get("regulation") or rule.source
    ver = rule.version or meta.get("version_label") or meta.get("amendment_name")
    eff_from = rule.effective_dates.effective_from or meta.get("effective_date")

    conditions_dict: Dict[str, Any] = {
        "extracted_text": [c.condition_text for c in rule.conditions],
        "extracted_types": [c.condition_type for c in rule.conditions if c.condition_type],
    }
    if meta.get("substantive_trigger_date"):
        conditions_dict["substantive_trigger_date"] = meta["substantive_trigger_date"]
    if meta.get("substantive_trigger_scope"):
        conditions_dict["substantive_trigger_scope"] = meta["substantive_trigger_scope"]
    if meta.get("applicability_duration"):
        conditions_dict["applicability_duration"] = meta["applicability_duration"]

    applicability_dict: Dict[str, Any] = {}
    if meta.get("substantive_trigger_date"):
        applicability_dict["manufactured_packed_imported_after"] = meta["substantive_trigger_date"]
    if meta.get("applicability_duration"):
        applicability_dict["duration"] = meta["applicability_duration"]
    if meta.get("substantive_trigger_scope"):
        applicability_dict["scope"] = meta["substantive_trigger_scope"]

    # Calculate distinct applicability_end_date without collapsing dates
    if meta.get("substantive_trigger_date") and meta.get("applicability_duration"):
        dur = str(meta["applicability_duration"]).lower()
        if "1 year" in dur or "one year" in dur:
            try:
                trig = date.fromisoformat(str(meta["substantive_trigger_date"])[:10])
                end_d = date(trig.year + 1, trig.month, trig.day)
                applicability_dict["applicability_end_date"] = end_d.isoformat()
                conditions_dict["applicability_end_date"] = end_d.isoformat()
            except Exception:
                pass

    if applicability_dict:
        conditions_dict["applicability"] = applicability_dict

    if meta.get("notification_number"):
        conditions_dict["notification_number"] = meta["notification_number"]
    if rule.source_provision:
        conditions_dict["source_provision"] = rule.source_provision
    if rule.amendment_target:
        conditions_dict["amendment_target"] = rule.amendment_target
    if rule.amendment_item:
        conditions_dict["amendment_item"] = rule.amendment_item
    op_type = classify_amendment_operation(rule.text)
    conditions_dict["amendment_operation"] = op_type
    if meta.get("commencement_source_provision"):
        conditions_dict["commencement_source_provision"] = meta["commencement_source_provision"]
    if rule.metadata_sources:
        conditions_dict["metadata_sources"] = rule.metadata_sources

    has_hindi = bool(rule.raw_ocr_text and "[HINDI TEXT]" in rule.raw_ocr_text)
    source_langs = ["hi", "en"] if has_hindi else ["en"]


    return {
        "id": None,  # assigned by the existing regulatory store on ingest, not by Module 1
        "module": module,
        "regulation": reg,
        "rule_id": rule.rule_id,
        "version": ver,
        "effective_from": eff_from,
        "effective_to": rule.effective_dates.effective_to,
        "approval_state": "EXTRACTED",
        "source_document_id": rule.document_id,
        "source_url": None,
        "conditions": conditions_dict,
        "thresholds": [
            {"value": t.value, "unit": t.unit, "operator": t.operator, "source_text": t.source_text}
            for t in rule.thresholds
        ],
        "evidence_requirements": [
            {
                "id": r.id,
                "field": r.suggested_field,
                "description": r.description,
                "condition": r.condition_ref,
                "required": True,
            }
            for r in rule.requirements
        ],
        "text": rule.text,
        # Additive metadata not present on the existing RuleVersion model;
        # kept alongside for reviewer visibility rather than lost.
        "extraction_metadata": {
            "title": rule.title,
            "categories": rule.classification.categories,
            "classification_confidence": rule.classification.confidence,
            "classification_signals": rule.classification.signals,
            "exemptions": [e.description for e in rule.exemptions],
            "evidence_required_tokens": rule.evidence_required,
            "source_location": {
                "document_id": rule.source_location.document_id,
                "page_start": rule.source_location.page_start,
                "page_end": rule.source_location.page_end,
                "clause": rule.source_location.clause,
            },
            "source_languages": source_langs,
            "source_provision": rule.source_provision,
            "provision_type": rule.provision_type.value if rule.provision_type else "SUBSTANTIVE_AMENDMENT",
            "is_substantive": rule.is_substantive,
            "metadata_sources": rule.metadata_sources,
            "extraction_confidence": rule.extraction_confidence,
            "review_status": rule.review_status.value,
            "review_reasons": rule.review_reasons,

            # NEW (semantic extraction v2): validation results and the
            # relationship-bound clause breakdown, so a reviewer approving
            # this RuleVersion can see exactly which clause supports each
            # threshold/requirement/exception before it goes ACTIVE.
            "validation_errors": rule.validation_errors,
            "validation_warnings": rule.validation_warnings,
            "clauses": [
                {
                    "clause_id": c.clause_id,
                    "parent_clause_id": c.parent_clause_id,
                    "clause_type": c.clause_type.value,
                    "semantic_role": c.semantic_role.value,
                    "role_confidence": c.role_confidence,
                    "confidence": c.confidence,
                    "review_status": c.review_status.value,
                    "thresholds": [
                        {
                            "value": t.value, "unit": t.unit, "operator": t.operator,
                            "applies_to": t.applies_to, "clause_id": t.clause_id,
                            "source_text": t.source_text, "page": t.page,
                        }
                        for t in c.thresholds
                    ],
                    "validation_errors": c.validation_errors,
                    "validation_warnings": c.validation_warnings,
                }
                for c in rule.clauses
            ],
        },
    }


def to_amendment_draft(
    rules: List[ExtractedRule],
    *,
    source_document_id: str,
    module: str = "lmpc",
    draft_id: str | None = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build an AmendmentDraft-shaped dict from a batch of extracted rules.

    ``approval_state`` is fixed at "EXTRACTED" for the draft and every
    proposed rule version within it — this module never proposes
    "APPROVED" or "ACTIVE".
    """
    meta = metadata or {}
    changes = [
        {
            "rule_id": rule.rule_id,
            "change_type": classify_amendment_operation(rule.text),  # deterministic keyword detection
            "old_text": None,
            "new_text": rule.text,
            "effective_from": rule.effective_dates.effective_from or meta.get("effective_date"),
            "threshold_changes": [],
            "applicability_changes": [],
            "changed_fields": [],
        }
        for rule in rules
    ]

    impact: Dict[str, Any] = {
        "rule_count": len(rules),
        "needs_review_count": sum(1 for r in rules if r.review_status.value != "auto_accepted"),
    }
    if meta:
        impact["amendment_metadata"] = meta
        if meta.get("regulation"):
            impact["regulation"] = meta["regulation"]
        if meta.get("amendment_name"):
            impact["amendment"] = meta["amendment_name"]
            impact["amendment_name"] = meta["amendment_name"]
        if meta.get("year"):
            impact["year"] = meta["year"]
        if meta.get("notification_number"):
            impact["notification"] = meta["notification_number"]
            impact["notification_number"] = meta["notification_number"]
        if meta.get("gazette_date"):
            impact["gazette_date"] = meta["gazette_date"]
        if meta.get("effective_date"):
            impact["effective_date"] = meta["effective_date"]
        if meta.get("substantive_trigger_date"):
            impact["substantive_trigger_date"] = meta["substantive_trigger_date"]
        if meta.get("substantive_trigger_scope"):
            impact["substantive_trigger_scope"] = meta["substantive_trigger_scope"]

    return {
        "id": draft_id,
        "module": module,
        "source_document_id": source_document_id,
        "approval_state": "EXTRACTED",
        "extracted_at": None,  # set by the caller/integration layer at ingest time
        "changes": changes,
        "proposed_rule_versions": [_rule_to_version_dict(r, module, metadata=meta) for r in rules],
        "impact": impact,
    }


# ---------------------------------------------------------------------------
# Per-operation amendment materialisation
# ---------------------------------------------------------------------------
# Maps a single ExtractedRule (with its amendment_target, amendment_item,
# change_type) to the correct set of AmendmentChange + RuleVersion payloads.
#
# Operation semantics:
#   INSERT     → one new RuleVersion for the inserted provision;
#                amendment_target is recorded as the legal parent;
#                nothing is closed (old text is untouched).
#   REMOVE     → one AmendmentChange closing the existing provision
#                (sets effective_to = amendment effective date).
#                No new RuleVersion — the historical one is the evidence.
#   SUBSTITUTE → one AmendmentChange (old → new text) +
#                one new RuleVersion with the replacement text.
#   NEW_RULE   → one new RuleVersion whose rule_id = amendment_target
#                (the completely new rule, not just a sub-clause insertion).
#
# Returns a dict with keys:
#   "changes"               list[dict]  — AmendmentChange-shaped dicts
#   "proposed_rule_versions" list[dict]  — RuleVersion-shaped dicts
#   "operation"             str         — the detected operation label

def build_amendment_change_for_operation(
    rule: ExtractedRule,
    *,
    module: str = "unknown",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Materialise the correct AmendmentChange + RuleVersion payloads for the
    amendment operation encoded in *rule*.

    Parameters
    ----------
    rule:
        An ``ExtractedRule`` that has been processed through the amendment
        pipeline, i.e. ``rule.amendment_target`` and ``rule.amendment_item``
        are populated, and ``classify_amendment_operation(rule.text)`` returns
        a non-UNKNOWN label.
    module:
        Regulatory module identifier (e.g. ``"lmpc"``, ``"fssai"``).
    metadata:
        Optional ambient metadata dict (same shape as used by
        ``to_amendment_draft``).

    Returns
    -------
    dict with keys:
        ``"operation"``              — ``"INSERT" | "REMOVE" | "SUBSTITUTE" | "NEW_RULE" | "UNKNOWN"``
        ``"changes"``                — list of AmendmentChange-shaped dicts
        ``"proposed_rule_versions"`` — list of RuleVersion-shaped dicts
    """
    meta = metadata or {}
    operation = classify_amendment_operation(rule.text)
    eff_from = rule.effective_dates.effective_from or meta.get("effective_date")
    target = rule.amendment_target  # e.g. "Rule 6(1)(a)", or None
    item = rule.amendment_item      # e.g. "(i)", or None

    # Shared base for every AmendmentChange
    base_change: Dict[str, Any] = {
        "rule_id": target or rule.rule_id,
        "change_type": operation,
        "old_text": None,
        "new_text": rule.text,
        "effective_from": eff_from,
        "threshold_changes": [],
        "applicability_changes": [],
        "changed_fields": [],
    }

    if operation == "INSERT":
        # Create a new canonical RuleVersion for the inserted provision.
        # rule_id = amendment_target so it lands under the correct parent rule.
        version_dict = _rule_to_version_dict(rule, module, metadata=meta)
        version_dict["rule_id"] = target or rule.rule_id
        version_dict["extraction_metadata"]["amendment_item"] = item
        version_dict["extraction_metadata"]["amendment_operation"] = "INSERT"
        version_dict["extraction_metadata"]["amendment_target"] = target
        return {
            "operation": "INSERT",
            "changes": [base_change],
            "proposed_rule_versions": [version_dict],
        }

    elif operation == "REMOVE":
        # Close the existing provision: set effective_to on the AmendmentChange.
        # No new RuleVersion is produced — the historical version IS the evidence.
        removal_change = dict(base_change)
        removal_change["new_text"] = None          # nothing is being added
        removal_change["effective_to"] = eff_from  # provision ceases on this date
        removal_change["changed_fields"] = ["effective_to", "status"]
        removal_change["extraction_metadata"] = {
            "amendment_item": item,
            "amendment_operation": "REMOVE",
            "amendment_target": target,
            "source_provision": rule.source_provision,
        }
        return {
            "operation": "REMOVE",
            "changes": [removal_change],
            "proposed_rule_versions": [],  # no new version — old one is closed by effective_to
        }

    elif operation == "SUBSTITUTE":
        # Produce both the closing change (old text → None) and a new
        # RuleVersion with the replacement text.
        sub_change = dict(base_change)
        sub_change["old_text"] = None  # populated by the integration layer when it
                                        # looks up the current ACTIVE version in its store
        sub_change["changed_fields"] = ["text"]
        sub_change["extraction_metadata"] = {
            "amendment_item": item,
            "amendment_operation": "SUBSTITUTE",
            "amendment_target": target,
        }

        version_dict = _rule_to_version_dict(rule, module, metadata=meta)
        version_dict["rule_id"] = target or rule.rule_id
        version_dict["extraction_metadata"]["amendment_item"] = item
        version_dict["extraction_metadata"]["amendment_operation"] = "SUBSTITUTE"
        version_dict["extraction_metadata"]["amendment_target"] = target
        return {
            "operation": "SUBSTITUTE",
            "changes": [sub_change],
            "proposed_rule_versions": [version_dict],
        }

    elif operation == "NEW_RULE":
        # The amendment introduces an entirely new top-level rule.
        # rule_id = amendment_target because that IS the new rule's canonical id.
        version_dict = _rule_to_version_dict(rule, module, metadata=meta)
        new_rule_id = target or rule.rule_id
        version_dict["rule_id"] = new_rule_id
        version_dict["extraction_metadata"]["amendment_item"] = item
        version_dict["extraction_metadata"]["amendment_operation"] = "NEW_RULE"
        version_dict["extraction_metadata"]["amendment_target"] = target

        new_change = dict(base_change)
        new_change["rule_id"] = new_rule_id

        return {
            "operation": "NEW_RULE",
            "changes": [new_change],
            "proposed_rule_versions": [version_dict],
        }

    else:  # UNKNOWN
        version_dict = _rule_to_version_dict(rule, module, metadata=meta)
        version_dict["extraction_metadata"]["amendment_operation"] = "UNKNOWN"
        return {
            "operation": "UNKNOWN",
            "changes": [base_change],
            "proposed_rule_versions": [version_dict],
        }