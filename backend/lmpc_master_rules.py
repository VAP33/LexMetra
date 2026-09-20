"""
LMPC Master Rule Register
Statutory legal metrology rules under the Legal Metrology (Packaged Commodities) Rules, 2011 (G.S.R. 202(E), 7th March 2011)
and Legal Metrology Act, 2009.
"""

from typing import List, Dict, Any, Optional

LMPC_MASTER_RULES: List[Dict[str, Any]] = [
    {
        "id": "RULE-3-SCOPE",
        "citation": "Rule 3, Chapter II",
        "chapter": "Chapter II - Provisions Applicable to Packages Intended for Retail Sale",
        "title": "Application of Chapter II to Retail Packages",
        "summary": "Provisions of Chapter II apply to all pre-packaged commodities intended for retail sale, except where specifically exempted under Rule 26.",
        "category_scope": "All Commodities",
        "is_mandatory": True,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Fine up to ₹25,000 (first offense), up to ₹50,000 (second), up to ₹1,00,000 or imprisonment up to 1 year for subsequent offenses.",
        "exemptions": [
            "Packages containing net quantity <= 10g or <= 10ml (except tobacco)",
            "Packages containing > 25kg or > 25L (except cement/fertilizer up to 50kg)",
            "Packages for industrial / institutional consumers for direct usage",
            "Export packages conforming to foreign market requirements"
        ]
    },
    {
        "id": "RULE-6-1-A-NAME-ADDRESS",
        "citation": "Rule 6(1)(a)",
        "chapter": "Chapter II - Declarations on Retail Packages",
        "title": "Name & Address of Manufacturer / Packer / Importer",
        "summary": "Every package must bear the name and complete address of the manufacturer, or where manufacturer is not packer, the packer, and for imported goods, the importer.",
        "category_scope": "All Commodities",
        "is_mandatory": True,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Non-compoundable without rectification; fine up to ₹25,000 for first violation.",
        "exemptions": [
            "Rule 26(a): Net quantity <= 10g / 10ml",
            "Rule 26(b): Agricultural / fast food wrapped in presence of purchaser"
        ]
    },
    {
        "id": "RULE-6-1-B-GENERIC-NAME",
        "citation": "Rule 6(1)(b)",
        "chapter": "Chapter II - Declarations on Retail Packages",
        "title": "Generic or Common Name of Commodity",
        "summary": "The common or generic names of the commodity contained in the package and in case of packages with more than one product, the name and number or quantity of each.",
        "category_scope": "All Commodities",
        "is_mandatory": True,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Fine up to ₹25,000 for misleading or omitted generic commodity designation.",
        "exemptions": [
            "Rule 26(a): Net quantity <= 10g or 10ml"
        ]
    },
    {
        "id": "RULE-6-1-C-NET-QUANTITY",
        "citation": "Rule 6(1)(c) read with Rule 11 & 12",
        "chapter": "Chapter II - Declarations on Retail Packages",
        "title": "Net Quantity in Standard Units of Weight, Measure or Number",
        "summary": "The net quantity in terms of the standard unit of weight or measure or number of commodity contained in the package, conforming to Schedule I Maximum Permissible Errors.",
        "category_scope": "All Commodities",
        "is_mandatory": True,
        "penal_section": "Section 36(1) & 36(2), LM Act 2009",
        "penalty_description": "Short quantity attracts penalty up to ₹50,000 and potential seizure of non-compliant batch.",
        "exemptions": [
            "Rule 26(a): <= 10g / <= 10ml",
            "Schedule II specifies commodities that must be sold by weight or volume"
        ]
    },
    {
        "id": "RULE-6-1-D-DATE-MFG-PACK",
        "citation": "Rule 6(1)(d)",
        "chapter": "Chapter II - Declarations on Retail Packages",
        "title": "Month & Year of Manufacture / Packing / Import",
        "summary": "The month and year in which the commodity is manufactured or pre-packed or imported, enabling consumer awareness of shelf-life and vintage.",
        "category_scope": "All Commodities",
        "is_mandatory": True,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Fine up to ₹25,000; date obliteration or smudging treated as deliberate alteration.",
        "exemptions": [
            "Bidis and incense sticks exempted from date requirement",
            "Commodities with 'Best Before / Use by' permitted to display only date of expiry if shelf-life < 3 months"
        ]
    },
    {
        "id": "RULE-6-1-E-MRP",
        "citation": "Rule 6(1)(e)",
        "chapter": "Chapter II - Declarations on Retail Packages",
        "title": "Maximum Retail Price (MRP) Inclusive of All Taxes",
        "summary": "Maximum Retail Price in the format 'MRP ₹ xx.xx (inclusive of all taxes)' or 'Maximum Retail Price ₹ xx.xx (incl. of all taxes)'. Dual pricing on identical packages prohibited.",
        "category_scope": "All Commodities",
        "is_mandatory": True,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Overcharging above declared MRP attracts stringent prosecution and compounding fines.",
        "exemptions": [
            "Rule 26(b): Industrial consumers buying directly from manufacturer",
            "Rule 26(c): Institutional consumers (railways, hotels, airlines) for own service"
        ]
    },
    {
        "id": "RULE-6-1-11-UNIT-SALE-PRICE",
        "citation": "Rule 6(11) (G.S.R. 779(E) Amendment)",
        "chapter": "Chapter II - Declarations on Retail Packages",
        "title": "Unit Sale Price (USP) Declaration",
        "summary": "Mandatory declaration of unit sale price per gram, per kilogram, per millilitre, per litre or per number wherever package contains more than 1 unit/kg/L.",
        "category_scope": "Retail Packages with weight > 1g or volume > 1ml",
        "is_mandatory": True,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Fine up to ₹25,000 for omission or miscalculation of unit rate.",
        "exemptions": [
            "Packages containing exact 1g, 1kg, 1ml, 1L, or 1 number do not require duplicate USP declaration"
        ]
    },
    {
        "id": "RULE-6-1-F-CONSUMER-CARE",
        "citation": "Rule 6(1)(f)",
        "chapter": "Chapter II - Declarations on Retail Packages",
        "title": "Consumer Care Details & Grievance Contact",
        "summary": "Name, address, telephone number and email address of the person or office which can be contacted in case of consumer complaints or grievances.",
        "category_scope": "All Commodities",
        "is_mandatory": True,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Fine up to ₹25,000 for invalid, disconnected, or missing helpline credentials.",
        "exemptions": [
            "Rule 26(a): <= 10g or <= 10ml packages"
        ]
    },
    {
        "id": "RULE-6-10-COUNTRY-OF-ORIGIN",
        "citation": "Rule 6(10) (G.S.R. 583(E))",
        "chapter": "Chapter II - Declarations on Retail Packages",
        "title": "Country of Origin for Imported Packages",
        "summary": "Every imported package shall prominently declare the country of manufacture or country of origin.",
        "category_scope": "Imported Commodities & Global Trade",
        "is_mandatory": True,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Seizure and fine up to ₹50,000 for false or masked country of origin.",
        "exemptions": [
            "Indigenous commodities manufactured within India (marked 'Made in India')"
        ]
    },
    {
        "id": "RULE-7-FONT-SIZE-SCHEDULE-II",
        "citation": "Rule 7 read with Schedule II",
        "chapter": "Chapter II - Declaration Standards",
        "title": "Height of Numerals & Letters on Principal Display Panel",
        "summary": "Minimum height of letters and numerals on PDP based on area: Area <= 50 cm²: min 1.0mm (blown/moulded 2.0mm); 50-200 cm²: min 2.0mm (blown 4.0mm); 200-1000 cm²: min 4.0mm; > 1000 cm²: min 6.0mm.",
        "category_scope": "All Commodities",
        "is_mandatory": True,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Prosecution for illegible, truncated or microscopic declaration typography.",
        "exemptions": [
            "Blown, formed, moulded or perforated containers have specific Schedule II multiplier table"
        ]
    },
    {
        "id": "RULE-9-CONTRAST-READABILITY",
        "citation": "Rule 9(1)",
        "chapter": "Chapter II - Declaration Standards",
        "title": "Manner and Prominence of Mandatory Declarations",
        "summary": "Every declaration shall be legible, distinct, conspicuous, and clearly visible. Background color contrast must ensure effortless readability without camouflage.",
        "category_scope": "All Commodities",
        "is_mandatory": True,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Notice for deceptive typography or camouflage printing.",
        "exemptions": []
    },
    {
        "id": "RULE-18-NO-PRICE-ALTERATION",
        "citation": "Rule 18(2)",
        "chapter": "Chapter II - Declarations on Retail Packages",
        "title": "Prohibition on Sticker Overwriting & Alteration of Price",
        "summary": "No person shall alter, smudge, or overwrite the maximum retail price declared on the package by affixing fresh stickers or stamping higher prices, except as permitted under statutory GST rate transitions.",
        "category_scope": "All Commodities",
        "is_mandatory": True,
        "penal_section": "Section 36(1) & Section 53, LM Act 2009",
        "penalty_description": "Strict liability offense; cancellation of trading authorization and seizure.",
        "exemptions": [
            "Official transitional notification issued by DCA for downward tax rate adjustment"
        ]
    },
    {
        "id": "RULE-24-WHOLESALE-PACKAGES",
        "citation": "Rule 24, Chapter III",
        "chapter": "Chapter III - Provisions Applicable to Wholesale Packages",
        "title": "Declarations on Wholesale Packages",
        "summary": "Wholesale packages must declare name & address of manufacturer, generic identity of commodity, net quantity in metric units, and total number of retail packages contained.",
        "category_scope": "Wholesale / Distribution Packages",
        "is_mandatory": False,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Fine up to ₹25,000 for unlabelled wholesale shippers.",
        "exemptions": [
            "Retail packages contained within are governed separately by Chapter II"
        ]
    },
    {
        "id": "RULE-25-EXPORT-EXEMPTION",
        "citation": "Rule 25, Chapter IV",
        "chapter": "Chapter IV - Export Packages",
        "title": "Export Package Exemption",
        "summary": "Packages intended strictly for export outside India are exempt from Chapter II declarations provided they conform to destination nation standards and bear 'For Export Only'.",
        "category_scope": "Export Commodities",
        "is_mandatory": False,
        "penal_section": "Section 36(1), LM Act 2009",
        "penalty_description": "Diversion of export packages to domestic retail constitutes statutory evasion.",
        "exemptions": [
            "Fully exempt from domestic LMPC rules if marked 'FOR EXPORT ONLY'"
        ]
    },
    {
        "id": "RULE-26-EXEMPTIONS",
        "citation": "Rule 26, Chapter V",
        "chapter": "Chapter V - Exemptions in Respect of Certain Packages",
        "title": "General Statutory Exemptions",
        "summary": "Exempts: (a) packages <= 10g or <= 10ml (except tobacco); (b) packages > 25kg or > 25L (except cement/fertilizer up to 50kg); (c) packaged commodities for industrial consumers; (d) institutional consumers.",
        "category_scope": "All Qualifying Packages",
        "is_mandatory": False,
        "penal_section": "N/A - Exemption Statute",
        "penalty_description": "Misuse of exemption category constitutes deliberate non-compliance.",
        "exemptions": [
            "Applies as statutory safe harbor when conditions are proven by invoice"
        ]
    }
]

