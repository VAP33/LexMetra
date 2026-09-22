"""
OCR and declaration-field extraction for packaged-commodity inspection.

Design goals:
- OCR is evidence extraction only. It never decides legal compliance.
- The public output shape remains compatible with the existing pipeline:
    {field: {value, confidence, bbox, numeric_value, numeric_unit, ...}}
- Gemini Vision API is the primary OCR backend when GEMINI_API_KEY is configured,
  for maximum speed and accuracy. Tesseract is the fallback backend.
- `run_ocr()` is intentionally isolated so other OCR engines can replace it.
- Multiple preprocessing variants and conservative parsing are preferred over
- aggressive guessing. "Not observed" must not become "missing" merely because
- OCR failed.
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import config

try:
    from google import genai as _genai
    from google.genai import types as _genai_types
except ImportError:
    _genai = None
    _genai_types = None

_gemini_client = None

def get_gemini_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    
    key = getattr(config, "get_gemini_api_key", lambda: os.environ.get("GEMINI_API_KEY", ""))()
    if not key or _genai is None:
        return None
    try:
        _gemini_client = _genai.Client(
            api_key=key,
            http_options=_genai_types.HttpOptions(
                timeout=int(config.GEMINI_OCR_TIMEOUT_SECONDS * 1000),
            ),
        )
        print(f"[+] [GEMINI CLIENT] Successfully initialized GenAI client with key: {key[:6]}...{key[-4:]}", flush=True)
        return _gemini_client
    except Exception as exc:
        print(f"[!] [GEMINI CLIENT ERROR] Could not initialize GenAI client: {exc}", flush=True)
        return None
from semantic_parsers import (
    MoneyValue,
    BatchCandidate,
    RoleAddressBlock,
    TemporalValue,
    parse_money,
    parse_batch_code,
    parse_date_or_duration,
    parse_role_company_block,
)
from temporal_reasoning import resolve_temporal_evidence, TemporalEvidence
from declaration_graph import DeclarationGraphResolver


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
    Produce fast, conservative OCR variants.
    Capping dimensions to 1200px ensures sub-second Tesseract CPU execution
    without losing OCR text clarity.
    """
    rgb = image.convert("RGB")
    max_dim = max(rgb.size)
    if max_dim > 1200:
        scale = 1200.0 / max_dim
        target_size = (max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale)))
        rgb_scaled = rgb.resize(target_size, Image.Resampling.BILINEAR)
    elif max_dim < 800:
        scale = min(1.5, 1100.0 / max(1, max_dim))
        target_size = (max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale)))
        rgb_scaled = rgb.resize(target_size, Image.Resampling.BILINEAR)
    else:
        rgb_scaled = rgb

    gray = ImageOps.grayscale(rgb_scaled)
    contrast = ImageEnhance.Contrast(gray).enhance(1.4)
    auto = ImageOps.autocontrast(contrast, cutoff=1)
    return [rgb_scaled, auto]


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


_gemini_circuit_broken_until: float = 0.0

