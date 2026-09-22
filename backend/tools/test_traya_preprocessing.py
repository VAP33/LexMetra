"""
Test harness:
1. Executes the 9-stage OpenCV package preprocessing pipeline on Traya Back.
2. Saves all stages to backend/debug/preprocessing/traya/
3. Sends 09_final.jpg to Qwen3.8-27B on OpenRouter with reasoning: {"effort": "none"}
4. Evaluates performance, token usage, latency, and extraction accuracy.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

import cv2
import httpx
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).resolve().parent.parent.parent
backend_dir = project_root / "backend"
sys.path.insert(0, str(backend_dir))

from package_preprocessor import run_preprocessing_pipeline

env_path = backend_dir / ".env"
load_dotenv(dotenv_path=env_path)

api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY2")
if not api_key:
    print("ERROR: No OPENROUTER_API_KEY found!", file=sys.stderr)
    sys.exit(1)

traya_img_path = project_root / "images new" / "TRAYA BACK.jpg"
if not traya_img_path.exists():
    print(f"ERROR: Traya image not found at {traya_img_path}", file=sys.stderr)
    sys.exit(1)

debug_dir = backend_dir / "debug" / "preprocessing" / "traya"
debug_dir.mkdir(parents=True, exist_ok=True)

print("=" * 80)
print("LEXMETRA: RUNNING FIRST-STAGE CV PREPROCESSING PIPELINE ON TRAYA BACK")
print("=" * 80)

img_bgr = cv2.imread(str(traya_img_path))
h_orig, w_orig = img_bgr.shape[:2]
orig_size_bytes = traya_img_path.stat().st_size

print(f"Original image: {traya_img_path.name}")
print(f"Original dimensions: {w_orig}x{h_orig} px")
print(f"Original file size: {orig_size_bytes} bytes ({orig_size_bytes // 1024} KB)")

# Run the 9-stage CV pipeline
t_cv_start = time.perf_counter()
res = run_preprocessing_pipeline(
    img_bgr=img_bgr,
    source_name=traya_img_path.name,
    debug_dir=debug_dir,
)
cv_latency_ms = round((time.perf_counter() - t_cv_start) * 1000, 1)

print("\n--- Preprocessing Execution Complete ---")
print(f"CV Preprocessing Latency: {cv_latency_ms} ms")
print(f"Boundary Detected: {res.metadata['boundary_detected']} (confidence={res.metadata['boundary_confidence']})")
print(f"Detected Corners: {res.metadata.get('detected_corners')}")
print(f"Perspective Corrected: {res.metadata['perspective_corrected']}")
print(f"Final Image Dimensions: {res.metadata['final_dimensions'][0]}x{res.metadata['final_dimensions'][1]} px")
print(f"Final File Size: {res.metadata['final_file_size_bytes']} bytes ({res.metadata['final_file_size_bytes'] // 1024} KB)")
print(f"Fallback Used: {res.metadata['fallback_used']}")

# Verify expected debug files
expected_files = [
    "01_original.jpg",
    "02_boundary_detected.jpg",
    "03_perspective.jpg",
    "04_crop.jpg",
    "05_background_normalized.jpg",
    "06_glare_reduced.jpg",
    "07_illumination_corrected.jpg",
    "08_text_enhanced.jpg",
    "09_final.jpg",
    "metadata.json",
]

print("\nVerifying generated debug artifacts:")
for fname in expected_files:
    fpath = debug_dir / fname
    status = "EXISTS" if fpath.exists() else "MISSING"
    size_kb = fpath.stat().st_size // 1024 if fpath.exists() else 0
    print(f"  * {fname:30s} [{status}] ({size_kb} KB)")

# ===========================================================================
# QWEN INTEGRATION TEST
# ===========================================================================
final_img_path = debug_dir / "09_final.jpg"
print("\n" + "=" * 80)
print(f"SENDING EXACT FINAL PREPROCESSED IMAGE ({final_img_path.name}) TO QWEN3.8-27B")
print("=" * 80)

with open(final_img_path, "rb") as f:
    final_data = f.read()
final_b64 = base64.b64encode(final_data).decode("utf-8")

SYSTEM_PROMPT = """You are LexMetra's packaged-commodity declaration extraction engine.
Extract: PRODUCT_NAME, MRP, USP, NET_QUANTITY, MFD, EXPIRY, USE_BEFORE, BATCH, MANUFACTURER, MARKETER, PACKER, IMPORTER, ADDRESS, CONSUMER_CARE, COUNTRY_OF_ORIGIN.

Return ONLY valid JSON:
{
  "product_name": { "value": "str|null", "confidence": 0.0, "status": "DETECTED|REVIEW_REQUIRED" },
  "declarations": [
    {
      "field": "FIELD_NAME",
      "value": "str|null",
      "unit": "str|null",
      "currency": "str|null",
      "evidence_text": "str",
      "confidence": 0.0,
      "status": "DETECTED|REVIEW_REQUIRED"
    }
  ]
}"""

payload = {
    "model": "qwen/qwen3.8-27b",
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract all visible declarations from this packaged commodity image."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{final_b64}"}
                }
            ]
        }
    ],
    "temperature": 0.05,
    "max_tokens": 2048,
    "response_format": {"type": "json_object"},
    "reasoning": {"effort": "none"},
}

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://lexmetra.local",
    "X-Title": "LexMetra CV Benchmark",
}

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
print(f"Endpoint: {ENDPOINT}")
print(f"Model: qwen/qwen3.8-27b | Reasoning effort: none | Max tokens: 2048")
print(f"Payload image size: {len(final_data)} bytes ({len(final_data)//1024} KB)")

t_qwen_start = time.perf_counter()
with httpx.Client(timeout=120.0) as client:
    qwen_resp = client.post(ENDPOINT, headers=headers, json=payload)
qwen_latency_ms = round((time.perf_counter() - t_qwen_start) * 1000, 1)

print(f"\nQwen HTTP Status: {qwen_resp.status_code}")
print(f"Qwen Latency: {qwen_latency_ms} ms ({qwen_latency_ms/1000:.2f} s)")

try:
    resp_json = qwen_resp.json()
except Exception as e:
    resp_json = {"error": str(e), "raw": qwen_resp.text}

usage = resp_json.get("usage", {})
prompt_tokens = usage.get("prompt_tokens")
completion_tokens = usage.get("completion_tokens")
total_tokens = usage.get("total_tokens")
completion_details = usage.get("completion_tokens_details", {})
reasoning_tokens = completion_details.get("reasoning_tokens", 0)

print(f"Prompt Tokens: {prompt_tokens}")
print(f"Completion Tokens: {completion_tokens}")
print(f"Reasoning Tokens: {reasoning_tokens}")
print(f"Total Tokens: {total_tokens}")

choices = resp_json.get("choices", [])
first_choice = choices[0] if choices else {}
message = first_choice.get("message", {})
content = message.get("content")

parsed_output = None
if content:
    try:
        parsed_output = json.loads(content)
    except Exception:
        pass

print("\n" + "=" * 80)
print("PARSED QWEN EXTRACTION")
print("=" * 80)
if parsed_output:
    print(json.dumps(parsed_output, indent=2, ensure_ascii=False))
else:
    print("Raw Content:", content)

# Save test results
results_file = debug_dir / "qwen_test_result.json"
with open(results_file, "w", encoding="utf-8") as f:
    json.dump({
        "cv_latency_ms": cv_latency_ms,
        "qwen_latency_ms": qwen_latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "parsed_output": parsed_output,
        "raw_response": resp_json,
    }, f, indent=2)

print(f"\n[Saved full test results to {results_file}]")