def get_lmpc_master_rule_register() -> List[Dict[str, Any]]:
    """Returns the full master rule register."""
    return LMPC_MASTER_RULES

def evaluate_contextual_rule_applicability(
    product_category: Optional[str] = None,
    sale_type: Optional[str] = None,
    net_quantity_val: Optional[float] = None,
    net_quantity_unit: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Evaluates each master rule against specific package parameters
    and tags status: APPLICABLE, EXEMPT, or CONDITIONAL.
    """
    category_norm = (product_category or "").lower()
    sale_type_norm = (sale_type or "retail").lower()
    unit_norm = (net_quantity_unit or "").lower()

    is_small_pack = False
    if net_quantity_val is not None:
        if unit_norm in ["g", "gm", "gram", "ml", "milli"] and net_quantity_val <= 10.0:
            is_small_pack = True

    is_bulk = False
    if net_quantity_val is not None:
        if unit_norm in ["kg", "kilogram", "l", "litre", "liter"] and net_quantity_val > 25.0:
            if "cement" not in category_norm and "fertilizer" not in category_norm:
                is_bulk = True

    is_export = sale_type_norm in ["export", "export_only"]
    is_wholesale = sale_type_norm in ["wholesale", "shipper", "bulk"]
    is_institutional = sale_type_norm in ["institutional", "industrial"]

    results = []
    for rule in LMPC_MASTER_RULES:
        rule_id = rule["id"]
        status = "APPLICABLE"
        context_note = "Mandatory statutory requirement for current retail package."

        if rule_id == "RULE-25-EXPORT-EXEMPTION":
            if is_export:
                status = "ACTIVE_EXEMPTION"
                context_note = "Package marked for export. Domestic retail rules superseded."
            else:
                status = "NOT_APPLICABLE"
                context_note = "Commodity intended for domestic sale; export exemption does not apply."

        elif rule_id == "RULE-24-WHOLESALE-PACKAGES":
            if is_wholesale:
                status = "APPLICABLE"
                context_note = "Wholesale shipper packaging standard actively applies."
            else:
                status = "NOT_APPLICABLE"
                context_note = "Individual retail package evaluated; wholesale shipper rule inactive."

        elif is_export:
            status = "EXEMPT"
            context_note = "Exempt under Rule 25 (Export Package Exemption)."

        elif is_institutional:
            if rule_id in ["RULE-6-1-E-MRP", "RULE-6-1-11-UNIT-SALE-PRICE"]:
                status = "EXEMPT"
                context_note = "Exempt under Rule 26(c) (Direct Institutional/Industrial Consumer Supply)."

        elif is_small_pack:
            if rule_id in ["RULE-6-1-A-NAME-ADDRESS", "RULE-6-1-B-GENERIC-NAME", "RULE-6-1-C-NET-QUANTITY", "RULE-6-1-F-CONSUMER-CARE"]:
                status = "EXEMPT"
                context_note = f"Exempt under Rule 26(a): Net quantity <= 10{unit_norm or 'g'}."

        elif is_bulk:
            status = "EXEMPT"
            context_note = f"Exempt under Rule 26(b): Package net quantity > 25{unit_norm or 'kg'}."

        results.append({
            **rule,
            "evaluation_status": status,
            "context_note": context_note
        })

    return results
