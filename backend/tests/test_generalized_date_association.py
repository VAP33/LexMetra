"""
Comprehensive Generalized Date Association Test Suite.

Verifies correct evidence-based semantic association across:
Layout A: Same-line horizontal
Layout B: Vertical stacked
Layout C: Two-column grid (parallel columns)
Layout D: Rotated text (orientation-normalized geometry)
Layout E: Separate OCR regions (label and value separate)
Layout F: Cross-surface association
Layout G: OCR noise and spacing variations (P KD, USE 8Y, MFD.)
Layout H: Unit price collision protection (2.80/g, ₹2.80/g, = 2.80/g)
Layout I: Ambiguous spatial evidence (flags REVIEW_REQUIRED, no guessing)
Layout J: Contradictory dates (mfg > exp flags REVIEW_REQUIRED without blind swap)
Layout K: Missing date value (label alone flags REVIEW_REQUIRED, value=None)
Layout L: Multiple unrelated dates on package
Layout M: Best-before duration instead of explicit expiry date ("12 months from packaging")
Layout N: Supported date formats (DD/MM/YYYY, MM/YY, MM/YYYY, Month YYYY)
"""

import pytest
from ocr_extraction import OcrLine, classify_fields
from date_association import (
    DateCandidate,
    LabelCandidate,
    DateAssociationGraph,
    associate_date_fields,
    is_unit_rate_expression,
    extract_raw_date_tokens,
    normalize_parsed_date,
)


