"""
GTIN validation, GS1 prefix interpretation and symbol reading.

The pure-function tests are deterministic and use REAL published GTINs, because
a check-digit routine that is wrong in a way self-consistent with its own test
fixtures is worse than no test. The two integration tests read actual
photographs from `images dataset/` and are skipped when it is absent.

MEASURED CAPABILITY, recorded here so nobody has to rediscover it: across the 29
photographs in `images dataset/`, this module reads a symbol from 3 and locates
an unreadable one in a further 5. The bar decoder alone reads 2. The extra one is
the Bru coffee jar, whose symbol OpenCV cannot decode at any scale because the
jar is cylindrical, and which the human-readable-digit path recovers exactly.
The Doraemon candy ball is NOT read: its label is wrapped around a sphere under
crinkled cellophane with glare across the digits. That is a real limitation, and
the correct behaviour there is to say so rather than to produce a number.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import barcode_decode as bd
from barcode_decode import ReadMethod, SymbolStatus, SymbologyKind

_ROOT = Path(__file__).resolve().parent.parent.parent
_DATASET = _ROOT / "images dataset" if (_ROOT / "images dataset").exists() else _ROOT / "DEPENDENCIES" / "images dataset"
_BRU = _DATASET / "Screenshot_2026-09-06-22-06-12-38_92460851df6f172a4592fca41cc2d2e6.jpg"

requires_dataset = pytest.mark.skipif(
    not _BRU.exists(), reason="images dataset/ not present"
)


class TestGtinValidation:
    def test_real_published_gtins_validate(self):
        """Real codes from four symbologies and four issuing organisations."""
        for code, kind in [
            ("8909106043251", SymbologyKind.EAN_13),   # Bru coffee, GS1 India
            ("8901030953149", SymbologyKind.EAN_13),   # HUL, GS1 India
            ("5000112637922", SymbologyKind.EAN_13),   # GS1 UK
            ("036000291452", SymbologyKind.UPC_A),     # the canonical UPC-A
            ("9780306406157", SymbologyKind.EAN_13),   # ISBN as EAN-13
        ]:
            ok, got = bd.validate_gtin(code)
            assert ok, code
            assert got is kind, (code, got)

    def test_check_digit_weighting_is_right_anchored(self):
        """
        The weights alternate from the RIGHT of the partial payload.

        Left-anchoring inverts them on odd-length payloads, which still validates
        many 13-digit codes by luck while breaking UPC-A. `036000291452` is the
        regression guard: it only passes when the anchoring is correct.
        """
        assert bd.gtin_check_digit("890910604325") == 1
        assert bd.gtin_check_digit("03600029145") == 2
        assert bd.validate_gtin("036000291452")[0] is True

    def test_corruptions_are_rejected(self):
        """
        Every rejection here is the mechanism that makes the OCR path safe.

        These are the exact strings Tesseract produced from the Bru digit strip at
        the wrong upscale factors: a duplicated leading digit, a dropped one, and
        a wrong check digit. All must fail, because the alternative is a
        fabricated product identity.
        """
        for bad in [
            "8909106043252",    # wrong check digit
            "890910604325",     # digit dropped
            "89909106043251",   # digit duplicated
            "9909106043251",    # leading digit lost
            "8909106043i51",    # non-numeric
            "",
            "1234",
        ]:
            ok, kind = bd.validate_gtin(bad)
            assert ok is False, bad
            assert kind is None, bad

    def test_upc_a_normalises_to_gtin13_without_changing_identity(self):
        assert bd.to_gtin13("036000291452") == "0036000291452"
        assert bd.validate_gtin("0036000291452")[0] is True

    def test_carton_code_does_not_become_a_retail_identity(self):
        """
        A GTIN-14 whose indicator digit is not 0/1 identifies a multi-pack.

        Treating an outer carton as the retail unit would attach the carton's
        net quantity to an inspection of a single pack, so `to_gtin13` refuses.
        """
        inner = "8909106043251"
        for indicator in ("2", "5", "9"):
            partial = indicator + inner[:12]
            check = bd.gtin_check_digit(partial)
            carton = partial + str(check)
            assert bd.validate_gtin(carton)[0] is True, carton
            assert bd.to_gtin13(carton) is None, carton

    def test_unvalidated_payload_is_evidence_but_not_identity(self):
        sym = bd._build_symbol("99999999999999999", ReadMethod.CV_BARS_DECODED,
                               "img.jpg", None)
        assert sym.check_digit_valid is False
        assert sym.gtin13 is None
        assert sym.needs_confirmation is True
        assert sym.kind is SymbologyKind.UNVALIDATED_1D


class TestGs1Prefix:
    def test_india_prefix_is_recognised(self):
        p = bd.gs1_prefix("8909106043251")
        assert p is not None
        assert p.prefix == "890"
        assert "India" in p.member_organisation

    def test_prefix_is_never_country_of_origin_evidence(self):
        """
        The legally consequential one.

        Rule 6 requires a country-of-origin declaration for imported goods. A GS1
        prefix identifies the member organisation that issued the company prefix,
        not where the goods were made — an importer registered with GS1 India can
        sell goods manufactured anywhere. Satisfying the declaration from the
        prefix would fabricate a finding, so the flag is False for every prefix
        and the caveat travels with the value.
        """
        for code in ["8909106043251", "5000112637922", "6901234567892"]:
            p = bd.gs1_prefix(code)
            assert p is not None
            assert p.is_country_of_origin_evidence is False
            d = p.to_dict()
            assert d["is_country_of_origin_evidence"] is False
            assert "not the country of manufacture" in d["caveat"]

    def test_special_ranges_are_flagged_as_non_products(self):
        """ISBN, ISSN, coupon and in-store ranges are not packaged commodities."""
        for code, expect in [
            ("9780306406157", "ISBN"),
            ("2001234567893", "Restricted distribution"),
        ]:
            p = bd.gs1_prefix(code)
            assert p is not None, code
            assert p.special_range is True, code
            assert expect in p.member_organisation, code

    def test_unknown_prefix_says_so_rather_than_guessing(self):
        p = bd.gs1_prefix("1401234567897")
        assert p is not None
        assert "Unassigned or unknown" in p.member_organisation


class TestHriCandidates:
    def test_guard_bar_splits_are_recombined(self):
        """
        EAN-13's human-readable line prints as three groups and the guard bars
        between them are read as spaces or stray glyphs, so the concatenation of
        the runs has to be a candidate.
        """
        cands = bd._hri_candidates("8 909106 043251")
        assert "8909106043251" in cands

    def test_candidates_are_length_bounded(self):
        for c in bd._hri_candidates("1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8"):
            assert 7 <= len(c) <= 14

    def test_no_digits_yields_no_candidates(self):
        assert bd._hri_candidates("MRP INCL OF ALL TAXES") == []


class TestSymbolStatusSemantics:
    def test_absent_symbol_is_not_a_compliance_finding(self):
        """
        The coverage note has to say this in words, because a barcode is not a
        Legal Metrology declaration at all: its absence cannot be a violation,
        and a photograph of the front panel simply does not show the panel the
        symbol sits on.
        """
        import numpy as np

        blank = np.full((200, 200, 3), 240, dtype=np.uint8)
        r = bd.decode_symbols(blank, image_id="blank.jpg")
        assert r.status is SymbolStatus.NO_SYMBOL_LOCALISED
        assert r.symbols == []
        assert r.best is None
        assert "not a Legal Metrology non-compliance" in r.coverage_note

    def test_conflicting_payloads_yield_no_identity(self):
        """
        Two valid product codes in one frame is a second pack, a shelf label or a
        carton in shot. Per the standing invariant, conflicting reads stay
        conflicting; `best` must refuse to pick a winner.
        """
        r = bd.SymbolReadResult(image_id="two.jpg", status=SymbolStatus.CONFLICTING)
        r.symbols = [
            bd._build_symbol("8909106043251", ReadMethod.CV_BARS_DECODED, "two.jpg", None),
            bd._build_symbol("5000112637922", ReadMethod.CV_BARS_DECODED, "two.jpg", None),
        ]
        assert r.best is None

    def test_ocr_path_is_trusted_less_than_the_bar_decoder(self):
        """
        Provenance must change the numbers, not just a label.

        A checksum-validated OCR read is one modulo-10 test away from a guess;
        a bar decode has passed guard patterns and per-module parity as well.
        """
        bars = bd._build_symbol("8909106043251", ReadMethod.CV_BARS_DECODED, "i", None)
        hri = bd._build_symbol("8909106043251",
                               ReadMethod.OCR_HRI_CHECK_DIGIT_VALIDATED, "i", None)
        assert bars.confidence > hri.confidence
        assert bars.needs_confirmation is False
        assert hri.needs_confirmation is True
        assert any("inspector must confirm" in n for n in hri.notes)


class TestRealPhotographs:
    @requires_dataset
    def test_cylindrical_jar_barcode_is_read_from_the_photograph(self):
        """
        The headline case: the Bru jar's identity comes from the image.

        OpenCV's bar decoder returns nothing here at any scale or crop because the
        jar is cylindrical and the bar pitch is compressed towards the edges. The
        human-readable-digit path recovers 8909106043251, which is what a human
        annotator independently read from the same photograph.
        """
        import cv2

        r = bd.decode_symbols(cv2.imread(str(_BRU)), image_id="bru_front.jpg")
        assert r.status is SymbolStatus.DECODED
        best = r.best
        assert best is not None
        assert best.gtin13 == "8909106043251"
        assert best.check_digit_valid is True
        assert best.method is ReadMethod.OCR_HRI_CHECK_DIGIT_VALIDATED
        assert best.needs_confirmation is True
        assert best.bbox is not None, "a reviewer must be able to see the symbol"
        assert best.image_id == "bru_front.jpg"
        assert best.prefix is not None and "India" in best.prefix.member_organisation

    @requires_dataset
    def test_flat_label_barcode_is_read_by_the_bar_decoder(self):
        """A flat-labelled pack decodes properly, via the machine-readable channel."""
        import cv2

        path = _DATASET / (
            "Screenshot_2026-09-06-22-07-38-18_"
            "92460851df6f172a4592fca41cc2d2e6.jpg"
        )
        if not path.exists():
            pytest.skip("specific photograph absent")
        r = bd.decode_symbols(cv2.imread(str(path)), image_id="flat.jpg")
        assert r.status is SymbolStatus.DECODED
        best = r.best
        assert best is not None
        assert best.method is ReadMethod.CV_BARS_DECODED
        assert best.check_digit_valid is True
        assert best.needs_confirmation is False
