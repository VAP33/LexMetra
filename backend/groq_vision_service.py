import os
import time
import base64
import json
import logging
import re
from typing import List, Tuple, Dict, Any, Optional
import httpx
import cv2
import numpy as np

logger = logging.getLogger("groq_vision")

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")

GROQ_INSPECTION_PROMPT = """You are India's Legal Metrology (Packaged Commodities) Rules, 2011 compliance perception engine.
Analyze the provided package face images as faces of the SAME product.

Extract the statutory declarations visible on the package with strict factual accuracy.
NEVER extrapolate or invent data.

FIELDS TO EXTRACT:
- product_name: Brand and generic product name
- product_id: Explicit printed alphanumeric product ID / SKU (NOT the 12-14 digit barcode)
- barcode: 12-14 digit numeric barcode / GTIN / EAN printed on the package (e.g. "8901071705479")
- fssai_license_number: 14-digit FSSAI food business license or registration number (e.g. "10012026000226")
- mrp: Maximum Retail Price (total package price in INR, e.g. "₹800.00" or "800.00")
- unit_sale_price: Rate per unit (e.g. "₹26.67/ml")
- net_quantity: Declared net weight / volume with unit (e.g. "150 g", "500 ml")
- mfg_date: Month & Year of manufacture/packing (e.g. "01/2025")
- expiry_date: Explicit expiry date or best before statement
- batch_code: Batch / Lot number (e.g. "B.No: B123")
- manufacturer_name_address: Complete name and address of manufacturer / packer / marketer
- consumer_care: Customer care helpline phone, email, and contact address

Return a valid JSON object matching EXACTLY this structure:
{
  "product_name": "string or null",
  "product_id": "string or null",
  "barcode": "string or null",
  "fssai_license_number": "string or null",
  "declarations": [
    {
      "field": "MRP | USP | NET_QUANTITY | MFD | EXPIRY | USE_BEFORE | BATCH | MANUFACTURER | CONSUMER_CARE | FSSAI | BARCODE",
      "value": "string or null",
      "face": "Face 1 | Face 2 | Face 3",
      "evidence_text": "verbatim visible text (<50 chars)",
      "confidence": 0.0 to 1.0
    }
  ]
}

Return ONLY raw JSON, without markdown formatting or commentary.
"""

def resize_and_compress_image(img_bgr: np.ndarray, max_dim: int = 768, quality: int = 80) -> str:
    """Resize image to reasonable max dimension and compress as JPEG base64 for fast Groq transmission."""
    h, w = img_bgr.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        img_bgr = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, buffer = cv2.imencode('.jpg', img_bgr, encode_params)
    if not success:
        raise ValueError("Failed to encode image to JPEG")
    return base64.b64encode(buffer).decode('utf-8')


def is_groq_available(api_key: Optional[str] = None) -> bool:
    """Return True if a valid Groq API key is present."""
    key = (api_key or os.getenv("GROQ_API_KEY") or "").strip()
    return bool(key and key.startswith("gsk_"))


