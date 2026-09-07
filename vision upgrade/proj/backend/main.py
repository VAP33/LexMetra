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
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

import config
import auth
import capture_session
import evidence_fusion
import image_quality as image_quality_module
import vision_pipeline
from schema import FactStatus, MeasurementMode, ProductInspection, SurfaceObservation
from rule_engine import RawExtraction, run_inspection
from sticker_detection import detect_sticker_regions
from product_similarity import (
    detect_price_or_label_change,
    embed_image,
    find_similar,
    save_to_index,
)
from ocr_extraction import OcrLine, classify_fields, run_ocr
from vlm_verifier import verify_ambiguous_field
from db import persistence as db
from report import build_inspection_report_pdf


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

# CORS origins are read from configuration (ALLOWED_ORIGINS env var). Do not
# use "*" once authentication is enabled — wildcard origins + bearer tokens is
# an unsafe combination for a government inspection system.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    db.init_schema()


# ---------------------------------------------------------------------------
# Authentication endpoints
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = None
    role: str = "inspector"


@app.post("/auth/register")
def register(req: RegisterRequest):
    """
    Create a user account.

    Bootstrap rule: if no user exists yet in the database, the very first
    registration is allowed without authentication and is granted 'admin' so
    the system is operable on first deployment. Every subsequent registration
    requires an authenticated admin caller.
    """
    if req.role not in auth.ROLE_HIERARCHY:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    if db.any_user_exists():
        raise HTTPException(
            status_code=401,
            detail=(
                "An account already exists. Use an authenticated admin "
                "session to create additional users (see /auth/login, then "
                "call this endpoint with a Bearer token)."
            ),
        )

    if db.get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail="Username already exists.")

    role = req.role if db.any_user_exists() else "admin"
    record = db.create_user(
        username=req.username,
        hashed_password=auth.hash_password(req.password),
        role=role,
        full_name=req.full_name,
    )
    db.record_audit_event(
        action="user_created", actor_username=req.username,
        resource_type="user", resource_id=req.username,
        detail=f"role={role} (bootstrap)",
    )
    return {"user_id": record["user_id"], "username": record["username"], "role": record["role"]}


@app.post("/auth/register/admin")
def register_by_admin(
    req: RegisterRequest,
    current_user: auth.CurrentUser = Depends(auth.require_admin),
):
    """Admin-only endpoint to create additional accounts of any role."""
    if req.role not in auth.ROLE_HIERARCHY:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")
    if db.get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail="Username already exists.")

    record = db.create_user(
        username=req.username,
        hashed_password=auth.hash_password(req.password),
        role=req.role,
        full_name=req.full_name,
    )
    db.record_audit_event(
        action="user_created", actor_username=current_user.username,
        resource_type="user", resource_id=req.username, detail=f"role={req.role}",
    )
    return {"user_id": record["user_id"], "username": record["username"], "role": record["role"]}


@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = auth.authenticate_user(form_data.username, form_data.password)
    if not user:
        db.record_audit_event(action="login_failed", actor_username=form_data.username)
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.create_access_token(user.username, user.role)
    db.record_audit_event(action="login_success", actor_username=user.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
    }


@app.get("/auth/me")
def read_current_user(current_user: auth.CurrentUser = Depends(auth.get_current_user)):
    return current_user


@app.get("/audit-log")
def get_audit_log(
    limit: int = 100,
    current_user: auth.CurrentUser = Depends(auth.require_admin),
):
    return db.list_audit_log(limit=limit)


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


