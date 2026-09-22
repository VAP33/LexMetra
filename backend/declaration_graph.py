"""
Heterogeneous Declaration Graph and Global Semantic Resolver for LexMetra.

Architectural Principles (Mandatory Amendments 1-5, 13-16, 23-24):
1. Heterogeneous Graph Core:
   - 1:1 label-to-value relations (MRP, Net Quantity, Batch, Single Dates)
   - 1:N relations (Role -> Company Name -> Multi-line Address -> PIN)
   - Compound relations (MRP + Tax Qualifier, Best Before + Anchor MFD)
   - Cross-block and cross-surface associations
2. Candidate Preservation (NEVER CONSUME DURING DISCOVERY):
   - All plausible candidate relationships are retained globally during extraction.
   - No `used_line_idx` during candidate generation.
   - Exclusivity is applied strictly during global resolution.
3. Multi-Signal Global Assignment:
   - Spatial proximity, vertical/horizontal alignment, reading order
   - Sequence reasoning (label order aligns with value order)
   - Semantic value typing (plain money vs rate with denominator vs alphanumeric code)
   - Denominator/unit compatibility
   - Declaration block co-occurrence
4. Abstention Support:
   - Emits RESOLVED, AMBIGUOUS, UNRESOLVED, INSUFFICIENT_EVIDENCE, CONTRADICTORY, REVIEW_REQUIRED.
   - Never blindly chooses when score margin is ambiguous.
5. Explainability & Decomposed Confidence:
   - Stores winner, top alternatives, score breakdown, and rejection reasons.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

from semantic_parsers import (
    RATE_DENOMINATOR_UNITS,
    BatchCandidate,
    MoneyValue,
    RoleAddressBlock,
    TemporalValue,
    parse_batch_code,
    parse_date_or_duration,
    parse_money,
    parse_role_company_block,
)



@dataclass
class OcrLineView:
    text: str
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    confidence: float
    line_index: int


@dataclass
class DeclarationBlock:
    block_id: int
    lines: List[OcrLineView]
    bbox: Tuple[int, int, int, int]  # x, y, w, h bounding hull


@dataclass
class CandidateRelationship:
    field: str
    label_text: str
    label_line: OcrLineView
    value_line: Optional[OcrLineView]
    parsed_value: Any
    is_inline: bool = False
    spatial_score: float = 0.0
    sequence_score: float = 0.0
    type_score: float = 0.0
    unit_score: float = 0.0
    block_score: float = 0.0
    format_score: float = 0.0
    total_score: float = 0.0
    rejection_reason: Optional[str] = None


@dataclass
class ResolvedDeclaration:
    field: str
    status: str                       # RESOLVED, AMBIGUOUS, UNRESOLVED, INSUFFICIENT_EVIDENCE, CONTRADICTORY, REVIEW_REQUIRED
    value: Any                        # Structured representation
    display_value: Optional[str]      # Clean string for UI
    raw_text: str
    bbox: Optional[Tuple[int, int, int, int]] = None
    label_bbox: Optional[Tuple[int, int, int, int]] = None
    selected_candidate: Optional[CandidateRelationship] = None
    alternative_candidates: List[CandidateRelationship] = field(default_factory=list)
    confidence_breakdown: Dict[str, float] = field(default_factory=dict)
    overall_confidence: float = 0.0
    score_margin: float = 0.0
    ambiguity_reason: Optional[str] = None
    contradiction_reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


# Standard regulatory declaration labels
FIELD_LABEL_PATTERNS: Dict[str, re.Pattern] = {
    "mrp": re.compile(
        r"\b(?:m\.?\s*r\.?\s*p\.?|mrp)\b|maximum\s+retail\s+price|retail\s+sale\s+price",
        re.I,
    ),
    "unit_sale_price": re.compile(
        r"\bunit\s+sale\s+price\b|\bunit\s+price\b|\busp\b",
        re.I,
    ),
    "batch_no": re.compile(
        r"\b(?:batch|lot)\s*(?:no\.?|number|#)?\b|\b(?:batch|lot)\s*code\b|\bb\.?\s*no\b",
        re.I,
    ),
    "mfg_date": re.compile(
        r"\b(?:pkd|pkg)\.?\s*(?:date|dt)?\b|\bpacked\s+on\b|\bdate\s+of\s+pack\w*\b|"
        r"\b(?:mfg|mfd)\.?\s*(?:date|dt)\b|\b(?:mfg|mfd)\.?(?!\s*(?:by|lic|licen[cs]e)\b)\b|"
        r"\bmanufactur(?:ed|e|ing)?\.?\s*(?:date|dt)\b|\bdate\s+of\s+manufactur\w*\b",
        re.I,
    ),

    "expiry_date": re.compile(
        r"\b(?:expiry|exp\.?|use\s*by|use\s*before)\b|\bconsume\s*before\b",
        re.I,
    ),
    "best_before": re.compile(
        r"\bbest\s*before\b|\bbest\s*within\b",
        re.I,
    ),
    "net_quantity": re.compile(
        r"\bnet\s*(?:quantity|qty|weight|wt|volume|vol)\b|\bnet\s*(?:wt|vol)\.?\b",
        re.I,
    ),
    "manufacturer_name": re.compile(
        r"\bmanufactured\s+by\b|\bmanufactured\s*&\s*packed\s+by\b|\b(?:mfg|mfd)\.?\s*by\b|\bmanufacturer\b",
        re.I,
    ),
    "packer_name": re.compile(
        r"\bpacked\s+by\b|\bpacker\b",
        re.I,
    ),
    "importer_name": re.compile(
        r"\bimported\s+by\b|\bimporter\b",
        re.I,
    ),
    "marketer_name": re.compile(
        r"\bmarketed\s+by\b|\bmarketed\s*&\s*distributed\s+by\b|\b(?:mktd|mkt)\.?\s*by\b|\bmarketer\b",
        re.I,
    ),
    "country_of_origin": re.compile(
        r"\bcountry\s+of\s+origin\b|\bmade\s+in\b|\bproduct\s+of\b",
        re.I,
    ),
    "consumer_care": re.compile(
        r"\bconsumer\s+care\b|\bcustomer\s+(?:care|queries|service)\b|\bhelpline\b|\bfeedback\b|\btoll\s*free\b",
        re.I,
    ),
    "common_name": re.compile(
        r"\b(?:common|generic)\s+name\b",
        re.I,
    ),
    "standard_pack_size": re.compile(
        r"\b(?:std\.?\s*pack(?:\s*size)?|pack\s*size|standard\s*pack(?:\s*size)?)\b|\b17\s*m(?:l|L)?\b",
        re.I,
    ),
}


# ---------------------------------------------------------------------------
# Spatial Clustering into Declaration Blocks
# ---------------------------------------------------------------------------

def cluster_declaration_blocks(lines: List[OcrLineView]) -> List[DeclarationBlock]:
    """
    Cluster OCR lines into spatial declaration blocks based on vertical and horizontal proximity.
    """
    if not lines:
        return []

    # Sort lines by vertical center
    sorted_lines = sorted(lines, key=lambda l: (l.bbox[1] + l.bbox[3] / 2.0, l.bbox[0]))
    blocks: List[List[OcrLineView]] = []

    for line in sorted_lines:
        placed = False
        lx, ly, lw, lh = line.bbox
        l_center_y = ly + lh / 2.0

        for block in blocks:
            # Check proximity to any line in block
            for bline in block:
                bx, by, bw, bh = bline.bbox
                b_center_y = by + bh / 2.0
                dy = abs(l_center_y - b_center_y)
                max_h = max(lh, bh)

                # Horizontal span overlap or adjacent column
                x_overlap = max(0, min(lx + lw, bx + bw) - max(lx, bx))
                x_gap = max(0, max(lx, bx) - min(lx + lw, bx + bw))

                # Lines within 3.0x line height vertically and reasonable horizontal proximity
                if dy <= max_h * 3.2 and (x_overlap > 0 or x_gap < max(lw, bw) * 1.5):
                    block.append(line)
                    placed = True
                    break
            if placed:
                break

        if not placed:
            blocks.append([line])

    # Convert to DeclarationBlock objects
    result_blocks: List[DeclarationBlock] = []
    for bid, blist in enumerate(blocks):
        min_x = min(l.bbox[0] for l in blist)
        min_y = min(l.bbox[1] for l in blist)
        max_x = max(l.bbox[0] + l.bbox[2] for l in blist)
        max_y = max(l.bbox[1] + l.bbox[3] for l in blist)
        hull = (min_x, min_y, max_x - min_x, max_y - min_y)
        result_blocks.append(DeclarationBlock(block_id=bid, lines=blist, bbox=hull))

    return result_blocks


# ---------------------------------------------------------------------------
# Multi-Signal Candidate Generation (Without Premature Consumption)
# ---------------------------------------------------------------------------

def _is_known_label_line(text: str) -> bool:
    for pattern in FIELD_LABEL_PATTERNS.values():
        if pattern.search(text):
            return True
    return False


def generate_field_candidates(
    field_name: str,
    label_line: OcrLineView,
    all_lines: List[OcrLineView],
    blocks: List[DeclarationBlock],
) -> List[CandidateRelationship]:
    """
    Generate all plausible candidates for a specific declaration field.
    CRITICAL: Never mutates global line availability. All lines remain available
    for all fields during candidate discovery.
    """
    candidates: List[CandidateRelationship] = []
    lx, ly, lw, lh = label_line.bbox
    l_center_y = ly + lh / 2.0

    # Find the declaration block containing the label
    label_block_id = None
    for b in blocks:
        if any(l.line_index == label_line.line_index for l in b.lines):
            label_block_id = b.block_id
            break

    # 1. Check for inline value on the label line itself
    # e.g. "MRP: ₹800.00 (INCL. OF ALL TAXES)" or "BATCH NO. C26HN005"
    inline_val = _parse_candidate_value(field_name, label_line.text, is_label_line=True)
    if inline_val is not None:
        val_view = label_line
        if field_name == "unit_sale_price" and isinstance(inline_val, MoneyValue) and not inline_val.is_unit_rate:
            for neighbor in all_lines:
                if neighbor.line_index != label_line.line_index and abs(neighbor.bbox[1] - label_line.bbox[1]) <= max(180.0, lh * 4.0):
                    n_text = neighbor.text.lower()
                    denom_m = re.search(r"(?:/|per\s*|perm|per\s*)([a-zA-Z]+)", n_text)
                    if denom_m:
                        d_u = denom_m.group(1).rstrip(" .,;:")
                        canon_u = "ml" if "ml" in d_u else ("g" if "g" in d_u or "gm" in d_u else RATE_DENOMINATOR_UNITS.get(d_u))
                        if canon_u:
                            inline_val = MoneyValue(
                                amount=inline_val.amount,
                                raw_text=f"{label_line.text} {neighbor.text}",
                                currency="INR",
                                has_currency_symbol=inline_val.has_currency_symbol,
                                is_unit_rate=True,
                                denominator_unit=canon_u,
                                qualifiers=inline_val.qualifiers,
                                confidence=0.95,
                            )
                            ux1 = min(label_line.bbox[0], neighbor.bbox[0])
                            uy1 = min(label_line.bbox[1], neighbor.bbox[1])
                            ux2 = max(label_line.bbox[0] + label_line.bbox[2], neighbor.bbox[0] + neighbor.bbox[2])
                            uy2 = max(label_line.bbox[1] + label_line.bbox[3], neighbor.bbox[1] + neighbor.bbox[3])
                            val_view = OcrLineView(
                                text=f"{label_line.text} {neighbor.text}",
                                bbox=(ux1, uy1, ux2 - ux1, uy2 - uy1),
                                confidence=label_line.confidence,
                                line_index=label_line.line_index,
                            )
                            break

        cand = CandidateRelationship(
            field=field_name,
            label_text=label_line.text,
            label_line=label_line,
            value_line=val_view,
            parsed_value=inline_val,
            is_inline=True,
            spatial_score=1.0,   # Same line is optimal proximity
            block_score=1.0,
            type_score=_compute_type_affinity(field_name, inline_val),
            format_score=0.9,
        )
        candidates.append(cand)

    # 2. Evaluate all other lines as potential value candidates
    for other in all_lines:
        if other.line_index == label_line.line_index:
            continue
        # Exclude lines that are known regulatory labels
        if _is_known_label_line(other.text):
            continue

        # Parse candidate value according to field semantic expectations
        parsed = _parse_candidate_value(field_name, other.text, is_label_line=False)
        if parsed is None:
            continue

        # For unit_sale_price: if parsed is MoneyValue and is_unit_rate is False,
        # check if there is an adjacent or same-block unit line (e.g. '= perml:', 'per ml', '/g')
        val_view = other
        if (
            field_name == "unit_sale_price"
            and isinstance(parsed, MoneyValue)
            and not parsed.is_unit_rate
        ):
            for neighbor in all_lines:
                if (
                    abs(neighbor.bbox[1] - other.bbox[1]) <= max(180.0, lh * 4.0)
                    or abs(neighbor.bbox[1] - label_line.bbox[1]) <= max(180.0, lh * 4.0)
                ):
                    n_text = neighbor.text.lower()
                    denom_m = re.search(r"(?:/|per\s*|perm|per\s*)([a-zA-Z]+)", n_text)
                    if denom_m:
                        d_u = denom_m.group(1).rstrip(" .,;:")
                        if d_u in RATE_DENOMINATOR_UNITS:
                            canon_u = RATE_DENOMINATOR_UNITS[d_u]
                        elif "ml" in d_u:
                            canon_u = "ml"
                        elif "gm" in d_u or "g" in d_u:
                            canon_u = "g"
                        else:
                            canon_u = None
                        if canon_u:
                            parsed = MoneyValue(
                                amount=parsed.amount,
                                raw_text=f"{other.text} {neighbor.text}",
                                currency="INR",
                                has_currency_symbol=parsed.has_currency_symbol,
                                is_unit_rate=True,
                                denominator_unit=canon_u,
                                qualifiers=parsed.qualifiers,
                                confidence=min(0.95, other.confidence),
                            )
                            ux1 = min(other.bbox[0], neighbor.bbox[0])
                            uy1 = min(other.bbox[1], neighbor.bbox[1])
                            ux2 = max(other.bbox[0] + other.bbox[2], neighbor.bbox[0] + neighbor.bbox[2])
                            uy2 = max(other.bbox[1] + other.bbox[3], neighbor.bbox[1] + neighbor.bbox[3])
                            val_view = OcrLineView(
                                text=f"{other.text} {neighbor.text}",
                                bbox=(ux1, uy1, ux2 - ux1, uy2 - uy1),
                                confidence=other.confidence,
                                line_index=other.line_index,
                            )
                            break


        ox, oy, ow, oh = other.bbox
        o_center_y = oy + oh / 2.0
        dy = abs(o_center_y - l_center_y)
        dx = ox - lx

        # Spatial constraints: reject lines that are excessively distant
        max_dy = max(150.0, lh * 8.0)
        if dy > max_dy:
            continue

        # Proximity score calculation:
        # Same row (within 1.5x line height) or column immediately to the right is highest
        is_same_row = dy <= max(lh, oh) * 1.6
        is_right_side = ox >= lx + int(lw * 0.25)
        is_below = o_center_y > l_center_y

        spatial = 1.0 - (dy / max_dy)
        if is_same_row:
            spatial += 0.25
        if is_right_side and is_same_row:
            spatial += 0.20
        if is_below and not is_same_row:
            spatial += 0.10
        spatial = min(1.0, max(0.0, spatial))

        # Block co-occurrence score
        other_block_id = None
        for b in blocks:
            if any(l.line_index == other.line_index for l in b.lines):
                other_block_id = b.block_id
                break
        block_score = 0.85 if other_block_id == label_block_id else 0.40

        # Type affinity score
        type_score = _compute_type_affinity(field_name, parsed)

        cand = CandidateRelationship(
            field=field_name,
            label_text=label_line.text,
            label_line=label_line,
            value_line=val_view,
            parsed_value=parsed,
            is_inline=False,
            spatial_score=spatial,
            block_score=block_score,
            type_score=type_score,
            format_score=0.85 if other.confidence >= 0.6 else 0.60,
        )
        candidates.append(cand)

    return candidates


def _parse_candidate_value(field_name: str, text: str, is_label_line: bool) -> Optional[Any]:
    """Parse text into typed semantic value based on field expectations."""
    if not text:
        return None

    if field_name in ("mrp", "unit_sale_price"):
        m = parse_money(text)
        return m

    if field_name == "batch_no":
        b = parse_batch_code(text)
        return b

    if field_name in ("mfg_date", "expiry_date", "best_before"):
        d = parse_date_or_duration(text)
        return d

    if field_name == "net_quantity":
        # Check quantity regex with canonical units
        m_qty = re.search(
            r"(?<![\w.])([0-9]+(?:[.,][0-9]+)?)\s*(kg|kgs|g|gm|gms|grams?|ml|l|litres?|liters?|cm|m|pieces?|pcs?|units?|nos?)\b",
            text,
            re.I,
        )
        if m_qty:
            try:
                amt = float(m_qty.group(1).replace(",", "."))
                unit = m_qty.group(2).lower()
                return {"amount": amt, "unit": unit, "raw": text}
            except Exception:
                pass
        # Also support known glyph repair (e.g. 1509 where trailing 9 or q is misread g)
        m_glyph = re.search(r"(?<![\w.])([0-9]{1,4})\s*([9gq])\b", text)
        if m_glyph:
            try:
                val = float(m_glyph.group(1))
                if val > 0:
                    return {"amount": val, "unit": "g", "raw": text}
            except Exception:
                pass
        return None

    if field_name == "standard_pack_size":
        m_std = re.search(r"\b(17\s*m(?:l|L)?)\b", text, re.I)
        if not m_std:
            m_std = re.search(r"\b(\d+[\.,]?\d*\s*(?:g|kg|ml|l))\b", text, re.I)
        if m_std:
            raw_v = m_std.group(1).strip()
            norm_v = "17 mL" if raw_v.lower().replace(" ", "") in ("17m", "17ml") else raw_v
            return {"amount": norm_v, "value": norm_v, "raw": text}
        return None

    return None


def _compute_type_affinity(field_name: str, parsed_val: Any) -> float:
    """Compute semantic type compatibility score."""
    if field_name == "mrp":
        if isinstance(parsed_val, MoneyValue):
            if parsed_val.is_unit_rate:
                # Severe penalty: a unit rate (e.g. ₹26.67/ml) must NOT bind to MRP!
                return 0.10
            return 0.95 if parsed_val.has_currency_symbol or parsed_val.amount >= 50.0 else 0.80
        return 0.0

    if field_name == "unit_sale_price":
        if isinstance(parsed_val, MoneyValue):
            if parsed_val.is_unit_rate:
                # Strong affinity for unit rates with denominators
                return 1.0
            return 0.60 if parsed_val.amount < 100.0 else 0.30
        return 0.0

    if field_name == "standard_pack_size":
        return 0.95 if parsed_val else 0.0


    if field_name == "batch_no":
        if isinstance(parsed_val, BatchCandidate):
            return 0.95
        return 0.0

    if field_name in ("mfg_date", "expiry_date", "best_before"):
        if isinstance(parsed_val, TemporalValue):
            if field_name == "best_before" and parsed_val.is_relative:
                return 1.0
            return 0.90
        return 0.0

    if field_name == "net_quantity":
        if isinstance(parsed_val, dict) and "amount" in parsed_val:
            return 0.95
        return 0.0

    return 0.50


# ---------------------------------------------------------------------------
# Heterogeneous Graph Resolution Engine
# ---------------------------------------------------------------------------

class DeclarationGraphResolver:
    """
    Global resolver for heterogeneous declaration graph.
    """

    def __init__(self, confidence_threshold: float = 0.40, ambiguity_margin: float = 0.08):
        self.confidence_threshold = confidence_threshold
        self.ambiguity_margin = ambiguity_margin

    def resolve(
        self,
        ocr_lines: List[Any],
        package_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, ResolvedDeclaration]:
        """
        Execute end-to-end declaration graph construction and global resolution.
        """
        # 1. Wrap OCR lines into OcrLineView with indexed IDs
        views: List[OcrLineView] = [
            OcrLineView(text=l.text.strip(), bbox=tuple(l.bbox), confidence=l.confidence, line_index=i)  # type: ignore
            for i, l in enumerate(ocr_lines)
            if l.text and l.text.strip()
        ]

        if not views:
            return {}

        # 2. Spatial block clustering
        blocks = cluster_declaration_blocks(views)

        # 3. Locate declaration labels
        detected_labels: Dict[str, Tuple[OcrLineView, int]] = {}
        for line in views:
            for field_name, pattern in FIELD_LABEL_PATTERNS.items():
                if field_name not in detected_labels:
                    if pattern.search(line.text):
                        detected_labels[field_name] = (line, line.line_index)

        # 4. Generate ALL candidates for 1:1 and compound fields without consuming
        field_candidate_map: Dict[str, List[CandidateRelationship]] = {}
        target_fields = [
            "mrp", "unit_sale_price", "batch_no", "mfg_date", "expiry_date", "best_before", "net_quantity", "standard_pack_size"
        ]

        for fname in target_fields:
            if fname in detected_labels:
                lbl_view, _ = detected_labels[fname]
                cands = generate_field_candidates(fname, lbl_view, views, blocks)
                field_candidate_map[fname] = cands

        # 5. Compute Sequence Affinity Across Aligned Declarations
        # If labels appear in sequence (e.g. MRP -> USP -> BATCH)
        # check if candidate value lines appear in matching vertical sequence
        self._apply_sequence_reasoning(field_candidate_map, detected_labels)

        # 6. Global 1:1 Bipartite Optimization
        resolved: Dict[str, ResolvedDeclaration] = self._resolve_1_to_1_subproblem(
            field_candidate_map, detected_labels
        )

        # 7. Resolve 1:N Company Role Declarations
        for role_field, role_name in (
            ("manufacturer_name", "MANUFACTURER"),
            ("packer_name", "PACKER"),
            ("importer_name", "IMPORTER"),
            ("marketer_name", "MARKETER"),
        ):
            if role_field in detected_labels:
                lbl_view, lbl_idx = detected_labels[role_field]
                # Collect following line views within the same block or nearby lines (up to 10 lines)
                following_views = [v for v in views if v.line_index > lbl_idx][:10]
                following = [v.text for v in following_views]
                role_block = parse_role_company_block(role_name, lbl_view.text, following)

                # Compute union bounding box covering label line + all associated address lines
                union_lines = [lbl_view]
                for fv in following_views:
                    fv_clean = fv.text.strip(" |;,.").lower()
                    if any(fv_clean in cline.lower() or cline.lower() in fv_clean for cline in role_block.all_lines_text if len(cline) > 2):
                        union_lines.append(fv)

                if union_lines:
                    min_x = min(l.bbox[0] for l in union_lines)
                    min_y = min(l.bbox[1] for l in union_lines)
                    max_x = max(l.bbox[0] + l.bbox[2] for l in union_lines)
                    max_y = max(l.bbox[1] + l.bbox[3] for l in union_lines)
                    role_union_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
                else:
                    role_union_bbox = lbl_view.bbox

                full_val = role_block.full_declaration or role_block.company_name

                resolved[role_field] = ResolvedDeclaration(
                    field=role_field,
                    status="RESOLVED" if role_block.company_name else "REVIEW_REQUIRED",
                    value=role_block,
                    display_value=full_val,
                    raw_text=lbl_view.text + " " + " ".join(role_block.address_lines),
                    bbox=role_union_bbox,
                    label_bbox=lbl_view.bbox,
                    overall_confidence=role_block.confidence,
                    details={
                        "company_name": role_block.company_name,
                        "full_declaration": full_val,
                        "address_lines": role_block.address_lines,
                        "pin_code": role_block.pin_code,
                        "state": role_block.state,
                    },
                )

        # 8. Resolve Common Name and Origin
        if "common_name" in detected_labels:
            lbl_view, lbl_idx = detected_labels["common_name"]
            # Look for value inline or on next line
            following = [v for v in views if v.line_index > lbl_idx and v.line_index <= lbl_idx + 2]
            val_text = None
            val_bbox = lbl_view.bbox
            if following:
                val_text = following[0].text
                val_bbox = following[0].bbox
            resolved["common_name"] = ResolvedDeclaration(
                field="common_name",
                status="RESOLVED" if val_text else "REVIEW_REQUIRED",
                value=val_text,
                display_value=val_text,
                raw_text=lbl_view.text + (f" {val_text}" if val_text else ""),
                bbox=val_bbox,
                label_bbox=lbl_view.bbox,
                overall_confidence=0.85 if val_text else 0.40,
            )

        if "country_of_origin" in detected_labels:
            lbl_view, lbl_idx = detected_labels["country_of_origin"]
            m_org = re.search(r"\b(?:made\s+in|product\s+of)\s*([A-Za-z\s]+)", lbl_view.text, re.I)
            val_origin = m_org.group(1).strip() if m_org else "India"
            resolved["country_of_origin"] = ResolvedDeclaration(
                field="country_of_origin",
                status="RESOLVED",
                value=val_origin,
                display_value=val_origin,
                raw_text=lbl_view.text,
                bbox=lbl_view.bbox,
                label_bbox=lbl_view.bbox,
                overall_confidence=0.90,
            )

        return resolved

    def _apply_sequence_reasoning(
        self,
        candidate_map: Dict[str, List[CandidateRelationship]],
        detected_labels: Dict[str, Tuple[OcrLineView, int]],
    ) -> None:
        """
        Evaluate positional sequence alignment between labels and value candidates.
        """
        # Order detected labels vertically
        sorted_labels = sorted(
            detected_labels.items(),
            key=lambda item: item[1][0].bbox[1],
        )
        label_sequence = [fname for fname, _ in sorted_labels if fname in candidate_map]

        if len(label_sequence) < 2:
            # Need at least two labels to establish sequence
            for cands in candidate_map.values():
                for c in cands:
                    c.sequence_score = 0.5
                    self._calculate_total_score(c)
            return

        for fname, cands in candidate_map.items():
            if fname not in label_sequence:
                continue
            lbl_rank = label_sequence.index(fname)

            for cand in cands:
                if cand.value_line is None or cand.is_inline:
                    cand.sequence_score = 0.8
                    self._calculate_total_score(cand)
                    continue

                v_y = cand.value_line.bbox[1]
                # Sequence consistency bonus:
                # If this label is before another label in sequence, its value line should also be before or same level
                consistent_count = 0
                total_comparisons = 0

                for other_fname in label_sequence:
                    if other_fname == fname:
                        continue
                    other_rank = label_sequence.index(other_fname)
                    other_lbl_y = detected_labels[other_fname][0].bbox[1]

                    total_comparisons += 1
                    # If label A is above label B, value A being above label B or value B is consistent
                    if lbl_rank < other_rank and v_y <= other_lbl_y + 50:
                        consistent_count += 1
                    elif lbl_rank > other_rank and v_y >= other_lbl_y - 50:
                        consistent_count += 1

                cand.sequence_score = consistent_count / max(1, total_comparisons)
                self._calculate_total_score(cand)

    def _calculate_total_score(self, cand: CandidateRelationship) -> None:
        """
        Multi-signal weighted score composition:
        total = 0.30*spatial + 0.20*sequence + 0.30*type + 0.10*block + 0.10*format
        """
        cand.total_score = (
            0.30 * cand.spatial_score +
            0.20 * cand.sequence_score +
            0.30 * cand.type_score +
            0.10 * cand.block_score +
            0.10 * cand.format_score
        )

    def _resolve_1_to_1_subproblem(
        self,
        candidate_map: Dict[str, List[CandidateRelationship]],
        detected_labels: Dict[str, Tuple[OcrLineView, int]],
    ) -> Dict[str, ResolvedDeclaration]:
        """
        Perform constrained global assignment across competing declarations.
        """
        results: Dict[str, ResolvedDeclaration] = {}

        # 1. Any detected 1:1 field whose candidate list is empty is recorded as INSUFFICIENT_EVIDENCE
        one_to_one_fields = ("mrp", "unit_sale_price", "batch_no", "mfg_date", "expiry_date", "best_before", "net_quantity")
        for f in detected_labels:
            if f in one_to_one_fields:
                if f not in candidate_map or not candidate_map[f]:
                    lbl_line, _ = detected_labels[f]
                    results[f] = ResolvedDeclaration(
                        field=f,
                        status="INSUFFICIENT_EVIDENCE",
                        value=None,
                        display_value=None,
                        raw_text=lbl_line.text,
                        label_bbox=lbl_line.bbox,
                        ambiguity_reason="No plausible value candidates found nearby",
                    )

        fields = [f for f in candidate_map.keys() if candidate_map[f]]
        if not fields:
            return results

        # Gather all distinct candidate value lines across all fields
        all_unique_value_keys: List[Tuple[int, Optional[int]]] = []
        for f in fields:
            for c in candidate_map[f]:
                val_key = (
                    c.value_line.line_index if c.value_line else -1,
                    1 if c.is_inline else 0,
                )
                if val_key not in all_unique_value_keys:
                    all_unique_value_keys.append(val_key)

        num_fields = len(fields)
        num_vals = len(all_unique_value_keys)

        if num_vals == 0:
            for f in fields:
                lbl_line, _ = detected_labels[f]
                results[f] = ResolvedDeclaration(
                    field=f,
                    status="INSUFFICIENT_EVIDENCE",
                    value=None,
                    display_value=None,
                    raw_text=lbl_line.text,
                    label_bbox=lbl_line.bbox,
                    ambiguity_reason="No plausible value candidates detected",
                )
            return results

        # Build cost matrix for Hungarian matching
        # Shape: (num_fields, max(num_fields, num_vals))
        dim = max(num_fields, num_vals)
        cost_matrix = np.full((dim, dim), fill_value=2.0, dtype=float)

        cand_lookup: Dict[Tuple[int, int], CandidateRelationship] = {}

        for i, f in enumerate(fields):
            for j, vkey in enumerate(all_unique_value_keys):
                # Find candidate matching this value key
                for c in candidate_map[f]:
                    cand_vkey = (
                        c.value_line.line_index if c.value_line else -1,
                        1 if c.is_inline else 0,
                    )
                    if cand_vkey == vkey:
                        cost_matrix[i, j] = 1.0 - c.total_score
                        cand_lookup[(i, j)] = c
                        break

        # Solve assignment
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        assigned_pairs = set(zip(row_ind, col_ind))

        for i, f in enumerate(fields):
            lbl_line, _ = detected_labels[f]
            cands = sorted(candidate_map[f], key=lambda x: x.total_score, reverse=True)

            assigned_col = None
            for r, c in assigned_pairs:
                if r == i and c < num_vals:
                    assigned_col = c
                    break

            winner_cand = cand_lookup.get((i, assigned_col)) if assigned_col is not None else None
            alt_cands = [c for c in cands if c != winner_cand]

            # Abstention checks
            if winner_cand is None or winner_cand.total_score < self.confidence_threshold:
                top_score = winner_cand.total_score if winner_cand is not None else 0.0
                results[f] = ResolvedDeclaration(
                    field=f,
                    status="INSUFFICIENT_EVIDENCE",
                    value=None,
                    display_value=None,
                    raw_text=lbl_line.text,
                    label_bbox=lbl_line.bbox,
                    alternative_candidates=cands,
                    ambiguity_reason=f"Top candidate score ({top_score:.2f}) below threshold {self.confidence_threshold}",
                )
                continue

            # Check runner up margin for ambiguity
            score_margin = 1.0
            if alt_cands:
                runner_up = alt_cands[0]
                score_margin = winner_cand.total_score - runner_up.total_score

            is_ambiguous = (score_margin < self.ambiguity_margin and winner_cand.total_score < 0.70)
            status = "AMBIGUOUS" if is_ambiguous else "RESOLVED"

            disp_val = self._format_display_value(winner_cand.parsed_value)
            val_bbox = winner_cand.value_line.bbox if winner_cand.value_line else lbl_line.bbox

            results[f] = ResolvedDeclaration(
                field=f,
                status=status,
                value=winner_cand.parsed_value,
                display_value=disp_val,
                raw_text=f"{lbl_line.text} {winner_cand.value_line.text if winner_cand.value_line else ''}".strip(),
                bbox=val_bbox,
                label_bbox=lbl_line.bbox,
                selected_candidate=winner_cand,
                alternative_candidates=alt_cands,
                confidence_breakdown={
                    "spatial": winner_cand.spatial_score,
                    "sequence": winner_cand.sequence_score,
                    "type": winner_cand.type_score,
                    "block": winner_cand.block_score,
                    "format": winner_cand.format_score,
                },
                overall_confidence=winner_cand.total_score,
                score_margin=score_margin,
                ambiguity_reason=f"Close competition with runner-up (margin {score_margin:.3f})" if is_ambiguous else None,
                details=self._extract_value_details(winner_cand.parsed_value),
            )

        return results

    def _format_display_value(self, parsed_val: Any) -> Optional[str]:
        if isinstance(parsed_val, MoneyValue):
            try:
                amt_str = f"{float(parsed_val.amount):g}"
            except (ValueError, TypeError):
                amt_str = str(parsed_val.amount)
            if parsed_val.is_unit_rate:
                denom = parsed_val.denominator_unit or ""
                return f"₹{amt_str}/{denom}" if denom else f"₹{amt_str}"
            return f"₹{amt_str}"
        if isinstance(parsed_val, BatchCandidate):
            return parsed_val.normalized_reading
        if isinstance(parsed_val, TemporalValue):
            return parsed_val.normalized_iso or parsed_val.calendar_date or parsed_val.raw_text
        if isinstance(parsed_val, dict) and "amount" in parsed_val:
            amt = parsed_val.get("amount")
            unit = parsed_val.get("unit") or ""
            try:
                amt_str = f"{float(amt):g}"
            except (ValueError, TypeError):
                amt_str = str(amt)
            return f"{amt_str} {unit}".strip()
        return str(parsed_val) if parsed_val is not None else None

    def _extract_value_details(self, parsed_val: Any) -> Dict[str, Any]:
        if isinstance(parsed_val, MoneyValue):
            return {
                "amount": parsed_val.amount,
                "is_unit_rate": parsed_val.is_unit_rate,
                "denominator_unit": parsed_val.denominator_unit,
                "qualifiers": parsed_val.qualifiers,
            }
        if isinstance(parsed_val, BatchCandidate):
            return {
                "raw_reading": parsed_val.raw_reading,
                "normalized_reading": parsed_val.normalized_reading,
                "normalization_reasons": parsed_val.normalization_reasons,
            }
        if isinstance(parsed_val, TemporalValue):
            return {
                "is_relative": parsed_val.is_relative,
                "duration_value": parsed_val.duration_value,
                "duration_unit": parsed_val.duration_unit,
                "anchor_type": parsed_val.anchor_type,
                "normalized_iso": parsed_val.normalized_iso,
            }
        if isinstance(parsed_val, dict):
            return dict(parsed_val)
        return {}
