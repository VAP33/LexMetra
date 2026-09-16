from lexmetra_rules.extraction import extract_exemptions


def test_extracts_explicit_exemption():
    exemptions = extract_exemptions(
        "Nothing contained in these rules shall apply to any package "
        "containing a commodity if the net weight is ten grams or less."
    )
    assert len(exemptions) == 1


def test_extracts_exemption_with_effective_date():
    exemptions = extract_exemptions(
        "This exemption shall not apply with effect from 1 January 2018."
    )
    assert exemptions
    assert exemptions[0].effective_from == "1 January 2018"


def test_extracts_except_clause():
    exemptions = extract_exemptions(
        "This rule shall apply to all packages except those intended "
        "for industrial or institutional use."
    )
    assert exemptions


def test_no_exemption_language_returns_empty():
    exemptions = extract_exemptions("Every package shall bear the maximum retail price.")
    assert exemptions == []


def test_exemption_does_not_evaluate_product_eligibility():
    """Module 1 must not decide whether a product qualifies — it only
    records that an exemption exists in the text."""
    exemptions = extract_exemptions(
        "Nothing in this rule shall apply to packages intended for "
        "industrial consumers."
    )
    assert exemptions
    # The model has no field for "applies_to_this_product" or similar —
    # this is a structural guarantee, not just a behavioural one.
    from lexmetra_rules.models import ExtractionExemption
    assert set(ExtractionExemption.model_fields) == {
        "description", "condition_text", "effective_from", "source_text"
    }
