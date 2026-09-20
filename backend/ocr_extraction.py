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
    Produce conservative OCR variants.

    The original image is always included. Extra variants mainly help with
    low-contrast labels and small text. Image dimensions are capped to 2048px
    to prevent runaway CPU latency on high-resolution camera images.
    """
    rgb = image.convert("RGB")
    gray = ImageOps.grayscale(rgb)

    max_dim = max(gray.size)
    if max_dim < 1000:
        scale = min(2.0, 1600.0 / max(1, max_dim))
    elif max_dim < 1600:
        scale = min(1.3, 1920.0 / max(1, max_dim))
    else:
        scale = min(1.0, 2048.0 / max(1, max_dim))

    if abs(scale - 1.0) > 0.05:
        target_size = (max(1, int(gray.width * scale)), max(1, int(gray.height * scale)))
        enlarged = gray.resize(target_size, Image.Resampling.BILINEAR)
    else:
        enlarged = gray

    contrast = ImageEnhance.Contrast(enlarged).enhance(1.5)
    sharp = contrast.filter(ImageFilter.SHARPEN)
    auto = ImageOps.autocontrast(sharp, cutoff=1)

    # For large images, 2 variants (rgb + auto) provide excellent coverage at 2x speed
    if max_dim >= 1200:
        return [rgb, auto]
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


def _ocr_gemini(image: Image.Image) -> List[OcrLine]:
    """
    Run Gemini Vision API for OCR extraction.

    Returns OcrLine objects compatible with the existing pipeline.
    Falls back gracefully if the API is unavailable or returns unexpected format.
    """
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
    candidate_models = [config.GEMINI_OCR_MODEL]
    for alt in ("gemini-3.5-flash-lite", "gemini-3.6-flash"):
        if alt not in candidate_models:
            candidate_models.append(alt)

    text = ""
    for model_name in candidate_models:
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
            break
        except Exception as e:
            print(f"[!] [GEMINI OCR] {model_name} failed ({e}). Trying next model...", flush=True)

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
        txt = str(reading.get("text", "")).strip()
        if not txt:
            continue
        try:
            x, y, w, h = (int(reading[k]) for k in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError):
            continue

        # A box is evidence.  Reject malformed/off-image geometry rather than
        # clipping it into an apparently plausible but wrong overlay.
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > rgb_image.width or y + h > rgb_image.height:
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

        # PSM 6 handles text blocks and label panels well
        psms = [6]
        # Only add sparse mode (PSM 11) on first variant if initial extraction found very few lines
        if variant_index == 0 and len(all_lines) < 6:
            psms.append(11)

        for psm in psms:
            try:
                lines = _ocr_single(variant, psm=psm)
            except Exception:
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

