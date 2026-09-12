"""
Declaration extraction, normalization, canonical mapping and multi-surface
aggregation.

NOTE ON THIS FILE'S HISTORY. It was originally written against an API that did
not exist: it imported `OCRLine` (the class is `OcrLine`), asserted
`CanonicalStatus.ABSENT` / `.UNOBSERVED` (neither is a member of the enum),
read `_MONEY_RE.group(1)` for patterns that match on groups 2-4, and expected
`classify_fields` to report `VERIFIED`. It therefore could not even be
imported, and every one of its 8 tests errored at collection.

Where the test and the code disagreed, the CODE was right and the test has been
corrected to match it. In particular `classify_fields` reports `DETECTED`, never
`VERIFIED`: the reader's job is to say what it saw, and only the deterministic
rule engine may pronounce a declaration compliant. An extractor that returned
`VERIFIED` would be claiming a legal conclusion it is not entitled to make.
"""

from __future__ import annotations

import pytest

from schema import (
    CanonicalStatus,
    UNATTRIBUTED_IMAGE_ID,
)
from ocr_extraction import (
    OcrLine,
    _MONEY_RE,
    _extract_money,
    _normalize_date,
    normalize_date,
    classify_fields,
)
from rule_engine import RawExtraction, run_inspection
import capture_session


# ---------------------------------------------------------------------------
# 1. Price extraction and normalization
# ---------------------------------------------------------------------------

class TestPricingExtraction:
    def test_indian_pricing_patterns(self):
        """Indian packaging price formats: =420/-, 420/-, Rs. 420.50, INR 120."""
        cases = [
            ("=420/-", 420.0),
            ("420/-", 420.0),
            ("F420/-", 420.0),          # OCR misread of the rupee marker
            ("₹420", 420.0),
            ("Rs. 420", 420.0),
            ("Rs. 420.50", 420.50),
            ("MRP: ₹ 120.00", 120.0),
            ("INCL. OF ALL TAXES =420/-", 420.0),
        ]
        for text, expected in cases:
            assert _MONEY_RE.search(text) is not None, f"no money match in {text!r}"
            # Use the parser rather than a fixed group index: the pattern has
            # four alternatives and only one group is populated per match.
            assert _extract_money(text) == expected, text

    def test_measurements_and_identifiers_are_never_prices(self):
        """
        The "16.89 gMs" guard, and the regression that reopened it.

        A hyphen was briefly admitted to the currency-marker class as a
        "common OCR misread of the rupee sign". A hyphen is also the ordinary
        separator in net weights, batch codes, dates and phone numbers, so
        every one of those became a currency-marked amount and skipped the
        measurement guard entirely. `mrp.numeric_value` is the numerator of
        the Rule 6(11) unit-price consistency check, so a mass accepted as a
        price can fabricate a FAIL against a compliant package.
        """
        for text in [
            "NET WT-500 g",
            "16.89 gMs",
            "BATCH-1234",
            "13-05-26",
            "12-05-2026",
            "1800-10-22-221",
            "NET WT 500 g",
        ]:
            assert _extract_money(text) is None, f"{text!r} was accepted as a price"

    def test_mrp_label_without_amount_is_not_a_value(self):
        """'MRP&' with no price must yield no value and a review flag."""
        classified = classify_fields([
            OcrLine(text="MRP&", bbox=(187, 1045, 51, 16), confidence=0.9),
            OcrLine(text="(INCL. OF ALL TAXES)", bbox=(187, 1066, 145, 20), confidence=0.95),
        ])
        mrp = classified.get("mrp")
        assert mrp is not None
        assert mrp.get("value") is None
        assert mrp.get("numeric_value") is None
        assert mrp.get("status") == "REVIEW_REQUIRED"
        assert mrp.get("source") == "ocr_label_only"
        # The label itself is retained: it is the evidence that a declaration
        # was attempted, which is what separates "unreadable" from "absent".
        assert mrp.get("label") == "MRP&"
        assert mrp.get("confidence") <= 0.35

    def test_mrp_two_column_association(self):
        """Bru jar layout: label on the left, value '=420/-' on the right."""
        classified = classify_fields([
            OcrLine(text="MRP&", bbox=(187, 1045, 51, 16), confidence=0.88),
            OcrLine(text="(INCL. OF ALL TAXES)", bbox=(187, 1066, 145, 20), confidence=0.95),
            OcrLine(text="=420/-", bbox=(367, 1098, 77, 18), confidence=0.92),
        ])
        mrp = classified.get("mrp")
        assert mrp is not None
        assert mrp.get("numeric_value") == 420.0
        assert mrp.get("currency") == "INR"
        # DETECTED, not VERIFIED - see the module docstring.
        assert mrp.get("status") == "DETECTED"
        assert mrp.get("confidence") >= 0.70
        # The value's own bbox, not the label's, is what a reviewer must be
        # shown; both are kept so the association can be audited.
        assert tuple(mrp.get("bbox")) == (367, 1098, 77, 18)
        assert tuple(mrp.get("label_bbox")) == (187, 1045, 51, 16)


