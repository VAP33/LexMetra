from __future__ import annotations
import os
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, status, Response, Request, Body
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

import config
from db import persistence as db
import auth
from inspection_helpers import ReviewRequest
from report import build_inspection_report_pdf
import package_integrity
import rule_engine
import fssai_verification

logger = logging.getLogger('routes_inspections')
router = APIRouter(tags=['inspections'])

def _build_integrity_image_paths(detail: Dict[str, Any], insp_data: Dict[str, Any]):
    """
    Build Package Integrity inspected-image paths using ORIGINAL captures only.

    Surface original_image_path entries retain their persisted face order. Legacy
    image_path/image and capture image_id values are appended only when unique.
    Canonical/rectified images are deliberately excluded because localized
    evidence.bbox coordinates are defined on the original captured image.
    """
    img_path = detail.get("image_path") or detail.get("image")
    all_insp_paths: List[str] = []

    surfaces = detail.get("surfaces") or insp_data.get("surfaces") or []
    for s in surfaces:
        if not isinstance(s, dict):
            continue
        sp = (
            s.get("original_image_path")
            or s.get("image_path")
            or s.get("image_url")
            or s.get("image_id")
        )
        if sp and str(sp) not in all_insp_paths:
            all_insp_paths.append(str(sp))

    if img_path and str(img_path) not in all_insp_paths:
        all_insp_paths.append(str(img_path))

    captures = detail.get("captures") or insp_data.get("captures") or []
    for c in captures:
        if not isinstance(c, dict):
            continue
        cp = c.get("image_id")
        if cp and str(cp) not in all_insp_paths:
            all_insp_paths.append(str(cp))

    return img_path, all_insp_paths




