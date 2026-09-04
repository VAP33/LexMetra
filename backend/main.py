"""
FastAPI entrypoint for the LMPC packaged-commodity inspection MVP.

Pipeline:
    image -> OCR -> field extraction -> CV checks -> legal rule engine
          -> persistence -> structured API response

Design principles:
- The frontend supplies inspection context; OCR supplies evidence.
- OCR/CV never makes the legal decision.
- The deterministic rule engine is the authority for PASS/FAIL/UNCERTAIN/EXEMPT.
- OCR-derived values are used when they are explicitly and cleanly parsed.
- Missing OCR evidence is not silently converted into proof that a declaration
  is legally absent.
- This file keeps the HTTP/integration layer separate from legal logic.
"""

from __future__ import annotations

import io
import time
import uuid
from typing import Any, Dict, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

from schema import MeasurementMode, ProductInspection
from rule_engine import RawExtraction, run_inspection
from sticker_detection import detect_sticker_regions
from product_similarity import (
    detect_price_or_label_change,
    embed_image,
    find_similar,
    save_to_index,
)
from ocr_extraction import classify_fields, run_ocr
from db import persistence as db


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LMPC Compliance Inspection API",
    version="1.0.0",
    description=(
        "Evidence-backed packaged-commodity inspection using OCR, computer "
        "vision and a deterministic Legal Metrology rule engine."
    ),
)

# Prototype-friendly CORS. Restrict this to the deployed frontend origin before
# production use. The legal engine is independent of this setting.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    db.init_schema()


# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
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
    Translate OCR evidence into the rule engine's extraction contract.

    OCR confidence is extraction confidence. The rule engine remains responsible
    for the legal finding and should not treat this as legal confidence.
    """
    measurement_mode = data.get(
        "measurement_mode",
        MeasurementMode.UNCERTAIN,
    )

    if isinstance(measurement_mode, str):
        try:
            measurement_mode = MeasurementMode(measurement_mode)
        except ValueError:
            measurement_mode = MeasurementMode.UNCERTAIN

    return RawExtraction(
        field=field,
        value=data.get("value"),
        confidence=float(data.get("confidence", 0.0) or 0.0),
        measured_height_mm=data.get("measured_height_mm"),
        measurement_mode=measurement_mode,
        numeric_value=data.get("numeric_value"),
        numeric_unit=data.get("numeric_unit"),
    )


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
    supplied_value: float,
    supplied_unit: str,
    classified: Dict[str, dict],
) -> tuple[float, str, str]:
    """
    Prefer a clean OCR net-quantity extraction when available.

    Returns:
        quantity_value, quantity_unit, source
    """
    ocr_value, ocr_unit = _extract_numeric_field(
        classified,
        "net_quantity",
    )

    if ocr_value is not None and ocr_unit:
        return ocr_value, ocr_unit, "ocr"

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

    Auxiliary keys beginning with '_' are evidence metadata, not legal fields.
    """
    return {
        field: _field_to_raw_extraction(field, data)
        for field, data in classified.items()
        if not field.startswith("_")
    }


# ---------------------------------------------------------------------------
# Structured inspection endpoint
# ---------------------------------------------------------------------------

@app.post("/inspect", response_model=ProductInspection)
def inspect(req: InspectRequest) -> ProductInspection:
    """Run the deterministic compliance engine on already-structured evidence."""
    extractions = {
        field: RawExtraction(
            field=field,
            value=value.value,
            confidence=value.confidence,
            measured_height_mm=value.measured_height_mm,
            measurement_mode=value.measurement_mode,
            numeric_value=value.numeric_value,
            numeric_unit=value.numeric_unit,
        )
        for field, value in req.fields.items()
    }

    result = run_inspection(
        inspection_id=req.inspection_id,
        sale_type=req.sale_type,
        product_category=req.product_category,
        net_quantity_value=req.net_quantity_value,
        net_quantity_unit=req.net_quantity_unit,
        mrp=req.mrp,
        extractions=extractions,
        pdp_area_cm2=req.pdp_area_cm2,
        is_export_only=req.is_export_only,
        retail_bundle_count=req.retail_bundle_count,
    )

    db.save_inspection(result, mrp=req.mrp)
    return result


# ---------------------------------------------------------------------------
# Image analysis endpoint
# ---------------------------------------------------------------------------

@app.post("/analyze-image")
async def analyze_image(
    file: UploadFile = File(...),
    product_id: str = Form(...),
    mrp: Optional[float] = Form(None),
):
    """
    Run visual alteration/product-history analysis without legal inspection.

    This endpoint intentionally does not produce a legal compliance verdict.
    """
    _, img, _ = await _read_image_upload(file)
    image_id = _safe_filename(file)

    suspects = detect_sticker_regions(img)

    embedding = embed_image(
        img,
        product_id=product_id,
        image_id=image_id,
        mrp=mrp,
    )

    price_flag = detect_price_or_label_change(embedding)
    matches = find_similar(embedding, top_k=3)
    save_to_index(embedding)

    return {
        "product_id": product_id,
        "image_id": image_id,
        "sticker_suspects": _sticker_payload(suspects),
        "nearest_matches": _similarity_payload(matches),
        "price_or_label_change_flag": price_flag,
    }


