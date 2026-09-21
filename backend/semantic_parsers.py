"""
Specialized Semantic Parsers for LexMetra Legal Metrology Inspection.

Design Principles:
- Semantic disambiguation: Differentiates plain monetary amounts (e.g. ₹800.00)
  from unit rates with denominators (e.g. ₹26.67/ml) and measurements (e.g. 16.89 g).
- Batch code normalization: Repairs dot-matrix character confusions (O/0, I/1, S/5, B/8, oo/N)
  while strictly preserving the raw OCR reading and recording normalization reasons.
- Temporal extraction: Parses absolute calendar dates and relative shelf-life durations
  (e.g. "24 months from MFD") with anchors.
- Role-aware company blocks: Aggregates multi-line company names, street addresses, and
  PIN codes across lines without premature inline truncation.
- Never mutates OCR candidate availability globally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Unit and Currency Constants
# ---------------------------------------------------------------------------

RATE_DENOMINATOR_UNITS: Dict[str, str] = {
    "ml": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "l",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "g": "g",
    "gm": "g",
    "gms": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "cm": "cm",
    "centimetre": "cm",
    "centimetres": "cm",
    "centimeter": "cm",
    "centimeters": "cm",
    "m": "m",
    "metre": "m",
    "metres": "m",
    "meter": "m",
    "meters": "m",
    "piece": "piece",
    "pieces": "piece",
    "pc": "piece",
    "pcs": "piece",
    "unit": "unit",
    "units": "unit",
    "no": "number",
    "no.": "number",
    "nos": "number",
    "nos.": "number",
    "number": "number",
    "numbers": "number",
    "item": "item",
    "items": "item",
}

NON_PRICE_MEASUREMENT_UNITS = re.compile(
    r"\b(?:kg|kgs|g|gm|gms|grams?|mg|ml|l|litres?|liters?|cm|m|metres?|meters?|kcal|cal|kj|%)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# 1. Money & Unit Rate Parser
# ---------------------------------------------------------------------------

@dataclass
class MoneyValue:
    amount: float
    raw_text: str
    currency: str = "INR"
    has_currency_symbol: bool = False
    is_unit_rate: bool = False
    denominator_unit: Optional[str] = None
    qualifiers: List[str] = field(default_factory=list)  # e.g. ["incl. of all taxes"]
    confidence: float = 1.0


_CURRENCY_SYMBOL_RE = re.compile(r"(?:₹|rs\.?|inr|£)", re.I)
_TAX_QUALIFIER_RE = re.compile(
    r"\b(?:incl(?:usive)?\.?\s*(?:of)?\s*all\s*taxes?|incl\.?\s*taxes?)\b",
    re.I,
)


def parse_money(text: str) -> Optional[MoneyValue]:
    """
    Parse a string into a MoneyValue object.

    Accurately distinguishes:
    1. Unit rate with denominator (e.g. "₹26.67/ml", "26.67 / ml", "₹ 2.80/g", "5.00 per unit")
    2. Plain monetary price (e.g. "₹800.00", "₹800", "800.00", "Rs. 120/-")
    3. Rejects mass / volume measurements (e.g. "16.89 g", "30 ml", "500 g") when bare.
    """
    if not text:
        return None

    cleaned = text.strip()

    # Detect tax qualifiers
    qualifiers = []
    if _TAX_QUALIFIER_RE.search(cleaned):
        qualifiers.append("inclusive of all taxes")

    has_curr = bool(_CURRENCY_SYMBOL_RE.search(cleaned)) or "/-" in cleaned

    # Check for unit rate pattern: amount / unit or amount per unit
    # e.g. ₹26.67/ml, =26.67/ml, 26.67/ml, ₹2.80/g, 5.00 per unit
    rate_pattern = re.compile(
        r"(?:(?:₹|rs\.?|inr|=)\s*)?([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:/|per)\s*([a-zA-Z.]+)",
        re.I,
    )
    m_rate = rate_pattern.search(cleaned)
    if m_rate:
        raw_amt_str = m_rate.group(1).replace(",", "")
        unit_str = m_rate.group(2).lower().rstrip(" .,;:")
        try:
            amt = float(raw_amt_str)
            canon_unit = RATE_DENOMINATOR_UNITS.get(unit_str)
            if canon_unit and amt > 0:
                return MoneyValue(
                    amount=amt,
                    raw_text=cleaned,
                    currency="INR",
                    has_currency_symbol=has_curr,
                    is_unit_rate=True,
                    denominator_unit=canon_unit,
                    qualifiers=qualifiers,
                    confidence=0.95 if has_curr else 0.85,
                )
        except (ValueError, TypeError):
            pass

    # Check for plain monetary value
    # Case A: Explicit currency symbol or /- suffix: e.g. ₹800.00, Rs. 800, 800/-
    curr_pattern = re.compile(
        r"(?:₹|rs\.?|inr|£)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)(?:\s*/\s*[-–])?",
        re.I,
    )
    m_curr = curr_pattern.search(cleaned)
    if m_curr:
        raw_amt_str = m_curr.group(1).replace(",", "")
        try:
            amt = float(raw_amt_str)
            if amt > 0:
                # Ensure no immediate unit denominator immediately following
                rem = cleaned[m_curr.end():].strip()
                if rem.startswith("/") or rem.lower().startswith("per "):
                    unit_m = re.match(r"^(?:/|per)\s*([a-zA-Z]+)", rem, re.I)
                    if unit_m and unit_m.group(1).lower() in RATE_DENOMINATOR_UNITS:
                        return MoneyValue(
                            amount=amt,
                            raw_text=cleaned,
                            currency="INR",
                            has_currency_symbol=True,
                            is_unit_rate=True,
                            denominator_unit=RATE_DENOMINATOR_UNITS[unit_m.group(1).lower()],
                            qualifiers=qualifiers,
                            confidence=0.95,
                        )
                return MoneyValue(
                    amount=amt,
                    raw_text=cleaned,
                    currency="INR",
                    has_currency_symbol=True,
                    is_unit_rate=False,
                    denominator_unit=None,
                    qualifiers=qualifiers,
                    confidence=0.95,
                )
        except (ValueError, TypeError):
            pass

    # Case B: Notation with /- suffix: e.g. "800/-"
    suffix_pattern = re.compile(r"(?<![0-9.])([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*/\s*[-–]")
    m_suffix = suffix_pattern.search(cleaned)
    if m_suffix:
        raw_amt_str = m_suffix.group(1).replace(",", "")
        try:
            amt = float(raw_amt_str)
            if amt > 0:
                return MoneyValue(
                    amount=amt,
                    raw_text=cleaned,
                    currency="INR",
                    has_currency_symbol=True,
                    is_unit_rate=False,
                    denominator_unit=None,
                    qualifiers=qualifiers,
                    confidence=0.92,
                )
        except (ValueError, TypeError):
            pass

    # Case C: Bare 2-decimal amount without currency symbol (e.g. "800.00", "120.50")
    # Must apply the mass/measurement guard (The "16.89 g" guard)
    bare_pattern = re.compile(r"(?<![\d.])([0-9][0-9,]*\.[0-9]{2})(?![\d.])")
    m_bare = bare_pattern.search(cleaned)
    if m_bare:
        raw_amt_str = m_bare.group(1).replace(",", "")
        # Inspect what immediately follows the bare number
        after_match = cleaned[m_bare.end():]
        # If followed by measurement unit (g, gm, ml, etc.) -> REJECT as price
        if NON_PRICE_MEASUREMENT_UNITS.match(after_match.strip()):
            return None
        # If followed by "/" or "per" and unit -> unit rate!
        rate_post = re.match(r"^\s*(?:/|per)\s*([a-zA-Z]+)", after_match, re.I)
        if rate_post:
            unit_candidate = rate_post.group(1).lower()
            if unit_candidate in RATE_DENOMINATOR_UNITS:
                try:
                    amt = float(raw_amt_str)
                    return MoneyValue(
                        amount=amt,
                        raw_text=cleaned,
                        currency="INR",
                        has_currency_symbol=False,
                        is_unit_rate=True,
                        denominator_unit=RATE_DENOMINATOR_UNITS[unit_candidate],
                        qualifiers=qualifiers,
                        confidence=0.85,
                    )
                except (ValueError, TypeError):
                    pass
        try:
            amt = float(raw_amt_str)
            if amt > 0:
                return MoneyValue(
                    amount=amt,
                    raw_text=cleaned,
                    currency="INR",
                    has_currency_symbol=False,
                    is_unit_rate=False,
                    denominator_unit=None,
                    qualifiers=qualifiers,
                    confidence=0.80,
                )
        except (ValueError, TypeError):
            pass

    # Case D: Dot-matrix OCR confusion repair for price (e.g. "soq.oo", "soo.o0o", "soq.ag", "8oo.oo")
    dm_match = re.search(
        r"(?<![\w.])([sSB0-9][oOqQ0-9]{1,4}\.[oOqQ0-9a-zA-Z]{2})(?![\w.])", cleaned
    )
    if dm_match:
        raw_dm = dm_match.group(1)
        if any(c in "sSBoOqQag" for c in raw_dm):
            DOT_MATRIX_NUMERIC_CHARS = str.maketrans({
                "s": "8", "S": "8", "B": "8",
                "o": "0", "O": "0", "q": "0", "Q": "0",
                "a": "0", "g": "0",
            })
            fixed = raw_dm.translate(DOT_MATRIX_NUMERIC_CHARS)
            try:
                amt = float(fixed)
                if amt > 0:
                    return MoneyValue(
                        amount=amt,
                        raw_text=cleaned,
                        currency="INR",
                        has_currency_symbol=False,
                        is_unit_rate=False,
                        denominator_unit=None,
                        qualifiers=qualifiers,
                        confidence=0.85,
                    )
            except (ValueError, TypeError):
                pass

    return None



# ---------------------------------------------------------------------------
# 2. Batch / Lot Code Parser with Dot-Matrix OCR Repair
# ---------------------------------------------------------------------------

@dataclass
class BatchCandidate:
    raw_reading: str
    normalized_reading: str
    normalization_reasons: List[str] = field(default_factory=list)
    confidence: float = 0.85


def parse_batch_code(text: str, label_prefix: Optional[str] = None) -> Optional[BatchCandidate]:
    """
    Specialized batch/lot code parser.

    Handles real dot-matrix and stamped character confusion:
    - O <-> 0
    - I <-> 1
    - S <-> 5
    - B <-> 8
    - H/oo <-> N (e.g. in 'c26Ho0s' -> 'C26HN005')

    Strictly preserves raw_reading and records normalization_reasons.
    """
    if not text:
        return None

    raw = text.strip()

    # Strip label prefix if present (e.g. "BATCH NO.", "B.NO:", "LOT:")
    code_text = raw
    if label_prefix and label_prefix.lower() in code_text.lower():
        idx = code_text.lower().find(label_prefix.lower())
        code_text = code_text[idx + len(label_prefix):]
    else:
        m_lbl = re.search(
            r"\b(?:batch|lot)\s*(?:no\.?|number|#|code)?\s*[:\-–=]*\s*",
            code_text,
            re.I,
        )
        if m_lbl:
            code_text = code_text[m_lbl.end():]

    code_text = re.sub(r"^[\s:\-–=~,|]+", "", code_text).rstrip(" |;,.")
    if not code_text or len(code_text) < 2:
        return None

    # Do not treat date patterns (e.g. 03/2026, 12/24, 13/05/26, 13/05/2026, 2026-05-13, 13-MAY-26) as batch codes
    if (
        re.match(r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}$", code_text)
        or re.match(r"^\d{1,2}[/.-]\d{2,4}$", code_text)
        or re.match(r"^\d{4}[/.-]\d{1,2}[/.-]\d{1,2}$", code_text)
        or re.match(r"^\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{2,4}$", code_text)
    ):
        return None
    # Do not treat pure monetary amounts or prices with /- as batch codes
    if re.match(r"^(?:₹|rs\.?|inr)?\s*\d+(?:\.\d{1,2})?(?:\s*/\s*[-–])?$", code_text, re.I):
        return None
    # Do not treat unit sale prices / rates (e.g. 2.80/g, ₹2.80/g, Rs 2.80/g, 1.20/ml) as batch codes
    if re.search(r"(?:₹|rs\.?|=|/)?\s*\d+(?:\.\d{1,2})?\s*/\s*(?:g|kg|gm|gms|grams?|ml|l|cm|m|pc|pcs|unit|units|nos?)\b", code_text, re.I):
        return None
    # Do not treat price/tax/mrp labels as batch codes
    if re.search(r"\b(?:mrp|price|taxes?|rate|incl)\b", text, re.I):
        return None
    # Do not treat declaration label keywords (e.g. "USP", "MRP", "EXP") as batch codes
    reserved_keywords = {"mrp", "usp", "mfg", "mfd", "exp", "expiry", "batch", "lot", "net", "qty", "pkd", "pkg", "date"}
    if re.sub(r"[^\w]+", "", code_text).lower() in reserved_keywords:
        return None

    # Do not treat telephone numbers / customer care / contact numbers as batch codes
    digits_clean = re.sub(r"\D", "", code_text)
    if (
        re.search(r"\b(?:tel|phone|ph|call|toll|free|care|contact|whatsapp|helpline|query)\b", text, re.I)
        or code_text.startswith(("+91", "91 ", "91-", "1800", "1860"))
        or (
            not re.search(r"[a-zA-Z]", code_text[:3])
            and len(digits_clean) in (10, 11, 12)
            and not re.search(r"\d{1,2}:\d{2}", code_text)
            and digits_clean.startswith(("91", "1800", "1860", "080", "022", "011", "044", "033", "040", "020"))
        )
    ):
        return None

    raw_reading = code_text
    reasons = []
    norm = code_text

    # 1. Dot-matrix lowercase leading letter repair (e.g. 'c26...' -> 'C26...')
    if norm[0].islower():
        norm = norm[0].upper() + norm[1:]
        reasons.append("Capitalized leading character")

    # 2. General dot-matrix confusion repair in alphanumeric codes (O/0, S/5)
    if re.search(r"^[a-zA-Z]\d{2}[a-zA-Z0-9]+", norm):
        if re.search(r"\d[sS]$", norm):
            norm = re.sub(r"(\d)[sS]$", r"\g<1>5", norm)
            reasons.append("Normalized terminal 's' to '5'")
        if re.search(r"\d[oO]+|\b\d+[oO]+\d+", norm):
            norm = re.sub(r"(\d)[oO]", r"\g<1>0", norm)
            norm = re.sub(r"[oO](\d)", r"0\g<1>", norm)
            reasons.append("Normalized dot-matrix 'O' to '0'")
        if re.search(r"\d[sS]$", norm):
            norm = re.sub(r"(\d)[sS]$", r"\g<1>5", norm)
            reasons.append("Normalized terminal 's' to '5'")
        if re.search(r"\d[oO]+|\b\d+[oO]+\d+", norm):
            norm = re.sub(r"(\d)[oO]", r"\g<1>0", norm)
            norm = re.sub(r"[oO](\d)", r"0\g<1>", norm)
            reasons.append("Normalized 'o' to '0' within digit sequence")

    # 3. Trailing/leading noise punctuation cleanup
    norm = re.sub(r"^[^\w]+|[^\w]+$", "", norm)

    # Validate that batch code contains at least one digit
    if not re.search(r"\d", norm):
        # Pure alpha strings without any digits (e.g. 'Noan', 'Omg') are not batch codes
        return None

    # Length must be at least 3
    if len(norm) < 3:
        return None

    return BatchCandidate(
        raw_reading=raw_reading,
        normalized_reading=norm,
        normalization_reasons=reasons,
        confidence=0.88 if reasons else 0.95,
    )



# ---------------------------------------------------------------------------
# 3. Structured Temporal Parser (Dates & Relative Durations)
# ---------------------------------------------------------------------------

@dataclass
class TemporalValue:
    raw_text: str
    is_relative: bool
    # For absolute dates:
    calendar_date: Optional[str] = None       # e.g. "03/2026" or "13/05/2026"
    normalized_iso: Optional[str] = None     # e.g. "2026-03" or "2026-05-13"
    # For relative durations:
    duration_value: Optional[float] = None   # e.g. 24.0
    duration_unit: Optional[str] = None      # e.g. "months", "years", "days"
    anchor_type: Optional[str] = None        # e.g. "MFD", "PKD", "MANUFACTURE"
    confidence: float = 0.90


_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_RELATIVE_DURATION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(months?|years?|days?|weeks?)\s*(?:from|of)\s*(?:the\s*)?(?:date\s*of\s*)?(mfd|mfg|manufactur\w*|pack\w*|pkd|pkg|import\w*|production)",
    re.I,
)

_USE_WITHIN_RE = re.compile(
    r"(?:use\s*within|best\s*within|consume\s*within)\s*(\d+(?:\.\d+)?)\s*(months?|years?|days?|weeks?)",
    re.I,
)


def parse_date_or_duration(text: str) -> Optional[TemporalValue]:
    """
    Parse a text fragment into a structured TemporalValue.

    Supports:
    1. Relative durations with anchors:
       - "24 months from MFD"
       - "24 months from manufacturing"
       - "2 years from date of manufacture"
       - "Use within 24 months of manufacture"
       - "Use before 24 months from MFD"
    2. Absolute calendar dates:
       - MM/YYYY: "03/2026", "05-2026"
       - DD/MM/YYYY: "13/05/2026", "13-05-2026", "13.05.2026"
       - DD/MM/YY: "13/05/26", "13-05-26"
       - Month YYYY: "MAR 2026", "OCT 2028", "12 OCT 2026"
    """
    if not text:
        return None

    cleaned = text.strip()

    # 1. Check relative duration pattern
    m_rel = _RELATIVE_DURATION_RE.search(cleaned)
    if m_rel:
        dur_val = float(m_rel.group(1))
        dur_unit = m_rel.group(2).lower()
        anchor_raw = m_rel.group(3).lower()
        anchor = "MFD" if any(w in anchor_raw for w in ("mfd", "mfg", "manufactur")) else "PKD"
        return TemporalValue(
            raw_text=cleaned,
            is_relative=True,
            duration_value=dur_val,
            duration_unit=dur_unit,
            anchor_type=anchor,
            confidence=0.92,
        )

    m_use = _USE_WITHIN_RE.search(cleaned)
    if m_use:
        dur_val = float(m_use.group(1))
        dur_unit = m_use.group(2).lower()
        return TemporalValue(
            raw_text=cleaned,
            is_relative=True,
            duration_value=dur_val,
            duration_unit=dur_unit,
            anchor_type="MFD",
            confidence=0.88,
        )

    _USE_BEFORE_RE = re.compile(
        r"(?:use\s*before|best\s*before|use\s*by|best\s*by)\s*(\d+(?:\.\d+)?)\s*(months?|years?|days?|weeks?)",
        re.I,
    )
    m_use_before = _USE_BEFORE_RE.search(cleaned)
    if m_use_before:
        dur_val = float(m_use_before.group(1))
        dur_unit = m_use_before.group(2).lower()
        return TemporalValue(
            raw_text=cleaned,
            is_relative=True,
            duration_value=dur_val,
            duration_unit=dur_unit,
            anchor_type="MFD",
            confidence=0.92,
        )


    # 2. Check absolute dates
    # Case A: DD/MM/YYYY (checked first so 13/05/2026 is not caught by 05/2026)
    m_dmy = re.search(r"(?<![\d/.-])([0-2]?[1-9]|[123]0|31)\s*[/.-]\s*(0[1-9]|1[0-2])\s*[/.-]\s*(20\d{2})\b", cleaned)
    if m_dmy:
        d, mo, yr = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        return TemporalValue(
            raw_text=cleaned,
            is_relative=False,
            calendar_date=f"{d:02d}/{mo:02d}/{yr:04d}",
            normalized_iso=f"{yr:04d}-{mo:02d}-{d:02d}",
            confidence=0.95,
        )

    # Case B: DD/MM/YY
    m_dmy2 = re.search(r"(?<![\d/.-])([0-2]?[1-9]|[123]0|31)\s*[/.-]\s*(0[1-9]|1[0-2])\s*[/.-]\s*(\d{2})\b", cleaned)
    if m_dmy2:
        d, mo, yr2 = int(m_dmy2.group(1)), int(m_dmy2.group(2)), int(m_dmy2.group(3))
        yr = 2000 + yr2 if yr2 < 50 else 1900 + yr2
        return TemporalValue(
            raw_text=cleaned,
            is_relative=False,
            calendar_date=f"{d:02d}/{mo:02d}/{yr:04d}",
            normalized_iso=f"{yr:04d}-{mo:02d}-{d:02d}",
            confidence=0.90,
        )

    # Case C: MM/YYYY e.g. 03/2026 or 03-2026
    m_my = re.search(r"(?<![\d/.-])(0[1-9]|1[0-2])\s*[/.-]\s*(20\d{2})\b", cleaned)
    if m_my:
        mo, yr = int(m_my.group(1)), int(m_my.group(2))
        return TemporalValue(
            raw_text=cleaned,
            is_relative=False,
            calendar_date=f"{mo:02d}/{yr:04d}",
            normalized_iso=f"{yr:04d}-{mo:02d}",
            confidence=0.95,
        )

    # Case D: Dot-matrix MM/YYYY repair where 0 is OCR'd as 9 (e.g. 93-2026 -> 03/2026)
    m_dm_my = re.search(r"(?<![\d/.-])([9oO][1-9])\s*[/.-]\s*(20\d{2})\b", cleaned)
    if m_dm_my:
        raw_m = m_dm_my.group(1).replace("9", "0").replace("o", "0").replace("O", "0")
        mo, yr = int(raw_m), int(m_dm_my.group(2))
        return TemporalValue(
            raw_text=cleaned,
            is_relative=False,
            calendar_date=f"{mo:02d}/{yr:04d}",
            normalized_iso=f"{yr:04d}-{mo:02d}",
            confidence=0.88,
        )


    # Case D: MM/YY
    m_my2 = re.search(r"\b(0[1-9]|1[0-2])\s*[/.-]\s*(\d{2})\b", cleaned)
    if m_my2:
        mo, yr2 = int(m_my2.group(1)), int(m_my2.group(2))
        yr = 2000 + yr2 if yr2 < 50 else 1900 + yr2
        return TemporalValue(
            raw_text=cleaned,
            is_relative=False,
            calendar_date=f"{mo:02d}/{yr:04d}",
            normalized_iso=f"{yr:04d}-{mo:02d}",
            confidence=0.88,
        )

    # Case E: Month name with year (e.g. "OCT 2026", "MAR 26", "12 OCT 2026")
    m_mon = re.search(
        r"\b(?:(\d{1,2})\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(?:[/.-]|\s+)?(\d{2,4})\b",
        cleaned,
        re.I,
    )
    if m_mon:
        d_str, mon_str, yr_str = m_mon.group(1), m_mon.group(2).lower(), m_mon.group(3)
        mo = _MONTH_MAP.get(mon_str, 1)
        yr = int(yr_str)
        if yr < 100:
            yr = 2000 + yr if yr < 50 else 1900 + yr
        if d_str:
            d = int(d_str)
            return TemporalValue(
                raw_text=cleaned,
                is_relative=False,
                calendar_date=f"{d:02d}/{mo:02d}/{yr:04d}",
                normalized_iso=f"{yr:04d}-{mo:02d}-{d:02d}",
                confidence=0.92,
            )
        else:
            return TemporalValue(
                raw_text=cleaned,
                is_relative=False,
                calendar_date=f"{mo:02d}/{yr:04d}",
                normalized_iso=f"{yr:04d}-{mo:02d}",
                confidence=0.90,
            )

    return None


# ---------------------------------------------------------------------------
# 4. Role-Aware Company & Multi-line Address Parser
# ---------------------------------------------------------------------------

@dataclass
class RoleAddressBlock:
    role: str                       # MANUFACTURER, PACKER, IMPORTER, MARKETER
    raw_label: str
    company_name: Optional[str] = None
    address_lines: List[str] = field(default_factory=list)
    pin_code: Optional[str] = None
    state: Optional[str] = None
    all_lines_text: List[str] = field(default_factory=list)
    confidence: float = 0.85

    @property
    def full_declaration(self) -> str:
        """Complete manufacturer / packer / marketer declaration including full address, state, and PIN."""
        parts = []
        if self.company_name:
            parts.append(self.company_name)
        for line in self.address_lines:
            if line and line not in parts:
                parts.append(line)
        if self.state and not any(self.state.lower() in p.lower() for p in parts):
            parts.append(self.state)
        if self.pin_code and not any(self.pin_code in p for p in parts):
            parts.append(f"PIN: {self.pin_code}")
        return ", ".join(parts) if parts else (self.company_name or "")


_PIN_RE = re.compile(r"\b(?:pin(?:\s*code)?\s*[:\-–=]*\s*)?([1-9][0-9]{5})\b", re.I)
_LEGAL_ENTITY_INDICATORS = re.compile(
    r"\b(?:pvt\.?\s*ltd\.?|private\s+limited|ltd\.?|limited|inc\.?|llp|corp\.?|industries|laboratories|pharmaceuticals|wellness|products)\b",
    re.I,
)


_INDIAN_STATES_RE = re.compile(
    r"\b(?:Maharashtra|Tamil\s*Nadu|Karnataka|Gujarat|Delhi|Uttar\s*Pradesh|Haryana|Punjab|West\s*Bengal|Telangana|Andhra\s*Pradesh|Kerala|Rajasthan|Madhya\s*Pradesh|Bihar|Odisha|Assam|Goa|Uttarakhand|Himachal\s*Pradesh|Jharkhand|Chhattisgarh)\b",
    re.I,
)


def parse_role_company_block(
    role: str,
    label_text: str,
    following_lines: Sequence[str],
) -> RoleAddressBlock:
    """
    Parse a company role declaration block without premature inline truncation.

    Aggregates full company name, address lines, state, and PIN code.
    Cleanly separates adjacent roles (e.g. MKTD. BY and MFG. BY).
    """
    block = RoleAddressBlock(
        role=role.upper(),
        raw_label=label_text.strip(),
    )

    # 1. Extract inline remainder if any
    lbl_cleaned = label_text.strip()
    # Strip the role prefix
    m_role = re.search(
        r"\b(?:manufactured|packed|imported|marketed)(?:\s*(?:&|and)\s*packed)?\s+by\b|\b(?:mfg|mfd|mktd|pkg)\.?\s*by\b",
        lbl_cleaned,
        re.I,
    )
    inline_rem = ""
    if m_role:
        inline_rem = lbl_cleaned[m_role.end():].strip(" :–-=|")

    # If inline remainder contains another role, split it
    if role.upper() == "MARKETER" and re.search(r"\b(?:mfg|mfd|manufactured)\.?\s*by\b", inline_rem, re.I):
        m_other = re.search(r"\b(?:mfg|mfd|manufactured)\.?\s*by\b", inline_rem, re.I)
        inline_rem = inline_rem[:m_other.start()].strip(" :–-=|;,.")
    elif role.upper() in ("MANUFACTURER", "PACKER") and re.search(r"\b(?:mktd|marketed)\.?\s*by\b", inline_rem, re.I):
        m_other = re.search(r"\b(?:mktd|marketed)\.?\s*by\b", inline_rem, re.I)
        inline_rem = inline_rem[:m_other.start()].strip(" :–-=|;,.")

    all_candidate_lines = []
    if inline_rem and len(inline_rem) > 1 and not re.match(r"^[a-zA-Z]\s*\|?$", inline_rem):
        all_candidate_lines.append(inline_rem)

    for line in following_lines:
        line_clean = line.strip(" |;,.")
        if not line_clean:
            continue
        # Stop if we hit an unrelated major declaration label
        if re.search(r"\b(?:m\.?r\.?p\.?|net\s*qty|mfg\.?\s*date|batch|exp\.?\s*date|best\s*before)\b", line_clean, re.I):
            break
        # If we are parsing MARKETER and hit MFG. BY, take any preceding text and stop
        if role.upper() == "MARKETER" and re.search(r"\b(?:mfg|mfd|manufactured)\.?\s*by\b", line_clean, re.I):
            m_mfg = re.search(r"\b(?:mfg|mfd|manufactured)\.?\s*by\b", line_clean, re.I)
            before_mfg = line_clean[:m_mfg.start()].strip(" |;,.")
            if before_mfg and len(before_mfg) > 2:
                all_candidate_lines.append(before_mfg)
            break
        # Similarly, if parsing MANUFACTURER and hit MKTD. BY, take preceding text and stop
        if role.upper() in ("MANUFACTURER", "PACKER") and re.search(r"\b(?:mktd|marketed)\.?\s*by\b", line_clean, re.I):
            m_mkt = re.search(r"\b(?:mktd|marketed)\.?\s*by\b", line_clean, re.I)
            before_mkt = line_clean[:m_mkt.start()].strip(" |;,.")
            if before_mkt and len(before_mkt) > 2:
                all_candidate_lines.append(before_mkt)
            break

        all_candidate_lines.append(line_clean)
        # Allow up to 10 address lines to prevent truncation of full multi-line factory addresses
        if len(all_candidate_lines) >= 10:
            break

    block.all_lines_text = all_candidate_lines

    # Identify company name (first line with entity indicator, or first substantial line)
    comp_name = None
    remaining_lines = []

    for i, cline in enumerate(all_candidate_lines):
        if comp_name is None:
            if _LEGAL_ENTITY_INDICATORS.search(cline) or len(cline) >= 6:
                comp_name = cline
                continue
        remaining_lines.append(cline)

    if comp_name is None and all_candidate_lines:
        comp_name = all_candidate_lines[0]
        remaining_lines = all_candidate_lines[1:]

    block.company_name = comp_name
    block.address_lines = remaining_lines

    # Extract PIN code and state from all candidate lines
    for line in all_candidate_lines:
        m_pin = _PIN_RE.search(line)
        if m_pin and not block.pin_code:
            block.pin_code = m_pin.group(1)
        m_st = _INDIAN_STATES_RE.search(line)
        if m_st and not block.state:
            block.state = m_st.group(0).strip()

    if comp_name and _LEGAL_ENTITY_INDICATORS.search(comp_name):
        block.confidence = 0.95
    elif comp_name:
        block.confidence = 0.90

    return block
