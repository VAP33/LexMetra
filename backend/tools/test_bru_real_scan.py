import json
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import sys

# Ensure backend directory is in path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from main import app
import auth
from db import persistence as db

# In-memory storage for test run
_store = {}

def mock_save_inspection(inspection, image_filename=None, mrp=None):
    _store[inspection.inspection_id] = inspection.model_dump(mode="json")
    _store[inspection.inspection_id]["mrp"] = mrp

def mock_get_inspection_detail(inspection_id):
    return _store.get(inspection_id)

db.save_inspection = mock_save_inspection
db.get_inspection_detail = mock_get_inspection_detail
db.set_inspection_attribution = MagicMock()
db.record_audit_event = MagicMock()

# Dependency override for auth
fake_user = auth.CurrentUser(user_id=1, username="inspector", role="inspector", full_name="Field Inspector")
app.dependency_overrides[auth.get_current_user] = lambda: fake_user
app.dependency_overrides[auth.require_inspector] = lambda: fake_user

client = TestClient(app)

workspace_root = backend_dir.parent
dataset_dir = workspace_root / "images dataset" if (workspace_root / "images dataset").exists() else workspace_root / "DEPENDENCIES" / "images dataset"
img1_path = dataset_dir / "Screenshot_2026-09-06-22-06-12-38_92460851df6f172a4592fca41cc2d2e6.jpg"
img2_path = dataset_dir / "Screenshot_2026-09-06-22-06-22-17_92460851df6f172a4592fca41cc2d2e6.jpg"

assert img1_path.exists(), f"Image 1 not found: {img1_path}"
assert img2_path.exists(), f"Image 2 not found: {img2_path}"

with open(img1_path, "rb") as f1, open(img2_path, "rb") as f2:
    files = [
        ("files", (img1_path.name, f1.read(), "image/jpeg")),
        ("files", (img2_path.name, f2.read(), "image/jpeg")),
    ]

data = {
    "sale_type": "retail",
    "product_category": "food",
}

print("=" * 60)
print("RUNNING REAL BRU PHOTOS THROUGH PRODUCTION /scan ENDPOINT")
print("=" * 60)

resp = client.post("/scan", data=data, files=files)
print("HTTP Response status:", resp.status_code)

if resp.status_code != 200:
    print("Error:", resp.text)
    sys.exit(1)

body = resp.json()
insp = body["inspection"]
print("\n--- 1. INSPECTION RESULT ---")
print("Inspection ID:          ", insp["inspection_id"])
print("Overall status:         ", insp["overall_status"])
print("Applicable rule version:", insp.get("applicable_rule_version"))
print("Review required:        ", insp.get("review_required"))

print("\n--- 2. REGULATORY SCOPE ---")
scope = body.get("regulatory_scope", {})
print("Primary module:         ", scope.get("primary_module"))
print("Active modules:         ", scope.get("active_modules"))
print("Is Food:                ", scope.get("is_food"))

print("\n--- 3. RAG GROUNDED LEGAL KNOWLEDGE ---")
grounding = body.get("rag_grounding", [])
print(f"Total grounded provisions: {len(grounding)}")
for g in grounding[:6]:
    print(f"  [{g['module'].upper()}] {g['rule_id']} ({g['rule_version']}, eff: {g['effective_date']})")
    print(f"      Source: {g['source_reference']}")

print("\n--- 4. RESOLVED INPUTS ---")
for k, v in body.get("resolved_inputs", {}).items():
    print(f"  {k}: {v}")

print("\n--- 5. EXTRACTED DECLARATION EVIDENCE ---")
fields = body.get("raw_ocr_fields", {})
for k in [
    "common_name", "net_quantity", "mrp", "manufacturer_name", "marketer_name",
    "mfg_date", "expiry_date", "consumer_care", "unit_sale_price", "batch_no"
]:
    f_data = fields.get(k)
    if f_data:
        val = f_data.get("value")
        conf = f_data.get("confidence")
        stat = f_data.get("status") or f_data.get("verification")
        srcs = f_data.get("source_images") or [f_data.get("image_id")]
        val_str = str(val).replace("\u20b9", "Rs. ")
        print(f"  {k:22s}: {val_str:35s} | status: {str(stat):15s} | conf: {conf} | src: {srcs}")

print("\n--- 6. PDF REPORT GENERATION ---")
rep_resp = client.get(f"/inspections/{insp['inspection_id']}/report")
print(f"PDF Report status: {rep_resp.status_code}")
print(f"PDF Bytes length:  {len(rep_resp.content)}")
print(f"Valid PDF header:  {rep_resp.content.startswith(b'%PDF')}")

print("\n" + "=" * 60)
print("REAL BRU MULTI-SURFACE HTTP INSPECTION SUCCEEDED")
print("=" * 60)
