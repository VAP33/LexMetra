"""Canonical on-disk dataset locations for LexMetra.

ARCH-01 / TEST-01 recorded that older tools still look for
``images dataset/`` or ``DEPENDENCIES/images dataset``. Those paths are
dead. Real data lives under ``dataset/``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNTHETIC_IMAGES = REPO_ROOT / "dataset" / "images dataset"
REAL_IMAGES = REPO_ROOT / "dataset" / "real images"
LEGACY_GENERATED_IMAGES = REPO_ROOT / "dataset" / "images"  # generate_dataset.py default
ANNOTATIONS = REPO_ROOT / "dataset" / "annotations" / "annotations.json"


def existing_image_dirs() -> List[Path]:
    dirs: List[Path] = []
    for path in (SYNTHETIC_IMAGES, REAL_IMAGES, LEGACY_GENERATED_IMAGES):
        if path.is_dir():
            dirs.append(path)
    return dirs


def first_existing(*candidates: Path) -> Optional[Path]:
    for path in candidates:
        if path.exists():
            return path
    return None


def find_named_image(filename: str) -> Optional[Path]:
    for directory in existing_image_dirs():
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def list_images(directories: Optional[Iterable[Path]] = None) -> List[Path]:
    roots = list(directories) if directories is not None else existing_image_dirs()
    found: List[Path] = []
    for directory in roots:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                found.append(path)
    return found


def dataset_inventory() -> dict:
    synthetic = list_images([SYNTHETIC_IMAGES, LEGACY_GENERATED_IMAGES])
    real = list_images([REAL_IMAGES])
    ann_count = 0
    synthetic_flag = None
    if ANNOTATIONS.is_file():
        import json

        data = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
        images = data.get("images") or []
        ann_count = len(images)
        synthetic_flag = bool((data.get("_meta") or {}).get("synthetic"))
    return {
        "synthetic_image_files": len(synthetic),
        "real_image_files": len(real),
        "annotation_records": ann_count,
        "annotations_marked_synthetic": synthetic_flag,
        "synthetic_dir": str(SYNTHETIC_IMAGES),
        "real_dir": str(REAL_IMAGES),
    }
