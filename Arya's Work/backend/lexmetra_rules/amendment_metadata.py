"""
Document-level amendment metadata extraction for official Indian Gazette notifications.

Extracts and preserves:
1. Notification Number (e.g. G.S.R. 577(E), सा.का.नि. 577(अ))
2. Full Title, Base Regulation, Amendment Name, and Year:
   - Base Regulation: Legal Metrology (Packaged Commodities) Rules, 2011
   - Amendment Name: Second Amendment
   - Year: 2022
   - Full Title: Legal Metrology (Packaged Commodities) (Second Amendment) Rules, 2022
3. Gazette / Publication Date:
   - e.g. "New Delhi, the 14th July, 2022" -> date(2022, 7, 14)
4. Legal Effective Date:
   - Rule 1(2): "They shall come into force on the date of their publication in the Official Gazette"
     -> resolved to Gazette date 2022-07-14 (never defaulted to ingestion date).
5. Substantive Applicability / Trigger Date (kept strictly separate):
   - e.g. Rule 2: "for electronic products manufactured or packed or imported after the 15th July, 2022"
     -> 2022-07-15.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "जनवरी": 1, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6,
    "जुलाई": 7, "अगस्त": 8, "सितंबर": 9, "अक्टूबर": 10, "नवंबर": 11, "दिसंबर": 12,
}

_ORDINALS = {
    "first": "First Amendment",
    "second": "Second Amendment",
    "third": "Third Amendment",
    "fourth": "Fourth Amendment",
    "fifth": "Fifth Amendment",
    "sixth": "Sixth Amendment",
    "seventh": "Seventh Amendment",
    "पहला": "First Amendment",
    "दूसरा": "Second Amendment",
    "तीसरा": "Third Amendment",
    "चौथा": "Fourth Amendment",
    "पांचवा": "Fifth Amendment",
}


def normalize_whitespace(text: Optional[str]) -> Optional[str]:
    """
    Normalize line breaks, repeated whitespace, and leading/trailing whitespace.
    E.g. 'Second\\nAmendment, 2022' -> 'Second Amendment, 2022'.
    """
    if text is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    return cleaned if cleaned else None


@dataclass
class AmendmentMetadata:
    notification_number: Optional[str] = None
    notification: Optional[str] = None
    amendment_name: Optional[str] = None
    amendment: Optional[str] = None
    year: Optional[int] = None
    regulation: Optional[str] = None
    full_title: Optional[str] = None
    title: Optional[str] = None
    version_label: Optional[str] = None
    gazette_date: Optional[date] = None
    effective_date: Optional[date] = None
    commencement_source_provision: Optional[str] = None
    substantive_trigger_date: Optional[date] = None
    substantive_trigger_scope: Optional[str] = None
    applicability_duration: Optional[str] = None
    issuing_authority: Optional[str] = None

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> None:
        for field in [
            "notification_number", "notification", "amendment_name", "amendment",
            "regulation", "full_title", "title", "version_label",
            "commencement_source_provision", "substantive_trigger_scope",
            "applicability_duration", "issuing_authority"
        ]:
            val = getattr(self, field, None)
            if isinstance(val, str):
                setattr(self, field, normalize_whitespace(val))

    def to_dict(self) -> Dict[str, Any]:
        self.normalize()
        return {
            "notification_number": self.notification_number,
            "notification": self.notification,
            "amendment_name": self.amendment_name,
            "amendment": self.amendment,
            "year": self.year,
            "regulation": self.regulation,
            "full_title": self.full_title,
            "version_label": self.version_label,
            "gazette_date": self.gazette_date.isoformat() if self.gazette_date else None,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "commencement_source_provision": self.commencement_source_provision,
            "substantive_trigger_date": (
                self.substantive_trigger_date.isoformat() if self.substantive_trigger_date else None
            ),
            "substantive_trigger_scope": self.substantive_trigger_scope,
            "applicability_duration": self.applicability_duration,
            "issuing_authority": self.issuing_authority,
        }



def _parse_date(day_str: str, month_str: str, year_str: str) -> Optional[date]:
    try:
        m = _MONTH_MAP.get(month_str.strip().lower())
        if not m:
            return None
        return date(int(year_str), m, int(day_str))
    except (ValueError, TypeError):
        return None


