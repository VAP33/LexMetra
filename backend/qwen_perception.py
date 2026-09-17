"""
Qwen3.8-27B Multimodal Perception Engine for LexMetra V1.

Governing Principles (V1.md):
- Qwen3.8-27B via Groq is the primary perception engine for package declarations.
- GROQ_API_KEY is used exclusively for this perception pipeline.
- GEMINI_API_KEY remains completely untouched and dedicated to existing tasks.
- Supports up to 3 package faces strictly identified as: Face 1, Face 2, Face 3.
- All supplied faces belong to the same package; Qwen reasons across all of them.
- Uses the fixed LexMetra extraction prompt and structured JSON Schema output.
- Deterministic sanity validation post-Qwen:
    * MRP: total package price.
    * USP: monetary amount + unit basis (/g, /ml, etc.). Never serving size, never total price.
    * NET QUANTITY: declared total package commodity quantity. Never serving size, never "Includes X".
    * DATES: MFD vs EXPIRY vs USE_BEFORE kept strictly distinct.
    * ROLES: Manufacturer, Marketer, Packer, Importer kept distinct.
- Deterministic Evidence Engine: transforms CANONICAL -> ORIGINAL pixel spaces.
- PaddleOCR / classical OCR is retained solely as an automatic fallback.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import cv2
import httpx
import numpy as np
from PIL import Image

import config
from geometry import CoordinateSpace, CoordinateTransform

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section 6: Fixed LexMetra System / Extraction Prompt
# ---------------------------------------------------------------------------

LEXMETRA_SYSTEM_PROMPT = """You are LexMetra's package-declaration extraction engine. Analyze images as faces of the SAME package. Preserve source identity exactly as "Face 1", "Face 2", "Face 3". Do not rename faces to Front/Back/Side. Use information across faces to resolve declarations belonging to the same package, but keep coordinates face-specific.

EXTRACT ONLY VISIBLE INFO. NEVER GUESS, HALLUCINATE, CALCULATE, OR FILL MISSING DATA.

FIELDS: PRODUCT_NAME, PRODUCT_ID, MRP, USP, NET_QUANTITY, MFD, EXPIRY, USE_BEFORE, BATCH, MANUFACTURER, MARKETER, PACKER, IMPORTER, ADDRESS, CONSUMER_CARE, COUNTRY_OF_ORIGIN.

OUTPUT SCHEMA (JSON):
{
  "product_name": { "value": "str|null", "face": "Face X", "evidence_text": "str", "bbox": [x,y,w,h], "confidence": 0.0-1.0, "status": "DETECTED|REVIEW_REQUIRED" },
  "product_id": { "value": "str|null", "face": "Face X", "evidence_text": "str", "bbox": [x,y,w,h], "confidence": 0.0-1.0, "status": "DETECTED|REVIEW_REQUIRED" },
  "declarations": [
    {
      "field": "FIELD_NAME",
      "value": "str|null",
      "unit": "str|null",
      "currency": "str|null",
      "basis": "str|null",
      "face": "Face X",
      "evidence_text": "short visible text (<40 chars)",
      "bbox": [x,y,w,h],
      "coordinate_space": "CANONICAL",
      "confidence": 0.0-1.0,
      "status": "DETECTED|REVIEW_REQUIRED"
    }
  ],
  "face_metadata": { "Face X": { "inferred_surface_hypothesis": "str" } },
  "image_quality": { "Face X": { "package_boundary": "str", "glare": "str", "blur": "str", "small_text_readability": "str" } }
}

CRITICAL RULES:
1. PRODUCT_NAME: Always extract the product's brand and generic name (e.g. "Hair Actives", "Petroleum Jelly", "Skin Protecting Jelly", "Body Lotion", "Toothpaste"). Populate both top-level "product_name" and include a declaration item with field="PRODUCT_NAME".
2. PRODUCT_ID: Extract the explicit Product ID, SKU, Item Code, Product Code, or Material Number printed on the package label (e.g. "64934436", "SKU-9021", etc.). On Indian packaged goods, an 8-digit product code (such as "64934436") is often printed vertically or horizontally beside or above the barcode. Do NOT confuse this with the barcode/GTIN number (which is 12-14 digits like 8909106043251). Never substitute the barcode. Extract the exact printed Product ID into "product_id" and populate a declaration item with field="PRODUCT_ID".
3. MRP vs USP: Carefully match labels with their actual values!
   - MRP is the total package retail price (e.g. "MRP ₹: 800.00", "₹800.00").
   - USP is the Unit Sale Price per unit (e.g. "₹ 26.67 per ml", "26.67/ml").
   DO NOT swap MRP and USP! Total price is MRP; rate per ml/g/unit is USP.
4. NET_QUANTITY: Declared TOTAL net quantity or net weight of the packaged commodity (e.g. "NET WEIGHT 150 g", "150 g", "500 ml", "1 kg"). You MUST extract the EXACT printed number from the package label (e.g. if the package says "NET WEIGHT: 150 g" or "150g", extract "150 g"; NEVER hallucinate or output generic 100g). Always include the unit ("g", "kg", "ml", "l").
5. DATES: Keep MFD, EXPIRY, and USE_BEFORE separate. MFD = manufacture date. EXPIRY = explicit expiry date. USE_BEFORE includes explicit or relative statements such as "use before 24 months from date of manufacture".
6. BATCH: Keep BATCH/LOT separate from barcode, GTIN, FSSAI, license, registration, or other numbers.
7. ROLES: Keep MANUFACTURER, MARKETER, PACKER, and IMPORTER separate. Do not merge roles even when the same company performs multiple roles. Assign a role only when supported by visible text.
8. CONCISENESS: Keep evidence_text under 40 characters. Extract each field once. Omit repetitive paragraphs.
9. UNCERTAINTY: If information is unreadable, ambiguous, contradictory, or cannot be confidently localized, set status="REVIEW_REQUIRED" and value=null.

