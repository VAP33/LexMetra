"""
Auto-annotate new packaging images and update dataset annotations.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from paddle_ocr_service import get_paddle_ocr
from ocr_extraction import classify_fields


def main():
    dataset_dir = PROJECT_ROOT / "dataset"
    images_src_dir = dataset_dir / "images dataset"
    images_dst_dir = dataset_dir / "images"
    annotations_file = dataset_dir / "annotations" / "annotations.json"

    images_dst_dir.mkdir(parents=True, exist_ok=True)
    ocr = get_paddle_ocr()

    with open(annotations_file, "r", encoding="utf-8") as f:
        ann_data = json.load(f)

    existing_img_ids = {img["image_id"] for img in ann_data.get("images", [])}
    new_files = list(images_src_dir.glob("*.jpg")) + list(images_src_dir.glob("*.png"))
    print(f"Found {len(new_files)} new images in '{images_src_dir.name}'.", flush=True)

    splits = ["train", "train", "train", "val", "test"]
    split_idx = 0

    for idx, fpath in enumerate(new_files):
        dst_path = images_dst_dir / fpath.name
        if not dst_path.exists():
            shutil.copy2(fpath, dst_path)

        if fpath.name in existing_img_ids:
            print(f"Skipping already annotated: {fpath.name}", flush=True)
            continue

        with Image.open(dst_path) as pil_im:
            pil_rgb = pil_im.convert("RGB")
            img_w, img_h = pil_rgb.size
            img_np = np.array(pil_rgb)
            ocr_readings = ocr.read_text(img_np)

        ocr_lines = [r.to_ocr_line() for r in ocr_readings]
        classified = classify_fields(ocr_lines)

        fields_list = []
        for field_name, item in classified.items():
            if field_name.startswith("_") or not isinstance(item, dict):
                continue
            bbox = item.get("bbox")
            val = item.get("value")
            if bbox and len(bbox) == 4 and val:
                # Convert x, y, w, h to x1, y1, x2, y2
                bx, by, bw, bh = bbox
                fields_list.append({
                    "field": field_name,
                    "value": str(val),
                    "bbox": [int(bx), int(by), int(bx + bw), int(by + bh)]
                })

        # Add general declaration panel bbox
        if ocr_lines:
            all_x1s = [line.bbox[0] for line in ocr_lines]
            all_y1s = [line.bbox[1] for line in ocr_lines]
            all_x2s = [line.bbox[0] + line.bbox[2] for line in ocr_lines]
            all_y2s = [line.bbox[1] + line.bbox[3] for line in ocr_lines]
            if all_x1s and all_y1s:
                fields_list.append({
                    "field": "declaration_panel",
                    "value": "Text Panel",
                    "bbox": [
                        max(0, int(min(all_x1s))),
                        max(0, int(min(all_y1s))),
                        min(img_w, int(max(all_x2s))),
                        min(img_h, int(max(all_y2s)))
                    ]
                })

        assigned_split = splits[split_idx % len(splits)]
        split_idx += 1

        ann_data["images"].append({
            "image_id": fpath.name,
            "product_id": f"REAL-{idx+1:03d}",
            "synthetic": False,
            "category": "packaged_commodity",
            "expected_overall_status": "PASS" if any(f["field"] == "mrp" for f in fields_list) else "UNCERTAIN",
            "fields": fields_list,
            "split": assigned_split
        })
        print(f"[{idx+1}/{len(new_files)}] Annotated {fpath.name}: {len(fields_list)} fields extracted (Split: {assigned_split})", flush=True)

    ann_data["_meta"]["total_images"] = len(ann_data["images"])
    with open(annotations_file, "w", encoding="utf-8") as f:
        json.dump(ann_data, f, indent=2)

    print(f"Successfully updated annotations.json! Total images in dataset: {len(ann_data['images'])}", flush=True)


if __name__ == "__main__":
    main()