# ---------------------------------------------------------------------------
# Full scan endpoint
# ---------------------------------------------------------------------------

@app.post("/scan")
async def scan(
    file: UploadFile = File(...),
    product_id: str = Form(...),
    sale_type: str = Form("retail"),
    product_category: str = Form("food"),
    net_quantity_value: float = Form(...),
    net_quantity_unit: str = Form(...),
    mrp: Optional[float] = Form(None),
    pdp_area_cm2: Optional[float] = Form(None),
    is_export_only: bool = Form(False),
    retail_bundle_count: Optional[int] = Form(None),
):
    """
    Full single-surface MVP inspection.

    Pipeline:
        image
          -> OCR
          -> field classification
          -> sticker analysis
          -> product similarity
          -> deterministic legal inspection
          -> persistence

    This endpoint deliberately remains single-image/single-capture for the MVP.
    Multi-surface inspection should be added as an inspection-session layer
    rather than pretending one image represents an entire package.
    """
    if not product_id.strip():
        raise HTTPException(status_code=400, detail="product_id is required.")

    if net_quantity_value <= 0:
        raise HTTPException(
            status_code=400,
            detail="net_quantity_value must be greater than zero.",
        )

    if mrp is not None and mrp < 0:
        raise HTTPException(
            status_code=400,
            detail="MRP cannot be negative.",
        )

    if pdp_area_cm2 is not None and pdp_area_cm2 <= 0:
        raise HTTPException(
            status_code=400,
            detail="pdp_area_cm2 must be greater than zero.",
        )

    if retail_bundle_count is not None and retail_bundle_count < 1:
        raise HTTPException(
            status_code=400,
            detail="retail_bundle_count must be at least 1.",
        )

    raw_bytes, img, pil_img = await _read_image_upload(file)
    image_id = _safe_filename(file)

    # ------------------------- OCR / extraction -------------------------
    ocr_lines = run_ocr(pil_img)
    classified = classify_fields(ocr_lines)
    extractions = _prepare_extractions(classified)

    # Resolve explicit numeric evidence. API values remain the fallback.
    qty_val, qty_unit, quantity_source = _resolve_quantity(
        net_quantity_value,
        net_quantity_unit,
        classified,
    )
    resolved_mrp = _resolve_mrp(mrp, classified)

    # ------------------------- Visual analysis ---------------------------
    suspects = detect_sticker_regions(img)

    embedding = embed_image(
        img,
        product_id=product_id,
        image_id=image_id or f"scan-{int(time.time())}",
        mrp=resolved_mrp,
    )

    price_flag = detect_price_or_label_change(embedding)
    matches = find_similar(embedding, top_k=3)
    save_to_index(embedding)

    # ------------------------- Legal evaluation --------------------------
    inspection_id = f"{product_id}:scan-{uuid.uuid4().hex[:8]}"

    result = run_inspection(
        inspection_id=inspection_id,
        sale_type=sale_type,
        product_category=product_category,
        net_quantity_value=qty_val,
        net_quantity_unit=qty_unit,
        mrp=resolved_mrp,
        extractions=extractions,
        pdp_area_cm2=pdp_area_cm2,
        is_export_only=is_export_only,
        retail_bundle_count=retail_bundle_count,
        sticker_suspects=suspects,
    )

    # ------------------------- Persistence ------------------------------
    db.save_inspection(
        result,
        image_filename=image_id,
        mrp=resolved_mrp,
    )

    return {
        "inspection": result,
        "raw_ocr_lines": [
            {
                "text": line.text,
                "bbox": line.bbox,
                "confidence": round(float(line.confidence), 3),
            }
            for line in ocr_lines
        ],
        "raw_ocr_fields": classified,
        "resolved_inputs": {
            "mrp": resolved_mrp,
            "mrp_source": "request" if mrp is not None else (
                "ocr" if resolved_mrp is not None else "not_observed"
            ),
            "net_quantity_value": qty_val,
            "net_quantity_unit": qty_unit,
            "net_quantity_source": quantity_source,
        },
        "sticker_suspects": _sticker_payload(suspects),
        "nearest_matches": _similarity_payload(matches),
        "price_or_label_change_flag": price_flag,
    }


# ---------------------------------------------------------------------------
# Inspection read/review endpoints
# ---------------------------------------------------------------------------

@app.get("/inspections")
def get_inspections(
    limit: int = 50,
    status: Optional[str] = None,
    needs_review: Optional[bool] = None,
):
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 200.",
        )

    return db.list_inspections(
        limit=limit,
        status=status,
        needs_review=needs_review,
    )


@app.get("/inspections/{inspection_id}")
def get_inspection(inspection_id: str):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    return detail


@app.post("/inspections/{inspection_id}/review")
def review_inspection(inspection_id: str, req: ReviewRequest):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    db.mark_reviewed(
        inspection_id,
        note=req.note.strip(),
    )

    return {
        "status": "ok",
        "inspection_id": inspection_id,
        "review_note": req.note.strip(),
    }


@app.get("/products/{product_id}/history")
def get_product_history(product_id: str):
    return db.product_history(product_id)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "lmpc-compliance-api",
    }
