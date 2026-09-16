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
import logging
import math
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
import uuid
from pathlib import Path

_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

import config
import auth
import capture_session
import image_quality as image_quality_module
import schema
from schema import FactStatus, MeasurementMode, ProductInspection, SurfaceObservation
from rule_engine import RawExtraction, run_inspection
from sticker_detection import detect_sticker_regions
from product_similarity import (
    detect_price_or_label_change,
    embed_image,
    find_similar,
    save_to_index,
)
from ocr_extraction import classify_fields, run_ocr
from vlm_verifier import verify_ambiguous_field, verify_ambiguous_field_gemini, recover_fields_from_image
from visual_recovery import merge_visual_candidates
from db import persistence as db
from report import build_inspection_report_pdf
import barcode_decode
import geometry
import calibration


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
    try:
        db.init_schema()

        # Never create predictable credentials implicitly. Demo accounts are an
        # explicit development-only opt-in and are disabled by default.
        if config.BOOTSTRAP_DEMO_USERS and config.DEV_MODE:
            for u, p, r, n in [
                ("admin", "password123", "admin", "System Admin"),
                ("inspector", "password123", "inspector", "Field Inspector"),
                ("reviewer", "password123", "reviewer", "Metrology Reviewer"),
            ]:
                if not db.get_user_by_username(u):
                    try:
                        db.create_user(
                            username=u,
                            hashed_password=auth.hash_password(p),
                            role=r,
                            full_name=n,
                        )
                    except Exception:
                        pass
    except Exception as exc:
        logging.getLogger("uvicorn.error").warning(
            f"Database initialization deferred (PostgreSQL unavailable at startup: {exc})."
        )


_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
_REACT_DIST_DIR = _FRONTEND_DIR / "react-app" / "dist"

if _REACT_DIST_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(_REACT_DIST_DIR), html=True), name="react_app")

if _FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")


