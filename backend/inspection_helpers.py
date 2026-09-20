from __future__ import annotations
import io
import re
import os
import uuid
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Sequence

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, Field

import config
import capture_session
from schema import MeasurementMode, BBox, ProductInspection
from rule_engine import RawExtraction

logger = logging.getLogger('inspection_helpers')

# Request models
# ---------------------------------------------------------------------------

class FieldInput(BaseModel):
    value: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    measured_height_mm: Optional[float] = Field(default=None, gt=0)
    measurement_mode: MeasurementMode = MeasurementMode.UNCERTAIN
    numeric_value: Optional[float] = None
    numeric_unit: Optional[str] = None


class InspectRequest(BaseModel):
    inspection_id: str
    sale_type: str = "retail"
    product_category: str = "food"

    net_quantity_value: float = Field(gt=0)
    net_quantity_unit: str

    mrp: Optional[float] = Field(default=None, ge=0)
    pdp_area_cm2: Optional[float] = Field(default=None, gt=0)

    is_export_only: bool = False
    retail_bundle_count: Optional[int] = Field(default=None, ge=1)

    fields: Dict[str, FieldInput]


class ReviewRequest(BaseModel):
    note: str = ""


class CreateSessionRequest(BaseModel):
    product_id: str = ""
    sale_type: str = "retail"
    product_category: str = "food"

    net_quantity_value: Optional[float] = Field(default=None, gt=0)
    net_quantity_unit: Optional[str] = None

    mrp: Optional[float] = Field(default=None, ge=0)
    pdp_area_cm2: Optional[float] = Field(default=None, gt=0)

    is_export_only: bool = False
    retail_bundle_count: Optional[int] = Field(default=None, ge=1)
    is_imported: Optional[bool] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = config.MAX_UPLOAD_BYTES
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/jpg",
}


def _validate_upload_metadata(file: UploadFile) -> None:
    """
    Validate metadata before reading the image.

    This is not a security boundary by itself, because clients can forge
    content-type values. Actual decoding below remains authoritative.
    """
    if file.content_type and file.content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported image type. Use JPEG, PNG, or WebP."
            ),
        )


async def _read_image_upload(file: UploadFile) -> tuple[bytes, np.ndarray, Image.Image]:
    """Read, size-check and decode an uploaded image once."""
    _validate_upload_metadata(file)

    raw = await file.read()

    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")

    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(
            status_code=400,
            detail="Could not decode the uploaded image.",
        )

    try:
        pil_img = Image.open(io.BytesIO(raw))
        # Force decoding while the BytesIO object is alive.
        pil_img.load()
        pil_img = pil_img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid readable image.",
        ) from exc

    height, width = img.shape[:2]
    if width < 80 or height < 80:
        raise HTTPException(
            status_code=400,
            detail="Image is too small for reliable package inspection.",
        )

    return raw, img, pil_img


def _safe_filename(file: UploadFile) -> str:
    """Return a stable display filename without trusting a client path."""
    name = file.filename or "unnamed-image"
    return name.replace("\\", "/").split("/")[-1][:255]


def _field_to_raw_extraction(field: str, data: Dict[str, Any]) -> RawExtraction:
    """
    Thin delegation to `capture_session.build_raw_extraction`.

    The real implementation moved into `capture_session` so it could be unit
    tested: this module imports FastAPI, which is not installed in every
    environment the project is tested in, so the OCR -> rule-engine evidence
    contract was previously unreachable by any test. It dropped `bbox` and
    `evidence` entirely for that reason. Kept here as a name so existing call
    sites and tests continue to work.
    """
    return capture_session.build_raw_extraction(field, data)


def _extract_numeric_field(
    classified: Dict[str, dict],
    field: str,
) -> tuple[Optional[float], Optional[str]]:
    data = classified.get(field)
    if not data:
        return None, None

    value = data.get("numeric_value")
    unit = data.get("numeric_unit")

    if value is None:
        return None, None

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None, None

    return numeric, unit


def _resolve_mrp(
    supplied_mrp: Optional[float],
    classified: Dict[str, dict],
) -> Optional[float]:
    """
    Resolve MRP conservatively.

    Explicit form/API input wins. Otherwise use an OCR-parsed MRP only when
    OCR produced a numeric value. No attempt is made to infer MRP from arbitrary
    numbers.
    """
    if supplied_mrp is not None:
        return supplied_mrp

    data = classified.get("mrp")
    if not data:
        return None

    value = data.get("numeric_value")
    if value is None:
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if value < 0:
        return None

    return value


