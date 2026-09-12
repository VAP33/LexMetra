"""
Barcode / QR decoding and GTIN interpretation.

`region_detection.py` has always said that "decoding belongs in `barcode.py`",
but no such module was ever written: the pipeline could LOCALISE a symbol and
never read one. Consequently `ProductIdentity.barcode` could only ever be filled
by hand, which is precisely the manual-entry problem this work exists to remove.

TWO READ PATHS, DELIBERATELY NOT EQUAL
--------------------------------------
Measured on the 29 real phone photographs in `images dataset/`, OpenCV's
`cv2.barcode.BarcodeDetector` decodes the bars on only a small minority of
frames. It localises far more than it decodes, and it fails specifically on
symbols printed around a CYLINDRICAL pack (a coffee jar, a bottle), where the
bar pitch is compressed towards the edges by perspective. The Bru jar is exactly
this case: the symbol is fully in frame, sharp and unoccluded, and the bar
decoder still returns nothing at any scale.

So there is a second path: read the human-readable digits printed beneath the
bars with OCR, then verify them against the symbology's own CHECK DIGIT. This
recovers identities the bar decoder cannot reach. It is not equivalent evidence
and this module never pretends it is:

  * `CV_BARS_DECODED` reads the machine-readable channel. A successful decode has
    passed the start/stop guard patterns, per-module parity and the check digit,
    so a wrong-but-accepted payload is very unlikely.

  * `OCR_HRI_CHECK_DIGIT_VALIDATED` reads a picture of text and then applies one
    modulo-10 test. That test rejects roughly nine of every ten random corruptions
    — during development it correctly rejected every OCR misread produced at the
    wrong upscale factor — but it is NOT proof. GS1's check digit cannot detect a
    transposition of adjacent digits differing by 5 (…27… read as …72…), and a
    dropped-plus-inserted digit can coincidentally re-validate.

The second path therefore carries a lower confidence and sets
`needs_confirmation`, so an inspector confirms the identity before it is treated
as established. The distinction is preserved all the way into the audit record
rather than collapsed into a single "barcode" string, because "the scanner read
this" and "a person's phone camera photographed digits that happened to satisfy
a checksum" are different claims about the world.

WHAT A DECODED GTIN DOES AND DOES NOT ESTABLISH
----------------------------------------------
A GTIN identifies the product. It is an INPUT to identity and catalogue lookup,
never a compliance verdict, and this module returns evidence only.

One trap is called out explicitly because it is legally consequential and very
commonly got wrong: the GS1 prefix (890 for India) identifies the GS1 MEMBER
ORGANISATION that issued the company prefix. It does NOT identify the country of
manufacture, packing or origin. A company registered with GS1 India can lawfully
import goods made anywhere, and an importer's own barcode says nothing about
where the goods were made. Rule 6 requires a declaration of the country of
origin for imported goods; satisfying that requirement from a barcode prefix
would be a fabricated finding. `Gs1Prefix.is_country_of_origin_evidence` is
therefore hard-coded False, and the advisory note travels with the value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

BBoxT = Tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class SymbologyKind(str, Enum):
    """The symbology a payload conforms to, after validation."""

    EAN_13 = "EAN_13"
    EAN_8 = "EAN_8"
    UPC_A = "UPC_A"
    ITF_14 = "ITF_14"
    QR = "QR"
    #: A 1D symbol was read but its payload does not satisfy any GTIN check we
    #: implement. Retained as evidence; never used as a product identity.
    UNVALIDATED_1D = "UNVALIDATED_1D"


class ReadMethod(str, Enum):
    """
    How the payload was obtained. This is provenance, not a detail.

    See the module docstring: these two are not interchangeable and the
    difference must survive into the audit record.
    """

    CV_BARS_DECODED = "CV_BARS_DECODED"
    OCR_HRI_CHECK_DIGIT_VALIDATED = "OCR_HRI_CHECK_DIGIT_VALIDATED"
    QR_DECODED = "QR_DECODED"


class SymbolStatus(str, Enum):
    """
    Outcome for one image.

    `NO_SYMBOL_LOCALISED` is the reason this enum exists. It means "this
    photograph did not show us a symbol", NOT "this package bears no barcode".
    Nothing downstream may turn it into a finding against the package: a barcode
    is not a Legal Metrology declaration in the first place, and a pack
    photographed from the front simply does not show the panel it sits on.
    """

    DECODED = "DECODED"
    #: A symbol was found but could not be read. Genuinely useful: it tells the
    #: inspector to re-photograph that panel rather than implying anything about
    #: the pack.
    LOCALISED_NOT_DECODED = "LOCALISED_NOT_DECODED"
    NO_SYMBOL_LOCALISED = "NO_SYMBOL_LOCALISED"
    #: Two or more mutually exclusive valid payloads were read. Per the project's
    #: standing invariant, conflicting reads stay conflicting; we do not pick one.
    CONFLICTING = "CONFLICTING"


#: Confidence for a payload decoded from the bars themselves. High, but not 1.0:
#: the module is not entitled to absolute certainty about anything it read from a
#: photograph.
CONFIDENCE_BARS_DECODED = 0.97

#: Confidence for digits read as text and then checksum-validated. Deliberately
#: below any threshold that would let it pass as established fact unreviewed.
CONFIDENCE_HRI_VALIDATED = 0.75


# ---------------------------------------------------------------------------
# GTIN validation
# ---------------------------------------------------------------------------


def gtin_check_digit(digits: str) -> Optional[int]:
    """
    GS1 modulo-10 check digit for the payload WITHOUT its check digit.

    Weights alternate 3 and 1 from the RIGHTMOST character of the partial
    payload. Anchoring on the right rather than the left is what makes the same
    routine correct for GTIN-8, -12, -13 and -14 alike; anchoring left silently
    inverts the weights on odd-length payloads.
    """
    if not digits.isdigit():
        return None
    total = 0
    for i, ch in enumerate(reversed(digits)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10


def validate_gtin(payload: str) -> Tuple[bool, Optional[SymbologyKind]]:
    """
    Validate a numeric payload as a GTIN and report which symbology it fits.

    Returns (False, None) for anything that is not a well-formed, check-digit
    correct GTIN of a length we recognise. Callers must not fall back to
    "probably fine" on a False: an unvalidated payload is not an identity.
    """
    if not payload or not payload.isdigit():
        return False, None
    kinds = {8: SymbologyKind.EAN_8, 12: SymbologyKind.UPC_A,
             13: SymbologyKind.EAN_13, 14: SymbologyKind.ITF_14}
    kind = kinds.get(len(payload))
    if kind is None:
        return False, None
    expected = gtin_check_digit(payload[:-1])
    if expected is None or expected != int(payload[-1]):
        return False, None
    return True, kind


def to_gtin13(payload: str) -> Optional[str]:
    """
    Normalise a validated GTIN to 13 digits for catalogue lookup.

    A UPC-A is zero-padded, which is the standard GTIN-13 rendering of a 12-digit
    code and does not change its check digit. GTIN-14 is a TRADE UNIT code
    (a case or outer carton), so its leading indicator digit is dropped only when
    it is 0 or 1; anything else identifies a multi-pack whose contents are a
    different commodity from the retail unit, and quietly treating a carton code
    as the retail item would attach the wrong net quantity to the inspection.
    """
    ok, kind = validate_gtin(payload)
    if not ok:
        return None
    if kind is SymbologyKind.EAN_13:
        return payload
    if kind is SymbologyKind.UPC_A:
        return "0" + payload
    if kind is SymbologyKind.ITF_14 and payload[0] in ("0", "1"):
        inner = payload[1:13]
        check = gtin_check_digit(inner)
        return inner + str(check) if check is not None else None
    return None


# ---------------------------------------------------------------------------
# GS1 prefix — advisory only
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Gs1Prefix:
    """
    What a GS1 prefix does and does not tell us.

    `is_country_of_origin_evidence` is a constant False and is expressed as a
    field so that any code reaching for this value has to see it. See the module
    docstring: using a prefix to satisfy the Rule 6 country-of-origin
    declaration for imported goods would manufacture a finding.
    """

    prefix: str
    member_organisation: str
    #: True for ranges that are not consumer product GTINs at all.
    special_range: bool = False
    note: str = ""

    @property
    def is_country_of_origin_evidence(self) -> bool:
        return False

    def to_dict(self) -> Dict[str, object]:
        return {
            "prefix": self.prefix,
            "gs1_member_organisation": self.member_organisation,
            "special_range": self.special_range,
            "note": self.note,
            "is_country_of_origin_evidence": False,
            "caveat": (
                "A GS1 prefix identifies the GS1 member organisation that issued "
                "the company prefix, not the country of manufacture, packing or "
                "origin. It must not be used to satisfy a country-of-origin "
                "declaration."
            ),
        }


#: (low, high, label) over the first three digits. Ranges, not an exhaustive
#: per-country table: only the entries a Legal Metrology inspection in India
#: plausibly meets, plus every SPECIAL range, because those change the meaning of
#: the payload rather than merely its geography.
_GS1_RANGES: Tuple[Tuple[int, int, str, bool, str], ...] = (
    (0, 19, "GS1 US", False, ""),
    (20, 29, "Restricted distribution", True,
     "Reserved for in-store or internal use. Not a globally unique product id; "
     "a retailer's own shelf label can carry one."),
    (30, 39, "GS1 US", False, ""),
    (40, 49, "Restricted distribution", True,
     "Reserved for company-internal use."),
    (50, 59, "GS1 UK (coupons)", True, "Coupon range."),
    (60, 139, "GS1 US", False, ""),
    (200, 299, "Restricted distribution", True,
     "Reserved for in-store use, commonly variable-measure items priced at the "
     "counter. Carries no manufacturer identity."),
    (300, 379, "GS1 France", False, ""),
    (380, 380, "GS1 Bulgaria", False, ""),
    (400, 440, "GS1 Germany", False, ""),
    (450, 459, "GS1 Japan", False, ""),
    (460, 469, "GS1 Russia", False, ""),
    (471, 471, "GS1 Taiwan", False, ""),
    (479, 479, "GS1 Sri Lanka", False, ""),
    (480, 480, "GS1 Philippines", False, ""),
    (489, 489, "GS1 Hong Kong", False, ""),
    (500, 509, "GS1 UK", False, ""),
    (520, 521, "GS1 Greece", False, ""),
    (539, 539, "GS1 Ireland", False, ""),
    (540, 549, "GS1 Belgium & Luxembourg", False, ""),
    (560, 560, "GS1 Portugal", False, ""),
    (570, 579, "GS1 Denmark", False, ""),
    (590, 590, "GS1 Poland", False, ""),
    (600, 601, "GS1 South Africa", False, ""),
    (628, 628, "GS1 Saudi Arabia", False, ""),
    (629, 629, "GS1 Emirates", False, ""),
    (640, 649, "GS1 Finland", False, ""),
    (690, 699, "GS1 China", False, ""),
    (700, 709, "GS1 Norway", False, ""),
    (729, 729, "GS1 Israel", False, ""),
    (730, 739, "GS1 Sweden", False, ""),
    (750, 750, "GS1 Mexico", False, ""),
    (754, 755, "GS1 Canada", False, ""),
    (760, 769, "GS1 Switzerland", False, ""),
    (789, 790, "GS1 Brazil", False, ""),
    (800, 839, "GS1 Italy", False, ""),
    (840, 849, "GS1 Spain", False, ""),
    (858, 858, "GS1 Slovakia", False, ""),
    (859, 859, "GS1 Czech Republic", False, ""),
    (868, 869, "GS1 Turkey", False, ""),
    (870, 879, "GS1 Netherlands", False, ""),
    (880, 880, "GS1 South Korea", False, ""),
    (885, 885, "GS1 Thailand", False, ""),
    (888, 888, "GS1 Singapore", False, ""),
    (890, 890, "GS1 India", False, ""),
    (893, 893, "GS1 Vietnam", False, ""),
    (896, 896, "GS1 Pakistan", False, ""),
    (899, 899, "GS1 Indonesia", False, ""),
    (900, 919, "GS1 Austria", False, ""),
    (930, 939, "GS1 Australia", False, ""),
    (940, 949, "GS1 New Zealand", False, ""),
    (955, 955, "GS1 Malaysia", False, ""),
    (960, 969, "GS1 Global Office (GTIN-8)", False, ""),
    (977, 977, "ISSN (serial publication)", True,
     "Identifies a periodical, not a packaged commodity."),
    (978, 979, "ISBN (book)", True,
     "Identifies a book, not a packaged commodity."),
    (980, 980, "Refund receipt", True, "Not a product identifier."),
    (981, 984, "GS1 coupon", True, "Coupon, not a product identifier."),
    (990, 999, "GS1 coupon", True, "Coupon, not a product identifier."),
)


def gs1_prefix(gtin13: str) -> Optional[Gs1Prefix]:
    """Look up the GS1 member organisation for a 13-digit GTIN."""
    if not gtin13 or not gtin13.isdigit() or len(gtin13) != 13:
        return None
    head = int(gtin13[:3])
    for low, high, label, special, note in _GS1_RANGES:
        if low <= head <= high:
            return Gs1Prefix(gtin13[:3], label, special, note)
    return Gs1Prefix(gtin13[:3], "Unassigned or unknown GS1 prefix", False,
                     "The prefix does not fall in a range known to this build.")


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class DecodedSymbol:
    """One successfully read symbol, with everything an audit needs."""

    payload: str
    kind: SymbologyKind
    method: ReadMethod
    confidence: float
    image_id: str
    bbox: Optional[BBoxT] = None
    check_digit_valid: bool = False
    gtin13: Optional[str] = None
    prefix: Optional[Gs1Prefix] = None
    #: True when a human must confirm before this is treated as established.
    #: Always True for the OCR path; see the module docstring.
    needs_confirmation: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "payload": self.payload,
            "symbology": self.kind.value,
            "read_method": self.method.value,
            "confidence": round(float(self.confidence), 4),
            "image_id": self.image_id,
            "bbox": [int(v) for v in self.bbox] if self.bbox else None,
            "check_digit_valid": self.check_digit_valid,
            "gtin13": self.gtin13,
            "gs1_prefix": self.prefix.to_dict() if self.prefix else None,
            "needs_confirmation": self.needs_confirmation,
            "notes": list(self.notes),
        }


@dataclass
class SymbolReadResult:
    """
    Everything one image yielded, including the honest negatives.

    `localised_not_decoded` is carried separately from `symbols` so a caller can
    tell an inspector "there is a barcode in frame that we could not read, move
    closer" — actionable — instead of silently reporting nothing found.
    """

    image_id: str
    status: SymbolStatus
    symbols: List[DecodedSymbol] = field(default_factory=list)
    localised_not_decoded: List[BBoxT] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def coverage_note(self) -> str:
        return (
            "Symbol reading reports what was readable in the supplied images. "
            "The absence of a barcode is not a Legal Metrology non-compliance "
            "and must never be recorded as one."
        )

    @property
    def best(self) -> Optional[DecodedSymbol]:
        """
        Highest-trust single symbol, or None when the reads conflict.

        Returning None on CONFLICTING is the point: a caller that wants "the
        barcode" must handle the case where the images disagree rather than
        receive an arbitrary winner.
        """
        if self.status is SymbolStatus.CONFLICTING:
            return None
        product = [s for s in self.symbols if s.gtin13]
        if not product:
            return self.symbols[0] if self.symbols else None
        return max(product, key=lambda s: s.confidence)

    def to_dict(self) -> Dict[str, object]:
        return {
            "image_id": self.image_id,
            "status": self.status.value,
            "symbols": [s.to_dict() for s in self.symbols],
            "localised_not_decoded": [[int(v) for v in b]
                                      for b in self.localised_not_decoded],
            "notes": list(self.notes),
            "coverage_note": self.coverage_note,
        }


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def _detectors():
    """
    Build the OpenCV detectors, tolerating builds that lack the barcode module.

    `cv2.barcode` is absent from some minimal wheels. Returning (None, None)
    degrades to the OCR path rather than raising, but the caller records a note:
    a silently barcode-less pipeline that looks like "no symbols on any package"
    is exactly the class of failure this codebase keeps rooting out.
    """
    import cv2

    bar = None
    qr = None
    try:
        bar = cv2.barcode.BarcodeDetector()
    except Exception:
        bar = None
    try:
        qr = cv2.QRCodeDetector()
    except Exception:
        qr = None
    return bar, qr


def _cv_decode(detector, image: np.ndarray) -> List[Tuple[str, str]]:
    """Return [(payload, opencv_type_label)] from the bar decoder."""
    if detector is None or image is None or image.size == 0:
        return []
    if image.shape[0] < 8 or image.shape[1] < 8:
        return []
    try:
        ok, infos, types, _pts = detector.detectAndDecodeWithType(image)
    except Exception:
        return []
    if not ok or not infos:
        return []
    out: List[Tuple[str, str]] = []
    for payload, kind in zip(infos, list(types) + [""] * len(infos)):
        if payload:
            out.append((str(payload), str(kind)))
    return out


def _upscaled(gray: np.ndarray, factors: Sequence[int] = (2, 3, 4)):
    """Yield progressively upscaled copies, bounded so we never blow up memory."""
    import cv2

    h, w = gray.shape[:2]
    for k in factors:
        if h * w * k * k > 12_000_000:
            continue
        yield k, cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)


def _hri_candidates(text: str) -> List[str]:
    """
    Digit strings worth checksum-testing, from one OCR line.

    EAN-13's human-readable form is printed in three groups ("8 909106 043251"),
    and the guard bars between them are frequently read as spaces or as stray
    glyphs. So both the individual runs AND their in-order concatenation are
    candidates. Every candidate still has to pass the check digit, which is what
    keeps this from being a licence to invent numbers out of neighbouring text.
    """
    runs = re.findall(r"\d+", text)
    if not runs:
        return []
    candidates: List[str] = ["".join(runs)]
    candidates.extend(runs)
    # Adjacent pairs catch the case where one guard bar was read as a digit and
    # split the payload in two while a third run belongs to unrelated text.
    for i in range(len(runs) - 1):
        candidates.append(runs[i] + runs[i + 1])
    seen: set = set()
    ordered: List[str] = []
    for c in candidates:
        if c not in seen and 7 <= len(c) <= 14:
            seen.add(c)
            ordered.append(c)
    return ordered


def _read_hri(gray: np.ndarray, bbox: BBoxT, image_shape) -> List[str]:
    """
    OCR the human-readable digits printed beneath a localised 1D symbol.

    The band is derived generously from the symbol's own box because the
    localiser routinely returns a FRAGMENT of the symbol: on the Bru jar it
    proposed 165px of a symbol roughly 450px wide. A band scaled tightly to that
    fragment would clip the payload, and a clipped payload fails the check digit
    and is discarded — the safe direction, but it reads nothing. Hence the
    horizontal expansion, with the checksum left to reject whatever extra text
    the wider crop drags in.
    """
    import cv2

    try:
        import pytesseract
    except Exception:
        return []

    x, y, w, h = (int(v) for v in bbox)
    ih, iw = image_shape[:2]
    x0 = max(0, int(x - 1.5 * w))
    x1 = min(iw, int(x + 2.5 * w))
    # The digits sit just below the bars; allow for the localiser cutting the
    # bars short vertically too.
    y0 = max(0, int(y + 0.70 * h))
    y1 = min(ih, int(y + 1.55 * h))
    if x1 - x0 < 20 or y1 - y0 < 8:
        return []

    strip = gray[y0:y1, x0:x1]
    found: List[str] = []
    config = "-c tessedit_char_whitelist=0123456789"
    for _k, up in _upscaled(strip, (4, 3, 5)):
        for prepared in (
            up,
            cv2.threshold(up, 0, 255,
                          cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        ):
            for psm in (7, 11):
                try:
                    text = pytesseract.image_to_string(
                        prepared, config=f"--psm {psm} {config}")
                except Exception:
                    continue
                for cand in _hri_candidates(text):
                    ok, _kind = validate_gtin(cand)
                    if ok and cand not in found:
                        found.append(cand)
        if found:
            # Stop at the first scale that produced a checksum-valid read. Extra
            # scales mostly produce corrupted variants of the same payload, and
            # feeding those in would trip the CONFLICTING guard against itself.
            break
    return found


def _build_symbol(payload: str, method: ReadMethod, image_id: str,
                  bbox: Optional[BBoxT], cv_type: str = "") -> DecodedSymbol:
    """Wrap a payload with its validation, normalisation and prefix advisory."""
    ok, kind = validate_gtin(payload)
    if not ok:
        # A payload the bar decoder produced but that we cannot validate is kept
        # as evidence and explicitly denied identity status.
        return DecodedSymbol(
            payload=payload,
            kind=SymbologyKind.QR if method is ReadMethod.QR_DECODED
            else SymbologyKind.UNVALIDATED_1D,
            method=method,
            confidence=CONFIDENCE_BARS_DECODED if method is not
            ReadMethod.OCR_HRI_CHECK_DIGIT_VALIDATED else CONFIDENCE_HRI_VALIDATED,
            image_id=image_id,
            bbox=bbox,
            check_digit_valid=False,
            needs_confirmation=True,
            notes=[
                "Payload did not validate as a GTIN"
                + (f" (OpenCV reported {cv_type})" if cv_type else "")
                + ". Retained as evidence only; not used as a product identity."
            ],
        )

    gtin13 = to_gtin13(payload)
    prefix = gs1_prefix(gtin13) if gtin13 else None
    notes: List[str] = []
    needs_confirmation = method is ReadMethod.OCR_HRI_CHECK_DIGIT_VALIDATED
    if needs_confirmation:
        notes.append(
            "Digits were read as text from the symbol's human-readable line and "
            "validated against the GS1 check digit. The check digit rejects most "
            "but not all misreads, so an inspector must confirm this identity."
        )
    if gtin13 is None:
        notes.append(
            "Validated as a trade-unit code (GTIN-14) for an outer carton. Its "
            "contents are not the retail unit, so no retail identity was derived."
        )
    if prefix and prefix.special_range:
        notes.append(
            f"GS1 prefix {prefix.prefix} is a special range "
            f"({prefix.member_organisation}). {prefix.note}"
        )

    return DecodedSymbol(
        payload=payload,
        kind=kind or SymbologyKind.UNVALIDATED_1D,
        method=method,
        confidence=(CONFIDENCE_HRI_VALIDATED if needs_confirmation
                    else CONFIDENCE_BARS_DECODED),
        image_id=image_id,
        bbox=bbox,
        check_digit_valid=True,
        gtin13=gtin13,
        prefix=prefix,
        needs_confirmation=needs_confirmation,
        notes=notes,
    )


def decode_symbols(image: np.ndarray, *, image_id: str,
                   regions: Optional[Sequence[BBoxT]] = None,
                   allow_hri_fallback: bool = True) -> SymbolReadResult:
    """
    Read every barcode / QR symbol this image will give up.

    Strategy, cheapest and most trustworthy first:
      1. bar decoder on the full frame;
      2. bar decoder on each localised region, padded and upscaled;
      3. QR decoder on the full frame;
      4. OCR of the human-readable digits under any region still unread,
         accepted only on a valid check digit.

    `regions` are barcode bounding boxes from `region_detection`; when omitted
    they are detected here. Passing them in lets a caller reuse one detection
    pass across OCR and decoding instead of paying for it twice.
    """
    import cv2

    result = SymbolReadResult(image_id=image_id, status=SymbolStatus.NO_SYMBOL_LOCALISED)
    if image is None or getattr(image, "size", 0) == 0:
        result.notes.append("No image data supplied.")
        return result

    bar, qr = _detectors()
    if bar is None:
        result.notes.append(
            "cv2.barcode is unavailable in this OpenCV build; bar decoding was "
            "skipped and only the OCR path ran."
        )

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    by_payload: Dict[str, DecodedSymbol] = {}

    def record(sym: DecodedSymbol) -> None:
        prior = by_payload.get(sym.payload)
        # A payload read BOTH ways keeps the stronger provenance.
        if prior is None or sym.confidence > prior.confidence:
            by_payload[sym.payload] = sym

    # 1. Full frame.
    for payload, cv_type in _cv_decode(bar, image):
        record(_build_symbol(payload, ReadMethod.CV_BARS_DECODED, image_id,
                             None, cv_type))

    # 2. Region crops.
    boxes: List[BBoxT] = list(regions) if regions is not None else []
    if regions is None:
        try:
            import region_detection

            boxes = [r.bbox for r in region_detection.detect_symbology_regions(image)]
        except Exception as exc:
            result.notes.append(f"Region localisation unavailable: {exc}")

    undecoded: List[BBoxT] = []
    for bbox in boxes:
        x, y, w, h = (int(v) for v in bbox)
        hit = False
        for pad in (6, 20):
            x0, y0 = max(0, x - pad), max(0, y - pad)
            crop = image[y0:min(image.shape[0], y + h + pad),
                         x0:min(image.shape[1], x + w + pad)]
            if crop.size == 0:
                continue
            g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
            for _k, up in _upscaled(g):
                for payload, cv_type in _cv_decode(bar, up):
                    record(_build_symbol(payload, ReadMethod.CV_BARS_DECODED,
                                         image_id, bbox, cv_type))
                    hit = True
                if hit:
                    break
            if hit:
                break
        if not hit:
            undecoded.append((x, y, w, h))

    # 3. QR on the full frame.
    if qr is not None:
        try:
            value, _pts, _sr = qr.detectAndDecode(image)
        except Exception:
            value = ""
        if value:
            record(_build_symbol(str(value), ReadMethod.QR_DECODED, image_id, None))

    # 4. HRI fallback for regions the bar decoder could not read.
    if allow_hri_fallback and undecoded:
        for bbox in undecoded:
            for payload in _read_hri(gray, bbox, image.shape):
                record(_build_symbol(payload,
                                     ReadMethod.OCR_HRI_CHECK_DIGIT_VALIDATED,
                                     image_id, bbox))

    symbols = list(by_payload.values())
    result.symbols = symbols
    # Only regions that yielded nothing at all remain "localised, not decoded".
    read_boxes = {tuple(s.bbox) for s in symbols if s.bbox}
    result.localised_not_decoded = [b for b in undecoded if tuple(b) not in read_boxes]

    product_ids = {s.gtin13 for s in symbols if s.gtin13}
    if len(product_ids) > 1:
        result.status = SymbolStatus.CONFLICTING
        result.notes.append(
            "More than one valid product code was read from this image "
            f"({sorted(product_ids)}). They cannot all identify the pack under "
            "inspection, so no identity is derived. This is commonly a second "
            "pack, a shelf label or a carton in frame."
        )
    elif symbols:
        result.status = SymbolStatus.DECODED
    elif result.localised_not_decoded:
        result.status = SymbolStatus.LOCALISED_NOT_DECODED
        result.notes.append(
            f"{len(result.localised_not_decoded)} symbol region(s) were located "
            "but could not be read. Re-photograph the barcode panel square-on "
            "and closer. Curved packs compress the bar pitch and commonly defeat "
            "the decoder."
        )
    else:
        result.status = SymbolStatus.NO_SYMBOL_LOCALISED
        result.notes.append("No barcode or QR symbol was located in this image.")

    return result


def decode_across_images(images: Sequence[Tuple[str, np.ndarray]],
                         **kwargs) -> SymbolReadResult:
    """
    Read symbols across every surface of one inspection.

    Merged under the id `MULTI_SURFACE` while each symbol keeps the id of the
    image it actually came from, so a reviewer is always sent to the photograph
    that contains the evidence. Disagreement between two images is CONFLICTING
    for the same reason it is within one image: an inspection of one pack cannot
    have two product identities, and choosing a winner here would hide the fact
    that something else was in shot.
    """
    merged = SymbolReadResult(image_id="MULTI_SURFACE",
                              status=SymbolStatus.NO_SYMBOL_LOCALISED)
    per_image: List[SymbolReadResult] = []
    for image_id, img in images:
        one = decode_symbols(img, image_id=image_id, **kwargs)
        per_image.append(one)
        merged.symbols.extend(one.symbols)
        merged.localised_not_decoded.extend(one.localised_not_decoded)
        merged.notes.extend(f"[{image_id}] {n}" for n in one.notes)

    product_ids = {s.gtin13 for s in merged.symbols if s.gtin13}
    if len(product_ids) > 1:
        merged.status = SymbolStatus.CONFLICTING
        merged.notes.append(
            f"Images disagree on the product code ({sorted(product_ids)}); no "
            "identity was derived."
        )
    elif merged.symbols:
        merged.status = SymbolStatus.DECODED
    elif merged.localised_not_decoded:
        merged.status = SymbolStatus.LOCALISED_NOT_DECODED
    elif any(r.status is SymbolStatus.CONFLICTING for r in per_image):
        merged.status = SymbolStatus.CONFLICTING
    return merged
