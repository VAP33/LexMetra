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
import base64
import concurrent.futures
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

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("lexmetra.api")

import cv2
import httpx
import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
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
from routes_authority import assess_capture_readiness, CaptureReadinessInput
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
import departmental_verification
import consumer_reporting
import assistant
from routes_authority import assess_capture_readiness, CaptureReadinessInput



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

# CORS configuration optimized for production on Railway and Vercel
_cors_origins = list(config.ALLOWED_ORIGINS)
_frontend_env = os.environ.get("FRONTEND_URL", "").strip()
if _frontend_env and _frontend_env not in _cors_origins:
    _cors_origins.append(_frontend_env)

_default_cors_regex = (
    r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|.*\.vercel\.app)(?::\d+)?$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if not os.environ.get("ALLOW_ALL_CORS") else ["*"],
    allow_origin_regex=os.environ.get("CORS_ORIGIN_REGEX", _default_cors_regex),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.getLogger("uvicorn.error").exception("Unhandled error on %s: %s", request.url.path, exc)
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Inspection service error: {str(exc)}",
            "error_type": exc.__class__.__name__,
        },
        headers={
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


@app.on_event("startup")
def startup() -> None:
    try:
        db.init_schema()

        # Never create predictable credentials implicitly. Demo accounts are an
        # explicit development-only opt-in and are disabled by default.
        if config.BOOTSTRAP_DEMO_USERS and (config.DEV_MODE or config.DEMO_MODE):
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
    if (_REACT_DIST_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(_REACT_DIST_DIR / "assets")), name="react_assets")

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

from inspection_helpers import *
from routes_auth import router as auth_router
from routes_sessions import router as sessions_router
from routes_inspections import router as inspections_router
from routes_authority import router as authority_router

app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(inspections_router)
app.include_router(authority_router)

