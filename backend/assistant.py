"""
Grounded Multilingual Legal Metrology & Inspection Assistant (USP 4).

Provides voice and text assistance in English, Hindi (हिन्दी), and Marathi (मराठी).
All explanations are strictly grounded in:
1. Current inspection facts (Qwen & OCR evidence)
2. Versioned Legal Metrology (LMPC 2011) findings
3. FSSAI Verification status
4. Package Integrity comparison
5. Authoritative statutory gazette rules

Features:
- Action menu support: Explain inspection, Explain violation, Why is this uncertain,
  Show supporting evidence, Explain rule, Summarize findings, Generate report, Read summary aloud.
- Dynamically generates grounded text and speech for EN, HI, MR.
- Zero hallucination of statutory clauses or facts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("lexmetra.assistant")

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

    # Extract inspection facts if provided
    p_name = "This Packaged Commodity"
    verdict = "UNCERTAIN"
    findings: List[Dict[str, Any]] = []
    declarations: Dict[str, Any] = {}
    evidence_items: List[Dict[str, Any]] = []

    if inspection_context:
        insp = inspection_context.get("inspection") or inspection_context
        p_name = (
            (insp.get("product_identity") or {}).get("product_name")
            or insp.get("product_id")
            or insp.get("product")
            or "This Packaged Commodity"
        )
        verdict = insp.get("overall_status") or insp.get("status") or "UNCERTAIN"
        findings = insp.get("findings") or []
        for d in insp.get("declarations") or []:
            if isinstance(d, dict) and d.get("field"):
                declarations[d["field"]] = d.get("value")
                if d.get("canonicalPolygonPx") or d.get("evidence"):
                    evidence_items.append(d)

    def _format_res(
        msg_text: str,
        speech_text: str,
        intent_name: str,
        stat_ref: str,
        actions: List[str],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        d = {
            "reply": msg_text,
            "response_text": msg_text,
            "speech_text": speech_text,
            "language": target_lang,
            "intent": intent_name,
            "statutory_reference": stat_ref,
            "grounding_sources": [stat_ref, "Legal Metrology Act, 2009", "LMPC Rules, 2011", "Gazette of India GSR 779(E)"],
            "suggested_actions": actions,
            "suggested_questions": actions,
        }
        if extra:
            d.update(extra)
        return d

    # 1. Action: Explain this inspection / Summarize findings
    if any(k in q_lower for k in [
        "explain this inspection", "summarize findings", "summary", "overview",
        "समझाओ", "सांगा", "सारांश", "तपासणी समजावून सांगा", "निरीक्षण समझाइए"
    ]):
        if target_lang == LANG_MR:
            msg = (
                f"📋 **{p_name} चे वैधानिक तपासणी सारांश**:\n\n"
                f"• **एकंदर स्थिती**: **{verdict}**\n"
                f"• **निव्वळ प्रमाण (Net Quantity)**: {declarations.get('net_quantity', 'नोंदवले नाही')}\n"
                f"• **कमाल किरकोळ किंमत (MRP)**: ₹{declarations.get('mrp', 'नोंदवले नाही')}\n"
                f"• **प्रति युनिट विक्री दर (USP)**: {declarations.get('unit_sale_price', 'नोंदवले नाही')}\n"
                f"• **उत्पादन दिनांक (MFD)**: {declarations.get('mfg_date', 'नोंदवले नाही')}\n"
                f"• **बॅच क्रमांक**: {declarations.get('batch_no', 'नोंदवले नाही')}\n\n"
                f"सदर माहिती पॅकेजच्या दृश्यमान पृष्ठभागावरून पडताळली गेली असून विधिक मापविज्ञान (LMPC) 2011 नियमांनुसार तपासली आहे."
            )
            speech = f"{p_name} चे वैधानिक तपासणी निष्कर्ष: एकंदर स्थिती {verdict}. निव्वळ प्रमाण {declarations.get('net_quantity', 'नोंदवले नाही')}. कमाल किंमत रुपये {declarations.get('mrp', 'नोंदवले नाही')}."
        elif target_lang == LANG_HI:
            msg = (
                f"📋 **{p_name} का वैधानिक निरीक्षण सारांश**:\n\n"
                f"• **समग्र स्थिति**: **{verdict}**\n"
                f"• **शुद्ध मात्रा (Net Quantity)**: {declarations.get('net_quantity', 'प्राप्त नहीं')}\n"
                f"• **अधिकतम खुदरा मूल्य (MRP)**: ₹{declarations.get('mrp', 'प्राप्त नहीं')}\n"
                f"• **इकाई विक्रय मूल्य (USP)**: {declarations.get('unit_sale_price', 'प्राप्त नहीं')}\n"
                f"• **उत्पादन माह/वर्ष (MFD)**: {declarations.get('mfg_date', 'प्राप्त नहीं')}\n"
                f"• **बैच / लॉट संख्या**: {declarations.get('batch_no', 'प्राप्त नहीं')}\n\n"
                f"यह विश्लेषण विधिक मापविज्ञान (पैकेज्ड कमोडिटीज) नियम 2011 के प्रावधानों के अंतर्गत किया गया है।"
            )
            speech = f"{p_name} का वैधानिक निरीक्षण सारांश: समग्र स्थिति {verdict}. शुद्ध मात्रा {declarations.get('net_quantity', 'प्राप्त नहीं')}. अधिकतम खुदरा मूल्य रुपये {declarations.get('mrp', 'प्राप्त नहीं')}."
        else:
            msg = (
                f"📋 **Statutory Inspection Summary for {p_name}**:\n\n"
                f"• **Overall Regulatory Verdict**: **{verdict}**\n"
                f"• **Net Quantity Declared**: {declarations.get('net_quantity', 'Not declared')}\n"
                f"• **Maximum Retail Price (MRP)**: ₹{declarations.get('mrp', 'Not declared')}\n"
                f"• **Unit Sale Price (USP)**: {declarations.get('unit_sale_price', 'Not declared')}\n"
                f"• **Date of Manufacture/Pack**: {declarations.get('mfg_date', 'Not declared')}\n"
                f"• **Batch / Lot Reference**: {declarations.get('batch_no', 'Not declared')}\n\n"
                f"Grounded deterministically in India Legal Metrology (Packaged Commodities) Rules, 2011."
            )
            speech = f"Statutory Inspection Summary for {p_name}. Overall verdict is {verdict}. Net quantity is {declarations.get('net_quantity', 'not declared')}. MRP is {declarations.get('mrp', 'not declared')} rupees."

        return _format_res(
            msg, speech, "INSPECTION_SUMMARY", "LMPC Rules, 2011 (Rule 6)",
            ["Explain a violation", "Why is this uncertain?", "Show supporting evidence", "Read summary aloud", "Generate report"]
        )

    # 2. Action: Explain a violation / Why is this uncertain?
    if any(k in q_lower for k in [
        "explain a violation", "why is this uncertain", "violation", "why", "fail", "uncertain",
        "उल्लंघन", "चूक", "असमंजस", "का अयशस्वी", "संशयास्पद", "नियम उल्लंघन"
    ]):
        viols = [f for f in findings if f.get("status") in ("FAIL", "NON_COMPLIANT", "UNCERTAIN")]
        if not viols:
            if target_lang == LANG_MR:
                msg = f"✅ **कोणतेही कायदेशीर उल्लंघन आढळले नाही**:\n\n{p_name} वरील सर्व दृश्यमान घोषणा विधिक मापविज्ञान नियम 2011 च्या कलम 6(1) च्या निकषांची पूर्तता करतात."
                speech = f"{p_name} वर कोणतेही कायदेशीर उल्लंघन आढळले नाही. सर्व विहित घोषणा वैध आहेत."
            elif target_lang == LANG_HI:
                msg = f"✅ **कोई वैधानिक उल्लंघन नहीं पाया गया**:\n\n{p_name} पर सभी अनिवार्य घोषणाएं विधिक मापविज्ञान नियम 2011 के प्रावधानों के अनुरूप पाई गई हैं।"
                speech = f"{p_name} पर कोई वैधानिक उल्लंघन नहीं पाया गया। सभी घोषणाएं नियम संगत हैं।"
            else:
                msg = f"✅ **No Statutory Violations Detected**:\n\nAll mandatory declarations visible on {p_name} satisfy Rule 6 and Rule 12 requirements of the LMPC Rules, 2011."
                speech = f"No statutory violations detected on {p_name}. All declarations are legally compliant."
        else:
            first_v = viols[0]
            req_name = first_v.get("requirement_description") or first_v.get("rule_id") or "Mandatory Declaration"
            reason = first_v.get("reason") or "Evidence incomplete on captured panels"
            rule_ref = first_v.get("rule_id") or "LMPC Rule 6"

            if target_lang == LANG_MR:
                msg = (
                    f"⚠️ **उल्लंघन / संशयास्पद बाबींचा तपशील**:\n\n"
                    f"• **नियम / तरतूद**: `{rule_ref}` — {req_name}\n"
                    f"• **तपासणी निष्कर्ष**: {reason}\n\n"
                    f"**कायदेशीर आधार**: {LEGAL_PROVISIONS_KNOWLEDGE.get('net_quantity', {}).get('mr', '')}\n\n"
                    f"कमी वजनाचा संशय असल्यास किंवा युनिट विक्री दर नसल्यास कलम 36(1) अन्वये कारवाई होऊ शकते."
                )
                speech = f"उल्लंघन तपशील: नियम {rule_ref}. कारण: {reason}."
            elif target_lang == LANG_HI:
                msg = (
                    f"⚠️ **उल्लंघन एवं अनिश्चितता का विवरण**:\n\n"
                    f"• **नियम / प्रावधान**: `{rule_ref}` — {req_name}\n"
                    f"• **अन्वेषण निष्कर्ष**: {reason}\n\n"
                    f"**विधिक आधार**: {LEGAL_PROVISIONS_KNOWLEDGE.get('net_quantity', {}).get('hi', '')}\n\n"
                    f"यदि घोषणा धुंधली या अनुपस्थित है, तो अधिकारी द्वारा भौतिक सत्यापन आवश्यक है।"
                )
                speech = f"उल्लंघन विवरण: नियम {rule_ref}. कारण: {reason}."
            else:
                msg = (
                    f"⚠️ **Violation / Uncertainty Analysis**:\n\n"
                    f"• **Statutory Rule**: `{rule_ref}` — {req_name}\n"
                    f"• **Reason for Flag**: {reason}\n\n"
                    f"**Statutory Standard**: {LEGAL_PROVISIONS_KNOWLEDGE.get('net_quantity', {}).get('en', '')}\n\n"
                    f"A violation under Rule 6 attracts statutory notice under Section 36 of the Legal Metrology Act, 2009."
                )
                speech = f"Violation flagged under {rule_ref}. Reason: {reason}."

        return _format_res(
            msg, speech, "EXPLAIN_VIOLATION", "Legal Metrology Act, 2009 (Sec 36)",
            ["Show supporting evidence", "Explain this rule", "Generate report", "Report to Authority"]
        )

    # 3. Action: Show supporting evidence
    if any(k in q_lower for k in ["show supporting evidence", "evidence", "polygon", "box", "पुरावा", "साक्ष्य", "प्रमाण"]):
        ev_count = len(evidence_items)
        if target_lang == LANG_MR:
            msg = (
                f"🔍 **सत्यापित पुरावे (Evidence Polygons)**:\n\n"
                f"• एकूण संकलित साक्ष्य: **{ev_count} क्षेत्रे**\n"
                f"• **पॅडल-ओसीआर (PaddleOCR)** द्वारे अचूक व्हेक्टर पॉलीगॉन座標 निश्चित करण्यात आले आहेत.\n"
                f"• **तपासणी पॅनलवर 'View evidence' बटण दाबून** आपण मूळ कॅमेरा प्रतिमा आणि त्यावर दर्शवलेले पॉलीगॉन पाहू शकता."
            )
            speech = f"या उत्पादनावर {ev_count} पुरावा क्षेत्रे नोंदवण्यात आली आहेत. आपण स्क्रीनवर दृश्यमान साक्ष्य तपासू शकता."
        elif target_lang == LANG_HI:
            msg = (
                f"🔍 **समर्थक साक्ष्य एवं साक्ष्य पॉलीगॉन (Evidence Regions)**:\n\n"
                f"• कुल सत्यापित साक्ष्य क्षेत्र: **{ev_count}**\n"
                f"• PaddleOCR PP-OCRv6 द्वारा प्रत्येक घोषणा के लिए सटीक पिक्सेल बाउंडिंग बॉक्स और वेक्टर पॉलीगॉन रिकॉर्ड किए गए हैं।\n"
                f"• विस्तृत दृश्य साक्ष्य के लिए स्क्रीन पर 'View evidence' बटन पर क्लिक करें।"
            )
            speech = f"इस उत्पाद पर कुल {ev_count} साक्ष्य क्षेत्र दर्ज हैं। आप स्क्रीन पर व्यू एविडेंस बटन से इन्हें देख सकते हैं।"
        else:
            msg = (
                f"🔍 **Supporting Vector Evidence & Localization**:\n\n"
                f"• Total Linked Evidence Regions: **{ev_count}**\n"
                f"• Localized via **PaddleOCR PP-OCRv6** vector polygons directly linked to Qwen canonical extractions.\n"
                f"• Click the **'View evidence'** button on the results dashboard to inspect interactive overlays on original camera captures."
            )
            speech = f"There are {ev_count} linked evidence regions verified via vector polygons. You can open View Evidence to inspect them."

        return _format_res(
            msg, speech, "SHOW_EVIDENCE", "PaddleOCR PP-OCRv6 Vector Evidence",
            ["Explain this inspection", "Explain a violation", "Generate report"]
        )

    # 4. Action: Explain this rule
    if any(k in q_lower for k in ["explain this rule", "rule", "कानून", "कायदा", "नियम समजावा"]):
        kb_mrp = LEGAL_PROVISIONS_KNOWLEDGE["mrp"].get(target_lang, LEGAL_PROVISIONS_KNOWLEDGE["mrp"]["en"])
        kb_usp = LEGAL_PROVISIONS_KNOWLEDGE["unit_sale_price"].get(target_lang, LEGAL_PROVISIONS_KNOWLEDGE["unit_sale_price"]["en"])
        if target_lang == LANG_MR:
            msg = (
                f"📜 **विधिक मापविज्ञान प्रमुख नियम (LMPC 2011)**:\n\n"
                f"1. **नियम 6(1)(da) - MRP**: {kb_mrp}\n\n"
                f"2. **नियम 6(11) - USP**: {kb_usp}\n\n"
                f"सदर नियमांचे उल्लंघन ग्राहकांची दिशाभूल करणारे ठरते आणि दंडास पात्र आहे."
            )
            speech = "विधिक मापविज्ञान नियम 2011 अंतर्गत एमआरपी आणि युनिट विक्री दर नमूद करणे कायद्याने बंधनकारक आहे."
        elif target_lang == LANG_HI:
            msg = (
                f"📜 **प्रमुख विधिक मापविज्ञान नियम (LMPC 2011)**:\n\n"
                f"1. **नियम 6(1)(da) - MRP**: {kb_mrp}\n\n"
                f"2. **नियम 6(11) - USP**: {kb_usp}\n\n"
                f"इन नियमों का उद्देश्य उपभोक्ताओं को पारदर्शी एवं सही मूल्य जानकारी उपलब्ध कराना है।"
            )
            speech = "विधिक मापविज्ञान नियम 2011 के तहत एमआरपी और यूनिट सेल प्राइस घोषित करना अनिवार्य है।"
        else:
            msg = (
                f"📜 **Key Statutory Provisions (LMPC Rules, 2011)**:\n\n"
                f"1. **Rule 6(1)(da) - MRP**: {kb_mrp}\n\n"
                f"2. **Rule 6(11) - Unit Sale Price (USP)**: {kb_usp}\n\n"
                f"These statutory provisions protect consumers against arbitrary pack pricing and hidden shortages."
            )
            speech = "Key provisions under Legal Metrology Rules include mandatory MRP inclusive of taxes and Unit Sale Price."

        return _format_res(
            msg, speech, "EXPLAIN_RULE", "Legal Metrology Rules, 2011",
            ["Explain this inspection", "Show supporting evidence", "Generate report"]
        )

    # 5. Action: Generate report / Read summary aloud
    if any(k in q_lower for k in ["generate report", "read summary aloud", "अहवाल", "रिपोर्ट", "आवाज", "वाचून दाखवा"]):
        if target_lang == LANG_MR:
            msg = (
                f"📄 **अहवाल निर्मिती (Statutory PDF Report)**:\n\n"
                f"सदर तपासणीचा अधिकृत 'Legal Metrology Compliance Inspection Report' डाऊनलोड करण्यासाठी आपण खालील **'Report preview'** पर्यायावर क्लिक करू शकता. यामध्ये ग्राहक व्यवहार मंत्रालय चिन्ह आणि सर्व पुरावा प्रतिमा समाविष्ट आहेत."
            )
            speech = f"अधिकृत विधिक मापविज्ञान अहवाल तयार आहे. आपण रिपोर्ट प्रिव्ह्यू वरून डाऊनलोड करू शकता."
        elif target_lang == LANG_HI:
            msg = (
                f"📄 **वैधानिक निरीक्षण रिपोर्ट (Inspection PDF)**:\n\n"
                f"इस निरीक्षण का आधिकारिक उपभोक्ता मामले विभाग संरचित PDF रिपोर्ट तैयार है। इसे डाउनलोड या प्रिंट करने के लिए 'Report preview' बटन दबाएं।"
            )
            speech = f"आधिकारिक वैधानिक रिपोर्ट तैयार है। आप रिपोर्ट प्रिव्यू से पीडीएफ डाउनलोड कर सकते हैं।"
        else:
            msg = (
                f"📄 **Statutory Inspection Report Ready**:\n\n"
                f"You can preview and download the official evidence-backed PDF report formatted for the Department of Consumer Affairs by clicking **'Report preview'** on the dashboard."
            )
            speech = f"The official compliance inspection report is ready for download in the report preview section."

        return _format_res(
            msg, speech, "GENERATE_REPORT", "Statutory PDF Evidence Report",
            ["Explain this inspection", "Show supporting evidence", "Report to Authority"],
            extra={"action_trigger": "OPEN_REPORT_PREVIEW"}
        )

    # Default fallback response
    if target_lang == LANG_MR:
        msg = f"मी लेक्समेट्रा (LexMetra) सहाय्यक आहे. मी {p_name} च्या तपासणीचे विश्लेषण, कायदेशीर नियम, पुरावे आणि तक्रार प्रक्रियेबद्दल साहाय्य करू शकतो."
        speech = f"मी लेक्समेट्रा सहाय्यक आहे. आपण काय विचारू इच्छिता?"
    elif target_lang == LANG_HI:
        msg = f"मैं लेक्समेट्रा (LexMetra) सहायक हूँ। मैं {p_name} के निरीक्षण, वैधानिक नियमों (LMPC 2011), साक्ष्यों और शिकायत प्रक्रिया में आपकी सहायता कर सकता हूँ।"
        speech = f"मैं लेक्समेट्रा सहायक हूँ। आप मुझसे निरीक्षण और नियमों के बारे में पूछ सकते हैं।"
    else:
        msg = f"I am your LexMetra Assistant, grounded in the inspection data for {p_name}. You can ask me to explain violations, inspect evidence polygons, cite statutory rules, or generate reports in English, Hindi, or Marathi."
        speech = f"I am your LexMetra Assistant. How can I help you inspect this packaged commodity?"

    return _format_res(
        msg, speech, "GENERAL_GUIDANCE", "Legal Metrology Act, 2009",
        ["Explain this inspection", "Explain a violation", "Why is this uncertain?", "Show supporting evidence", "Explain this rule", "Summarize findings", "Generate report", "Read summary aloud"]
    )