@app.get("/", include_in_schema=False)
def root():
    if _REACT_DIST_DIR.exists():
        return RedirectResponse(url="/app/")
    return RedirectResponse(url="/frontend/dashboard.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard_shortcut():
    return RedirectResponse(url="/frontend/dashboard.html")


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
            if config.GEMINI_API_KEY:
                verification = verify_ambiguous_field_gemini(
                    field=fact.field,
                    extracted_text=fact.extracted_value or "",
                    rule_requirement=fact.reason or fact.field,
                )
            else:
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


@app.post("/inspect/v2/engine", response_model=ProductInspection)
def inspect_v2_engine(
    req: InspectRequest,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
) -> ProductInspection:
    """
    Same request/response contract as ``/inspect``, but the compliance
    decision is made by the new generic, data-driven rule engine
    (backend/engine/) reading rules/generic/lmpc_rules.json, instead of the
    legacy hard-coded per-field logic in rule_engine.py. Both endpoints can
    be run side by side and compared; nothing about ``/inspect`` changes.
    """
    from engine.lexmetra_adapter import run_inspection_v2

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

    result = run_inspection_v2(
        inspection_id=req.inspection_id,
        sale_type=req.sale_type,
        product_category=req.product_category,
        net_quantity_value=req.net_quantity_value,
        net_quantity_unit=req.net_quantity_unit,
        mrp=req.mrp,
        extractions=extractions,
        is_export_only=req.is_export_only,
        retail_bundle_count=req.retail_bundle_count,
        category_requires_best_before=best_before_applicable,
        is_imported=is_imported,
    )

    db.record_audit_event(
        action="inspection_created_v2_engine", actor_username=current_user.username,
        resource_type="inspection", resource_id=result.inspection_id,
        detail="via /inspect/v2/engine (generic rule engine)",
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
# Extract Preview endpoint (lightweight OCR preview for capture -> confirm flow)
# ---------------------------------------------------------------------------

# Category keyword weights.
#
# WHY THIS IS SCORED AND NOT FIRST-MATCH-WINS. The previous implementation
# tested `personal_care` first against a flat keyword list that contained
# "cream" and "oil". A jar of instant coffee whose label reads "creamer", or
# any edible oil, therefore matched personal_care and returned before the
# "coffee" keyword in the beverage branch was ever reached. Measured on a real
# Bru coffee photo: classified `personal_care`. First-match-wins over an
# unordered list makes the result depend on branch order rather than evidence.
#
# THE RULE. Every category is scored across the whole text, and the strongest
# total wins. Keywords that name a product outright ("coffee", "shampoo") carry
# more weight than substrings that merely co-occur with many product types
# ("cream", "oil", "wash", "water"), because the latter appear in ingredient
# lists and marketing copy far more often than they identify a category.
#
# A TIE IS NOT A CLASSIFICATION. If nothing scores, or the top two categories
# tie, this returns "other" rather than picking one. The category only seeds a
# suggestion the inspector confirms, so an honest "other" is preferable to a
# confident wrong guess that silently changes which rules get applied.
_CATEGORY_KEYWORD_WEIGHTS: Dict[str, Dict[str, float]] = {
    "personal_care": {
        # Strong: these name the product category.
        "shampoo": 3.0, "conditioner": 3.0, "toothpaste": 3.0, "sunscreen": 3.0,
        "cosmetic": 3.0, "deodorant": 3.0, "perfume": 3.0, "lotion": 3.0,
        "moisturiser": 3.0, "moisturizer": 3.0, "facewash": 3.0, "shaving": 3.0,
        "talc": 3.0, "kajal": 3.0, "lipstick": 3.0,
        # Weak: common in ingredient lists and other categories too.
        "soap": 1.5, "serum": 1.5, "hair": 1.0, "skin": 1.0,
        "cream": 0.5, "oil": 0.5,
    },
    "household": {
        "detergent": 3.0, "dishwash": 3.0, "disinfectant": 3.0, "bleach": 3.0,
        "freshener": 3.0, "phenyl": 3.0, "toilet cleaner": 3.0,
        "cleaner": 1.5, "floor": 1.0, "wash": 0.5,
    },
    "beverage": {
        "coffee": 3.0, "instant coffee": 3.0, "chicory": 3.0, "tea": 3.0,
        "juice": 3.0, "beverage": 3.0, "soda": 3.0, "cola": 3.0,
        "squash": 3.0, "energy drink": 3.0, "milkshake": 3.0,
        "drink": 1.5, "syrup": 1.0, "water": 0.5,
    },
    "food": {
        "biscuit": 3.0, "cookie": 3.0, "namkeen": 3.0, "noodle": 3.0,
        "atta": 3.0, "basmati": 3.0, "masala": 3.0, "spice": 3.0,
        "chocolate": 3.0, "paneer": 3.0, "cheese": 3.0, "butter": 3.0,
        "ghee": 3.0, "pickle": 3.0, "jam": 3.0, "snack": 3.0, "wafer": 3.0,
        # Edible oils. These must be STRONG and must live here, because
        # personal_care also scores a bare "oil": without an explicit edible-oil
        # keyword, a bottle of sunflower oil outscored food and classified as
        # personal_care. Measured, not hypothetical.
        "edible oil": 3.0, "refined oil": 3.0, "sunflower oil": 3.0,
        "mustard oil": 3.0, "groundnut oil": 3.0, "soyabean oil": 3.0,
        "soybean oil": 3.0, "rice bran": 3.0, "vanaspati": 3.0,
        "cooking oil": 3.0, "coconut oil": 2.0,
        "rice": 1.5, "flour": 1.5, "wheat": 1.5, "grain": 1.5, "pulse": 1.5,
        "milk": 1.0, "food": 1.0,
    },
}


def _infer_suggested_category(accumulated_fields: Dict[str, dict], all_ocr_lines: List[Any]) -> str:
    """
    Infer a suggested product category from extracted text.

    Scores every category over the full text and returns the strongest match.
    Returns "other" when nothing matches or when the top two categories tie --
    see the comment above _CATEGORY_KEYWORD_WEIGHTS for why order-independent
    scoring replaced the original first-match-wins chain.

    This is a SUGGESTION the inspector confirms, never an authoritative
    classification. It is deliberately allowed to abstain.
    """
    combined_text = " ".join(
        [str(v.get("value", "")) for v in accumulated_fields.values() if isinstance(v, dict)]
        + [str(getattr(l, "text", "")) for l in all_ocr_lines]
    ).lower()

    if not combined_text.strip():
        return "other"

    scores: Dict[str, float] = {}
    for category, keywords in _CATEGORY_KEYWORD_WEIGHTS.items():
        total = 0.0
        for keyword, weight in keywords.items():
            if keyword in combined_text:
                total += weight
        if total > 0:
            scores[category] = total

    if not scores:
        return "other"

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        # Ambiguous evidence: two categories are equally supported. Abstain
        # rather than let dict ordering decide a legal-metrology rule set.
        return "other"

    return ranked[0][0]


@app.post("/extract-preview")
async def extract_preview(
    file: Optional[UploadFile] = File(default=None),
    files: List[UploadFile] = File(default=[]),
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    """
    Lightweight OCR extraction preview.
    Takes captured image(s), runs run_ocr() + classify_fields() across surfaces,
    stamps provenance, and returns extracted fields and smart suggestions
    (suggested_product_id, suggested_qty_value, suggested_qty_unit, suggested_mrp, suggested_category).
    Does NOT persist to the database and requires NO prior product metadata.
    """
    upload_list: List[UploadFile] = []
    if files and isinstance(files, (list, tuple)):
        upload_list.extend([f for f in files if hasattr(f, "filename") and f.filename])
    elif files and hasattr(files, "filename") and files.filename:
        upload_list.append(files)
    if file and hasattr(file, "filename") and file.filename:
        if file not in upload_list and getattr(file, "filename", None) not in [f.filename for f in upload_list]:
            upload_list.append(file)
    if not upload_list:
        raise HTTPException(status_code=400, detail="At least one image file is required.")

    all_ocr_lines = []
    accumulated_fields: Dict[str, dict] = {}
    images_meta = []
    images_cv: List[Tuple[str, np.ndarray]] = []
    images_ocr_boxes: Dict[str, List[Tuple[int, int, int, int]]] = {}

    for i, upload in enumerate(upload_list):
        raw_bytes, img, pil_img = await _read_image_upload(upload)
        image_id = _safe_filename(upload) or f"surface_{i+1}.jpg"
        images_cv.append((image_id, img))

        ocr_lines = run_ocr(pil_img)
        all_ocr_lines.extend(ocr_lines)
        images_ocr_boxes[image_id] = [l.bbox for l in ocr_lines]

        classified = classify_fields(ocr_lines)
        surface_id = capture_session.new_surface_id()
        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)

        # Build 02: visual recovery is evidence extraction only. It runs before
        # legal evaluation, fills genuinely weak fields, and preserves any
        # OCR/VLM disagreement as explicit conflicting evidence for review.
        if config.VLM_VERIFICATION_ENABLED:
            weak_fields = {
                k: v for k, v in classified.items()
                if k in {
                    "common_name", "net_quantity", "mrp", "mfg_date",
                    "expiry_date", "manufacturer_name", "packer_name",
                    "importer_name", "consumer_care", "country_of_origin",
                }
                and (not v.get("value") or float(v.get("confidence", 0.0) or 0.0) < 0.62)
            }
            if weak_fields:
                try:
                    visual_candidates = recover_fields_from_image(
                        pil_img, weak_fields, image_id=image_id, surface_id=surface_id
                    )
                    classified = merge_visual_candidates(classified, visual_candidates)
                except Exception:
                    # Visual recovery is advisory evidence. OCR/CV and the
                    # deterministic rule engine remain fully functional if the
                    # model is unavailable, times out, or returns bad JSON.
                    pass

        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)

        images_meta.append({
            "index": i,
            "image_id": image_id,
            "width": img.shape[1],
            "height": img.shape[0],
            "lines_detected": len(ocr_lines),
        })

    # 1. Barcode decoding across uploaded surfaces
    barcode_result = barcode_decode.decode_across_images(images_cv)
    primary_symbol = barcode_result.symbols[0] if barcode_result.symbols else None

    # 2. Geometry & PDP Area estimation
    computed_pdp_area_cm2: Optional[float] = None
    primary_img_id = (primary_symbol.image_id if primary_symbol and primary_symbol.image_id != "MULTI_SURFACE" else None) or (images_cv[0][0] if images_cv else "")
    primary_img_np = next((img for iid, img in images_cv if iid == primary_img_id), images_cv[0][1] if images_cv else None)

    if primary_img_np is not None:
        try:
            pkg_geom = geometry.detect_package_geometry(primary_img_np, primary_img_id)
            ocr_boxes = images_ocr_boxes.get(primary_img_id, [])
            pdp_geom = geometry.detect_pdp_geometry(primary_img_np, primary_img_id, package_geometry=pkg_geom, ocr_boxes=ocr_boxes)

            calib = None
            if primary_symbol and primary_symbol.bbox:
                bw = primary_symbol.bbox[2]
                calib = calibration.calibrate_from_known_package_dimension(
                    known_pixel_length=float(bw), known_dimension_mm=37.29, source_image=primary_img_id, dimension_source_note="EAN-13 nominal width 37.29mm"
                )
            elif pkg_geom.bbox and pkg_geom.bbox.width > 10:
                calib = calibration.calibrate_from_known_package_dimension(
                    known_pixel_length=float(pkg_geom.bbox.width), known_dimension_mm=85.0, source_image=primary_img_id, dimension_source_note="Estimated standard package width (~85mm)"
                )

            if calib:
                circ_bbox = None
                if pkg_geom.shape in (schema.GeometryType.CYLINDRICAL, schema.GeometryType.NEAR_CYLINDRICAL) and pkg_geom.bbox:
                    circ_bbox = schema.BBox(x=0, y=0, width=max(1, int(math.pi * pkg_geom.bbox.width)), height=1)
                pdp_meas = calibration.measure_pdp_area(pdp_geom, pkg_geom.shape, calib, circumference_bbox=circ_bbox)
                if pdp_meas and pdp_meas.value is not None and pdp_meas.value > 0:
                    computed_pdp_area_cm2 = round(float(pdp_meas.value), 2)
        except Exception:
            pass

    # Numeric extractions
    qty_val, qty_unit = _extract_numeric_field(accumulated_fields, "net_quantity")
    mrp_val = None
    mrp_data = accumulated_fields.get("mrp")
    if mrp_data and mrp_data.get("numeric_value") is not None:
        try:
            mrp_val = float(mrp_data["numeric_value"])
        except (ValueError, TypeError):
            mrp_val = None

    # Suggested product ID: Barcode (primary) -> Common name -> Manufacturer -> Placeholder
    c_name = accumulated_fields.get("common_name", {}).get("value")
    m_name = accumulated_fields.get("manufacturer_name", {}).get("value") or accumulated_fields.get("manufacturer_name_address", {}).get("value")
    suggested_pid = ""
    pid_source = "unidentified-placeholder"
    needs_manual_entry = False
    barcode_needs_confirmation = False

    if primary_symbol:
        suggested_pid = primary_symbol.gtin13 or primary_symbol.payload
        if primary_symbol.method == barcode_decode.ReadMethod.CV_BARS_DECODED:
            pid_source = "barcode_machine_decoded"
            barcode_needs_confirmation = False
        else:
            pid_source = "barcode_hri_checksum_verified"
            barcode_needs_confirmation = bool(primary_symbol.needs_confirmation)
    elif c_name:
        clean_c = re.sub(r'[^a-zA-Z0-9]+', '-', c_name).strip('-')[:25]
        if clean_c:
            suggested_pid = f"PROD-{clean_c.upper()}"
            pid_source = "ocr_common_name"
    elif m_name:
        clean_m = re.sub(r'[^a-zA-Z0-9]+', '-', m_name).strip('-')[:20]
        if clean_m:
            suggested_pid = f"PROD-{clean_m.upper()}"
            pid_source = "ocr_manufacturer"

    if not suggested_pid:
        suggested_pid = f"PROD-{uuid.uuid4().hex[:6].upper()}"
        pid_source = "unidentified-placeholder"
        needs_manual_entry = True

    suggested_category = _infer_suggested_category(accumulated_fields, all_ocr_lines)

    field_confidences = {
        k: {
            "value": v.get("value"),
            "confidence": round(float(v.get("confidence", 0.0)), 2),
            "source_image": v.get("image_id"),
            "detected": bool(v.get("value")),
        }
        for k, v in accumulated_fields.items()
    }

    if primary_symbol:
        field_confidences["barcode"] = {
            "value": primary_symbol.gtin13 or primary_symbol.payload,
            "confidence": round(float(primary_symbol.confidence), 2),
            "source_image": primary_symbol.image_id,
            "detected": True,
        }

    return {
        "status": "success",
        "images": images_meta,
        "total_lines": len(all_ocr_lines),
        "suggested_details": {
            "product_id": suggested_pid,
            "product_id_source": pid_source,
            "needs_manual_entry": needs_manual_entry,
            "barcode_needs_confirmation": barcode_needs_confirmation,
            "barcode_info": {
                "status": barcode_result.status.value,
                "symbol_count": len(barcode_result.symbols),
                "primary_gtin": primary_symbol.gtin13 if primary_symbol else None,
                "primary_symbology": primary_symbol.kind.value if primary_symbol else None,
                "primary_method": primary_symbol.method.value if primary_symbol else None,
                "notes": barcode_result.notes,
            } if primary_symbol else None,
            "sale_type": "retail",
            "category": suggested_category,
            "net_quantity_value": qty_val,
            "net_quantity_unit": qty_unit or "g",
            "mrp": mrp_val,
            "pdp_area_cm2": computed_pdp_area_cm2,
        },
        "field_extractions": field_confidences,
        "raw_ocr_fields": accumulated_fields,
    }


# ---------------------------------------------------------------------------
# Full scan endpoint
# ---------------------------------------------------------------------------

@app.post("/scan")
async def scan(
    file: Optional[UploadFile] = File(default=None),
    files: List[UploadFile] = File(default=[]),
    product_id: Optional[str] = Form(None),
    sale_type: str = Form("retail"),
    product_category: str = Form("food"),
    net_quantity_value: Optional[float] = Form(None),
    net_quantity_unit: Optional[str] = Form(None),
    mrp: Optional[float] = Form(None),
    pdp_area_cm2: Optional[float] = Form(None),
    is_export_only: bool = Form(False),
    retail_bundle_count: Optional[int] = Form(None),
    is_imported: Optional[bool] = Form(None),
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    """
    Full package inspection supporting single or multi-image captures.

    Pipeline:
        image(s)
          -> OCR & field classification per surface
          -> provenance stamping & cross-surface merge
          -> sticker analysis & product similarity
          -> deterministic legal inspection
          -> persistence
    """
    # Normalize Form/Field parameters if called directly in Python
    product_id = product_id if isinstance(product_id, str) else None
    sale_type = sale_type if isinstance(sale_type, str) else "retail"
    product_category = product_category if isinstance(product_category, str) else "other"
    net_quantity_value = net_quantity_value if isinstance(net_quantity_value, (int, float)) else None
    net_quantity_unit = net_quantity_unit if isinstance(net_quantity_unit, str) else None
    mrp = mrp if isinstance(mrp, (int, float)) else None
    pdp_area_cm2 = pdp_area_cm2 if isinstance(pdp_area_cm2, (int, float)) else None
    retail_bundle_count = retail_bundle_count if isinstance(retail_bundle_count, int) else None
    is_export_only = bool(is_export_only) if not hasattr(is_export_only, "default") else False
    is_imported = bool(is_imported) if is_imported is not None and not hasattr(is_imported, "default") else None

    if product_id is not None and product_id != "" and not product_id.strip():
        raise HTTPException(status_code=400, detail="product_id cannot be blank whitespace.")

    if net_quantity_value is not None and net_quantity_value <= 0:
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

    upload_list: List[UploadFile] = []
    if files and isinstance(files, (list, tuple)):
        upload_list.extend([f for f in files if hasattr(f, "filename") and f.filename])
    elif files and hasattr(files, "filename") and files.filename:
        upload_list.append(files)
    if file and hasattr(file, "filename") and file.filename:
        if file not in upload_list and getattr(file, "filename", None) not in [f.filename for f in upload_list]:
            upload_list.append(file)
    if not upload_list:
        raise HTTPException(status_code=400, detail="At least one image file is required.")

    all_ocr_lines = []
    accumulated_fields: Dict[str, dict] = {}
    all_suspects: list[Any] = []
    surface_observations: List[SurfaceObservation] = []
    first_pil_img: Optional[Image.Image] = None
    first_img_np: Optional[np.ndarray] = None
    first_image_id: Optional[str] = None
    first_stored_path: Optional[Path] = None
    images_cv: List[Tuple[str, np.ndarray]] = []
    images_ocr_boxes: Dict[str, List[Tuple[int, int, int, int]]] = {}

    for i, upload in enumerate(upload_list):
        raw_bytes, img, pil_img = await _read_image_upload(upload)
        image_id = _safe_filename(upload)
        images_cv.append((image_id, img))

        if first_pil_img is None:
            first_pil_img = pil_img
            first_img_np = img
            first_image_id = image_id

        # ------------------------- Evidence retention -------------------------
        stored_filename = f"{uuid.uuid4().hex}_{image_id}"
        stored_path = config.UPLOAD_DIR / stored_filename
        try:
            stored_path.write_bytes(raw_bytes)
            if first_stored_path is None:
                first_stored_path = stored_path
        except OSError:
            pass

        # ------------------------- OCR / extraction -------------------------
        ocr_lines = run_ocr(pil_img)
        all_ocr_lines.extend(ocr_lines)
        images_ocr_boxes[image_id] = [l.bbox for l in ocr_lines]

        classified = classify_fields(ocr_lines)
        surface_id = capture_session.new_surface_id()
        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)

        # Build 02: visual recovery is evidence extraction only. It runs before
        # legal evaluation, fills genuinely weak fields, and preserves any
        # OCR/VLM disagreement as explicit conflicting evidence for review.
        if config.VLM_VERIFICATION_ENABLED:
            weak_fields = {
                k: v for k, v in classified.items()
                if k in {
                    "common_name", "net_quantity", "mrp", "mfg_date",
                    "expiry_date", "manufacturer_name", "packer_name",
                    "importer_name", "consumer_care", "country_of_origin",
                }
                and (not v.get("value") or float(v.get("confidence", 0.0) or 0.0) < 0.62)
            }
            if weak_fields:
                try:
                    visual_candidates = recover_fields_from_image(
                        pil_img, weak_fields, image_id=image_id, surface_id=surface_id
                    )
                    classified = merge_visual_candidates(classified, visual_candidates)
                except Exception:
                    # Visual recovery is advisory evidence. OCR/CV and the
                    # deterministic rule engine remain fully functional if the
                    # model is unavailable, times out, or returns bad JSON.
                    pass

        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)

        # Quality & PDP
        quality = image_quality_module.assess_image_quality(img, ocr_line_count=len(ocr_lines))
        pdp_bbox = image_quality_module.estimate_pdp_bbox(
            [line.bbox for line in ocr_lines],
            image_width=img.shape[1],
            image_height=img.shape[0],
        )

        stype_name = "FRONT" if i == 0 else ("BACK" if i == 1 else "SIDE")
        surface_type = capture_session.parse_surface_type(stype_name)
        surface_obs = capture_session.build_surface_observation(
            image_id=image_id,
            surface_type=surface_type,
            image_quality=quality,
            coverage=0.0,
            pdp_bbox_px=pdp_bbox,
            surface_id=surface_id,
        )
        surface_observations.append(surface_obs)

        suspects = detect_sticker_regions(img)
        all_suspects.extend(suspects)

    # 1. Barcode decoding across uploaded surfaces
    barcode_result = barcode_decode.decode_across_images(images_cv)
    primary_symbol = barcode_result.symbols[0] if barcode_result.symbols else None

    # 2. Geometry & PDP Area estimation (unblocks Rule 7(2) font height)
    computed_pdp_area_cm2: Optional[float] = None
    primary_img_id = (primary_symbol.image_id if primary_symbol and primary_symbol.image_id != "MULTI_SURFACE" else None) or (images_cv[0][0] if images_cv else "")
    primary_img_np = next((img for iid, img in images_cv if iid == primary_img_id), images_cv[0][1] if images_cv else None)

    if primary_img_np is not None:
        try:
            pkg_geom = geometry.detect_package_geometry(primary_img_np, primary_img_id)
            ocr_boxes = images_ocr_boxes.get(primary_img_id, [])
            pdp_geom = geometry.detect_pdp_geometry(primary_img_np, primary_img_id, package_geometry=pkg_geom, ocr_boxes=ocr_boxes)

            calib = None
            if primary_symbol and primary_symbol.bbox:
                bw = primary_symbol.bbox[2]
                calib = calibration.calibrate_from_known_package_dimension(
                    known_pixel_length=float(bw), known_dimension_mm=37.29, source_image=primary_img_id, dimension_source_note="EAN-13 nominal width 37.29mm"
                )
            elif pkg_geom.bbox and pkg_geom.bbox.width > 10:
                calib = calibration.calibrate_from_known_package_dimension(
                    known_pixel_length=float(pkg_geom.bbox.width), known_dimension_mm=85.0, source_image=primary_img_id, dimension_source_note="Estimated standard package width (~85mm)"
                )

            if calib:
                circ_bbox = None
                if pkg_geom.shape in (schema.GeometryType.CYLINDRICAL, schema.GeometryType.NEAR_CYLINDRICAL) and pkg_geom.bbox:
                    circ_bbox = schema.BBox(x=0, y=0, width=max(1, int(math.pi * pkg_geom.bbox.width)), height=1)
                pdp_meas = calibration.measure_pdp_area(pdp_geom, pkg_geom.shape, calib, circumference_bbox=circ_bbox)
                if pdp_meas and pdp_meas.value is not None and pdp_meas.value > 0:
                    computed_pdp_area_cm2 = round(float(pdp_meas.value), 2)
        except Exception:
            pass

    if pdp_area_cm2 is None and computed_pdp_area_cm2 is not None:
        pdp_area_cm2 = computed_pdp_area_cm2

    extractions = _prepare_extractions(accumulated_fields)
    if primary_symbol and "barcode" not in extractions:
        extractions["barcode"] = RawExtraction(
            field="barcode",
            raw_text=primary_symbol.payload,
            value=primary_symbol.gtin13 or primary_symbol.payload,
            confidence=float(primary_symbol.confidence),
        )

    # Resolve product_id fallback: Barcode (primary) -> Common name -> Manufacturer -> Placeholder
    resolved_product_id = product_id.strip() if (product_id and product_id.strip()) else ""
    if not resolved_product_id:
        if primary_symbol:
            resolved_product_id = primary_symbol.gtin13 or primary_symbol.payload
        else:
            c_name = accumulated_fields.get("common_name", {}).get("value")
            m_name = accumulated_fields.get("manufacturer_name", {}).get("value") or accumulated_fields.get("manufacturer_name_address", {}).get("value")
            if c_name:
                slug = re.sub(r'[^a-zA-Z0-9]+', '-', c_name).strip('-')[:25]
                if slug:
                    resolved_product_id = f"PROD-{slug.upper()}"
            if not resolved_product_id and m_name:
                slug = re.sub(r'[^a-zA-Z0-9]+', '-', m_name).strip('-')[:20]
                if slug:
                    resolved_product_id = f"PROD-{slug.upper()}"
            if not resolved_product_id:
                resolved_product_id = f"SCAN-{uuid.uuid4().hex[:8].upper()}"

    # Resolve explicit numeric evidence. API values remain the fallback.
    qty_val, qty_unit, quantity_source = _resolve_quantity(
        net_quantity_value if net_quantity_value is not None else 0.0,
        net_quantity_unit or "",
        accumulated_fields,
    )
    if qty_val is None or qty_val <= 0:
        qty_val = 1.0
        qty_unit = qty_unit or "unit"
        quantity_source = "default_fallback"

    resolved_mrp = _resolve_mrp(mrp, accumulated_fields)

    best_before_applicable, resolved_is_imported = _infer_applicability_context(
        product_category, sale_type, accumulated_fields, is_imported_hint=is_imported,
    )

    # ------------------------- Visual analysis ---------------------------
    price_flag = None
    matches = []
    if first_img_np is not None:
        embedding = embed_image(
            first_img_np,
            product_id=resolved_product_id,
            image_id=first_image_id or f"scan-{int(time.time())}",
            mrp=resolved_mrp,
        )
        price_flag = detect_price_or_label_change(embedding)
        matches = find_similar(embedding, top_k=3)
        save_to_index(embedding)

    # ------------------------- Legal evaluation --------------------------
    inspection_id = f"{resolved_product_id}:scan-{uuid.uuid4().hex[:8]}"

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
        sticker_suspects=all_suspects,
        captures=surface_observations,
        best_before_applicable=best_before_applicable,
        is_imported=resolved_is_imported,
    )

    # ------------------------- Legal advisory VLM verification -----------
    vlm_notes = _apply_vlm_verification(result, first_pil_img) if first_pil_img is not None else []

    # ------------------------- Persistence ------------------------------
    db.save_inspection(
        result,
        image_filename=first_image_id,
        mrp=resolved_mrp,
    )
    db.set_inspection_attribution(
        result.inspection_id,
        created_by=current_user.username,
        image_path=str(first_stored_path) if first_stored_path else None,
    )
    db.record_audit_event(
        action="inspection_created", actor_username=current_user.username,
        resource_type="inspection", resource_id=result.inspection_id,
        detail=f"via /scan, sale_type={sale_type}, images={len(upload_list)}",
    )

    return {
        "inspection": result,
        "raw_ocr_lines": [
            {
                "text": line.text,
                "bbox": line.bbox,
                "confidence": round(float(line.confidence), 3),
            }
            for line in all_ocr_lines
        ],
        "raw_ocr_fields": accumulated_fields,
        "resolved_inputs": {
            "mrp": resolved_mrp,
            "mrp_source": "request" if mrp is not None else (
                "ocr" if resolved_mrp is not None else "not_observed"
            ),
            "net_quantity_value": qty_val,
            "net_quantity_unit": qty_unit,
            "net_quantity_source": quantity_source,
            "pdp_area_cm2": pdp_area_cm2,
        },
        "barcode_info": {
            "status": barcode_result.status.value,
            "symbol_count": len(barcode_result.symbols),
            "primary_gtin": primary_symbol.gtin13 if primary_symbol else None,
            "primary_symbology": primary_symbol.kind.value if primary_symbol else None,
            "primary_method": primary_symbol.method.value if primary_symbol else None,
        } if primary_symbol else None,
        "sticker_suspects": _sticker_payload(all_suspects),
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
    ocr_lines = run_ocr(pil_img)
    classified = classify_fields(ocr_lines)

    # Stamp provenance BEFORE the session merge. `merge_classified_fields`
    # keeps whichever observation has the higher confidence, so in a
    # multi-surface session the winning reading of `mrp` may come from a
    # different photograph than the winning reading of `net_quantity`. Stamping
    # per field means each surviving observation carries its own source image,
    # rather than all of them inheriting the id of whichever capture happened
    # to be last.
    surface_id = capture_session.new_surface_id()
    classified = capture_session.stamp_provenance(
        classified, image_id=image_id, surface_id=surface_id
    )

    quality = image_quality_module.assess_image_quality(img, ocr_line_count=len(ocr_lines))
    pdp_bbox = image_quality_module.estimate_pdp_bbox(
        [line.bbox for line in ocr_lines],
        image_width=img.shape[1],
        image_height=img.shape[0],
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
    for cap in previous_captures:
        accumulated_fields = capture_session.merge_classified_fields(
            accumulated_fields, cap.get("ocr_fields") or {},
        )
    merged_fields = capture_session.merge_classified_fields(accumulated_fields, classified)

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
        surface_id=surface_id,
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
        "cumulative_coverage": round(coverage, 3),
        "missing_fields": missing,
        "evidence_sufficient": coverage >= capture_session.EVIDENCE_SUFFICIENT_COVERAGE,
        "guidance": guidance,
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
@app.head("/inspections/{inspection_id}/report.pdf")
def get_inspection_report(
    inspection_id: str,
    token: Optional[str] = None,
    bearer_token: Optional[str] = Depends(auth.oauth2_scheme),
):
    effective_token = bearer_token or token
    actor_username = "inspector"
    if effective_token:
        try:
            token_data = auth.decode_access_token(effective_token)
            user = db.get_user_by_username(token_data.username)
            if user:
                actor_username = user["username"]
        except Exception:
            pass
    elif not config.DEV_MODE:
        raise HTTPException(
            status_code=401,
            detail="Authentication required to access inspection report.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    pdf_bytes = build_inspection_report_pdf(detail)
    db.record_audit_event(
        action="report_generated",
        actor_username=actor_username,
        resource_type="inspection",
        resource_id=inspection_id,
    )
    safe_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", inspection_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_id}_report.pdf"'
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
    """Cheap liveness probe. It deliberately does not require dependencies."""
    from ocr_engine import active_engines
    engines, engine_notes = active_engines()
    return {
        "status": "ok",
        "service": "lmpc-compliance-api",
        "mode": "demo" if config.DEMO_MODE else "production",
        "ocr": {
            "active_engines": [getattr(engine, "name", str(engine)) for engine in engines],
            "paddle_requested": bool(config.ENABLE_PADDLEOCR),
            "notes": engine_notes,
        },
        "vlm": {
            "visual_recovery_enabled": bool(config.VLM_VERIFICATION_ENABLED),
        },
    }


@app.get("/ready")
def readiness():
    """Dependency-aware readiness probe without exposing connection details."""
    checks = {"database": "unavailable", "redis": "not_configured"}
    ready = True

    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        checks["database"] = "ok"
    except Exception:
        ready = False

    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        try:
            import redis
            client = redis.Redis.from_url(
                redis_url, decode_responses=True,
                socket_connect_timeout=1, socket_timeout=1,
            )
            client.ping()
            checks["redis"] = "ok"
        except Exception:
            # Redis is operational infrastructure, not legal truth. A Redis
            # outage is reported but does not alter inspection correctness.
            checks["redis"] = "unavailable"
    return {"status": "ready" if ready else "not_ready", "service": "lmpc-compliance-api", "checks": checks}


# ---------------------------------------------------------------------------
# Regulation ingestion (Module 1 integration)
# ---------------------------------------------------------------------------
# Upload a regulation PDF -> OCR/extract -> propose rule versions as an
# AmendmentDraft (approval_state=EXTRACTED). A draft NEVER affects current
# compliance evaluation on its own -- see regulation_ingestion.py and
# amendments.py. A reviewer must explicitly move it through
# pending_review -> approved -> scheduled -> active before
# regulatory/runtime.apply_rule_versions will ever select it.

import tempfile as _tempfile

from amendments import activate_amendment, transition_amendment
from models import AmendmentDraft, ApprovalState
from regulation_ingestion import RegulationIngestionError, ingest_regulation_pdf


class TransitionRequest(BaseModel):
    target_state: str
    reviewer: Optional[str] = None


@app.post("/regulations/ingest")
async def regulations_ingest(
    file: UploadFile = File(...),
    regulation: str = Form("IN-LMPC-2011"),
    module: str = Form("lmpc"),
    version: Optional[str] = Form(None),
    start_page: Optional[int] = Form(None),
    end_page: Optional[int] = Form(None),
    force_ocr: bool = Form(False),
    current_user: auth.CurrentUser = Depends(auth.require_role("reviewer")),
):
    """
    Upload a regulation PDF and run it through the full ingestion pipeline
    (OCR -> clause/rule extraction -> normalization). Returns the resulting
    AmendmentDraft (approval_state=EXTRACTED) for review.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted for regulation ingestion.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    with _tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name

    try:
        result = ingest_regulation_pdf(
            tmp_path,
            source_document_id=_safe_filename(file),
            regulation=regulation,
            module=module,
            version=version,
            start_page=start_page,
            end_page=end_page,
            force_ocr=force_ocr,
            created_by=current_user.username,
        )
    except RegulationIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    db.record_audit_event(
        action="regulation_ingested", actor_username=current_user.username,
        resource_type="amendment_draft", resource_id=result.draft.id,
        detail=f"pages={result.page_count} rules={result.rule_count} "
               f"rejected={result.rejected_count} needs_review={result.needs_review_count}",
    )
    return {
        "draft": result.draft.model_dump(mode="json"),
        "page_count": result.page_count,
        "rule_count": result.rule_count,
        "rejected_count": result.rejected_count,
        "needs_review_count": result.needs_review_count,
    }


@app.get("/regulations/drafts")
def regulations_list_drafts(
    approval_state: Optional[str] = None,
    limit: int = 100,
    current_user: auth.CurrentUser = Depends(auth.require_role("reviewer")),
):
    rows = db.list_amendment_drafts(approval_state=approval_state, limit=limit)
    return {"drafts": [r["payload"] for r in rows]}


@app.get("/regulations/drafts/{draft_id}")
def regulations_get_draft(
    draft_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_role("reviewer")),
):
    row = db.get_amendment_draft(draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Amendment draft not found.")
    return row["payload"]


@app.post("/regulations/drafts/{draft_id}/transition")
def regulations_transition_draft(
    draft_id: str,
    req: TransitionRequest,
    current_user: auth.CurrentUser = Depends(auth.require_admin),
):
    """
    Move a draft through the approval lifecycle
    (draft->extracted->ai_parsed->pending_review->approved->scheduled->active
    or ->rejected/superseded). Only ACTIVE rule versions are ever picked up
    by current compliance evaluation (see regulatory/runtime.py).
    """
    row = db.get_amendment_draft(draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Amendment draft not found.")

    draft = AmendmentDraft(**row["payload"])
    try:
        target = ApprovalState(req.target_state.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown approval state: {req.target_state!r}")

    try:
        if target is ApprovalState.ACTIVE:
            updated = activate_amendment(draft, authorized_by=req.reviewer or current_user.username)
            # Atomically publish the approved executable rules into PostgreSQL
            db.publish_amendment_draft(draft_id, published_by=req.reviewer or current_user.username)
        else:
            updated = transition_amendment(draft, target)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    db.update_amendment_draft_state(
        draft_id=draft_id,
        approval_state=updated.approval_state.value,
        payload_json=updated.model_dump_json(),
        reviewed_by=req.reviewer or current_user.username,
        activated_at=datetime.now(timezone.utc) if target is ApprovalState.ACTIVE else None,
    )
    db.record_audit_event(
        action="amendment_draft_transitioned", actor_username=current_user.username,
        resource_type="amendment_draft", resource_id=draft_id,
        detail=f"-> {updated.approval_state.value}",
    )
    return updated.model_dump(mode="json")


class ApplicabilityEvaluationRequest(BaseModel):
    product_category: Optional[str] = "electronics"
    manufacture_date: Optional[str] = "2022-08-01"
    is_imported: Optional[bool] = False
    sale_type: Optional[str] = "retail"


@app.get("/regulations/drafts/{draft_id}/rules-identified")
def regulations_get_rules_identified(
    draft_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_role("reviewer")),
):
    """
    Return classified rules for reviewer validation:
    - Executable compliance rules (e.g. Rule 2(a)(i), 2(a)(ii), 2(a)(iii), 2(b))
    - Non-executable context/metadata provisions (e.g. Rule 1(1) SHORT_TITLE, Rule 1(2) COMMENCEMENT)
    - Raw extraction/provenance for audit
    """
    row = db.get_amendment_draft(draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Amendment draft not found.")

    payload = row["payload"]
    impact = payload.get("impact") or {}
    meta = impact.get("amendment_metadata") or {}

    # 1. Executable rules identified
    changes_by_rule = {c.get("rule_id"): c for c in payload.get("changes", []) if c.get("rule_id")}
    rules_identified = []
    for v in payload.get("proposed_rule_versions", []):
        conds = v.get("conditions") or {}
        ext_meta = v.get("extraction_metadata") or {}
        rule_id = v.get("rule_id")
        chg = changes_by_rule.get(rule_id) or {}
        
        # Resolve target, item, and operation from conditions, extraction_metadata, or changes
        amendment_target = conds.get("amendment_target") or ext_meta.get("amendment_target")
        amendment_item = conds.get("amendment_item") or ext_meta.get("amendment_item")
        amendment_operation = conds.get("amendment_operation") or ext_meta.get("amendment_operation") or chg.get("change_type")

        # Fallback if unpopulated: derive from rule_id and text if present
        if not amendment_target and v.get("text"):
            from lexmetra_rules.provision_classification import extract_amendment_target
            amendment_target = extract_amendment_target(v.get("text"))
        if not amendment_item and rule_id:
            import re
            m = re.search(r"(\([^)]+\))$", rule_id)
            if m:
                amendment_item = m.group(1)
        if not amendment_operation and v.get("text"):
            from lexmetra_rules.provision_classification import classify_amendment_operation
            amendment_operation = classify_amendment_operation(v.get("text"))

        rules_identified.append({
            "rule_id": rule_id,
            "display_provision": conds.get("source_provision") or rule_id,
            "amendment_target": amendment_target,
            "amendment_item": amendment_item,
            "amendment_operation": amendment_operation,
            "canonical_english_text": v.get("text"),
            "rule_type": conds.get("provision_type") or "SUBSTANTIVE_AMENDMENT",
            "parent_regulation": v.get("regulation") or meta.get("regulation") or "Legal Metrology (Packaged Commodities) Rules, 2011",
            "amendment_version": v.get("version") or meta.get("version_label"),
            "effective_from": v.get("effective_from"),
            "effective_to": v.get("effective_to"),
            "applicability": conds.get("applicability") or {},
            "source_provision": conds.get("source_provision"),
            "source_languages": ["en", "hi"] if "multilingual" in conds or "hi" in (conds.get("metadata_sources") or {}) else ["en"],
            "status": v.get("approval_state", "EXTRACTED"),
            "evidence_requirements": v.get("evidence_requirements", []),
            "metadata_sources": conds.get("metadata_sources", {}),
        })

    # 2. Context / metadata provisions (not executable compliance rules)
    raw_ctx = meta.get("context_provisions") or {}
    context_provisions = []
    for prov_name, prov_data in raw_ctx.items():
        ptype = prov_data.get("provision_type", "METADATA")
        purpose = "Amendment title and version metadata" if ptype == "SHORT_TITLE" else "Determines commencement / legal effective date" if ptype == "COMMENCEMENT" else "Context metadata"
        eff_date = meta.get("effective_date") if ptype == "COMMENCEMENT" else None
        context_provisions.append({
            "provision": prov_name,
            "type": ptype,
            "purpose": purpose,
            "is_executable": False,
            "effective_from": eff_date,
            "title": prov_data.get("title"),
            "version": prov_data.get("version"),
            "source": meta.get("notification_number") or "Gazette Header",
        })

    # Fallback if context_provisions was not pre-populated
    if not context_provisions and meta.get("amendment_name"):
        context_provisions.append({
            "provision": "Rule 1(1)",
            "type": "SHORT_TITLE",
            "purpose": "Amendment title and version identity",
            "is_executable": False,
            "effective_from": None,
            "title": meta.get("full_title"),
            "version": meta.get("version_label"),
            "source": meta.get("notification_number"),
        })
        context_provisions.append({
            "provision": "Rule 1(2)",
            "type": "COMMENCEMENT",
            "purpose": "Determines commencement and legal effective date",
            "is_executable": False,
            "effective_from": meta.get("effective_date"),
            "title": "Commencement on publication date",
            "version": meta.get("version_label"),
            "source": meta.get("notification_number"),
        })

    return {
        "draft_id": draft_id,
        "source_document_id": payload.get("source_document_id"),
        "approval_state": payload.get("approval_state"),
        "rules_identified_count": len(rules_identified),
        "rules_identified": rules_identified,
        "context_provisions_count": len(context_provisions),
        "context_provisions": context_provisions,
        "amendment_metadata": meta,
        "raw_extraction": {
            "source_document_id": payload.get("source_document_id"),
            "extracted_at": payload.get("extracted_at"),
            "changes": payload.get("changes", []),
            "impact": impact,
        },
    }


@app.post("/regulations/drafts/{draft_id}/evaluate-applicability")
def regulations_evaluate_applicability(
    draft_id: str,
    req: ApplicabilityEvaluationRequest,
    current_user: auth.CurrentUser = Depends(auth.require_role("reviewer")),
):
    """
    Evaluate which rules are CONSIDERED (applicable) vs NOT CONSIDERED (excluded)
    for a given product/inspection context, with genuine legal rationale.
    """
    row = db.get_amendment_draft(draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Amendment draft not found.")

    payload = row["payload"]
    rules_considered = []
    rules_not_considered = []

    mfg_date = None
    if req.manufacture_date:
        try:
            mfg_date = date.fromisoformat(req.manufacture_date[:10])
        except ValueError:
            pass

    for v in payload.get("proposed_rule_versions", []):
        rule_id = v.get("rule_id")
        conds = v.get("conditions") or {}
        app = dict(conds.get("applicability") or {})
        display_prov = conds.get("source_provision") or rule_id
        ptype = conds.get("provision_type") or v.get("rule_type")

        # Exclude non-executable context/metadata provisions (e.g. Rule 1(1), 1(2))
        if ptype in ("SHORT_TITLE", "COMMENCEMENT") or v.get("is_substantive") is False:
            rules_not_considered.append({
                "rule": display_prov,
                "rule_id": rule_id,
                "status": "EXCLUDED",
                "reason": f"Provision '{display_prov}' is a non-substantive metadata/commencement provision excluded from compliance evaluation.",
                "applicability_condition": app,
                "evidence_used": {},
            })
            continue

        trigger_date_str = app.get("manufactured_packed_imported_after") or conds.get("substantive_trigger_date")
        trigger_date = None
        if trigger_date_str:
            try:
                trigger_date = date.fromisoformat(str(trigger_date_str)[:10])
            except ValueError:
                pass

        # Preserve and calculate distinct dates without collapsing
        duration_str = str(app.get("duration") or conds.get("applicability_duration") or "").strip()
        end_date_str = app.get("applicability_end_date") or conds.get("applicability_end_date")
        end_date = None
        if end_date_str:
            try:
                end_date = date.fromisoformat(str(end_date_str)[:10])
            except ValueError:
                pass
        elif trigger_date and ("1 year" in duration_str.lower() or "one year" in duration_str.lower()):
            try:
                end_date = date(trigger_date.year + 1, trigger_date.month, trigger_date.day)
            except ValueError:
                end_date = trigger_date + timedelta(days=365)

        # Enrich applicability condition payload with distinct dates
        if v.get("effective_from"):
            app["amendment_effective_date"] = str(v.get("effective_from"))[:10]
        if trigger_date_str:
            app["manufactured_packed_imported_after"] = str(trigger_date_str)[:10]
        if end_date:
            app["applicability_end_date"] = end_date.isoformat()
        if duration_str:
            app["duration"] = duration_str

        scope_str = str(app.get("scope") or conds.get("substantive_trigger_scope") or "").lower()
        rule_text = str(v.get("text") or "").lower()

        is_electronic_rule = "electronic" in scope_str or "electronic" in rule_text or "qr code" in rule_text
        product_cat = (req.product_category or "").lower().strip()
        is_electronic_product = "electronic" in product_cat

        # Check applicability
        if is_electronic_rule:
            if not req.product_category:
                rules_not_considered.append({
                    "rule": display_prov,
                    "rule_id": rule_id,
                    "status": "UNCERTAIN",
                    "reason": "Product category is not provided; cannot determine if electronic product scope applies.",
                    "applicability_condition": app,
                    "evidence_used": {"product_category": req.product_category},
                })
            elif not is_electronic_product:
                rules_not_considered.append({
                    "rule": display_prov,
                    "rule_id": rule_id,
                    "status": "NOT_APPLICABLE",
                    "reason": f"Product category '{req.product_category}' does not satisfy scope condition (requires electronic product).",
                    "applicability_condition": app,
                    "evidence_used": {"product_category": req.product_category},
                })
            elif trigger_date and not mfg_date:
                rules_not_considered.append({
                    "rule": display_prov,
                    "rule_id": rule_id,
                    "status": "UNCERTAIN",
                    "reason": f"Manufacture date is not provided; cannot verify post-{trigger_date_str} trigger condition.",
                    "applicability_condition": app,
                    "evidence_used": {"manufacture_date": req.manufacture_date, "trigger_date": trigger_date_str},
                })
            elif trigger_date and mfg_date and mfg_date <= trigger_date:
                rules_not_considered.append({
                    "rule": display_prov,
                    "rule_id": rule_id,
                    "status": "NOT_APPLICABLE",
                    "reason": f"Manufacture date ({req.manufacture_date}) is on or before substantive trigger date ({trigger_date_str}).",
                    "applicability_condition": app,
                    "evidence_used": {"manufacture_date": req.manufacture_date, "trigger_date": trigger_date_str},
                })
            elif end_date and mfg_date and mfg_date > end_date:
                rules_not_considered.append({
                    "rule": display_prov,
                    "rule_id": rule_id,
                    "status": "NOT_APPLICABLE",
                    "reason": f"Manufacture date ({req.manufacture_date}) is after applicability period end date ({end_date.isoformat()}).",
                    "applicability_condition": app,
                    "evidence_used": {"manufacture_date": req.manufacture_date, "end_date": end_date.isoformat()},
                })
            else:
                rules_considered.append({
                    "rule": display_prov,
                    "rule_id": rule_id,
                    "status": "CONSIDERED / APPLICABLE",
                    "reason": f"Product falls within applicable electronic product scope and meets post-{trigger_date_str or 'July 15, 2022'} trigger condition.",
                    "applicability_condition": app,
                    "evidence_used": {
                        "product_category": req.product_category,
                        "manufacture_date": req.manufacture_date,
                    },
                })
        else:
            # Non-electronic or general rule
            rules_considered.append({
                "rule": display_prov,
                "rule_id": rule_id,
                "status": "CONSIDERED / APPLICABLE",
                "reason": "General legal requirement applicable across package commodity categories.",
                "applicability_condition": app,
                "evidence_used": {"product_category": req.product_category},
            })

    return {
        "draft_id": draft_id,
        "product_context": req.model_dump(),
        "rules_considered_count": len(rules_considered),
        "rules_considered": rules_considered,
        "rules_not_considered_count": len(rules_not_considered),
        "rules_not_considered": rules_not_considered,
    }


@app.post("/regulations/drafts/{draft_id}/publish")
def regulations_publish_draft(
    draft_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_admin),
):
    """
    Atomically publish an approved amendment into PostgreSQL:
    - Writes all canonical rules into regulatory_rule_versions with approval_state = 'ACTIVE'
    - Connects them to the parent regulation (e.g. Legal Metrology Rules, 2011)
    - Updates regulatory_amendments and amendment_drafts
    """
    try:
        receipt = db.publish_amendment_draft(draft_id, published_by=current_user.username)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"Publishing failed: {exc}")

    db.record_audit_event(
        action="amendment_published",
        actor_username=current_user.username,
        resource_type="amendment_draft",
        resource_id=draft_id,
        detail=f"Published {receipt['rules_published_count']} rules into {receipt['parent_regulation']}",
    )
    return receipt


@app.get("/regulations/active-rules")
def regulations_get_active_rules(
    module: str = "lmpc",
    as_of: Optional[str] = None,
    current_user: auth.CurrentUser = Depends(auth.require_role("inspector")),
):
    """Retrieve all currently ACTIVE rules directly from PostgreSQL."""
    as_of_date = None
    if as_of:
        try:
            as_of_date = date.fromisoformat(as_of[:10])
        except ValueError:
            pass

    rows = db.get_active_rule_versions(module_id=module, as_of=as_of_date)
    return {
        "module": module,
        "parent_regulation": "Legal Metrology (Packaged Commodities) Rules, 2011",
        "active_rules_count": len(rows),
        "active_rules": rows,
    }


@app.get("/regulations/verification/{draft_id}")
def regulations_get_verification(
    draft_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_role("reviewer")),
):
    """Inspect full relational database integrity in PostgreSQL."""
    try:
        return db.get_database_verification(draft_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))

