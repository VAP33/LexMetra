from lexmetra_rules import rule_detection
from lexmetra_rules.models import PageText, TextSource


def _page(text, page_no=1):
    return PageText(page_no=page_no, text=text, source=TextSource.NATIVE, confidence=1.0)


def test_detects_real_rule_headings(synthetic_pages):
    candidates = rule_detection.detect_headings(synthetic_pages)
    accepted_numbers = {c.raw_number for c in candidates if c.accepted}
    assert accepted_numbers == {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}


def test_rejects_isolated_number_breaking_sequence(synthetic_pages):
    """The '44.' decoy heading in the fixture must not become a rule."""
    candidates = rule_detection.detect_headings(synthetic_pages)
    forty_four = next(c for c in candidates if c.raw_number == "44")
    assert forty_four.accepted is False
    assert any("sequence" in reason for reason in forty_four.reasons)


def test_rejects_number_beyond_plausible_range(synthetic_pages):
    """
    The '2011.' decoy (a year) must not become a rule. A 4-digit number is
    excluded at the regex level (headings are capped at 3 digits) — an even
    stronger guarantee than the range-score check, so it never appears as a
    candidate at all rather than appearing and being scored down.
    """
    candidates = rule_detection.detect_headings(synthetic_pages)
    assert all(c.raw_number != "2011" for c in candidates)

    # Directly confirm the range-score defense too, for a 3-digit number
    # that *does* reach the regex (the structural exclusion above only
    # covers 4+ digit numbers).
    page = _page("6. Real rule text that is long enough to look like prose.\n\n199. Some out-of-range number followed by real-looking prose text.")
    over_range_candidates = rule_detection.detect_headings([page], max_rule_number=50)
    over_range = next(c for c in over_range_candidates if c.raw_number == "199")
    assert over_range.accepted is False
    assert any("range" in reason for reason in over_range.reasons)


def test_bare_number_with_no_period_is_not_even_a_candidate():
    """A standalone page-footer-style number like '44' with no trailing
    text must never become a heading candidate at all."""
    page = _page("Some heading text.\n\n44\n\nMore text follows here.")
    candidates = rule_detection.detect_headings([page])
    assert all(c.raw_number != "44" for c in candidates)


def test_page_footer_number_rejected():
    page = _page("3. Real rule text here that is long enough.\n\nPage 4\n\n5. Another real rule with enough text.")
    candidates = rule_detection.detect_headings([page])
    for c in candidates:
        if "Page 4" in c.line_text:
            assert c.accepted is False


def test_gazette_reference_rejected():
    page = _page(
        "3. Real rule text here that is long enough to look like prose.\n\n"
        "629. G.S.R. 629(E) dated the 1st March, 2011.\n\n"
        "4. Another real rule with enough text to look like prose."
    )
    candidates = rule_detection.detect_headings([page])
    gazette_candidate = next(c for c in candidates if c.raw_number == "629")
    assert gazette_candidate.accepted is False


def test_money_amount_after_number_scored_low():
    page = _page("6. Rs. 500 shall be the maximum fee payable under this provision.")
    candidates = rule_detection.detect_headings([page])
    candidate = candidates[0]
    # Not asserting hard rejection (could legitimately be a heading in some
    # documents) but it must not be treated with full confidence.
    assert candidate.confidence < 0.8


def test_sub_clause_marker_is_not_a_heading():
    page = _page("6. Declarations on every package.\n(11) unit sale price shall be declared.")
    candidates = rule_detection.detect_headings([page])
    assert all(c.raw_number != "11" for c in candidates)


def test_short_heading_text_rejected():
    """A number followed by only a couple of characters is too short to
    plausibly be a real rule title."""
    page = _page("6. Ok.\n\n7. A genuinely long enough rule heading text follows here.")
    candidates = rule_detection.detect_headings([page])
    short_one = next(c for c in candidates if c.raw_number == "6")
    assert short_one.accepted is False


def test_every_candidate_carries_confidence_and_reasons(synthetic_pages):
    candidates = rule_detection.detect_headings(synthetic_pages)
    assert len(candidates) > 0
    for c in candidates:
        assert 0.0 <= c.confidence <= 1.0
        assert isinstance(c.reasons, list) and len(c.reasons) > 0