async def inspect_package_with_groq(
    images: List[Tuple[str, np.ndarray]], 
    custom_prompt: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_secs: float = 25.0
) -> Dict[str, Any]:
    """
    Send up to 3 package face images in ONE Groq multimodal request.
    Strictly follows:
    - [GROQ] REQUEST START
    - [GROQ] 3 IMAGES SENT
    - [GROQ] RESPONSE RECEIVED: Xs
    - [GROQ] RESULT RETURNED
    """
    # Normalize images input to List[Tuple[str, np.ndarray]]
    norm_images: List[Tuple[str, np.ndarray]] = []
    for idx, item in enumerate(images or []):
        if isinstance(item, tuple) and len(item) == 2:
            lbl = str(item[0])
            arr = item[1]
            if isinstance(arr, np.ndarray):
                norm_images.append((lbl, arr))
            elif isinstance(arr, (str, bytes, os.PathLike)):
                loaded = cv2.imread(str(arr))
                if loaded is not None:
                    norm_images.append((lbl, loaded))
        elif isinstance(item, np.ndarray):
            norm_images.append((f"Face {idx+1}", item))
        elif isinstance(item, (str, bytes, os.PathLike)):
            loaded = cv2.imread(str(item))
            if loaded is not None:
                norm_images.append((f"Face {idx+1}", loaded))
    images = norm_images
    num_images = min(3, len(images))

    # -------------------------------------------------------------------------
    # High-Speed Perception: Gemini 3.5 Flash Lite Primary (~1.4s response time)
    # Provides full statutory Legal Metrology compliance perception without latency
    # -------------------------------------------------------------------------
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        try:
            import config
            gemini_key = config.get_gemini_api_key()
        except Exception:
            pass

    if gemini_key:
        try:
            t_gem0 = time.perf_counter()
            print("\n" + "=" * 80, flush=True)
            print(f">>> [STATUTORY PERCEPTION - GEMINI HIGH SPEED ENGINE] faces={num_images}", flush=True)
            print("=" * 80, flush=True)

            from google import genai
            from google.genai import types
            from PIL import Image

            client = genai.Client(api_key=gemini_key)
            contents: List[Any] = [custom_prompt or GROQ_INSPECTION_PROMPT]

            for idx, (face_label, img_bgr) in enumerate(images[:num_images]):
                rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
                pil_img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                contents.append(f"\n--- [{face_label or f'Face {idx+1}'}] ---")
                contents.append(pil_img)

            candidate_models = ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
            for model_name in candidate_models:
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.05,
                        )
                    )
                    raw_text = (resp.text or "").strip()
                    if raw_text:
                        if raw_text.startswith("```"):
                            raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
                            raw_text = re.sub(r"\n?```\s*$", "", raw_text).strip()
                        gem_res_json = json.loads(raw_text)
                        lat_sec = round(time.perf_counter() - t_gem0, 2)
                        decls = gem_res_json.get("declarations", [])
                        print(f"[+] [GEMINI STATUTORY SUCCESS] Model={model_name} Latency={lat_sec}s Declarations={len(decls)}", flush=True)
                        return gem_res_json
                except Exception as m_err:
                    print(f"[!] [GEMINI MODEL {model_name}] {m_err}. Trying next candidate...", flush=True)
        except Exception as gem_err:
            print(f"[!] [GEMINI SPEED PATH ERROR] {gem_err}. Falling back to secondary provider...", flush=True)

    # Secondary Path: Groq / OpenRouter Fallback
    if not is_groq_available(api_key):
        logger.info("Neither Gemini nor Groq available. Skipping remote perception.")
        return {"product_name": None, "product_id": None, "declarations": []}

    key = (api_key or os.getenv("GROQ_API_KEY") or "").strip()

    print(f"\n[GROQ FALLBACK] REQUEST START", flush=True)

    content_list: List[Dict[str, Any]] = [
        {"type": "text", "text": custom_prompt or GROQ_INSPECTION_PROMPT}
    ]

    for idx, (face_label, img_bgr) in enumerate(images[:num_images]):
        b64_str = resize_and_compress_image(img_bgr, max_dim=768, quality=80)
        content_list.append({
            "type": "text", 
            "text": f"--- [{face_label or f'Face {idx+1}'}] ---"
        })
        content_list.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64_str}"
            }
        })

    print(f"[GROQ] {num_images} IMAGES SENT", flush=True)

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "user",
                "content": content_list
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.05,
        "max_tokens": 900
    }

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout_secs) as client:
        resp = await client.post(
            GROQ_ENDPOINT,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload
        )
    
    latency = time.perf_counter() - t0
    print(f"[GROQ] RESPONSE RECEIVED: {latency:.2f}s", flush=True)

    if resp.status_code != 200:
        error_detail = resp.text[:300]
        print(f"[!] [GROQ ERROR] Status {resp.status_code}: {error_detail}", flush=True)
        raise RuntimeError(f"Groq API returned HTTP {resp.status_code}: {error_detail}")

    data = resp.json()
    raw_content = data["choices"][0]["message"]["content"]

    try:
        clean_text = raw_content.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```[a-zA-Z]*\n?", "", clean_text)
            clean_text = re.sub(r"\n?```\s*$", "", clean_text).strip()
        result_json = json.loads(clean_text)
    except Exception as e:
        print(f"[!] [GROQ JSON PARSE ERROR]: {e}\nRaw: {raw_content[:200]}", flush=True)
        raise ValueError(f"Failed to parse Groq structured JSON: {e}")

    print(f"[GROQ] RESULT RETURNED", flush=True)
    return result_json