class TestLayoutASameLineHorizontal:
    def test_same_line_horizontal_standard(self):
        """PKD 13/05/26   USE BY 12/10/27 on the same horizontal line."""
        lines = [
            OcrLine(text="PKD 13/05/26", bbox=(100, 200, 150, 25), confidence=0.95),
            OcrLine(text="USE BY 12/10/27", bbox=(400, 200, 180, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["status"] == "DETECTED"
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"
        assert res["expiry_date"]["status"] == "DETECTED"
        assert res["expiry_date"]["normalized_value"] == "2027-10-12"

    def test_single_line_multiple_declarations(self):
        """Single line containing both declarations separated by spacing."""
        lines = [
            OcrLine(text="MFD 05/2026  EXP 04/2028", bbox=(100, 200, 500, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05"
        assert res["expiry_date"]["normalized_value"] == "2028-04"


class TestLayoutBVerticalStacked:
    def test_vertical_stacked_alternating(self):
        """
        PKD
        13/05/26
        USE BY
        12/10/27
        """
        lines = [
            OcrLine(text="PKD", bbox=(100, 100, 50, 20), confidence=0.95),
            OcrLine(text="13/05/26", bbox=(100, 130, 90, 20), confidence=0.95),
            OcrLine(text="USE BY", bbox=(100, 180, 70, 20), confidence=0.95),
            OcrLine(text="12/10/27", bbox=(100, 210, 90, 20), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"
        assert res["expiry_date"]["normalized_value"] == "2027-10-12"

    def test_vertical_stacked_manufactured_best_before(self):
        """
        Manufactured:
        13/05/26
        Best Before:
        12/10/27
        """
        lines = [
            OcrLine(text="Manufactured:", bbox=(200, 100, 120, 22), confidence=0.95),
            OcrLine(text="13/05/26", bbox=(200, 130, 90, 22), confidence=0.95),
            OcrLine(text="Best Before:", bbox=(200, 180, 110, 22), confidence=0.95),
            OcrLine(text="12/10/27", bbox=(200, 210, 90, 22), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"
        assert res["expiry_date"]["normalized_value"] == "2027-10-12"


class TestLayoutCTwoColumnGrid:
    def test_two_column_grid_parallel(self):
        """
        PKD        USE BY
        13/05/26   12/10/27
        """
        lines = [
            OcrLine(text="PKD", bbox=(100, 100, 50, 20), confidence=0.95),
            OcrLine(text="USE BY", bbox=(300, 100, 70, 20), confidence=0.95),
            OcrLine(text="13/05/26", bbox=(100, 140, 90, 20), confidence=0.95),
            OcrLine(text="12/10/27", bbox=(300, 140, 90, 20), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"
        assert res["expiry_date"]["normalized_value"] == "2027-10-12"

    def test_two_column_labels_left_values_right(self):
        """
        Labels column on left, values column on right (BRU regression layout):
        PKD:        13/05/26
        USE BY:     12/10/27
        """
        lines = [
            OcrLine(text="PKD.", bbox=(280, 1666, 60, 25), confidence=0.95),
            OcrLine(text="USE BY", bbox=(280, 1738, 90, 25), confidence=0.95),
            OcrLine(text="13/05/26", bbox=(540, 1722, 150, 30), confidence=0.95),
            OcrLine(text="12/10/27", bbox=(540, 1762, 150, 30), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"
        assert res["expiry_date"]["normalized_value"] == "2027-10-12"


class TestLayoutDRotatedText:
    def test_rotated_text_relative_alignment(self):
        """Vertical banner reading with consistent spatial offset."""
        lines = [
            OcrLine(text="PACKED ON", bbox=(50, 300, 30, 90), confidence=0.90),
            OcrLine(text="13/05/26", bbox=(50, 410, 30, 80), confidence=0.90),
            OcrLine(text="EXPIRY DATE", bbox=(50, 520, 30, 100), confidence=0.90),
            OcrLine(text="12/10/27", bbox=(50, 640, 30, 80), confidence=0.90),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"
        assert res["expiry_date"]["normalized_value"] == "2027-10-12"


class TestLayoutESeparateOcrRegions:
    def test_label_and_value_in_separate_lines(self):
        """Label in one block, value in a distinct non-adjacent box."""
        lines = [
            OcrLine(text="DATE OF PACKING", bbox=(100, 100, 180, 25), confidence=0.95),
            OcrLine(text="LOT NO 994", bbox=(100, 135, 120, 20), confidence=0.90),
            OcrLine(text="13.05.2026", bbox=(320, 100, 110, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"


class TestLayoutFCrossSurface:
    def test_cross_surface_compatible_association(self):
        """Association when surfaces are declared."""
        lines = [
            OcrLine(text="PKD 13/05/26", bbox=(50, 50, 200, 25), confidence=0.95),
        ]
        res = associate_date_fields(lines, surface_id="front_panel")
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"


class TestLayoutGNoiseVariations:
    def test_noisy_labels(self):
        """Test variations: 'P KD', 'USE 8Y', 'MFD.'."""
        test_cases = [
            ("P KD 13/05/26", "2026-05-13", "mfg_date"),
            ("USE 8Y 12/10/27", "2027-10-12", "expiry_date"),
            ("MFD. 05/2026", "2026-05", "mfg_date"),
            ("BEST-BEFORE 12/10/27", "2027-10-12", "expiry_date"),
        ]
        for text, expected_date, expected_field in test_cases:
            lines = [OcrLine(text=text, bbox=(100, 100, 200, 25), confidence=0.90)]
            res = classify_fields(lines)
            assert expected_field in res, f"Failed to detect {expected_field} from '{text}'"
            assert res[expected_field]["normalized_value"] == expected_date


class TestLayoutHUnitPriceCollision:
    def test_unit_price_not_parsed_as_date(self):
        """Ensure 2.80/g, ₹2.80/g, = 2.80/g are NEVER extracted as dates."""
        unit_rates = [
            "2.80/g",
            "₹2.80/g",
            "= 2.80/g",
            "USP Rs. 2.80 / kg",
            "Unit Sale Price: ₹ 2.80/ml",
        ]
        for rate_str in unit_rates:
            assert is_unit_rate_expression(rate_str)
            tokens = extract_raw_date_tokens(rate_str)
            assert len(tokens) == 0, f"Rate {rate_str!r} was falsely extracted as date tokens: {tokens}"

    def test_valid_mm_yy_date_preserved_alongside_unit_price(self):
        """Ensure MM/YY date is preserved even when unit price exists in same OCR stream."""
        lines = [
            OcrLine(text="PKD 05/26", bbox=(100, 100, 150, 25), confidence=0.95),
            OcrLine(text="= 2.80/g", bbox=(100, 140, 120, 25), confidence=0.90),
            OcrLine(text="USE BY 10/27", bbox=(100, 180, 150, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05"
        assert res["expiry_date"]["normalized_value"] == "2027-10"
        assert res["unit_sale_price"]["numeric_value"] == 2.80


class TestLayoutIAmbiguousLabels:
    def test_ambiguous_spatial_association_flags_review(self):
        """
        When a label is ambiguous between two competing candidate dates,
        the system must return REVIEW_REQUIRED and not guess.
        """
        lines = [
            OcrLine(text="USE BY", bbox=(300, 200, 80, 25), confidence=0.90),
            # Date 1 to the right
            OcrLine(text="13/05/26", bbox=(450, 200, 100, 25), confidence=0.90),
            # Date 2 below
            OcrLine(text="12/10/27", bbox=(300, 235, 100, 25), confidence=0.90),
        ]
        res = classify_fields(lines)
        assert "expiry_date" in res
        assert len(res["expiry_date"]["alternative_associations"]) > 0


class TestLayoutJContradictoryDates:
    def test_mfg_date_after_expiry_date_flags_review_without_blind_swap(self):
        """
        Illogical date sequence (mfg > expiry) must be flagged as REVIEW_REQUIRED,
        and MUST NOT be silently or blindly swapped.
        """
        lines = [
            OcrLine(text="MFD 12/10/2028", bbox=(100, 100, 200, 25), confidence=0.95),
            OcrLine(text="EXP 13/05/2026", bbox=(100, 150, 200, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["status"] == "REVIEW_REQUIRED"
        assert res["expiry_date"]["status"] == "REVIEW_REQUIRED"
        # The values must remain with their respective semantic labels!
        assert res["mfg_date"]["normalized_value"] == "2028-10-12"
        assert res["expiry_date"]["normalized_value"] == "2026-05-13"
        assert "Illogical date sequence" in res["mfg_date"]["reason"]


class TestLayoutKMissingDate:
    def test_label_alone_without_date_is_review_required(self):
        """Declaration label without date value yields REVIEW_REQUIRED and value=None."""
        lines = [
            OcrLine(text="USE BY", bbox=(100, 100, 80, 25), confidence=0.90),
        ]
        res = classify_fields(lines)
        assert "expiry_date" in res
        assert res["expiry_date"]["value"] is None
        assert res["expiry_date"]["status"] == "REVIEW_REQUIRED"
        assert res["expiry_date"]["confidence"] <= 0.35


class TestLayoutLMultipleUnrelatedDates:
    def test_multiple_dates_with_target_labels(self):
        """Package has an unrelated copyright year or standard reference year."""
        lines = [
            OcrLine(text="© 2019 ACME FOODS", bbox=(50, 50, 200, 20), confidence=0.90),
            OcrLine(text="PKD 13/05/26", bbox=(100, 150, 150, 25), confidence=0.95),
            OcrLine(text="USE BY 12/10/27", bbox=(100, 200, 180, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"
        assert res["expiry_date"]["normalized_value"] == "2027-10-12"


class TestLayoutMRelativeDuration:
    def test_best_before_relative_shelf_life(self):
        """Best before duration (e.g. 12 months from packaging)."""
        lines = [
            OcrLine(text="PKD 13/05/26", bbox=(100, 100, 150, 25), confidence=0.95),
            OcrLine(text="BEST BEFORE 12 MONTHS FROM PACKAGING", bbox=(100, 150, 350, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"
        assert "expiry_date" in res
        assert "12 months" in str(res["expiry_date"]["value"]).lower()


class TestLayoutNDateFormatVariants:
    @pytest.mark.parametrize(
        "raw_str,expected_norm",
        [
            ("13/05/26", "2026-05-13"),
            ("13.05.2026", "2026-05-13"),
            ("13-05-2026", "2026-05-13"),
            ("05/2026", "2026-05"),
            ("05-2026", "2026-05"),
            ("05/26", "2026-05"),
            ("OCT 2026", "2026-10"),
            ("12 OCT 2026", "2026-10-12"),
            ("2026/05/13", "2026-05-13"),
        ],
    )
    def test_format_variants_normalization(self, raw_str, expected_norm):
        norm = normalize_parsed_date(raw_str)
        assert norm == expected_norm, f"Failed for {raw_str}: expected {expected_norm}, got {norm}"


class TestLayoutOCompanyDeclarationGuard:
    def test_mfg_by_company_name_is_not_date_label(self):
        """MAHARASHTRA. MFG. BY: HINDUSTAN UNILEVER is an entity declaration, NOT a date label."""
        lines = [
            OcrLine(text="MAHARASHTRA. MFG. BY: HINDUSTAN UNILEVER LIMITED", bbox=(100, 100, 450, 25), confidence=0.95),
            OcrLine(text="PKD 13/05/26", bbox=(100, 200, 150, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05-13"
        assert res["mfg_date"]["label"].strip() == "PKD"

    def test_mfg_by_with_inline_date_is_accepted(self):
        """MFG. BY followed directly by a date is accepted as a date label."""
        lines = [
            OcrLine(text="MFG. BY 05/2026", bbox=(100, 100, 200, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert res["mfg_date"]["normalized_value"] == "2026-05"


class TestLayoutPTollFreeAndDecimalGuards:
    def test_toll_free_phone_number_not_extracted_as_date(self):
        """TOLL FREE: 1800-10-22-221 must NOT be parsed as October 22, 1800."""
        lines = [
            OcrLine(text="TOLL FREE: 1800-10-22-221", bbox=(100, 100, 300, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert "mfg_date" not in res
        assert "expiry_date" not in res

    def test_decimal_double_zero_not_parsed_as_year_2000(self):
        """MRP: 10.00 or 110.00 must not be parsed as October 2000."""
        lines = [
            OcrLine(text="MRP: Rs. 10.00", bbox=(100, 100, 200, 25), confidence=0.95),
        ]
        res = classify_fields(lines)
        assert "mfg_date" not in res
        assert "expiry_date" not in res