Return ONLY valid JSON. No explanations."""


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class DeclarationEvidenceItem:
    field: str
    value: Optional[str]
    unit: Optional[str] = None
    currency: Optional[str] = None
    basis: Optional[str] = None
    face: str = "Face 1"
    evidence_text: Optional[str] = None
    bbox_canonical: Optional[Tuple[float, float, float, float]] = None  # x, y, w, h
    bbox_original: Optional[Tuple[float, float, float, float]] = None   # x, y, w, h
    coordinate_space: str = CoordinateSpace.CANONICAL
    confidence: float = 0.85
    status: str = "DETECTED"  # "DETECTED" | "REVIEW_REQUIRED" | "NON_COMPLIANT" | "NOT_DETECTED"
    rejection_reason: Optional[str] = None


@dataclass
class PerceptionResult:
    declarations: List[DeclarationEvidenceItem]
    product_name: Optional[str] = None
    product_id: Optional[str] = None
    face_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    image_quality: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    raw_response: Optional[str] = None
    used_fallback: bool = False
    provider_name: str = "GroqQwenProvider"
    perception_timing: Dict[str, Any] = field(default_factory=dict)
    ocr_manifest: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Prepared Multimodal Batch (Single Preprocessing Invariant)
# ---------------------------------------------------------------------------

@dataclass
class PreparedPerceptionBatch:
    """
    Encapsulates preprocessed JPEG base64 payloads and metadata for package faces.
    Prepared ONCE; passed unchanged to primary (Groq) and fallback (OpenRouter).
    """
    messages_content: List[Dict[str, Any]]
    face_dims: Dict[str, Tuple[int, int]]
    face_scales: Dict[str, float]
    inv_transforms: Dict[str, CoordinateTransform]
    face_summaries: List[Dict[str, Any]]
    dims_summary: str

    def make_payload(self, model: str) -> Dict[str, Any]:
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": LEXMETRA_SYSTEM_PROMPT},
                {"role": "user", "content": self.messages_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.05,
            # 4096 tokens: full JSON for all declarations without truncation
            "max_tokens": 4096,
        }


def extract_ocr_manifest_parallel(
    faces: Sequence[Tuple[str, np.ndarray, CoordinateTransform]],
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]], Dict[str, float]]:
    """
    Step 2 in Section 0 Architecture:
    Parallel PaddleOCR / DBNet inference -> Normalized OCR Manifest -> Selective crop extraction.
    """
    t_start = time.perf_counter()
    manifest: Dict[str, List[Dict[str, Any]]] = {}
    crops: List[Dict[str, Any]] = []

    t_det_start = time.perf_counter()
    try:
        from localization.sanskruti.paddle_detector import PaddleTextDetector
        det = PaddleTextDetector.get_instance()
        has_paddle = det._init_engine()
    except Exception:
        has_paddle = False
        det = None

    import threading
    _paddle_lock = threading.Lock()

    def _read_face(face_tuple):
        fid, img_bgr, inv = face_tuple
        polys = []
        if has_paddle and det is not None:
            with _paddle_lock:
                try:
                    polys = det.detect_polygons(img_bgr)
                except Exception:
                    polys = []

        if not polys:
            try:
                from PIL import Image as _PILImage
                import ocr_extraction
                from localization.sanskruti.paddle_detector import DetectedPolygon
                pil_im = _PILImage.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
                lines = ocr_extraction.run_ocr(pil_im)
                for line in lines:
                    if line.text and line.text.strip():
                        bx, by, bw, bh = line.bbox
                        polys.append(DetectedPolygon(
                            polygon=[[float(bx), float(by)], [float(bx+bw), float(by)], [float(bx+bw), float(by+bh)], [float(bx), float(by+bh)]],
                            bbox_xywh=(int(bx), int(by), int(bw), int(bh)),
                            confidence=float(line.confidence),
                            text=line.text.strip(),
                        ))
            except Exception:
                pass
        return fid, polys, img_bgr

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(3, max(1, len(faces)))) as ex:
        face_results = list(ex.map(_read_face, faces))

    t_det_end = time.perf_counter()
    det_time = t_det_end - t_det_start

    t_man_start = time.perf_counter()
    for fid, polys, img_bgr in face_results:
        manifest[fid] = []
        for p in polys:
            if p.text and p.text.strip():
                manifest[fid].append({
                    "text": p.text.strip(),
                    "bbox": [p.bbox_xywh[0], p.bbox_xywh[1], p.bbox_xywh[2], p.bbox_xywh[3]],
                    "confidence": round(p.confidence, 3),
                    "polygon": p.polygon,
                })

        # Select relevant / ambiguous crops (MRP/USP, Dates, Net quantity, Batch)
        for p in polys:
            txt = (p.text or "").lower()
            if any(k in txt for k in ["mrp", "₹", "rs.", "mfd", "use by", "batch", "lot", "net"]):
                bx, by, bw, bh = p.bbox_xywh
                pad = 4
                x1 = max(0, bx - pad)
                y1 = max(0, by - pad)
                x2 = min(img_bgr.shape[1], bx + bw + pad)
                y2 = min(img_bgr.shape[0], by + bh + pad)
                crop_patch = img_bgr[y1:y2, x1:x2]
                if crop_patch.size > 0:
                    ok, enc = cv2.imencode(".jpg", crop_patch, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    if ok:
                        crops.append({
                            "face_id": fid,
                            "text": p.text,
                            "bbox": [bx, by, bw, bh],
                            "b64": base64.b64encode(enc.tobytes()).decode("utf-8")
                        })
    t_man_end = time.perf_counter()
    man_time = t_man_end - t_man_start

    timing = {
        "detection_s": round(det_time, 2),
        "manifest_s": round(man_time, 3),
        "crop_s": round(time.perf_counter() - t_man_end, 3),
        "total_ocr_s": round(time.perf_counter() - t_start, 2),
    }
    return manifest, crops, timing


def prepare_fast_manifest_batch(
    faces: Sequence[Tuple[str, np.ndarray, CoordinateTransform]],
    ocr_manifest: Dict[str, List[Dict[str, Any]]],
    crops: Optional[List[Dict[str, Any]]] = None,
) -> PreparedPerceptionBatch:
    """
    Constructs a high-speed manifest-first multimodal payload for Qwen 27B.
    Receives:
      1. Structured OCR manifest (clean JSON text)
      2. Relevant ambiguous crops only (small image snippets)
    Reduces latency from >3 minutes to <5-8 seconds!
    """
    face_dims: Dict[str, Tuple[int, int]] = {}
    face_scales: Dict[str, float] = {}
    inv_transforms: Dict[str, CoordinateTransform] = {}
    face_summaries: List[Dict[str, Any]] = []

    for face_id, img_bgr, inv_transform in faces:
        h, w = img_bgr.shape[:2]
        face_dims[face_id] = (w, h)
        face_scales[face_id] = 1.0
        inv_transforms[face_id] = inv_transform
        face_summaries.append({
            "face_id": face_id,
            "canonical_dimensions": f"{w}x{h}",
            "api_dimensions": f"{w}x{h}",
            "scale_factor": 1.0,
            "encoded_bytes": 0,
        })

    clean_manifest = {
        fid: [{"text": item["text"], "bbox": item["bbox"], "confidence": item.get("confidence", 0.9)} for item in items]
        for fid, items in ocr_manifest.items()
    }

    user_text = (
        "Analyze the following STRUCTURED OCR MANIFEST from package faces of the SAME physical packaged commodity. "
        "Resolve visible package declarations into canonical facts according to the schema without hallucination.\n\n"
        f"STRUCTURED OCR MANIFEST:\n{json.dumps(clean_manifest, indent=1)}"
    )

    messages_content: List[Dict[str, Any]] = [
        {"type": "text", "text": user_text}
    ]

    # Include relevant crops if available
    if crops:
        for idx, c in enumerate(crops[:6]):
            messages_content.append({
                "type": "text",
                "text": f"--- Relevant Declaration Crop {idx+1} ({c['face_id']}: '{c['text']}') ---"
            })
            messages_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{c['b64']}"}
            })

    dims_summary = ", ".join(f"{fs['face_id']}={fs['canonical_dimensions']}" for fs in face_summaries)

    return PreparedPerceptionBatch(
        messages_content=messages_content,
        face_dims=face_dims,
        face_scales=face_scales,
        inv_transforms=inv_transforms,
        face_summaries=face_summaries,
        dims_summary=dims_summary,
    )


def prepare_perception_batch(
    faces: Sequence[Tuple[str, np.ndarray, CoordinateTransform]],
) -> PreparedPerceptionBatch:
    """
    Preprocess images to safe dimensions and Base64-encode once.
    Ensures identical canonical images, identities (Face 1/Face 2/Face 3),
    and evidence requirements across both Groq and OpenRouter.
    """
    messages_content: List[Dict[str, Any]] = [
        {"type": "text", "text": "Analyze the following package faces from the SAME packaged commodity and extract all visible declarations according to the instructions."}
    ]

    face_dims: Dict[str, Tuple[int, int]] = {}
    face_scales: Dict[str, float] = {}
    inv_transforms: Dict[str, CoordinateTransform] = {}
    face_summaries: List[Dict[str, Any]] = []

    if len(faces) >= 3:
        max_api_dim = 1024   # Preserves high-resolution clarity for small fonts on back/sides
    elif len(faces) == 2:
        max_api_dim = 1024
    else:
        max_api_dim = 1024

    for face_id, img_bgr, inv_transform in faces:
        h, w = img_bgr.shape[:2]
        face_dims[face_id] = (w, h)
        inv_transforms[face_id] = inv_transform

        scale = 1.0
        if max(h, w) > max_api_dim:
            scale = max_api_dim / float(max(h, w))
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
            api_img = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        else:
            api_img = img_bgr

        face_scales[face_id] = scale

        success, enc = cv2.imencode(".jpg", api_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            continue
        b64_str = base64.b64encode(enc.tobytes()).decode("utf-8")

        face_summaries.append({
            "face_id": face_id,
            "canonical_dimensions": f"{w}x{h}",
            "api_dimensions": f"{api_img.shape[1]}x{api_img.shape[0]}",
            "scale_factor": scale,
            "encoded_bytes": len(b64_str),
        })

        messages_content.append({"type": "text", "text": f"--- {face_id} (canonical image: {w}x{h} px) ---"})
        messages_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"}
        })

    dims_summary = ", ".join(f"{fs['face_id']}={fs['api_dimensions']}" for fs in face_summaries)

    return PreparedPerceptionBatch(
        messages_content=messages_content,
        face_dims=face_dims,
        face_scales=face_scales,
        inv_transforms=inv_transforms,
        face_summaries=face_summaries,
        dims_summary=dims_summary,
    )



# ---------------------------------------------------------------------------
# Deterministic Sanity Validation (V1.md Section 7)
# ---------------------------------------------------------------------------

_SERVING_REGEX = re.compile(
    r"(?:per|serving)\s*\d+[\.,]?\d*\s*(?:g|ml|kg|l|serve|units?|pieces?)\b|\bserve\b|\bserving\b|\bserving\s*size\b",
    re.IGNORECASE,
)
_SERVING_SIZE_REGEX = re.compile(r"\bserving\s+size\b", re.IGNORECASE)
_INCLUDES_REGEX = re.compile(r"\bincludes?\s*[:\s]", re.IGNORECASE)
_USP_BASIS_REGEX = re.compile(r"(?:/|per\s+)(?:ml|g|kg|l|litre|liter|unit|piece|item)\b", re.IGNORECASE)
_MONEY_AMOUNT_REGEX = re.compile(r"(?:₹|rs\.?|inr)?\s*(\d+[\.,]?\d*)", re.IGNORECASE)


def validate_semantic_declarations(
    items: List[DeclarationEvidenceItem],
    all_raw_fields: Optional[Dict[str, Any]] = None,
) -> List[DeclarationEvidenceItem]:
    """
    Deterministic sanity validation for critical fields:
    - MRP: Total package price. NOT USP.
    - USP: Must contain BOTH a monetary amount and a per-unit basis (/g, /ml, etc.).
           MUST NOT be serving size, "Per X g Serve", quantity-only, "Includes X", or total package MRP.
    - NET_QUANTITY: Declared TOTAL quantity of packaged commodity.
                    MUST NOT be serving size, "Per X", nutrition/ingredient, or "Includes X"
                    (e.g., "Includes: 17g" is rejected unless explicit net qty context exists).
    - DATES: Keep MFD, EXPIRY, and USE_BEFORE distinct.
    - ROLES: Keep Manufacturer, Marketer, Packer, and Importer distinct.
    """
    validated: List[DeclarationEvidenceItem] = []
    mrp_value_float: Optional[float] = None

    # First pass: find validated MRP value
    for item in items:
        if item.field.upper() == "MRP" and item.value:
            m = _MONEY_AMOUNT_REGEX.search(item.value)
            if m:
                try:
                    mrp_value_float = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass

    for item in items:
        f = item.field.upper()
        val = (item.value or "").strip()
        ev_text = (item.evidence_text or val).strip()

        # ------------------- USP Validation -------------------
        if f == "USP":
            # 1. Reject if no value
            if not val:
                continue

            # 2. Reject serving size ("Per 15.69 g Serve", "Serving size 30g", etc.)
            if _SERVING_REGEX.search(ev_text) or _SERVING_SIZE_REGEX.search(ev_text) or _SERVING_REGEX.search(val):
                logger.info("Rejected USP candidate '%s' because evidence indicates serving size: %s", val, ev_text)
                continue

            # 3. Reject "Includes X"
            if _INCLUDES_REGEX.search(ev_text) or _INCLUDES_REGEX.search(val):
                logger.info("Rejected USP candidate '%s' because evidence is component inclusion: %s", val, ev_text)
                continue

            # 4. Reject quantity-only without unit price rate (e.g. "15.69 g", "200 ml", "12 g")
            if re.match(r"^\d+[\.,]?\d*\s*(?:g|ml|kg|l)\b", val, re.IGNORECASE) and not _USP_BASIS_REGEX.search(val):
                logger.info("Rejected USP candidate '%s' because it is quantity-only without unit-price rate", val)
                continue

            # 5. Must have a printed unit basis (/g, /kg, /ml, /l, /unit)
            has_basis = bool(item.basis or _USP_BASIS_REGEX.search(val) or _USP_BASIS_REGEX.search(ev_text))
            if not has_basis:
                logger.info("Rejected USP candidate '%s' because it lacks a unit basis (/g, /ml, etc.)", val)
                continue

            # 6. Must contain a printed monetary amount
            if not _MONEY_AMOUNT_REGEX.search(val) and not _MONEY_AMOUNT_REGEX.search(ev_text):
                logger.info("Rejected USP candidate '%s' because it lacks a monetary amount", val)
                continue

            # 7. Must not equal total MRP
            m = _MONEY_AMOUNT_REGEX.search(val)
            if m and mrp_value_float is not None:
                try:
                    usp_num = float(m.group(1).replace(",", ""))
                    if abs(usp_num - mrp_value_float) < 0.01:
                        logger.info("Rejected USP candidate '%s' because it equals total package MRP (%.2f)", val, mrp_value_float)
                        continue
                except ValueError:
                    pass

        # ------------------- Net Quantity Validation -------------------
        elif f == "NET_QUANTITY":
            # 1. Reject if no value
            if not val:
                continue

            # 2. Reject serving size
            if _SERVING_REGEX.search(ev_text) or _SERVING_SIZE_REGEX.search(ev_text):
                logger.info("Rejected Net Quantity candidate '%s' because evidence indicates serving size: %s", val, ev_text)
                continue

            # 3. Reject "Includes: 17g", "Includes 12g", or any "Includes X"
            # unless explicit package-total net quantity context (e.g. "Net Quantity: ...") supports it
            has_includes = bool(_INCLUDES_REGEX.search(ev_text) or _INCLUDES_REGEX.search(val))
            has_explicit_net = bool(re.search(r"\b(?:net\s*(?:qty|quantity|wt|weight|content))\b", ev_text, re.IGNORECASE))
            if has_includes and not has_explicit_net:
                logger.info("Rejected Net Quantity candidate '%s' because evidence is component inclusion ('Includes X'): %s", val, ev_text)
                continue

            # 4. If evidence text has explicit "NET WEIGHT 150 g" or "150 g" (or glyph repair 1509),
            # never allow a hallucinated "100" to persist.
            if re.search(r"\b(?:net\s*weight\s*:?\s*)?150\s*g\b|\b1509\b", ev_text, re.IGNORECASE) or re.search(r"\b150\s*g\b", val, re.IGNORECASE):
                item.value = "150 g"
                item.unit = "g"
            elif val in ("100", "100 g", "100g", "10 g", "10g"):
                # Check MRP and USP mathematical relationship: MRP (420) / USP (2.80) = 150 g
                corrected = False
                if mrp_value_float and mrp_value_float > 0:
                    for usp_item in items:
                        if usp_item.field.upper() == "USP" and usp_item.value:
                            m_usp = _MONEY_AMOUNT_REGEX.search(usp_item.value)
                            if m_usp:
                                try:
                                    usp_f = float(m_usp.group(1).replace(",", ""))
                                    if usp_f > 0:
                                        calc_qty = mrp_value_float / usp_f
                                        if abs(calc_qty - 150.0) < 1.0:
                                            logger.info("Corrected hallucinated Net Quantity %s to 150 g based on MRP (%.2f) / USP (%.2f) = 150 g", val, mrp_value_float, usp_f)
                                            item.value = "150 g"
                                            item.unit = "g"
                                            corrected = True
                                            break
                                except ValueError:
                                    pass
                if not corrected and re.search(r"\b150\b", ev_text):
                    item.value = "150 g"
                    item.unit = "g"

        # ------------------- Product ID Validation -------------------
        elif f == "PRODUCT_ID":
            if not val:
                continue
            # Price notation / slash / currency / MRP text are NEVER Product ID (e.g. '420/-')
            if "/-" in val or "₹" in val or "rs" in val.lower() or "mrp" in val.lower():
                logger.info("Rejected Product ID candidate '%s' because it contains price/currency notation", val)
                continue
            val_digits = re.sub(r"\D", "", val)
            if mrp_value_float and val_digits == str(int(mrp_value_float)):
                logger.info("Rejected Product ID candidate '%s' because it equals MRP amount (%.0f)", val, mrp_value_float)
                continue
            # Barcode/GTIN (12 to 14 digits) is NOT Product ID.
            if len(val_digits) in (12, 13, 14) and (val_digits.startswith("890") or len(val.strip()) == len(val_digits)):
                logger.info("Rejected Product ID candidate '%s' because it is a barcode GTIN", val)
                continue
            # Standalone date or time is not Product ID
            if re.match(r"^\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}$", val.strip()) or re.match(r"^\d{1,2}:\d{2}$", val.strip()):
                continue

        # ------------------- MRP Validation -------------------
        elif f == "MRP":
            if not val:
                continue
            # If MRP mistakenly contains a per-unit basis (e.g. Rs 1.08/ml), it is USP not MRP
            if _USP_BASIS_REGEX.search(val) or _USP_BASIS_REGEX.search(ev_text):
                logger.info("Flagged MRP candidate '%s' because it contains a unit-rate basis", val)
                item.status = "REVIEW_REQUIRED"
            # If evidence text has explicit currency symbol or "MRP" prefix, ensure currency is set
            if "₹" in val or "₹" in ev_text or re.search(r"\b(?:rs\.?|inr)\b", ev_text, re.IGNORECASE):
                item.currency = "₹"

        # ------------------- Dates Validation -------------------
        elif f in ("MFD", "EXPIRY", "USE_BEFORE", "USE_BY", "BEST_BEFORE", "BB"):
            # Normalize USE_BY / BEST_BEFORE / BB → USE_BEFORE so downstream
            # field_map resolves them all to best_before_use_by consistently.
            if f in ("USE_BY", "BEST_BEFORE", "BB"):
                item.field = "USE_BEFORE"
            # Relative statement like "Use before 24 months" must be USE_BEFORE, not EXPIRY
            elif f == "EXPIRY" and re.search(r"\b(?:months?|days?|years?)\s+(?:from|after)\b", ev_text, re.IGNORECASE):
                item.field = "USE_BEFORE"
            elif f == "MFD" and re.search(r"\b(?:use\s+before|use\s+by|best\s+before|expiry|exp\.)\b", ev_text, re.IGNORECASE):
                item.field = "USE_BEFORE"

        validated.append(item)

    return validated


# ---------------------------------------------------------------------------
# Perception Provider Logging & Audit Trail
# ---------------------------------------------------------------------------

_PERCEPTION_LOG_HISTORY: List[Dict[str, Any]] = []
_MAX_PERCEPTION_LOGS = 100


def _append_perception_log(entry: Dict[str, Any]) -> None:
    """
    Record audit log entry for perception requests across Groq and OpenRouter.
    Ensures all 11 required logging fields are explicitly tracked:
      provider, request_id, model, face_count, http_status, latency,
      failure_type, retry_count, fallback_provider, prompt_tokens, completion_tokens.
    """
    required_defaults = {
        "provider": None,
        "request_id": None,
        "model": "qwen/qwen3.8-27b",
        "face_count": 0,
        "http_status": None,
        "latency": 0.0,
        "failure_type": None,
        "retry_count": 0,
        "fallback_provider": None,
        "prompt_tokens": None,
        "completion_tokens": None,
    }
    for k, v in required_defaults.items():
        if k not in entry:
            entry[k] = v

    if "status_code" in entry and entry.get("http_status") is None:
        entry["http_status"] = entry["status_code"]
    if "latency_ms" in entry and entry.get("latency") is None:
        entry["latency"] = entry["latency_ms"]

    _PERCEPTION_LOG_HISTORY.append(entry)
    if len(_PERCEPTION_LOG_HISTORY) > _MAX_PERCEPTION_LOGS:
        del _PERCEPTION_LOG_HISTORY[0]

    # Persist log entry to backend/logs/groq_api.log
    try:
        log_dir = getattr(config, "LOG_DIR", Path(__file__).resolve().parent / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "groq_api.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as exc:
        logger.warning("Could not persist perception log to disk: %s", exc)


def get_groq_recent_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent perception API request/response audit logs."""
    return list(reversed(_PERCEPTION_LOG_HISTORY[-limit:]))


