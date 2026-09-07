"""
OCR and declaration-field extraction for packaged-commodity inspection.

Design goals:
- OCR is evidence extraction only. It never decides legal compliance.
- The public output shape remains compatible with the existing pipeline:
    {field: {value, confidence, bbox, numeric_value, numeric_unit, ...}}
- Tesseract is the default OCR backend because it is already used by the MVP.
  `run_ocr()` is intentionally isolated so PaddleOCR can replace it later.
- Multiple preprocessing variants and conservative parsing are preferred over
  aggressive guessing. "Not observed" must not become "missing" merely because
  OCR failed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


@dataclass
class OcrLine:
    text: str
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    confidence: float                 # 0..1


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _ocr_single(image: Image.Image, psm: int = 6) -> List[OcrLine]:
    """
    Run Tesseract once and preserve its line geometry.

    psm=6 is useful for package panels containing multiple text blocks.
    psm=11 is useful for sparse labels. Both are used by run_ocr().
    """
    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
        config=f"--psm {psm}",
    )

    lines: Dict[Tuple[int, int, int], List[int]] = {}
    for i, raw_text in enumerate(data["text"]):
        text = str(raw_text).strip()
        if not text:
            continue

        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        lines.setdefault(key, []).append(i)

    result: List[OcrLine] = []
    for idxs in lines.values():
        words = [str(data["text"][i]).strip() for i in idxs if str(data["text"][i]).strip()]
        if not words:
            continue

        confs: List[float] = []
        xs: List[int] = []
        ys: List[int] = []
        x2s: List[int] = []
        y2s: List[int] = []

        for i in idxs:
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1.0

            if conf >= 0:
                confs.append(conf)

            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            xs.append(x)
            ys.append(y)
            x2s.append(x + w)
            y2s.append(y + h)

        if not xs:
            continue

        text = " ".join(words).strip()
        bbox = (
            min(xs),
            min(ys),
            max(x2s) - min(xs),
            max(y2s) - min(ys),
        )
        confidence = (
            _clamp_confidence(sum(confs) / len(confs) / 100.0)
            if confs
            else 0.0
        )

        result.append(
            OcrLine(text=text, bbox=bbox, confidence=confidence)
        )

    return result


def _preprocess_variants(image: Image.Image) -> List[Image.Image]:
    """
    Produce conservative OCR variants.

    The original image is always included. Extra variants mainly help with
    low-contrast labels and small text. No geometric transformation is applied
    here because rotating/cropping the entire package blindly can damage
    already-correct OCR geometry.
    """
    rgb = image.convert("RGB")
    gray = ImageOps.grayscale(rgb)

    # Upscaling helps small declarations. Limit the size to avoid enormous
    # Tesseract inputs from modern phone cameras.
    scale = 2.0 if max(gray.size) < 2500 else 1.5
    enlarged = gray.resize(
        (max(1, int(gray.width * scale)), max(1, int(gray.height * scale))),
        Image.Resampling.LANCZOS,
    )

    contrast = ImageEnhance.Contrast(enlarged).enhance(1.6)
    sharp = contrast.filter(ImageFilter.SHARPEN)

    # Autocontrast is intentionally moderate. It can improve faint legal text
    # while avoiding a hard threshold that destroys coloured packaging text.
    auto = ImageOps.autocontrast(sharp, cutoff=1)

    return [rgb, enlarged, auto]


def _dedupe_lines(lines: Iterable[OcrLine]) -> List[OcrLine]:
    """
    Deduplicate repeated OCR results from preprocessing variants.

    Text is normalized and nearby boxes are treated as the same observation.
    When duplicates exist, retain the highest-confidence observation.
    """
    selected: List[OcrLine] = []

    def norm(text: str) -> str:
        return re.sub(r"\W+", "", text.lower(), flags=re.UNICODE)

    def iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ax2, ay2 = ax + aw, ay + ah
        bx2, by2 = bx + bw, by + bh
        ix1, iy1 = max(ax, bx), max(ay, by)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        union = aw * ah + bw * bh - inter
        return inter / union if union else 0.0

    for line in sorted(lines, key=lambda x: x.confidence, reverse=True):
        n = norm(line.text)
        if not n:
            continue

        duplicate = False
        for existing in selected:
            if n == norm(existing.text) and iou(line.bbox, existing.bbox) >= 0.35:
                duplicate = True
                break

        if not duplicate:
            selected.append(line)

    # Restore approximate reading order.
    selected.sort(key=lambda x: (x.bbox[1], x.bbox[0]))
    return selected


def run_ocr(image: Image.Image) -> List[OcrLine]:
    """
    Run OCR using multiple conservative image variants and page segmentation
    modes.

    Returned bounding boxes are expressed in the original image coordinate
    system where possible. For scaled preprocessing variants, coordinates are
    mapped back to the original image dimensions.
    """
    original = image.convert("RGB")
    orig_w, orig_h = original.size
    variants = _preprocess_variants(original)

    all_lines: List[OcrLine] = []

    for variant_index, variant in enumerate(variants):
        vw, vh = variant.size
        sx = orig_w / vw
        sy = orig_h / vh

        psms = (6, 11) if variant_index == 0 else (6, 11)

        for psm in psms:
            try:
                lines = _ocr_single(variant, psm=psm)
            except Exception:
                # OCR backend failure must not crash the inspection endpoint.
                continue

            for line in lines:
                x, y, w, h = line.bbox
                mapped = (
                    max(0, int(round(x * sx))),
                    max(0, int(round(y * sy))),
                    max(1, int(round(w * sx))),
                    max(1, int(round(h * sy))),
                )
                all_lines.append(
                    OcrLine(
                        text=line.text,
                        bbox=mapped,
                        confidence=line.confidence,
                    )
                )

    return _dedupe_lines(all_lines)


# ---------------------------------------------------------------------------
# Field patterns and parsers
# ---------------------------------------------------------------------------

FIELD_PATTERNS = {
    "mrp": re.compile(
        r"\b(?:m\.?\s*r\.?\s*p\.?|mrp)\b|maximum\s+retail\s+price|retail\s+sale\s+price",
        re.I,
    ),
    "net_quantity": re.compile(
        r"\bnet\s*(?:quantity|qty|weight|wt|volume|vol)\b|"
        r"\bnet\s*(?:wt|vol)\.?\b",
        re.I,
    ),
    "mfg_date": re.compile(
        r"\b(?:mfg|mfd)\.?\s*(?:date|dt)\b|"
        r"\bmanufactur(?:ed|e|ing)?\.?\s*(?:date|dt)\b|"
        r"\bdate\s+of\s+manufactur\w*\b",
        re.I,
    ),
    "expiry_date": re.compile(
        r"\b(?:expiry|exp\.?|use\s*by|use\s*before)\b|"
        r"\bbest\s*before\b|\bconsume\s*before\b",
        re.I,
    ),
    "batch_no": re.compile(
        r"\b(?:batch|lot)\s*(?:no\.?|number|#)?\b|"
        r"\b(?:batch|lot)\s*code\b",
        re.I,
    ),
    "manufacturer_name": re.compile(
        r"\bmanufactured\s+by\b|\bmanufactured\s*&\s*packed\s+by\b|"
        r"\bpacked\s+by\b|\bmanufacturer\b",
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
        r"\bmarketed\s+by\b|\bmarketed\s*&\s*distributed\s+by\b|"
        r"\bmarketer\b|\bmarketed\s+and\s+distributed\s+by\b",
        re.I,
    ),
    "country_of_origin": re.compile(
        r"\bcountry\s+of\s+origin\b|\bmade\s+in\b|\bproduct\s+of\b",
        re.I,
    ),
    "consumer_care": re.compile(
        r"\bconsumer\s+care\b|\bcustomer\s+(?:care|queries|service)\b|"
        r"\bconsumer\s+(?:queries|helpline)\b|\bhelpline\b|"
        r"\bcontact\s+(?:us|customer)\b",
        re.I,
    ),
    "unit_sale_price": re.compile(
        r"\bunit\s+sale\s+price\b|\bunit\s+price\b|\busp\b",
        re.I,
    ),
    "common_name": re.compile(
        r"\b(?:common|generic)\s+name\b",
        re.I,
    ),
}

# These labels commonly have their value in the same line or in a nearby
# column. We do not blindly attach arbitrary nearby text to other fields.
_COLUMN_VALUE_FIELDS = {
    "mrp",
    "unit_sale_price",
    "mfg_date",
    "expiry_date",
    "batch_no",
}

_FIELDS_TAKE_FOLLOWING_LINES = {
    "manufacturer_name",
    "packer_name",
    "importer_name",
    "marketer_name",
}

_MONEY_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
    r"|(?:^|[^\d.])([0-9][0-9,]*\.[0-9]{2})(?!\d)"
    # Common Indian whole-rupee shorthand, e.g. "420/-". Tesseract frequently
    # renders the "₹" glyph as "=", "z", or drops it entirely (verified on a
    # real product photo - see IMPLEMENTATION_STATUS.md), so a bare decimal
    # match alone was silently rejecting genuine MRP values like "₹420/-"
    # while accepting an unrelated "X.XX/unit" price on the same label.
    r"|(?:^|[^\d.])([0-9][0-9,]*)\s*/[-–—]",
    re.I,
)

# Avoid treating arbitrary 2-digit numbers as quantities. Support common OCR
# punctuation around units, including "N", "No." and multiplication counts.
_QTY_RE = re.compile(
    r"(?<![\w.])"
    r"([0-9]+(?:[.,][0-9]+)?)\s*"
    r"(kg|kgs?|g|gm|gms|grams?|"
    r"ml|millilit(?:re|er)s?|l|lit(?:re|er)s?|"
    r"cm|centi(?:metre|meter)s?|m|met(?:re|er)s?|"
    r"capsules?|tabs?|tablets?|pieces?|pcs?|pc|nos?\.?|"
    r"units?|number)"
    r"\b",
    re.I,
)

_DATE_RE = re.compile(
    r"\b(?:"
    r"\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*\d{2,4}"
    r"|\d{1,2}\s*[/.-]\s*\d{4}"
    r"|\d{4}\s*[/.-]\s*\d{1,2}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"(?:[a-z]*)\s*[/.-]\s*\d{2,4}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\s+\d{4}"
    r")\b",
    re.I,
)

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+91[\s-]?)?(?:0)?[6-9]\d{9}(?!\d)"
    r"|(?<!\d)\d{3,5}[\s-]\d{6,8}(?!\d)"
)

_ADDRESS_HINT_RE = re.compile(
    r"\b(?:road|rd|street|st|lane|ln|nagar|industrial|estate|"
    r"plot|phase|sector|city|district|state|india|pin|pincode)\b",
    re.I,
)

# A generic "label: value" separator helps with OCR such as "MRP: ₹5".
_LABEL_SEPARATOR_RE = re.compile(r"^\s*[:\-]\s*")


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_money(text: str) -> Optional[float]:
    matches = _MONEY_RE.search(text)
    if not matches:
        return None

    raw = next((group for group in matches.groups() if group), None)
    if raw is None:
        return None

    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _canonical_numeric_unit(unit: str) -> Optional[str]:
    u = unit.strip().lower().rstrip(".")
    aliases = {
        "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
        "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
        "ml": "ml", "millilitre": "ml", "millilitres": "ml",
        "milliliter": "ml", "milliliters": "ml",
        "l": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
        "cm": "cm", "centimetre": "cm", "centimetres": "cm",
        "centimeter": "cm", "centimeters": "cm",
        "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
        "capsule": "number", "capsules": "number",
        "tab": "number", "tabs": "number", "tablet": "number", "tablets": "number",
        "piece": "number", "pieces": "number", "pc": "number", "pcs": "number",
        "no": "number", "nos": "number", "unit": "number", "units": "number",
        "number": "number",
    }
    return aliases.get(u)


def _extract_qty(text: str) -> Optional[Tuple[float, str]]:
    match = _QTY_RE.search(text)
    if not match:
        return None

    raw_value = match.group(1).replace(",", ".")
    try:
        value = float(raw_value)
    except ValueError:
        return None

    if value <= 0:
        return None

    unit = _canonical_numeric_unit(match.group(2))
    if unit is None:
        return None

    return value, unit


def _extract_date(text: str) -> Optional[str]:
    match = _DATE_RE.search(text)
    return match.group(0) if match else None


def _extract_unit_price_unit(text: str) -> Optional[str]:
    """
    Extract a unit after 'per' from a declared unit-price line.

    This intentionally returns None when the unit is absent. The unit-price
    engine must not infer a unit from context.
    """
    m = re.search(
        r"\bper\s+(kg|g|ml|l|litre|liter|cm|m|number|no\.?|nos?\.?|"
        r"piece|pieces|unit|units)\b",
        text,
        re.I,
    )
    if not m:
        return None
    return _canonical_numeric_unit(m.group(1))


def _value_shape(field: str, text: str) -> bool:
    if field in {"mrp", "unit_sale_price"}:
        return _extract_money(text) is not None

    if field in {"mfg_date", "expiry_date"}:
        return _extract_date(text) is not None

    if field == "batch_no":
        # Batch codes may contain letters, digits, slashes and hyphens.
        # Require at least one alphanumeric token of reasonable length.
        return bool(re.search(r"\b[A-Z0-9][A-Z0-9./_-]{3,}\b", text, re.I))

    return False


def _line_center_y(line: OcrLine) -> float:
    return line.bbox[1] + line.bbox[3] / 2.0


def _vertical_distance(a: OcrLine, b: OcrLine) -> float:
    return abs(_line_center_y(a) - _line_center_y(b))


def _x_gap(a: OcrLine, b: OcrLine) -> int:
    ax, _, aw, _ = a.bbox
    bx, _, _, _ = b.bbox
    a2 = ax + aw
    b2 = bx + b.bbox[2]
    if a2 < bx:
        return bx - a2
    if b2 < ax:
        return ax - b2
    return 0


def _is_label_line(text: str) -> bool:
    for field, pattern in FIELD_PATTERNS.items():
        if field == "common_name":
            continue
        if pattern.search(text):
            return True
    return False


def _candidate_value_lines(
    label_line: OcrLine,
    lines: Sequence[OcrLine],
    field: str,
    label_index: int,
    used_line_idx: set[int],
) -> List[Tuple[float, int, OcrLine]]:
    """
    Find plausible value lines without crossing unrelated label sections.

    Score is deliberately conservative. Same-row/right-column candidates are
    preferred, then close vertical neighbours.
    """
    candidates: List[Tuple[float, int, OcrLine]] = []
    lx, ly, lw, lh = label_line.bbox
    label_center = _line_center_y(label_line)

    for j, other in enumerate(lines):
        if j == label_index or j in used_line_idx:
            continue
        if _is_label_line(other.text):
            continue
        if not _value_shape(field, other.text):
            continue

        ox, oy, ow, oh = other.bbox
        other_center = _line_center_y(other)
        dy = abs(other_center - label_center)
        x_gap = _x_gap(label_line, other)

        # A same-row/right-side value is strongest.
        same_row = dy <= max(lh, oh) * 1.5
        right_side = ox >= lx + max(1, int(lw * 0.35))

        # Reject distant paragraphs. Package labels often have several
        # unrelated dates/numbers nearby.
        max_dy = max(60.0, lh * 4.0)
        if dy > max_dy:
            continue

        score = dy
        if same_row:
            score -= 40.0
        if right_side:
            score -= 20.0
        if x_gap > 0:
            score += min(80.0, x_gap / 10.0)

        candidates.append((score, j, other))

    candidates.sort(key=lambda x: x[0])
    return candidates


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_fields(lines: List[OcrLine]) -> Dict[str, dict]:
    """
    Convert OCR lines into conservative structured declaration evidence.

    Important semantic distinction:
    - A field absent from this dictionary means "not observed by this
      extraction pass", not proof that the package legally lacks it.
    - The rule engine / evidence-completeness layer should decide whether more
      images or human review are required before declaring a legal FAIL.
    """
    found: Dict[str, dict] = {}
    used_line_idx: set[int] = set()

    # Sort a copy into reading order. Do not mutate the caller's list.
    ordered = sorted(lines, key=lambda x: (x.bbox[1], x.bbox[0]))

    # First locate explicit declaration labels.
    label_hits: Dict[str, Tuple[int, OcrLine]] = {}
    for i, line in enumerate(ordered):
        text = _normalized_text(line.text)
        if not text:
            continue

        for field, pattern in FIELD_PATTERNS.items():
            if field == "common_name":
                continue
            if field in label_hits:
                continue
            if pattern.search(text):
                label_hits[field] = (i, line)

    # Explicit-label fields.
    for field, (i, label_line) in label_hits.items():
        entry = {
            "value": _normalized_text(label_line.text),
            "confidence": label_line.confidence,
            "bbox": label_line.bbox,
            "source": "ocr_label_line",
        }

        if field in _COLUMN_VALUE_FIELDS and not _value_shape(field, label_line.text):
            candidates = _candidate_value_lines(
                label_line,
                ordered,
                field,
                i,
                used_line_idx,
            )

            if candidates:
                _, j, best = candidates[0]
                entry = {
                    "value": _normalized_text(best.text),
                    # The value is only as trustworthy as both OCR and the
                    # association between label and value.
                    "confidence": min(label_line.confidence, best.confidence) * 0.85,
                    "bbox": best.bbox,
                    "label_bbox": label_line.bbox,
                    "source": "ocr_associated_value_line",
                }
                used_line_idx.add(j)

        if field in {"mrp", "unit_sale_price"}:
            money = _extract_money(entry["value"])
            if money is not None:
                entry["numeric_value"] = money

            # Prefer a unit from the value line, then the label line.
            unit = _extract_unit_price_unit(entry["value"])
            if unit is None:
                unit = _extract_unit_price_unit(label_line.text)
            if unit is not None:
                entry["numeric_unit"] = unit

        elif field in {"mfg_date", "expiry_date"}:
            date_value = _extract_date(entry["value"])
            if date_value is not None:
                entry["date_value"] = date_value

        elif field == "batch_no":
            entry["batch_code"] = entry["value"]

        found[field] = entry
        used_line_idx.add(i)

    # Manufacturer / packer / importer / marketer roles generally introduce
    # the actual company/address on the next line(s).
    for field in _FIELDS_TAKE_FOLLOWING_LINES:
        if field not in label_hits:
            continue

        i, label_line = label_hits[field]
        value_lines: List[OcrLine] = []

        for j in range(i + 1, min(i + 4, len(ordered))):
            nxt = ordered[j]

            if j in used_line_idx:
                break
            if _is_label_line(nxt.text):
                break

            # Avoid swallowing an unrelated distant paragraph.
            if _vertical_distance(label_line, nxt) > max(120.0, label_line.bbox[3] * 8):
                break

            value_lines.append(nxt)
            used_line_idx.add(j)

        if value_lines:
            combined = ", ".join(_normalized_text(l.text) for l in value_lines)
            avg_conf = sum(l.confidence for l in value_lines) / len(value_lines)

            found[field] = {
                "value": combined,
                "confidence": min(label_line.confidence, avg_conf) * 0.9,
                "bbox": value_lines[0].bbox,
                "label_bbox": label_line.bbox,
                "source": "ocr_following_lines",
            }

    # Consumer care: explicit label is strong evidence. Contact details add
    # supporting evidence even if the label and phone/email are separate lines.
    contact_candidates: List[Tuple[int, OcrLine]] = []
    for i, line in enumerate(ordered):
        if _EMAIL_RE.search(line.text) or _PHONE_RE.search(line.text):
            contact_candidates.append((i, line))

    if "consumer_care" in label_hits:
        i, label_line = label_hits["consumer_care"]
        best: Optional[OcrLine] = None
        best_score = float("inf")

        for j, line in contact_candidates:
            if j == i:
                continue
            dy = _vertical_distance(label_line, line)
            if dy <= max(180.0, label_line.bbox[3] * 10):
                score = dy
                if j > i:
                    score -= 25
                if score < best_score:
                    best_score = score
                    best = line

        if best is not None:
            found["consumer_care"] = {
                "value": _normalized_text(best.text),
                "confidence": min(label_line.confidence, best.confidence) * 0.9,
                "bbox": best.bbox,
                "label_bbox": label_line.bbox,
                "source": "ocr_label_plus_contact",
            }
        else:
            found["consumer_care"] = {
                "value": _normalized_text(label_line.text),
                "confidence": label_line.confidence,
                "bbox": label_line.bbox,
                "source": "ocr_label_line",
            }
    elif contact_candidates:
        # Contact information alone is only supporting evidence. Require nearby
        # care/helpline language before classifying it as consumer care.
        for i, line in contact_candidates:
            nearby = " ".join(
                l.text for l in ordered[max(0, i - 3): min(len(ordered), i + 4)]
            )
            if re.search(
                r"\b(?:care|queries|helpline|customer|consumer|contact|toll)\b",
                nearby,
                re.I,
            ):
                found["consumer_care"] = {
                    "value": _normalized_text(line.text),
                    "confidence": line.confidence * 0.8,
                    "bbox": line.bbox,
                    "source": "ocr_contact_context",
                }
                break

    # Net quantity: only accept explicit net labels first. This avoids picking
    # nutrition serving sizes such as "16 g per serving".
    if "net_quantity" in label_hits:
        i, label_line = label_hits["net_quantity"]
        candidate_lines = [label_line]

        if not _extract_qty(label_line.text):
            for _, j, candidate in _candidate_value_lines(
                label_line,
                ordered,
                "net_quantity",
                i,
                used_line_idx,
            ):
                if _extract_qty(candidate.text):
                    candidate_lines.append(candidate)
                    break

        for candidate in candidate_lines:
            qty = _extract_qty(candidate.text)
            if qty:
                confidence = min(label_line.confidence, candidate.confidence)
                if candidate is not label_line:
                    confidence *= 0.85

                found["net_quantity"] = {
                    "value": _normalized_text(candidate.text),
                    "confidence": confidence,
                    "bbox": candidate.bbox,
                    "label_bbox": label_line.bbox,
                    "numeric_value": qty[0],
                    "numeric_unit": qty[1],
                    "source": "ocr_explicit_net_quantity",
                }
                break
    else:
        # Fallback only for an unmistakable standalone quantity line. Do not
        # infer net quantity from arbitrary nutrition/ingredient text.
        standalone_candidates: List[Tuple[float, OcrLine, Tuple[float, str]]] = []

        for line in ordered:
            qty = _extract_qty(line.text)
            if not qty:
                continue

            # Real-world false positive observed on a genuine product photo:
            # a "17m" fragment printed next to a barcode was matched as a
            # standalone quantity. "m"/"cm" are legitimate net-quantity units
            # only for length-declared goods (rare) and are far more often
            # OCR noise from barcodes/other print near the label. Without an
            # explicit "net quantity/weight/volume" label context, do not
            # accept them as a fallback guess.
            if qty[1] in {"m", "cm"}:
                continue

            text = line.text.lower()
            if re.search(
                r"\b(?:serving|per\s+serving|protein|carbohydrate|"
                r"energy|calories|ingredients?|nutrition|%rda)\b",
                text,
                re.I,
            ):
                continue

            # A line containing "net" is stronger even if OCR missed the word
            # "quantity".
            score = line.confidence
            if re.search(r"\bnet\b", text, re.I):
                score += 0.25

            standalone_candidates.append((score, line, qty))

        if standalone_candidates:
            standalone_candidates.sort(key=lambda x: x[0], reverse=True)
            score, line, qty = standalone_candidates[0]

            # Still label it as a fallback so downstream review can distinguish
            # it from explicit-label evidence.
            found["net_quantity"] = {
                "value": _normalized_text(line.text),
                "confidence": min(1.0, score * 0.8),
                "bbox": line.bbox,
                "numeric_value": qty[0],
                "numeric_unit": qty[1],
                "source": "ocr_quantity_fallback",
            }

    # Common/generic name:
    # Prefer an explicit "common/generic name" label. Otherwise, use a very
    # conservative candidate from prominent short lines, but mark it as
    # inferred. This prevents the old empty-regex implementation from silently
    # making common_name impossible to extract.
    if "common_name" in label_hits:
        i, label_line = label_hits["common_name"]
        if _LABEL_SEPARATOR_RE.search(label_line.text):
            value = _LABEL_SEPARATOR_RE.split(label_line.text, maxsplit=1)[-1].strip()
        else:
            value = label_line.text

        if value and not FIELD_PATTERNS["common_name"].fullmatch(value):
            found["common_name"] = {
                "value": _normalized_text(value),
                "confidence": label_line.confidence,
                "bbox": label_line.bbox,
                "source": "ocr_explicit_common_name",
            }
        else:
            for j in range(i + 1, min(i + 3, len(ordered))):
                candidate = ordered[j]
                if not _is_label_line(candidate.text):
                    found["common_name"] = {
                        "value": _normalized_text(candidate.text),
                        "confidence": min(label_line.confidence, candidate.confidence) * 0.85,
                        "bbox": candidate.bbox,
                        "label_bbox": label_line.bbox,
                        "source": "ocr_common_name_following_line",
                    }
                    break

    # Country of origin is useful for imported products. Preserve the actual
    # OCR text instead of normalizing it to "India" or any other guessed value.
    if "country_of_origin" in label_hits:
        i, label_line = label_hits["country_of_origin"]
        value = _normalized_text(label_line.text)

        if re.search(r"\b(?:made\s+in|product\s+of)\b", value, re.I):
            found["country_of_origin"] = {
                "value": value,
                "confidence": label_line.confidence,
                "bbox": label_line.bbox,
                "source": "ocr_origin_line",
            }
        else:
            for j in range(i + 1, min(i + 3, len(ordered))):
                candidate = ordered[j]
                if _is_label_line(candidate.text):
                    break
                found["country_of_origin"] = {
                    "value": _normalized_text(candidate.text),
                    "confidence": min(label_line.confidence, candidate.confidence) * 0.85,
                    "bbox": candidate.bbox,
                    "label_bbox": label_line.bbox,
                    "source": "ocr_origin_following_line",
                }
                break

    # Preserve all high-confidence date-like lines as auxiliary evidence. This
    # is not promoted to a legal field unless an explicit label exists.
    auxiliary_dates = []
    for line in ordered:
        date_value = _extract_date(line.text)
        if date_value:
            auxiliary_dates.append({
                "value": date_value,
                "text": _normalized_text(line.text),
                "confidence": line.confidence,
                "bbox": line.bbox,
            })

    if auxiliary_dates:
        # Avoid changing the established field-only contract too much. Expose
        # them under a private-looking auxiliary key that callers may ignore.
        found["_auxiliary_dates"] = auxiliary_dates

    return found


def extract_from_image(image_path: str) -> Dict[str, dict]:
    """Convenience entrypoint: image path -> OCR + classified field evidence."""
    with Image.open(image_path) as img:
        return classify_fields(run_ocr(img))


if __name__ == "__main__":
    import json
    import sys

    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/mnt/user-data/uploads/WhatsApp_Image_2026-09-04_at_1_03_48_AM.jpeg"
    )

    fields = extract_from_image(path)
    print(json.dumps(fields, indent=2, ensure_ascii=False))
