from __future__ import annotations
import os
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, status, Response, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

import config
from db import persistence as db
import auth
from inspection_helpers import ReviewRequest
from report import build_inspection_report_pdf
import package_integrity

logger = logging.getLogger('routes_inspections')
router = APIRouter(tags=['inspections'])

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


@router.get("/inspections/{inspection_id}")
def get_inspection(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    # Enrich with FSSAI & Package Integrity if not present
    if "package_integrity" not in detail:
        persisted_integrity = db.get_latest_package_integrity_comparison(inspection_id)
        if persisted_integrity:
            detail["package_integrity"] = persisted_integrity
        else:
            insp_data = detail.get("inspection") or detail
            p_id = (insp_data.get("product_identity") or {}).get("product_id") or insp_data.get("product_id")
            p_name = (insp_data.get("product_identity") or {}).get("product_name") or insp_data.get("product_name")
            img_path = detail.get("image_path") or detail.get("image")
            try:
                integrity_res = package_integrity.evaluate_package_integrity(
                    img_path,
                    product_id=p_id,
                    product_name=p_name,
                    allow_demo_fixtures=True,
                    inspection_declarations=insp_data.get("declarations") or [],
                )
                rep_dict = integrity_res.to_dict()
                rep_dict["inspection_id"] = inspection_id
                detail["package_integrity"] = rep_dict
                # PERSISTENCE: Always save every computed comparison, even UNABLE_TO_VERIFY.
                # This ensures page reload restores the exact same comparison_id without re-running OCR.
                try:
                    db.save_package_integrity_comparison(rep_dict)
                except Exception:
                    pass
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

    return detail


@router.get("/inspections/{inspection_id}/integrity")
def get_inspection_integrity(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    # Rule: Restore the exact comparison without silently recomputing every time the page loads
    persisted = db.get_latest_package_integrity_comparison(inspection_id)
    if persisted:
        return persisted

    detail = db.get_inspection_detail(inspection_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    if detail.get("package_integrity"):
        rec = detail["package_integrity"]
        rec["inspection_id"] = inspection_id
        try:
            db.save_package_integrity_comparison(rec)
        except Exception:
            pass
        return rec

    insp_data = detail.get("inspection") or detail
    p_id = (insp_data.get("product_identity") or {}).get("product_id") or insp_data.get("product_id")
    p_name = (insp_data.get("product_identity") or {}).get("product_name") or insp_data.get("product_name")
    img_path = detail.get("image_path") or detail.get("image")
    declarations = insp_data.get("declarations") or []

    all_insp_paths = []
    if img_path:
        all_insp_paths.append(str(img_path))
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
        img_path,
        inspected_image_paths=all_insp_paths,
        product_id=p_id,
        product_name=p_name,
        inspection_declarations=declarations,
        allow_demo_fixtures=True,
    )
    report_dict = res.to_dict()
    report_dict["inspection_id"] = inspection_id
    # PERSISTENCE: Always save every computed comparison, even UNABLE_TO_VERIFY.
    # This ensures page reload restores the exact same comparison_id/statuses/values.
    try:
        db.save_package_integrity_comparison(report_dict)
    except Exception:
        pass
    detail["package_integrity"] = report_dict
    try:
        db.save_inspection_detail(inspection_id, detail)
    except Exception:
        pass
    return report_dict


@router.get("/integrity/{inspection_id}")
def get_integrity_direct(
    inspection_id: str,
    current_user: auth.CurrentUser = Depends(auth.require_scan_access),
):
    return get_inspection_integrity(inspection_id, current_user=current_user)


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

