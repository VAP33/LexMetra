import os
import sys
import asyncio
from pathlib import Path
import cv2
import json

backend_dir = Path(r"c:\Users\HP\SIH LATEST\backend")
sys.path.insert(0, str(backend_dir))

import httpx
import qwen_perception
from geometry import CoordinateSpace, CoordinateTransform

PROMPT = """You are LexMetra's package-declaration extraction engine. Analyze images as faces of the SAME package.
EXTRACT ONLY VISIBLE INFO. NEVER GUESS, HALLUCINATE, OR INVENT DATA.

FIELDS: PRODUCT_NAME, PRODUCT_ID, MRP, USP, NET_QUANTITY, MFD, EXPIRY, USE_BEFORE, BATCH, MANUFACTURER, MARKETER, PACKER, IMPORTER, ADDRESS, CONSUMER_CARE, COUNTRY_OF_ORIGIN.

OUTPUT SCHEMA (JSON):
{
  "product_name": "str|null",
  "product_id": "str|null",
  "declarations": [
    {
      "field": "FIELD_NAME",
      "value": "str|null",
      "unit": "str|null",
      "currency": "str|null",
      "basis": "str|null",
      "face": "Face 1",
      "evidence_text": "short visible text (<50 chars)",
      "confidence": 0.95,
      "status": "DETECTED|REVIEW_REQUIRED"
    }
  ]
}

CRITICAL RULES:
1. PRODUCT_NAME: The brand / product title (e.g. "Hair Actives", "Traya Hair Actives").
2. PRODUCT_ID: Extract ONLY when an explicit Product ID, SKU, Product Code, or Item Code is printed on the label. If absent, set null. Never invent.
3. MRP vs USP: Carefully match labels with their actual values!
   - MRP is the total package retail price (e.g., "MRP ₹: 800.00", "₹800.00").
   - USP is the Unit Sale Price per unit (e.g., "₹ 26.67 per ml", "26.67/ml").
   DO NOT swap MRP and USP! Total price is MRP; rate per ml/g is USP.
4. NET_QUANTITY: Declared net quantity (e.g., "30 ml", "30ml", "100g").
5. BATCH: Batch or lot number (e.g. "C26HN005", "C26H005").
6. MFD vs EXPIRY: MFD is date of manufacture/packing (e.g. "03/2026", "08/2026"). EXPIRY is expiry date. USE_BEFORE is e.g. "24 months from date of mfg". Keep them distinct!
7. ROLES: MANUFACTURER (e.g. Cheryl Laboratories...) and MARKETER (e.g. Tatvartha Health...) are distinct. Do not merge them!
8. CONCISENESS: Keep evidence_text under 50 characters. Extract each field once.

Return ONLY valid JSON."""

async def test_prompt():
    img_path = r"c:\Users\HP\SIH LATEST\images new\TRAYA BACK.jpg"
    bgr = cv2.imread(img_path)
    h, w = bgr.shape[:2]

    transform = CoordinateTransform(
        source_space=CoordinateSpace.CANONICAL_PIXEL,
        target_space=CoordinateSpace.ORIGINAL_PIXEL,
        matrix=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        source_dims=(w, h),
        target_dims=(w, h),
    )
    faces = [("Face 1", bgr, transform)]
    batch = qwen_perception.prepare_perception_batch(faces)

    key = os.getenv("OPENROUTER_API_KEY2") or os.getenv("GROQ_API_KEY")
    provider = qwen_perception.OpenRouterQwenProvider(api_key=key)

    payload = {
        "model": provider.model_name,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": batch.messages_content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.05,
        "max_tokens": 1000,
        "reasoning": {"effort": "none"},
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://lexmetra.internal",
        "X-Title": "LexMetra-V1-Perception",
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(provider.endpoint, json=payload, headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            with open(r"c:\Users\HP\SIH LATEST\backend\traya_qwen_clean.json", "w", encoding="utf-8") as f:
                f.write(content)
            print("Successfully saved to traya_qwen_clean.json!")
            parsed = json.loads(content)
            print(f"Product Name: {parsed.get('product_name')}")
            print(f"Product ID: {parsed.get('product_id')}")
            for d in parsed.get("declarations", []):
                print(f"  {d.get('field'):18s} = '{d.get('value')}' (evidence: '{d.get('evidence_text')}')")
        else:
            print(f"Error: {resp.text}")

if __name__ == "__main__":
    asyncio.run(test_prompt())