def _ocr_gemini(image: Image.Image) -> List[OcrLine]:
    """
    Run Gemini Vision API for OCR extraction.

    Returns OcrLine objects compatible with the existing pipeline.
    Falls back gracefully if the API is unavailable or returns unexpected format.
    """
    global _gemini_circuit_broken_until
    if time.time() < _gemini_circuit_broken_until:
        return []

    if not getattr(config, "GEMINI_OCR_ENABLED", True) or getattr(config, "GEMINI_OCR_MODEL", "") in ("", "disabled", "none"):
        return []

    client = get_gemini_client()
    if client is None:
        print("[!] [GEMINI OCR] No client available (GEMINI_API_KEY missing or invalid)", flush=True)
        return []

    # Convert PIL image to RGB if needed
    rgb_image = image.convert("RGB")

    # Build the prompt for declaration extraction
    prompt = (
        "You are an OCR extraction system for Legal Metrology packaged commodity inspection. "
        "Extract all text visible in this image with their bounding boxes. "
        "Return ONLY a complete JSON array where each element has: "
        "{\"text\": \"<extracted text>\", \"x\": <int>, \"y\": <int>, \"w\": <int>, \"h\": <int>} "
        f"x,y,w,h are integer pixels in this exact {rgb_image.width}x{rgb_image.height} image, "
        "with (0,0) at the top-left. Never use a normalized 0-1000 coordinate system. "
        "Include all readable text, "
        "especially: MRP, Net Quantity, Manufacturing Date, Expiry Date, Batch Number, "
        "Manufacturer name, Unit Sale Price, Product Name/Common Name, Country of Origin. "
        "Do not invent or infer values not present in the image. "
        "If a field is not visible, omit it entirely."
    )

    response = None
    model_name = getattr(config, "GEMINI_OCR_MODEL", "gemini-2.5-flash-lite")
    text = ""
    try:
        print(f"[+] [GEMINI OCR] Sending image ({rgb_image.width}x{rgb_image.height}) to {model_name}...", flush=True)
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt, rgb_image],
            config=_genai_types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                max_output_tokens=config.GEMINI_OCR_MAX_OUTPUT_TOKENS,
            ),
        )
        text = getattr(response, "text", "") or ""
        print(f"[+] [GEMINI OCR SUCCESS] {model_name} returned response ({len(text)} chars)", flush=True)
    except Exception as e:
        print(f"[!] [GEMINI OCR] {model_name} failed ({e}).", flush=True)
        _gemini_circuit_broken_until = time.time() + 180.0
        print(f"[!] [GEMINI OCR] Tripping circuit breaker for 180s to prevent scan stalls.", flush=True)

    if not text:
        return []

    # Parse the JSON array response
    try:
        # Do not repair a partial response.  Salvaging a prefix silently drops
        # declarations, which is worse than using the deterministic fallback.
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
        readings = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[!] [GEMINI OCR PARSE ERROR] JSON decode failed: {e}", flush=True)
        return []

    if not isinstance(readings, list):
        return []

    # Convert readings to OcrLine objects
    lines: List[OcrLine] = []
    for reading in readings:
        if not isinstance(reading, dict):
            continue
        txt = str(reading.get("text", reading.get("label", ""))).strip()
        if not txt:
            continue

        # Check if box_2d or bbox array is provided [ymin, xmin, ymax, xmax]
        box = reading.get("box_2d") or reading.get("bbox")
        if isinstance(box, (list, tuple)) and len(box) == 4:
            try:
                ymin, xmin, ymax, xmax = (float(v) for v in box)
                # Check if normalized 0-1000
                if max(ymin, xmin, ymax, xmax) <= 1000:
                    x = int(xmin * rgb_image.width / 1000)
                    y = int(ymin * rgb_image.height / 1000)
                    w = int((xmax - xmin) * rgb_image.width / 1000)
                    h = int((ymax - ymin) * rgb_image.height / 1000)
                else:
                    x = int(xmin)
                    y = int(ymin)
                    w = int(xmax - xmin)
                    h = int(ymax - ymin)
            except (ValueError, TypeError):
                continue
        else:
            try:
                x = int(reading.get("x", reading.get("left", 0)))
                y = int(reading.get("y", reading.get("top", 0)))
                w = int(reading.get("w", reading.get("width", 0)))
                h = int(reading.get("h", reading.get("height", 0)))
            except (KeyError, TypeError, ValueError):
                continue

            # Detect if w/h were actually right/bottom bounds (x2, y2)
            if x + w > rgb_image.width and x < w <= rgb_image.width:
                w = w - x
            if y + h > rgb_image.height and y < h <= rgb_image.height:
                h = h - y

            # Detect if coordinates are normalized to 0-1000
            if max(x, y, w, h) <= 1000 and (x + w > rgb_image.width or y + h > rgb_image.height):
                if rgb_image.width != 1000 or rgb_image.height != 1000:
                    x = int(x * rgb_image.width / 1000)
                    y = int(y * rgb_image.height / 1000)
                    w = int(w * rgb_image.width / 1000)
                    h = int(h * rgb_image.height / 1000)

        # Clip slightly out-of-bounds coords to image boundaries
        if x < 0:
            x = 0
        if y < 0:
            y = 0
        if x + w > rgb_image.width:
            w = max(1, rgb_image.width - x)
        if y + h > rgb_image.height:
            h = max(1, rgb_image.height - y)

        if w <= 0 or h <= 0 or x >= rgb_image.width or y >= rgb_image.height:
            continue

        lines.append(
            OcrLine(
                text=txt,
                bbox=(int(x), int(y), int(w), int(h)),
                # The API does not provide line confidence; this is deliberately
                # below definitive evidence and is later localized independently.
                confidence=0.72,
                fusion_state="SINGLE_SOURCE",  # Single reading from Gemini
                alternatives=(),
                region_id=None,
            )
        )

    print(f"[+] [GEMINI OCR] Processed {len(lines)} valid bounding box lines from Gemini response.", flush=True)
    return lines


