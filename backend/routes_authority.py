from __future__ import annotations
import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import cv2
import httpx
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

import config
from db import persistence as db
import auth
import package_integrity
import fssai_verification
import departmental_verification
import consumer_reporting
import assistant
import social_intelligence
import regional_analytics
from routes_inspections import (
    ConsumerReportInput,
    AuthorityActionInput,
    AssistantQueryInput,
    AssistantTtsInput,
)

logger = logging.getLogger('routes_authority')
router = APIRouter(tags=['authority'])

@router.post("/integrity/compare")
async def compare_package_integrity(
    inspection_id: str = Form(...),
    reference_type: str = Form("UNVERIFIED"),  # TRUSTED | DEMO | UNVERIFIED
    reference_file: Optional[UploadFile] = File(default=None),
    reference_files: List[UploadFile] = File(default=[]),
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    upload_list: List[UploadFile] = []
    if reference_files and isinstance(reference_files, (list, tuple)):
        upload_list.extend([f for f in reference_files if hasattr(f, "filename") and f.filename])
    elif reference_files and hasattr(reference_files, "filename") and reference_files.filename:
        upload_list.append(reference_files)
    if reference_file and hasattr(reference_file, "filename") and reference_file.filename:
        if reference_file not in upload_list and getattr(reference_file, "filename", None) not in [f.filename for f in upload_list]:
            upload_list.append(reference_file)

    custom_ref_paths: List[str] = []
    for f in upload_list:
        ref_filename = f"ref_{uuid.uuid4().hex[:8]}_{f.filename}"
        ref_dest = config.UPLOAD_DIR / ref_filename
        contents = await f.read()
        with open(ref_dest, "wb") as out_f:
            out_f.write(contents)
        custom_ref_paths.append(str(ref_dest))

    insp_data = detail.get("inspection") or detail
    p_id = (insp_data.get("product_identity") or {}).get("product_id") or insp_data.get("product_id")
    p_name = (insp_data.get("product_identity") or {}).get("product_name") or insp_data.get("product_name")
    primary_img_path = detail.get("image_path") or detail.get("image")
    declarations = insp_data.get("declarations") or []

    all_insp_paths = []
    if primary_img_path:
        all_insp_paths.append(str(primary_img_path))
    for s in (detail.get("surfaces") or insp_data.get("surfaces") or []):
        if isinstance(s, dict):
            sp = (
                s.get("original_image_path")
                or s.get("canonical_image_path")
                or s.get("image_url")
                or s.get("image_path")
                or s.get("image_id")
            )
            if sp and str(sp) not in all_insp_paths:
                all_insp_paths.append(str(sp))
    for c in (detail.get("captures") or insp_data.get("captures") or []):
        if isinstance(c, dict):
            cp = c.get("image_id")
            if cp and str(cp) not in all_insp_paths:
                all_insp_paths.append(str(cp))

    res = package_integrity.evaluate_package_integrity(
        primary_img_path,
        inspected_image_paths=all_insp_paths,
        product_id=p_id,
        product_name=p_name,
        inspection_declarations=declarations,
        custom_reference_path=custom_ref_paths[0] if custom_ref_paths else None,
        custom_reference_paths=custom_ref_paths,
        custom_reference_type=reference_type,
        allow_demo_fixtures=True,
    )
    report_dict = res.to_dict()
    report_dict["inspection_id"] = inspection_id
    # Persist the new comparison record as a distinct historical version
    try:
        db.save_package_integrity_comparison(report_dict)
    except Exception as exc:
        logger.warning("Failed saving comparison record: %s", exc)
    detail["package_integrity"] = report_dict
    try:
        db.save_inspection_detail(inspection_id, detail)
    except Exception:
        pass
    return report_dict


class FssaiVerifyInput(BaseModel):
    inspection_id: str
    license_number: Optional[str] = None
    product_category: Optional[str] = None
    declared_manufacturer: Optional[str] = None


@router.post("/regulatory/fssai/verify")
def verify_regulatory_fssai(
    req: FssaiVerifyInput,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    detail = db.get_inspection_detail(req.inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    insp_data = detail.get("inspection") or detail
    cat = req.product_category or insp_data.get("commodity_category") or insp_data.get("product_category") or "food"
    raw_fields = {}
    for d in (insp_data.get("declarations") or []):
        if isinstance(d, dict):
            raw_fields[d.get("field")] = d.get("value")
    for f in (detail.get("facts") or []):
        if isinstance(f, dict) and f.get("field"):
            raw_fields[f.get("field")] = f.get("extracted_value")

    if req.license_number:
        raw_fields["fssai_license_number"] = req.license_number
    if req.declared_manufacturer:
        raw_fields["manufacturer_name"] = req.declared_manufacturer

    res = fssai_verification.verify_fssai_compliance(cat, raw_fields)
    res_dict = res.to_dict()
    detail["fssai"] = res_dict
    try:
        db.save_inspection_detail(req.inspection_id, detail)
    except Exception:
        pass
    return res_dict


@router.get("/regulatory/fssai/{inspection_id}")
def get_regulatory_fssai(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    return get_inspection_fssai(inspection_id, current_user=current_user)


@router.get("/inspections/{inspection_id}/regulatory-cross-verification")
@router.get("/regulatory/cross-verification/{inspection_id}")
def get_regulatory_cross_verification(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    insp_data = detail.get("inspection") or detail
    cat = insp_data.get("commodity_category") or insp_data.get("product_category") or insp_data.get("category")
    p_name = (insp_data.get("product_identity") or {}).get("product_name") or insp_data.get("product_name") or insp_data.get("product")

    raw_fields = {}
    for d in (insp_data.get("declarations") or []):
        if isinstance(d, dict):
            raw_fields[d.get("field")] = d.get("value")
    for f in (detail.get("facts") or []):
        if isinstance(f, dict) and f.get("field"):
            raw_fields[f.get("field")] = f.get("extracted_value")

    gtin = (
        raw_fields.get("barcode")
        or raw_fields.get("gtin")
        or (insp_data.get("product_identity") or {}).get("product_id")
        or insp_data.get("productId")
        or insp_data.get("product_id")
    )

    all_lines = detail.get("ocr_lines") or []
    mfg_entry = raw_fields.get("manufacturer_name") or raw_fields.get("manufacturer_name_address")
    mfg = mfg_entry.get("value") if isinstance(mfg_entry, dict) else str(mfg_entry) if mfg_entry else None

    dossier = departmental_verification.generate_departmental_regulatory_dossier(
        inspection_id=inspection_id,
        product_category=cat,
        product_name=p_name,
        raw_ocr_fields=raw_fields,
        all_ocr_lines=all_lines,
        product_gtin=str(gtin) if gtin else None,
        declared_manufacturer=str(mfg) if mfg else None,
    )
    return dossier.to_dict()


@router.get("/inspections/{inspection_id}/fssai")
def get_inspection_fssai(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    insp_data = detail.get("inspection") or detail
    cat = insp_data.get("commodity_category") or insp_data.get("product_category") or insp_data.get("category") or "food"
    p_name = (insp_data.get("product_identity") or {}).get("product_name") or insp_data.get("product_name") or insp_data.get("product")

    raw_fields = {}
    for d in (insp_data.get("declarations") or []):
        if isinstance(d, dict):
            raw_fields[d.get("field")] = d.get("value")
    for f in (detail.get("facts") or []):
        if isinstance(f, dict) and f.get("field"):
            raw_fields[f.get("field")] = f.get("extracted_value")

    gtin = (
        raw_fields.get("barcode")
        or raw_fields.get("gtin")
        or (insp_data.get("product_identity") or {}).get("product_id")
        or insp_data.get("productId")
        or insp_data.get("product_id")
    )

    all_lines = detail.get("ocr_lines") or []
    mfg_entry = raw_fields.get("manufacturer_name") or raw_fields.get("manufacturer_name_address")
    mfg = mfg_entry.get("value") if isinstance(mfg_entry, dict) else str(mfg_entry) if mfg_entry else None

    # Generate full departmental dossier to ensure VLM commodity classification is unified
    dossier = departmental_verification.generate_departmental_regulatory_dossier(
        inspection_id=inspection_id,
        product_category=cat,
        product_name=p_name,
        raw_ocr_fields=raw_fields,
        all_ocr_lines=all_lines,
        product_gtin=str(gtin) if gtin else None,
        declared_manufacturer=str(mfg) if mfg else None,
    )

    fssai_dept = next((d for d in dossier.departments if d.department_code == "FSSAI"), None)
    res = fssai_verification.verify_fssai_compliance(
        cat,
        raw_fields,
        all_ocr_lines=all_lines,
        is_food_hint=dossier.commodity.is_food,
        gtin=str(gtin) if gtin else None,
    )
    res_dict = res.to_dict()
    res_dict["commodity_classification"] = dossier.commodity.to_dict()
    res_dict["departmental_dossier"] = dossier.to_dict()
    return res_dict


class CaptureReadinessInput(BaseModel):
    image_base64: str


@router.post("/capture/readiness")
def assess_capture_readiness(
    req: CaptureReadinessInput,
):
    """
    Lightweight assistive capture readiness evaluator.
    Returns dynamic perspective quadrilateral, blur, glare, coverage, and guidance.
    Does NOT invoke Gemini or heavy neural networks on camera frames.
    """
    try:
        b64_data = req.image_base64
        if "," in b64_data:
            b64_data = b64_data.split(",", 1)[1]
        img_bytes = base64.b64decode(b64_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return {"is_ready": False, "guidance": "Hold steady", "corners": []}

        h, w = img_bgr.shape[:2]
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        # 1. Blur evaluation: Laplacian variance
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_blur_ok = lap_var > 45.0

        # 2. Glare & exposure evaluation
        glare_px = np.sum(gray > 248)
        glare_ratio = float(glare_px) / float(h * w)
        is_glare_ok = glare_ratio < 0.14

        # Prioritize blur & glare feedback
        if not is_blur_ok:
            fallback_guidance = "Hold steady"
        elif not is_glare_ok:
            fallback_guidance = "Reduce glare"
        else:
            fallback_guidance = "Center package"

        # 3. Package boundary detection
        import package_preprocessor
        b_res = package_preprocessor.detect_package_boundary(img_bgr)
        detected = bool(b_res.get("detected"))
        corners = b_res.get("corners", [])

        # Default fallback corners if not detected
        if not detected or len(corners) != 4:
            margin_x = int(w * 0.15)
            margin_y = int(h * 0.15)
            default_corners = [
                [margin_x, margin_y],
                [w - margin_x, margin_y],
                [w - margin_x, h - margin_y],
                [margin_x, h - margin_y],
            ]
            return {
                "is_ready": False,
                "detected": False,
                "guidance": fallback_guidance,
                "corners": default_corners,
                "blur_score": round(lap_var, 1),
                "glare_ratio": round(glare_ratio, 3),
            }

        pts = np.array(corners, dtype=np.float32)
        quad_area = cv2.contourArea(pts)
        frame_area = w * h
        area_ratio = float(quad_area) / float(frame_area)

        min_x = np.min(pts[:, 0])
        max_x = np.max(pts[:, 0])
        min_y = np.min(pts[:, 1])
        max_y = np.max(pts[:, 1])

        touches_edge = (min_x < w * 0.02) or (max_x > w * 0.98) or (min_y < h * 0.02) or (max_y > h * 0.98)

        if not is_blur_ok:
            guidance = "Hold steady"
            is_ready = False
        elif not is_glare_ok:
            guidance = "Reduce glare"
            is_ready = False
        elif area_ratio < 0.18:
            guidance = "Move closer"
            is_ready = False
        elif area_ratio > 0.88 or touches_edge:
            guidance = "Move farther"
            is_ready = False
        else:
            top_w = np.linalg.norm(pts[1] - pts[0])
            bot_w = np.linalg.norm(pts[2] - pts[3])
            ratio = max(top_w, bot_w) / max(1.0, min(top_w, bot_w))
            if ratio > 1.8:
                guidance = "Rotate / Align camera"
                is_ready = False
            else:
                guidance = "Ready for capture"
                is_ready = True

        return {
            "is_ready": is_ready,
            "detected": True,
            "guidance": guidance,
            "corners": [[round(float(c[0]), 1), round(float(c[1]), 1)] for c in corners],
            "blur_score": round(lap_var, 1),
            "glare_ratio": round(glare_ratio, 3),
            "area_ratio": round(area_ratio, 3),
        }
    except Exception as exc:
        logger.warning("Capture readiness check error: %s", exc)
        return {"is_ready": False, "guidance": "Hold steady", "corners": []}


# ---------------------------------------------------------------------------
# USP 3: Consumer -> Authority Reporting & Enforcement Queue
# ---------------------------------------------------------------------------

@router.post("/reports/consumer")
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


@router.get("/reports/{report_id}")
def get_report(report_id: str):
    case = consumer_reporting.get_case_by_id(report_id)
    if not case:
        raise HTTPException(status_code=404, detail="Report not found.")
    return case


@router.get("/authority/cases")
def get_authority_cases(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    return consumer_reporting.list_authority_cases(status_filter=status, priority_filter=priority)


@router.get("/authority/cases/{case_id}")
def get_authority_case(
    case_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    case = consumer_reporting.get_case_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Authority case not found.")
    return case


@router.post("/authority/cases/{case_id}/action")
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

@router.post("/assistant/chat")
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


@router.post("/assistant/tts")
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
    speaker = req.speaker or "shubh"
    pace = float(req.pace) if req.pace else 1.15

    # Clean text and insert natural dynamic pauses for points and sections
    raw_text = req.text.strip()
    # Remove markdown markup (stars, hashes, ticks)
    clean = re.sub(r"[*#`_~]", "", raw_text)
    # Ensure numbered items and bullet points have clear pauses
    clean = re.sub(r"^[•\-\*]\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"(\d+)\.\s*", r"\1. ", clean)
    clean = re.sub(r"\n+\s*", ". ", clean)
    clean = re.sub(r"\.{2,}", ".", clean)
    clean = re.sub(r"\s+", " ", clean).strip()[:3500]

    if not clean:
        raise HTTPException(status_code=400, detail="Empty text for TTS.")

    payload = {
        "inputs": [clean],
        "target_language_code": target_lang,
        "speaker": speaker,
        "model": "bulbul:v3",
        "pace": pace,
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
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
                        "pace": pace,
                    }
            return JSONResponse(
                status_code=resp.status_code,
                content={"error": "Sarvam API returned error", "details": resp.text},
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS synthesis error: {str(e)}")




@router.get("/regional/intelligence")
def get_regional_intelligence(
    language: str = "en",
    current_user: auth.CurrentUser = Depends(auth.require_senior_inspector),
):
    """Answers: WHERE ARE PROBLEMS OCCURRING across districts and retailers."""
    return regional_analytics.get_regional_intelligence_summary(language=language)


@router.get("/social/summary")
def get_social_summary(
    language: str = "en",
    current_user: auth.CurrentUser = Depends(auth.require_senior_inspector),
):
    """Grounded AI synthesis and regional cluster distribution from public social intelligence."""
    return social_intelligence.get_social_intelligence_summary(language=language)


@router.get("/social/mentions")
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


@router.post("/social/mentions/{mention_id}/action")
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


@router.post("/social/pipeline/reprocess")
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
