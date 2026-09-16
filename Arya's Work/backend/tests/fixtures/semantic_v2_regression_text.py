"""
Fixture built specifically to reproduce and verify the fix for the
failure modes named in the semantic-extraction-upgrade brief:

  A. Rule 1's commencement date is identified as EFFECTIVE_DATE.
  B. Rule 2 does NOT incorrectly receive an unrelated "4 litre" threshold
     (the exact bug named in the brief).
  C. Rule 3's thresholds (25 kg / 25 litre / 50 kg) remain correctly
     associated with their own distinct applicability sub-clauses, not
     merged into one undifferentiated rule-level blob.
  D. Rule 6's enumerated requirements (name/address, common/generic name,
     net quantity, month/year, MRP) remain associated with the correct
     (inherited) obligation rather than becoming untyped fragments.
  E. Rule 7's numeric requirement (3 mm font height) stays bound to the
     labelling requirement it modifies, with a determinable `applies_to`,
     rather than floating as a standalone number.
  F. OCR-corrupted text lowers confidence rather than being blindly
     auto-accepted (see the OCR-degraded variant below).
"""

from __future__ import annotations

from lexmetra_rules.models import PageText, TextSource

CLEAN_TEXT = """\
1. Short title and commencement.\u2014These rules may be called the Test Rules,\
 2011. They shall come into force with effect from 1 April 2011.

2. Definitions.\u2014In these rules, "pre-packaged commodity" means a commodity\
 placed in a package, for example a 4 litre container of edible oil, so that\
 the quantity is predetermined.

3. Applicability of specific provisions.\u2014
(1) The provisions of rule 6 shall not apply to a package containing a\
 commodity if the net weight of the commodity does not exceed 25 kg.
(2) The provisions of rule 7 shall not apply to a package containing a\
 liquid commodity if the net volume of the commodity does not exceed 25 litre.
(3) Nothing in this rule shall apply to a package intended for industrial use\
 if the net weight of the commodity exceeds 50 kg.

6. Declarations on every package.\u2014Every package shall bear thereon or\
 on a label securely affixed thereto the following declarations, namely:\u2014
(1) the name and address of the manufacturer or packer or importer;
(2) the common or generic name of the commodity;
(3) the net quantity in terms of the standard unit of weight, measure or number;
(4) the month and year in which the commodity is manufactured or packed;
(5) the maximum retail price of the package.

7. Declaration of net quantity.\u2014Every package shall declare the net\
 quantity in a font not less than 3 mm in height on the principal display panel.
"""

# The same content as CLEAN_TEXT but with the specific OCR-corruption
# patterns named in the brief ("perscn", "shail", "1* day", "decleration")
# injected into Rule 7, to verify OCR-quality-aware confidence scoring.
OCR_DEGRADED_TEXT = """\
1. Short title and commencement.\u2014These rules may be called the Test Rules,\
 2011. They shall come into force with effect from 1 April 2011.

2. Definitions.\u2014In these rules, "pre-packaged commodity" means a commodity\
 placed in a package, for example a 4 litre container of edible oil, so that\
 the quantity is predetermined.

3. Applicability of specific provisions.\u2014
(1) The provisions of rule 6 shall not apply to a package containing a\
 commodity if the net weight of the commodity does not exceed 25 kg.

6. Declarations on every package.\u2014Every package shall bear thereon or\
 on a label securely affixed thereto the following declarations, namely:\u2014
(1) the name and address of the manufacturer or packer or importer;

7. Decleration of net quantity.\u2014Every perscn shail decleration the net\
 quantity in a font not less than 3 mm in height on the 1* day of packing.
"""


def make_clean_pages() -> list[PageText]:
    return [PageText(page_no=1, text=CLEAN_TEXT, source=TextSource.NATIVE, confidence=1.0)]


def make_ocr_degraded_pages() -> list[PageText]:
    """
    Simulates an OCR-sourced page (source=OCR, moderate engine confidence)
    whose text contains the specific corruption patterns named in the
    brief. Rule 7 here is the OCR-corrupted one; rules 1/2/3/6 stay clean
    so the test can confirm degraded confidence is localized to the
    actually-corrupted rule rather than applied blindly document-wide.
    """
    return [
        PageText(
            page_no=1,
            text=OCR_DEGRADED_TEXT,
            source=TextSource.OCR,
            confidence=0.55,
            engine="tesseract",
        )
    ]
