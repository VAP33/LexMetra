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

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import config


@dataclass
class OcrLine:
    text: str
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    confidence: float                 # 0..1

    # How the independent readings of THIS line agreed with each other, carried
    # as the plain string value of `schema.EvidenceAgreement` /
    # `ocr_engine.FusionState` (identical vocabularies).
    #
    # A string rather than the enum on purpose: `ocr_engine` imports
    # `ocr_extraction` for this class, so a reverse import would make the graph
    # cyclic, and the whole point of this field is to survive the hop from the
    # engine to the rule contract without either module having to know the
    # other. `schema.coerce_evidence_agreement()` interprets it at the boundary
    # and turns anything unrecognised into AGREEMENT_UNKNOWN rather than into a
    # false claim of agreement.
    #
    # None means "the reader did not report an agreement state" — the legacy
    # whole-image path, which performs no cross-reading and so is SINGLE_SOURCE.
    fusion_state: Optional[str] = None

    # The competing readings when `fusion_state` is CONFLICTING, so a reviewer
    # can be shown the disagreement rather than just told one exists.
    alternatives: Tuple[str, ...] = ()

    # Which detected region produced this reading. Diagnostic, and it lets the
    # agreement post-pass explain an attribution failure.
    region_id: Optional[str] = None


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
    Read an image and return text lines in ORIGINAL image coordinates.

    This is the single choke point for OCR in the whole application — `/scan`,
    `/inspect` and `extract_from_image()` all arrive here — so it is where the
    region-first pipeline is selected.

    Two paths, chosen by `config.ENABLE_REGION_FIRST_OCR`:

    REGION-FIRST (`ocr_engine.read_image`, default). Detects package surfaces and
    text regions, preprocesses and orients EACH REGION on its own terms, runs an
    OCR ensemble, then fuses the results deterministically. Only this path
    produces the evidence semantics the legal engine is designed around:
    CORROBORATED / SINGLE_SOURCE / CONFLICTING fusion states, per-region
    NOT_OBSERVED coverage, and a conflict record when two readings of the same
    pixels disagree. Readings withheld as symbology or typographic noise stay
    available on the reading object for audit; they are simply not offered for
    field extraction.

    LEGACY (`_run_ocr_whole_image`). The original whole-image variant loop. It
    still works and is retained as an escape hatch, but it has no orientation
    handling, no fusion state and no coverage accounting — which means an unread
    region is indistinguishable from an absent declaration. That is precisely the
    "NOT_OBSERVED != MISSING" confusion the system exists to avoid, so it is not
    the default.

    Both paths return the same `List[OcrLine]` contract, so `classify_fields()`
    and everything downstream are unaffected by the choice. A failure in the
    region-first path falls back to the legacy path rather than losing the
    inspection: fewer readings is a coverage problem, an exception is an outage.
    """
    lines: List[OcrLine] = []

    # 1. Whole-image multi-variant OCR (preserves sparse tables, 2-column prices, dates)
    try:
        lines.extend(_run_ocr_whole_image(image))
    except Exception:
        pass

    # 2. Region-first oriented OCR (handles rotated labels and dense sub-regions)
    if config.ENABLE_REGION_FIRST_OCR:
        try:
            import numpy as np
            import ocr_engine

            rgb = np.asarray(image.convert("RGB"))
            bgr = rgb[:, :, ::-1].copy()
            lines.extend(ocr_engine.read_image(bgr).lines)
        except Exception:
            pass

    return _dedupe_lines(lines)


def _run_ocr_whole_image(image: Image.Image) -> List[OcrLine]:
    """
    Legacy whole-image OCR: several conservative variants x page-segmentation
    modes, with bounding boxes mapped back to the original coordinate system.

    Kept as the fallback for `run_ocr()`. See that function for why it is no
    longer the default.
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
    # 1. GENUINE currency marker (e.g. ₹420, Rs. 120, INR 50, £420).
    #
    #    This group, and only this group, is treated by `_extract_money` as
    #    proof of price-hood strong enough to waive the measurement guard, so
    #    membership is restricted to symbols that cannot be anything else.
    #
    #    `=`, `_`, `-`, `~` and `F` were once listed here as "common OCR
    #    misreads of ₹". They are not safe in this position: a hyphen is also
    #    the ordinary separator in "NET WT-500 g", "BATCH-1234" and "13-05-26",
    #    so admitting it as a currency marker made those numbers currency-marked
    #    and thereby EXEMPT from the `_NON_PRICE_UNIT_RE` guard below —
    #    reintroducing precisely the "16.89 gMs" bug that guard exists to
    #    prevent, and feeding a mass into the Rule 6(11) unit-price check.
    #
    #    Nothing is lost by removing them. The real observed cases ("=420/-",
    #    "F420/-", "~420/-") all carry the Indian `/-` suffix and are matched by
    #    branch 2, which stays subject to the measurement guard.
    r"(?:₹|rs\.?|inr|£)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)(?:\s*/\s*[-–])?"
    # 2. Amount followed explicitly by Indian /- notation (e.g. 420/-, 50/-).
    #    Uses a digit lookbehind rather than \b so that a LETTER immediately
    #    before the amount still matches — "F420/-" is an OCR misread of a
    #    rupee marker and \b would refuse it, while the lookbehind still
    #    prevents splitting "1420/-" into "420/-".
    r"|(?<![0-9.])([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*/\s*[-–]"
    # 3. Bare amount with exactly 2 decimal digits (e.g. 120.50, 420.00)
    r"|(?:^|[^\d.])([0-9][0-9,]*\.[0-9]{2})(?!\d)"
    # 4. Standard 2-5 digit amount when preceded by price context words
    r"|(?:\b(?:price|mrp|amount|rate)\b[^\d]{1,6})([0-9]{2,5}(?:\.[0-9]{1,2})?)\b",
    re.I,
)

