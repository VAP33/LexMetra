"""
test_amendment_operation_materialisation.py

Four focused tests for build_amendment_change_for_operation().

Each test covers one operation type and verifies the correct
AmendmentChange + RuleVersion materialisation semantics:

  INSERT    → new RuleVersion with rule_id = amendment_target
  REMOVE    → AmendmentChange with effective_to set; no new RuleVersion
  SUBSTITUTE → new RuleVersion; change records old_text slot + changed_fields
  NEW_RULE  → new RuleVersion with rule_id = amendment_target (top-level)
"""
from datetime import date

import pytest

from lexmetra_rules.adapters.regulatory_model_adapter import (
    build_amendment_change_for_operation,
)
from lexmetra_rules.models import (
    ClassificationResult,
    EffectiveDates,
    ExtractedRule,
    SourceLocation,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_rule(
    rule_id: str,
    text: str,
    *,
    amendment_target: str | None = None,
    amendment_item: str | None = None,
    effective_from: date | None = date(2022, 7, 15),
) -> ExtractedRule:
    return ExtractedRule(
        rule_id=rule_id,
        title=rule_id,
        source="Test Regulation 2022",
        document_id="doc-001",
        text=text,
        source_location=SourceLocation(
            document_id="doc-001",
            page_start=1,
            page_end=1,
            clause=rule_id,
        ),
        effective_dates=EffectiveDates(
            effective_from=effective_from.isoformat() if effective_from else None
        ),
        amendment_target=amendment_target,
        amendment_item=amendment_item,
    )


# ---------------------------------------------------------------------------
# Test 1: INSERT
# ---------------------------------------------------------------------------

def test_insert_produces_new_rule_version_linked_to_target():
    """INSERT: creates a new RuleVersion; rule_id = amendment_target; no old text."""
    rule = _make_rule(
        rule_id="Rule 2(a)(i)",
        text=(
            "In rule 6, in sub-rule (1), in clause (a), after the existing proviso, "
            "the following proviso shall be inserted, namely:- "
            "\"Provided further that electronic products manufactured on or after "
            "15th July 2022 shall bear the mandatory declarations.\""
        ),
        amendment_target="Rule 6(1)(a)",
        amendment_item="(i)",
    )

    result = build_amendment_change_for_operation(rule, module="test_module")

    assert result["operation"] == "INSERT"

    # One AmendmentChange
    assert len(result["changes"]) == 1
    change = result["changes"][0]
    assert change["change_type"] == "INSERT"
    assert change["rule_id"] == "Rule 6(1)(a)"      # points at target, not amendment item
    assert change["new_text"] is not None            # the inserted text is carried

    # One new RuleVersion
    assert len(result["proposed_rule_versions"]) == 1
    rv = result["proposed_rule_versions"][0]
    assert rv["rule_id"] == "Rule 6(1)(a)"           # canonical target, not "Rule 2(a)(i)"
    assert rv["extraction_metadata"]["amendment_operation"] == "INSERT"
    assert rv["extraction_metadata"]["amendment_target"] == "Rule 6(1)(a)"
    assert rv["extraction_metadata"]["amendment_item"] == "(i)"


# ---------------------------------------------------------------------------
# Test 2: REMOVE
# ---------------------------------------------------------------------------

def test_remove_closes_provision_with_no_new_version():
    """REMOVE: AmendmentChange has effective_to set; no new RuleVersion produced."""
    rule = _make_rule(
        rule_id="Rule 3(b)",
        text="In rule 3, clause (b) shall be omitted.",
        amendment_target="Rule 3(b)",
        amendment_item="(b)",
        effective_from=date(2023, 1, 1),
    )

    result = build_amendment_change_for_operation(rule, module="test_module")

    assert result["operation"] == "REMOVE"

    # One AmendmentChange with effective_to
    assert len(result["changes"]) == 1
    change = result["changes"][0]
    assert change["change_type"] == "REMOVE"
    assert change["rule_id"] == "Rule 3(b)"
    assert change["new_text"] is None                # nothing new — provision is gone
    assert change["effective_to"] is not None        # closure date is set
    assert "effective_to" in change["changed_fields"]

    # No new RuleVersion — historical evidence is preserved in the existing store
    assert result["proposed_rule_versions"] == []


# ---------------------------------------------------------------------------
# Test 3: SUBSTITUTE
# ---------------------------------------------------------------------------

def test_substitute_produces_new_version_and_change_record():
    """SUBSTITUTE: new RuleVersion with replacement text; change records field update."""
    rule = _make_rule(
        rule_id="Rule 2(a)(iii)",
        text=(
            "In rule 6, in sub-rule (1), in clause (f), for the figures "
            "\"500 g\" and \"200 g\", the figures \"1 kg\" and \"500 g\" "
            "shall be substituted."
        ),
        amendment_target="Rule 6(1)(f)",
        amendment_item="(iii)",
    )

    result = build_amendment_change_for_operation(rule, module="test_module")

    assert result["operation"] == "SUBSTITUTE"

    # One AmendmentChange
    assert len(result["changes"]) == 1
    change = result["changes"][0]
    assert change["change_type"] == "SUBSTITUTE"
    assert change["rule_id"] == "Rule 6(1)(f)"
    assert "text" in change["changed_fields"]

    # One new RuleVersion carrying the replacement text
    assert len(result["proposed_rule_versions"]) == 1
    rv = result["proposed_rule_versions"][0]
    assert rv["rule_id"] == "Rule 6(1)(f)"           # canonical target
    assert rv["extraction_metadata"]["amendment_operation"] == "SUBSTITUTE"
    assert rv["text"] is not None                    # replacement text is present


# ---------------------------------------------------------------------------
# Test 4: NEW_RULE
# ---------------------------------------------------------------------------

def test_new_rule_creates_standalone_canonical_rule():
    """NEW_RULE: entirely new canonical rule; rule_id = amendment_target."""
    rule = _make_rule(
        rule_id="Rule 5",
        text=(
            "After rule 4, the following new rule shall be inserted, namely:- "
            "\"Rule 4A. Records.— Every manufacturer shall maintain records of "
            "each lot of packaged commodity for a minimum period of three years.\""
        ),
        amendment_target="Rule 4A",
        amendment_item="Rule 5",
    )

    result = build_amendment_change_for_operation(rule, module="test_module")

    assert result["operation"] == "NEW_RULE"

    # One AmendmentChange
    assert len(result["changes"]) == 1
    change = result["changes"][0]
    assert change["change_type"] == "NEW_RULE"
    assert change["rule_id"] == "Rule 4A"            # the new rule's canonical id

    # One new RuleVersion with its own canonical rule_id
    assert len(result["proposed_rule_versions"]) == 1
    rv = result["proposed_rule_versions"][0]
    assert rv["rule_id"] == "Rule 4A"                # standalone, not "Rule 5"
    assert rv["extraction_metadata"]["amendment_operation"] == "NEW_RULE"
    assert rv["extraction_metadata"]["amendment_target"] == "Rule 4A"
