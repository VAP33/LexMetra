"""
Generalized Evidence-Based Date Field Association Engine.

Provides generalized semantic association between OCR date labels (MFG, MFD, PKD,
PACKED ON, EXP, EXPIRY, USE BY, BEST BEFORE, etc.) and date value expressions
across diverse packaging layouts (same-line, vertical stacked, multi-column,
multi-row, rotated, separate OCR regions, and cross-surface).

Design Invariants:
1. Evidence-first: associations are based on spatial proximity, relative layout,
   reading order, column/row alignment, and semantic label strength.
2. Chronology is VALIDATION, NOT the primary assignment rule.
   Never assume "first date is manufacturing, second date is expiry".
3. Rate/unit-price expressions (e.g. 2.80/g, ₹2.80/g, = 2.80/g) are protected
   and never misidentified as dates.
4. Ambiguous or contradictory spatial evidence yields UNCERTAIN / REVIEW_REQUIRED,
   never a forced guess.
5. Preserves complete provenance: raw_text, normalized_value, bbox, image_id,
   surface_id, confidence, nearby_text, and alternative associations.
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class DateCandidate:
    """An extracted date-shaped value expression from OCR."""
    raw_text: str
    normalized_value: Optional[str]
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    confidence: float
    line_index: int
    image_id: Optional[str] = None
    surface_id: Optional[str] = None
    source_region: Optional[int] = None
    orientation: int = 0
    nearby_text: str = ""
    is_duration: bool = False
    duration_text: Optional[str] = None

    @property
    def center_x(self) -> float:
        return self.bbox[0] + self.bbox[2] / 2.0

    @property
    def center_y(self) -> float:
        return self.bbox[1] + self.bbox[3] / 2.0


@dataclass
class LabelCandidate:
    """An identified date declaration label in OCR text."""
    raw_text: str
    field_type: str  # "mfg_date" | "expiry_date"
    semantic_subtype: str  # "MFG", "PKD", "EXP", "USE_BY", "BEST_BEFORE", etc.
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    confidence: float
    line_index: int
    image_id: Optional[str] = None
    surface_id: Optional[str] = None
    source_region: Optional[int] = None
    orientation: int = 0
    has_inline_value: bool = False
    inline_value_text: Optional[str] = None

    @property
    def center_x(self) -> float:
        return self.bbox[0] + self.bbox[2] / 2.0

    @property
    def center_y(self) -> float:
        return self.bbox[1] + self.bbox[3] / 2.0


@dataclass
class DateAssociation:
    """The result of associating a DateCandidate with a LabelCandidate."""
    field: str  # "mfg_date" or "expiry_date"
    label: LabelCandidate
    date: DateCandidate
    association_score: float
    status: str  # "DETECTED", "VERIFIED", "UNCERTAIN", "REVIEW_REQUIRED"
    reason: Optional[str] = None
    alternative_associations: List[Dict[str, Any]] = field(default_factory=list)
    chronology_validated: bool = False


# ---------------------------------------------------------------------------
# Generalized Semantic Patterns
# ---------------------------------------------------------------------------

# Manufacturing / Packaging Semantic Group
# Supports: MFG, MFD, MFG. BY, MFD DATE, MANUFACTURED, MANUFACTURING DATE,
#           PACKED, PACKED ON, PKD, PACKING DATE, DATE OF PACKAGING, DOM, DOP,
#           with OCR noise/spacing variations (P K D, M F D, etc.)
MFG_LABEL_PATTERNS = [
    (re.compile(r"\bdate\s+of\s+(?:pack\w*|mfg|manufactur\w*)\b", re.I), "DATE_OF_PACK", 1.0),
    (re.compile(r"\bpacked\s+on\b|\bpacking\s+date\b|\bpkg\s+date\b", re.I), "PACKED_ON", 1.0),
    (re.compile(r"\b(?:mfg|mfd)\.?\s*(?:date|dt)\b|\bmanufacturing\s+date\b", re.I), "MFG_DATE", 1.0),
    (re.compile(r"\bmanufactur(?:ed|ing)?(?!\s*by\b)\b", re.I), "MANUFACTURED", 0.95),
    (re.compile(r"\b(?:pkd|pkg)\.?\b|\bp\s*k\s*d\b", re.I), "PKD", 0.95),
    (re.compile(r"\b(?:mfg|mfd)\.?(?!\s*by\b)\b|\bm\s*f\s*[gd]\b", re.I), "MFD", 0.95),
    (re.compile(r"\b(?:dom|dop)\b", re.I), "DOM", 0.85),
]

# Expiry / Best Before Semantic Group
# Supports: EXP, EXPIRY, EXPIRATION, USE BY, USE BEFORE, BEST BEFORE, BB,
#           CONSUME BEFORE, VALID TILL, SHELF LIFE, with OCR noise (USE 8Y, BEST-BEFORE)
EXP_LABEL_PATTERNS = [
    (re.compile(r"\b(?:use\s*by|use\s*before|use\s*8y|useby)\b", re.I), "USE_BY", 1.0),
    (re.compile(r"\bbest\s*(?:before|by)\b|\bbest-before\b", re.I), "BEST_BEFORE", 1.0),
    (re.compile(r"\bconsume\s*before\b|\bvalid\s*(?:till|through|upto)\b", re.I), "CONSUME_BEFORE", 0.95),
    (re.compile(r"\b(?:expiry|expiration)\.?\s*(?:date|dt)?\b", re.I), "EXPIRY", 0.95),
    (re.compile(r"\bexp\.?\s*(?:date|dt)?\b", re.I), "EXP", 0.95),
    (re.compile(r"\b(?:b\.?b\.?|bb)\.?\b(?!\w)", re.I), "BB", 0.85),
    (re.compile(r"\bshelf\s*life\b", re.I), "SHELF_LIFE", 0.85),
]

# Unit rate exclusion guard: matches unit prices and rates with denominators
# (e.g. = 2.80/g, ₹2.80/g, 2.80/g, 2.80 / kg, Rs 2.80/ml)
_UNIT_RATE_DENOMINATOR_RE = re.compile(
    r"(?:/\s*(?:g|kg|gm|gms|grams?|ml|l|litres?|liters?|cm|m|piece|pieces|pcs?|pc|nos?|units?))\b",
    re.I,
)

# Relative duration patterns (e.g. "12 MONTHS FROM PACKAGING", "BEST BEFORE 6 MONTHS")
_RELATIVE_DURATION_RE = re.compile(
    r"\b(\d{1,2})\s+(months?|days?|weeks?|years?)(?:\s+(?:from|of)\s+(?:pkg\w*|pkd\w*|mfd\w*|mfg\w*|pack\w*|manufactur\w*|date|production))?\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Date Extraction & Normalization
# ---------------------------------------------------------------------------

def is_unit_rate_expression(text: str) -> bool:
    """
    Check if a numeric expression is a unit sale price or rate rather than a date.
    Protects 2.80/g, ₹2.80/g, = 2.80/g from being misparsed as February 1980.
    """
    if _UNIT_RATE_DENOMINATOR_RE.search(text):
        return True
    if re.search(r"(?:₹|rs\.?|=|/)\s*\d+\.\d{2}\b", text, re.I):
        return True
    return False


def extract_raw_date_tokens(text: str) -> List[Tuple[str, int, int]]:
    """
    Extract date substrings with their character start/end spans.
    Strictly excludes unit rates with denominators while preserving MM/YY and DD/MM/YY.
    Guards against toll-free/phone numbers (e.g. 1800-10-22-221) and decimal .00 prices.
    """
    if is_unit_rate_expression(text):
        # If the line is strictly a unit rate without other content, return empty
        if re.search(r"^\s*(?:usp|unit\s*price)?\s*[:=~]?\s*(?:₹|rs\.?|=|/)?\s*\d+(?:\.\d{1,2})?\s*/\s*[a-zA-Z]+\s*$", text, re.I):
            return []

    # Guard: Customer care / toll-free / helpline telephone numbers
    # Lines declaring telephone numbers like "TOLL FREE: 1800-10-22-221" are communication lines, not dates
    if re.search(r"\b(?:toll\s*free|helpline|consumer\s*care|call|phone|tel)\b", text, re.I):
        if not re.search(r"\b(?:pkd|mfg|mfd|exp|use\s*by|best\s*before)\b", text, re.I):
            return []

    tokens: List[Tuple[str, int, int]] = []

    # 1. Relative duration expressions (e.g. "12 months from packaging")
    for m in _RELATIVE_DURATION_RE.finditer(text):
        tokens.append((m.group(0), m.start(), m.end()))

    # 2. Standard calendar dates
    date_patterns = [
        # DD/MM/YYYY or DD/MM/YY (e.g. 13/05/26, 13-05-2026, 13.05.26, 13.05.2026)
        r"(?<!\d)(?<!\d-)\b\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*(?:\d{4}|\d{2})(?!-\d)(?!\d)\b",
        # DD MonthName YYYY or MonthName YYYY (e.g. 12 OCT 2026, OCT 2026, OCT 26)
        r"\b(?:\d{1,2}\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(?:[/.-]|\s+)?(?:\d{4}|\d{2})\b",
        # YYYY/MM/DD or YYYY-MM-DD (e.g. 2026-05-13, 2024/10/22)
        # Constrained to realistic packaging years (1970-2049) and not followed/preceded by digit/hyphen (phone number guard)
        r"(?<!\d)(?<!\d-)\b(?:19[7-9]\d|20[0-4]\d)\s*[/.-]\s*\d{1,2}\s*[/.-]\s*\d{1,2}(?!-\d)(?!\d)\b",
        # MM/YYYY (e.g. 05/2026, 12-2027, 05.2026)
        r"(?<!\d)(?<!\d-)\b(?:0[1-9]|1[0-2]|[1-9])\s*[/.-]\s*(?:19[7-9]\d|20[0-4]\d)(?!-\d)(?!\d)\b",
        # MM/YY or MM-YY or MM.YY (e.g. 05/26, 12/27, 09-24, 05.26)
        # Explicit lookahead guard: cannot be followed by a unit denominator (/g, /kg, /ml, /l),
        # cannot have year "00" (which collides with decimal prices like 10.00, 12.00)
        r"(?<!\d)(?<!\d-)\b(?:0[1-9]|1[0-2])\s*[/.-]\s*(?!00\b)\d{2}(?!\s*/\s*[a-zA-Z])(?!\s*g\b)(?!\s*kg\b)(?!\s*ml\b)(?!-\d)(?!\d)\b",
    ]

    combined_re = re.compile("|".join(f"(?:{p})" for p in date_patterns), re.I)

    for m in combined_re.finditer(text):
        candidate_str = m.group(0).strip()
        # Guard: check trailing text for unit rate denominator
        tail = text[m.end():m.end() + 6]
        if _UNIT_RATE_DENOMINATOR_RE.match(tail):
            continue
        # Avoid duplicate spans
        if any(t[1] <= m.start() and m.end() <= t[2] for t in tokens):
            continue
        tokens.append((candidate_str, m.start(), m.end()))

    return tokens


def normalize_parsed_date(text: str) -> Optional[str]:
    """Normalize extracted date string to ISO format YYYY-MM-DD, YYYY-MM, or relative shelf-life."""
    if not text:
        return None
    t = text.strip()

    # Relative shelf life duration
    dur_m = _RELATIVE_DURATION_RE.search(t)
    if dur_m:
        return t.lower()

    # DD/MM/YYYY or DD.MM.YYYY or DD-MM-YYYY
    m = re.match(r"^(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4})$", t)
    if m:
        d, mo, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{yr:04d}-{mo:02d}-{d:02d}"

    # DD/MM/YY or DD.MM.YY or DD-MM-YY
    m = re.match(r"^(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{2})$", t)
    if m:
        d, mo, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            full_yr = 2000 + yr if yr < 50 else 1900 + yr
            return f"{full_yr:04d}-{mo:02d}-{d:02d}"

    # MM/YYYY
    m = re.match(r"^(\d{1,2})\s*[/.-]\s*(\d{4})$", t)
    if m:
        mo, yr = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{yr:04d}-{mo:02d}"

    # MM/YY
    m = re.match(r"^(\d{1,2})\s*[/.-]\s*(\d{2})$", t)
    if m:
        mo, yr = int(m.group(1)), int(m.group(2))
        if yr == 0:
            return None  # .00 indicates decimal precision (currency/weight), not year 2000
        if 1 <= mo <= 12:
            full_yr = 2000 + yr if yr < 50 else 1900 + yr
            return f"{full_yr:04d}-{mo:02d}"

    # YYYY-MM-DD or YYYY/MM/DD
    m = re.match(r"^(\d{4})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})$", t)
    if m:
        yr, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{yr:04d}-{mo:02d}-{d:02d}"

    # Month name
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    m = re.search(r"\b(?:(\d{1,2})\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(?:[/.-]|\s+)?(\d{2,4})\b", t, re.I)
    if m:
        day_str, mo_str, yr_str = m.group(1), m.group(2).lower(), m.group(3)
        mo = month_map.get(mo_str, 1)
        yr = int(yr_str)
        if yr < 100:
            yr = 2000 + yr if yr < 50 else 1900 + yr
        if day_str:
            d = int(day_str)
            if 1 <= d <= 31:
                return f"{yr:04d}-{mo:02d}-{d:02d}"
        return f"{yr:04d}-{mo:02d}"

    return None


# ---------------------------------------------------------------------------
# Label Identification & Candidate Extraction
# ---------------------------------------------------------------------------

def identify_date_labels(line: Any, line_index: int) -> List[LabelCandidate]:
    """Scan an OCR line for date declaration labels."""
    text = getattr(line, "text", "") or ""
    bbox = getattr(line, "bbox", (0, 0, 10, 10))
    conf = float(getattr(line, "confidence", 1.0))
    image_id = getattr(line, "image_id", None)
    surface_id = getattr(line, "surface_id", None)

    candidates: List[LabelCandidate] = []

    # Check manufacturing labels
    for pattern, subtype, weight in MFG_LABEL_PATTERNS:
        m = pattern.search(text)
        if m:
            remainder = text[m.end():].strip()
            date_tokens = extract_raw_date_tokens(remainder)

            # Guard against manufacturer/packer/marketer entity declarations ("MFG. BY:", "PACKED BY:", "MFD BY:")
            # If the label has a trailing "by" or "at" and is followed by company text rather than a date, skip it.
            if re.match(r"^[\s.:-]*(?:by\b|at\b)", text[m.end():], re.I) and not date_tokens:
                continue

            # Sub-bbox for the label if line contains extra text
            lbl_bbox = bbox
            if len(text) > len(m.group(0)) + 3 and bbox[2] > 0:
                char_w = bbox[2] / max(1, len(text))
                lbl_bbox = (
                    int(bbox[0] + m.start() * char_w),
                    bbox[1],
                    max(10, int((m.end() - m.start()) * char_w)),
                    bbox[3],
                )

            lbl_candidate = LabelCandidate(
                raw_text=m.group(0),
                field_type="mfg_date",
                semantic_subtype=subtype,
                bbox=lbl_bbox,
                confidence=conf * weight,
                line_index=line_index,
                image_id=image_id,
                surface_id=surface_id,
            )
            # Check for inline date following this label
            if date_tokens:
                lbl_candidate.has_inline_value = True
                lbl_candidate.inline_value_text = date_tokens[0][0]
            candidates.append(lbl_candidate)
            break

    # Check expiry / best before labels
    for pattern, subtype, weight in EXP_LABEL_PATTERNS:
        m = pattern.search(text)
        if m:
            lbl_bbox = bbox
            if len(text) > len(m.group(0)) + 3 and bbox[2] > 0:
                char_w = bbox[2] / max(1, len(text))
                lbl_bbox = (
                    int(bbox[0] + m.start() * char_w),
                    bbox[1],
                    max(10, int((m.end() - m.start()) * char_w)),
                    bbox[3],
                )

            lbl_candidate = LabelCandidate(
                raw_text=m.group(0),
                field_type="expiry_date",
                semantic_subtype=subtype,
                bbox=lbl_bbox,
                confidence=conf * weight,
                line_index=line_index,
                image_id=image_id,
                surface_id=surface_id,
            )
            remainder = text[m.end():].strip()
            date_tokens = extract_raw_date_tokens(remainder)
            if date_tokens:
                lbl_candidate.has_inline_value = True
                lbl_candidate.inline_value_text = date_tokens[0][0]
            candidates.append(lbl_candidate)
            break

    return candidates


# ---------------------------------------------------------------------------
# Spatial NMS & Deduplication
# ---------------------------------------------------------------------------

def _bbox_iou(boxA: Tuple[int, int, int, int], boxB: Tuple[int, int, int, int]) -> float:
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = boxA[2] * boxA[3]
    boxBArea = boxB[2] * boxB[3]

    unionArea = float(boxAArea + boxBArea - interArea)
    return interArea / unionArea if unionArea > 0 else 0.0


def deduplicate_date_candidates(candidates: List[DateCandidate]) -> List[DateCandidate]:
    """
    Merge duplicate / overlapping detections of the same physical date.
    Suppresses lower-confidence OCR misreads of the same bounding box (IOU > 0.40).
    """
    if len(candidates) <= 1:
        return candidates

    # Prefer higher confidence candidates; tie-break by tighter bounding boxes
    sorted_cands = sorted(candidates, key=lambda c: (c.confidence, -c.bbox[2] * c.bbox[3]), reverse=True)
    kept: List[DateCandidate] = []

    for c in sorted_cands:
        is_dup = False
        for k in kept:
            iou = _bbox_iou(c.bbox, k.bbox)
            dist = math.hypot(c.center_x - k.center_x, c.center_y - k.center_y)

            # High spatial overlap: overlapping OCR passes on the exact same physical print
            if iou > 0.40:
                is_dup = True
                break

            # If same normalized date and close spatial proximity
            if c.normalized_value == k.normalized_value:
                if iou > 0.15 or dist < max(c.bbox[3], k.bbox[3]) * 2.5:
                    is_dup = True
                    break

        if not is_dup:
            kept.append(c)

    # Sort back into reading order (top-to-bottom, left-to-right)
    kept.sort(key=lambda c: (c.bbox[1], c.bbox[0]))
    return kept


def deduplicate_label_candidates(candidates: List[LabelCandidate]) -> List[LabelCandidate]:
    """
    Merge duplicate / overlapping detections of the same physical label.
    Prefers tighter bounding boxes with high confidence.
    """
    if len(candidates) <= 1:
        return candidates

    sorted_cands = sorted(candidates, key=lambda c: (c.confidence, -c.bbox[2] * c.bbox[3]), reverse=True)
    kept: List[LabelCandidate] = []

    for c in sorted_cands:
        is_dup = False
        for k in kept:
            if c.field_type == k.field_type:
                iou = _bbox_iou(c.bbox, k.bbox)
                dist = math.hypot(c.center_x - k.center_x, c.center_y - k.center_y)
                if iou > 0.25 or dist < max(c.bbox[3], k.bbox[3]) * 2.5:
                    is_dup = True
                    break
        if not is_dup:
            kept.append(c)

    kept.sort(key=lambda c: (c.bbox[1], c.bbox[0]))
    return kept


# ---------------------------------------------------------------------------
# Global Bipartite Evidence Graph
# ---------------------------------------------------------------------------

class DateAssociationGraph:
    """
    Solves optimal, conflict-free association between multiple LabelCandidates
    and DateCandidates across packages.
    """
    def __init__(self) -> None:
        self.raw_labels: List[LabelCandidate] = []
        self.raw_dates: List[DateCandidate] = []

    def add_label(self, label: LabelCandidate) -> None:
        self.raw_labels.append(label)

    def add_date(self, date_cand: DateCandidate) -> None:
        self.raw_dates.append(date_cand)

    def compute_pair_affinity(
        self,
        lbl: LabelCandidate,
        dt: DateCandidate,
        all_lines: Sequence[Any],
    ) -> float:
        """
        Compute pairwise spatial affinity between a LabelCandidate and DateCandidate.
        Takes into account horizontal alignment, column alignment, reading order,
        relative displacement, and intervening labels.
        """
        lx, ly, lw, lh = lbl.bbox
        dx, dy, dw, dh = dt.bbox

        delta_x = dt.center_x - lbl.center_x
        delta_y = dt.center_y - lbl.center_y
        abs_dy = abs(delta_y)
        abs_dx = abs(delta_x)

        h_ref = max(float(lh), float(dh), 15.0)
        w_ref = max(float(lw), float(dw), 30.0)

        base_score = 0.0

        # A. Same Line / Inline Horizontal Alignment
        if abs_dy <= h_ref * 0.75:
            if delta_x > 0:
                gap_x = max(0.0, dx - (lx + lw))
                if gap_x <= 35.0:
                    base_score = 0.95  # Inline / immediately adjacent
                elif gap_x <= 300.0:
                    # Same row across a table column gap
                    base_score = 0.88 - min(0.12, (gap_x - 35.0) / 1000.0)
                else:
                    base_score = 0.65
            else:
                # Left of label in same line is heavily penalized
                base_score = 0.15

        # B. Vertical Stacked Alignment (Date directly below label)
        elif delta_y > 0 and abs_dx <= w_ref * 1.3:
            gap_y = max(0.0, dy - (ly + lh))
            if gap_y <= h_ref * 2.0:
                base_score = 0.90
            elif gap_y <= h_ref * 4.5:
                base_score = 0.78
            else:
                base_score = 0.55

        # C. Two-Column Staggered Alignment (Values to the right, slightly below labels)
        elif delta_x > 30.0 and 0.0 < delta_y <= h_ref * 3.5:
            base_score = 0.82 - min(0.15, delta_y / 250.0)

        # D. General Proximity Fallback
        if base_score == 0.0:
            if delta_x < -w_ref * 0.5 and delta_y < -h_ref * 0.5:
                # Value is above and to the left of the label in reading space
                base_score = 0.05
            else:
                # Normalize distances with vertical distance penalized more heavily
                dist = math.hypot(delta_x, delta_y * 2.2)
                base_score = max(0.08, 0.60 - min(0.50, dist / 800.0))

        # E. Intervening Label Penalty
        # If another date declaration label is physically positioned between this label and date
        for other_line in all_lines:
            ol_text = getattr(other_line, "text", "") or ""
            if any(p[0].search(ol_text) for p in MFG_LABEL_PATTERNS + EXP_LABEL_PATTERNS):
                ox, oy, ow, oh = getattr(other_line, "bbox", (0, 0, 0, 0))
                oc_y = oy + oh / 2.0
                if min(lbl.center_y, dt.center_y) + 5.0 < oc_y < max(lbl.center_y, dt.center_y) - 5.0:
                    if max(lx, dx) - 40 <= ox <= min(lx + lw, dx + dw) + 40:
                        base_score *= 0.25

        final_affinity = base_score * (0.4 + 0.6 * lbl.confidence) * (0.4 + 0.6 * dt.confidence)
        return round(float(final_affinity), 4)

    def solve(self, all_lines: Sequence[Any]) -> Dict[str, DateAssociation]:
        """
        Compute optimal global bipartite matching maximizing total affinity score.
        Enforces 1-to-1 constraint per date candidate and flags ambiguous ties.
        Uses permutation search with monotonic rank-order alignment and vector parallelism.
        """
        results: Dict[str, DateAssociation] = {}

        # 1. Deduplicate candidate detections
        labels = deduplicate_label_candidates(self.raw_labels)
        dates = deduplicate_date_candidates(self.raw_dates)

        if not labels or not dates:
            return results

        # Group labels by target field type (keep highest confidence label per field)
        field_labels: Dict[str, LabelCandidate] = {}
        for l in labels:
            if l.field_type not in field_labels or l.confidence > field_labels[l.field_type].confidence:
                field_labels[l.field_type] = l

        active_labels = list(field_labels.values())

        # Build pairwise affinity matrix
        # affinity_map[label_candidate, date_candidate] -> float
        pair_scores: Dict[Tuple[int, int], float] = {}
        for l_idx, lbl in enumerate(active_labels):
            for d_idx, dt in enumerate(dates):
                pair_scores[(l_idx, d_idx)] = self.compute_pair_affinity(lbl, dt, all_lines)

        # 2. Evaluate Global Matching Hypotheses
        # We consider all valid 1-to-1 assignments from active_labels to dates (or None)
        import itertools

        best_hypothesis: Optional[Dict[int, int]] = None
        best_score = -1e9
        all_hypotheses: List[Tuple[float, Dict[int, int]]] = []

        m = len(active_labels)
        n = len(dates)

        # Generate assignments where each label is assigned to a unique date or None
        # Candidate date indices plus None slots for unassigned
        date_slots: List[Optional[int]] = list(range(n)) + [None] * m

        seen_assignments: set[Tuple[Optional[int], ...]] = set()
        for p in itertools.permutations(date_slots, m):
            assignment = tuple(p)
            if assignment in seen_assignments:
                continue
            seen_assignments.add(assignment)

            matched_pairs = [(l_idx, d_idx) for l_idx, d_idx in enumerate(assignment) if d_idx is not None]
            if not matched_pairs:
                continue

            # Base score: sum of affinities
            hyp_score = sum(pair_scores[(l_idx, d_idx)] for l_idx, d_idx in matched_pairs)

            # Reject hypotheses containing individually incompatible pairs (< 0.20 affinity)
            if any(pair_scores[(l_idx, d_idx)] < 0.20 for l_idx, d_idx in matched_pairs):
                continue

            # Geometric Coherence Check (when 2 or more fields are matched simultaneously)
            if len(matched_pairs) >= 2:
                for idx_a in range(len(matched_pairs)):
                    for idx_b in range(idx_a + 1, len(matched_pairs)):
                        l_a_idx, d_a_idx = matched_pairs[idx_a]
                        l_b_idx, d_b_idx = matched_pairs[idx_b]

                        lbl_a = active_labels[l_a_idx]
                        lbl_b = active_labels[l_b_idx]
                        dt_a = dates[d_a_idx]
                        dt_b = dates[d_b_idx]

                        # A. Vertical Monotonic Alignment
                        delta_y_lbl = lbl_b.center_y - lbl_a.center_y
                        delta_y_dt = dt_b.center_y - dt_a.center_y

                        if abs(delta_y_lbl) > 15.0:
                            if (delta_y_lbl > 0 and delta_y_dt > -15.0) or (delta_y_lbl < 0 and delta_y_dt < 15.0):
                                # Parallel vertical reading order (top label -> top date, bottom -> bottom)
                                hyp_score += 0.35
                            else:
                                # Lines cross vertically! (top label -> bottom date, bottom label -> top date)
                                hyp_score -= 0.85

                        # B. Horizontal Monotonic Alignment
                        delta_x_lbl = lbl_b.center_x - lbl_a.center_x
                        delta_x_dt = dt_b.center_x - dt_a.center_x

                        if abs(delta_x_lbl) > 30.0:
                            if (delta_x_lbl > 0 and delta_x_dt > -20.0) or (delta_x_lbl < 0 and delta_x_dt < 20.0):
                                # Parallel horizontal reading order
                                hyp_score += 0.25
                            else:
                                # Lines cross horizontally!
                                hyp_score -= 0.65

                        # C. Displacement Vector Parallelism
                        v_ax = dt_a.center_x - lbl_a.center_x
                        v_ay = dt_a.center_y - lbl_a.center_y
                        v_bx = dt_b.center_x - lbl_b.center_x
                        v_by = dt_b.center_y - lbl_b.center_y

                        diff_v = math.hypot(v_ax - v_bx, v_ay - v_by)
                        if diff_v < 80.0:
                            hyp_score += 0.20
                        elif diff_v < 160.0:
                            hyp_score += 0.10

                        if v_ay * v_by < -300.0:
                            # One vector points upwards, the other points downwards
                            hyp_score -= 0.45

            all_hypotheses.append((hyp_score, dict(matched_pairs)))
            if hyp_score > best_score:
                best_score = hyp_score
                best_hypothesis = dict(matched_pairs)

        if not best_hypothesis or best_score < 0.20:
            return results

        # 3. Check for Ambiguity
        # Sort hypotheses to find alternative distinct matchings
        all_hypotheses.sort(key=lambda x: x[0], reverse=True)
        is_ambiguous = False
        runner_up = None
        for score, hyp in all_hypotheses[1:]:
            # If the hypothesis proposes a different date for any field
            if hyp != best_hypothesis:
                runner_up = (score, hyp)
                if abs(best_score - score) < 0.08 and score > 0.45:
                    is_ambiguous = True
                break

        # 4. Construct DateAssociation Results
        for l_idx, d_idx in best_hypothesis.items():
            lbl = active_labels[l_idx]
            dt = dates[d_idx]
            assoc_score = pair_scores[(l_idx, d_idx)]

            alternatives: List[Dict[str, Any]] = []
            for other_d_idx, other_dt in enumerate(dates):
                if other_d_idx != d_idx:
                    alternatives.append({
                        "raw_text": other_dt.raw_text,
                        "normalized_value": other_dt.normalized_value,
                        "bbox": other_dt.bbox,
                        "affinity_score": pair_scores.get((l_idx, other_d_idx), 0.0),
                    })

            assoc = DateAssociation(
                field=lbl.field_type,
                label=lbl,
                date=dt,
                association_score=assoc_score,
                status="REVIEW_REQUIRED" if is_ambiguous else "DETECTED",
                reason=(
                    f"Ambiguous spatial association between '{lbl.raw_text}' and multiple candidate dates."
                    if is_ambiguous else None
                ),
                alternative_associations=alternatives,
            )
            results[lbl.field_type] = assoc

        # 5. Chronological Validation (as VALIDATION, NOT primary assignment)
        if "mfg_date" in results and "expiry_date" in results:
            mfg_assoc = results["mfg_date"]
            exp_assoc = results["expiry_date"]

            mfg_norm = mfg_assoc.date.normalized_value
            exp_norm = exp_assoc.date.normalized_value

            if mfg_norm and exp_norm and not mfg_assoc.date.is_duration and not exp_assoc.date.is_duration:
                if str(mfg_norm) <= str(exp_norm):
                    mfg_assoc.chronology_validated = True
                    exp_assoc.chronology_validated = True
                else:
                    # Illogical date sequence: manufacturing date is after expiry date
                    # Do NOT blindly swap; preserve evidence and flag for human review
                    mfg_assoc.status = "REVIEW_REQUIRED"
                    exp_assoc.status = "REVIEW_REQUIRED"
                    mfg_assoc.reason = (
                        f"Illogical date sequence: extracted manufacturing date ({mfg_norm}) "
                        f"is after expiry date ({exp_norm}). Flagged for human verification."
                    )
                    exp_assoc.reason = mfg_assoc.reason

        return results


# ---------------------------------------------------------------------------
# High-Level Public API
# ---------------------------------------------------------------------------

def associate_date_fields(
    lines: Sequence[Any],
    *,
    image_id: Optional[str] = None,
    surface_id: Optional[str] = None,
) -> Dict[str, dict]:
    """
    Public entry point for generalized evidence-based date association.
    
    Transforms raw OCR lines into structured date declaration facts for:
    - mfg_date (Date of manufacturing / packing / PKD)
    - expiry_date (Expiry / Use By / Best Before / Shelf Life)
    
    Preserves exact provenance, alternative readings, and handles multi-column,
    stacked, same-line, and rotated layouts.
    """
    graph = DateAssociationGraph()

    for idx, line in enumerate(lines):
        text = getattr(line, "text", "") or ""
        bbox = getattr(line, "bbox", (0, 0, 10, 10))
        conf = float(getattr(line, "confidence", 1.0))
        l_img = getattr(line, "image_id", image_id)
        l_surf = getattr(line, "surface_id", surface_id)

        # Discover labels
        labels = identify_date_labels(line, idx)
        for lbl in labels:
            if l_img:
                lbl.image_id = l_img
            if l_surf:
                lbl.surface_id = l_surf
            graph.add_label(lbl)

        # Discover date values
        date_tokens = extract_raw_date_tokens(text)
        for dt_str, start_char, end_char in date_tokens:
            norm_val = normalize_parsed_date(dt_str)
            is_dur = bool(_RELATIVE_DURATION_RE.search(dt_str))

            dt_bbox = bbox
            if len(text) > len(dt_str) + 4 and bbox[2] > 0:
                char_w = bbox[2] / max(1, len(text))
                sub_x = int(bbox[0] + start_char * char_w)
                sub_w = max(10, int((end_char - start_char) * char_w))
                dt_bbox = (sub_x, bbox[1], sub_w, bbox[3])

            dt_cand = DateCandidate(
                raw_text=dt_str,
                normalized_value=norm_val,
                bbox=dt_bbox,
                confidence=conf,
                line_index=idx,
                image_id=l_img,
                surface_id=l_surf,
                is_duration=is_dur,
                duration_text=dt_str if is_dur else None,
            )
            graph.add_date(dt_cand)

    # Solve global bipartite matching
    associations = graph.solve(lines)

    classified_dates: Dict[str, dict] = {}

    for field_name, assoc in associations.items():
        val_text = assoc.date.raw_text
        norm_val = assoc.date.normalized_value

        # The declaration extraction confidence combines OCR token readability with association strength
        token_conf = float(assoc.date.confidence or 0.8)
        lbl_conf = float(assoc.label.confidence or 0.8)
        assoc_score = float(assoc.association_score)

        if assoc.status == "DETECTED":
            comp_conf = min(token_conf, max(lbl_conf, min(1.0, assoc_score * 1.25)))
            composite_confidence = round(float(comp_conf), 4)
        else:
            composite_confidence = round(float(min(token_conf, assoc_score)), 4)

        entry: Dict[str, Any] = {
            "field": field_name,
            "label": assoc.label.raw_text,
            "value": val_text,
            "normalized_value": norm_val,
            "date_value": val_text,
            "raw_text": f"{assoc.label.raw_text} {val_text}".strip(),
            "confidence": composite_confidence,
            "association_score": round(assoc_score, 4),
            "bbox": assoc.date.bbox,
            "label_bbox": assoc.label.bbox,
            "source": (
                "ocr_date_association_inline"
                if assoc.label.line_index == assoc.date.line_index
                else "ocr_date_association_bipartite"
            ),
            "status": assoc.status,
            "alternative_associations": assoc.alternative_associations,
            "chronology_validated": assoc.chronology_validated,
        }
        if assoc.reason:
            entry["reason"] = assoc.reason

        if assoc.date.is_duration:
            entry["is_duration"] = True
            entry["duration_text"] = assoc.date.duration_text

        classified_dates[field_name] = entry

    # Emit REVIEW_REQUIRED for unassociated labels
    for lbl in deduplicate_label_candidates(graph.raw_labels):
        if lbl.field_type not in classified_dates:
            classified_dates[lbl.field_type] = {
                "field": lbl.field_type,
                "label": lbl.raw_text,
                "value": None,
                "normalized_value": None,
                "date_value": None,
                "raw_text": lbl.raw_text,
                "confidence": round(float(lbl.confidence * 0.35), 4),
                "bbox": lbl.bbox,
                "label_bbox": lbl.bbox,
                "source": "ocr_date_label_only",
                "status": "REVIEW_REQUIRED",
                "reason": f"Declaration label '{lbl.raw_text}' was detected, but no matching date value could be established from evidence.",
            }

    return classified_dates
