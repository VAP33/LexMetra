from lexmetra_rules import rule_detection, segmentation
from lexmetra_rules.clause_segmentation import segment_clauses
from lexmetra_rules.models import ClauseType
from tests.fixtures.semantic_v2_regression_text import make_clean_pages


def _span_for(rule_id):
    pages = make_clean_pages()
    candidates = rule_detection.detect_headings(pages)
    spans = segmentation.segment_rules(pages, candidates)
    return next(s for s in spans if s.raw_number == rule_id)


def test_rule_with_no_sub_numbering_is_one_body_clause():
    span = _span_for("2")
    clauses = segment_clauses(span)
    assert len(clauses) == 1
    assert clauses[0].clause_type == ClauseType.BODY
    assert clauses[0].clause_id == "2"


def test_subrules_get_distinct_clause_ids_and_parent():
    span = _span_for("3")
    clauses = segment_clauses(span)
    subrule_ids = [c.clause_id for c in clauses if c.clause_type == ClauseType.SUBRULE]
    assert subrule_ids == ["3(1)", "3(2)", "3(3)"]
    for c in clauses:
        if c.clause_type == ClauseType.SUBRULE:
            assert c.parent_clause_id == "3"


def test_subclause_nests_under_its_subrule():
    span = _span_for("6")
    clauses = segment_clauses(span)
    sub = next(c for c in clauses if c.clause_id == "6(1)")
    assert sub.parent_clause_id == "6"
    assert sub.clause_type == ClauseType.SUBRULE


def test_clauses_preserve_original_text_verbatim():
    span = _span_for("3")
    clauses = segment_clauses(span)
    clause_31 = next(c for c in clauses if c.clause_id == "3(1)")
    assert "does not exceed 25 kg" in clause_31.text


def test_clause_page_locations_are_within_rule_span_bounds():
    span = _span_for("6")
    clauses = segment_clauses(span)
    for c in clauses:
        assert span.page_start <= c.page_start <= span.page_end
        assert span.page_start <= c.page_end <= span.page_end


def test_table_block_is_its_own_clause_type():
    from lexmetra_rules.models import PageText, TextSource
    from lexmetra_rules.segmentation import RuleSpan

    text = (
        "6. Some rule.\u2014Every package shall comply.\n"
        "500 1000 1500\n"
        "250 750 1250\n"
        "(1) a genuine sub-rule follows the table.\n"
    )
    span = RuleSpan(
        raw_number="6", heading_line_text="6. Some rule.", text=text,
        page_start=1, page_end=1, lines=[(1, l) for l in text.splitlines()],
    )
    clauses = segment_clauses(span)
    table_clauses = [c for c in clauses if c.clause_type == ClauseType.TABLE]
    assert len(table_clauses) == 1
    assert "500" in table_clauses[0].text


def test_proviso_on_its_own_line_becomes_separate_clause():
    from lexmetra_rules.models import PageText, TextSource
    from lexmetra_rules.segmentation import RuleSpan

    text = (
        "9. Exemption.\u2014Every package containing tea shall be exempt.\n"
        "Provided that this exemption shall not apply to tea sold loose.\n"
    )
    span = RuleSpan(
        raw_number="9", heading_line_text="9. Exemption.", text=text,
        page_start=1, page_end=1, lines=[(1, l) for l in text.splitlines()],
    )
    clauses = segment_clauses(span)
    provisos = [c for c in clauses if c.clause_type == ClauseType.PROVISO]
    assert len(provisos) == 1
    assert "shall not apply to tea sold loose" in provisos[0].text


def test_explanation_becomes_separate_clause():
    from lexmetra_rules.segmentation import RuleSpan

    text = (
        "9. Some rule.\u2014Every package shall comply with this rule.\n"
        "Explanation.\u2014For the purposes of this rule, \"package\" includes any wrapper.\n"
    )
    span = RuleSpan(
        raw_number="9", heading_line_text="9. Some rule.", text=text,
        page_start=1, page_end=1, lines=[(1, l) for l in text.splitlines()],
    )
    clauses = segment_clauses(span)
    explanations = [c for c in clauses if c.clause_type == ClauseType.EXPLANATION]
    assert len(explanations) == 1


def test_empty_span_yields_no_clauses():
    from lexmetra_rules.segmentation import RuleSpan
    span = RuleSpan(raw_number="1", heading_line_text="", text="", page_start=1, page_end=1, lines=[])
    assert segment_clauses(span) == []
