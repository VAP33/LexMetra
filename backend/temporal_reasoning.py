"""
Structured Temporal Reasoning Engine for LexMetra Legal Metrology Inspection.

Design Principles:
- Models temporal declarations as structured semantic networks rather than isolated strings.
- Resolves anchor dates, relative shelf-life durations, and computes derived endpoints:
    MFD (03/2026) + Duration (24 months from MFD) -> Derived Endpoint (03/2028)
- Bidirectional temporal consistency:
    - Relative -> Absolute: MFD + duration -> derived expiry
    - Absolute -> Relationship: MFD + Expiry -> implied duration
    - Clashing dates/durations or expiry before MFD are flagged as CONTRADICTORY.
- BOUNDARY RULE: Temporal reasoning produces structured evidence only.
  It NEVER declares legal non-compliance or marks "Expiry Missing" merely because
  a separate EXP label is absent when a lawful relative Best-Before declaration exists.
  The legal determination belongs exclusively to rule_engine.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from semantic_parsers import TemporalValue, parse_date_or_duration


@dataclass
class TemporalEvidence:
    """Structured temporal evidence model for an inspection."""
    raw_text: str
    temporal_type: str                        # MFG_DATE, EXPIRY_DATE, BEST_BEFORE, USE_BEFORE, SHELF_LIFE
    anchor_type: Optional[str] = None         # MFG_DATE, PACK_DATE, IMPORT_DATE
    anchor_evidence: Optional[str] = None     # e.g. "MFG. DATE: 03-2026"
    duration_value: Optional[float] = None    # e.g. 24.0
    duration_unit: Optional[str] = None       # "months", "years", "days"
    absolute_date: Optional[str] = None       # e.g. "03/2026" or "2026-03"
    derived_date: Optional[str] = None        # e.g. "03/2028" or "2028-03"
    derivation_method: str = "NONE"           # "PRINTED_ABSOLUTE", "ANCHOR_ADDITION", "IMPLIED_DIFFERENCE"
    confidence: float = 0.90
    contradiction_status: str = "NONE"        # "NONE", "EXPIRY_BEFORE_MFD", "DURATION_MISMATCH", "UNRESOLVED_ANCHOR"
    details: Dict[str, Any] = field(default_factory=dict)


def compute_derived_endpoint(
    start_iso: str,
    duration_value: float,
    duration_unit: str,
) -> Optional[str]:
    """
    Compute derived endpoint date string (YYYY-MM or YYYY-MM-DD) from start date and duration.
    e.g. 2026-03 + 24 months -> 2028-03
    """
    if not start_iso or duration_value <= 0:
        return None

    unit = duration_unit.lower()

    # Case 1: Start date is YYYY-MM
    m_ym = re.match(r"^(\d{4})-(\d{2})$", start_iso)
    if m_ym:
        yr, mo = int(m_ym.group(1)), int(m_ym.group(2))
        if "year" in unit:
            add_months = int(round(duration_value * 12))
        elif "month" in unit:
            add_months = int(round(duration_value))
        elif "day" in unit:
            add_months = int(round(duration_value / 30.0))
        else:
            add_months = int(round(duration_value))

        total_mo = (yr * 12 + (mo - 1)) + add_months
        end_yr = total_mo // 12
        end_mo = (total_mo % 12) + 1
        return f"{end_yr:04d}-{end_mo:02d}"

    # Case 2: Start date is YYYY-MM-DD
    m_ymd = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", start_iso)
    if m_ymd:
        yr, mo, d = int(m_ymd.group(1)), int(m_ymd.group(2)), int(m_ymd.group(3))
        try:
            dt = date(yr, mo, d)
            if "day" in unit:
                end_dt = dt + timedelta(days=int(duration_value))
                return end_dt.isoformat()
            elif "month" in unit or "year" in unit:
                add_months = int(round(duration_value * 12 if "year" in unit else duration_value))
                total_mo = (yr * 12 + (mo - 1)) + add_months
                end_yr = total_mo // 12
                end_mo = (total_mo % 12) + 1
                # Clip day if month has fewer days
                max_d = 28 if end_mo == 2 else (30 if end_mo in (4, 6, 9, 11) else 31)
                end_d = min(d, max_d)
                return f"{end_yr:04d}-{end_mo:02d}-{end_d:02d}"
        except Exception:
            pass

    return None


def calculate_implied_duration_months(start_iso: str, end_iso: str) -> Optional[float]:
    """
    Calculate the duration in months between start and end dates.
    e.g. 2026-03 to 2028-03 -> 24.0 months.
    """
    m_start = re.match(r"^(\d{4})-(\d{2})", start_iso)
    m_end = re.match(r"^(\d{4})-(\d{2})", end_iso)
    if not m_start or not m_end:
        return None

    y1, m1 = int(m_start.group(1)), int(m_start.group(2))
    y2, m2 = int(m_end.group(1)), int(m_end.group(2))

    months = (y2 - y1) * 12 + (m2 - m1)
    return float(months)


def resolve_temporal_evidence(
    mfg_raw: Optional[str] = None,
    expiry_raw: Optional[str] = None,
    best_before_raw: Optional[str] = None,
) -> Dict[str, TemporalEvidence]:
    """
    Resolve structured temporal evidence across manufacturing, expiry, and best-before declarations.

    Returns a dictionary mapping field names ('mfg_date', 'expiry_date', 'best_before')
    to structured TemporalEvidence objects.
    """
    results: Dict[str, TemporalEvidence] = {}

    # 1. Parse manufacturing date
    mfg_parsed: Optional[TemporalValue] = None
    if mfg_raw:
        mfg_parsed = parse_date_or_duration(mfg_raw)
        if mfg_parsed:
            results["mfg_date"] = TemporalEvidence(
                raw_text=mfg_raw,
                temporal_type="MFG_DATE",
                absolute_date=mfg_parsed.normalized_iso or mfg_parsed.calendar_date,
                derivation_method="PRINTED_ABSOLUTE",
                confidence=mfg_parsed.confidence,
                details={"calendar_date": mfg_parsed.calendar_date},
            )

    # 2. Parse best before / use before
    bb_parsed: Optional[TemporalValue] = None
    if best_before_raw:
        bb_parsed = parse_date_or_duration(best_before_raw)

    # 3. Parse explicit expiry date
    exp_parsed: Optional[TemporalValue] = None
    if expiry_raw:
        exp_parsed = parse_date_or_duration(expiry_raw)

    # Resolve Best Before
    if bb_parsed:
        if bb_parsed.is_relative:
            # Relative duration: e.g. "24 months from MFD"
            anchor = bb_parsed.anchor_type or "MFD"
            mfg_iso = results.get("mfg_date", TemporalEvidence(raw_text="", temporal_type="")).absolute_date

            derived_end = None
            derivation_method = "UNRESOLVED_ANCHOR"
            contradiction = "NONE"

            if mfg_iso and bb_parsed.duration_value:
                derived_end = compute_derived_endpoint(
                    mfg_iso,
                    bb_parsed.duration_value,
                    bb_parsed.duration_unit or "months",
                )
                derivation_method = "ANCHOR_ADDITION"
            else:
                contradiction = "UNRESOLVED_ANCHOR"

            results["best_before"] = TemporalEvidence(
                raw_text=best_before_raw or bb_parsed.raw_text,
                temporal_type="BEST_BEFORE",
                anchor_type=anchor,
                anchor_evidence=mfg_raw if mfg_iso else None,
                duration_value=bb_parsed.duration_value,
                duration_unit=bb_parsed.duration_unit,
                derived_date=derived_end,
                derivation_method=derivation_method,
                confidence=bb_parsed.confidence * (1.0 if derived_end else 0.8),
                contradiction_status=contradiction,
                details={
                    "is_relative": True,
                    "shelf_life_duration": f"{bb_parsed.duration_value:g} {bb_parsed.duration_unit}",
                },
            )
        else:
            # Absolute best-before date: e.g. "03/2028"
            results["best_before"] = TemporalEvidence(
                raw_text=best_before_raw or bb_parsed.raw_text,
                temporal_type="BEST_BEFORE",
                absolute_date=bb_parsed.normalized_iso or bb_parsed.calendar_date,
                derivation_method="PRINTED_ABSOLUTE",
                confidence=bb_parsed.confidence,
                details={"calendar_date": bb_parsed.calendar_date},
            )

    # Resolve Expiry Date
    if exp_parsed:
        if exp_parsed.is_relative:
            # Relative expiry: e.g. "24 months from manufacturing"
            anchor = exp_parsed.anchor_type or "MFD"
            mfg_iso = results.get("mfg_date", TemporalEvidence(raw_text="", temporal_type="")).absolute_date
            derived_end = None
            if mfg_iso and exp_parsed.duration_value:
                derived_end = compute_derived_endpoint(
                    mfg_iso,
                    exp_parsed.duration_value,
                    exp_parsed.duration_unit or "months",
                )
            results["expiry_date"] = TemporalEvidence(
                raw_text=expiry_raw or exp_parsed.raw_text,
                temporal_type="EXPIRY_DATE",
                anchor_type=anchor,
                anchor_evidence=mfg_raw if mfg_iso else None,
                duration_value=exp_parsed.duration_value,
                duration_unit=exp_parsed.duration_unit,
                derived_date=derived_end,
                derivation_method="ANCHOR_ADDITION" if derived_end else "UNRESOLVED_ANCHOR",
                confidence=exp_parsed.confidence,
                details={"is_relative": True},
            )
        else:
            results["expiry_date"] = TemporalEvidence(
                raw_text=expiry_raw or exp_parsed.raw_text,
                temporal_type="EXPIRY_DATE",
                absolute_date=exp_parsed.normalized_iso or exp_parsed.calendar_date,
                derivation_method="PRINTED_ABSOLUTE",
                confidence=exp_parsed.confidence,
                details={"calendar_date": exp_parsed.calendar_date},
            )

    # 4. Bidirectional consistency checks & contradiction detection
    mfg_ev = results.get("mfg_date")
    exp_ev = results.get("expiry_date")
    bb_ev = results.get("best_before")

    # Check 1: Expiry before MFD
    if mfg_ev and mfg_ev.absolute_date and exp_ev and exp_ev.absolute_date:
        implied_mo = calculate_implied_duration_months(mfg_ev.absolute_date, exp_ev.absolute_date)
        if implied_mo is not None and implied_mo < 0:
            exp_ev.contradiction_status = "EXPIRY_BEFORE_MFD"
            mfg_ev.contradiction_status = "EXPIRY_BEFORE_MFD"

    # Check 2: Relative duration vs explicit printed expiry
    if mfg_ev and mfg_ev.absolute_date and bb_ev and bb_ev.duration_value and exp_ev and exp_ev.absolute_date:
        implied_mo = calculate_implied_duration_months(mfg_ev.absolute_date, exp_ev.absolute_date)
        if implied_mo is not None:
            # Allow +- 1 month tolerance for month-end boundaries
            diff = abs(implied_mo - bb_ev.duration_value)
            if diff > 1.5:
                bb_ev.contradiction_status = "DURATION_MISMATCH"
                bb_ev.details["contradiction_reason"] = (
                    f"Declared duration {bb_ev.duration_value:g} months clashes with "
                    f"implied duration {implied_mo:g} months between MFD ({mfg_ev.absolute_date}) "
                    f"and Expiry ({exp_ev.absolute_date})"
                )

    return results
