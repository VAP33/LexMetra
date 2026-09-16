from lexmetra_rules.adapters import to_amendment_draft, to_rules_json_dict
from lexmetra_rules.pipeline import run_pipeline_from_pages


def _rules(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    return result.rules


def test_rules_json_adapter_produces_expected_top_level_keys(synthetic_pages):
    rule = _rules(synthetic_pages)[3]  # rule 4, food
    dumped = to_rules_json_dict(rule)
    expected_keys = {
        "rule_id", "source", "clause", "version", "effective_from", "effective_to",
        "rule_type", "category", "subcategory", "applies_to", "scope", "condition",
        "requirements", "threshold", "evidence_required", "exemptions", "exclusions",
        "decision", "verification_status", "legal_note", "source_location",
    }
    assert expected_keys.issubset(dumped.keys())


def test_rules_json_adapter_never_writes_condition_expression(synthetic_pages):
    """condition.expression belongs to the existing engine's closed
    vocabulary and must never be auto-populated (see adapter docstring)."""
    for rule in _rules(synthetic_pages):
        dumped = to_rules_json_dict(rule)
        assert dumped["condition"] is None


def test_rules_json_adapter_never_writes_engine_threshold_keys(synthetic_pages):
    for rule in _rules(synthetic_pages):
        dumped = to_rules_json_dict(rule)
        assert dumped["threshold"] is None


def test_rules_json_adapter_default_verification_status_is_needs_official_verification(synthetic_pages):
    for rule in _rules(synthetic_pages):
        dumped = to_rules_json_dict(rule)
        assert dumped["verification_status"] == "needs_official_verification"


def test_rules_json_adapter_carries_category_as_new_field(synthetic_pages):
    rule = _rules(synthetic_pages)[3]
    dumped = to_rules_json_dict(rule)
    assert dumped["category"] == rule.classification.categories
    # And it must not have overwritten the narrower existing field's list.
    assert dumped["applies_to"]["product_category"] == []


def test_amendment_draft_adapter_fixes_approval_state_to_extracted(synthetic_pages):
    rules = _rules(synthetic_pages)
    draft = to_amendment_draft(rules, source_document_id="doc-1")
    assert draft["approval_state"] == "EXTRACTED"
    assert all(v["approval_state"] == "EXTRACTED" for v in draft["proposed_rule_versions"])


def test_amendment_draft_never_proposes_active_or_approved(synthetic_pages):
    rules = _rules(synthetic_pages)
    draft = to_amendment_draft(rules, source_document_id="doc-1")
    all_states = [draft["approval_state"]] + [v["approval_state"] for v in draft["proposed_rule_versions"]]
    assert "ACTIVE" not in all_states
    assert "APPROVED" not in all_states


def test_amendment_draft_preserves_rule_count_and_review_impact(synthetic_pages):
    rules = _rules(synthetic_pages)
    draft = to_amendment_draft(rules, source_document_id="doc-1")
    assert draft["impact"]["rule_count"] == len(rules)
    assert draft["impact"]["needs_review_count"] <= len(rules)


def test_amendment_draft_rule_version_shape_matches_expected_fields(synthetic_pages):
    rules = _rules(synthetic_pages)
    draft = to_amendment_draft(rules, source_document_id="doc-1")
    version = draft["proposed_rule_versions"][0]
    expected = {
        "id", "module", "regulation", "rule_id", "version", "effective_from",
        "effective_to", "approval_state", "source_document_id", "source_url",
        "conditions", "thresholds", "evidence_requirements", "text",
    }
    assert expected.issubset(version.keys())