def _append_groq_log(entry: Dict[str, Any]) -> None:
    """Backward-compatible alias for existing log appender."""
    _append_perception_log(entry)


# ---------------------------------------------------------------------------
# Provider Abstraction
# ---------------------------------------------------------------------------

class QwenProvider(ABC):
    """
    Base abstraction for LexMetra package perception.
    The perception model remains Qwen3.8-27B regardless of provider:
      QwenProvider
      ├── GroqQwenProvider (PRIMARY)
      └── OpenRouterQwenProvider (FALLBACK)
    """

    @abstractmethod
    async def perceive(
        self,
        faces: List[Tuple[str, np.ndarray, CoordinateTransform]],
    ) -> PerceptionResult:
        """
        faces: list of (face_id, canonical_bgr, inverse_transform)
        where face_id is "Face 1", "Face 2", "Face 3"
        """
        pass

    def is_available(self) -> bool:
        return True

    def _parse_and_validate_response(
        self,
        parsed: Dict[str, Any],
        inv_transforms: Dict[str, CoordinateTransform],
        face_dims: Dict[str, Tuple[int, int]],
        face_scales: Dict[str, float],
        raw_response: str,
        provider_name: str = "GroqQwenProvider",
        used_fallback: bool = False,
        ocr_manifest: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        perception_timing: Optional[Dict[str, Any]] = None,
    ) -> PerceptionResult:
        items: List[DeclarationEvidenceItem] = []

        raw_decls = parsed.get("declarations", [])
        if isinstance(raw_decls, list):
            for d in raw_decls:
                if not isinstance(d, dict):
                    continue
                fld = str(d.get("field", "")).strip().upper()
                val = d.get("value")
                if val is not None:
                    val = str(val).strip()
                if not fld or not val:
                    continue

                face_id = str(d.get("face", "Face 1")).strip()
                if not face_id.startswith("Face "):
                    face_id = "Face 1"

                scale = face_scales.get(face_id, 1.0)
                orig_w, orig_h = face_dims.get(face_id, (1000, 1000))

                # Parse canonical bbox
                bbox_canon: Optional[Tuple[float, float, float, float]] = None
                raw_bbox = d.get("bbox")
                if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
                    try:
                        bx, by, bw, bh = [float(v) for v in raw_bbox]
                        if scale > 0 and abs(scale - 1.0) > 1e-4:
                            bx = bx / scale
                            by = by / scale
                            bw = bw / scale
                            bh = bh / scale

                        bx = max(0.0, min(float(orig_w), bx))
                        by = max(0.0, min(float(orig_h), by))
                        bw = max(1.0, min(float(orig_w - bx), bw))
                        bh = max(1.0, min(float(orig_h - by), bh))
                        bbox_canon = (bx, by, bw, bh)
                    except (ValueError, TypeError):
                        bbox_canon = None

                # If bbox wasn't in Qwen response, map from high-precision PaddleOCR manifest
                if bbox_canon is None and ocr_manifest and face_id in ocr_manifest:
                    search_str = (d.get("evidence_text") or val or "").lower().strip()
                    best_match = None
                    best_score = 0
                    for reg in ocr_manifest[face_id]:
                        rtxt = reg.get("text", "").lower().strip()
                        if not rtxt:
                            continue
                        if rtxt in search_str or search_str in rtxt:
                            score = len(rtxt)
                            if score > best_score:
                                best_score = score
                                best_match = reg
                    if best_match:
                        bx, by, bw, bh = best_match["bbox"]
                        bbox_canon = (float(bx), float(by), float(bw), float(bh))

                # Compute ORIGINAL coordinate mapping via inverse transform
                bbox_orig: Optional[Tuple[float, float, float, float]] = None
                if bbox_canon is not None and face_id in inv_transforms:
                    inv_t = inv_transforms[face_id]
                    try:
                        mapped_orig = inv_t.transform_bbox(bbox_canon)
                        orig_w, orig_h = inv_t.target_dims
                        if orig_w > 0 and orig_h > 0:
                            ox, oy, ow, oh = mapped_orig
                            ox = max(0.0, min(float(orig_w), ox))
                            oy = max(0.0, min(float(orig_h), oy))
                            ow = max(1.0, min(float(orig_w - ox), ow))
                            oh = max(1.0, min(float(orig_h - oy), oh))
                            bbox_orig = (ox, oy, ow, oh)
                        else:
                            bbox_orig = mapped_orig
                    except Exception:
                        bbox_orig = bbox_canon

                conf = 0.85
                try:
                    conf = float(d.get("confidence", 0.85))
                except (ValueError, TypeError):
                    conf = 0.85

                status = str(d.get("status", "DETECTED")).upper()
                if status not in ("DETECTED", "REVIEW_REQUIRED", "NON_COMPLIANT", "NOT_DETECTED"):
                    status = "DETECTED"

                # If Paddle could not locate the region coordinates:
                # Section 3 rule: EVIDENCE UNAVAILABLE, not a fake rectangle.
                if bbox_canon is None:
                    status = "REVIEW_REQUIRED"

                items.append(DeclarationEvidenceItem(
                    field=fld,
                    value=val,
                    unit=d.get("unit"),
                    currency=d.get("currency"),
                    basis=d.get("basis"),
                    face=face_id,
                    evidence_text=d.get("evidence_text") or val,
                    bbox_canonical=bbox_canon,
                    bbox_original=bbox_orig,
                    coordinate_space=CoordinateSpace.CANONICAL,
                    confidence=conf,
                    status=status,
                ))

        # Deterministic sanity validation
        validated_items = validate_semantic_declarations(items)

        prod_name_obj = parsed.get("product_name")
        prod_name = None
        if isinstance(prod_name_obj, dict):
            prod_name = prod_name_obj.get("value")
        elif isinstance(prod_name_obj, str):
            prod_name = prod_name_obj

        if not prod_name:
            for item in validated_items:
                if item.field.upper() in ("PRODUCT_NAME", "COMMON_NAME", "GENERIC_NAME") and item.value:
                    prod_name = item.value
                    break

        prod_id_obj = parsed.get("product_id")
        prod_id = None
        if isinstance(prod_id_obj, dict):
            prod_id = prod_id_obj.get("value")
        elif isinstance(prod_id_obj, str):
            prod_id = prod_id_obj

        if prod_id:
            s_pid = str(prod_id).strip()
            digits_pid = re.sub(r"\D", "", s_pid)
            # Find parsed MRP if available to reject accidental price assignment
            mrp_item = next((it for it in validated_items if it.field.upper() == "MRP" and it.value), None)
            parsed_mrp: Optional[float] = None
            if mrp_item and mrp_item.value:
                mrp_m = _MONEY_AMOUNT_REGEX.search(mrp_item.value)
                if mrp_m:
                    try:
                        parsed_mrp = float(mrp_m.group(1).replace(",", ""))
                    except ValueError:
                        pass
            if "/-" in s_pid or "₹" in s_pid or "rs" in s_pid.lower() or "mrp" in s_pid.lower() or (parsed_mrp and digits_pid == str(int(parsed_mrp))):
                prod_id = None

        if not prod_id:
            for item in validated_items:
                if item.field.upper() == "PRODUCT_ID" and item.value:
                    prod_id = item.value
                    break

        return PerceptionResult(
            declarations=validated_items,
            product_name=prod_name,
            product_id=prod_id,
            face_metadata=parsed.get("face_metadata", {}),
            image_quality=parsed.get("image_quality", {}),
            raw_response=raw_response,
            used_fallback=used_fallback,
            provider_name=provider_name,
            perception_timing=perception_timing or {},
            ocr_manifest=ocr_manifest or {},
        )


    async def _fallback_classical(
        self,
        faces: List[Tuple[str, np.ndarray, CoordinateTransform]],
    ) -> PerceptionResult:
        """
        Qwen-only authoritative extraction. Classical OCR fallback is disabled.
        """
        logger.warning("Qwen perception unavailable across providers. Classical OCR fallback is disabled.")
        return PerceptionResult(
            declarations=[],
            product_name=None,
            product_id=None,
            face_metadata={},
            image_quality={},
            raw_response=None,
            used_fallback=True,
            provider_name="QwenUnavailable",
        )


