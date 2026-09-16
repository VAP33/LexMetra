"""
Prepare YOLO Dataset for Legal Metrology Packaged Commodities.

Converts `dataset/annotations/annotations.json` and images in `dataset/images/`
into the standard Ultralytics YOLO dataset structure:

    dataset/yolo/
      data.yaml
      images/
        train/
        val/
        test/
      labels/
        train/
        val/
        test/

Each label file contains rows:
    <class_id> <x_center> <y_center> <width> <height>
all normalized in [0.0, 1.0].
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "dataset"
ANNOTATIONS_FILE = DATASET_DIR / "annotations" / "annotations.json"
IMAGES_DIR = DATASET_DIR / "images"
YOLO_DIR = DATASET_DIR / "yolo"

# Canonical Legal Metrology class vocabulary
CLASSES: List[str] = [
    "mrp",
    "net_quantity",
    "mfg_date",
    "manufacturer",
    "consumer_care",
    "unit_price",
    "common_name",
    "expiry_date",
    "country_of_origin",
    "barcode_qr",
    "declaration_panel",
]

CLASS_TO_ID: Dict[str, int] = {name: i for i, name in enumerate(CLASSES)}


def normalize_field_name(field: str) -> str:
    """Map annotation field names to canonical class labels."""
    f = field.strip().lower().replace(" ", "_")
    mapping = {
        "mrp": "mrp",
        "maximum_retail_price": "mrp",
        "net_quantity": "net_quantity",
        "net_qty": "net_quantity",
        "mfg_date": "mfg_date",
        "date_of_manufacture": "mfg_date",
        "manufacturer": "manufacturer",
        "packer": "manufacturer",
        "importer": "manufacturer",
        "consumer_care": "consumer_care",
        "customer_care": "consumer_care",
        "unit_price": "unit_price",
        "unit_sale_price": "unit_price",
        "common_name": "common_name",
        "generic_name": "common_name",
        "expiry_date": "expiry_date",
        "best_before": "expiry_date",
        "use_by": "expiry_date",
        "country_of_origin": "country_of_origin",
        "barcode": "barcode_qr",
        "qr": "barcode_qr",
        "declaration_panel": "declaration_panel",
    }
    return mapping.get(f, "declaration_panel")


def convert_bbox_to_yolo(
    bbox: Sequence[float], img_w: int, img_h: int
) -> Tuple[float, float, float, float]:
    """
    Convert [x1, y1, x2, y2] to YOLO [x_center, y_center, width, height] normalized.
    Clamps values to [0.0, 1.0].
    """
    x1, y1, x2, y2 = bbox
    # Ensure proper ordering
    xmin = max(0.0, min(float(x1), float(x2)))
    xmax = min(float(img_w), max(float(x1), float(x2)))
    ymin = max(0.0, min(float(y1), float(y2)))
    ymax = min(float(img_h), max(float(y1), float(y2)))

    box_w = max(1.0, xmax - xmin)
    box_h = max(1.0, ymax - ymin)
    x_center = xmin + (box_w / 2.0)
    y_center = ymin + (box_h / 2.0)

    # Normalize
    x_norm = max(0.0, min(1.0, x_center / float(img_w)))
    y_norm = max(0.0, min(1.0, y_center / float(img_h)))
    w_norm = max(0.0, min(1.0, box_w / float(img_w)))
    h_norm = max(0.0, min(1.0, box_h / float(img_h)))

    return x_norm, y_norm, w_norm, h_norm


def build_yolo_dataset(output_dir: Path = YOLO_DIR) -> Dict[str, int]:
    """Reads annotations.json and builds YOLO train/val/test structure."""
    if not ANNOTATIONS_FILE.exists():
        raise FileNotFoundError(f"Annotations file not found: {ANNOTATIONS_FILE}")

    with open(ANNOTATIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    images_meta = data.get("images", [])
    if not images_meta:
        raise ValueError("No images found in annotations.json")

    # Prepare directories
    for split in ["train", "val", "test"]:
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = {"train": 0, "val": 0, "test": 0, "total_boxes": 0}

    for idx, item in enumerate(images_meta):
        image_id = item["image_id"]
        split = item.get("split", "train")
        if split not in stats:
            split = "train"

        src_img_path = IMAGES_DIR / image_id
        if not src_img_path.exists():
            continue

        # Target paths
        dst_img_path = output_dir / "images" / split / image_id
        dst_lbl_path = output_dir / "labels" / split / f"{src_img_path.stem}.txt"

        # Copy image
        shutil.copy2(src_img_path, dst_img_path)

        # Get image dimensions
        with Image.open(src_img_path) as im:
            img_w, img_h = im.size

        # Build labels
        label_lines: List[str] = []
        fields = item.get("fields", [])
        for fld in fields:
            bbox = fld.get("bbox")
            if not bbox or len(bbox) != 4:
                continue

            raw_field = fld.get("field", "")
            canonical = normalize_field_name(raw_field)
            class_id = CLASS_TO_ID.get(canonical, CLASS_TO_ID["declaration_panel"])

            xc, yc, nw, nh = convert_bbox_to_yolo(bbox, img_w, img_h)
            label_lines.append(f"{class_id} {xc:.6f} {yc:.6f} {nw:.6f} {nh:.6f}")
            stats["total_boxes"] += 1

        with open(dst_lbl_path, "w", encoding="utf-8") as lf:
            lf.write("\n".join(label_lines) + "\n")

        stats[split] += 1

    # Write data.yaml for Ultralytics
    yaml_content = f"""# Ultralytics YOLO dataset configuration for Legal Metrology Packaged Commodities
path: {output_dir.resolve().as_posix()}
train: images/train
val: images/val
test: images/test

names:
"""
    for i, cname in enumerate(CLASSES):
        yaml_content += f"  {i}: {cname}\n"

    yaml_path = output_dir / "data.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")

    print(f"YOLO dataset built at: {output_dir}")
    print(f"Stats: {stats}")
    print(f"Data YAML: {yaml_path}")
    return stats


if __name__ == "__main__":
    build_yolo_dataset()
