from lexmetra_rules import classification
from lexmetra_rules.models import ReviewStatus


def test_food_specific_text_classified_food_and_general():
    result = classification.classify(
        "Every package containing a food article intended for human "
        "consumption shall bear a declaration of net quantity, in "
        "compliance with FSSAI labelling requirements."
    )
    assert "FOOD" in result.categories
    assert "food" in result.signals.get("FOOD", []) or "fssai" in result.signals.get("FOOD", [])


def test_cosmetic_specific_text_excludes_food():
    result = classification.classify(
        "Every package of a cosmetic, including shampoo or soap, shall "
        "bear the name of the manufacturer and net quantity."
    )
    assert "COSMETICS" in result.categories
    assert "FOOD" not in result.categories


def test_general_packaging_text_classified_general():
    result = classification.classify(
        "Every package shall bear the name and address of the "
        "manufacturer, packer or importer, and the net quantity in "
        "terms of the standard unit of weight."
    )
    assert "GENERAL" in result.categories


def test_multi_category_supported():
    result = classification.classify(
        "Every package containing a food article intended for human "
        "consumption shall bear a declaration of net quantity and "
        "comply with general packaged commodity labelling requirements."
    )
    assert set(result.categories) >= {"GENERAL", "FOOD"}


def test_no_signal_text_defaults_to_general_low_confidence():
    result = classification.classify("This provision concerns matters not otherwise addressed.")
    assert result.categories == ["GENERAL"]
    assert result.confidence < 0.5
    assert result.review_status in (ReviewStatus.NEEDS_REVIEW, ReviewStatus.UNCERTAIN)


def test_signals_are_explainable():
    result = classification.classify(
        "Every package of an imported commodity shall declare the "
        "country of origin and the name of the importer."
    )
    assert "IMPORT" in result.categories
    assert len(result.signals.get("IMPORT", [])) > 0


def test_high_confidence_gets_auto_accepted():
    result = classification.classify(
        "Every pre-packaged commodity and packaged commodity shall bear "
        "a principal display panel with net quantity, maximum retail "
        "price, and the name of the manufacturer or packer or importer."
    )
    assert result.confidence >= classification.AUTO_ACCEPT_CONFIDENCE
    assert result.review_status == ReviewStatus.AUTO_ACCEPTED