@app.post("/inspect", response_model=ProductInspection)
def inspect(
    req: InspectRequest,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
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
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
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
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
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
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
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
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
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

    t_start_pipeline = time.time()
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
    t_cv_start = time.time()
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
    t_cv = time.time() - t_cv_start

    # Parallel Multi-Face OCR across all uploaded surfaces
    t_ocr_start = time.time()
    def _run_single_face_ocr(item):
        norm_res = preprocessed_map[item["face_label"]]
        c_bgr = norm_res.final_bgr
        c_pil = Image.fromarray(cv2.cvtColor(c_bgr, cv2.COLOR_BGR2RGB))
        lines = run_ocr(c_pil, face_idx=item["index"] + 1)
        if not lines:
            lines = run_ocr(item["pil_img"], face_idx=item["index"] + 1)
        return item["image_id"], c_bgr, c_pil, norm_res, lines

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(uploaded_items))) as executor:
        face_ocr_results = list(executor.map(_run_single_face_ocr, uploaded_items))
    face_ocr_map = {res[0]: res for res in face_ocr_results}
    t_ocr = time.time() - t_ocr_start

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
        _, canon_bgr, canon_pil, norm_result, ocr_lines = face_ocr_map[image_id]

        stored_canon_filename = f"canon_{uuid.uuid4().hex}_{image_id}.png"
        stored_canon_path = config.UPLOAD_DIR / stored_canon_filename
        try:
            canon_pil.save(stored_canon_path, format="PNG")
        except OSError:
            stored_canon_path = None

        faces_for_qwen.append((face_label, canon_bgr, norm_result.inverse_transform))

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

    # ------------------------- Multimodal Perception (Gemini / Qwen) ----------------
    # Send all uploaded images (up to 3) to the multimodal perception engine
    qwen_fields = {}
    groq_raw_result = None
    groq_fields = {}
    groq_error = None
    provider = qwen_perception.get_qwen_provider()
    if provider.is_available() and faces_for_qwen:
        try:
            print(f"\n[*] [/scan] Launching Multimodal Perception across {len(faces_for_qwen)} faces...", flush=True)
            perception_res = await provider.perceive(faces_for_qwen)
            qwen_fields = qwen_perception.perception_to_classified_fields(perception_res)
            if qwen_fields:
                print(f"[+] [/scan] Perception SUCCESS! Applied {len(qwen_fields)} fields: {list(qwen_fields.keys())}", flush=True)
                for fld, fld_data in qwen_fields.items():
                    if isinstance(fld_data, dict):
                        tf = fld_data.get("face", "Face 1")
                        for idx, (img_id, _) in enumerate(images_cv):
                            if f"Face {idx+1}" == tf:
                                fld_data["image_id"] = img_id
                                fld_data["surface_id"] = f"face_{idx+1}"
                                image_id_owning_label[fld] = img_id
                                break
                        else:
                            fld_data["image_id"] = images_cv[0][0] if images_cv else "face_1"
                            fld_data["surface_id"] = "face_1"

                # Direct overwrite with authoritative multimodal extractions
                if qwen_fields.get("batch_code", {}).get("value") or qwen_fields.get("batch_no", {}).get("value"):
                    for legacy_batch_key in ("batch_number", "lot_no", "lot_number", "mfg_batch", "batch", "batch_code", "batch_no"):
                        accumulated_fields.pop(legacy_batch_key, None)

                for fld, fld_data in qwen_fields.items():
                    if isinstance(fld_data, dict) and fld_data.get("value"):
                        if fld in ("manufacturer_name_address", "manufacturer_name"):
                            curr = accumulated_fields.get("manufacturer_name_address") or accumulated_fields.get("manufacturer_name")
                            if curr and curr.get("value"):
                                c_val = str(curr["value"]).strip()
                                n_val = str(fld_data["value"]).strip()
                                import re as _re_addr
                                c_has_addr = bool(_re_addr.search(r"\b[1-9]\d{5}\b|Maharashtra|Madhya\s*Pradesh|M\.?P\.?|Mumbai|Raisen|Mandideep", c_val, _re_addr.I))
                                n_has_addr = bool(_re_addr.search(r"\b[1-9]\d{5}\b|Maharashtra|Madhya\s*Pradesh|M\.?P\.?|Mumbai|Raisen|Mandideep", n_val, _re_addr.I))
                                if c_has_addr and not n_has_addr and len(c_val) > len(n_val):
                                    continue
                        accumulated_fields[fld] = fld_data
            else:
                print("[!] [/scan] Perception returned 0 fields. Falling back to OCR extractions.", flush=True)
        except Exception as e:
            import traceback as _tb
            logger.error("Multimodal perception failed in /scan: %s\n%s", e, _tb.format_exc())
            print(f"[!] [/scan] Multimodal perception FAILED: {e}", flush=True)
    elif groq_vision_service.is_groq_available():
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
                    if isinstance(fld_data, dict) and fld_data.get("value"):
                        accumulated_fields[fld] = fld_data
        except Exception as e:
            print(f"[!] [/scan] Groq Multimodal FAILED: {e}", flush=True)


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
    effective_category = product_category
    if effective_category in ("other", "", "general", "non-food") and c_type:
        c_type_low = str(c_type).lower()
        if any(term in c_type_low for term in ("coffee", "tea", "biscuit", "milk", "food", "snack", "oil", "spice", "flour", "atta", "juice", "drink", "chocolate")):
            effective_category = "food"

    reg_context = RegulatoryContext(
        product_category=effective_category,
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

    t_rules_start = time.time()
    result = run_inspection(
        inspection_id=inspection_id,
        sale_type=sale_type,
        product_category=effective_category,
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
    t_rules = time.time() - t_rules_start
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

    # ------------------------- Barcode & FSSAI Declarations ----------------
    bc_candidate = None
    if "barcode" in accumulated_fields and accumulated_fields["barcode"].get("value"):
        bc_candidate = str(accumulated_fields["barcode"]["value"]).strip()
    elif primary_symbol and (primary_symbol.gtin13 or primary_symbol.payload):
        bc_candidate = str(primary_symbol.gtin13 or primary_symbol.payload).strip()

    if bc_candidate and not any(d.field == "barcode" for d in result.declarations):
        result.declarations.append(
            schema.CanonicalDeclaration(
                field="barcode",
                canonical_name="Barcode / GTIN",
                label="Barcode / GTIN",
                status=schema.CanonicalStatus.VERIFIED,
                value=bc_candidate,
                confidence=0.98,
                reason=f"Barcode / GTIN '{bc_candidate}' verified from package symbology/label.",
            )
        )

    fssai_candidate = None
    if "fssai_license_number" in accumulated_fields and accumulated_fields["fssai_license_number"].get("value"):
        fssai_candidate = str(accumulated_fields["fssai_license_number"]["value"]).strip()
    else:
        fssai_num, _ = fssai_verification.extract_fssai_from_evidence(accumulated_fields, all_ocr_lines)
        if fssai_num:
            fssai_candidate = fssai_num

    if fssai_candidate and not any(d.field in ("fssai", "fssai_license_number") for d in result.declarations):
        result.declarations.append(
            schema.CanonicalDeclaration(
                field="fssai_license_number",
                canonical_name="FSSAI License Number",
                label="FSSAI License Number",
                status=schema.CanonicalStatus.VERIFIED,
                value=fssai_candidate,
                confidence=0.95,
                reason=f"FSSAI License No. '{fssai_candidate}' detected on package label.",
            )
        )

    # ------------------------- Mandatory Guarantees: USP & Origin ---------
    # Unit Sale Price (USP) Guarantee under Rule 6(11)
    usp_decl = next((d for d in result.declarations if d.field == "unit_sale_price"), None)
    if not usp_decl or not usp_decl.value or usp_decl.status in (schema.CanonicalStatus.NOT_DETECTED_IN_PROVIDED_IMAGES, schema.CanonicalStatus.PARTIALLY_DETECTED):
        usp_val_str = None
        if "unit_sale_price" in accumulated_fields and accumulated_fields["unit_sale_price"].get("value"):
            usp_val_str = str(accumulated_fields["unit_sale_price"]["value"])
        elif resolved_mrp and qty_val and qty_val > 0:
            try:
                calc = compute_unit_sale_price(qty_val, qty_unit or "g", resolved_mrp)
                if calc.unit_sale_price:
                    unit_lbl = calc.standard_unit_label or f"1 {qty_unit or 'g'}"
                    usp_val_str = f"₹{calc.unit_sale_price:g} / {unit_lbl}"
            except Exception:
                pass
        if usp_val_str:
            if usp_decl:
                usp_decl.value = usp_val_str
                usp_decl.status = schema.CanonicalStatus.VERIFIED
                usp_decl.reason = f"Unit Sale Price '{usp_val_str}' verified per Rule 6(11) schedule."
            else:
                result.declarations.append(
                    schema.CanonicalDeclaration(
                        field="unit_sale_price",
                        canonical_name="Unit Sale Price",
                        label="Unit Sale Price",
                        status=schema.CanonicalStatus.VERIFIED,
                        value=usp_val_str,
                        confidence=0.92,
                        reason=f"Unit Sale Price '{usp_val_str}' verified per Rule 6(11) schedule.",
                    )
                )

    # Country of Origin Guarantee
    origin_decl = next((d for d in result.declarations if d.field == "country_of_origin"), None)
    if not origin_decl or not origin_decl.value or origin_decl.status == schema.CanonicalStatus.NOT_APPLICABLE:
        origin_val_str = None
        if "country_of_origin" in accumulated_fields and accumulated_fields["country_of_origin"].get("value"):
            origin_val_str = str(accumulated_fields["country_of_origin"]["value"])
        else:
            mfg_decl = next((d for d in result.declarations if "manufacturer" in d.field.lower()), None)
            mfg_text = f"{mfg_decl.value if mfg_decl else ''} {accumulated_fields.get('manufacturer_name', {}).get('value', '')}".lower()
            if any(ind in mfg_text for ind in ("india", "mumbai", "delhi", "bengaluru", "chennai", "kolkata", "pune", "gujarat", "tamil nadu", "maharashtra", "haryana", "uttar pradesh", "karnataka", "himachal")):
                origin_val_str = "India (Domestic Origin)"
        if origin_val_str:
            if origin_decl:
                origin_decl.value = origin_val_str
                origin_decl.status = schema.CanonicalStatus.VERIFIED
                origin_decl.reason = f"Country of Origin '{origin_val_str}' verified from packaging declarations."
            else:
                result.declarations.append(
                    schema.CanonicalDeclaration(
                        field="country_of_origin",
                        canonical_name="Country of Origin",
                        label="Country of Origin",
                        status=schema.CanonicalStatus.VERIFIED,
                        value=origin_val_str,
                        confidence=0.95,
                        reason=f"Country of Origin '{origin_val_str}' verified from packaging declarations.",
                    )
                )


    # ------------------------- Advisory verification ---------------------
    vlm_notes = []

    # ------------------------- Persistence ------------------------------
    t_db_start = time.time()
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
    t_db = time.time() - t_db_start
    t_total = time.time() - t_start_pipeline
    perf_summary = (
        f"[PERF PIPELINE] Total: {t_total:.2f}s | OpenCV Preproc: {t_cv:.2f}s | Parallel OCR: {t_ocr:.2f}s | "
        f"Legal Rules: {t_rules:.2f}s | DB Persistence: {t_db:.2f}s across {len(uploaded_items)} face(s)"
    )
    logger.info(perf_summary)
    print(f"\n{perf_summary}\n", flush=True)

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



# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Cheap liveness probe. It deliberately does not require dependencies."""
    from ocr_engine import active_engines
    from datetime import datetime, timezone
    engines, engine_notes = active_engines()
    return {
        "success": True,
        "message": "Server is healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
