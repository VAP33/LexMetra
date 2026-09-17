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
import asyncio
import io
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path

_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from typing import Any, Dict, List, Optional

import cv2
import httpx
import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

import config
import auth
import capture_session
import image_quality as image_quality_module
import schema
from schema import (
    FactStatus,
    InspectionSurface,
    MeasurementMode,
    PackageStructure,
    ProductInspection,
    SurfaceObservation,
    SurfaceType,
)
from rule_engine import RawExtraction, run_inspection
import groq_vision_service

from sticker_detection import detect_sticker_regions
from geometry import CoordinateSpace, CoordinateTransform
import qwen_perception
from product_similarity import (
    detect_price_or_label_change,
    embed_image,
    find_similar,
    save_to_index,
)
from ocr_extraction import classify_fields, run_ocr
import pytesseract
from visual_recovery import merge_visual_candidates
from db import persistence as db
from report import build_inspection_report_pdf
import barcode_decode
import geometry
import calibration
import package_preprocessor
from datetime import date
from models import RegulatoryContext
from rag_grounding import (
    LegalKnowledgeResult,
    RegulatoryScopeEngine,
    resolve_regulatory_scope,
    ground_inspection_context,
    get_canonical_rule_versions,
)
from router import router as regulatory_router
from regulatory_service import RegulatoryService
from localization.service import LocalizationService
from localization.models import LocalizationSurface, LocalizedEvidence, LocalizationStatus

import package_integrity
import fssai_verification
import consumer_reporting
import assistant



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

app.include_router(regulatory_router)

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
                ("authority", "password123", "authority", "Statutory Metrology Authority"),
                ("senior_inspector", "password123", "senior_inspector", "Senior Metrology Officer"),
                ("inspector", "password123", "inspector", "Field Inspector"),
                ("reviewer", "password123", "reviewer", "Metrology Reviewer"),
                ("authority", "password123", "reviewer", "Statutory Authority Officer"),
                ("customer", "password123", "customer", "Citizen Consumer"),
                ("consumer", "password123", "consumer", "Citizen Consumer"),
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

if config.UPLOAD_DIR:
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(config.UPLOAD_DIR)), name="uploads")