# ---------------------------------------------------------------------------
# 2. Date extraction and normalization
# ---------------------------------------------------------------------------

class TestDateExtraction:
    def test_date_normalization(self):
        assert _normalize_date("12/10") == "2010-12"
        assert _normalize_date("13/05/26") == "2026-05-13"
        assert _normalize_date("31/12/2027") == "2027-12-31"
        assert _normalize_date("OCT 2026") == "2026-10"
        assert _normalize_date("12 months from packaging") == "12 months from packaging"

    def test_public_normalizer_refuses_unparseable_text(self):
        """
        `normalize_date` is strict where `_normalize_date` is permissive.

        The internal parser ends in an unconditional `return t`, which is safe
        for its callers because they only reach it with a substring that was
        already matched as date-shaped. The public entry point is called with
        arbitrary caller-supplied text, and the rule engine reads "normalized
        value is not None" as "a date was established" - so a passthrough
        would turn "see bottom of pack" into a satisfied date declaration.
        """
        assert normalize_date("see bottom of pack") is None
        assert normalize_date("not a date") is None
        assert normalize_date(None) is None
        assert normalize_date("13/05/26") == "2026-05-13"
        # A relative shelf life is a lawful declaration form and survives.
        assert normalize_date("12 months from packaging") == "12 months from packaging"

    def test_use_by_label_without_date_is_not_a_value(self):
        classified = classify_fields([
            OcrLine(text="USE BY", bbox=(187, 1163, 59, 16), confidence=1.0),
        ])
        # The OCR vocabulary calls this `expiry_date`; the legal vocabulary
        # calls it `best_before_use_by`. Bridging is a separate step.
        exp = classified.get("expiry_date")
        assert exp is not None
        assert exp.get("value") is None
        assert exp.get("status") == "REVIEW_REQUIRED"
        assert exp.get("confidence") <= 0.35

    def test_use_by_with_associated_date(self):
        classified = classify_fields([
            OcrLine(text="USE BY", bbox=(187, 1163, 59, 16), confidence=0.98),
            OcrLine(text="12/10", bbox=(367, 1183, 58, 15), confidence=0.92),
        ])
        exp = classified.get("expiry_date")
        assert exp is not None
        assert exp.get("value") == "12/10"
        assert exp.get("normalized_value") == "2010-12"
        assert exp.get("status") == "DETECTED"


# ---------------------------------------------------------------------------
# 3. The OCR -> legal vocabulary bridge
# ---------------------------------------------------------------------------

class TestVocabularyBridge:
    def test_label_only_observation_survives_the_bridge(self):
        """
        A declaration whose label was read but whose value was not must reach
        the rule engine under its legal name.

        The bridge previously required a non-empty value, so this observation
        was dropped and the engine saw no `best_before_use_by` at all - the
        input to its ABSENCE branch, which with sufficient coverage is a FAIL.
        "Label present, value unreadable" is a photograph problem; "no
        declaration observed" is a compliance problem. Collapsing the first
        into the second manufactures a violation.
        """
        classified = {
            "expiry_date": {
                "field": "expiry_date",
                "label": "USE BY",
                "value": None,
                "confidence": 0.27,
                "status": "REVIEW_REQUIRED",
            }
        }
        bridged = capture_session.bridge_classified_fields(classified)
        assert "best_before_use_by" in bridged
        assert bridged["best_before_use_by"]["label"] == "USE BY"
        assert bridged["best_before_use_by"]["value"] is None

    def test_bridge_prefers_a_source_carrying_an_actual_value(self):
        classified = {
            "manufacturer_name": {"label": "Mfg by", "value": None, "confidence": 0.2},
            "packer_name": {
                "label": "Packed by",
                "value": "Hindustan Unilever Ltd",
                "confidence": 0.9,
            },
        }
        bridged = capture_session.bridge_classified_fields(classified)
        assert bridged["manufacturer_name_address"]["value"] == "Hindustan Unilever Ltd"

    def test_bridge_still_drops_nothing_when_nothing_was_observed(self):
        assert "best_before_use_by" not in capture_session.bridge_classified_fields({})


