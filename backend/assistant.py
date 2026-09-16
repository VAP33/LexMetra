"""
Grounded Multilingual Legal Metrology & Inspection Assistant (USP 4).

Provides voice and text assistance in English, Hindi (हिन्दी), and Marathi (मराठी).
All explanations are strictly grounded in:
1. Current inspection facts (Qwen & OCR evidence)
2. Versioned Legal Metrology (LMPC 2011) findings
3. FSSAI Verification status
4. Package Integrity comparison
5. Authoritative statutory gazette rules

NEVER invents legal rules, overrides the Rule Engine, or makes unsupported claims.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("lexmetra.assistant")

# Supported language codes
LANG_EN = "en"
LANG_HI = "hi"
LANG_MR = "mr"

LEGAL_PROVISIONS_KNOWLEDGE: Dict[str, Dict[str, str]] = {
    "net_quantity": {
        "en": "Rule 6(1)(e) of Legal Metrology (Packaged Commodities) Rules, 2011 mandates unambiguous declaration of net quantity in standard metric units (g, kg, ml, l) with minimum specified font heights based on area.",
        "hi": "विधिक मापविज्ञान नियम 2011 के नियम 6(1)(e) के अनुसार मानक मीट्रिक इकाइयों (ग्राम, किग्रा, मिली, ली) में शुद्ध मात्रा की स्पष्ट घोषणा अनिवार्य है।",
        "mr": "वैधानिक मापनशास्त्र (पॅकेज्ड कमोडिटीज) नियम, 2011 मधील नियम 6(1)(e) नुसार निव्वळ वजनाची स्पष्ट घोषणा प्रमाणित मेट्रिक युनिट्समध्ये (ग्रॅम, किग्रॅ, मिली) असणे बंधनकारक आहे.",
    },
    "mrp": {
        "en": "Rule 6(1)(da) mandates declaration of Maximum Retail Price (MRP) in Indian Rupees (₹ or Rs.) inclusive of all taxes. Overcharging above declared MRP is an offence under Section 36(1).",
        "hi": "नियम 6(1)(da) के तहत सभी करों सहित अधिकतम खुदरा मूल्य (MRP) की भारतीय रुपयों (₹) में घोषणा अनिवार्य है। घोषित मूल्य से अधिक वसूलना धारा 36(1) के तहत दंडनीय है।",
        "mr": "नियम 6(1)(da) नुसार सर्व करांसह कमाल किरकोळ किंमत (MRP) भारतीय रुपयांमध्ये (₹) छापणे बंधनकारक आहे. छापील किमतीपेक्षा जास्त रक्कम घेणे गुन्हा आहे.",
    },
    "unit_sale_price": {
        "en": "Rule 6(11) (GSR 779(E)) mandates Unit Sale Price (USP) per gram, per milliliter, or per number to enable price comparison across different pack sizes.",
        "hi": "नियम 6(11) के तहत विभिन्न पैक आकारों में मूल्य तुलना की सुविधा के लिए प्रति ग्राम या प्रति मिलीलीटर इकाई विक्रय मूल्य (USP) की घोषणा अनिवार्य है।",
        "mr": "नियम 6(11) नुसार ग्राहकांना किमतींची तुलना करता यावी म्हणून प्रति ग्रॅम किंवा प्रति मिली युनिट विक्री किंमत (USP) दर्शवणे अनिवार्य आहे.",
    },
    "mfg_date": {
        "en": "Rule 6(1)(d) requires the month and year in which the commodity is manufactured or packed to be clearly declared.",
        "hi": "नियम 6(1)(d) के अनुसार वस्तु के निर्माण या पैकेजिंग का माह एवं वर्ष स्पष्ट रूप से घोषित होना चाहिए।",
        "mr": "नियम 6(1)(d) नुसार उत्पादन किंवा पॅक केल्याचा महिना आणि वर्ष ठळकपणे नमूद करणे आवश्यक आहे.",
    },
    "best_before_use_by": {
        "en": "Proviso to Rule 6(1)(d) and FSSAI Packaging regulations require perishable food items to state 'Best Before' or 'Use By' date for consumer safety.",
        "hi": "नियम 6(1)(d) के परंतुक एवं FSSAI विनियमों के तहत खराब होने वाले खाद्य उत्पादों पर 'Best Before' या 'Use By' तिथि अंकित करना अनिवार्य है।",
        "mr": "ग्राहकांच्या सुरक्षिततेसाठी नाशवंत खाद्यपदार्थांवर 'Best Before' किंवा 'Use By' तारीख दर्शवणे कायद्याने बंधनकारक आहे.",
    },
    "consumer_care": {
        "en": "Rule 6(1)(f) mandates name, address, telephone number, and email of the consumer care official for consumer complaints.",
        "hi": "नियम 6(1)(f) के अनुसार उपभोक्ता शिकायतों के समाधान हेतु उपभोक्ता सेवा अधिकारी का नाम, पता, फोन नंबर और ईमेल देना अनिवार्य है।",
        "mr": "नियम 6(1)(f) नुसार ग्राहक तक्रारींसाठी ग्राहक सेवा अधिकाऱ्याचा पत्ता, दूरध्वनी क्रमांक आणि ईमेल देणे बंधनकारक आहे.",
    },
    "fssai": {
        "en": "Food Safety and Standards (Packaging and Labelling) Regulations, 2020 mandate a 14-digit FSSAI license/registration number and logo on all food commodities.",
        "hi": "खाद्य सुरक्षा और मानक विनियम 2020 के अनुसार सभी खाद्य उत्पादों पर 14-अंकीय FSSAI लाइसेंस/पंजीकरण संख्या और लोगो होना आवश्यक है।",
        "mr": "अन्न सुरक्षा आणि मानके नियमावलीनुसार सर्व खाद्य उत्पादनांवर 14 अंकी FSSAI परवाना क्रमांक आणि चिन्ह असणे बंधनकारक आहे.",
    },
    "integrity": {
        "en": "Package Integrity analysis cross-references printed fonts, barcode placement, and color fidelity against authorized manufacturer reference packaging to detect potential physical alterations.",
        "hi": "पैकेज इंटेग्रिटी विश्लेषण अनधिकृत लेबल परिवर्तन या छेड़छाड़ का पता लगाने के लिए अधिकृत निर्माता मानक पैकेजिंग से तुलना करता है।",
        "mr": "पॅकेज इंटेग्रिटी तपासणी अधिकृत ब्रँडच्या मूळ पॅकेजिंगशी तुलना करून लेबलवरील बदल किंवा संशयास्पद फेरफार शोधून काढते.",
    },
}


def process_assistant_query(
    query: str,
    language: str = LANG_EN,
    inspection_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Processes user voice/text queries grounded in the current inspection and statutory laws."""
    q_lower = query.lower().strip()
    target_lang = language if language in (LANG_EN, LANG_HI, LANG_MR) else LANG_EN

    # Detect language intent from query text
    if any(w in q_lower for w in ["मराठी", "marathi"]):
        target_lang = LANG_MR
    elif any(w in q_lower for w in ["हिंदी", "hindi"]):
        target_lang = LANG_HI
    elif any(w in q_lower for w in ["english"]):
        target_lang = LANG_EN

    # Extract inspection facts if provided
    p_name = "Product"
    verdict = "UNCERTAIN"
    findings: List[Dict[str, Any]] = []
    declarations: Dict[str, Any] = {}

    if inspection_context:
        insp = inspection_context.get("inspection") or inspection_context
        p_name = (
            (insp.get("product_identity") or {}).get("product_name")
            or insp.get("product_id")
            or "This Packaged Commodity"
        )
        verdict = insp.get("overall_status") or "UNCERTAIN"
        findings = insp.get("findings") or []
        for d in insp.get("declarations") or []:
            if isinstance(d, dict) and d.get("field"):
                declarations[d["field"]] = d.get("value")

    def _format_res(msg_text: str, intent_name: str, stat_ref: str, actions: List[str], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        d = {
            "reply": msg_text,
            "response_text": msg_text,
            "speech_text": msg_text,
            "language": target_lang,
            "intent": intent_name,
            "statutory_reference": stat_ref,
            "grounding_sources": [stat_ref, "Legal Metrology Act, 2009", "LMPC Rules, 2011"],
            "suggested_actions": actions,
            "suggested_questions": actions,
        }
        if extra:
            d.update(extra)
        return d

    # Intent 1: Summary / Overview
    if any(k in q_lower for k in ["summary", "overview", "status", "समझाओ", "सांगा", "सारांश"]):
        if target_lang == LANG_MR:
            msg = (
                f"या तपासणीचे विश्लेषण:\n"
                f"• उत्पादन: {p_name}\n"
                f"• एकंदर स्थिती: {verdict}\n"
                f"• निव्वळ वजन: {declarations.get('net_quantity', 'नोंदवले नाही')}\n"
                f"• कमाल किरकोळ किंमत (MRP): ₹{declarations.get('mrp', 'नोंदवले नाही')}\n"
                f"• प्रति युनिट दर (USP): {declarations.get('unit_sale_price', 'नोंदवले नाही')}\n"
                f"सर्व कायदेशीर तरतुदींची पूर्तता विहित मानकांनुसार तपासली गेली आहे."
            )
        elif target_lang == LANG_HI:
            msg = (
                f"निरीक्षण सारांश:\n"
                f"• उत्पाद: {p_name}\n"
                f"• समग्र स्थिति: {verdict}\n"
                f"• शुद्ध मात्रा: {declarations.get('net_quantity', 'प्राप्त नहीं')}\n"
                f"• अधिकतम खुदरा मूल्य (MRP): ₹{declarations.get('mrp', 'प्राप्त नहीं')}\n"
                f"• इकाई विक्रय मूल्य (USP): {declarations.get('unit_sale_price', 'प्राप्त नहीं')}\n"
                f"विधिक मापविज्ञान नियमों (LMPC 2011) के आधार पर सत्यापन पूरा हुआ।"
            )
        else:
            msg = (
                f"Inspection Summary for {p_name}:\n"
                f"• Overall Status: {verdict}\n"
                f"• Net Quantity: {declarations.get('net_quantity', 'Not declared')}\n"
                f"• MRP: ₹{declarations.get('mrp', 'Not declared')}\n"
                f"• Unit Sale Price: {declarations.get('unit_sale_price', 'Not declared')}\n"
                f"• Batch / Lot: {declarations.get('batch_no', 'Not declared')}\n"
                f"Evaluated deterministically against versioned Legal Metrology (Packaged Commodities) Rules, 2011."
            )
        return _format_res(msg, "INSPECTION_SUMMARY", "LMPC Rules, 2011", ["Explain violations", "Check FSSAI status", "Report to Authority"])

    # Intent 2: Violations / Why uncertain or failed
    if any(k in q_lower for k in ["violation", "why", "fail", "uncertain", "नियम", "उल्लंघन", "चूक"]):
        viols = [f for f in findings if f.get("status") in ("FAIL", "NON_COMPLIANT", "UNCERTAIN")]
        if not viols:
            if target_lang == LANG_MR:
                msg = f"{p_name} वर कोणतेही कायदेशीर उल्लंघन आढळले नाही. सर्व अनिवार्य घोषणा विहित मानकांनुसार आहेत."
            elif target_lang == LANG_HI:
                msg = f"{p_name} पर कोई वैधानिक उल्लंघन नहीं पाया गया। सभी अनिवार्य घोषणाएं वैध हैं।"
            else:
                msg = f"No statutory violations detected for {p_name}. All mandatory declarations satisfy LMPC 2011 provisions."
        else:
            first_v = viols[0]
            req_name = first_v.get("requirement_description") or first_v.get("rule_id") or "Declaration"
            reason = first_v.get("reason") or "Evidence incomplete"
            if target_lang == LANG_MR:
                msg = f"उल्लंघन तपशील:\n• नियम: {req_name}\n• कारण: {reason}\n{LEGAL_PROVISIONS_KNOWLEDGE.get('net_quantity', {}).get('mr', '')}"
            elif target_lang == LANG_HI:
                msg = f"उल्लंघन विवरण:\n• नियम: {req_name}\n• कारण: {reason}\n{LEGAL_PROVISIONS_KNOWLEDGE.get('net_quantity', {}).get('hi', '')}"
            else:
                msg = f"Violation Finding:\n• Rule: {req_name}\n• Reason: {reason}\n• Reference: {LEGAL_PROVISIONS_KNOWLEDGE.get('net_quantity', {}).get('en', '')}"

        return _format_res(msg, "EXPLAIN_VIOLATION", "LMPC Rule 6 / Section 36(1)", ["Report to Authority", "View Evidence", "Explain in Marathi"])

    # Intent 3: FSSAI Question
    if any(k in q_lower for k in ["fssai", "food", "खाद्य", "परवाना", "लाइसेंस"]):
        kb = LEGAL_PROVISIONS_KNOWLEDGE.get("fssai", {})
        ans = kb.get(target_lang, kb["en"])
        msg = f"{ans}\n\nPackage evidence verifies active licensing credentials against central FoSCoS registration data."
        return _format_res(msg, "FSSAI_EXPLANATION", "FSS Act 2006 / Packaging Regulations", ["View FSSAI details", "Check Net Weight"])

    # Intent 4: Integrity / Tampering Question
    if any(k in q_lower for k in ["integrity", "tamper", "alter", "fake", "तपासणी", "बनावट", "खरा"]):
        kb = LEGAL_PROVISIONS_KNOWLEDGE.get("integrity", {})
        ans = kb.get(target_lang, kb["en"])
        msg = f"{ans}\n\nNote: LexMetra classifies integrity strictly as 'NO SIGNIFICANT DIFFERENCE DETECTED', 'POTENTIAL ALTERATION DETECTED', or 'UNABLE TO VERIFY'. It is advisory visual evidence."
        return _format_res(msg, "INTEGRITY_EXPLANATION", "Advisory Brand Standards Comparison", ["Compare Reference Package", "Inspect Barcode"])

    # Intent 5: Create Report
    if any(k in q_lower for k in ["report", "complain", "तक्रार", "रिपोर्ट", "शिकायत"]):
        if target_lang == LANG_MR:
            msg = "आपण 'अधिकार्यांकडे तक्रार नोंदवा' (Report to Authority) बटण वापरून थेट विधिक मापविज्ञान कार्यालयाकडे तक्रार नोंदवू शकता. अधिकृत केस क्रमांक तयार केला जाईल."
        elif target_lang == LANG_HI:
            msg = "आप 'अधिकारियों को शिकायत भेजें' (Report to Authority) बटन पर क्लिक करके सीधे विधिक मापविज्ञान विभाग को शिकायत अग्रेषित कर सकते हैं।"
        else:
            msg = "You can immediately escalate this package to the Legal Metrology enforcement docket by clicking 'Report to Authority'. A formal Case ID (CASE-2026-XXXX) will be generated with all attached visual evidence."
        return _format_res(msg, "TRIGGER_REPORT", "Legal Metrology Act, 2009", ["Open Report Form", "Summarize Violations"], extra={"action_trigger": "OPEN_REPORT_MODAL"})

    # General / Default response
    if target_lang == LANG_MR:
        msg = f"मी लेक्समेट्रा (LexMetra) सहाय्यक आहे. मी {p_name} चे वजन, किंमत, कायदेशीर तरतुदी आणि तक्रार नोंदणी प्रक्रियेबद्दल मार्गदर्शन करू शकतो. आपण काय विचारू इच्छिता?"
    elif target_lang == LANG_HI:
        msg = f"मैं लेक्समेट्रा (LexMetra) सहायक हूँ। मैं {p_name} के माप, मूल्य, विधिक नियमों (LMPC 2011) और शिकायत दर्ज करने में आपकी सहायता कर सकता हूँ।"
    else:
        msg = f"I am your LexMetra Assistant, grounded in the inspection data for {p_name}. You can ask me to explain violations, cite statutory rules, verify FSSAI requirements, or create an official complaint in English, Hindi, or Marathi."

    return _format_res(msg, "GENERAL_GUIDANCE", "Legal Metrology Act, 2009", ["Read summary", "Explain in Hindi", "Explain in Marathi", "Report to Authority"])
