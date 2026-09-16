import os
import sys
import asyncio
from pathlib import Path
import cv2
import json

backend_dir = Path(r"c:\Users\HP\SIH LATEST\backend")
sys.path.insert(0, str(backend_dir))

import qwen_perception
from geometry import CoordinateSpace, CoordinateTransform

async def test_qwen():
    img_path = r"c:\Users\HP\SIH LATEST\images new\TRAYA BACK.jpg"
    if not os.path.exists(img_path):
        print(f"File not found: {img_path}")
        return

    bgr = cv2.imread(img_path)
    h, w = bgr.shape[:2]
    print(f"Loaded image: {w}x{h}")

    transform = CoordinateTransform(
        source_space=CoordinateSpace.CANONICAL_PIXEL,
        target_space=CoordinateSpace.ORIGINAL_PIXEL,
        matrix=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        source_dims=(w, h),
        target_dims=(w, h),
    )

    provider = qwen_perception.get_qwen_provider()
    print(f"Provider: {type(provider).__name__}")
    print(f"Provider available: {provider.is_available()}")

    faces = [("Face 1", bgr, transform)]
    res = await provider.perceive(faces)

    print("\n--- PERCEPTION RESULT ---")
    print(f"Provider used: {res.provider_name}")
    print(f"Used fallback: {res.used_fallback}")
    print(f"Product name: {res.product_name}")
    print(f"Declarations ({len(res.declarations)}):")
    for d in res.declarations:
        print(f"  Field: {d.field:20s} Value: '{d.value}' Status: {d.status} Face: {d.face}")

    classified = qwen_perception.perception_to_classified_fields(res)
    print("\n--- CLASSIFIED FIELDS ---")
    print(json.dumps(classified, indent=2, default=str))

if __name__ == "__main__":
    asyncio.run(test_qwen())