def run_ocr(image: Image.Image, face_idx: Optional[int] = None, **kwargs: Any) -> List[OcrLine]:
    """
    Read an image and return text lines in ORIGINAL image coordinates.

    Uses Gemini Vision API as the primary backend when GEMINI_API_KEY is configured,
    for maximum speed and accuracy. Falls back to Tesseract whole-image multi-variant OCR
    only if Gemini is unavailable or returns 0 lines.
    """
    import time
    t_start = time.perf_counter()
    lines: List[OcrLine] = []

    # 1. Gemini Vision API (primary when configured)
    gemini_client = get_gemini_client()
    gemini_done = False
    if gemini_client is not None:
        t_gemini_start = time.perf_counter()
        print("[*] [OCR PIPELINE] Executing Gemini Vision OCR...", flush=True)
        try:
            gemini_lines = _ocr_gemini(image)
            t_gemini_elapsed = (time.perf_counter() - t_gemini_start) * 1000.0
            if gemini_lines:
                lines.extend(gemini_lines)
                gemini_done = True
                print(f"[+] [OCR PIPELINE] [TIMING] Gemini Vision OCR extracted {len(gemini_lines)} lines in {t_gemini_elapsed:.1f}ms", flush=True)
            else:
                print(f"[!] [OCR PIPELINE] Gemini Vision returned 0 lines in {t_gemini_elapsed:.1f}ms, falling back to local OCR.", flush=True)
        except Exception as e:
            print(f"[!] [OCR PIPELINE] Gemini Vision error ({e}), falling back to local OCR.", flush=True)
    else:
        print("[*] [OCR PIPELINE] Gemini client unavailable. Using local OCR engines.", flush=True)

    # 2. Whole-image Tesseract OCR (fallback only when primary returned 0 lines)
    if not gemini_done or len(lines) == 0:
        t_tess_start = time.perf_counter()
        try:
            print(f"[*] [OCR PIPELINE] Running Tesseract whole-image OCR fallback (current lines={len(lines)})...", flush=True)
            whole_lines = _run_ocr_whole_image(image)
            lines.extend(whole_lines)
            t_tess_elapsed = (time.perf_counter() - t_tess_start) * 1000.0
            print(f"[+] [OCR PIPELINE] [TIMING] Tesseract OCR completed in {t_tess_elapsed:.1f}ms. Total lines: {len(lines)}", flush=True)
        except Exception as e:
            print(f"[!] [OCR PIPELINE] Tesseract OCR error: {e}", flush=True)
    else:
        print(f"[+] [OCR PIPELINE] Fast path active: skipped redundant local Tesseract passes ({len(lines)} high-quality lines available).", flush=True)

    deduped = _dedupe_lines(lines)
    total_elapsed = (time.perf_counter() - t_start) * 1000.0
    print(f"[+] [OCR PIPELINE] [TIMING] Total OCR completed in {total_elapsed:.1f}ms (final lines: {len(deduped)})", flush=True)
    return deduped


def _run_ocr_whole_image(image: Image.Image) -> List[OcrLine]:
    """
    Fast whole-image OCR across tuned preprocessing variants with bounding
    boxes mapped back to original coordinates.
    """
    original = image.convert("RGB")
    orig_w, orig_h = original.size
    variants = _preprocess_variants(original)

    all_lines: List[OcrLine] = []

    for variant_index, variant in enumerate(variants):
        vw, vh = variant.size
        sx = orig_w / vw
        sy = orig_h / vh

        # Fast PSM 6 (single uniform block of text)
        try:
            lines = _ocr_single(variant, psm=6)
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
        except Exception:
            pass

        # Early exit: if variant 0 already extracted rich text (>= 8 lines),
        # skip subsequent variants to ensure sub-second CPU response time.
        if variant_index == 0 and len(all_lines) >= 8:
            break

    # If initial pass found very few lines (< 4), try sparse mode PSM 11 on variant 0
    if len(all_lines) < 4 and len(variants) > 0:
        vw, vh = variants[0].size
        sx = orig_w / vw
        sy = orig_h / vh
        try:
            sparse_lines = _ocr_single(variants[0], psm=11)
            for line in sparse_lines:
                x, y, w, h = line.bbox
                all_lines.append(
                    OcrLine(
                        text=line.text,
                        bbox=(
                            max(0, int(round(x * sx))),
                            max(0, int(round(y * sy))),
                            max(1, int(round(w * sx))),
                            max(1, int(round(h * sy))),
                        ),
                        confidence=line.confidence,
                    )
                )
        except Exception:
            pass

    return _dedupe_lines(all_lines)


# ---------------------------------------------------------------------------
# Field patterns and parsers
# ---------------------------------------------------------------------------



# Re-export patterns, classifiers, and normalization functions from ocr_patterns
from ocr_patterns import (
    FIELD_PATTERNS,
    _MONEY_RE,
    classify_fields,
    normalize_date,
    _extract_money,
    _extract_qty,
    _extract_date,
    _normalized_text,
    _canonical_numeric_unit,
    _extract_unit_price_unit,
    _value_shape,
    _line_center_y,
    _vertical_distance,
    _x_gap,
    _is_label_line,
    _inline_label_value,
    _candidate_value_lines,
)

_normalize_date = normalize_date

__all__ = [
    "OcrLine",
    "run_ocr",
    "classify_fields",
    "normalize_date",
    "_normalize_date",
    "FIELD_PATTERNS",
]

