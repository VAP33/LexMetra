import pytest

from lexmetra_rules.models import ReviewStatus, SourceLocation
from lexmetra_rules.pipeline import run_pipeline_from_pages
from lexmetra_rules.review import apply_reviewer_correction


def test_high_confidence_rule_is_auto_accepted(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    rule_4 = next(r for r in result.rules if r.rule_id == "4")
    assert rule_4.review_status == ReviewStatus.AUTO_ACCEPTED


def test_rule_with_validation_warning_is_not_auto_accepted(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    # Rule 3 has an unbound-threshold validation warning (see
    # test_semantic_extraction_v2.py) and must not be silently
    # auto-accepted despite otherwise-solid classification signal.
    rule_3 = next(r for r in result.rules if r.rule_id == "3")
    assert len(rule_3.validation_warnings) > 0
    assert rule_3.review_status != ReviewStatus.AUTO_ACCEPTED


def test_reviewer_correction_creates_new_object_without_mutating_original(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    original = next(r for r in result.rules if r.rule_id == "3")
    original_snapshot = original.model_copy(deep=True)

    record = apply_reviewer_correction(
        original,
        {"title": "Corrected title", "subcategory": "small_pack"},
        reviewer="reviewer@example.com",
        rule_key="doc-1:3",
    )

    # Original object must be untouched.
    assert original == original_snapshot
    assert record.system_extraction == original_snapshot
    assert record.corrected_rule.title == "Corrected title"
    assert record.corrected_rule.subcategory == "small_pack"
    assert record.corrected_rule.review_status == ReviewStatus.AUTO_ACCEPTED
    assert record.corrected_fields == ["subcategory", "title"]
    assert record.corrected_by == "reviewer@example.com"


def test_reviewer_correction_requires_reviewer_identity(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    rule = result.rules[0]
    with pytest.raises(ValueError):
        apply_reviewer_correction(rule, {"title": "x"}, reviewer="", rule_key="k")


def test_reviewer_correction_rejects_unknown_field(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    rule = result.rules[0]
    with pytest.raises(ValueError):
        apply_reviewer_correction(rule, {"not_a_real_field": "x"}, reviewer="r", rule_key="k")


def test_reviewer_correction_requires_at_least_one_change(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    rule = result.rules[0]
    with pytest.raises(ValueError):
        apply_reviewer_correction(rule, {}, reviewer="r", rule_key="k")
