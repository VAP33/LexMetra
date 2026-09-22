"""
Isolated benchmark harness: Testing Qwen3.8-27B through OpenRouter on GEMS package images.
Evaluates model accuracy, cross-face multimodal intelligence, and latency.
Does not alter any production code.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load backend/.env
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=False)

# Configure UTF-8 on Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY2")
if not api_key:
    print("ERROR: OPENROUTER_API_KEY not found in environment or .env file!", file=sys.stderr)
    sys.exit(1)

MODEL_NAME = "qwen/qwen3.8-27b"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are LexMetra's packaged-commodity declaration extraction engine.

The supplied images are Face 1, Face 2, and Face 3 of the SAME physical package. Preserve these exact face names. Use all faces together to understand the package, but keep evidence coordinates tied to the face where the text appears.

EXTRACT ONLY VISIBLE INFORMATION. NEVER GUESS, HALLUCINATE, CALCULATE, DERIVE, OR FILL MISSING DATA.

Extract:
PRODUCT_NAME, PRODUCT_ID, PRODUCT_CATEGORY, MRP, USP, NET_QUANTITY, MFD, EXPIRY, USE_BEFORE, BATCH, MANUFACTURER, MARKETER, PACKER, IMPORTER, ADDRESS, CONSUMER_CARE, COUNTRY_OF_ORIGIN.

Return ONLY valid JSON:

{
  "product_name": {
    "value": "str|null",
    "face": "Face X|null",
    "evidence_text": "str",
    "bbox": [x,y,w,h],
    "confidence": 0.0,
    "status": "DETECTED|REVIEW_REQUIRED"
  },
  "product_id": {
    "value": "str|null",
    "face": "Face X|null",
    "evidence_text": "str",
    "bbox": [x,y,w,h],
    "confidence": 0.0,
    "status": "DETECTED|REVIEW_REQUIRED"
  },
  "product_category": {
    "value": "str|null",
    "face": "Face X|null",
    "evidence_text": "str",
    "bbox": [x,y,w,h],
    "confidence": 0.0,
    "status": "DETECTED|REVIEW_REQUIRED"
  },
  "declarations": [
    {
      "field": "FIELD_NAME",
      "value": "str|null",
      "unit": "str|null",
      "currency": "str|null",
      "basis": "str|null",
      "face": "Face X",
      "evidence_text": "exact visible text",
      "bbox": [x,y,w,h],
      "coordinate_space": "CANONICAL",
      "confidence": 0.0,
      "status": "DETECTED|REVIEW_REQUIRED"
    }
  ],
  "face_metadata": {
    "Face 1": {"inferred_surface_hypothesis": "str"},
    "Face 2": {"inferred_surface_hypothesis": "str"},
    "Face 3": {"inferred_surface_hypothesis": "str"}
  }
}

RULES:

1. MRP = total package/retail price. MRP is NOT USP.

2. USP = printed unit sale price containing BOTH a monetary amount and an explicit per-unit basis such as /g, /kg, /ml, /L, /unit, or equivalent. Do not calculate USP. Serving sizes, nutrition values, ingredient quantities, "Per X g Serve", "Per X ml Serve", "Includes X", and MRP are NOT USP.

3. NET_QUANTITY = declared TOTAL quantity of the packaged commodity. Serving sizes, "Per X", nutrition quantities, ingredient quantities, "Includes X", and individual component quantities are NOT automatically net quantity.

4. Keep MFD, EXPIRY, and USE_BEFORE separate. Do not convert relative use-before statements into calendar dates.

5. BATCH/LOT must remain separate from barcode, GTIN, EAN, UPC, FSSAI, licence, or registration numbers.

6. PRODUCT_ID only when explicitly identified as Product ID, SKU, Product Code, or equivalent. Barcode/GTIN/EAN/UPC is NOT automatically Product ID. Never derive Product ID.

7. PRODUCT_CATEGORY must describe what the product actually IS, not its brand, flavour, variant, character, ingredient, or marketing claim.

8. Keep MANUFACTURER, MARKETER, PACKER, and IMPORTER separate. Assign roles only when supported by visible text.

9. evidence_text must be the actual visible text supporting the field. bbox must correspond to that evidence and remain face-specific. Never fabricate coordinates.

10. If information is unreadable, ambiguous, contradictory, or unsupported, return value=null and status=REVIEW_REQUIRED.

11. Use cross-face reasoning because all images represent the SAME package.

Return ONLY valid JSON."""

# Locate the 3 GEMS images
project_root = Path(__file__).resolve().parent.parent.parent
images_dir = project_root / "images new"