#: Units which, immediately following a number that carries NO currency marker,
#: prove the number is a measurement rather than a price. See `_extract_money`.
_NON_PRICE_UNIT_RE = re.compile(
    r"\s*(?:(?:"
    r"kgs?|gms?|grams?|gm|g|mg|"
    r"ml|millilit(?:re|er)s?|lit(?:re|er)s?|l|"
    r"mm|cm|centi(?:metre|meter)s?|met(?:re|er)s?|m|"
    r"kcal|cal|kj"
    r")\b|%)",
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
    # DD/MM/YYYY or DD/MM/YY (e.g. 13/05/26, 31/12/2027)
    r"\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*(?:\d{4}|\d{2})"
    # MM/YYYY (e.g. 05/2026, 12/2027)
    r"|\d{1,2}\s*[/.-]\s*\d{4}"
    # MM/YY where month is 01-12 and year is 2 digits (e.g. 12/10, 05/26, 09/24)
    r"|(?:0[1-9]|1[0-2]|[1-9])\s*[/.-]\s*\d{2}"
    # YYYY/MM or YYYY/MM/DD (e.g. 2026/05/13, 2026-05)
    r"|\d{4}\s*[/.-]\s*\d{1,2}(?:\s*[/.-]\s*\d{1,2})?"
    # Month name with 2- or 4-digit year (e.g. OCT 26, DEC 2027, 12 OCT 2026)
    r"|(?:\d{1,2}\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(?:[/.-]|\s+)?(?:\d{4}|\d{2})"
    # Relative shelf life: e.g. "12 MONTHS FROM PACKAGING", "6 MONTHS FROM MFD"
    r"|(?:\d{1,2})\s+(?:months?|days?|weeks?|years?)\s+(?:from|of)\s+(?:pkg|pkd|mfd|mfg|pack|manufacture|date)"
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

# ---------------------------------------------------------------------------
# The "17m" guard
# ---------------------------------------------------------------------------
#
# WHAT ACTUALLY HAPPENS. On the Bru coffee jar in the dataset, a small print code
# reading "17m" is printed on the label just above the top-right corner of the
# barcode. OCR reads it correctly — it is real ink, not barcode noise, and it must
# NOT be discarded as a reading. The defect was downstream: `_QTY_RE` matches
# "17m" as 17 metres, and the unlabelled-quantity fallback below then promoted it
# to `net_quantity`, producing a fabricated declaration of "17m" for a jar of
# coffee. A fabricated net quantity is the most dangerous extraction error in this
# system, because net quantity feeds the Rule 6 declaration check and the Second
# Schedule standard-pack-size test directly: it does not weaken a finding, it
# manufactures one.
#
# WHY LENGTH IS THE DISCRIMINATOR. Metres and centimetres ARE lawful net-quantity
# units — Rule 26 and the Second Schedule cover commodities sold by length, such
# as fabric, thread and cable — so they cannot simply be banned. But a BARE length
# token with no net-quantity wording is far more often a print code, a batch
# marking or a dimension than a declaration. Mass, volume and count units carry no
# such ambiguity: "500g" alone on a front panel is a normal declaration.
#
# THE RULE. A length-unit quantity may become `net_quantity` only when the line
# also carries explicit net-quantity wording. Otherwise it is not accepted.
#
# NOT_OBSERVED, NOT MISSING. Refusing the promotion does not delete the reading:
# "17m" stays in `ocr_engine.ImageReading.observations` with full provenance, and
# net_quantity is simply absent from the extraction — which downstream means
# NOT_OBSERVED, never MISSING, and can never by itself become a FAIL.

_LENGTH_UNITS = frozenset(
    {
        "m",
        "metre",
        "metres",
        "meter",
        "meters",
        "cm",
        "centimetre",
        "centimetres",
        "centimeter",
        "centimeters",
    }
)

#: Wording that makes a quantity a DECLARATION rather than an incidental number.
_NET_CONTEXT_RE = re.compile(
    r"\b(?:net|nett|qty|quantity|wt|weight|contents?|vol|volume|drained)\b",
    re.I,
)


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_money(text: str) -> Optional[float]:
    """
    Parse a rupee amount, refusing numbers that are provably measurements.

    THE "16.89 gMs" GUARD — a sibling of the "17m" guard documented above
    `_LENGTH_UNITS`, and found the same way: by dumping what this function
    actually returned on the `images dataset` photographs.

    On dataset image 3 the associated MRP value line was read as
    `'i Pr : 16.89 gMs (Incj Of al] taxes : 40/ f'`. The second branch of
    `_MONEY_RE` matches any bare number carrying exactly two decimals with NO
    currency marker whatsoever, so `16.89` — a mass in GRAMS, printed in the
    nutrition block — was returned as a price and stored as `mrp.numeric_value`
    by the caller below.

    WHY THAT IS A LEGAL-SAFETY BUG, NOT A COSMETIC ONE. `mrp.numeric_value`
    is not merely displayed. It is the numerator of the Rule 6(11) unit-sale-price
    consistency check, so a mass silently substituted for the retail price can
    make a CORRECTLY priced package contradict its own declared unit price. That
    is a fabricated FAIL against a compliant package, which is the worst outcome
    this system can produce.

    WHY THE BARE BRANCH CANNOT SIMPLY REQUIRE PRICE WORDING. This function is
    called on the value line that was already ASSOCIATED with an MRP label, so
    the words "MRP"/"Rs" usually sit on the LABEL line, not in `text`. Demanding
    price wording here would reject the perfectly ordinary value line `45.00`.

    THE RULE. Positive evidence AGAINST price-hood is used instead: a bare
    number immediately followed by a unit of mass, volume, length, energy or
    percentage is a measurement and is never a price. A number carrying an
    explicit currency marker (₹ / Rs / INR) keeps its meaning and is not
    second-guessed. Scanning continues past a rejected candidate, so a real
    price later in the same line is still found.

    NOT_OBSERVED, NOT MISSING. Refusing the number does not invent a value and
    does not delete the reading: the OCR line keeps full provenance, and the
    field simply carries no `numeric_value`, which downstream is NOT_OBSERVED
    and can never by itself become a FAIL.
    """
    for match in _MONEY_RE.finditer(text):
        raw = next((group for group in match.groups() if group), None)
        if raw is None:
            continue

        # Group 1 is the currency-marked branch; a marker is strong enough
        # evidence of price-hood that no further test is applied.
        currency_marked = match.group(1) is not None

        if not currency_marked and _NON_PRICE_UNIT_RE.match(text, match.end()):
            # e.g. "16.89 gMs" -> a mass, not ₹16.89.
            continue

        try:
            return float(raw.replace(",", ""))
        except ValueError:
            continue

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


def normalize_date(text: Optional[str]) -> Optional[str]:
    """
    Public entry point for date normalization.

    Exported so that the OCR -> rule-engine translation layer
    (`capture_session.build_raw_extraction`) can normalize a date supplied as
    free text by a structured caller, WITHOUT the system growing a second date
    grammar. There is one date parser; this is its front door.

    Returns None when the text cannot be parsed. None means "no date
    established", which downstream is unresolved/UNCERTAIN — never a FAIL.

    STRICTER THAN THE INTERNAL PARSER, DELIBERATELY. `_normalize_date` ends in
    an unconditional `return t`: text it cannot parse comes back unchanged. That
    is tolerable for its internal callers, which only reach it with a substring
    `_extract_date` has already matched as date-shaped. It is NOT tolerable
    here, because the rule engine reads "normalized value is not None" as "a
    date was established" — so a free-text value of "see bottom of pack" would
    arrive as a satisfied date declaration. Passing `strict=True` makes
    unparseable text return None instead.
    """
    return _normalize_date(text, strict=True)


def _normalize_date(text: Optional[str], *, strict: bool = False) -> Optional[str]:
    if not text:
        return None
    t = text.strip()
    # Check MM/YY (e.g. 12/10 or 05/26)
    m = re.match(r"^(\d{1,2})\s*[/.-]\s*(\d{2})$", t)
    if m:
        mo, yr = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            full_yr = 2000 + yr if yr < 50 else 1900 + yr
            return f"{full_yr:04d}-{mo:02d}"
    # Check DD/MM/YY (e.g. 13/05/26)
    m = re.match(r"^(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{2})$", t)
    if m:
        d, mo, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            full_yr = 2000 + yr if yr < 50 else 1900 + yr
            return f"{full_yr:04d}-{mo:02d}-{d:02d}"
    # Check DD/MM/YYYY
    m = re.match(r"^(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4})$", t)
    if m:
        d, mo, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{yr:04d}-{mo:02d}-{d:02d}"
    # Check MM/YYYY
    m = re.match(r"^(\d{1,2})\s*[/.-]\s*(\d{4})$", t)
    if m:
        mo, yr = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{yr:04d}-{mo:02d}"
    # Month name e.g. OCT 2026 or 12 OCT 2026
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
    }
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(?:[/.-]|\s+)?(\d{2,4})\b", t, re.I)
    if m:
        mo_str, yr_str = m.group(1).lower(), m.group(2)
        mo = month_map.get(mo_str, 1)
        yr = int(yr_str)
        if yr < 100:
            yr = 2000 + yr if yr < 50 else 1900 + yr
        return f"{yr:04d}-{mo:02d}"
    # Return cleaned raw text if relative (e.g. "12 months from packaging"),
    # which is a lawful way to express a best-before declaration.
    if any(u in t.lower() for u in ("month", "day", "week", "year")):
        return t.lower()
    # Nothing matched. Under `strict` the honest answer is "no date
    # established" — see `normalize_date`. The permissive passthrough is kept
    # for internal callers, which only arrive here with text that
    # `_extract_date` already matched as date-shaped.
    if strict:
        return None
    return t


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
        return bool(re.search(r"\b[A-Z0-9][A-Z0-9./_-]{3,}\b", text, re.I))

    if field == "net_quantity":
        return _extract_qty(text) is not None

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
        if pattern.search(text):
            return True
    return False


