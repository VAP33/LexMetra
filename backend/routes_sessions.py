from __future__ import annotations
import io
import os
import re
import time
import uuid
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Sequence

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, status

import config
from db import persistence as db
import auth
from schema import (
    ProductInspection,
    SurfaceObservation,
    PackageStructure,
    GeometryType,
    EvidenceReference,
    FactStatus,
    ExtractedFact,
    RuleFinding,
)
from inspection_helpers import (
    CreateSessionRequest,
    _validate_upload_metadata,
    _read_image_upload,
    _safe_filename,
    _resolve_mrp,
    _resolve_quantity,
    _prepare_extractions,
    _infer_applicability_context,
)
import calibration as calib
import preprocess
import region_detection
import orientation
import ocr_engine
import ocr_extraction
import rule_engine
import geometry
import qwen_perception
from qwen_perception import CoordinateTransform

logger = logging.getLogger('routes_sessions')
router = APIRouter(tags=['sessions'])

@router.post("/sessions")
def create_session(
    req: CreateSessionRequest,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
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


@router.post("/sessions/{session_id}/captures")
async def add_capture(
    session_id: str,
    file: UploadFile = File(...),
    surface_type: Optional[str] = Form(None),
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
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


@router.get("/sessions/{session_id}")
def get_session_status(
    session_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
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


@router.post("/sessions/{session_id}/finalize", response_model=ProductInspection)
async def finalize_session(
    session_id: str,
    payload: Optional[FinalizeSessionRequest] = None,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
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
            if faces_multi and groq_vision_service.is_groq_available():
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

    if localizer_mode in ("shadow", "paddle", "sanskruti"):
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
        localized_evidence=localized_evidence_list if localizer_mode in ("paddle", "sanskruti") else None,
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

