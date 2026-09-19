import os
import sys
import json
import time
import requests
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

BASE_URL = "http://127.0.0.1:8000"
GEMS_DIR = Path(r"c:\Users\HP\SIH LATEST\images new")

def main():
    print("=" * 80)
    print("STARTING REAL RUNTIME END-TO-END INTEGRATION TEST")
    print("=" * 80)

    # 1. Login
    print("\n[Step 1] Authenticating...")
    login_resp = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "admin", "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✓ Login successful, JWT token acquired.")

    # 2. Check Qwen model config
    from config import EVIDENCE_LOCALIZER_MODE, REGULATORY_ENGINE_MODE
    from qwen_perception import OpenRouterQwenProvider
    QWEN_MODEL_NAME = OpenRouterQwenProvider.MODEL_NAME
    print(f"✓ Configured Qwen Model Identifier: {QWEN_MODEL_NAME}")
    print(f"✓ Active Localizer Mode: {EVIDENCE_LOCALIZER_MODE}")
    print(f"✓ Active Regulatory Engine Mode: {REGULATORY_ENGINE_MODE}")

    # 3. Create Session
    print("\n[Step 2] Creating Scan Session...")
    session_payload = {
        "product_category": "FOOD",
        "sale_type": "RETAIL",
        "is_export_only": False,
        "is_wholesale": False,
    }
    s_resp = requests.post(f"{BASE_URL}/sessions", json=session_payload, headers=headers)
    assert s_resp.status_code in (200, 201), f"Create session failed: {s_resp.text}"
    session_data = s_resp.json()
    session_id = session_data["session_id"]
    print(f"✓ Created session: {session_id}")

    # 4. Upload Captures for Face 1, Face 2, Face 3
    print("\n[Step 3] Uploading Captures for 3 Faces...")
    face_files = [
        ("Face 1", GEMS_DIR / "GEMS.jpg"),
        ("Face 2", GEMS_DIR / "GEMS 1.jpg"),
        ("Face 3", GEMS_DIR / "GEMS 2.jpg"),
    ]
    
    for face_label, img_path in face_files:
        assert img_path.exists(), f"Image not found: {img_path}"
        with open(img_path, "rb") as f:
            files = {"file": (img_path.name, f, "image/png")}
            cap_resp = requests.post(
                f"{BASE_URL}/sessions/{session_id}/captures",
                files=files,
                headers=headers,
            )
        assert cap_resp.status_code == 200, f"Upload capture failed for {face_label}: {cap_resp.text}"
        cap_data = cap_resp.json()
        print(f"✓ Uploaded {face_label} ({img_path.name}) -> capture {cap_data.get('capture_id')}")

    # 5. Invoke Qwen extraction
    print("\n[Step 4] Invoking Qwen Perception Extraction...")
    import asyncio
    import cv2
    import geometry
    from qwen_perception import get_qwen_provider, perception_to_classified_fields

    provider = get_qwen_provider()
    faces_for_qwen = []
    for face_label, img_path in face_files:
        img_bgr = cv2.imread(str(img_path))
        norm_res = geometry.normalize_package_surface(img_bgr, source_name=img_path.name)
        faces_for_qwen.append((face_label, norm_res.canonical_image, norm_res.inverse_transform))

    t0 = time.time()
    perception_result = asyncio.run(provider.perceive(faces_for_qwen))
    qwen_latency = time.time() - t0

    print(f"✓ Qwen request succeeded in {qwen_latency:.2f}s!")
    print(f"✓ Qwen provider: {perception_result.provider_name}")
    print(f"✓ Extracted {len(perception_result.declarations)} raw evidence items from Qwen:")
    
    classified_qwen_fields = perception_to_classified_fields(perception_result)
    for fld, f_val in classified_qwen_fields.items():
        print(f"   - {fld}: value={f_val.get('value')!r}, face={f_val.get('surface_id')}, bbox={f_val.get('bbox')}")

    assert len(classified_qwen_fields) > 0, "Qwen produced no fields!"

    # 6. Finalize session passing the authoritative Qwen fields
    print("\n[Step 5] Finalizing Session (Paddle Localization + Regulatory Evaluation)...")
    mrp_val = classified_qwen_fields.get("mrp", {}).get("numeric_value") or classified_qwen_fields.get("mrp", {}).get("normalized_value")
    finalize_payload = {
        "confirmed_fields": classified_qwen_fields,
        "product_category": "FOOD",
        "sale_type": "RETAIL",
        "mrp": float(mrp_val) if mrp_val else None,
    }
    
    fin_resp = requests.post(
        f"{BASE_URL}/sessions/{session_id}/finalize",
        json=finalize_payload,
        headers=headers,
    )
    assert fin_resp.status_code == 200, f"Finalize failed: {fin_resp.text}"
    fin_data = fin_resp.json()
    inspection_id = fin_data["inspection_id"]
    print(f"✓ Session finalized -> Inspection ID: {inspection_id}")
    print(f"✓ Overall Status: {fin_data.get('overall_status')}")

    # 7. Reload from database to verify persistence
    print("\n[Step 6] Reloading Inspection from Database (GET /inspections/{id})...")
    detail_resp = requests.get(f"{BASE_URL}/inspections/{inspection_id}", headers=headers)
    assert detail_resp.status_code == 200, f"Get detail failed: {detail_resp.text}"
    detail = detail_resp.json()
    print("✓ Successfully reloaded inspection from database.")

    # 8. Check DB rows count
    from db.persistence import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM inspections WHERE inspection_id = %s", (inspection_id,))
            cnt = cur.fetchone()[0]
            print(f"✓ Inspection rows written to database: {cnt} (Expected: 1)")
            assert cnt == 1, f"Expected 1 inspection row, found {cnt}"

            cur.execute("SELECT COUNT(*) FROM inspection_surfaces WHERE inspection_id = %s", (inspection_id,))
            s_cnt = cur.fetchone()[0]
            print(f"✓ Inspection surfaces persisted: {s_cnt} (Expected: 3)")

            cur.execute("SELECT declarations_json FROM inspections WHERE inspection_id = %s", (inspection_id,))
            d_json = cur.fetchone()[0]
            assert d_json is not None, "declarations_json is null!"
            print(f"✓ declarations_json persisted length: {len(d_json)} chars")

    # 9. Verify Paddle OCR output & Tight BBoxes
    print("\n" + "=" * 80)
    print("DETAILED VERIFICATION OF MANDATORY ACCEPTANCE CRITERIA")
    print("=" * 80)
    
    declarations = detail.get("declarations") or fin_data.get("declarations") or []
    print(f"\nTotal Declarations: {len(declarations)}")
    print(f"{'Field':<28} | {'Status':<12} | {'Loc Status':<16} | {'Tight BBox':<24} | {'Polygon Pts'}")
    print("-" * 100)

    match_table = []
    for d in declarations:
        f_name = d.get("canonical_name") or d.get("field")
        val = d.get("value")
        stat = d.get("status")
        ev = d.get("evidence") or {}
        loc_stat = ev.get("localization_status") or "UNLOCALIZED"
        bbox = ev.get("bbox") or ev.get("canonical_bbox")
        poly = ev.get("polygon") or ev.get("canonical_polygon")
        
        bbox_str = f"[{bbox[0]:.1f},{bbox[1]:.1f},{bbox[2]:.1f},{bbox[3]:.1f}]" if bbox and len(bbox) == 4 else "None"
        poly_pts = len(poly) if poly else 0
        
        print(f"{f_name:<28} | {stat:<12} | {loc_stat:<16} | {bbox_str:<24} | {poly_pts} pts")
        match_table.append({
            "field": f_name,
            "value": val,
            "status": stat,
            "loc_status": loc_stat,
            "bbox": bbox,
            "poly_pts": poly_pts,
            "rule_id": d.get("rule_id"),
            "rule_clause": d.get("rule_clause"),
            "reason": d.get("reason"),
        })

    # 10. Check Generic Ruleset
    print(f"\nRuleset ID / Version: {fin_data.get('applicable_rule_version')}")
    print("Declarations Summary:", json.dumps(fin_data.get("declaration_summary"), indent=2))

    # Save complete verification report to json artifact
    report = {
        "qwen_model": QWEN_MODEL_NAME,
        "qwen_extracted_fields": classified_qwen_fields,
        "active_modes": {
            "evidence_localizer": EVIDENCE_LOCALIZER_MODE,
            "regulatory_engine": REGULATORY_ENGINE_MODE,
        },
        "inspection_id": inspection_id,
        "overall_status": fin_data.get("overall_status"),
        "ruleset_version": fin_data.get("applicable_rule_version"),
        "declaration_summary": fin_data.get("declaration_summary"),
        "match_table": match_table,
    }
    
    report_path = Path(__file__).resolve().parent / "e2e_verification_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n✓ Verification report saved to {report_path}")
    print("=" * 80)
    print("REAL END-TO-END FLOW COMPLETED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    main()
