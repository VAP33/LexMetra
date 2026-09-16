from lexmetra_rules.extraction import extract_effective_dates


def test_extracts_effective_from_date_text_form():
    dates = extract_effective_dates(
        "These rules shall come into force with effect from 1 April 2011."
    )
    assert dates.effective_from == "2011-04-01"
    assert dates.effective_from_raw == "1 April 2011"


def test_extracts_effective_from_iso_form():
    dates = extract_effective_dates("This rule shall come into force with effect from 2011-04-01.")
    assert dates.effective_from == "2011-04-01"


def test_extracts_supersession_date():
    dates = extract_effective_dates(
        "Rule 6(11) shall stand superseded with effect from 1 January 2018."
    )
    # "superseded with effect from" matches the _TO_KEYWORDS phrase, not a
    # from-date for a *new* provision — it should land in effective_to.
    assert dates.effective_to == "2018-01-01"


def test_no_date_keyword_returns_none():
    dates = extract_effective_dates("Every package shall bear the name of the manufacturer.")
    assert dates.effective_from is None
    assert dates.effective_to is None


def test_unrelated_date_elsewhere_in_text_is_not_captured():
    """A date not attached to an effective/commencement keyword must not
    be treated as the rule's effective date."""
    dates = extract_effective_dates(
        "This example refers to an invoice dated 5 May 2015 for illustration only."
    )
    assert dates.effective_from is None
    assert dates.effective_to is None


def test_never_invents_a_date_it_cannot_parse():
    """An oddly-formatted date near a keyword should not crash or silently
    produce a wrong ISO date — it should simply not resolve."""
    dates = extract_effective_dates("This rule shall come into force with effect from Someday Never.")
    assert dates.effective_from is None
