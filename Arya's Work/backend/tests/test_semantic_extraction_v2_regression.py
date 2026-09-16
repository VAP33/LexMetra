"""
Regression tests directly mirroring "Test against the current failure
cases" from the semantic-extraction-upgrade brief, items A-F.
"""

from lexmetra_rules.models import ReviewStatus
from lexmetra_rules.pipeline import run_pipeline_from_pages
from tests.fixtures.semantic_v2_regression_text import make_clean_pages, make_ocr_degraded_pages


def _rule(result, rule_id):
    return next(r for r in result.rules if r.rule_id == rule_id)


def test_A_rule1_commencement_date_identified_as_effective_date():
    result = run_pipeline_from_pages(make_clean_pages(), document_id="doc-1", source="Test Reg")
    rule_1 = _rule(result, "1")
    assert rule_1.effective_dates.effective_from == "2011-04-01"
    effective_date_clauses = [c for c in rule_1.clauses if c.semantic_role.value == "EFFECTIVE_DATE"]
    assert len(effective_date_clauses) == 1
    assert effective_date_clauses[0].effective_date.effective_from == "2011-04-01"


def test_B_rule2_does_not_receive_unrelated_four_litre_threshold():
    result = run_pipeline_from_pages(make_clean_pages(), document_id="doc-1", source="Test Reg")
    rule_2 = _rule(result, "2")
    assert rule_2.thresholds == []
    # And the omission is explained, not silent.
    assert any("4" in w and "litre" in w for w in rule_2.validation_warnings)


def test_C_rule3_thresholds_bound_to_correct_applicability_subclauses():
    result = run_pipeline_from_pages(make_clean_pages(), document_id="doc-1", source="Test Reg")
    rule_3 = _rule(result, "3")
    values_units = {(t.value, t.unit) for t in rule_3.thresholds}
    assert values_units == {(25.0, "kg"), (25.0, "litre"), (50.0, "kg")}
    by_clause = {c.clause_id: c for c in rule_3.clauses}
    assert [t.value for t in by_clause["3(1)"].thresholds] == [25.0]
    assert by_clause["3(1)"].thresholds[0].unit == "kg"
    assert [t.value for t in by_clause["3(2)"].thresholds] == [25.0]
    assert by_clause["3(2)"].thresholds[0].unit == "litre"
    assert [t.value for t in by_clause["3(3)"].thresholds] == [50.0]
    assert by_clause["3(3)"].thresholds[0].unit == "kg"


def test_D_rule6_requirements_associated_with_correct_provisions():
    result = run_pipeline_from_pages(make_clean_pages(), document_id="doc-1", source="Test Reg")
    rule_6 = _rule(result, "6")
    descriptions = [r.description for r in rule_6.requirements]
    assert any("name and address of the manufacturer" in d for d in descriptions)
    assert any("common or generic name" in d for d in descriptions)
    assert any("net quantity" in d for d in descriptions)
    assert any("month and year" in d for d in descriptions)
    assert any("maximum retail price" in d for d in descriptions)
    # Each requirement traces back to its own distinct clause_id, not one
    # merged blob.
    req_ids = {r.id for r in rule_6.requirements}
    assert req_ids == {"6", "6(1)", "6(2)", "6(3)", "6(4)", "6(5)"}


def test_E_rule7_numeric_requirement_bound_not_standalone():
    result = run_pipeline_from_pages(make_clean_pages(), document_id="doc-1", source="Test Reg")
    rule_7 = _rule(result, "7")
    assert len(rule_7.thresholds) == 1
    threshold = rule_7.thresholds[0]
    assert threshold.value == 3.0
    assert threshold.unit == "mm"
    # `label` carries the bound applies_to (see pipeline.py's legacy
    # aggregation) — it must not be None for this well-formed case.
    assert threshold.label == "font"
    # And the clause-level record shows the full binding explicitly.
    clause_7 = rule_7.clauses[0]
    assert clause_7.thresholds[0].clause_id == "7"
    assert clause_7.thresholds[0].applies_to == "font"


def test_F_ocr_corrupted_rule_gets_lower_confidence_than_clean_rules():
    result = run_pipeline_from_pages(make_ocr_degraded_pages(), document_id="doc-1", source="Test Reg")
    rule_7 = _rule(result, "7")  # the deliberately-corrupted rule
    rule_6 = _rule(result, "6")  # clean rule on the same (OCR-sourced) page

    assert rule_7.extraction_confidence < rule_6.extraction_confidence
    assert rule_7.review_status != ReviewStatus.AUTO_ACCEPTED

    # At least one clause in rule 7 should be flagged for OCR quality.
    assert any(c.ocr_quality_flag for c in rule_7.clauses)


def test_F_clean_native_text_is_not_penalized_for_ocr_quality():
    """Native-text rules must never be dragged down by the OCR-garbage
    heuristic, since they were never OCR'd in the first place."""
    result = run_pipeline_from_pages(make_clean_pages(), document_id="doc-1", source="Test Reg")
    for rule in result.rules:
        assert all(not c.ocr_quality_flag for c in rule.clauses)


def test_no_rule_is_auto_accepted_purely_because_regex_matched():
    """Section 12: confidence must be a genuine composite, not a
    regex-match pass/fail. Every auto_accepted rule in the clean fixture
    must have zero validation errors AND reasonably high per-clause
    confidence backing it up — not just 'some text was found'."""
    result = run_pipeline_from_pages(make_clean_pages(), document_id="doc-1", source="Test Reg")
    for rule in result.rules:
        if rule.review_status == ReviewStatus.AUTO_ACCEPTED:
            assert rule.validation_errors == []
            assert rule.extraction_confidence >= 0.75


def test_llm_assist_opt_in_degrades_gracefully_when_ollama_unreachable():
    """The brief requires the deterministic pipeline to keep working even
    if Ollama is unavailable — this exercises use_llm_assist=True end to
    end against an unreachable host, not a mock."""
    result = run_pipeline_from_pages(
        make_clean_pages(), document_id="doc-1", source="Test Reg",
        use_llm_assist=True, ollama_base_url="http://localhost:1",
    )
    assert len(result.rules) == 5
    for rule in result.rules:
        for clause in rule.clauses:
            assert clause.llm_assist is None


def test_clause_level_json_is_fully_traceable_for_every_rule():
    """Every threshold/requirement/condition/exception carries a
    clause_id and source text — the explainability requirement."""
    result = run_pipeline_from_pages(make_clean_pages(), document_id="doc-1", source="Test Reg")
    for rule in result.rules:
        for clause in rule.clauses:
            for t in clause.thresholds:
                assert t.clause_id == clause.clause_id
                assert t.source_text
                assert t.page >= rule.source_location.page_start
            if clause.requirement:
                assert clause.requirement.clause_id == clause.clause_id
                assert clause.requirement.requirement_text
            if clause.condition:
                assert clause.condition.clause_id == clause.clause_id
            if clause.exception:
                assert clause.exception.clause_id == clause.clause_id
