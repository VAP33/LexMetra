import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import cv2
import httpx
import json
from dotenv import load_dotenv

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
load_dotenv(backend_dir / ".env")

import geometry
from localization.sanskruti.paddle_detector import PaddleTextDetector

def run_fast_pipeline():
    images_dir = backend_dir.parent / "images new"
    face_paths = [
        ("Face 1", images_dir / "BRU FRONT.jpg"),
        ("Face 2", images_dir / "BRU BACK.jpg"),
        ("Face 3", images_dir / "BRU BACK 2.jpg"),
    ]
    
    t_start = time.perf_counter()
    
    # T1: Image decode
    t1_0 = time.perf_counter()
    raw_images = []
    for f_id, p in face_paths:
        img = cv2.imread(str(p))
        if img is None:
            raise FileNotFoundError(f"Could not load {p}")
        raw_images.append((f_id, img))
    t1_time = time.perf_counter() - t1_0
    
    # T2: Preprocessing (surface normalization)
    t2_0 = time.perf_counter()
    faces_canon = []
    for f_id, img in raw_images:
        norm = geometry.normalize_package_surface(img, source_name=f_id)
        faces_canon.append((f_id, norm.canonical_image, norm.inverse_transform))
    t2_time = time.perf_counter() - t2_0
    
    # T3 & T4: Parallel PaddleOCR / DBNet detection & recognition
    det = PaddleTextDetector.get_instance()
    det._init_engine()
    
    t34_0 = time.perf_counter()
    def process_face(face_tuple):
        fid, img_bgr, inv = face_tuple
        polys = det.detect_polygons(img_bgr)
        return fid, polys, img_bgr
    
    with ThreadPoolExecutor(max_workers=3) as ex:
        detected_results = list(ex.map(process_face, faces_canon))
    t34_time = time.perf_counter() - t34_0
    
    # T5: Construct Normalized OCR Manifest
    t5_0 = time.perf_counter()
    manifest = {}
    total_tokens = 0
    for fid, polys, _ in detected_results:
        manifest[fid] = []
        for p in polys:
            if p.text and len(p.text.strip()) > 0:
                manifest[fid].append({
                    "text": p.text.strip(),
                    "bbox": [p.bbox_xywh[0], p.bbox_xywh[1], p.bbox_xywh[2], p.bbox_xywh[3]],
                    "confidence": round(p.confidence, 3),
                })
                total_tokens += 1
    t5_time = time.perf_counter() - t5_0
    
    # T6: Selective crop extraction for key/ambiguous regions
    t6_0 = time.perf_counter()
    crops = []
    import base64
    for fid, polys, img_bgr in detected_results:
        for p in polys:
            txt = (p.text or "").lower()
            if any(k in txt for k in ["mrp", "₹", "rs.", "mfd", "use by", "batch", "lot", "net"]):
                bx, by, bw, bh = p.bbox_xywh
                pad = 4
                x1 = max(0, bx - pad)
                y1 = max(0, by - pad)
                x2 = min(img_bgr.shape[1], bx + bw + pad)
                y2 = min(img_bgr.shape[0], by + bh + pad)
                crop_patch = img_bgr[y1:y2, x1:x2]
                if crop_patch.size > 0:
                    ok, enc = cv2.imencode(".jpg", crop_patch, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    if ok:
                        crops.append({
                            "face": fid,
                            "text": p.text,
                            "bbox": [bx, by, bw, bh],
                            "b64": base64.b64encode(enc.tobytes()).decode("utf-8")
                        })
    t6_time = time.perf_counter() - t6_0
    
    # T7: Qwen 27B Semantic Resolution
    t7_0 = time.perf_counter()
    groq_key = os.environ.get("GROQ_API_KEY")
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
    
    system_prompt = """You are LexMetra's package-declaration semantic extraction engine.
Analyze the structured OCR manifest from 3 package faces of the SAME physical product.
Extract visible declarations strictly into valid JSON matching schema:
{
  "product_name": {"value": "str", "face": "Face X", "evidence_text": "str"},
  "product_id": {"value": null, "face": null, "evidence_text": null},
  "declarations": [
    {"field": "MRP", "value": "420.00", "currency": "INR", "face": "Face X", "evidence_text": "..."},
    {"field": "NET_QUANTITY", "value": "150 g", "unit": "g", "face": "Face X", "evidence_text": "..."},
    {"field": "MFD", "value": "...", "face": "Face X", "evidence_text": "..."},
    {"field": "EXPIRY", "value": "...", "face": "Face X", "evidence_text": "..."},
    {"field": "BATCH", "value": "...", "face": "Face X", "evidence_text": "..."}
  ]
}
Return ONLY valid JSON."""

    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"STRUCTURED OCR MANIFEST:\n{json.dumps(manifest, indent=1)}"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.05,
        "max_tokens": 1500
    }
    
    r = httpx.post(endpoint, headers=headers, json=payload, timeout=25.0)
    t7_time = time.perf_counter() - t7_0
    
    t_total = time.perf_counter() - t_start
    
    print("\n" + "=" * 80)
    print("PERCEPTION TIMING")
    print(f"T1 Image Decode:        {t1_time:.2f}s")
    print(f"T2 Preprocessing:       {t2_time:.2f}s")
    print(f"T3+T4 PaddleOCR Parallel: {t34_time:.2f}s ({total_tokens} text tokens detected)")
    print(f"T5 Manifest Build:      {t5_time:.3f}s")
    print(f"T6 Crop Extraction:     {t6_time:.3f}s ({len(crops)} declaration crops)")
    print(f"T7 Qwen 27B Semantic:   {t7_time:.2f}s (Status {r.status_code})")
    print(f"TOTAL TIME:             {t_total:.2f}s")
    print("=" * 80)
    
    if r.status_code == 200:
        parsed = r.json()["choices"][0]["message"]["content"]
        print("Qwen Canonical Extraction:")
        print(parsed[:600])

if __name__ == "__main__":
    run_fast_pipeline()