face_files = [
    ("Face 1", images_dir / "GEMS.jpg"),
    ("Face 2", images_dir / "GEMS 1.jpg"),
    ("Face 3", images_dir / "GEMS 2.jpg"),
]

for face_name, p in face_files:
    if not p.exists():
        print(f"ERROR: Image file not found for {face_name}: {p}", file=sys.stderr)
        sys.exit(1)

print("Preparing images for single batched multimodal request...")
user_content = [
    {
        "type": "text",
        "text": "Analyze the following 3 faces (Face 1, Face 2, Face 3) of the SAME physical package and extract all visible declarations according to the rules."
    }
]

for face_name, p in face_files:
    with open(p, "rb") as f:
        data = f.read()
    b64_str = base64.b64encode(data).decode("utf-8")
    file_size_kb = len(data) // 1024
    print(f"  * {face_name}: {p.name} ({file_size_kb} KB, base64 length {len(b64_str)})")
    user_content.append({
        "type": "text",
        "text": f"--- {face_name} ---"
    })
    user_content.append({
        "type": "image_url",
        "image_url": {
            "url": f"data:image/jpeg;base64,{b64_str}"
        }
    })

payload = {
    "model": MODEL_NAME,
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ],
    "temperature": 0.05,
    "max_tokens": 3000,
    "reasoning": {"effort": "none"},
    "response_format": {"type": "json_object"},
}

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://lexmetra.local",
    "X-Title": "LexMetra Benchmark",
}

print(f"\nSending ONE batched multimodal request to OpenRouter...")
print(f"Endpoint: {ENDPOINT}")
print(f"Model: {MODEL_NAME}")
print(f"Temperature: 0.05 | Max Tokens: 2048 | JSON Object Format: True")

t_start = time.perf_counter()

with httpx.Client(timeout=180.0) as client:
    response = client.post(ENDPOINT, headers=headers, json=payload)

latency_ms = round((time.perf_counter() - t_start) * 1000, 1)

print("\n" + "=" * 80)
print("BENCHMARK TEST EXECUTION RESULTS")
print("=" * 80)
print(f"A. HTTP Status: {response.status_code}")
print(f"B. Total Latency: {latency_ms:.1f} ms ({latency_ms / 1000:.2f} s)")

try:
    resp_data = response.json()
except Exception as e:
    resp_data = {"raw_text": response.text, "json_parse_error": str(e)}

# Save the full benchmark output to a JSON file immediately
output_file = project_root / "backend" / "tools" / "qwen_openrouter_gems_result.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump({
        "status_code": response.status_code,
        "latency_ms": latency_ms,
        "raw_response": resp_data,
    }, f, indent=2)

usage = resp_data.get("usage", {}) if isinstance(resp_data, dict) else {}
prompt_tokens = usage.get("prompt_tokens")
completion_tokens = usage.get("completion_tokens")
total_tokens = usage.get("total_tokens")

print(f"C. Time to First Response: Not directly reported by standard HTTP POST (total roundtrip = {latency_ms:.1f} ms)")
print(f"D. Prompt / Input Token Count: {prompt_tokens}")
print(f"E. Output Token Count: {completion_tokens}")
if total_tokens:
    print(f"   Total Token Count: {total_tokens}")

choices = resp_data.get("choices", []) if isinstance(resp_data, dict) else []
first_choice = choices[0] if choices else {}
finish_reason = first_choice.get("finish_reason")
print(f"F. Finish Reason: {finish_reason}")

message = first_choice.get("message", {})
content = message.get("content")
reasoning = message.get("reasoning")
tool_calls = message.get("tool_calls")

valid_json = False
parsed_extraction = None

if content:
    try:
        parsed_extraction = json.loads(content)
        valid_json = True
    except Exception as je:
        # Try stripping markdown fences
        clean = content.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        try:
            parsed_extraction = json.loads(clean.strip())
            valid_json = True
        except Exception:
            pass

print(f"G. Whether Valid JSON was Returned: {valid_json}")

if resp_data.get("error"):
    print(f"I. API / Provider Error: {resp_data.get('error')}")
else:
    print(f"I. API / Provider Error: None")

if not content:
    print("\nJ. Raw Response Structure (since content was null/empty):")
    print(json.dumps(resp_data, indent=2, ensure_ascii=False))
    if reasoning:
        print("\nFound reasoning in response (preview 500 chars):")
        print(reasoning[:500] + "...")

print("\n" + "=" * 80)
print("H. COMPLETE PARSED EXTRACTION")
print("=" * 80)
if parsed_extraction:
    print(json.dumps(parsed_extraction, indent=2, ensure_ascii=False))
else:
    print("Raw Content:")
    print(content)

print(f"\n[Saved benchmark data to {output_file}]")