def _inline_label_value(field: str, text: str) -> Optional[str]:
    """Return the text after an explicit field label when it is on one line."""
    pattern = FIELD_PATTERNS.get(field)
    if pattern is None:
        return None
    match = pattern.search(text)
    if not match:
        return None
    remainder = text[match.end():]
    remainder = re.sub(r"^\s*[:\-–=]+\s*", "", remainder)
    remainder = _normalized_text(remainder)
    if not remainder or pattern.fullmatch(remainder):
        return None
    return remainder


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
        same_row = dy <= max(lh, oh) * 1.8
        right_side = ox >= lx + max(1, int(lw * 0.35))

        # Reject distant paragraphs.
        # Allow vertical gap to accommodate intervening sub-lines (e.g. "(INCL. OF ALL TAXES)")
        max_dy = max(110.0, lh * 5.5)
        if dy > max_dy:
            continue

        score = dy
        if same_row:
            score -= 40.0
        if right_side:
            score -= 25.0
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
    - Declaration label without a valid value line is explicitly marked as
      such (value=None, status=REVIEW_REQUIRED). It NEVER receives a false 100% verified.
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
            if field in label_hits:
                continue
            if pattern.search(text):
                label_hits[field] = (i, line)

    # Explicit-label fields.
    for field, (i, label_line) in label_hits.items():
        has_inline_value = _value_shape(field, label_line.text)
        best_candidate: Optional[OcrLine] = None

        # Company/role declarations are frequently printed as
        # "Manufacturer: ACME Pvt Ltd". The old logic treated the whole line as
        # a label and then borrowed the next line, which could silently turn
        # "Common Name: Fruit Juice" into the manufacturer. Extract the inline
        # remainder first and keep its original bbox as the strongest evidence.
        if field in _FIELDS_TAKE_FOLLOWING_LINES:
            inline_company = _inline_label_value(field, label_line.text)
            if inline_company:
                found[field] = {
                    "field": field,
                    "label": _normalized_text(label_line.text[: label_line.text.lower().find(inline_company.lower())]).strip(" :-–="),
                    "value": inline_company,
                    "confidence": label_line.confidence,
                    "bbox": label_line.bbox,
                    "label_bbox": label_line.bbox,
                    "source": "ocr_label_inline",
                    "status": "DETECTED",
                }
                used_line_idx.add(i)
                continue

        if field in _COLUMN_VALUE_FIELDS and not has_inline_value:
            candidates = _candidate_value_lines(
                label_line,
                ordered,
                field,
                i,
                used_line_idx,
            )
            if candidates:
                _, j, best_candidate = candidates[0]
                used_line_idx.add(j)

        val_line = label_line if has_inline_value else best_candidate

        if field in {"mrp", "unit_sale_price"}:
            money = _extract_money(val_line.text) if val_line else None
            if money is not None:
                unit = _extract_unit_price_unit(val_line.text) or _extract_unit_price_unit(label_line.text)
                entry = {
                    "field": field,
                    "label": _normalized_text(label_line.text),
                    "value": f"₹{money:g}",
                    "numeric_value": money,
                    "currency": "INR",
                    "raw_text": f"{label_line.text} {val_line.text}" if val_line != label_line else label_line.text,
                    "confidence": min(label_line.confidence, val_line.confidence) * (1.0 if has_inline_value else 0.88),
                    "bbox": val_line.bbox if val_line else label_line.bbox,
                    "label_bbox": label_line.bbox,
                    "source": "ocr_label_inline" if has_inline_value else "ocr_associated_value_line",
                    "status": "DETECTED",
                }
                if unit:
                    entry["numeric_unit"] = unit
            else:
                # Label alone, or malformed OCR without price value:
                # Do NOT treat "MRP&" or label text as an extracted monetary price!
                entry = {
                    "field": field,
                    "label": _normalized_text(label_line.text),
                    "value": None,
                    "numeric_value": None,
                    "raw_text": label_line.text,
                    "confidence": min(0.35, label_line.confidence * 0.3),
                    "bbox": label_line.bbox,
                    "label_bbox": label_line.bbox,
                    "source": "ocr_label_only",
                    "status": "REVIEW_REQUIRED",
                    "reason": f"Declaration label '{label_line.text}' was detected, but no valid monetary price could be established.",
                }

        elif field in {"mfg_date", "expiry_date"}:
            date_val = _extract_date(val_line.text) if val_line else None
            if date_val is not None:
                norm_date = _normalize_date(date_val)
                entry = {
                    "field": field,
                    "label": _normalized_text(label_line.text),
                    "value": date_val,
                    "normalized_value": norm_date,
                    "date_value": date_val,
                    "raw_text": f"{label_line.text} {val_line.text}" if val_line != label_line else label_line.text,
                    "confidence": min(label_line.confidence, val_line.confidence) * (1.0 if has_inline_value else 0.88),
                    "bbox": val_line.bbox if val_line else label_line.bbox,
                    "label_bbox": label_line.bbox,
                    "source": "ocr_label_inline" if has_inline_value else "ocr_associated_value_line",
                    "status": "DETECTED",
                }
            else:
                # Label alone (e.g. "USE BY") without a date:
                # NEVER assign label text as the value or give 100% verified status!
                entry = {
                    "field": field,
                    "label": _normalized_text(label_line.text),
                    "value": None,
                    "normalized_value": None,
                    "date_value": None,
                    "raw_text": label_line.text,
                    "confidence": min(0.35, label_line.confidence * 0.3),
                    "bbox": label_line.bbox,
                    "label_bbox": label_line.bbox,
                    "source": "ocr_label_only",
                    "status": "REVIEW_REQUIRED",
                    "reason": f"Declaration label '{label_line.text}' detected, but corresponding date value was not reliably detected.",
                }

        elif field == "batch_no":
            code = val_line.text if val_line else None
            entry = {
                "field": field,
                "label": _normalized_text(label_line.text),
                "value": _normalized_text(code) if code else None,
                "batch_code": _normalized_text(code) if code else None,
                "raw_text": f"{label_line.text} {code}" if code and code != label_line.text else label_line.text,
                "confidence": min(label_line.confidence, getattr(val_line, "confidence", label_line.confidence)),
                "bbox": getattr(val_line, "bbox", label_line.bbox),
                "label_bbox": label_line.bbox,
                "source": "ocr_associated_value_line" if best_candidate else "ocr_label_line",
                "status": "DETECTED" if code else "REVIEW_REQUIRED",
            }

        elif field == "net_quantity":
            qty_res = _extract_qty(val_line.text) if val_line else None
            if qty_res is not None:
                qty_val, qty_unit = qty_res
                entry = {
                    "field": field,
                    "label": _normalized_text(label_line.text),
                    "value": f"{qty_val:g} {qty_unit}",
                    "numeric_value": qty_val,
                    "numeric_unit": qty_unit,
                    "raw_text": f"{label_line.text} {val_line.text}" if val_line != label_line else label_line.text,
                    "confidence": min(label_line.confidence, val_line.confidence),
                    "bbox": val_line.bbox if val_line else label_line.bbox,
                    "label_bbox": label_line.bbox,
                    "source": "ocr_label_inline" if has_inline_value else "ocr_associated_value_line",
                    "status": "DETECTED",
                }
            else:
                entry = {
                    "field": field,
                    "label": _normalized_text(label_line.text),
                    "value": None,
                    "raw_text": label_line.text,
                    "confidence": min(0.35, label_line.confidence * 0.3),
                    "bbox": label_line.bbox,
                    "label_bbox": label_line.bbox,
                    "source": "ocr_label_only",
                    "status": "REVIEW_REQUIRED",
                    "reason": f"Declaration label '{label_line.text}' detected, but quantity amount was not detected.",
                }
        else:
            entry = {
                "field": field,
                "label": _normalized_text(label_line.text),
                "value": _normalized_text(val_line.text) if val_line else None,
                "confidence": label_line.confidence,
                "bbox": label_line.bbox,
                "source": "ocr_label_line",
            }

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
        standalone_candidates: List[
            Tuple[float, OcrLine, Tuple[float, str], bool]
        ] = []

        for line in ordered:
            qty = _extract_qty(line.text)
            if not qty:
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
            has_context = bool(_NET_CONTEXT_RE.search(text))
            if re.search(r"\bnet\b", text, re.I):
                score += 0.25

            # THE "17m" GUARD. See the module comment above _LENGTH_UNITS: a bare
            # length token with no net-quantity wording is a print code far more
            # often than a declaration, and promoting it fabricates a net quantity.
            # The reading itself is untouched and remains in the OCR provenance.
            if str(qty[1]).lower() in _LENGTH_UNITS and not has_context:
                continue

            standalone_candidates.append((score, line, qty, has_context))

        # "Never average. Never silently choose."
        #
        # THE NUTRITION-PANEL GUARD, and why sorting was not enough. This block
        # used to sort the candidates by score and take the winner. A nutrition
        # panel is full of bare masses, so on a back-of-pack photograph the
        # "winner" is decided by OCR confidence among numbers that have nothing
        # to do with the net quantity. Measured on `images dataset` image 3: the
        # fallback promoted '16.89 gms' — a nutrition row — to net_quantity at
        # confidence 0.56, above the 0.55 legal threshold, so it would have been
        # treated as the declared quantity.
        #
        # WHY THE KEYWORD FILTER ABOVE DOES NOT CATCH IT. That filter needs the
        # nutrition wording to survive OCR. On image 3 it did not: 'Protein'
        # came through as 'tein' and 'Carbohydrates' as 'Crates', so the lines
        # slipped past a word-boundary match. A guard that depends on reading
        # words correctly cannot protect against misread words.
        #
        # THE RULE, which does not depend on reading any word. A quantity that
        # carries explicit net-quantity wording is labelled evidence and is
        # preferred, exactly as before. But if EVERY candidate is bare and they
        # disagree with each other, the extractor has several mutually exclusive
        # readings and no basis to prefer one: that is ambiguity, not evidence,
        # and choosing the highest-scoring one manufactures a declaration. Two
        # bare readings of the SAME value are not a disagreement, so a pack that
        # prints '500 g' on two panels is unaffected.
        #
        # NOT_OBSERVED, NOT MISSING. Refusing to choose leaves net_quantity
        # absent from the extraction, which downstream is NOT_OBSERVED and can
        # never by itself become a FAIL. Every reading stays in the OCR
        # provenance.
        labelled = [c for c in standalone_candidates if c[3]]
        pool = labelled or standalone_candidates

        if not labelled and len(pool) > 1:
            distinct = {
                (round(float(qty[0]), 4), str(qty[1]).lower())
                for _, _, qty, _ in pool
            }
            if len(distinct) > 1:
                pool = []

        if pool:
            pool.sort(key=lambda x: x[0], reverse=True)
            score, line, qty, _ = pool[0]

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
        value = _inline_label_value("common_name", label_line.text)
        if value is None:
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

    attach_reading_agreement(found, ordered)

    return found


