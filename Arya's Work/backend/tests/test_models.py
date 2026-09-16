from lexmetra_rules.models import (
    ClassificationResult,
    EffectiveDates,
    ExtractedRule,
    HeadingCandidate,
    PageText,
    ReviewStatus,
    SourceLocation,
    TextSource,
)


def _make_minimal_rule(**overrides) -> ExtractedRule:
    defaults = dict(
        rule_id="3",
        source="Test Regulation",
        document_id="doc-1",
        text="3. Some rule text.",
        source_location=SourceLocation(document_id="doc-1", page_start=1, page_end=1),
    )
    defaults.update(overrides)
    return ExtractedRule(**defaults)


def test_extracted_rule_minimal_construction():
    rule = _make_minimal_rule()
    assert rule.rule_id == "3"
    assert rule.review_status == ReviewStatus.NEEDS_REVIEW  # safe default
    assert rule.conditions == []
    assert rule.requirements == []
    assert rule.classification.categories == []


def test_extracted_rule_rejects_unknown_fields():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtractedRule(
            rule_id="3",
            source="Test",
            document_id="doc-1",
            text="text",
            source_location=SourceLocation(document_id="doc-1", page_start=1, page_end=1),
            made_up_field="should not be allowed",
        )


def test_page_text_defaults_to_none_source():
    page = PageText(page_no=1)
    assert page.source == TextSource.NONE
    assert page.confidence == 0.0


def test_heading_candidate_round_trip():
    candidate = HeadingCandidate(
        raw_number="6",
        page_no=3,
        line_index=0,
        line_text="6. Declarations on every package.",
        accepted=True,
        confidence=0.9,
        reasons=["matches pattern"],
    )
    dumped = candidate.model_dump()
    restored = HeadingCandidate(**dumped)
    assert restored == candidate


def test_classification_result_json_shape_matches_brief():
    result = ClassificationResult(
        categories=["GENERAL", "FOOD"],
        confidence=0.82,
        signals={"GENERAL": ["package"], "FOOD": ["food"]},
        review_status=ReviewStatus.NEEDS_REVIEW,
    )
    dumped = result.model_dump()
    assert dumped["categories"] == ["GENERAL", "FOOD"]
    assert dumped["signals"]["FOOD"] == ["food"]
    assert dumped["review_status"] == "needs_review"


def test_effective_dates_all_optional():
    dates = EffectiveDates()
    assert dates.effective_from is None
    assert dates.effective_to is None