# ---------------------------------------------------------------------------
# 4. Label / reason / status reach the rule-engine contract
# ---------------------------------------------------------------------------

class TestExtractionContract:
    def test_label_and_reason_are_forwarded_to_raw_extraction(self):
        """
        `classify_fields` computes `label`, `status` and `reason`;
        `build_raw_extraction` used to forward none of them, so every
        downstream `getattr(ext, "label", None)` was None in production and the
        PARTIALLY_DETECTED outcome was unreachable. Same shape of defect as the
        dropped bbox: computed upstream, nowhere to land.
        """
        ext = capture_session.build_raw_extraction("mrp", {
            "value": None,
            "label": "MRP&",
            "confidence": 0.27,
            "status": "REVIEW_REQUIRED",
            "reason": "label detected, no amount",
            "bbox": [187, 1045, 51, 16],
            "image_id": "front.jpg",
        })
        assert ext.label == "MRP&"
        assert ext.reason == "label detected, no amount"
        assert ext.detection_status == "REVIEW_REQUIRED"

    def test_date_is_normalized_at_the_translation_layer(self):
        """
        A structured caller supplying a plain date string gets it normalized
        here, because the rule engine treats an un-normalized date as
        unresolved and performs no text parsing itself.
        """
        ext = capture_session.build_raw_extraction("best_before_use_by", {
            "value": "12/10/2027",
            "confidence": 0.9,
        })
        assert ext.normalized_value == "2027-10-12"

    def test_unparseable_date_stays_unresolved(self):
        ext = capture_session.build_raw_extraction("best_before_use_by", {
            "value": "see bottom of pack",
            "confidence": 0.9,
        })
        assert ext.normalized_value is None


# ---------------------------------------------------------------------------
# 5. Canonical declarations: no duplicates, no fabricated confidence
# ---------------------------------------------------------------------------