class CreateSessionRequest(BaseModel):
    product_id: str = Field(min_length=1)
    sale_type: str = "retail"
    product_category: str = "food"

    net_quantity_value: float = Field(gt=0)
    net_quantity_unit: str

    mrp: Optional[float] = Field(default=None, ge=0)
    pdp_area_cm2: Optional[float] = Field(default=None, gt=0)

    is_export_only: bool = False
    retail_bundle_count: Optional[int] = Field(default=None, ge=1)
    is_imported: Optional[bool] = None


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

    Legal safety invariant: if evidence_fusion flagged this field CONFLICTING
    (independent OCR engines/images disagreed), that disagreement must never
    be silently resolved into a confident legal PASS or FAIL just because the
    higher-confidence of the two conflicting readings happened to look good.
    We force the confidence fed to the rule engine below its low-confidence
    threshold in that case, regardless of what confidence evidence_fusion
    computed - the rule engine then falls back to UNCERTAIN via its normal
    low-confidence path, so there is exactly one place (rule_engine.py) that
    decides low-confidence handling.
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

    confidence = float(data.get("confidence", 0.0) or 0.0)
    if data.get("verification") == "CONFLICTING":
        confidence = min(confidence, 0.05)

    return RawExtraction(
        field=field,
        value=data.get("value"),
        confidence=confidence,
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


PERISHABLE_CATEGORIES = {"food", "beverage", "dairy", "bakery", "confectionery"}


def _infer_applicability_context(
    product_category: str,
    sale_type: str,
    classified: Dict[str, dict],
    is_imported_hint: Optional[bool] = None,
) -> tuple[bool, bool]:
    """
    Conservatively infer `best_before_applicable` and `is_imported`.

    These flags gate *conditional* Rule 6 requirements (best-before/use-by,
    country-of-origin). Getting them wrong in either direction is a legal
    risk, so inference here is deliberately narrow:

    - best_before_applicable: True only when product_category is a known
      perishable category. This is a coarse category heuristic, not a
      determination of shelf-stability, and should be confirmed by the
      inspector for categories outside this list.
    - is_imported: True only when the caller explicitly says so (e.g. a
      future 'sale_type=import' or explicit form field) OR when OCR evidence
      has *positively* extracted a non-empty 'country_of_origin' declaration
      naming a country other than India. Absence of a country-of-origin
      field must NOT be treated as "not imported" — that would let an
      undeclared import silently skip the very check meant to catch it.
    """
    best_before_applicable = product_category.strip().lower() in PERISHABLE_CATEGORIES

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
    Advisory-only semantic ambiguity check for UNCERTAIN facts.

    This NEVER changes result.overall_status, a fact's status, or any
    rule-engine decision. It only adds an advisory note a human reviewer can
    read alongside the deterministic finding. Disabled unless
    VLM_VERIFICATION_ENABLED=true and ANTHROPIC_API_KEY is configured; any
    failure (missing SDK, network, bad response) is swallowed so the core
    inspection pipeline never depends on an external API being available.
    """
    if not config.VLM_VERIFICATION_ENABLED:
        return []

    notes: list[dict] = []
    for fact in result.facts:
        if fact.status != FactStatus.UNCERTAIN:
            continue
        if fact.confidence is not None and fact.confidence < 0.2:
            # Very low/no evidence — a semantic ambiguity check adds nothing;
            # this is a missing-evidence case, not a wording-ambiguity case.
            continue
        try:
            verification = verify_ambiguous_field(
                field=fact.field,
                extracted_text=fact.extracted_value or "",
                rule_requirement=fact.reason or fact.field,
            )
        except Exception as exc:  # noqa: BLE001 - advisory path must not break /scan
            notes.append({
                "field": fact.field,
                "status": "verification_unavailable",
                "detail": str(exc)[:200],
            })
            continue

        notes.append({
            "field": fact.field,
            "ambiguous": verification.ambiguous,
            "explanation": verification.explanation,
            "provider": verification.provider,
        })

    return notes


# ---------------------------------------------------------------------------
# Structured inspection endpoint
# ---------------------------------------------------------------------------

@app.post("/inspect", response_model=ProductInspection)
def inspect(
    req: InspectRequest,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
) -> ProductInspection:
    """Run the deterministic compliance engine on already-structured evidence."""
    # Reuse the same field-name bridge as /scan (manufacturer/packer/importer
    # -> manufacturer_name_address, expiry_date -> best_before_use_by, etc.)
    # so structured-input callers get the same rule coverage as OCR callers.
    classified_like = {
        field: {
            "value": value.value,
            "confidence": value.confidence,
            "measured_height_mm": value.measured_height_mm,
            "measurement_mode": value.measurement_mode,
            "numeric_value": value.numeric_value,
            "numeric_unit": value.numeric_unit,
        }
        for field, value in req.fields.items()
    }
    extractions = _prepare_extractions(classified_like)

    best_before_applicable, is_imported = _infer_applicability_context(
        req.product_category, req.sale_type, classified_like,
    )

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
        best_before_applicable=best_before_applicable,
        is_imported=is_imported,
    )

    db.save_inspection(result, mrp=req.mrp)
    db.set_inspection_attribution(result.inspection_id, created_by=current_user.username)
    db.record_audit_event(
        action="inspection_created", actor_username=current_user.username,
        resource_type="inspection", resource_id=result.inspection_id,
        detail="via /inspect (structured input)",
    )
    return result


# ---------------------------------------------------------------------------
# Image analysis endpoint
# ---------------------------------------------------------------------------

@app.post("/analyze-image")
async def analyze_image(
    file: UploadFile = File(...),
    product_id: str = Form(...),
    mrp: Optional[float] = Form(None),
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
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
    is_imported: Optional[bool] = Form(None),
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
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
    vision = vision_pipeline.run_vision_pipeline(pil_img, img)
    classified = vision.classified_fields
    ocr_lines = vision.ocr_lines
    extractions = _prepare_extractions(classified)

    # Resolve explicit numeric evidence. API values remain the fallback.
    qty_val, qty_unit, quantity_source = _resolve_quantity(
        net_quantity_value,
        net_quantity_unit,
        classified,
    )
    resolved_mrp = _resolve_mrp(mrp, classified)

    best_before_applicable, resolved_is_imported = _infer_applicability_context(
        product_category, sale_type, classified, is_imported_hint=is_imported,
    )

    # ------------------------- Evidence retention -------------------------
    # Legal evidence requires retaining the original image, not just the
    # extracted facts. Store under a UUID-prefixed name so it cannot collide
    # or be path-traversed via a client-supplied filename.
    stored_filename = f"{uuid.uuid4().hex}_{image_id}"
    stored_path = config.UPLOAD_DIR / stored_filename
    try:
        stored_path.write_bytes(raw_bytes)
    except OSError:
        stored_path = None  # Do not fail the inspection if disk write fails.

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
        best_before_applicable=best_before_applicable,
        is_imported=resolved_is_imported,
    )

    # ------------------------- Legal advisory VLM verification -----------
    # Advisory only: never overrides the deterministic engine's PASS/FAIL.
    # Only attempted for UNCERTAIN fields, and only when explicitly enabled
    # with an API key configured (see config.VLM_VERIFICATION_ENABLED).
    vlm_notes = _apply_vlm_verification(result, pil_img)

    # ------------------------- Persistence ------------------------------
    db.save_inspection(
        result,
        image_filename=image_id,
        mrp=resolved_mrp,
    )
    db.set_inspection_attribution(
        result.inspection_id,
        created_by=current_user.username,
        image_path=str(stored_path) if stored_path else None,
    )
    db.record_audit_event(
        action="inspection_created", actor_username=current_user.username,
        resource_type="inspection", resource_id=result.inspection_id,
        detail=f"via /scan, sale_type={sale_type}",
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
        "ocr_engine_status": [
            {"engine": e.engine, "enabled": e.enabled, "available": e.available, "reason": e.reason}
            for e in vision.engine_status
        ],
        "barcode": (
            {"data": vision.barcode.data, "symbology": vision.barcode.symbology}
            if vision.barcode else None
        ),
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
        "vlm_advisory_notes": vlm_notes,
    }


# ---------------------------------------------------------------------------
# Multi-surface inspection sessions
# ---------------------------------------------------------------------------
#
# One InspectionSession accumulates any number of SurfaceObservation
# captures (front, back, rotated views of a curved label, etc.) before the
# deterministic legal engine runs exactly once against the UNION of every
# surface observed — see capture_session.py for the merge/coverage logic.
#
# Workflow:
#   POST /sessions                    -> open a session, get session_id
#   POST /sessions/{id}/captures      -> upload one surface photo, get
#                                         guidance + running evidence status
#   GET  /sessions/{id}               -> current session status
#   POST /sessions/{id}/finalize      -> run the legal engine once, persist
#                                         as a normal inspection record
# ---------------------------------------------------------------------------

@app.post("/sessions")
def create_session(
    req: CreateSessionRequest,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    session_id = f"{req.product_id}:session-{uuid.uuid4().hex[:10]}"
    db.create_session(
        session_id=session_id,
        product_id=req.product_id,
        sale_type=req.sale_type,
        product_category=req.product_category,
        net_quantity_value=req.net_quantity_value,
        net_quantity_unit=req.net_quantity_unit,
        mrp=req.mrp,
        pdp_area_cm2=req.pdp_area_cm2,
        is_export_only=req.is_export_only,
        retail_bundle_count=req.retail_bundle_count,
        is_imported_hint=req.is_imported,
        created_by=current_user.username,
    )
    db.record_audit_event(
        action="session_created", actor_username=current_user.username,
        resource_type="inspection_session", resource_id=session_id,
    )

    rules_ctx_best_before, rules_ctx_is_imported = _infer_applicability_context(
        req.product_category, req.sale_type, {}, is_imported_hint=req.is_imported,
    )
    coverage, missing = capture_session.compute_coverage(
        req.sale_type,
        {
            "is_imported": rules_ctx_is_imported,
            "best_before_applicable": rules_ctx_best_before,
            "unit_price_rule_applies": True,
        },
        {},
    )

    return {
        "session_id": session_id,
        "status": "OPEN",
        "coverage": round(coverage, 3),
        "missing_fields": missing,
        "guidance": [
            "Start with the main/front label showing the product name and net quantity.",
        ],
    }


@app.post("/sessions/{session_id}/captures")
async def add_capture(
    session_id: str,
    file: UploadFile = File(...),
    surface_type: Optional[str] = Form(None),
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session["status"] != "OPEN":
        raise HTTPException(
            status_code=409,
            detail=f"Session is '{session['status']}' and no longer accepts captures.",
        )

    raw_bytes, img, pil_img = await _read_image_upload(file)
    image_id = _safe_filename(file)

    # ------------------------- Per-image OCR/CV --------------------------
    vision = vision_pipeline.run_vision_pipeline(pil_img, img)
    classified = vision.classified_fields
    ocr_lines = vision.ocr_lines

    quality = image_quality_module.assess_image_quality(img, ocr_line_count=len(ocr_lines))
    pdp_bbox = image_quality_module.estimate_pdp_bbox(
        [line.bbox for line in ocr_lines],
        image_width=img.shape[1],
        image_height=img.shape[0],
    )
    recapture_guidance = image_quality_module.build_recapture_guidance(
        quality, vision.field_quality,
    )

    # ------------------------- Evidence retention -------------------------
    stored_filename = f"{uuid.uuid4().hex}_{image_id}"
    stored_path = config.UPLOAD_DIR / stored_filename
    try:
        stored_path.write_bytes(raw_bytes)
    except OSError:
        stored_path = None

    # ------------------------- Merge into session evidence ---------------
    previous_captures = db.list_session_captures(session_id)
    accumulated_fields: Dict[str, dict] = {}
    label_owner_image: Dict[str, str] = {}
    other_images_lines: Dict[str, List[OcrLine]] = {}
    for cap in previous_captures:
        cap_fields = cap.get("ocr_fields") or {}
        accumulated_fields = capture_session.merge_classified_fields(
            accumulated_fields, cap_fields,
        )
        for f in cap_fields:
            label_owner_image.setdefault(f, cap.get("image_id"))
        raw_lines = cap.get("raw_ocr_lines") or []
        other_images_lines[cap.get("image_id")] = [
            OcrLine(text=l["text"], bbox=tuple(l["bbox"]), confidence=l.get("confidence", 0.0))
            for l in raw_lines
            if "text" in l and "bbox" in l
        ]
    merged_fields = capture_session.merge_classified_fields(accumulated_fields, classified)
    for f in classified:
        label_owner_image.setdefault(f, image_id)

    # ------------------- Scoped cross-image reconstruction ---------------
    # Only attempts a join for label-only fields (e.g. "MRP Rs" with no
    # digits) against a bare value fragment from a DIFFERENT capture in this
    # same session - see evidence_fusion.py docstring for the exact,
    # deliberately narrow rules. Ambiguous or unsupported cases are left
    # alone (field stays label-only / UNCERTAIN), never guessed.
    this_capture_lines_serializable = [
        {"text": l.text, "bbox": list(l.bbox), "confidence": l.confidence}
        for l in ocr_lines
    ]
    reconstructable_other_images = dict(other_images_lines)
    reconstructable_other_images[image_id] = ocr_lines
    try:
        reconstructed = evidence_fusion.reconstruct_split_fields(
            merged_fields, label_owner_image, reconstructable_other_images,
        )
        merged_fields.update(reconstructed)
    except Exception:
        reconstructed = {}

    best_before_applicable, resolved_is_imported = _infer_applicability_context(
        session["product_category"], session["sale_type"], merged_fields,
        is_imported_hint=session.get("is_imported_hint"),
    )
    context = {
        "is_imported": resolved_is_imported,
        "best_before_applicable": best_before_applicable,
        "unit_price_rule_applies": True,
    }

    coverage, missing = capture_session.compute_coverage(
        session["sale_type"], context, merged_fields,
    )
    guidance = capture_session.guidance_messages(quality, coverage, missing)

    surface = capture_session.build_surface_observation(
        image_id=image_id or f"capture-{int(time.time())}",
        surface_type=capture_session.parse_surface_type(surface_type),
        image_quality=quality,
        coverage=coverage,
        pdp_bbox_px=pdp_bbox,
    )

    db.add_session_capture(
        session_id=session_id,
        surface_id=surface.surface_id,
        image_id=surface.image_id,
        image_path=str(stored_path) if stored_path else None,
        surface_type=surface.surface_type.value,
        ocr_fields=classified,
        surface_observation=surface.model_dump(mode="json"),
        evidence_coverage=coverage,
        raw_ocr_lines=this_capture_lines_serializable,
        barcode_data=vision.barcode.data if vision.barcode else None,
    )
    db.record_audit_event(
        action="session_capture_added", actor_username=current_user.username,
        resource_type="inspection_session", resource_id=session_id,
        detail=f"surface={surface.surface_type.value}, coverage={coverage:.2f}",
    )

    return {
        "session_id": session_id,
        "surface_id": surface.surface_id,
        "image_quality": quality.model_dump(mode="json"),
        "extracted_fields_this_capture": classified,
        "reconstructed_fields": reconstructed,
        "cumulative_coverage": round(coverage, 3),
        "missing_fields": missing,
        "evidence_sufficient": coverage >= capture_session.EVIDENCE_SUFFICIENT_COVERAGE,
        "guidance": guidance,
        "recapture_guidance": recapture_guidance,
        "barcode": (
            {"data": vision.barcode.data, "symbology": vision.barcode.symbology}
            if vision.barcode else None
        ),
        "total_captures": len(previous_captures) + 1,
    }


@app.get("/sessions/{session_id}")
def get_session_status(
    session_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    captures = db.list_session_captures(session_id)
    accumulated_fields: Dict[str, dict] = {}
    for cap in captures:
        accumulated_fields = capture_session.merge_classified_fields(
            accumulated_fields, cap.get("ocr_fields") or {},
        )

    best_before_applicable, resolved_is_imported = _infer_applicability_context(
        session["product_category"], session["sale_type"], accumulated_fields,
        is_imported_hint=session.get("is_imported_hint"),
    )
    context = {
        "is_imported": resolved_is_imported,
        "best_before_applicable": best_before_applicable,
        "unit_price_rule_applies": True,
    }
    coverage, missing = capture_session.compute_coverage(
        session["sale_type"], context, accumulated_fields,
    )

    return {
        "session": session,
        "captures": [
            {
                "surface_id": c["surface_id"],
                "image_id": c["image_id"],
                "surface_type": c["surface_type"],
                "evidence_coverage": float(c["evidence_coverage"] or 0.0),
                "image_quality": (c.get("surface_observation") or {}).get("image_quality"),
                "created_at": c["created_at"],
            }
            for c in captures
        ],
        "cumulative_coverage": round(coverage, 3),
        "missing_fields": missing,
        "evidence_sufficient": coverage >= capture_session.EVIDENCE_SUFFICIENT_COVERAGE,
        "cumulative_fields": accumulated_fields,
    }


@app.post("/sessions/{session_id}/finalize", response_model=ProductInspection)
def finalize_session(
    session_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
) -> ProductInspection:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session["status"] != "OPEN":
        raise HTTPException(
            status_code=409,
            detail=f"Session is already '{session['status']}'.",
        )

    captures = db.list_session_captures(session_id)
    if not captures:
        raise HTTPException(
            status_code=400,
            detail="Cannot finalize a session with zero captures.",
        )

    # ------------------------- Merge all surfaces -------------------------
    accumulated_fields: Dict[str, dict] = {}
    for cap in captures:
        accumulated_fields = capture_session.merge_classified_fields(
            accumulated_fields, cap.get("ocr_fields") or {},
        )
    extractions = _prepare_extractions(accumulated_fields)

    qty_val, qty_unit, _ = _resolve_quantity(
        float(session["net_quantity_value"]),
        session["net_quantity_unit"],
        accumulated_fields,
    )
    resolved_mrp = _resolve_mrp(
        float(session["mrp"]) if session.get("mrp") is not None else None,
        accumulated_fields,
    )

    best_before_applicable, resolved_is_imported = _infer_applicability_context(
        session["product_category"], session["sale_type"], accumulated_fields,
        is_imported_hint=session.get("is_imported_hint"),
    )

    surface_observations: List[SurfaceObservation] = []
    for cap in captures:
        obs = cap.get("surface_observation")
        if obs:
            try:
                surface_observations.append(SurfaceObservation.model_validate(obs))
            except Exception:
                continue

    inspection_id = f"{session['product_id']}:scan-{uuid.uuid4().hex[:8]}"

    result = run_inspection(
        inspection_id=inspection_id,
        sale_type=session["sale_type"],
        product_category=session["product_category"],
        net_quantity_value=qty_val,
        net_quantity_unit=qty_unit,
        mrp=resolved_mrp,
        extractions=extractions,
        pdp_area_cm2=float(session["pdp_area_cm2"]) if session.get("pdp_area_cm2") is not None else None,
        is_export_only=bool(session["is_export_only"]),
        retail_bundle_count=session.get("retail_bundle_count"),
        captures=surface_observations,
        best_before_applicable=best_before_applicable,
        is_imported=resolved_is_imported,
    )

    db.save_inspection(result, mrp=resolved_mrp)
    latest_image_path = captures[-1].get("image_path") if captures else None
    db.set_inspection_attribution(
        result.inspection_id,
        created_by=current_user.username,
        image_path=latest_image_path,
    )
    db.finalize_session(session_id, result.inspection_id)
    db.record_audit_event(
        action="session_finalized", actor_username=current_user.username,
        resource_type="inspection_session", resource_id=session_id,
        detail=f"-> inspection {result.inspection_id}, {len(captures)} captures",
    )

    return result


# ---------------------------------------------------------------------------
# Inspection read/review endpoints
# ---------------------------------------------------------------------------

@app.get("/inspections")
def get_inspections(
    limit: int = 50,
    status: Optional[str] = None,
    needs_review: Optional[bool] = None,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
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
def get_inspection(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    return detail


@app.post("/inspections/{inspection_id}/review")
def review_inspection(
    inspection_id: str,
    req: ReviewRequest,
    current_user: auth.CurrentUser = Depends(auth.require_reviewer),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    db.mark_reviewed(
        inspection_id,
        note=req.note.strip(),
        reviewed_by=current_user.username,
    )
    db.record_audit_event(
        action="inspection_reviewed", actor_username=current_user.username,
        resource_type="inspection", resource_id=inspection_id,
        detail=req.note.strip()[:200],
    )

    return {
        "status": "ok",
        "inspection_id": inspection_id,
        "review_note": req.note.strip(),
        "reviewed_by": current_user.username,
    }


@app.get("/inspections/{inspection_id}/report.pdf")
def get_inspection_report(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    pdf_bytes = build_inspection_report_pdf(detail)
    db.record_audit_event(
        action="report_generated", actor_username=current_user.username,
        resource_type="inspection", resource_id=inspection_id,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{inspection_id}_report.pdf"'
        },
    )


@app.get("/products/{product_id}/history")
def get_product_history(
    product_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
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