def extract_amendment_metadata(text: str) -> AmendmentMetadata:
    """
    Extract structured metadata from full document text (bilingual or English/Hindi).
    """
    meta = AmendmentMetadata()

    # 1. Notification Number
    # Match G.S.R. 577(E) or G.S.R. 577 (E) or S.O. 577(E)
    gsr_match = re.search(
        r"\b(G\.?\s*S\.?\s*R\.?|S\.?\s*O\.?)\s*(?:No\.?)?\s*(\d+[A-Za-z]?(?:\s*\([A-Za-z0-9]+\))?)",
        text,
        re.IGNORECASE,
    )
    if gsr_match:
        prefix = "G.S.R." if "g" in gsr_match.group(1).lower() else "S.O."
        num_part = re.sub(r"\s+", "", gsr_match.group(2))
        meta.notification_number = f"{prefix} {num_part}"
        meta.notification = meta.notification_number
    else:
        # Check Hindi notification सा.का.नि. 577(अ)
        hi_gsr = re.search(
            r"\b(सा\.?\s*का\.?\s*नि\.?|का\.?\s*आ\.?)\s*(?:सं\.?)?\s*(\d+[A-Za-z]?(?:\s*\([A-Za-z0-9अ-ह]+\))?)",
            text,
        )
        if hi_gsr:
            num_part = re.sub(r"\s+", "", hi_gsr.group(2))
            meta.notification_number = f"सा.का.नि. {num_part}"
            meta.notification = meta.notification_number

    # 2. Gazette / Publication Date
    # "New Delhi, the 14th July, 2022" or "New Delhi, 14th July, 2022" or "NEW DELHI, THURSDAY, JULY 14, 2022"
    date_match = re.search(
        r"New Delhi,\s*(?:the\s*)?(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>[A-Za-z]+),?\s+(?P<year>\d{4})",
        text,
        re.IGNORECASE,
    )
    if not date_match:
        date_match = re.search(
            r"NEW DELHI,\s*[A-Z]+,\s*(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})",
            text,
            re.IGNORECASE,
        )
    if not date_match:
        # Hindi date: "नई दिल्ली, 14 जुलाई, 2022"
        date_match = re.search(
            r"नई दिल्ली,\s*(?P<day>\d{1,2})\s+(?P<month>जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर),?\s+(?P<year>\d{4})",
            text,
        )

    if date_match:
        meta.gazette_date = _parse_date(
            date_match.group("day"), date_match.group("month"), date_match.group("year")
        )

    # 3. Amendment Title, Name, Year, and Base Regulation
    # English title: "Legal Metrology (Packaged Commodities) (Second Amendment) Rules, 2022"
    title_match = re.search(
        r"(?P<title>(?P<base>Legal Metrology \(Packaged Commodities\) Rules(?:,\s*\d{4})?|[\w\s\(\)]+?)\s*\((?P<amendment>[A-Za-z0-9\s]+?Amendment)\)\s*Rules,\s*(?P<year>\d{4}))",
        text,
        re.IGNORECASE,
    )
    if title_match:
        raw_title = " ".join(title_match.group("title").split())
        clean_title = re.sub(
            r"^(?:\(?\d+\)?\s*)?(?:These\s+rules\s+may\s+be\s+called\s+(?:the\s+)?)?",
            "",
            raw_title,
            flags=re.IGNORECASE,
        ).strip()
        meta.full_title = clean_title
        meta.title = clean_title
        meta.amendment_name = title_match.group("amendment").strip()
        meta.amendment = meta.amendment_name
        meta.year = int(title_match.group("year"))
    else:
        # Hindi title: "विधिक मापविज्ञान (पैक की गई वस्तुएं) (दूसरा संशोधन) नियम, 2022"
        hi_title = re.search(
            r"(?P<title>विधिक मापविज्ञान\s*\(पैक की गई वस्तुएं\)\s*\((?P<amendment>[^)]*संशोधन)\)\s*नियम,\s*(?P<year>\d{4}))",
            text,
        )
        if hi_title:
            raw_hi = " ".join(hi_title.group("title").split())
            clean_hi = re.sub(
                r"^(?:\(?\d+\)?\s*)?(?:इन\s+नियमों\s+का\s+संक्षिप्त\s+नाम\s+)?",
                "",
                raw_hi,
            ).strip()
            meta.full_title = clean_hi
            meta.title = clean_hi
            raw_hi_amendment = hi_title.group("amendment").strip()
            amendment_key = raw_hi_amendment.replace("संशोधन", "").strip()
            meta.amendment_name = _ORDINALS.get(amendment_key, raw_hi_amendment)
            meta.amendment = meta.amendment_name
            meta.year = int(hi_title.group("year"))

    # Base Regulation detection
    # Look for "further to amend the Legal Metrology (Packaged Commodities) Rules, 2011"
    base_match = re.search(
        r"(?:to amend the|amend the)\s+(?P<reg>Legal Metrology \(Packaged Commodities\) Rules,\s*2011)",
        text,
        re.IGNORECASE,
    )
    if base_match:
        meta.regulation = base_match.group("reg").strip()
    elif "Legal Metrology (Packaged Commodities)" in text or "विधिक मापविज्ञान (पैक की गई वस्तुएं)" in text:
        meta.regulation = "Legal Metrology (Packaged Commodities) Rules, 2011"
    elif title_match and title_match.group("base"):
        meta.regulation = title_match.group("base").strip()

    # Build consistent version_label
    if meta.amendment_name and meta.year:
        meta.version_label = f"{meta.amendment_name}, {meta.year}"
    elif meta.amendment_name:
        meta.version_label = meta.amendment_name
    elif meta.full_title:
        meta.version_label = meta.full_title

    # 4. Effective Date resolution
    # Check Rule 1(2): "They shall come into force on the date of their publication in the Official Gazette."
    gazette_publication_clause = re.search(
        r"(?:shall come into force on the date of (?:their )?publication in the Official Gazette|"
        r"from the date of (?:their )?publication in the Official Gazette|"
        r"राजपत्र में उनके प्रकाशन की तारीख को प्रवृत्त होंगे)",
        text,
        re.IGNORECASE,
    )
    if gazette_publication_clause and meta.gazette_date:
        meta.effective_date = meta.gazette_date
        meta.commencement_source_provision = "Rule 1(2)"
    else:
        # Check if Rule 1(2) specifies an explicit commencement date
        rule1_match = re.search(
            r"1\.\s*(?:\(1\)[^\n]+)?\s*\(2\)\s*(?:They\s+)?shall come into force (?:on|with effect from)\s+(?:the\s+)?(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?(?P<month>[A-Za-z]+),?\s+(?P<year>\d{4})",
            text,
            re.IGNORECASE,
        )
        if rule1_match:
            meta.effective_date = _parse_date(
                rule1_match.group("day"), rule1_match.group("month"), rule1_match.group("year")
            )
            meta.commencement_source_provision = "Rule 1(2)"
        elif meta.gazette_date and "Official Gazette" in text:
            # If Gazette publication date is clear and document is an Official Gazette amendment
            meta.effective_date = meta.gazette_date
            meta.commencement_source_provision = "Rule 1(2)"

    # 5. Substantive Trigger Date (kept strictly separate from effective date)
    # e.g. Rule 2: "for electronic products manufactured or packed or imported after the 15th July, 2022"
    subst_match = re.search(
        r"(?P<scope>(?:for\s+)?(?:electronic\s+products\s+)?(?:manufactured|packed|imported)(?:\s+or\s+(?:packed|imported))*\s+after\s+(?:the\s+)?(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>[A-Za-z]+),?\s+(?P<year>\d{4}))",
        text,
        re.IGNORECASE,
    )
    if not subst_match:
        # Hindi: "15 जुलाई, 2022 के पश्चात् विनिर्मित या पैक किए गए या आयात किए गए इलेक्ट्रॉनिक उत्पादों के लिए"
        subst_match = re.search(
            r"(?P<scope>(?P<day>\d{1,2})\s+(?P<month>जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर),?\s+(?P<year>\d{4})\s+के\s+पश्चात्\s+(?:विनिर्मित|पैक|आयात)[^\n,\"]+)",
            text,
        )

    if subst_match:
        meta.substantive_trigger_date = _parse_date(
            subst_match.group("day"), subst_match.group("month"), subst_match.group("year")
        )
        meta.substantive_trigger_scope = subst_match.group("scope").strip()

    # 6. Applicability duration (e.g. "for a period of one year")
    dur_match = re.search(
        r"for\s+a\s+period\s+of\s+(?P<duration>[a-zA-Z0-9\s]+?)(?:\s+from\s+such\s+date|[,\.\n])",
        text,
        re.IGNORECASE,
    )
    if dur_match:
        raw_dur = dur_match.group("duration").strip()
        meta.applicability_duration = "1 year" if "one year" in raw_dur.lower() else raw_dur
    elif "एक वर्ष की अवधि" in text:
        meta.applicability_duration = "1 year"

    # 7. Issuing Authority
    auth_match = re.search(
        r"(MINISTRY\s+OF\s+[A-Z\s,]+(?:\([A-Za-z\s]+\))?)",
        text,
        re.IGNORECASE,
    )
    if auth_match:
        meta.issuing_authority = auth_match.group(1).strip()

    meta.normalize()
    return meta

