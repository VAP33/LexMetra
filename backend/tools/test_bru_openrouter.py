import base64
import json
import os
import sys
import time
from pathlib import Path

import cv2
import httpx
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
key = os.environ.get("OPENROUTER_API_KEY")

if not key:
    print("No OPENROUTER_API_KEY")
    sys.exit(1)

def encode_img(path: str, max_dim: int = 1024) -> str:
    img = cv2.imread(path)
    h, w = img.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    _, enc = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(enc.tobytes()).decode("utf-8")

b64_front = encode_img("images new/BRU FRONT.jpg")
b64_back = encode_img("images new/BRU BACK.jpg")

prompt = """You are LexMetra's package-declaration extraction engine. Analyze images as Face 1 and Face 2 of the SAME physical package.
EXTRACT ONLY VISIBLE INFO. NEVER GUESS OR FABRICATE.

FIELDS TO EXTRACT:
- PRODUCT_NAME (e.g. BRU Instant Coffee-Chicory mixture)
- PRODUCT_ID (Printed item/SKU/material code, e.g. 64934436, NOT barcode)
- MRP (Total price, e.g. 420.00)
- USP (Unit Sale Price rate, e.g. 2.80/g)
- NET_QUANTITY (Total quantity, e.g. 150 g)
- MFD (Manufacturing/Packaging date, e.g. 13/05/26)
- EXPIRY / USE_BEFORE (Best before / expiry, e.g. 12/10/27)
- BATCH (Batch/lot code, e.g. HF130526 17:08)
- MANUFACTURER (Manufacturer name & address)
- MARKETER (Marketer name & address)
- CONSUMER_CARE (Helpline/email, e.g. 1800-10-22-221 Levercare)

Return ONLY valid JSON matching:
{
  "product_name": {"value": "...", "face": "Face 1"},
  "product_id": {"value": "...", "face": "Face 1"},
  "declarations": [
    {"field": "FIELD_NAME", "value": "...", "unit": null, "face": "Face X", "evidence_text": "..."}
  ]
}
"""

payload = {
    "model": "qwen/qwen3.8-27b",
    "messages": [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Face 1 (Front Panel):"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_front}"}},
                {"type": "text", "text": "Face 2 (Back Panel):"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_back}"}},
            ],
        },
    ],
    "response_format": {"type": "json_object"},
    "temperature": 0.05,
    "max_tokens": 3000,
}

print("[*] Sending request to OpenRouter (qwen/qwen3.8-27b)...")
t0 = time.time()
r = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {key}"},
    json=payload,
    timeout=75.0,
)
elapsed = time.time() - t0
print(f"[*] Response received in {elapsed:.2f}s, status: {r.status_code}")

if r.status_code == 200:
    res = r.json()
    msg = res["choices"][0]["message"]
    print("Message keys:", msg.keys())
    print("Content:", repr(msg.get("content")))
    print("Reasoning:", repr(msg.get("reasoning")))
    print("Refusal:", repr(msg.get("refusal")))
    text = msg.get("content") or msg.get("reasoning") or ""
    Path("backend/tools/test_bru_openrouter_result.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print("Full response saved to backend/tools/test_bru_openrouter_result.json")
else:
    print("ERROR:", r.text)