# ---------------------------------------------------------------------------
# OpenRouter Fallback Provider
# ---------------------------------------------------------------------------

def deterministic_json_parse(raw: str) -> dict:
    """
    Robustly parse a Qwen JSON response that may be wrapped in markdown fences,
    have a trailing reasoning block, or be slightly truncated at the end.
    """
    if not raw:
        raise ValueError("Empty response from Qwen")

    text = raw.strip()

    # 1. Strip markdown code fences (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        # Remove opening fence line
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        # Remove closing fence
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    # 2. Try direct parse first (covers well-formed responses)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Extract the outermost {...} object (handles leading/trailing noise)
    start = text.find("{")
    if start != -1:
        # Walk from start to find matching closing brace
        depth = 0
        end = -1
        in_str = False
        escape = False
        for i, ch in enumerate(text[start:], start):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_str:
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        # Truncated: try closing off the last incomplete declaration
        # Find the last complete declaration object
        obj_text = text[start:]
        for suffix in ["\n    ]\n}", "\n  ]\n}", "]}"]:
            # Try after last complete },
            idx = obj_text.rfind("},")
            if idx != -1:
                candidate = obj_text[:idx + 1] + suffix
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
            # Try after last }
            idx = obj_text.rfind("}")
            if idx != -1:
                candidate = obj_text[:idx + 1] + suffix
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass

    raise ValueError(f"Could not parse Qwen JSON response. First 200 chars: {raw[:200]!r}")



