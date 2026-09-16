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

async def test_keys():
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

    keys = [
        ("OPENROUTER_API_KEY2", os.getenv("OPENROUTER_API_KEY2")),
        ("GROQ_API_KEY (as OR)", os.getenv("GROQ_API_KEY")),
    ]

    for name, key in keys:
        print(f"\n--- Testing key {name}: {key[:15]}... ---")
        provider = qwen_perception.OpenRouterQwenProvider(api_key=key)
        # test with max_tokens=800
        payload = batch.make_payload(provider.model_name)
        payload["max_tokens"] = 800
        payload["reasoning"] = {"effort": "none"}

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://lexmetra.internal",
            "X-Title": "LexMetra-V1-Perception",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(provider.endpoint, json=payload, headers=headers)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                print("SUCCESS! Content:")
                print(content[:500])
                try:
                    with open(r"c:\Users\HP\SIH LATEST\backend\traya_qwen_raw.json", "w", encoding="utf-8") as f:
                        f.write(content)
                    print("Saved to traya_qwen_raw.json")
                except Exception as e:
                    print("Save err:", e)
                break
            else:
                print(f"Error: {resp.text[:300]}")

if __name__ == "__main__":
    asyncio.run(test_keys())