def groq_result_to_classified_fields(groq_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Convert Groq multimodal response into classified fields compatible with rule engine."""
    classified: Dict[str, Dict[str, Any]] = {}
    
    field_map = {
        "MRP": "mrp",
        "USP": "unit_sale_price",
        "NET_QUANTITY": "net_quantity",
        "MFD": "mfg_date",
        "EXPIRY": "expiry_date",
        "USE_BEFORE": "best_before_use_by",
        "USE_BY": "best_before_use_by",
        "BEST_BEFORE": "best_before_use_by",
        "BATCH": "batch_code",
        "LOT": "batch_code",
        "MANUFACTURER": "manufacturer_name",
        "MARKETER": "marketer_name",
        "CONSUMER_CARE": "consumer_care",
        "PRODUCT_NAME": "common_name",
        "PRODUCT_ID": "product_id",
        "FSSAI": "fssai_license_number",
        "FSSAI_LICENSE": "fssai_license_number",
        "FSSAI_NO": "fssai_license_number",
        "BARCODE": "barcode",
        "GTIN": "barcode",
        "EAN": "barcode",
    }

    prod_name = groq_data.get("product_name")
    if prod_name:
        classified["common_name"] = {
            "field": "common_name",
            "value": str(prod_name).strip(),
            "raw_text": str(prod_name).strip(),
            "confidence": 0.95,
            "status": "DETECTED",
            "face": "Face 1",
        }

    prod_id = groq_data.get("product_id")
    if prod_id:
        classified["product_id"] = {
            "field": "product_id",
            "value": str(prod_id).strip(),
            "raw_text": str(prod_id).strip(),
            "confidence": 0.95,
            "status": "DETECTED",
            "face": "Face 1",
        }

    fssai_lic = groq_data.get("fssai_license_number")
    if fssai_lic:
        f_val = str(fssai_lic).strip()
        classified["fssai_license_number"] = {
            "field": "fssai_license_number",
            "value": f_val,
            "raw_text": f_val,
            "confidence": 0.95,
            "status": "DETECTED",
            "face": "Face 1",
        }

    barcode_val = groq_data.get("barcode")
    if barcode_val:
        b_val = str(barcode_val).strip()
        classified["barcode"] = {
            "field": "barcode",
            "value": b_val,
            "raw_text": b_val,
            "confidence": 0.98,
            "status": "DETECTED",
            "face": "Face 1",
        }

    for decl in groq_data.get("declarations", []):
        f_raw = (decl.get("field") or "").upper().strip()
        val = decl.get("value")
        if not val or val in ("null", "None"):
            continue
        canon_key = field_map.get(f_raw, f_raw.lower())
        face = decl.get("face", "Face 1")
        evidence = decl.get("evidence_text") or str(val)
        conf = float(decl.get("confidence", 0.95) or 0.95)

        f_data = {
            "field": canon_key,
            "value": str(val).strip(),
            "raw_text": str(evidence).strip(),
            "confidence": conf,
            "status": "DETECTED",
            "face": face,
        }

        # Parse numeric quantity if available
        if canon_key == "net_quantity":
            m_qty = re.search(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?", str(val))
            if m_qty:
                try:
                    f_data["numeric_value"] = float(m_qty.group(1))
                    f_data["numeric_unit"] = m_qty.group(2) or "g"
                except Exception:
                    pass

        # Parse numeric MRP if available
        if canon_key == "mrp":
            m_mrp = re.search(r"(\d+(?:\.\d+)?)", str(val).replace(",", ""))
            if m_mrp:
                try:
                    f_data["numeric_value"] = float(m_mrp.group(1))
                except Exception:
                    pass

        classified[canon_key] = f_data
        if canon_key in ("manufacturer_name", "marketer_name", "packer_name"):
            if "manufacturer_name_address" not in classified or canon_key == "manufacturer_name":
                classified["manufacturer_name_address"] = dict(f_data)

    return classified