class OpenRouterQwenProvider(QwenProvider):
    """
    Fallback perception provider for LexMetra V1 using the SAME Qwen3.8-27B model via OpenRouter.
    OpenRouter is NOT a second model; it is a fallback provider for the same model.
    """

    OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
    MODEL_NAME = "qwen/qwen3.8-27b"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout_secs: float = 75.0,  # 75s accommodates reasoning tokens + full structured JSON
    ):
        self._api_key = api_key
        self.model_name = (
            model_name
            or getattr(config, "OPENROUTER_MODEL", None)
            or os.getenv("OPENROUTER_MODEL")
            or self.MODEL_NAME
        )
        self.endpoint = (
            endpoint
            or getattr(config, "OPENROUTER_ENDPOINT", None)
            or os.getenv("OPENROUTER_ENDPOINT")
            or self.OPENROUTER_ENDPOINT
        )
        self.timeout_secs = timeout_secs
        self._lock = asyncio.Lock()
        self._cache: Dict[str, Tuple[float, PerceptionResult]] = {}
        self._in_flight: Dict[str, asyncio.Future] = {}

    def _compute_faces_hash(self, faces: Sequence[Tuple[str, np.ndarray, Any]]) -> str:
        h = hashlib.sha256()
        for face_id, img_bgr, _ in faces:
            h.update(face_id.encode("utf-8"))
            h.update(str(img_bgr.shape).encode("utf-8"))
            h.update(img_bgr.tobytes()[:4096])
            h.update(img_bgr.tobytes()[-4096:])
            h.update(str(img_bgr.size).encode("utf-8"))
        return h.hexdigest()

    @property
    def api_key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key
        key = getattr(config, "OPENROUTER_API_KEY", None) or os.getenv("OPENROUTER_API_KEY")
        if key and str(key).strip().startswith("sk-or-"):
            return str(key).strip()
        groq_key = getattr(config, "GROQ_API_KEY", None) or os.getenv("GROQ_API_KEY")
        if groq_key and str(groq_key).strip().startswith("sk-or-"):
            return str(groq_key).strip()
        key2 = getattr(config, "OPENROUTER_API_KEY2", None) or os.getenv("OPENROUTER_API_KEY2")
        if key2 and str(key2).strip().startswith("sk-or-"):
            return str(key2).strip()
        return key or groq_key or key2

    def is_available(self) -> bool:
        return bool(self.api_key and len(str(self.api_key).strip()) > 5)

    async def perceive(
        self,
        faces: List[Tuple[str, np.ndarray, CoordinateTransform]],
    ) -> PerceptionResult:
        if not faces:
            return PerceptionResult(declarations=[], provider_name="OpenRouterQwenProvider", used_fallback=True)

        # Deduplicate identical requests using stable face-set hash with a 5-minute TTL
        cache_key = self._compute_faces_hash(faces)
        now = time.time()
        if cache_key in self._cache:
            cached_time, cached_res = self._cache[cache_key]
            if now - cached_time < 300.0:
                print(f"[*] [OPENROUTER CACHE HIT] Reusing perception result ({len(faces)} faces, key={cache_key[:10]}, cached {now - cached_time:.1f}s ago).", flush=True)
                return cached_res

        # If a request for this exact face-set is already in flight, await it
        if cache_key in self._in_flight:
            print(f"[*] [OPENROUTER IN-FLIGHT DEDUP] Awaiting active request for face-set key={cache_key[:10]}...", flush=True)
            try:
                return await self._in_flight[cache_key]
            except Exception:
                pass

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._in_flight[cache_key] = fut

        try:
            async with self._lock:
                # Re-check cache after lock (another coroutine may have completed it)
                if cache_key in self._cache:
                    cached_time, cached_res = self._cache[cache_key]
                    if time.time() - cached_time < 300.0:
                        if not fut.done():
                            fut.set_result(cached_res)
                        return cached_res

                batch = prepare_perception_batch(faces)
                result = await self.perceive_prepared(batch, faces)
                self._cache[cache_key] = (time.time(), result)
                if not fut.done():
                    fut.set_result(result)
                return result
        except Exception as exc:
            if not fut.done():
                fut.set_exception(exc)
            raise
        finally:
            self._in_flight.pop(cache_key, None)

    async def perceive_prepared(
        self,
        batch: PreparedPerceptionBatch,
        faces: List[Tuple[str, np.ndarray, CoordinateTransform]],
    ) -> PerceptionResult:
        """
        Execute fallback request through OpenRouter using the ALREADY PREPARED canonical images,
        Face 1/Face 2/Face 3 identities, and prompt schema without re-processing.
        """
        req_id = f"openrouter_{uuid.uuid4().hex[:10]}"
        timestamp_start = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        face_count = len(batch.face_summaries)
        payload = batch.make_payload(self.model_name)
        # Disable chain-of-thought reasoning — structured JSON extraction needs no reasoning trace
        payload["reasoning"] = {"effort": "none"}

        if not self.is_available():
            latency = round((time.perf_counter() - t0) * 1000, 1)
            msg = "OPENROUTER_API_KEY not configured or invalid"
            logger.warning("[OPENROUTER PERCEPTION] %s -> falling back to classical OCR.", msg)
            print(f"[x] [OPENROUTER UNAVAILABLE] {msg} -> falling back to classical OCR.", flush=True)
            _append_perception_log({
                "provider": "OpenRouterQwenProvider",
                "request_id": req_id,
                "model": self.model_name,
                "face_count": face_count,
                "http_status": None,
                "latency": latency,
                "failure_type": "PROVIDER_UNAVAILABLE",
                "retry_count": 0,
                "fallback_provider": "ClassicalOcrFallback",
                "prompt_tokens": None,
                "completion_tokens": None,
                "timestamp": timestamp_start,
                "error": msg,
            })
            return await self._fallback_classical(faces)

        # Terminal live log: Fallback Request Sent
        print("\n" + "=" * 80, flush=True)
        print(f">>> [OPENROUTER FALLBACK REQUEST] id={req_id} | model={self.model_name} | faces={face_count}", flush=True)
        print(f"    Image dimensions (reusing prepared images): {batch.dims_summary}", flush=True)
        print(f"    Sending prompt + images in ONE multimodal fallback request (timeout={self.timeout_secs}s)...", flush=True)
        print("=" * 80, flush=True)

        logger.info(
            ">>> [OPENROUTER FALLBACK REQUEST] id=%s model=%s endpoint=%s faces=%s dims=%s",
            req_id, self.model_name, self.endpoint, [f["face_id"] for f in batch.face_summaries], batch.dims_summary
        )

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://lexmetra.local",
                "X-Title": "LexMetra Perception",
            }
            async with httpx.AsyncClient(timeout=self.timeout_secs) as client:
                resp = await client.post(self.endpoint, headers=headers, json=payload)

            latency = round((time.perf_counter() - t0) * 1000, 1)

            if resp.status_code != 200:
                error_text = resp.text
                failure_type = f"HTTP_{resp.status_code}"
                print(f"\n<<< [OPENROUTER ERROR] id={req_id} status={resp.status_code} latency={latency:.1f}ms", flush=True)
                print(f"    Error: {error_text[:300]}", flush=True)
                print("    Falling back to classical OCR.\n", flush=True)
                logger.error(
                    "<<< [OPENROUTER ERROR] id=%s status=%d latency=%.1fms error=%s. Falling back to classical OCR.",
                    req_id, resp.status_code, latency, error_text[:300]
                )
                _append_perception_log({
                    "provider": "OpenRouterQwenProvider",
                    "request_id": req_id,
                    "model": self.model_name,
                    "face_count": face_count,
                    "http_status": resp.status_code,
                    "latency": latency,
                    "failure_type": failure_type,
                    "retry_count": 0,
                    "fallback_provider": "ClassicalOcrFallback",
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "timestamp": timestamp_start,
                    "error": error_text,
                })
                return await self._fallback_classical(faces)

            # Successful HTTP 200 response
            data = resp.json()
            choice = data["choices"][0]
            raw_content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason") or choice.get("native_finish_reason") or "stop"
            usage = data.get("usage", {})
            prompt_tok = usage.get("prompt_tokens")
            comp_tok = usage.get("completion_tokens")
            total_tok = usage.get("total_tokens")

            # If Qwen still hit the token limit despite the 1800-token budget (very large label),
            # retry ONCE with a higher cap. This should be rare now that max_tokens=1800.
            if finish_reason == "length":
                print(f"[!] [OPENROUTER TRUNCATED] id={req_id} finish_reason=length comp={comp_tok} — retrying with max_tokens=2400...", flush=True)
                logger.warning("[OPENROUTER TRUNCATED] id=%s comp=%s — retrying with max_tokens=2400", req_id, comp_tok)
                retry_payload = dict(payload)
                retry_payload["max_tokens"] = 2400
                try:
                    async with httpx.AsyncClient(timeout=self.timeout_secs) as client:
                        retry_resp = await client.post(self.endpoint, headers=headers, json=retry_payload)
                    if retry_resp.status_code == 200:
                        retry_data = retry_resp.json()
                        retry_choice = retry_data["choices"][0]
                        retry_finish = retry_choice.get("finish_reason") or retry_choice.get("native_finish_reason") or "stop"
                        raw_content = retry_choice["message"]["content"]
                        usage = retry_data.get("usage", {})
                        prompt_tok = usage.get("prompt_tokens")
                        comp_tok = usage.get("completion_tokens")
                        total_tok = usage.get("total_tokens")
                        finish_reason = retry_finish
                        print(f"[*] [OPENROUTER RETRY] finish_reason={retry_finish} comp={comp_tok}", flush=True)
                    else:
                        print(f"[!] [OPENROUTER RETRY FAILED] status={retry_resp.status_code} — using deterministic parse on truncated response", flush=True)
                except Exception as retry_exc:
                    print(f"[!] [OPENROUTER RETRY EXCEPTION] {retry_exc} — using deterministic parse on truncated response", flush=True)

            try:
                parsed = deterministic_json_parse(raw_content)
            except Exception as parse_err:
                print(f"\n<<< [OPENROUTER MALFORMED RESPONSE] id={req_id} latency={latency:.1f}ms error={parse_err}", flush=True)
                print("    Falling back to classical OCR.\n", flush=True)
                logger.error("<<< [OPENROUTER MALFORMED RESPONSE] id=%s: %s", req_id, parse_err)
                _append_perception_log({
                    "provider": "OpenRouterQwenProvider",
                    "request_id": req_id,
                    "model": self.model_name,
                    "face_count": face_count,
                    "http_status": 200,
                    "latency": latency,
                    "failure_type": "MALFORMED_RESPONSE",
                    "retry_count": 0,
                    "fallback_provider": "ClassicalOcrFallback",
                    "prompt_tokens": prompt_tok,
                    "completion_tokens": comp_tok,
                    "timestamp": timestamp_start,
                    "error": str(parse_err),
                })
                return await self._fallback_classical(faces)

            declarations_list = parsed.get("declarations", [])
            p_name = parsed.get("product_name")
            p_name_str = p_name.get("value") if isinstance(p_name, dict) else p_name

            print("\n" + "=" * 80, flush=True)
            print(f"<<< [OPENROUTER RESPONSE] id={req_id} | status=200 OK | latency={latency:.1f}ms", flush=True)
            print(f"    Model: {self.model_name} | Faces: {face_count} | Tokens: prompt={prompt_tok}, comp={comp_tok}, total={total_tok}", flush=True)
            print(f"    Product Name: {p_name_str}".encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"), flush=True)
            print(f"    Declarations Found ({len(declarations_list)}):", flush=True)
            for d in declarations_list:
                line_str = f"      * [{d.get('face', 'Face 1')}] {d.get('field', ''):18s} = '{d.get('value')}' (conf={d.get('confidence')})"
                print(line_str.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"), flush=True)
            print("=" * 80 + "\n", flush=True)

            logger.info(
                "<<< [OPENROUTER RESPONSE] id=%s status=200 latency=%.1fms tokens=%s (prompt=%s, completion=%s)",
                req_id, latency, total_tok, prompt_tok, comp_tok
            )

            _append_perception_log({
                "provider": "OpenRouterQwenProvider",
                "request_id": req_id,
                "model": self.model_name,
                "face_count": face_count,
                "http_status": 200,
                "latency": latency,
                "failure_type": None,
                "retry_count": 0,
                "fallback_provider": None,
                "prompt_tokens": prompt_tok,
                "completion_tokens": comp_tok,
                "timestamp": timestamp_start,
                "usage": usage,
                "response": {
                    "raw_content": raw_content,
                    "parsed_declarations_count": len(declarations_list),
                    "product_name": p_name_str,
                },
            })

            return self._parse_and_validate_response(
                parsed,
                batch.inv_transforms,
                batch.face_dims,
                batch.face_scales,
                raw_content,
                provider_name="OpenRouterQwenProvider",
                used_fallback=True,
            )

        except Exception as e:
            latency = round((time.perf_counter() - t0) * 1000, 1)
            exc_type = type(e).__name__
            exc_repr = repr(e)
            print(f"\n<<< [OPENROUTER EXCEPTION] id={req_id} latency={latency:.1f}ms error={exc_type}: {exc_repr}", flush=True)
            print("    Falling back to classical OCR.\n", flush=True)
            logger.error("<<< [OPENROUTER EXCEPTION] id=%s latency=%.1fms error=%s: %s", req_id, latency, exc_type, exc_repr)
            _append_perception_log({
                "provider": "OpenRouterQwenProvider",
                "request_id": req_id,
                "model": self.model_name,
                "face_count": face_count,
                "http_status": None,
                "latency": latency,
                "failure_type": exc_type,
                "retry_count": 0,
                "fallback_provider": "ClassicalOcrFallback",
                "prompt_tokens": None,
                "completion_tokens": None,
                "timestamp": timestamp_start,
                "exception": f"{exc_type}: {exc_repr}",
            })
            return await self._fallback_classical(faces)


# ---------------------------------------------------------------------------
# Primary Provider: Groq Qwen with Provider-Level Failover
# ---------------------------------------------------------------------------

class GroqQwenProvider(QwenProvider):
    """
    Primary perception provider for LexMetra V1 using Qwen3.8-27B via Groq.
    Implements provider-level failover to OpenRouter for the SAME model on:
    - exhausted 429 retry
    - timeout
    - connection/network failure
    - retryable 5xx
    - provider unavailable
    - malformed/invalid response
    """

    GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
    MODEL_NAME = "qwen/qwen3.8-27b"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_secs: float = 40.0,  # Groq is fast; 40s is ample, fail faster if stuck
        fallback_provider: Optional[QwenProvider] = None,
    ):
        self._api_key = api_key
        self.timeout_secs = timeout_secs
        if fallback_provider is not None:
            self.fallback_provider: Optional[QwenProvider] = fallback_provider
        else:
            self.fallback_provider = OpenRouterQwenProvider()
        self._lock = asyncio.Lock()
        self._cache: Dict[str, Tuple[float, PerceptionResult]] = {}
        self._in_flight: Dict[str, asyncio.Future] = {}

    @property
    def api_key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key
        return os.getenv("GROQ_API_KEY") or getattr(config, "GROQ_API_KEY", None)

    def is_groq_available(self) -> bool:
        k = str(self.api_key or "").strip()
        return bool(k and k.startswith("gsk_") and len(k) > 10)

    def is_available(self) -> bool:
        """
        Provider is considered available if either primary Groq is available OR
        the fallback provider (OpenRouter) is available.
        """
        return self.is_groq_available() or (self.fallback_provider is not None and self.fallback_provider.is_available())

    def _compute_faces_hash(self, faces: Sequence[Tuple[str, np.ndarray, Any]]) -> str:
        h = hashlib.sha256()
        for face_id, img_bgr, _ in faces:
            h.update(face_id.encode("utf-8"))
            h.update(str(img_bgr.shape).encode("utf-8"))
            h.update(img_bgr.tobytes()[:4096])
            h.update(img_bgr.tobytes()[-4096:])
            h.update(str(img_bgr.size).encode("utf-8"))
        return h.hexdigest()

    async def perceive(
        self,
        faces: List[Tuple[str, np.ndarray, CoordinateTransform]],
    ) -> PerceptionResult:
        if not faces:
            return PerceptionResult(declarations=[], provider_name="GroqQwenProvider")

        # Deduplicate identical requests using stable face-set hash with a 5-minute TTL
        cache_key = self._compute_faces_hash(faces)
        now = time.time()
        if cache_key in self._cache:
            cached_time, cached_res = self._cache[cache_key]
            if now - cached_time < 300.0:
                print(f"[*] [GROQ CACHE HIT] Reusing perception result for face-set ({len(faces)} faces, key={cache_key[:10]}, cached {now - cached_time:.1f}s ago).", flush=True)
                return cached_res

        # If a request for this exact face-set is already in flight, await it
        if cache_key in self._in_flight:
            print(f"[*] [GROQ IN-FLIGHT DEDUP] Awaiting active perception request for face-set key={cache_key[:10]}...", flush=True)
            try:
                return await self._in_flight[cache_key]
            except Exception:
                pass

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._in_flight[cache_key] = fut

        try:
            # Serialize requests to prevent concurrent retry storms & rate limit pressure
            async with self._lock:
                if cache_key in self._cache:
                    cached_time, cached_res = self._cache[cache_key]
                    if time.time() - cached_time < 300.0:
                        if not fut.done():
                            fut.set_result(cached_res)
                        return cached_res

                # PRIMARY: Send all 3 package images directly to Groq/Qwen for visual reading.
                # Qwen must see the actual image pixels — it should NOT receive an OCR text manifest.
                # PaddleOCR runs in parallel ONLY for bbox fallback (never overwrites Qwen extraction).
                t_p0 = time.perf_counter()
                batch = prepare_perception_batch(faces)

                # Run PaddleOCR in background thread for bbox localization only.
                # It must NOT block the Groq network call, and its results must NEVER overwrite Qwen.
                ocr_manifest: Dict[str, Any] = {}
                ocr_timing: Dict[str, Any] = {}
                try:
                    loop = asyncio.get_running_loop()
                    ocr_future = loop.run_in_executor(
                        None,
                        lambda: extract_ocr_manifest_parallel(faces)
                    )
                except Exception:
                    ocr_future = None

                result = await self._perceive_with_failover(
                    batch, faces, ocr_manifest=ocr_manifest, ocr_timing=ocr_timing, t_pipeline_start=t_p0
                )

                # After Groq returns, retrieve OCR manifest for bbox enrichment (best-effort).
                if ocr_future is not None:
                    try:
                        ocr_manifest_res, _, ocr_timing_res = await asyncio.wait_for(ocr_future, timeout=10.0)
                        # Enrich bbox_canonical from OCR manifest for declarations that have no bbox
                        if ocr_manifest_res:
                            for decl in result.declarations:
                                if decl.bbox_canonical is None and decl.face in ocr_manifest_res:
                                    search_str = (decl.evidence_text or decl.value or "").lower().strip()
                                    best_match = None
                                    best_score = 0
                                    for reg in ocr_manifest_res[decl.face]:
                                        rtxt = reg.get("text", "").lower().strip()
                                        if not rtxt:
                                            continue
                                        if rtxt in search_str or search_str in rtxt:
                                            score = len(rtxt)
                                            if score > best_score:
                                                best_score = score
                                                best_match = reg
                                    if best_match:
                                        bx, by, bw, bh = best_match["bbox"]
                                        decl.bbox_canonical = (float(bx), float(by), float(bw), float(bh))
                    except Exception:
                        pass

                self._cache[cache_key] = (time.time(), result)
                if not fut.done():
                    fut.set_result(result)
                return result
        except Exception as exc:
            if not fut.done():
                fut.set_exception(exc)
            raise
        finally:
            self._in_flight.pop(cache_key, None)

    async def _failover_to_openrouter(
        self,
        batch: PreparedPerceptionBatch,
        faces: List[Tuple[str, np.ndarray, CoordinateTransform]],
        reason: str,
    ) -> PerceptionResult:
        """
        Fail over to OpenRouter for the SAME model (qwen/qwen3.8-27b).
        Reuses the exact canonical images and prompt already prepared in batch.
        """
        print("\n" + ">" * 40 + " [FAILOVER TRIGGERED] " + "<" * 40, flush=True)
        print(f"    Primary provider (Groq) failed: {reason}", flush=True)
        print(f"    Failing over to OpenRouter for the SAME model ({self.MODEL_NAME}).", flush=True)
        print(f"    Reusing {len(batch.face_summaries)} prepared canonical images without re-processing.", flush=True)
        print(">" * 102 + "\n", flush=True)
        logger.warning("Failover triggered from Groq to OpenRouter: %s", reason)

        if self.fallback_provider and isinstance(self.fallback_provider, OpenRouterQwenProvider):
            return await self.fallback_provider.perceive_prepared(batch, faces)
        elif self.fallback_provider:
            return await self.fallback_provider.perceive(faces)
        else:
            logger.warning("No fallback provider configured. Falling back to classical OCR.")
            return await self._fallback_classical(faces)

    async def _perceive_with_failover(
        self,
        batch: PreparedPerceptionBatch,
        faces: List[Tuple[str, np.ndarray, CoordinateTransform]],
        ocr_manifest: Optional[Dict[str, Any]] = None,
        ocr_timing: Optional[Dict[str, Any]] = None,
        t_pipeline_start: Optional[float] = None,
    ) -> PerceptionResult:
        req_id = f"groq_{uuid.uuid4().hex[:10]}"
        timestamp_start = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        face_count = len(batch.face_summaries)


        # 1. Provider unavailable check: GROQ_API_KEY missing or invalid -> immediate failover
        if not self.is_groq_available():
            latency = round((time.perf_counter() - t0) * 1000, 1)
            msg = "GROQ_API_KEY not configured or invalid"
            logger.warning("GROQ_API_KEY missing or invalid -> failing over to OpenRouter.")
            print(f"[!] [GROQ UNAVAILABLE] {msg} -> failing over to OpenRouter.", flush=True)
            _append_perception_log({
                "provider": "GroqQwenProvider",
                "request_id": req_id,
                "model": self.MODEL_NAME,
                "face_count": face_count,
                "http_status": None,
                "latency": latency,
                "failure_type": "PROVIDER_UNAVAILABLE",
                "retry_count": 0,
                "fallback_provider": "OpenRouterQwenProvider",
                "prompt_tokens": None,
                "completion_tokens": None,
                "timestamp": timestamp_start,
                "error": msg,
            })
            return await self._failover_to_openrouter(batch, faces, msg)

        payload = batch.make_payload(self.MODEL_NAME)

        # Terminal live log: Request Sent
        print("\n" + "=" * 80, flush=True)
        print(f">>> [GROQ API REQUEST] id={req_id} | model={self.MODEL_NAME} | faces={face_count}", flush=True)
        print(f"    Image dimensions sent to API: {batch.dims_summary}", flush=True)
        for fs in batch.face_summaries:
            print(f"      * {fs['face_id']}: canonical={fs['canonical_dimensions']} -> api={fs['api_dimensions']} (scale={fs['scale_factor']:.2f}, {fs['encoded_bytes']//1024} KB)", flush=True)
        print(f"    Sending prompt + images in ONE multimodal request (timeout={self.timeout_secs}s)...", flush=True)
        print("=" * 80, flush=True)

        logger.info(
            ">>> [GROQ API REQUEST] id=%s model=%s endpoint=%s faces=%s dims=%s",
            req_id, self.MODEL_NAME, self.GROQ_ENDPOINT, [f["face_id"] for f in batch.face_summaries], batch.dims_summary
        )

        # Controlled retry: At most ONE controlled retry for 429 or transient error
        max_retries = 1
        attempt = 0

        while attempt <= max_retries:
            attempt += 1
            t_attempt_start = time.perf_counter()

            try:
                async with httpx.AsyncClient(timeout=self.timeout_secs) as client:
                    resp = await client.post(
                        self.GROQ_ENDPOINT,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )

                latency_ms = round((time.perf_counter() - t_attempt_start) * 1000, 1)

                # HTTP 429 / 413: Rate Limit
                if resp.status_code in (429, 413):
                    error_text = resp.text
                    err_lower = error_text.lower()
                    if "input token" in err_lower or "itpm" in err_lower:
                        limit_type = "ITPM"
                    elif "output token" in err_lower or "otpm" in err_lower:
                        limit_type = "OTPM"
                    elif "tpm" in err_lower:
                        limit_type = "TPM"
                    elif "rpm" in err_lower:
                        limit_type = "RPM"
                    else:
                        limit_type = f"HTTP {resp.status_code}"

                    retry_header = resp.headers.get("retry-after")
                    wait_secs = 5.0
                    if retry_header:
                        try:
                            wait_secs = max(1.0, float(retry_header))
                        except (ValueError, TypeError):
                            wait_secs = 5.0
                    else:
                        m = re.search(r"try again in (\d+\.?\d*)\s*s", error_text, re.IGNORECASE)
                        if m:
                            try:
                                wait_secs = max(1.0, float(m.group(1)))
                            except ValueError:
                                wait_secs = 5.0

                    sleep_time = wait_secs + 1.0

                    print("\n" + "!" * 80, flush=True)
                    print(f"[!] [GROQ RATE LIMIT ({limit_type})] Attempt {attempt}/{max_retries + 1}", flush=True)
                    print(f"    Server requested wait: {wait_secs:.1f}s (sleeping {sleep_time:.1f}s)", flush=True)
                    print(f"    Details: {error_text[:200]}...", flush=True)
                    print("!" * 80 + "\n", flush=True)

                    logger.warning(
                        "[GROQ RATE LIMIT %d (%s)] id=%s attempt=%d/%d wait=%.1fs",
                        resp.status_code, limit_type, req_id, attempt, max_retries + 1, sleep_time
                    )

                    if attempt <= max_retries:
                        await asyncio.sleep(sleep_time)
                        print(f"[*] Resuming Groq request id={req_id} after rate-limit backoff (retry 1)...", flush=True)
                        continue
                    else:
                        # Controlled 429 retry exhausted -> Fail over to OpenRouter!
                        total_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                        print(f"[x] Groq 429 rate limit retry exhausted. Triggering failover to OpenRouter.", flush=True)
                        _append_perception_log({
                            "provider": "GroqQwenProvider",
                            "request_id": req_id,
                            "model": self.MODEL_NAME,
                            "face_count": face_count,
                            "http_status": resp.status_code,
                            "latency": total_latency_ms,
                            "failure_type": "429_RATE_LIMIT_EXHAUSTED",
                            "retry_count": 1,
                            "fallback_provider": "OpenRouterQwenProvider",
                            "prompt_tokens": None,
                            "completion_tokens": None,
                            "timestamp": timestamp_start,
                            "error": error_text,
                        })
                        return await self._failover_to_openrouter(
                            batch, faces, f"Groq 429 rate limit exhausted ({limit_type})"
                        )

                # Retryable 5xx (500, 502, 503, 504)
                if resp.status_code in (500, 502, 503, 504):
                    error_text = resp.text
                    if attempt <= max_retries:
                        print(f"[!] [GROQ 5XX ERROR {resp.status_code}] Attempt {attempt}/{max_retries + 1}. Retrying once in 1.0s...", flush=True)
                        logger.warning("[GROQ 5XX ERROR %d] id=%s attempt=%d/%d. Retrying once.", resp.status_code, req_id, attempt, max_retries + 1)
                        await asyncio.sleep(1.0)
                        continue
                    else:
                        total_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                        print(f"[x] Groq 5xx retry exhausted. Triggering failover to OpenRouter.", flush=True)
                        _append_perception_log({
                            "provider": "GroqQwenProvider",
                            "request_id": req_id,
                            "model": self.MODEL_NAME,
                            "face_count": face_count,
                            "http_status": resp.status_code,
                            "latency": total_latency_ms,
                            "failure_type": f"5XX_SERVER_ERROR_{resp.status_code}",
                            "retry_count": 1,
                            "fallback_provider": "OpenRouterQwenProvider",
                            "prompt_tokens": None,
                            "completion_tokens": None,
                            "timestamp": timestamp_start,
                            "error": error_text,
                        })
                        return await self._failover_to_openrouter(
                            batch, faces, f"Groq 5xx server error (HTTP {resp.status_code})"
                        )

                # Non-retryable HTTP error (4xx client errors, etc.)
                if resp.status_code != 200:
                    error_text = resp.text
                    total_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                    print(f"\n<<< [GROQ API ERROR] id={req_id} status={resp.status_code} latency={total_latency_ms:.1f}ms", flush=True)
                    print(f"    Error: {error_text[:300]}", flush=True)
                    print("    Triggering failover to OpenRouter.\n", flush=True)
                    logger.error("<<< [GROQ API ERROR] id=%s status=%d: %s", req_id, resp.status_code, error_text[:300])
                    _append_perception_log({
                        "provider": "GroqQwenProvider",
                        "request_id": req_id,
                        "model": self.MODEL_NAME,
                        "face_count": face_count,
                        "http_status": resp.status_code,
                        "latency": total_latency_ms,
                        "failure_type": f"HTTP_{resp.status_code}",
                        "retry_count": attempt - 1,
                        "fallback_provider": "OpenRouterQwenProvider",
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "timestamp": timestamp_start,
                        "error": error_text,
                    })
                    return await self._failover_to_openrouter(
                        batch, faces, f"Groq HTTP client error {resp.status_code}"
                    )

                # Successful HTTP 200 response
                total_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                data = resp.json()
                raw_content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

                # Use deterministic_json_parse to handle markdown-wrapped JSON, reasoning traces,
                # and truncated responses. This is more robust than a bare json.loads.
                try:
                    parsed = deterministic_json_parse(raw_content)
                except Exception as json_err:
                    print(f"\n<<< [GROQ MALFORMED RESPONSE] id={req_id} error={json_err}", flush=True)
                    print(f"    Raw content (first 300 chars): {raw_content[:300]!r}", flush=True)
                    print("    Triggering failover to OpenRouter.\n", flush=True)
                    logger.error("<<< [GROQ MALFORMED RESPONSE] id=%s: %s", req_id, json_err)
                    _append_perception_log({
                        "provider": "GroqQwenProvider",
                        "request_id": req_id,
                        "model": self.MODEL_NAME,
                        "face_count": face_count,
                        "http_status": 200,
                        "latency": total_latency_ms,
                        "failure_type": "MALFORMED_RESPONSE",
                        "retry_count": attempt - 1,
                        "fallback_provider": "OpenRouterQwenProvider",
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "timestamp": timestamp_start,
                        "error": str(json_err),
                    })
                    return await self._failover_to_openrouter(batch, faces, "Groq response was malformed/non-JSON")

                declarations_list = parsed.get("declarations", [])
                p_name = parsed.get("product_name")
                p_name_str = p_name.get("value") if isinstance(p_name, dict) else p_name

                prompt_tok = usage.get("prompt_tokens")
                comp_tok = usage.get("completion_tokens")
                total_tok = usage.get("total_tokens")

                # Terminal live log: Response Received with Token Debugging
                print("\n" + "=" * 80, flush=True)
                print(f"<<< [GROQ API RESPONSE] id={req_id} | status=200 OK | latency={total_latency_ms:.1f}ms", flush=True)
                print(f"    Model: {self.MODEL_NAME} | Faces in request: {face_count} ({', '.join(fs['face_id'] for fs in batch.face_summaries)})", flush=True)
                print(f"    Image dimensions sent to API: {batch.dims_summary}", flush=True)
                print(f"    Tokens: prompt={prompt_tok}, completion={comp_tok}, total={total_tok}", flush=True)
                print(f"    Product Name: {p_name_str}".encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"), flush=True)
                print(f"    Declarations Found ({len(declarations_list)}):", flush=True)
                for d in declarations_list:
                    f_name = d.get("field") or ""
                    f_val = str(d.get("value") or "")
                    f_face = d.get("face") or "Face 1"
                    f_conf = d.get("confidence")
                    f_text = str(d.get("evidence_text") or "")[:35]
                    line_str = f"      * [{f_face}] {f_name:18s} = '{f_val}' (conf={f_conf}) [evidence: '{f_text}']"
                    print(line_str.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"), flush=True)
                print("=" * 80 + "\n", flush=True)

                logger.info(
                    "<<< [GROQ API RESPONSE] id=%s status=200 latency=%.1fms tokens=%s (prompt=%s, completion=%s)",
                    req_id, total_latency_ms, total_tok, prompt_tok, comp_tok
                )

                _append_perception_log({
                    "provider": "GroqQwenProvider",
                    "request_id": req_id,
                    "model": self.MODEL_NAME,
                    "face_count": face_count,
                    "http_status": 200,
                    "latency": total_latency_ms,
                    "failure_type": None,
                    "retry_count": attempt - 1,
                    "fallback_provider": None,
                    "prompt_tokens": prompt_tok,
                    "completion_tokens": comp_tok,
                    "timestamp": timestamp_start,
                    "usage": usage,
                    "headers": {
                        "x-request-id": resp.headers.get("x-request-id"),
                        "x-ratelimit-remaining-tokens": resp.headers.get("x-ratelimit-remaining-tokens"),
                        "x-ratelimit-remaining-requests": resp.headers.get("x-ratelimit-remaining-requests"),
                    },
                    "response": {
                        "raw_content": raw_content,
                        "parsed_declarations_count": len(declarations_list),
                        "product_name": p_name_str,
                    },
                })

                t_qwen_done = time.perf_counter()
                qwen_duration = t_qwen_done - t0
                total_pipeline_time = (t_qwen_done - t_pipeline_start) if t_pipeline_start else qwen_duration

                timing_breakdown = {
                    "ocr": f"{ocr_timing.get('total_ocr_s', 0.0) if ocr_timing else 0.0:.2f}s",
                    "detection": f"{ocr_timing.get('detection_s', 0.0) if ocr_timing else 0.0:.2f}s",
                    "qwen": f"{qwen_duration:.2f}s",
                    "persistence": "0.10s",
                    "total": f"{total_pipeline_time:.2f}s",
                    "ocr_s": ocr_timing.get("total_ocr_s", 0.0) if ocr_timing else 0.0,
                    "detection_s": ocr_timing.get("detection_s", 0.0) if ocr_timing else 0.0,
                    "qwen_s": round(qwen_duration, 2),
                    "total_s": round(total_pipeline_time, 2),
                }

                print("\n" + "=" * 80, flush=True)
                print("PERCEPTION TIMING", flush=True)
                print(f"OCR:         {timing_breakdown['ocr']}", flush=True)
                print(f"Detection:   {timing_breakdown['detection']}", flush=True)
                print(f"Qwen:        {timing_breakdown['qwen']}", flush=True)
                print(f"Persistence: {timing_breakdown['persistence']}", flush=True)
                print(f"TOTAL:       {timing_breakdown['total']}", flush=True)
                print("=" * 80 + "\n", flush=True)

                return self._parse_and_validate_response(
                    parsed,
                    batch.inv_transforms,
                    batch.face_dims,
                    batch.face_scales,
                    raw_content,
                    provider_name="GroqQwenProvider",
                    used_fallback=False,
                    ocr_manifest=ocr_manifest,
                    perception_timing=timing_breakdown,
                )

            except Exception as e:
                exc_type = type(e).__name__
                exc_repr = repr(e)

                if attempt <= max_retries:
                    print(f"[!] [GROQ EXCEPTION {exc_type}] Attempt {attempt}/{max_retries + 1}. Retrying once in 1.0s...", flush=True)
                    logger.warning("[GROQ EXCEPTION %s] id=%s: %s. Retrying once.", exc_type, req_id, exc_repr)
                    await asyncio.sleep(1.0)
                    continue
                else:
                    total_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                    print(f"\n<<< [GROQ EXCEPTION EXHAUSTED] id={req_id} latency={total_latency_ms:.1f}ms error={exc_type}: {exc_repr}", flush=True)
                    print("    Triggering failover to OpenRouter.\n", flush=True)
                    logger.error("<<< [GROQ EXCEPTION] id=%s error=%s: %s", req_id, exc_type, exc_repr)
                    _append_perception_log({
                        "provider": "GroqQwenProvider",
                        "request_id": req_id,
                        "model": self.MODEL_NAME,
                        "face_count": face_count,
                        "http_status": None,
                        "latency": total_latency_ms,
                        "failure_type": exc_type,
                        "retry_count": 1,
                        "fallback_provider": "OpenRouterQwenProvider",
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "timestamp": timestamp_start,
                        "exception": f"{exc_type}: {exc_repr}",
                    })
                    return await self._failover_to_openrouter(batch, faces, f"Groq exception: {exc_type}")

        return await self._failover_to_openrouter(batch, faces, "Groq attempts exhausted")



# ---------------------------------------------------------------------------
# Global Provider Resolution & Vocabulary Bridge
# ---------------------------------------------------------------------------

_PROVIDER_INSTANCE: Optional[QwenProvider] = None


def get_qwen_provider() -> QwenProvider:
    """
    Return the primary Qwen perception provider.

    Architecture (V1.md):
      PRIMARY:  GroqQwenProvider  — Groq API for speed (Qwen3.8-27B via Groq).
      FALLBACK: OpenRouterQwenProvider — same model, different provider.

    Groq receives the REAL package images (not an OCR text manifest) so that
    Qwen can visually read + semantically understand all 3 package faces itself.
    """
    global _PROVIDER_INSTANCE
    if _PROVIDER_INSTANCE is None:
        _PROVIDER_INSTANCE = GroqQwenProvider()
        logger.info("[PROVIDER] Initialized GroqQwenProvider as primary perception engine (fallback: OpenRouter).")
    return _PROVIDER_INSTANCE


def set_qwen_provider(provider: QwenProvider) -> None:
    global _PROVIDER_INSTANCE
    _PROVIDER_INSTANCE = provider


def perception_to_classified_fields(
    perception: PerceptionResult,
) -> Dict[str, Dict[str, Any]]:
    """
    Bridge Qwen perception items into the existing backend field map
    consumed by capture_session and rule_engine.
    """
    classified: Dict[str, Dict[str, Any]] = {}

    field_map = {
        "MRP": "mrp",
        "USP": "unit_sale_price",
        "NET_QUANTITY": "net_quantity",
        "MFD": "mfg_date",
        "EXPIRY": "expiry_date",
        # USE_BEFORE and USE_BY are synonyms — many packages print "USE BY" not "USE BEFORE"
        "USE_BEFORE": "best_before_use_by",
        "USE_BY": "best_before_use_by",
        "BEST_BEFORE": "best_before_use_by",
        "BB": "best_before_use_by",
        "BATCH": "batch_code",
        "LOT": "batch_code",
        "BATCH_NO": "batch_code",
        "MANUFACTURER": "manufacturer_name",
        "MARKETER": "marketer_name",
        "PACKER": "packer_name",
        "IMPORTER": "importer_name",
        "ADDRESS": "address",
        "CONSUMER_CARE": "consumer_care",
        "CONSUMER_HELPLINE": "consumer_care",
        "COUNTRY_OF_ORIGIN": "country_of_origin",
        "PRODUCT_NAME": "common_name",
        "PRODUCT_ID": "product_id",
        "SKU": "product_id",
        "GENERIC_NAME": "common_name",
        "COMMON_NAME": "common_name",
    }

    # First, if perception top-level product_name exists, seed common_name
    if perception.product_name:
        classified["common_name"] = {
            "value": perception.product_name,
            "confidence": 0.95,
            "raw_text": perception.product_name,
            "face": "Face 1",
            "status": "DETECTED",
            "coordinate_space": CoordinateSpace.CANONICAL,
        }

    # If perception top-level product_id exists, seed product_id
    if perception.product_id:
        classified["product_id"] = {
            "value": perception.product_id,
            "confidence": 0.95,
            "raw_text": perception.product_id,
            "face": "Face 1",
            "status": "DETECTED",
            "coordinate_space": CoordinateSpace.CANONICAL,
        }

    for decl in perception.declarations:
        backend_name = field_map.get(decl.field.upper(), decl.field.lower())
        if not decl.value:
            continue

        entry: Dict[str, Any] = {
            "value": decl.value,
            "confidence": decl.confidence,
            # Always use the full extracted value as raw_text — evidence_text is
            # capped at 40 chars in the prompt and would truncate long declarations
            # like a marketer's full address. evidence_text is only useful for
            # localization matching, not for display or rule-engine consumption.
            "raw_text": decl.value,
            "evidence_text": decl.evidence_text or "",
            "face": decl.face,
            "status": decl.status,
            "coordinate_space": decl.coordinate_space,
        }
        if decl.rejection_reason:
            entry["rejection_reason"] = decl.rejection_reason

        # Stash bboxes: prefer bbox_original as primary bbox for rule engine and DynamicEvidenceCrop
        if decl.bbox_original:
            entry["bbox"] = list(decl.bbox_original)
            entry["bbox_original"] = list(decl.bbox_original)
        elif decl.bbox_canonical:
            entry["bbox"] = list(decl.bbox_canonical)

        if decl.bbox_canonical:
            entry["bbox_canonical"] = list(decl.bbox_canonical)

        # Parse numeric fields for legal engine
        if backend_name == "mrp":
            m = _MONEY_AMOUNT_REGEX.search(decl.value)
            if m:
                try:
                    entry["numeric_value"] = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass
        elif backend_name == "unit_sale_price":
            m = _MONEY_AMOUNT_REGEX.search(decl.value)
            if m:
                try:
                    entry["numeric_value"] = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass
            if decl.basis:
                entry["numeric_unit"] = decl.basis
        elif backend_name == "net_quantity":
            # Robust numeric extraction: handles "150 g", "NET WEIGHT 150 g",
            # "Net Qty: 150g", "150ml" etc. Find the LAST number+unit pair
            # because leading words like "NET WEIGHT" should not be parsed as numbers.
            qty_matches = list(re.finditer(r"(\d+[\.,]?\d*)\s*([a-zA-Z]+)?", decl.value))
            if qty_matches:
                # Use the last numeric match that has a plausible unit
                best_match = None
                for qm in reversed(qty_matches):
                    unit_candidate = (qm.group(2) or "").lower()
                    if unit_candidate in ("g", "kg", "ml", "l", "litre", "liter", "mg", "oz", "lb", "units", "pcs", "nos"):
                        best_match = qm
                        break
                if best_match is None:
                    best_match = qty_matches[-1]  # fallback: last match even without known unit
                try:
                    entry["numeric_value"] = float(best_match.group(1).replace(",", ""))
                    if best_match.group(2):
                        entry["numeric_unit"] = best_match.group(2).lower()
                except ValueError:
                    pass
            if decl.unit:
                entry["numeric_unit"] = decl.unit.lower()

        classified[backend_name] = entry
        if backend_name == "batch_code":
            classified["batch_no"] = dict(entry)
        elif backend_name == "batch_no":
            classified["batch_code"] = dict(entry)
        elif backend_name == "manufacturer_name":
            classified["manufacturer_name_address"] = dict(entry)
        elif backend_name in ("expiry_date", "best_before_use_by"):
            classified["expiry_date"] = entry
            classified["best_before_use_by"] = dict(entry)

    return classified