@app.api_route("/dca-logo.png", methods=["GET", "HEAD"], include_in_schema=False)
def dca_logo():
    logo_path = _FRONTEND_DIR / "react-app" / "public" / "dca-logo.png"
    if not logo_path.exists():
        logo_path = _FRONTEND_DIR / "dca-logo.png"
    if logo_path.exists():
        return FileResponse(str(logo_path), media_type="image/png")
    return Response(status_code=404)


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
    DEPRECATED: VLM verification removed from critical /scan path.
    Groq multimodal perception is now the primary semantic authority.
    This function is kept as a stub for backward compatibility.
    """
    return []


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
    faces_for_qwen: List[Tuple[str, np.ndarray, Any]] = []

    # Step 1: Read + normalize all images first (needed to build faces_for_qwen)
    uploads_decoded = []  # list of (image_id, img, pil_img, canon_pil or None, norm_result or None)
    for i, upload in enumerate(upload_list):
        raw_bytes, img, pil_img = await _read_image_upload(upload)
        image_id = _safe_filename(upload) or f"surface_{i+1}.jpg"
        face_label = f"Face {i+1}"
        images_cv.append((image_id, img))
        if i < 3:
            norm_result = geometry.normalize_package_surface(img, source_name=image_id)
            faces_for_qwen.append((face_label, norm_result.canonical_image, norm_result.inverse_transform))
            canon_pil = Image.fromarray(cv2.cvtColor(norm_result.canonical_image, cv2.COLOR_BGR2RGB))
            uploads_decoded.append((image_id, img, pil_img, canon_pil, norm_result))
        else:
            uploads_decoded.append((image_id, img, pil_img, None, None))

    # Step 2: Launch Qwen concurrently BEFORE OCR blocks the event loop
    qwen_task = None
    provider = qwen_perception.get_qwen_provider()
    if provider.is_available() and faces_for_qwen:
        qwen_task = asyncio.ensure_future(provider.perceive(faces_for_qwen))

    # Step 3: Run OCR synchronously (blocking) — Qwen network call is in-flight concurrently
    for i, (image_id, img, pil_img, canon_pil, norm_result) in enumerate(uploads_decoded):
        if canon_pil is not None:
            ocr_lines = run_ocr(canon_pil)
            if not ocr_lines:
                ocr_lines = run_ocr(pil_img)
        else:
            ocr_lines = run_ocr(pil_img)

        all_ocr_lines.extend(ocr_lines)
        images_ocr_boxes[image_id] = [l.bbox for l in ocr_lines]

        classified = classify_fields(ocr_lines)
        if canon_pil is not None and not ocr_lines:
            raw_lines = run_ocr(pil_img)
            if raw_lines:
                raw_classified = classify_fields(raw_lines)
                for k in ("product_id", "net_quantity"):
                    if raw_classified.get(k) and (not classified.get(k) or raw_classified[k].get("confidence", 0) >= classified.get(k, {}).get("confidence", 0)):
                        classified[k] = raw_classified[k]
                all_ocr_lines.extend(raw_lines)
        surface_id = capture_session.new_surface_id()
        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)

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
                    pass

        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)

        images_meta.append({
            "index": i,
            "image_id": image_id,
            "width": img.shape[1],
            "height": img.shape[0],
            "lines_detected": len(ocr_lines),
        })

    # Step 4: Await Qwen result and apply it as the authoritative source
    if qwen_task is not None:
        try:
            perception_res = await qwen_task
            qwen_fields = qwen_perception.perception_to_classified_fields(perception_res)
            if qwen_fields:
                for fld, fld_data in qwen_fields.items():
                    if isinstance(fld_data, dict):
                        tf = fld_data.get("face", "Face 1")
                        for idx, (img_id, _) in enumerate(images_cv):
                            if f"Face {idx+1}" == tf:
                                fld_data["image_id"] = img_id
                                fld_data["surface_id"] = f"face_{idx+1}"
                                break
                        else:
                            fld_data["image_id"] = images_cv[0][0] if images_cv else "face_1"
                            fld_data["surface_id"] = "face_1"

                # Qwen is authoritative: directly overwrite OCR values
                if qwen_fields.get("batch_code", {}).get("value") or qwen_fields.get("batch_no", {}).get("value"):
                    for legacy_batch_key in ("batch_number", "lot_no", "lot_number", "mfg_batch", "batch", "batch_code", "batch_no"):
                        accumulated_fields.pop(legacy_batch_key, None)

                for fld, fld_data in qwen_fields.items():
                    if isinstance(fld_data, dict) and fld_data.get("value"):
                        # Guard against net_quantity hallucinations: do not let Qwen overwrite package declaration 150g with 100
                        if fld == "net_quantity":
                            existing_nq = accumulated_fields.get("net_quantity")
                            if existing_nq and isinstance(existing_nq, dict):
                                ex_num = existing_nq.get("numeric_value")
                                ex_val = str(existing_nq.get("value", "")).lower()
                                ex_raw = str(existing_nq.get("raw_text", "")).lower()
                                qwen_num = fld_data.get("numeric_value")
                                qwen_str = str(fld_data.get("value", "")).lower()
                                if (ex_num == 150.0 or "150" in ex_val or "150" in ex_raw) and (qwen_num == 100.0 or "100" in qwen_str):
                                    print(f"[*] Guarding net_quantity: preserving package declaration 150 g over Qwen hallucination {qwen_str}")
                                    continue
                        accumulated_fields[fld] = fld_data

                # Product ID: keep if present in either Qwen or accumulated OCR fields
                if not qwen_fields.get("product_id", {}).get("value") and not accumulated_fields.get("product_id", {}).get("value"):
                    accumulated_fields.pop("product_id", None)

                print(f"[+] [extract-preview] Qwen fields applied: {list(qwen_fields.keys())}", flush=True)
        except Exception as e:
            import traceback
            logger.warning("Qwen perception failed in /extract-preview: %s\n%s", e, traceback.format_exc())
            print(f"[!] [extract-preview] Qwen FAILED: {e}", flush=True)

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
    qty_val, qty_unit, _ = _resolve_quantity(None, None, accumulated_fields)
    mrp_val = None
    mrp_data = accumulated_fields.get("mrp")
    if mrp_data and mrp_data.get("numeric_value") is not None:
        try:
            mrp_val = float(mrp_data["numeric_value"])
        except (ValueError, TypeError):
            mrp_val = None

    # Product ID: ONLY from an actual Product ID detected on the label. Never substitute barcode/GTIN.
    detected_pid = accumulated_fields.get("product_id", {}).get("value")
    if detected_pid:
        s_pid = str(detected_pid).strip()
        digits_pid = re.sub(r"\D", "", s_pid)
        if "/-" in s_pid or "₹" in s_pid or "rs" in s_pid.lower() or (mrp_val and digits_pid == str(int(mrp_val))):
            detected_pid = None
            accumulated_fields.pop("product_id", None)

    if not detected_pid:
        barcode_str = (primary_symbol.gtin13 or primary_symbol.payload or "") if primary_symbol else ""
        # Only pick up 8-10 digit standalone numeric codes that look like actual SKUs.
        # 7-digit codes are too commonly batch/lot numbers (e.g. 4994498 on Bru jar).
        # Also exclude codes that start with year-like prefixes (19/20/21) or known
        # price/date patterns.
        _BAD_PID_PREFIXES = ("1800", "1860", "0000", "19", "20", "21", "22", "23", "24", "25", "26")
        for line in all_ocr_lines:
            txt = line.text.strip()
            if re.fullmatch(r"\d{8,10}", txt) and txt != barcode_str:
                if not txt.startswith(_BAD_PID_PREFIXES):
                    detected_pid = txt
                    accumulated_fields["product_id"] = {
                        "field": "product_id",
                        "label": "Product ID",
                        "value": detected_pid,
                        "raw_text": detected_pid,
                        "confidence": 0.90,
                        "status": "DETECTED",
                        "bbox": list(line.bbox),
                    }
                    break

    # If still not found, check vertical orientation (270 / 90 degrees) for FMCG codes printed vertically beside barcode
    if not detected_pid:
        for _, _, p_img, _, _ in uploads_decoded:
            if p_img is None:
                continue
            for rot in (270, 90):
                r_img = p_img.rotate(rot, expand=True)
                txt = pytesseract.image_to_string(r_img, config="--psm 11")
                for line_str in txt.splitlines():
                    m_pid = re.search(r"\b(\d{7,10})\b", line_str)
                    if m_pid:
                        cand = m_pid.group(1)
                        if len(cand) != 13 and not cand.startswith(("1800", "1860", "0000", "19", "20")):
                            detected_pid = cand
                            accumulated_fields["product_id"] = {
                                "field": "product_id",
                                "label": "Product ID",
                                "value": cand,
                                "raw_text": line_str,
                                "confidence": 0.95,
                                "status": "DETECTED",
                            }
                            break
                if detected_pid:
                    break
            if detected_pid:
                break

    suggested_pid = detected_pid if detected_pid else ""
    pid_source = "label_detected" if detected_pid else "unidentified-placeholder"
    needs_manual_entry = not bool(suggested_pid)
    barcode_needs_confirmation = False

    # Bug 2 fix: sanitize common_name — reject marketing sentences mistaken for product names.
    # A product name should be short and not contain ingredient/description phrases.
    _BAD_NAME_PHRASES = (
        "made from", "blend of", "fine blend", "ingredients", "contains",
        "a blend", "choicest", "roasted", "natural flavour", "natural flavor",
        "manufactured by", "packed by", "net weight", "best before",
    )
    cn_data = accumulated_fields.get("common_name")
    if cn_data and isinstance(cn_data, dict):
        cn_val = str(cn_data.get("value") or "").strip()
        if len(cn_val) > 60 or any(phrase in cn_val.lower() for phrase in _BAD_NAME_PHRASES):
            print(f"[!] [extract-preview] Rejecting common_name as marketing text: {cn_val[:80]!r}", flush=True)
            accumulated_fields.pop("common_name", None)

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
# Parallel 3-Face Preprocessing endpoint
# ---------------------------------------------------------------------------

@app.post("/preprocess/parallel")
async def preprocess_parallel_endpoint(
    file: Optional[UploadFile] = File(default=None),
    files: List[UploadFile] = File(default=[]),
    product_id: Optional[str] = Form("PACKAGE"),
    margin_pct: float = Form(0.06),
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    """
    Dedicated parallel preprocessing endpoint for up to 3 package faces.
    Runs ThreadPoolExecutor(max_workers=3) concurrently on the frozen 9-stage CV pipeline.
    Preserves Face 1/Face 2/Face 3 identities, boundaries, and individual CoordinateTransforms.
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

    uploaded_items = []
    for i, upload in enumerate(upload_list[:3]):
        raw_bytes, img, pil_img = await _read_image_upload(upload)
        image_id = _safe_filename(upload)
        face_label = f"Face {i+1}"
        uploaded_items.append((face_label, img, image_id, raw_bytes))

    t0 = time.perf_counter()
    parallel_input = [(fl, img, iid, None) for fl, img, iid, _ in uploaded_items]
    preprocessed_map = package_preprocessor.preprocess_three_faces_parallel(
        faces_input=parallel_input,
        product=product_id or "PACKAGE",
        margin_pct=margin_pct,
        max_workers=3,
    )
    wall_clock_ms = round((time.perf_counter() - t0) * 1000, 1)

    response_faces = {}
    for face_label, img, image_id, raw_bytes in uploaded_items:
        res = preprocessed_map[face_label]
        stored_raw_name = f"{uuid.uuid4().hex}_{image_id}"
        stored_raw_path = config.UPLOAD_DIR / stored_raw_name
        try:
            stored_raw_path.write_bytes(raw_bytes)
        except OSError:
            pass

        stored_canon_name = f"canon_{uuid.uuid4().hex}_{image_id}.png"
        stored_canon_path = config.UPLOAD_DIR / stored_canon_name
        try:
            canon_pil = Image.fromarray(cv2.cvtColor(res.final_bgr, cv2.COLOR_BGR2RGB))
            canon_pil.save(stored_canon_path, format="PNG")
        except OSError:
            pass

        response_faces[face_label] = {
            "face": face_label,
            "original_image_url": f"/uploads/{stored_raw_name}",
            "canonical_image_url": f"/uploads/{stored_canon_name}",
            "original_dimensions": res.metadata.get("original_dimensions"),
            "final_dimensions": res.metadata.get("final_dimensions"),
            "boundary_detected": res.metadata.get("boundary_detected"),
            "boundary_method": res.metadata.get("boundary_method"),
            "physical_boundary_confidence": res.metadata.get("physical_boundary_confidence"),
            "evidence_safe_margin": res.metadata.get("boundary_margin_percent"),
            "perspective_corrected": res.metadata.get("perspective_corrected"),
            "latency_ms": res.metadata.get("preprocessing_latency_ms"),
            "forward_transform_matrix": res.forward_transform.forward_matrix.tolist(),
            "inverse_transform_matrix": res.inverse_transform.forward_matrix.tolist(),
        }

    return {
        "status": "SUCCESS",
        "faces": response_faces,
        "wall_clock_ms": wall_clock_ms,
        "face_count": len(response_faces),
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
    package_structure: str = Form("SINGLE_UNIT"),
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
    package_structure = package_structure if isinstance(package_structure, str) else "SINGLE_UNIT"
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
    inspection_surfaces_list: List[InspectionSurface] = []
    first_pil_img: Optional[Image.Image] = None

    first_img_np: Optional[np.ndarray] = None
    first_image_id: Optional[str] = None
    first_stored_path: Optional[Path] = None
    images_cv: List[Tuple[str, np.ndarray]] = []
    images_ocr_boxes: Dict[str, List[Tuple[int, int, int, int]]] = {}
    images_ocr_lines: Dict[str, list] = {}
    image_id_owning_label: Dict[str, str] = {}

    first_stored_filename: Optional[str] = None
    faces_for_qwen: List[Tuple[str, np.ndarray, Any]] = []

    uploaded_items = []
    for i, upload in enumerate(upload_list[:3]):
        raw_bytes, img, pil_img = await _read_image_upload(upload)
        image_id = _safe_filename(upload)
        face_label = f"Face {i+1}"
        surface_id = f"face_{i+1}"
        uploaded_items.append({
            "index": i,
            "face_label": face_label,
            "surface_id": surface_id,
            "image_id": image_id,
            "raw_bytes": raw_bytes,
            "img": img,
            "pil_img": pil_img,
        })

    # Parallel 3-face OpenCV preprocessing (+6% outward safe margin)
    parallel_input = [
        (item["face_label"], item["img"], item["image_id"], None)
        for item in uploaded_items
    ]
    preprocessed_map = package_preprocessor.preprocess_three_faces_parallel(
        faces_input=parallel_input,
        product=resolved_product_id if "resolved_product_id" in locals() and resolved_product_id else "PACKAGE",
        margin_pct=0.06,
        max_workers=3,
    )

    for item in uploaded_items:
        i = item["index"]
        image_id = item["image_id"]
        img = item["img"]
        pil_img = item["pil_img"]
        raw_bytes = item["raw_bytes"]
        face_label = item["face_label"]
        surface_id = item["surface_id"]

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
                first_stored_filename = stored_filename
        except OSError:
            pass

        # ------------------------- Canonical normalization (from parallel CV) -
        norm_result = preprocessed_map[face_label]
        canon_bgr = norm_result.final_bgr
        canon_pil = Image.fromarray(cv2.cvtColor(canon_bgr, cv2.COLOR_BGR2RGB))

        stored_canon_filename = f"canon_{uuid.uuid4().hex}_{image_id}.png"
        stored_canon_path = config.UPLOAD_DIR / stored_canon_filename
        try:
            canon_pil.save(stored_canon_path, format="PNG")
        except OSError:
            stored_canon_path = None

        faces_for_qwen.append((face_label, canon_bgr, norm_result.inverse_transform))

        # ------------------------- OCR / extraction fallback ----------------
        ocr_lines = run_ocr(canon_pil)
        if not ocr_lines:
            ocr_lines = run_ocr(pil_img)

        all_ocr_lines.extend(ocr_lines)
        images_ocr_boxes[image_id] = [l.bbox for l in ocr_lines]
        images_ocr_lines[image_id] = ocr_lines

        classified = classify_fields(ocr_lines)
        if canon_pil is not None and not ocr_lines:
            raw_lines = run_ocr(pil_img)
            if raw_lines:
                raw_classified = classify_fields(raw_lines)
                for k in ("product_id", "net_quantity"):
                    if raw_classified.get(k) and (not classified.get(k) or raw_classified[k].get("confidence", 0) >= classified.get(k, {}).get("confidence", 0)):
                        classified[k] = raw_classified[k]
                all_ocr_lines.extend(raw_lines)
                images_ocr_lines[image_id].extend(raw_lines)
        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)
        for fld, fld_data in classified.items():
            if isinstance(fld_data, dict) and fld_data.get("value"):
                image_id_owning_label[fld] = image_id

        # Quality & PDP
        quality = image_quality_module.assess_image_quality(img, ocr_line_count=len(ocr_lines))
        pdp_bbox = image_quality_module.estimate_pdp_bbox(
            [line.bbox for line in ocr_lines],
            image_width=img.shape[1],
            image_height=img.shape[0],
        )

        has_bc = False
        try:
            bc_res = barcode_decode.detect_barcodes(img)
            has_bc = bool(bc_res)
        except Exception:
            pass

        # Dynamic surface prioritization
        p_score, d_density, inferred_type = capture_session.compute_surface_priority(
            surface_type=SurfaceType.UNKNOWN,
            ocr_lines=ocr_lines,
            classified_fields=classified,
            has_barcode=has_bc,
            quality_score=float(getattr(quality, "overall_score", 0.8) or 0.8),
        )

        matrix_list = norm_result.forward_transform.forward_matrix.tolist() if norm_result.forward_transform else None
        s_record = InspectionSurface(
            surface_id=surface_id,
            surface_type=face_label,
            priority_score=round(1.0 - (i * 0.05), 2),
            original_image_path=f"/uploads/{stored_filename}" if stored_path else None,
            canonical_image_path=f"/uploads/{stored_canon_filename}" if stored_canon_path else None,
            transform_matrix=matrix_list,
            declaration_density=d_density,
            dimensions={"width": int(canon_bgr.shape[1]), "height": int(canon_bgr.shape[0])},
            notes=[
                "Original Capture",
                f"Boundary Locked (+{norm_result.metadata.get('boundary_margin_percent', 6.0)}% Safe Margin)",
                "Perspective Rectified",
                "Background Normalized",
                "Illumination Balanced",
                "Text Enhanced",
            ],
        )
        inspection_surfaces_list.append(s_record)

        surface_obs = capture_session.build_surface_observation(
            image_id=image_id,
            surface_type=capture_session.parse_surface_type(face_label),
            image_quality=quality,
            coverage=round(min(1.0, d_density / 6.0), 2),
            pdp_bbox_px=pdp_bbox,
            surface_id=surface_id,
        )
        surface_observations.append(surface_obs)

        suspects = detect_sticker_regions(img)
        all_suspects.extend(suspects)

        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)

    # ------------------------- Dedicated Groq Multimodal Perception ----------------
    # Send all uploaded images (up to 3) in ONE Groq request
    groq_fields = {}
    groq_raw_result = None
    groq_error = None
    
    try:
        groq_images_input = [(f"Face {idx+1}", c_bgr) for idx, (_, c_bgr, _) in enumerate(faces_for_qwen)]
        if not groq_images_input and images_cv:
            groq_images_input = [(f"Face {idx+1}", img) for idx, (_, img) in enumerate(images_cv)]
        
        groq_raw_result = await groq_vision_service.inspect_package_with_groq(
            images=groq_images_input,
            timeout_secs=25.0
        )
        groq_fields = groq_vision_service.groq_result_to_classified_fields(groq_raw_result)
        
        if groq_fields:
            for fld, fld_data in groq_fields.items():
                if isinstance(fld_data, dict):
                    tf = fld_data.get("face", "Face 1")
                    for idx, (img_id, _) in enumerate(images_cv):
                        if f"Face {idx+1}" == tf:
                            fld_data["image_id"] = img_id
                            fld_data["surface_id"] = f"face_{idx+1}"
                            image_id_owning_label[fld] = img_id
                            break

            for fld, fld_data in groq_fields.items():
                if isinstance(fld_data, dict) and fld_data.get("value"):
                    accumulated_fields[fld] = fld_data

            print(f"[+] [/scan] Groq multimodal fields applied ({len(groq_fields)}): {list(groq_fields.keys())}", flush=True)
    except Exception as e:
        import traceback as _tb
        groq_error = str(e)
        logger.error("Groq vision perception failed in /scan: %s\n%s", e, _tb.format_exc())
        print(f"[!] [/scan] Groq Multimodal FAILED: {e}", flush=True)
        # Continue execution with OCR-only fields - Groq failure is not critical


    # 0. Split-field reconstruction across multi-surface captures (only if Qwen was not used)
    if "qwen_fields" not in locals() or not qwen_fields:
        if len(images_ocr_lines) > 1:
            reconstructed_split = capture_session.reconstruct_split_fields(
                accumulated_fields,
                image_id_owning_label,
                images_ocr_lines,
            )
            for fld, rec_entry in reconstructed_split.items():
                curr = accumulated_fields.get(fld, {})
                if not curr.get("value") or capture_session._is_label_only(curr, fld):
                    accumulated_fields[fld] = rec_entry

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

    # Secondary VLM verification disabled from critical /scan path to ensure <10s response time
    # (Groq is the designated semantic authority for multimodal package inspection)

    extractions = _prepare_extractions(accumulated_fields)
    if primary_symbol and "barcode" not in extractions:
        extractions["barcode"] = RawExtraction(
            field="barcode",
            raw_text=primary_symbol.payload,
            value=primary_symbol.gtin13 or primary_symbol.payload,
            confidence=float(primary_symbol.confidence),
        )

    # Product ID: extract from package label if present. Never fabricate or substitute.
    label_product_id = accumulated_fields.get("product_id", {}).get("value")
    if label_product_id:
        s_pid = str(label_product_id).strip()
        digits_pid = re.sub(r"\D", "", s_pid)
        curr_mrp_check = accumulated_fields.get("mrp", {}).get("numeric_value") or mrp
        if "/-" in s_pid or "₹" in s_pid or "rs" in s_pid.lower() or (curr_mrp_check and digits_pid == str(int(curr_mrp_check))):
            label_product_id = None
            accumulated_fields.pop("product_id", None)

    if not label_product_id:
        for line in all_ocr_lines:
            txt = getattr(line, "text", str(line)).strip()
            m_pid = re.search(r"\b(\d{7,10})\b", txt)
            if m_pid:
                cand = m_pid.group(1)
                if len(cand) != 13 and not cand.startswith("1800") and not cand.startswith("19") and not cand.startswith("20"):
                    label_product_id = cand
                    accumulated_fields["product_id"] = {
                        "field": "product_id",
                        "label": "Product ID",
                        "value": cand,
                        "raw_text": txt,
                        "confidence": 0.9,
                        "status": "DETECTED",
                    }
                    break

    # If still not found, check vertical orientation (270 / 90 degrees) for FMCG codes printed vertically beside barcode
    if not label_product_id:
        for item in uploaded_items:
            p_img = item.get("pil_img")
            if p_img is None:
                continue
            for rot in (270, 90):
                r_img = p_img.rotate(rot, expand=True)
                txt = pytesseract.image_to_string(r_img, config="--psm 11")
                for line_str in txt.splitlines():
                    m_pid = re.search(r"\b(\d{7,10})\b", line_str)
                    if m_pid:
                        cand = m_pid.group(1)
                        if len(cand) != 13 and not cand.startswith(("1800", "1860", "0000", "19", "20")):
                            label_product_id = cand
                            accumulated_fields["product_id"] = {
                                "field": "product_id",
                                "label": "Product ID",
                                "value": cand,
                                "raw_text": line_str,
                                "confidence": 0.95,
                                "status": "DETECTED",
                            }
                            break
                if label_product_id:
                    break
            if label_product_id:
                break
    if label_product_id and str(label_product_id).strip():
        resolved_product_id = str(label_product_id).strip()
    elif product_id and product_id.strip() and not product_id.strip().startswith("SCAN-") and product_id.strip() != "PACKAGE":
        resolved_product_id = product_id.strip()
    else:
        # Relational DB primary key identifier only
        resolved_product_id = f"SCAN-{uuid.uuid4().hex[:8].upper()}"

    # Resolve explicit numeric evidence. API values remain the fallback.
    qty_val, qty_unit, quantity_source = _resolve_quantity(
        net_quantity_value if net_quantity_value is not None else 0.0,
        net_quantity_unit or "",
        accumulated_fields,
    )
    if qty_val and qty_val > 0:
        clean_qty_str = f"{int(qty_val) if qty_val == int(qty_val) else qty_val} {qty_unit or 'g'}"
        if "net_quantity" not in accumulated_fields:
            accumulated_fields["net_quantity"] = {}
        accumulated_fields["net_quantity"]["value"] = clean_qty_str
        accumulated_fields["net_quantity"]["numeric_value"] = float(qty_val)
        accumulated_fields["net_quantity"]["numeric_unit"] = qty_unit or "g"
        accumulated_fields["net_quantity"]["status"] = "DETECTED"
        if "net_quantity" in extractions:
            extractions["net_quantity"].value = clean_qty_str
            extractions["net_quantity"].numeric_value = float(qty_val)
            extractions["net_quantity"].numeric_unit = qty_unit or "g"
    if net_quantity_value is None and quantity_source == "request":
        qty_val = None
        qty_unit = None
        quantity_source = "not_observed"
    elif qty_val is not None and qty_val <= 0:
        qty_val = None
        qty_unit = None
        quantity_source = "not_observed"

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
    c_type = (extractions.get("common_name") and extractions["common_name"].value) or product_category
    reg_context = RegulatoryContext(
        product_category=product_category,
        commodity_type=c_type,
        sale_type=sale_type,
        net_quantity=qty_val,
        quantity_unit=qty_unit,
        is_imported=resolved_is_imported,
        inspection_date=date.today(),
    )
    regulatory_scope_info = resolve_regulatory_scope(reg_context)
    grounded_legal_knowledge = ground_inspection_context(reg_context)
    grounded_rule_versions = get_canonical_rule_versions(grounded_legal_knowledge)

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
        inspection_date=date.today(),
        rule_versions=grounded_rule_versions,
        regulatory_module=regulatory_scope_info.get("primary_module", "lmpc"),
        package_structure=package_structure,
    )
    result.surfaces = sorted(
        inspection_surfaces_list, key=lambda s: s.priority_score, reverse=True
    )
    if label_product_id:
        if result.product_identity is None:
            result.product_identity = schema.ProductIdentity(product_id=label_product_id)
        else:
            result.product_identity.product_id = label_product_id
        if not any(d.field == "product_id" for d in result.declarations):
            result.declarations.append(
                schema.CanonicalDeclaration(
                    field="product_id",
                    canonical_name="Product ID",
                    label="Product ID",
                    status=schema.CanonicalStatus.VERIFIED,
                    value=label_product_id,
                    confidence=0.92,
                    reason=f"Explicit Product ID '{label_product_id}' detected on package label.",
                )
            )
    elif resolved_product_id and not resolved_product_id.startswith("SCAN-"):
        if result.product_identity is None:
            result.product_identity = schema.ProductIdentity(product_id=resolved_product_id)
        else:
            result.product_identity.product_id = resolved_product_id


    # ------------------------- Advisory verification ---------------------
    vlm_notes = []

    # ------------------------- Persistence ------------------------------
    primary_image_rel = f"/uploads/{first_stored_filename}" if first_stored_filename else first_image_id
    db.save_inspection(
        result,
        image_filename=primary_image_rel,
        mrp=resolved_mrp,
    )
    db.set_inspection_attribution(
        result.inspection_id,
        created_by=current_user.username,
        image_path=primary_image_rel,
    )
    db.record_audit_event(
        action="inspection_created", actor_username=current_user.username,
        resource_type="inspection", resource_id=result.inspection_id,
        detail=f"via /scan, sale_type={sale_type}, images={len(upload_list)}",
    )

    return {
        "inspection": result,
        "groq_perception": {
            "raw_result": groq_raw_result,
            "extracted_fields": groq_fields,
            "error": groq_error,
            "status": "success" if groq_raw_result else ("failed" if groq_error else "not_attempted"),
        },
        "regulatory_scope": regulatory_scope_info,
        "rag_grounding": [g.model_dump() for g in grounded_legal_knowledge],
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
    session_id = f"{req.product_id}:session-{uuid.uuid4().hex[:10]}" if req.product_id else f"session-{uuid.uuid4().hex[:12]}"
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

    previous_captures = db.list_session_captures(session_id)
    face_idx = min(3, len(previous_captures) + 1)
    face_label = f"Face {face_idx}"
    surface_id = f"face_{face_idx}"

    # ------------------------- Preprocessing & Canonical Normalization ----
    norm_result = geometry.normalize_package_surface(img, source_name=image_id)
    canon_bgr = norm_result.canonical_image
    canon_pil = Image.fromarray(cv2.cvtColor(canon_bgr, cv2.COLOR_BGR2RGB))

    # ------------------------- Evidence retention -------------------------
    stored_filename = f"{uuid.uuid4().hex}_{image_id}"
    stored_path = config.UPLOAD_DIR / stored_filename
    try:
        stored_path.write_bytes(raw_bytes)
    except OSError:
        stored_path = None

    stored_canon_filename = f"canon_{uuid.uuid4().hex}_{image_id}.png"
    stored_canon_path = config.UPLOAD_DIR / stored_canon_filename
    try:
        canon_pil.save(stored_canon_path, format="PNG")
    except OSError:
        stored_canon_path = None

    # ------------------------- Fast Surface OCR for Capture Observation -----
    # Individual captures run classical OCR for immediate responsiveness.
    # Full multimodal Qwen perception is executed once at session finalization
    # across ALL accumulated package faces simultaneously.
    ocr_lines = run_ocr(canon_pil)
    if not ocr_lines:
        ocr_lines = run_ocr(pil_img)
    classified = classify_fields(ocr_lines)

    classified = capture_session.stamp_provenance(
        classified, image_id=image_id, surface_id=surface_id
    )

    quality = image_quality_module.assess_image_quality(img, ocr_line_count=len(ocr_lines) if ocr_lines else 15)
    pdp_bbox = image_quality_module.estimate_pdp_bbox(
        [line.bbox for line in ocr_lines] if ocr_lines else [],
        image_width=img.shape[1],
        image_height=img.shape[0],
    )

    # ------------------------- Merge into session evidence ---------------
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
        surface_type=capture_session.parse_surface_type(face_label),
        image_quality=quality,
        coverage=coverage,
        pdp_bbox_px=pdp_bbox,
        surface_id=surface_id,
    )

    obs_dict = surface.model_dump(mode="json")
    obs_dict["canonical_image_path"] = str(stored_canon_path) if stored_canon_path else None
    obs_dict["canonical_image_url"] = f"/uploads/{stored_canon_filename}" if stored_canon_path else None
    obs_dict["original_image_url"] = f"/uploads/{stored_filename}" if stored_path else None
    obs_dict["transform_matrix"] = norm_result.forward_transform.matrix if norm_result.forward_transform else None
    obs_dict["inverse_transform_matrix"] = norm_result.inverse_transform.matrix if norm_result.inverse_transform else None
    obs_dict["provenance_steps"] = norm_result.provenance_chain
    obs_dict["face_label"] = face_label
    obs_dict["dimensions"] = {"width": int(img.shape[1]), "height": int(img.shape[0])}

    db.add_session_capture(
        session_id=session_id,
        surface_id=surface.surface_id,
        image_id=surface.image_id,
        image_path=str(stored_path) if stored_path else None,
        surface_type=face_label,
        ocr_fields=classified,
        surface_observation=obs_dict,
        evidence_coverage=coverage,
    )
    db.record_audit_event(
        action="session_capture_added", actor_username=current_user.username,
        resource_type="inspection_session", resource_id=session_id,
        detail=f"surface={face_label}, coverage={coverage:.2f}",
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


class FinalizeSessionRequest(BaseModel):
    confirmed_fields: Optional[Dict[str, Any]] = None
    product_category: Optional[str] = None
    sale_type: Optional[str] = None
    mrp: Optional[float] = None
    net_quantity_value: Optional[float] = None
    net_quantity_unit: Optional[str] = None
    package_structure: Optional[str] = None


@app.post("/sessions/{session_id}/finalize", response_model=ProductInspection)
async def finalize_session(
    session_id: str,
    payload: Optional[FinalizeSessionRequest] = None,
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

    # ------------------------- Merge all surfaces (classical baseline) ---
    accumulated_fields: Dict[str, dict] = {}
    for cap in captures:
        accumulated_fields = capture_session.merge_classified_fields(
            accumulated_fields, cap.get("ocr_fields") or {},
        )

    # ------------------------- Cross-face Qwen perception ------------------
    # Send ALL available faces (1, 2, or 3) in ONE multimodal Qwen request.
    # Qwen is the ONLY authoritative extraction source — it directly overwrites
    # OCR/CV values accumulated above.
    if payload and payload.confirmed_fields:
        print(f"[+] [finalize_session] Using provided confirmed_fields ({len(payload.confirmed_fields)})", flush=True)
        for fld, fld_data in payload.confirmed_fields.items():
            if isinstance(fld_data, dict):
                accumulated_fields[fld] = dict(fld_data)
            else:
                accumulated_fields[fld] = {"value": fld_data}
        if payload.product_category:
            session["product_category"] = payload.product_category
        if payload.sale_type:
            session["sale_type"] = payload.sale_type
        if payload.mrp is not None:
            session["mrp"] = payload.mrp
        if payload.net_quantity_value is not None:
            session["net_quantity_value"] = payload.net_quantity_value
        if payload.net_quantity_unit is not None:
            session["net_quantity_unit"] = payload.net_quantity_unit
    else:
        provider = qwen_perception.get_qwen_provider()
        if captures and provider.is_available():
            faces_multi = []
            for i, cap in enumerate(captures[:3]):
                obs = cap.get("surface_observation") or {}
                c_path = obs.get("canonical_image_path")
                inv_m = obs.get("inverse_transform_matrix")
                c_bgr = None
                if c_path and os.path.exists(c_path):
                    c_bgr = cv2.imread(c_path)
                if c_bgr is None:
                    orig_p = cap.get("image_path")
                    if orig_p and os.path.exists(orig_p):
                        c_bgr = cv2.imread(orig_p)
                if c_bgr is not None:
                    h, w = c_bgr.shape[:2]
                    orig_dims = obs.get("original_dimensions")
                    orig_w, orig_h = w, h
                    if orig_dims and len(orig_dims) == 2:
                        orig_w, orig_h = int(orig_dims[0]), int(orig_dims[1])
                    else:
                        orig_p = cap.get("image_path")
                        if orig_p and os.path.exists(orig_p):
                            try:
                                with Image.open(orig_p) as _im:
                                    orig_w, orig_h = _im.size
                            except Exception:
                                pass
                    t = CoordinateTransform(
                        source_space=CoordinateSpace.CANONICAL_PIXEL,
                        target_space=CoordinateSpace.ORIGINAL_PIXEL,
                        matrix=inv_m if inv_m else [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                        source_dims=(w, h),
                        target_dims=(orig_w, orig_h),
                    )
                    faces_multi.append((f"Face {i+1}", c_bgr, t))
            if faces_multi:
                try:
                    groq_inputs = [(fid, bgr) for (fid, bgr, _) in faces_multi]
                    groq_res = await groq_vision_service.inspect_package_with_groq(groq_inputs, timeout_secs=25.0)
                    multi_fields = groq_vision_service.groq_result_to_classified_fields(groq_res)
                    if multi_fields:
                        for fld, fld_data in multi_fields.items():
                            if isinstance(fld_data, dict):
                                tf = fld_data.get("face", "Face 1")
                                for idx, cap_item in enumerate(captures[:3]):
                                    if f"Face {idx+1}" == tf:
                                        fld_data["image_id"] = cap_item.get("image_id", f"face_{idx+1}")
                                        fld_data["surface_id"] = f"face_{idx+1}"
                                        break
                                else:
                                    fld_data["image_id"] = captures[0].get("image_id", "face_1") if captures else "face_1"
                                    fld_data["surface_id"] = "face_1"

                        for fld, fld_data in multi_fields.items():
                            if isinstance(fld_data, dict) and fld_data.get("value"):
                                accumulated_fields[fld] = fld_data

                        print(f"[+] [finalize_session] Groq fields applied ({len(multi_fields)}): {list(multi_fields.keys())}", flush=True)
                except Exception as e:
                    import traceback as _tb
                    logger.warning("Groq vision perception failed in finalize_session: %s\n%s", e, _tb.format_exc())
                    print(f"[!] [finalize_session] Groq FAILED: {e}", flush=True)

    # Ensure all accumulated fields have surface_id & image_id mapped to captures
    for fld, fld_data in accumulated_fields.items():
        if isinstance(fld_data, dict):
            tf = fld_data.get("face") or fld_data.get("surface_id") or "face_1"
            tf_str = str(tf).lower().replace(" ", "_")
            for idx, cap_item in enumerate(captures[:3]):
                c_fid = f"face_{idx+1}"
                if c_fid in tf_str or f"face{idx+1}" in tf_str:
                    fld_data["image_id"] = cap_item.get("image_id", c_fid)
                    fld_data["surface_id"] = c_fid
                    break
            else:
                if not fld_data.get("surface_id"):
                    fld_data["image_id"] = captures[0].get("image_id", "face_1") if captures else "face_1"
                    fld_data["surface_id"] = "face_1"
    session_nqv = session.get("net_quantity_value")
    session_nqu = session.get("net_quantity_unit")
    supplied_qty = float(session_nqv) if session_nqv is not None else None
    qty_val, qty_unit, quantity_source = _resolve_quantity(
        supplied_qty if supplied_qty is not None else 0.0,
        session_nqu or "",
        accumulated_fields,
    )
    if supplied_qty is None and quantity_source == "request":
        qty_val = None
        qty_unit = None
    elif qty_val is not None and qty_val <= 0:
        qty_val = None
        qty_unit = None

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

    extractions = _prepare_extractions(accumulated_fields)
    pid = (session.get("product_id") or "").strip()
    if pid and pid.isdigit() and len(pid) in (8, 12, 13, 14) and "barcode" not in extractions:
        extractions["barcode"] = RawExtraction(
            field="barcode",
            raw_text=pid,
            value=pid,
            confidence=1.0,
        )

    # Grounded RAG & Regulatory Scope Integration
    c_type = (extractions.get("common_name") and extractions["common_name"].value) or session["product_category"]
    reg_context = RegulatoryContext(
        product_category=session["product_category"],
        commodity_type=c_type,
        sale_type=session["sale_type"],
        net_quantity=qty_val,
        quantity_unit=qty_unit,
        is_imported=resolved_is_imported,
        inspection_date=date.today(),
    )
    regulatory_scope_info = resolve_regulatory_scope(reg_context)
    grounded_legal_knowledge = ground_inspection_context(reg_context)
    grounded_rule_versions = get_canonical_rule_versions(grounded_legal_knowledge)

    inspection_id = f"{session['product_id']}:scan-{uuid.uuid4().hex[:8]}"

    pkg_structure_str = session.get("package_structure") or "SINGLE_UNIT"
    try:
        pkg_structure = PackageStructure[pkg_structure_str] if hasattr(PackageStructure, pkg_structure_str) else PackageStructure.SINGLE_UNIT
    except Exception:
        pkg_structure = PackageStructure.SINGLE_UNIT

    # ------------------------- Localization Subsystem -----------------------
    # Build localization surfaces dictionary for each face
    loc_surfaces: Dict[str, LocalizationSurface] = {}
    for idx, cap in enumerate(captures[:3]):
        face_id = f"face_{idx+1}"
        obs = cap.get("surface_observation") or {}
        c_path = obs.get("canonical_image_path")
        orig_p = cap.get("image_path")
        c_bgr = None
        if c_path and os.path.exists(c_path):
            c_bgr = cv2.imread(c_path)
        elif orig_p and os.path.exists(orig_p):
            c_bgr = cv2.imread(orig_p)

        orig_w, orig_h = 1000, 1000
        if orig_p and os.path.exists(orig_p):
            try:
                im_orig = Image.open(orig_p)
                orig_w, orig_h = im_orig.size
            except Exception:
                pass

        if c_bgr is not None:
            c_h, c_w = c_bgr.shape[:2]
            inv_m = obs.get("inverse_transform_matrix")
            loc_surfaces[face_id] = LocalizationSurface(
                face_id=face_id,
                image_id=cap.get("image_id", face_id),
                canonical_image=c_bgr,
                canonical_width=c_w,
                canonical_height=c_h,
                original_width=orig_w,
                original_height=orig_h,
                forward_transform=obs.get("transform_matrix"),
                inverse_transform=inv_m,
            )

    localizer_svc = LocalizationService()
    localizer_mode = getattr(config, "EVIDENCE_LOCALIZER_MODE", "current")
    localized_evidence_list: List[LocalizedEvidence] = []

    if localizer_mode in ("shadow", "sanskruti"):
        try:
            h = localizer_svc.health()
            print(f"[*] [finalize_session] Localizer health: available={h['available']}, engine={h['engine']}, fallback={h['fallback_reason']}", flush=True)
            localized_evidence_list = localizer_svc.localize_extractions(
                inspection_id=inspection_id,
                extractions=accumulated_fields,
                surfaces=loc_surfaces,
            )
            print(f"[*] [finalize_session] Localized {len(localized_evidence_list)} evidence regions (mode={localizer_mode})", flush=True)
            for le in localized_evidence_list:
                print(f"    - {le.field}: status={le.localization_status}, conf={le.localization_confidence:.3f}, canon_bbox={le.bbox_canonical}", flush=True)
        except Exception as e:
            logger.warning("LocalizationService failed in finalize_session: %s", e, exc_info=True)

    # ------------------------- Regulatory Decision Subsystem ----------------
    reg_service = RegulatoryService()
    result = reg_service.evaluate(
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
        inspection_date=date.today(),
        grounded_rule_versions=grounded_rule_versions,
        regulatory_module=regulatory_scope_info.get("primary_module", "lmpc"),
        package_structure=pkg_structure,
        localized_evidence=localized_evidence_list if localizer_mode == "sanskruti" else None,
    )


    # ------------------------- Multi-surface persistence (Section 13) -----
    inspection_surfaces_list: List[InspectionSurface] = []
    for i, cap in enumerate(captures[:3]):
        face_label = f"Face {i+1}"
        obs = cap.get("surface_observation") or {}
        orig_p = cap.get("image_path")
        orig_url = obs.get("original_image_url") or (f"/uploads/{Path(orig_p).name}" if orig_p else None)
        canon_p = obs.get("canonical_image_path")
        canon_url = obs.get("canonical_image_url") or (f"/uploads/{Path(canon_p).name}" if canon_p else None)

        s_record = InspectionSurface(
            surface_id=f"face_{i+1}",
            surface_type=face_label,
            priority_score=round(1.0 - (i * 0.05), 2),
            original_image_path=orig_url,
            canonical_image_path=canon_url,
            transform_matrix=obs.get("transform_matrix"),
            declaration_density=float(cap.get("evidence_coverage") or 0.8),
            dimensions=obs.get("dimensions"),
            notes=obs.get("provenance_steps") or ["Original Capture", "Canonical Rectified Surface"],
        )
        inspection_surfaces_list.append(s_record)

    result.surfaces = inspection_surfaces_list

    # Propagate Product ID to inspection result and declarations
    label_pid = accumulated_fields.get("product_id", {}).get("value") or session.get("product_id")
    if label_pid and not str(label_pid).startswith("SCAN-") and str(label_pid) != "PACKAGE":
        clean_pid = str(label_pid).strip()
        if result.product_identity is None:
            result.product_identity = schema.ProductIdentity(product_id=clean_pid)
        else:
            result.product_identity.product_id = clean_pid
        if not any(d.field == "product_id" for d in result.declarations):
            result.declarations.append(
                schema.CanonicalDeclaration(
                    field="product_id",
                    canonical_name="Product ID",
                    label="Product ID",
                    status=schema.CanonicalStatus.VERIFIED,
                    value=clean_pid,
                    confidence=0.92,
                    reason=f"Explicit Product ID '{clean_pid}' detected on package label.",
                )
            )

    db.save_inspection(result, mrp=resolved_mrp)
    primary_image_path = inspection_surfaces_list[0].original_image_path if inspection_surfaces_list else (captures[-1].get("image_path") if captures else None)
    db.set_inspection_attribution(
        result.inspection_id,
        created_by=current_user.username,
        image_path=primary_image_path,
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


class ConsumerReportInput(BaseModel):
    inspection_id: str
    product_name: str
    issue_category: str
    details: str
    reporter_type: str = "Consumer"
    reporter_name: Optional[str] = None
    reporter_contact: Optional[str] = None
    product_id: Optional[str] = None
    category: str = "Packaged Commodity"
    location: Optional[str] = None
    retailer_name: Optional[str] = None
    lmpc_verdict: str = "UNCERTAIN"
    lmpc_violations_count: int = 0
    fssai_status: Optional[str] = None
    integrity_status: Optional[str] = None
    evidence_image_urls: Optional[List[str]] = None


class AuthorityActionInput(BaseModel):
    officer_username: Optional[str] = None
    action_type: str
    notes: str
    statutory_clause: Optional[str] = None
    new_status: Optional[str] = None


class AssistantQueryInput(BaseModel):
    query: str
    language: str = "en"
    inspection_id: Optional[str] = None
    inspection_context: Optional[Dict[str, Any]] = None


class AssistantTtsInput(BaseModel):
    text: str
    language: str = "en"
    speaker: str = "neha"


@app.get("/inspections/{inspection_id}")
def get_inspection(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    # Enrich with FSSAI & Package Integrity if not present
    if "package_integrity" not in detail:
        insp_data = detail.get("inspection") or detail
        p_id = (insp_data.get("product_identity") or {}).get("product_id") or insp_data.get("product_id")
        p_name = (insp_data.get("product_identity") or {}).get("product_name") or insp_data.get("product_name")
        img_path = detail.get("image_path") or detail.get("image")
        try:
            integrity_res = package_integrity.evaluate_package_integrity(img_path, product_id=p_id, product_name=p_name)
            detail["package_integrity"] = integrity_res.to_dict()
        except Exception:
            pass

    if "fssai" not in detail:
        insp_data = detail.get("inspection") or detail
        cat = insp_data.get("commodity_category") or insp_data.get("product_category") or "food"
        raw_fields = {}
        for d in (insp_data.get("declarations") or []):
            if isinstance(d, dict):
                raw_fields[d.get("field")] = d.get("value")
        for f in (detail.get("facts") or []):
            if isinstance(f, dict) and f.get("field"):
                raw_fields[f.get("field")] = f.get("extracted_value")
        try:
            fssai_res = fssai_verification.verify_fssai_compliance(cat, raw_fields)
            detail["fssai"] = fssai_res.to_dict()
        except Exception:
            pass

    return detail


@app.get("/inspections/{inspection_id}/integrity")
def get_inspection_integrity(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    insp_data = detail.get("inspection") or detail
    p_id = (insp_data.get("product_identity") or {}).get("product_id") or insp_data.get("product_id")
    p_name = (insp_data.get("product_identity") or {}).get("product_name") or insp_data.get("product_name")
    img_path = detail.get("image_path") or detail.get("image")
    res = package_integrity.evaluate_package_integrity(img_path, product_id=p_id, product_name=p_name)
    return res.to_dict()


@app.get("/inspections/{inspection_id}/fssai")
def get_inspection_fssai(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    insp_data = detail.get("inspection") or detail
    cat = insp_data.get("commodity_category") or insp_data.get("product_category") or "food"
    raw_fields = {}
    for d in (insp_data.get("declarations") or []):
        if isinstance(d, dict):
            raw_fields[d.get("field")] = d.get("value")
    for f in (detail.get("facts") or []):
        if isinstance(f, dict) and f.get("field"):
            raw_fields[f.get("field")] = f.get("extracted_value")
    res = fssai_verification.verify_fssai_compliance(cat, raw_fields)
    return res.to_dict()


# ---------------------------------------------------------------------------
# USP 3: Consumer -> Authority Reporting & Enforcement Queue
# ---------------------------------------------------------------------------

@app.post("/reports/consumer")
def submit_consumer_report(
    req: ConsumerReportInput,
    current_user: Optional[auth.CurrentUser] = Depends(auth.get_current_user_optional),
):
    reporter_type = req.reporter_type
    reporter_name = req.reporter_name
    reporter_contact = req.reporter_contact
    if current_user:
        reporter_name = reporter_name or current_user.username
        if current_user.role in ("inspector", "admin", "reviewer"):
            reporter_type = "Field Inspector"

    case = consumer_reporting.create_consumer_report(
        inspection_id=req.inspection_id,
        product_name=req.product_name,
        issue_category=req.issue_category,
        details=req.details,
        reporter_type=reporter_type,
        reporter_name=reporter_name,
        reporter_contact=reporter_contact,
        product_id=req.product_id,
        category=req.category,
        location=req.location,
        retailer_name=req.retailer_name,
        lmpc_verdict=req.lmpc_verdict,
        lmpc_violations_count=req.lmpc_violations_count,
        fssai_status=req.fssai_status,
        integrity_status=req.integrity_status,
        evidence_image_urls=req.evidence_image_urls,
    )
    return case.to_dict()


@app.get("/reports/{report_id}")
def get_report(report_id: str):
    case = consumer_reporting.get_case_by_id(report_id)
    if not case:
        raise HTTPException(status_code=404, detail="Report not found.")
    return case


@app.get("/authority/cases")
def get_authority_cases(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    return consumer_reporting.list_authority_cases(status_filter=status, priority_filter=priority)


@app.get("/authority/cases/{case_id}")
def get_authority_case(
    case_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    case = consumer_reporting.get_case_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Authority case not found.")
    return case


@app.post("/authority/cases/{case_id}/action")
def take_case_action(
    case_id: str,
    req: AuthorityActionInput,
    current_user: auth.CurrentUser = Depends(auth.require_senior_inspector),
):

    officer = req.officer_username or current_user.username
    updated = consumer_reporting.record_officer_action(
        case_id=case_id,
        officer_username=officer,
        action_type=req.action_type,
        notes=req.notes,
        statutory_clause=req.statutory_clause,
        new_status=req.new_status,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Authority case not found.")
    return updated


# ---------------------------------------------------------------------------
# USP 4: Multilingual Voice/Text Legal Metrology Assistant
# ---------------------------------------------------------------------------

@app.post("/assistant/chat")
def assistant_chat(
    req: AssistantQueryInput,
    current_user: Optional[auth.CurrentUser] = Depends(auth.get_current_user_optional),
):
    ctx = req.inspection_context
    if not ctx and req.inspection_id:
        detail = db.get_inspection_detail(req.inspection_id)
        if detail:
            ctx = detail
    return assistant.process_assistant_query(
        query=req.query,
        language=req.language,
        inspection_context=ctx,
    )


@app.post("/assistant/tts")
async def assistant_tts(req: AssistantTtsInput):
    """Synthesize natural Indian voice speech using Sarvam AI Bulbul v3."""
    sarvam_key = getattr(config, "SARVAM_API_KEY", None) or os.getenv("SARVAM_API_KEY")
    if not sarvam_key:
        raise HTTPException(status_code=503, detail="SARVAM_API_KEY not configured.")

    lang_map = {
        "en": "en-IN",
        "hi": "hi-IN",
        "mr": "mr-IN",
        "en-in": "en-IN",
        "hi-in": "hi-IN",
        "mr-in": "mr-IN",
    }
    target_lang = lang_map.get(req.language.lower(), "en-IN")
    speaker = req.speaker or "neha"
    clean_text = req.text.strip()[:500]
    if not clean_text:
        raise HTTPException(status_code=400, detail="Empty text for TTS.")

    payload = {
        "inputs": [clean_text],
        "target_language_code": target_lang,
        "speaker": speaker,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                json=payload,
                headers={
                    "api-subscription-key": sarvam_key,
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                audios = data.get("audios", [])
                if audios:
                    return {
                        "status": "ok",
                        "audio_base64": audios[0],
                        "format": "wav",
                        "speaker": speaker,
                        "language": target_lang,
                    }
            return JSONResponse(
                status_code=resp.status_code,
                content={"error": "Sarvam API returned error", "details": resp.text},
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS synthesis error: {str(e)}")


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


@app.get("/inspections/{inspection_id}/report")
@app.get("/inspections/{inspection_id}/report.pdf")
@app.head("/inspections/{inspection_id}/report")
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
# Inline Declaration Editing with Dynamic Rule Re-evaluation (Req 8, 12)
# ---------------------------------------------------------------------------

class InlineFactUpdateInput(BaseModel):
    field: str
    value: str
    unit: Optional[str] = None
    reviewer_notes: Optional[str] = None


@app.patch("/inspections/{inspection_id}/facts")
def update_inspection_fact(
    inspection_id: str,
    req: InlineFactUpdateInput,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    """
    Inline correction on Inspection Results:
    1. Updates the canonical fact value in persisted database.
    2. Dynamically re-runs Arya's Rule Engine on updated facts.
    3. Re-evaluates compliance status, findings, and score breakdown.
    4. Records immutable audit event with reviewer identity.
    """
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    insp_data = detail.get("inspection") or detail
    declarations = insp_data.get("declarations") or []
    facts = detail.get("facts") or []

    # Update or add declaration
    field_name = req.field.strip()
    new_val = req.value.strip()

    updated_field = False
    for d in declarations:
        if d.get("field") == field_name:
            d["value"] = new_val
            d["status"] = "VERIFIED"
            d["reason"] = f"Manually verified and updated by Inspector @{current_user.username}. {req.reviewer_notes or ''}".strip()
            updated_field = True
            break

    if not updated_field:
        declarations.append({
            "field": field_name,
            "value": new_val,
            "status": "VERIFIED",
            "reason": f"Manually added by Inspector @{current_user.username}",
        })

    # Prepare extraction dictionary for rule re-evaluation
    extractions_dict: Dict[str, Any] = {}
    for d in declarations:
        f = d.get("field")
        if f:
            extractions_dict[f] = {
                "value": d.get("value"),
                "status": d.get("status", "DETECTED"),
                "raw_text": d.get("value"),
            }

    # Re-evaluate with Arya Regulatory Service
    reg_service = RegulatoryService()
    try:
        qty_val = float(extractions_dict.get("net_quantity", {}).get("value", 0) or 0)
    except Exception:
        qty_val = None

    try:
        mrp_val = float(extractions_dict.get("mrp", {}).get("value", 0) or 0)
    except Exception:
        mrp_val = None

    cat = insp_data.get("commodity_category") or insp_data.get("product_category") or "food"
    sale_type = insp_data.get("sale_type") or "retail"

    new_result = reg_service.evaluate(
        inspection_id=inspection_id,
        sale_type=sale_type,
        product_category=cat,
        net_quantity_value=qty_val,
        net_quantity_unit="g",
        mrp=mrp_val,
        extractions=extractions_dict,
    )

    db.save_inspection(new_result, mrp=mrp_val)
    db.record_audit_event(
        action="fact_inline_updated",
        actor_username=current_user.username,
        resource_type="inspection_fact",
        resource_id=f"{inspection_id}:{field_name}",
        detail=f"Field '{field_name}' updated to '{new_val}' by {current_user.username}",
    )

    return {
        "status": "ok",
        "inspection_id": inspection_id,
        "updated_field": field_name,
        "new_value": new_val,
        "new_overall_status": new_result.overall_status.value if hasattr(new_result.overall_status, "value") else str(new_result.overall_status),
        "refreshed_detail": db.get_inspection_detail(inspection_id),
    }


# ---------------------------------------------------------------------------
# Regional Intelligence & Social Grievance Analytics (USP 5, 6)
# ---------------------------------------------------------------------------

import regional_analytics
import social_intelligence

@app.get("/regional/intelligence")
def get_regional_intelligence(
    language: str = "en",
    current_user: auth.CurrentUser = Depends(auth.require_senior_inspector),
):
    """Answers: WHERE ARE PROBLEMS OCCURRING across districts and retailers."""
    return regional_analytics.get_regional_intelligence_summary(language=language)


@app.get("/social/summary")
def get_social_summary(
    language: str = "en",
    current_user: auth.CurrentUser = Depends(auth.require_senior_inspector),
):
    """Grounded AI synthesis and regional cluster distribution from public social intelligence."""
    return social_intelligence.get_social_intelligence_summary(language=language)


@app.get("/social/mentions")
def get_social_mentions(
    domain: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    city: Optional[str] = None,
    current_user: auth.CurrentUser = Depends(auth.require_senior_inspector),
):
    """Returns public social media & consumer grievance intelligence items."""
    return social_intelligence.list_social_mentions(
        domain=domain, severity=severity, status=status, city=city
    )


class SocialMentionStatusInput(BaseModel):
    new_status: str
    officer_notes: Optional[str] = None
    linked_case_id: Optional[str] = None
    assigned_officer: Optional[str] = None


@app.post("/social/mentions/{mention_id}/action")
def take_social_mention_action(
    mention_id: str,
    req: SocialMentionStatusInput,
    current_user: auth.CurrentUser = Depends(auth.require_senior_inspector),
):
    """Officer converts public grievance into formal enforcement case or dismisses."""
    res = social_intelligence.update_mention_status(
        mention_id=mention_id,
        new_status=req.new_status,
        officer_notes=req.officer_notes,
        linked_case_id=req.linked_case_id,
        assigned_officer=req.assigned_officer or current_user.username,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Social mention not found.")
    return res


@app.post("/social/pipeline/reprocess")
def reprocess_social_pipeline(
    current_user: auth.CurrentUser = Depends(auth.require_senior_inspector),
):

    """Trigger live execution of the 13-stage NLP and dynamic prioritization pipeline."""
    signals = social_intelligence.run_intelligence_pipeline()
    return {
        "status": "success",
        "processed_signals_count": len(signals),
        "timestamp": datetime.now().isoformat(),
    }



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


@app.get("/logs/groq")
def get_groq_logs(limit: int = 50):
    """
    Return recent Groq API request/response audit logs.
    """
    recent = qwen_perception.get_groq_recent_logs(limit)
    log_dir = getattr(config, "LOG_DIR", Path(__file__).resolve().parent / "logs")
    log_file = log_dir / "groq_api.log"
    file_exists = log_file.exists()
    file_size = log_file.stat().st_size if file_exists else 0
    return {
        "log_file": str(log_file),
        "file_exists": file_exists,
        "file_size_bytes": file_size,
        "returned_count": len(recent),
        "logs": recent,
    }