@router.get("/inspections")
def get_inspections(
    limit: int = 50,
    status: Optional[str] = None,
    needs_review: Optional[bool] = None,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 200.",
        )

    # Role-based scan isolation:
    # 1. Consumers/Citizens: only see their own consumer scans
    # 2. Field Inspectors: see scans by field inspectors / their own scans
    # 3. Senior Inspector / Authority / Admin: see all scans, including field inspector scans
    user_role = getattr(current_user, "role", "consumer")
    user_name = getattr(current_user, "username", "citizen_user")

    created_by_in = None
    if user_role in ("customer", "consumer"):
        created_by_in = [user_name, "customer", "consumer", "citizen_user"]
    elif user_role == "inspector":
        created_by_in = [user_name, "inspector", "inspector_dev"]

    return db.list_inspections(
        limit=limit,
        status=status,
        needs_review=needs_review,
        created_by_in=created_by_in,
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
    speaker: str = "shubh"
    pace: float = 1.15


def _is_stale_package_integrity(pi_record: Optional[Dict[str, Any]]) -> bool:
    if not pi_record or not isinstance(pi_record, dict):
        return True
    fc = pi_record.get("field_comparisons") or []
    if not fc:
        return True
    for c in fc:
        # Legacy dummy reference bbox
        if c.get("reference_bbox") == [230, 815, 530, 70]:
            return True
        # Missing inspection crop despite bbox being present
        if c.get("inspection_bbox") and not c.get("inspection_crop_base64"):
            return True
        # Missing inspection crop on key statutory fields
        if c.get("field_key") in ("mrp", "barcode", "fssai_license_number") and not c.get("inspection_crop_base64"):
            return True
    return False


@router.get("/inspections/{inspection_id}")
def get_inspection(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    # Enrich with FSSAI & Package Integrity if not present or if stale
    current_pi = detail.get("package_integrity") or db.get_latest_package_integrity_comparison(inspection_id)
    if current_pi and not _is_stale_package_integrity(current_pi):
        detail["package_integrity"] = current_pi
    else:
        # Do not automatically evaluate without user uploading reference images
        detail["package_integrity"] = {
            "status": "AWAITING_REFERENCE_STANDARD",
            "has_reference": False,
            "reference_type": "UNVERIFIED",
            "reference_image_urls": [],
            "detected_differences": [],
            "field_comparisons": [],
            "explanation": "No reference packaging standard uploaded. Upload reference package image(s) across faces to run comparative integrity verification.",
            "source_tag": "COMPUTER VISION",
        }

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

    import lmpc_master_rules
    insp_data = detail.get("inspection") or detail
    cat = insp_data.get("commodity_category") or insp_data.get("product_category") or "food"
    sale_type = insp_data.get("sale_type") or "retail"
    try:
        qty_val = float(insp_data.get("net_quantity_value") or 0)
    except Exception:
        qty_val = None
    qty_unit = str(insp_data.get("net_quantity_unit") or "")
    detail["lmpc_master_rules"] = lmpc_master_rules.evaluate_contextual_rule_applicability(
        product_category=cat,
        sale_type=sale_type,
        net_quantity_val=qty_val,
        net_quantity_unit=qty_unit,
    )

    detail["is_reference_cache"] = bool(detail.get("is_reference_cache", False))
    return detail


@router.get("/inspections/{inspection_id}/integrity")
def get_inspection_integrity(
    inspection_id: str,
    force_refresh: bool = False,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    persisted = db.get_latest_package_integrity_comparison(inspection_id)
    if persisted and not force_refresh and not _is_stale_package_integrity(persisted):
        if not persisted.get("status"):
            persisted["status"] = persisted.get("comparison_status")
        if not persisted.get("comparison_status"):
            persisted["comparison_status"] = persisted.get("status")
        return persisted

    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    if detail.get("package_integrity") and not force_refresh and not _is_stale_package_integrity(detail.get("package_integrity")):
        rec = detail["package_integrity"]
        rec["inspection_id"] = inspection_id
        if not rec.get("status"):
            rec["status"] = rec.get("comparison_status")
        if not rec.get("comparison_status"):
            rec["comparison_status"] = rec.get("status")
        try:
            db.save_package_integrity_comparison(rec)
        except Exception:
            pass
        return rec

    # Never auto-evaluate without the user uploading reference images!
    awaiting_rep = {
        "inspection_id": inspection_id,
        "status": "AWAITING_REFERENCE_STANDARD",
        "has_reference": False,
        "reference_type": "UNVERIFIED",
        "reference_image_urls": [],
        "detected_differences": [],
        "field_comparisons": [],
        "explanation": "No reference packaging standard uploaded. Please upload reference package image(s) across faces to run comparative integrity verification.",
        "source_tag": "COMPUTER VISION",
    }
    return awaiting_rep


class SavePackageIntegrityRequest(BaseModel):
    package_integrity: Optional[Dict[str, Any]] = None


@router.get("/integrity/{inspection_id}")
def get_integrity_direct(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    return get_inspection_integrity(inspection_id, current_user=current_user)


@router.post("/inspections/{inspection_id}/integrity/save")
@router.post("/integrity/{inspection_id}/save")
def save_inspection_integrity(
    inspection_id: str,
    payload: Optional[SavePackageIntegrityRequest] = None,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    """
    Explicitly persist and lock Package Integrity verification for this inspection.
    Ensures comparison results and crops are permanently saved and included in reports.
    """
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    rep_dict = (payload.package_integrity if payload else None) or detail.get("package_integrity")
    if not rep_dict:
        insp_data = detail.get("inspection") or detail
        declarations = detail.get("declarations") or insp_data.get("declarations") or []
        p_id = (insp_data.get("product_identity") or {}).get("product_id") or insp_data.get("product_id") or detail.get("product_id")
        p_name = (insp_data.get("product_identity") or {}).get("product_name") or insp_data.get("product_name") or detail.get("product_name")
        img_path, all_insp_paths = _build_integrity_image_paths(detail, insp_data)
        res = package_integrity.evaluate_package_integrity(
            img_path,
            inspected_image_paths=all_insp_paths,
            product_id=p_id,
            product_name=p_name,
            inspection_declarations=declarations,
            allow_demo_fixtures=True,
        )
        rep_dict = res.to_dict()

    rep_dict["inspection_id"] = inspection_id
    rep_dict["is_saved"] = True
    rep_dict["saved_at"] = datetime.now(timezone.utc).isoformat()
    if not rep_dict.get("status"):
        rep_dict["status"] = rep_dict.get("comparison_status")
    if not rep_dict.get("comparison_status"):
        rep_dict["comparison_status"] = rep_dict.get("status")
    detail["package_integrity"] = rep_dict
    detail["package_integrity_json"] = rep_dict
    detail["package_integrity_status"] = rep_dict.get("status") or "UNVERIFIED"

    try:
        db.save_package_integrity_comparison(rep_dict)
    except Exception as e:
        logger.warning("Could not save package integrity comparison: %s", e)
    try:
        db.save_inspection_detail(inspection_id, detail)
    except Exception as e:
        logger.warning("Could not save inspection detail: %s", e)

    return {"status": "success", "package_integrity": rep_dict}


@router.get("/inspections/{inspection_id}/integrity/history")
@router.get("/integrity/{inspection_id}/history")
def get_inspection_integrity_history(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    """
    Returns comparison history list for this inspection, newest first.
    """
    history = db.list_package_integrity_history(inspection_id)
    return {"history": history, "count": len(history)}


class ToggleReferenceCacheRequest(BaseModel):
    is_cache: Optional[bool] = None


@router.post("/inspections/{inspection_id}/toggle-reference-cache")
@router.post("/integrity/{inspection_id}/toggle-reference-cache")
def toggle_inspection_reference_cache(
    inspection_id: str,
    payload: Any = Body(None),
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    """
    Sets or toggles the single-tick reference caching status for this inspection.
    Enforces the single-tick invariant: only one inspection can be the active cache.
    """
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    current_state = bool(detail.get("is_reference_cache", False))
    target_state = None
    if payload is not None:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if isinstance(payload, dict):
            target_state = payload.get("is_cache")
        elif hasattr(payload, "is_cache"):
            target_state = payload.is_cache

    if target_state is None:
        target_state = not current_state
    else:
        target_state = bool(target_state)

    db.set_inspection_reference_cache(inspection_id, is_cache=target_state)
    detail["is_reference_cache"] = target_state
    try:
        db.save_inspection_detail(inspection_id, detail)
    except Exception:
        pass
    return {
        "status": "success",
        "inspection_id": inspection_id,
        "is_reference_cache": target_state,
    }




@router.post("/inspections/{inspection_id}/review")
def review_inspection(
    inspection_id: str,
    req: ReviewRequest,
    current_user: auth.CurrentUser = Depends(auth.require_customer),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    # Ownership guard: customers/consumers and inspectors/reviewers can only
    # save/review inspections they themselves created. Senior inspectors,
    # authority, and admins can review/save any inspection.
    user_level = auth.ROLE_HIERARCHY.get(current_user.role, 0)
    senior_level = auth.ROLE_HIERARCHY.get("senior_inspector", 2)
    owner = detail.get("created_by")
    if user_level < senior_level and owner is not None and owner != current_user.username:
        raise HTTPException(
            status_code=403,
            detail="You can only save inspections you created.",
        )

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


@router.get("/inspections/{inspection_id}/report")
@router.get("/inspections/{inspection_id}/report.pdf")
@router.head("/inspections/{inspection_id}/report")
@router.head("/inspections/{inspection_id}/report.pdf")
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

    # Load persisted Package Integrity and Departmental Regulatory Cross-Verification
    if "package_integrity" not in detail or not detail["package_integrity"]:
        persisted_pi = db.get_latest_package_integrity_comparison(inspection_id)
        if persisted_pi:
            detail["package_integrity"] = persisted_pi

    if "departmental_dossier" not in detail or not detail["departmental_dossier"]:
        persisted_dos = db.get_departmental_dossier(inspection_id)
        if persisted_dos:
            detail["departmental_dossier"] = persisted_dos

    pdf_bytes = build_inspection_report_pdf(detail)
    db.record_audit_event(
        action="report_generated",
        actor_username=actor_username,
        resource_type="inspection",
        resource_id=inspection_id,
    )
    safe_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", inspection_id)
    raw_prod = (
        detail.get("product_name")
        or next((d.get("value") for d in detail.get("declarations", []) if d.get("canonical_name") in ("Product Name", "product_name")), None)
        or "Product"
    )
    safe_prod = re.sub(r"[^a-zA-Z0-9]+", "_", str(raw_prod)).strip("_")
    filename = f"LexMetra_Inspection_Report_{safe_prod}_{safe_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        },
    )


@router.get("/products/{product_id}/history")
def get_product_history(
    product_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    return db.product_history(product_id)


@router.get("/rules/lmpc-master")
def get_master_rules(
    category: Optional[str] = None,
    sale_type: Optional[str] = None,
    net_quantity: Optional[float] = None,
    unit: Optional[str] = None,
):
    """Returns statutory LMPC 2011 master rules and contextual exemption evaluations."""
    import lmpc_master_rules
    if any([category, sale_type, net_quantity is not None, unit]):
        return lmpc_master_rules.evaluate_contextual_rule_applicability(
            product_category=category,
            sale_type=sale_type,
            net_quantity_val=net_quantity,
            net_quantity_unit=unit,
        )
    return lmpc_master_rules.get_lmpc_master_rule_register()


@router.get("/verify/{inspection_id}")
def get_public_verification_docket(inspection_id: str):
    """
    Public statutory verification portal endpoint.
    Accessible without login by citizens and field officers scanning QR codes.
    """
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Statutory verification docket not found.")

    insp = detail.get("inspection") or detail
    declarations = detail.get("declarations") or insp.get("declarations") or []

    verified_decls = [d for d in declarations if str(d.get("status", "")).upper() in ("VERIFIED", "PASS")]
    review_decls = [d for d in declarations if "REVIEW" in str(d.get("status", "")).upper() or "UNCERTAIN" in str(d.get("status", "")).upper()]
    violation_decls = [d for d in declarations if "NON_COMPLIANT" in str(d.get("status", "")).upper() or "NOT_DETECTED" in str(d.get("status", "")).upper()]

    p_integrity = detail.get("package_integrity") or {}

    return {
        "inspection_id": inspection_id,
        "product_name": insp.get("product_name") or "Packaged Commodity",
        "product_id": insp.get("product_id") or "Not detected",
        "category": insp.get("product_category") or "Packaged Commodity",
        "sale_type": insp.get("sale_type") or "retail",
        "overall_status": detail.get("overall_status") or insp.get("overall_status") or "UNCERTAIN",
        "created_at": detail.get("created_at") or detail.get("timestamp"),
        "digital_seal": {
            "issued_by": "Legal Metrology Division, Department of Consumer Affairs",
            "jurisdiction": "Republic of India",
            "statutory_act": "Legal Metrology Act, 2009 & LMPC Rules, 2011",
            "seal_status": "AUTHENTIC_GOVERNMENT_SCREENING_RECORD",
            "docket_hash": f"LMPC-INSP-{abs(hash(inspection_id)) % 100000000:08d}",
        },
        "counts": {
            "verified": len(verified_decls),
            "review_required": len(review_decls),
            "violations": len(violation_decls),
            "total_declarations": len(declarations),
        },
        "package_integrity_status": p_integrity.get("status") or "UNVERIFIED",
        "has_official_report_pdf": True,
        "report_pdf_url": f"/inspections/{inspection_id}/report.pdf",
    }


@router.get("/inspections/{inspection_id}/qrcode")
def get_inspection_qr_code(inspection_id: str, request: Request):
    """
    Returns a native vector SVG QR code encoding the live public verification docket URL.
    """
    try:
        from reportlab.graphics import renderSVG
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics.barcode.qr import QrCodeWidget

        # Dynamic base URL resolution
        base_url = str(request.base_url).rstrip("/")
        # If running in web app, verification docket hash path is /#verify:<id>
        verify_url = f"{base_url}/#verify:{inspection_id}"

        d = Drawing(120, 120)
        widget = QrCodeWidget(verify_url)
        widget.barWidth = 112
        widget.barHeight = 112
        widget.qrVersion = 1
        d.add(widget)

        svg_str = renderSVG.drawToString(d)
        return Response(content=svg_str, media_type="image/svg+xml")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate QR code: {e}")


# ---------------------------------------------------------------------------
# Inline Declaration Editing with Dynamic Rule Re-evaluation (Req 8, 12)
# ---------------------------------------------------------------------------

class InlineFactUpdateInput(BaseModel):
    field: str
    value: str
    unit: Optional[str] = None
    reviewer_notes: Optional[str] = None


@router.patch("/inspections/{inspection_id}/facts")
def update_inspection_fact(
    inspection_id: str,
    req: InlineFactUpdateInput,
    current_user: auth.CurrentUser = Depends(auth.require_inspector),
):
    """
    Inline correction on Inspection Results:
    1. Updates the canonical fact value in persisted database.
    2. Dynamically re-runs Rule Engine on updated facts.
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

    # Re-evaluate with Regulatory Service
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