# The most conservative state wins when several readings back one field: a
# single disagreement is enough to unsettle the value, and an unattributable
# reading is worse than a known conflict because nothing is known about it.
_AGREEMENT_SEVERITY = {
    "CORROBORATED": 0,
    "SINGLE_SOURCE": 1,
    "CONFLICTING": 2,
    "AGREEMENT_UNKNOWN": 3,
}


def attach_reading_agreement(
    found: Dict[str, dict],
    lines: Sequence[OcrLine],
) -> Dict[str, dict]:
    """
    Record, per classified field, whether the readings behind it agreed.

    Done once here instead of at each of the thirteen places that build a
    classified-field dict. That is not only less code: a rule enforced at
    thirteen sites is a rule that will one day be enforced at twelve, and the
    twelfth omission would be invisible, because the field would simply look
    undisputed. The classification logic above is left untouched.

    The attribution is exact rather than approximate. Every one of those sites
    stores some line's `.bbox` verbatim — none stores a merged or union box — so
    the field's recorded region identifies the reading that supplied its value,
    and the agreement state is looked up, not inferred.

    A field whose region matches no line is marked AGREEMENT_UNKNOWN. That is
    the point of the sentinel: if a future extraction site starts storing a
    computed region, this fails loudly and safely (AGREEMENT_UNKNOWN cannot
    produce a definitive verdict) instead of quietly asserting that readings
    which were never located agreed with each other.
    """
    by_bbox: Dict[Tuple[int, int, int, int], List[OcrLine]] = {}
    for line in lines:
        try:
            key = tuple(int(v) for v in line.bbox)  # type: ignore[assignment]
        except (TypeError, ValueError):
            continue
        by_bbox.setdefault(key, []).append(line)  # type: ignore[arg-type]

    for field, data in found.items():
        if not isinstance(data, dict):
            continue

        bbox = data.get("bbox")
        try:
            key = tuple(int(v) for v in bbox)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            key = None

        matches = by_bbox.get(key, []) if key is not None else []

        if not matches:
            # Includes the no-bbox case. Nothing to attribute the value to.
            data["agreement"] = "AGREEMENT_UNKNOWN"
            data["agreement_note"] = (
                "The reading behind this value could not be matched to an OCR "
                "line, so whether independent readings agreed is unknown."
            )
            continue

        states = [
            (line.fusion_state or "SINGLE_SOURCE")
            for line in matches
        ]
        worst = max(states, key=lambda s: _AGREEMENT_SEVERITY.get(s, 3))
        data["agreement"] = worst

        if worst == "CONFLICTING":
            alternatives: List[str] = []
            for line in matches:
                for alt in line.alternatives or ():
                    text = str(alt).strip()
                    if text and text not in alternatives:
                        alternatives.append(text)
            if alternatives:
                data["alternative_values"] = alternatives

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
