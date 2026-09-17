import httpx
import json
import os
import time
from dotenv import load_dotenv

load_dotenv('.env')
key = os.environ.get('OPENROUTER_API_KEY')
endpoint = 'https://openrouter.ai/api/v1/chat/completions'
headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

manifest = {
    'Face 1': [
        {'text': 'CADBURY GEMS', 'bbox': [50, 40, 200, 60]},
        {'text': 'CHOCOLATE BUTTONS', 'bbox': [50, 110, 180, 30]}
    ],
    'Face 2': [
        {'text': 'NET WEIGHT: 25.2 g', 'bbox': [100, 80, 150, 25]},
        {'text': 'MRP Rs. 20.00 (INCL. OF ALL TAXES)', 'bbox': [100, 120, 220, 30]},
        {'text': 'USP: Rs. 0.79 / g', 'bbox': [100, 160, 130, 25]},
        {'text': 'MFD. 12/24', 'bbox': [100, 200, 100, 20]},
        {'text': 'USE BY 9 MONTHS FROM PKG', 'bbox': [100, 230, 180, 20]},
        {'text': 'BATCH NO. B104', 'bbox': [100, 260, 110, 20]},
        {'text': 'MFD BY MONDELEZ INDIA FOODS PVT LTD', 'bbox': [100, 300, 250, 40]},
        {'text': 'LIC NO. 10014022002711', 'bbox': [100, 350, 170, 20]}
    ],
    'Face 3': [
        {'text': 'CONSUMER CARE: 1800-22-7080', 'bbox': [80, 50, 200, 30]}
    ]
}

system_prompt = """You are LexMetra's package-declaration semantic extraction engine.
Analyze the structured OCR manifest from faces of the SAME packaged commodity.
Resolve declarations into canonical facts without hallucination.
Output JSON schema:
{
  "product_name": {"value": "str", "face": "Face X", "evidence_text": "str", "bbox": [x,y,w,h]},
  "product_id": {"value": null, "face": null, "evidence_text": null, "bbox": null},
  "declarations": [
    {"field": "MRP", "value": "20.00", "currency": "INR", "face": "Face 2", "evidence_text": "MRP Rs. 20.00", "bbox": [100, 120, 220, 30]},
    {"field": "NET_QUANTITY", "value": "25.2 g", "unit": "g", "face": "Face 2", "evidence_text": "NET WEIGHT: 25.2 g", "bbox": [100, 80, 150, 25]}
  ]
}"""

payload = {
    'model': 'qwen/qwen3.8-27b',
    'messages': [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': f"STRUCTURED OCR MANIFEST:\n{json.dumps(manifest, indent=2)}"}
    ],
    'response_format': {'type': 'json_object'},
    'temperature': 0.05,
    'max_tokens': 1500
}

t0 = time.perf_counter()
print('Sending manifest to Qwen 27B on OpenRouter...')
resp = httpx.post(endpoint, headers=headers, json=payload, timeout=25.0)
elapsed = time.perf_counter() - t0
print(f'Done in {elapsed:.2f}s! Status: {resp.status_code}')
if resp.status_code == 200:
    print(resp.json()['choices'][0]['message']['content'])
else:
    print('Error:', resp.text[:400])
