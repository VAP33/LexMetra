"""
Synthetic regulation text used by most unit tests.

Modeled on the drafting style of India's Legal Metrology (Packaged
Commodities) Rules (numbered headings, "NUMBER. Title.—Text" style,
sub-rules in parenthesised numbers) but entirely fabricated for testing:
no real legal content should be assumed here.

Deliberately includes the concrete false-positive shapes named in the
brief — an isolated year, a page-footer-style number, a Gazette reference,
and a quantity table — interleaved with real headings, so
``rule_detection`` tests can assert that the noise is rejected while the
real headings survive.
"""

from __future__ import annotations

from typing import List

from lexmetra_rules.models import PageText, TextSource

PAGE_1_TEXT = """\
GOVERNMENT OF INDIA
MINISTRY OF CONSUMER AFFAIRS
Legal Metrology (Packaged Commodities) Rules, 2011
G.S.R. 629(E).—In exercise of the powers conferred by section 52 read
with sub-section (1) of section 11 of the Legal Metrology Act, 2009,
the Central Government hereby makes the following rules.

1. Short title and commencement.—These rules may be called the Legal
Metrology (Packaged Commodities) Rules, 2011. They shall come into
force with effect from 1 April 2011.

2. Definitions.—In these rules, unless the context otherwise requires,
"pre-packaged commodity" means a commodity which is placed in a
package of whatever nature, whether sealed or not, so that the
product contained therein has a pre-determined quantity.
"""

PAGE_2_TEXT = """\
Page 2

3. Exemption in respect of certain packages.—Nothing contained in
these rules shall apply to any package containing a commodity if the
net weight or measure of the commodity is ten grams or ten
millilitres or less, if sold by weight or measure, provided that
this exemption shall not extend to packages of tobacco or tobacco
products or pan masala.

4. Declaration on packages of food articles.—Every package containing
a food article intended for human consumption shall bear a
declaration of the common name of the commodity, the net quantity in
terms of standard units of weight, measure or number, and shall
comply with the labelling requirements of the Food Safety and
Standards Authority of India (FSSAI).
"""

PAGE_3_TEXT = """\
44. Continued overleaf from the previous section of the notification.

5. Declaration on cosmetics.—Every package of a cosmetic, including
soap, shampoo, or toiletry preparation, shall bear the name of the
manufacturer, the net quantity, and the date of manufacture. This
rule shall not apply to samples not intended for retail sale.

2011. All rights of the publisher in this Gazette are reserved.

6. Declarations on every package.—Every package shall bear thereon or
on a label securely affixed thereto the following declarations,
namely:—
(1) the name and address of the manufacturer or packer or importer;
(2) the common or generic name of the commodity;
(3) the net quantity in terms of the standard unit of weight,
measure or number;
(11) the unit sale price of the commodity, where the package
contains more than one piece or unit of the commodity.
"""

PAGE_4_TEXT = """\
Table 1: Sample quantities
500 1000 1500 2000
250 750 1250 1750

7. Declaration on imported packages.—Every package of an imported
commodity shall, in addition to the other declarations required
under these rules, declare the country of origin or manufacture or
assembly and the name and address of the importer.

8. Declaration on drug formulations.—Every package of a
patent or proprietary medicine or drug formulation shall bear the
name of the drug, the dosage, and shall comply with the labelling
requirements under the Drugs and Cosmetics Act. This rule shall not
apply to formulations exempted under Schedule K of the said Act.
"""

PAGE_5_TEXT = """\
9. Small package relaxation.—Where the net quantity of a
pre-packaged commodity does not exceed twenty grams or twenty
millilitres, the requirement to declare the maximum retail price
under rule 6 shall not apply, subject to the condition that the
package bears the declaration of net quantity prominently.

10. Soft drinks and aerated waters.—Every package of a soft drink,
aerated water, or ready to serve fruit beverage shall declare the
ingredients and the net quantity in terms of volume.

This amendment shall come into force with effect from 1 January
2018 and rule 6(11) shall stand superseded with effect from
1 January 2018 to the extent inconsistent herewith.
"""


def make_synthetic_pages() -> List[PageText]:
    """Five pages of native (non-OCR) text, confidence 1.0."""
    texts = [PAGE_1_TEXT, PAGE_2_TEXT, PAGE_3_TEXT, PAGE_4_TEXT, PAGE_5_TEXT]
    return [
        PageText(
            page_no=i + 1,
            text=text,
            source=TextSource.NATIVE,
            confidence=1.0,
            engine="pymupdf_text_layer",
        )
        for i, text in enumerate(texts)
    ]


FULL_TEXT = "\n".join([PAGE_1_TEXT, PAGE_2_TEXT, PAGE_3_TEXT, PAGE_4_TEXT, PAGE_5_TEXT])