class TestCanonicalDeclarations:
    def _result(self, extractions):
        return run_inspection(
            inspection_id="test:decl",
            sale_type="retail",
            product_category="food",
            net_quantity_value=150.0,
            net_quantity_unit="g",
            mrp=420.0,
            extractions=extractions,
            best_before_applicable=True,
            is_imported=False,
        )

    def test_no_duplicate_canonical_fields(self):
        result = self._result({
            "net_quantity": RawExtraction(
                field="net_quantity", value="150 g", confidence=0.95,
                numeric_value=150.0, numeric_unit="g",
            ),
            "mrp": RawExtraction(
                field="mrp", value="₹420", confidence=0.90, numeric_value=420.0,
            ),
            "unit_sale_price": RawExtraction(
                field="unit_sale_price", value="₹2.80 / g", confidence=0.88,
                numeric_value=2.80, numeric_unit="g",
            ),
            "manufacturer_name_address": RawExtraction(
                field="manufacturer_name_address",
                value="Hindustan Unilever Ltd, Mumbai 400099", confidence=0.92,
            ),
            "consumer_care": RawExtraction(
                field="consumer_care", value="1800-10-22-221", confidence=0.90,
            ),
            "best_before_use_by": RawExtraction(
                field="best_before_use_by", value="12/10", confidence=0.85,
                normalized_value="2010-12",
            ),
        })

        assert result.declarations
        fields = [d.field for d in result.declarations]
        assert len(fields) == len(set(fields)), f"duplicates: {fields}"
        assert fields.count("unit_sale_price") == 1
        assert [f.field for f in result.facts].count("unit_sale_price") == 1

    def test_declaration_carries_the_extractors_label_and_reason(self):
        """The PARTIALLY_DETECTED path, which was unreachable in production."""
        result = self._result({
            "mrp": RawExtraction(
                field="mrp", value=None, confidence=0.27, raw_text="MRP&",
                label="MRP&", detection_status="REVIEW_REQUIRED",
                reason="Declaration label 'MRP&' was detected, but no valid "
                       "monetary price could be established.",
            ),
        })
        mrp = next(d for d in result.declarations if d.field == "mrp")
        assert mrp.status == CanonicalStatus.PARTIALLY_DETECTED
        assert mrp.label == "MRP&"
        assert "no valid monetary price" in (mrp.reason or "")
        assert mrp.validation.present is False

    def test_unobserved_declarations_never_claim_confident_compliance(self):
        """
        An absent or unobserved declaration must not carry a high confidence,
        and must never be reported compliant on no evidence.
        """
        result = self._result({})
        assert result.declarations
        unobserved = [
            d for d in result.declarations
            if d.status in (
                CanonicalStatus.NOT_DETECTED_IN_PROVIDED_IMAGES,
                CanonicalStatus.INSUFFICIENT_EVIDENCE,
            )
        ]
        assert unobserved, "expected unobserved declarations with no extractions"
        for decl in unobserved:
            assert (decl.confidence or 0.0) == 0.0, decl.field
            assert decl.validation.present is False, decl.field
            assert decl.validation.compliant is not True, decl.field

    def test_no_extractions_never_produces_a_definitive_pass(self):
        """Invariant 18: insufficient evidence resolves to UNCERTAIN."""
        result = self._result({})
        assert result.overall_status.value != "PASS"


# ---------------------------------------------------------------------------
# 6. Multi-surface aggregation and per-field provenance
# ---------------------------------------------------------------------------

class TestMultiSurfaceAggregation:
    def test_multi_surface_provenance_and_merge(self):
        """Panel 1 carries MRP and batch; panel 2 carries net quantity and maker."""
        c1 = capture_session.stamp_provenance({
            "mrp": {"value": "₹420", "numeric_value": 420.0,
                    "confidence": 0.90, "status": "DETECTED", "label": "MRP"},
            "batch_no": {"value": "HF130526", "confidence": 0.88,
                         "status": "DETECTED", "label": "BATCH No"},
        }, image_id="panel_1.jpg", surface_id="s1")

        c2 = capture_session.stamp_provenance({
            "net_quantity": {"value": "150 g", "numeric_value": 150.0,
                             "numeric_unit": "g", "confidence": 0.95,
                             "status": "DETECTED", "label": "Net Qty"},
            "manufacturer_name_address": {"value": "Hindustan Unilever Ltd",
                                          "confidence": 0.91, "status": "DETECTED",
                                          "label": "Mfg by"},
        }, image_id="panel_2.jpg", surface_id="s2")

        merged = capture_session.merge_classified_fields(c1, c2)

        for field in ("mrp", "net_quantity", "batch_no", "manufacturer_name_address"):
            assert field in merged, field

        # Provenance is per FIELD, not per request: a single request-level
        # image id would send a reviewer to a photograph that does not contain
        # the text, which is worse than no attribution at all.
        assert merged["mrp"]["image_id"] == "panel_1.jpg"
        assert merged["net_quantity"]["image_id"] == "panel_2.jpg"
        assert merged["batch_no"]["image_id"] == "panel_1.jpg"
        assert merged["manufacturer_name_address"]["image_id"] == "panel_2.jpg"

    def test_merged_field_keeps_the_higher_confidence_reading(self):
        c1 = capture_session.stamp_provenance(
            {"mrp": {"value": "₹420", "confidence": 0.90}},
            image_id="panel_1.jpg",
        )
        c2 = capture_session.stamp_provenance(
            {"mrp": {"value": "₹999", "confidence": 0.40}},
            image_id="panel_2.jpg",
        )
        merged = capture_session.merge_classified_fields(c1, c2)
        assert merged["mrp"]["value"] == "₹420"
        assert merged["mrp"]["image_id"] == "panel_1.jpg"
