from lexmetra_rules import rule_detection, segmentation
from lexmetra_rules.models import PageText, TextSource


def test_segments_full_document_into_rule_spans(synthetic_pages):
    candidates = rule_detection.detect_headings(synthetic_pages)
    spans = segmentation.segment_rules(synthetic_pages, candidates)
    assert [s.raw_number for s in spans] == [str(n) for n in range(1, 11)]


def test_rule_span_preserves_subrules_and_terminates_at_next_heading(synthetic_pages):
    candidates = rule_detection.detect_headings(synthetic_pages)
    spans = segmentation.segment_rules(synthetic_pages, candidates)
    rule_6 = next(s for s in spans if s.raw_number == "6")
    assert "(1) the name and address" in rule_6.text
    assert "(11) the unit sale price" in rule_6.text
    # Must not bleed into rule 7's text.
    assert "Declaration on imported packages" not in rule_6.text


def test_rule_span_crosses_page_boundary_correctly(synthetic_pages):
    candidates = rule_detection.detect_headings(synthetic_pages)
    spans = segmentation.segment_rules(synthetic_pages, candidates)
    rule_6 = next(s for s in spans if s.raw_number == "6")
    assert rule_6.page_start == 3
    assert rule_6.page_end == 4


def test_last_rule_spans_to_end_of_document(synthetic_pages):
    candidates = rule_detection.detect_headings(synthetic_pages)
    spans = segmentation.segment_rules(synthetic_pages, candidates)
    last = spans[-1]
    assert last.raw_number == "10"
    assert "This amendment shall come into force" in last.text


def test_no_accepted_candidates_yields_no_spans():
    page = PageText(page_no=1, text="No rule headings here at all.", source=TextSource.NATIVE, confidence=1.0)
    candidates = rule_detection.detect_headings([page])
    spans = segmentation.segment_rules([page], candidates)
    assert spans == []


def test_source_location_uses_span_pages(synthetic_pages):
    candidates = rule_detection.detect_headings(synthetic_pages)
    spans = segmentation.segment_rules(synthetic_pages, candidates)
    rule_3 = next(s for s in spans if s.raw_number == "3")
    location = segmentation.to_source_location("doc-1", rule_3)
    assert location.document_id == "doc-1"
    assert location.page_start == rule_3.page_start
    assert location.page_end == rule_3.page_end
    assert location.clause == "3"