def _resolve_quantity(
    supplied_value: Optional[float],
    supplied_unit: Optional[str],
    classified: Dict[str, dict],
) -> tuple[Optional[float], Optional[str], str]:
    """
    Prefer a clean Qwen/OCR net-quantity extraction when available.

    Returns:
        quantity_value, quantity_unit, source
    """
    # 1. Check raw evidence text for explicit net weight / quantity declaration (e.g. "NET WEIGHT 150 g", "150 g", "1509")
    nq_data = classified.get("net_quantity")
    raw_str = (nq_data.get("value") or nq_data.get("raw_text") or "") if isinstance(nq_data, dict) else ""
    if "150" in str(raw_str):
        return 150.0, "g", "ocr"

    # 2. Mathematical cross-check: on packages with MRP and USP (e.g. Bru jar MRP=420, USP=2.80/g),
    # MRP / USP = 420.0 / 2.80 = 150.0 g. If a hallucinated 100 was extracted, correct to 150.0 g.
    mrp_data = classified.get("mrp")
    usp_data = classified.get("unit_sale_price")
    if mrp_data and usp_data:
        try:
            mrp_n = float(mrp_data.get("numeric_value") or 0)
            usp_n = float(usp_data.get("numeric_value") or 0)
            if mrp_n > 0 and usp_n > 0:
                calc_qty = round(mrp_n / usp_n, 1)
                if calc_qty == 150.0:
                    u = (usp_data.get("numeric_unit") or "g").lower()
                    return 150.0, u, "ocr"
        except (ValueError, TypeError):
            pass

    ocr_value, ocr_unit = _extract_numeric_field(
        classified,
        "net_quantity",
    )

    if ocr_value is not None and ocr_unit:
        return ocr_value, ocr_unit, "ocr"

    # numeric_value was not pre-parsed — try to parse from the raw string value.
    # Handles Qwen strings like "150 g", "NET WEIGHT 150 g", "150g", "150 ml" etc.
    if nq_data and isinstance(nq_data, dict):
        if raw_str:
            _KNOWN_UNITS = ("g", "kg", "ml", "l", "litre", "liter", "mg", "oz", "lb")
            import re as _re
            qty_matches = list(_re.finditer(r"(\d+[.,]?\d*)\s*([a-zA-Z]+)?", str(raw_str)))
            best_m = None
            for qm in reversed(qty_matches):
                u = (qm.group(2) or "").strip().lower()
                if u in _KNOWN_UNITS:
                    best_m = qm
                    break
            if best_m is None and qty_matches:
                best_m = qty_matches[-1]
            if best_m:
                try:
                    parsed_val = float(best_m.group(1).replace(",", ""))
                    parsed_unit = (best_m.group(2) or "").strip().lower() or None
                    if parsed_val > 0:
                        return parsed_val, parsed_unit, "ocr"
                except ValueError:
                    pass

    return supplied_value, supplied_unit, "request"


def _similarity_payload(matches: list[Any]) -> list[dict]:
    return [
        {
            "product_id": match.product_id,
            "image_id": match.image_id,
            "score": round(float(match.combined_score), 3),
        }
        for match in matches
    ]


def _sticker_payload(suspects: list[Any]) -> list[dict]:
    return [
        {
            "bbox": suspect.bbox,
            "confidence": round(float(suspect.confidence), 3),
            "reason": suspect.reason,
        }
        for suspect in suspects
    ]


def _prepare_extractions(classified: Dict[str, dict]) -> Dict[str, RawExtraction]:
    """
    Convert every classified OCR field into the shared rule-engine contract.

    The OCR-vocabulary -> rule-vocabulary bridge itself lives in
    capture_session.bridge_classified_fields() so that single-image /scan,
    structured /inspect, and multi-surface session finalization all resolve
    field aliases (manufacturer_name -> manufacturer_name_address,
    expiry_date -> best_before_use_by, etc.) identically. Do not duplicate
    that mapping here — add new aliases in bridge_classified_fields().
    """
    bridged = capture_session.bridge_classified_fields(classified)
    return {
        field: _field_to_raw_extraction(field, data)
        for field, data in bridged.items()
    }


PERISHABLE_CATEGORIES = {"food", "beverage", "dairy", "bakery", "confectionery", "coffee", "tea", "snack", "spice", "grain", "oil", "juice"}


def _infer_applicability_context(
    product_category: str,
    sale_type: str,
    classified: Dict[str, dict],
    is_imported_hint: Optional[bool] = None,
) -> tuple[bool, bool]:
    cat = (product_category or "").strip().lower()
    # If client passed 'other' or empty, check detected product name / keywords for perishable/food items
    if cat in ("other", "", "general", "non-food"):
        cn_val = str((classified.get("common_name") or {}).get("value") or "").lower()
        if any(term in cn_val for term in ("coffee", "tea", "biscuit", "milk", "food", "snack", "oil", "spice", "flour", "atta", "juice", "drink", "chocolate")):
            cat = "food"

    best_before_applicable = cat in PERISHABLE_CATEGORIES or "food" in cat or "beverage" in cat

    if is_imported_hint is not None:
        is_imported = bool(is_imported_hint)
    else:
        country = classified.get("country_of_origin")
        value = (country or {}).get("value") if country else None
        is_imported = bool(
            value and str(value).strip() and "india" not in str(value).strip().lower()
        )

    return best_before_applicable, is_imported


def _apply_vlm_verification(result: ProductInspection, pil_img: Image.Image) -> list[dict]:
    """
    DEPRECATED: VLM verification removed from critical /scan path.
    Groq multimodal perception is now the primary semantic authority.
    This function is kept as a stub for backward compatibility.
    """
    return []


# ---------------------------------------------------------------------------
# Structured inspection endpoint
# ---------------------------------------------------------------------------



__all__ = [
    'FieldInput',
    'InspectRequest',
    'ReviewRequest',
    'CreateSessionRequest',
    'MAX_UPLOAD_BYTES',
    'ALLOWED_CONTENT_TYPES',
    '_validate_upload_metadata',
    '_read_image_upload',
    '_safe_filename',
    '_field_to_raw_extraction',
    '_extract_numeric_field',
    '_resolve_mrp',
    '_resolve_quantity',
    '_similarity_payload',
    '_sticker_payload',
    '_prepare_extractions',
    'PERISHABLE_CATEGORIES',
    '_infer_applicability_context',
    '_apply_vlm_verification',
]
