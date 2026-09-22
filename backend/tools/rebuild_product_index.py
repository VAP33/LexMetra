#!/usr/bin/env python3
"""
Rebuild product_index.json from real dataset photos in 'images dataset/'.
Replaces synthetic single-item catalog with real embeddings for nearest-neighbor matching.
"""

from __future__ import annotations

import json
from pathlib import Path
import cv2

import sys
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import product_similarity
from product_similarity import ProductEmbedding

REPO_ROOT = _BACKEND_DIR.parent
PHOTOS_DIR = REPO_ROOT / "images dataset" if (REPO_ROOT / "images dataset").exists() else REPO_ROOT / "DEPENDENCIES" / "images dataset"
GT_FILE = REPO_ROOT / "dataset" / "real_photos_ground_truth.json"
INDEX_PATH = _BACKEND_DIR / "product_index.json"

def main():
    if not PHOTOS_DIR.exists():
        print(f"Error: Photos directory {PHOTOS_DIR} does not exist.")
        return

    # Load ground truth lookup if present
    gt_lookup = {}
    if GT_FILE.exists():
        try:
            with open(GT_FILE, "r", encoding="utf-8") as f:
                gt_data = json.load(f)
                for item in gt_data.get("images", []):
                    gt_lookup[item["file"]] = item
        except Exception as e:
            print(f"Warning loading ground truth: {e}")

    # Build known product mappings
    product_prefixes = {
        "22-06-12": ("BRU-INSTANT-COFFEE-150G", 420.0),
        "22-06-22": ("BRU-INSTANT-COFFEE-150G", 420.0),
        "22-06-31": ("BRU-INSTANT-COFFEE-150G", 420.0),
        "22-06-46": ("BRU-INSTANT-COFFEE-150G", 420.0),
        "22-06-55": ("BRU-INSTANT-COFFEE-150G", 420.0),
        "22-07-02": ("KELLOGGS-PRINGLES-PIZZA-102G", 110.0),
        "22-07-11": ("KELLOGGS-PRINGLES-PIZZA-102G", 110.0),
        "22-07-38": ("VASELINE-HEALTHY-BRIGHT-200ML", 260.0),
        "22-07-54": ("SW-999-SCREWDRIVER-SET", 199.0),
        "22-07-59": ("SW-999-SCREWDRIVER-SET", 199.0),
        "22-08-09": ("SW-999-SCREWDRIVER-SET", 199.0),
        "22-08-34": ("DETTOL-ORIGINAL-SOAP", 45.0),
        "22-08-57": ("DETTOL-ORIGINAL-SOAP", 45.0),
        "22-09-20": ("DORAEMON-CONFECTIONERY-BALL", 50.0),
        "22-09-33": ("DORAEMON-CONFECTIONERY-BALL", 50.0),
    }

    embeddings = []
    photo_files = sorted(PHOTOS_DIR.glob("*.jpg"))
    print(f"Found {len(photo_files)} photos in {PHOTOS_DIR}")

    for pf in photo_files:
        fn = pf.name
        img = cv2.imread(str(pf))
        if img is None:
            print(f"Skipping unreadable {fn}")
            continue

        gt_item = gt_lookup.get(fn)
        pid = None
        mrp = None

        if gt_item:
            product_title = gt_item.get("product", "")
            if "bru" in product_title.lower():
                pid = "8909106043251"  # GTIN-13 for Bru
                mrp = 420.0
            elif "pringles" in product_title.lower() or "kellogg" in product_title.lower():
                pid = "KELLOGGS-PRINGLES-102G"
                mrp = 110.0
            elif "vaseline" in product_title.lower():
                pid = "VASELINE-BRIGHT-200ML"
                mrp = 260.0
            elif "doraemon" in product_title.lower():
                pid = "7622202332241"
                mrp = 50.0
            elif "screwdriver" in product_title.lower():
                pid = "SW-999-SCREWDRIVER"
                mrp = 199.0

        if not pid:
            for stamp, (mapped_pid, mapped_mrp) in product_prefixes.items():
                if stamp in fn:
                    pid = mapped_pid
                    mrp = mapped_mrp
                    break

        if not pid:
            pid = f"PROD-RETAIL-{fn[:25]}"

        from dataclasses import asdict
        emb_obj = product_similarity.embed_image(
            img,
            product_id=pid,
            image_id=fn,
            mrp=mrp,
            scanned_at="2026-09-08T00:00:00Z"
        )
        embeddings.append(asdict(emb_obj))
        print(f"Indexed {fn} -> product_id={pid}, mrp={mrp}")

    # Write out to product_index.json
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(embeddings, f, indent=2)

    print(f"Successfully wrote {len(embeddings)} real product embeddings to {INDEX_PATH}")

if __name__ == "__main__":
    main()
