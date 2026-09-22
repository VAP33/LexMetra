"""
Dump the FIELD VALUES extraction returns for real dataset photographs.

WHY THIS EXISTS, AND WHY IT IS NOT bench_ocr.py.
`bench_ocr.py` reports character counts and field COUNTS. Counting fields is
actively misleading: on dataset image 3 the legacy whole-image path produced 5
fields and the region-first path 2, which reads like a 60% recall loss until you
print the values and find that legacy's extras were
`mrp = 'i Pr : 16.89 gMs (Incj Of al] taxes : 40/ f'` and
`batch_no = 'vy x | "hydrates 573.18 ams Batch No.: Ad7 ; |'`. Those are not
recall. A field count cannot tell a declaration from garbage, so this tool
prints what a reviewer would actually have to look at.

WHAT IT MAY AND MAY NOT BE USED FOR.
This is a DIAGNOSTIC, not a benchmark. There is no labelled ground truth in this
repository, so nothing here supports an accuracy claim; it supports "before this
change the value was X, after it is Y". Judging whether Y is correct still
requires a human reading the photograph.

Usage:
    python backend/tools/dump_fields.py --indices 0 3 7
    python backend/tools/dump_fields.py --indices 3 --path legacy
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "tools"))

_ROOT = _BACKEND.parent
_DATASET = _ROOT / "images dataset" if (_ROOT / "images dataset").exists() else _ROOT / "DEPENDENCIES" / "images dataset"


def _images() -> list[Path]:
    return sorted(
        p for p in _DATASET.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )


def _run(image_path: Path, region_first: bool) -> None:
    # config reads the flag at import time, so it must be set before the import.
    os.environ["LMPC_ENABLE_REGION_FIRST_OCR"] = "1" if region_first else "0"

    for mod in ("config", "ocr_extraction", "ocr_engine"):
        sys.modules.pop(mod, None)

    from PIL import Image

    import ocr_extraction as ox

    label = "region-first" if region_first else "legacy"
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        started = time.time()
        lines = ox.run_ocr(im)
        elapsed = time.time() - started

    fields = ox.classify_fields(lines)

    print(f"--- {label:12s} {image_path.name}")
    print(f"    {elapsed:6.1f}s  {len(lines):4d} lines  {len(fields):2d} fields")

    if not fields:
        print("    (no fields extracted)")
        return

    for name in sorted(fields):
        entry = fields[name]

        # Not every field is a dict: the address-style fields collect several
        # lines, so the shape varies. Print whatever is there rather than
        # assuming, since guessing the shape is how the earlier count-based
        # comparison went wrong in the first place.
        if not isinstance(entry, dict):
            print(f"      {name:22s} (non-dict {type(entry).__name__})")
            print(f"        {entry!r}")
            continue

        value = entry.get("value")
        conf = entry.get("confidence")
        numeric = entry.get("numeric_value")
        extra = f"  numeric={numeric!r}" if numeric is not None else ""
        conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "?"
        print(f"      {name:22s} conf={conf_s}{extra}")
        print(f"        {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--indices", type=int, nargs="+", required=True)
    parser.add_argument(
        "--path",
        choices=["legacy", "region-first", "both"],
        default="both",
    )
    args = parser.parse_args()

    images = _images()
    if not images:
        print(f"no images found in {_DATASET}", file=sys.stderr)
        return 1

    for idx in args.indices:
        if not 0 <= idx < len(images):
            print(f"index {idx} out of range (0..{len(images) - 1})")
            continue
        if args.path in {"legacy", "both"}:
            _run(images[idx], region_first=False)
        if args.path in {"region-first", "both"}:
            _run(images[idx], region_first=True)

    print(
        "\nDIAGNOSTIC ONLY. No labelled ground truth exists in this repo, so "
        "these values support before/after comparison, not an accuracy claim."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
