#!/usr/bin/env python3
"""
Real-photograph OCR benchmark for the `images dataset` folder.

WHY THIS EXISTS
---------------
Every speed or accuracy change to the region-first OCR path has to be justified
by measurement on ACTUAL dataset photographs, not on synthetic images. Synthetic
text is uniformly lit, axis-aligned and noise-free, so it hides exactly the
failures this pipeline exists to handle. This harness is the canonical way to
produce those numbers so that two runs are comparable.

WHAT IT REPORTS, AND WHAT THE NUMBERS DO NOT MEAN
-------------------------------------------------
Reported per image: wall-clock seconds, OCR calls issued, regions detected /
read / de-duplicated / unread, usable observations, withheld observations, and
total usable characters.

`usable_chars` is a PROXY for recall, not an accuracy score. It counts characters
that survived the plausibility gates; it cannot tell a correct reading from a
confident misreading. It is used here only to detect REGRESSIONS — if a change
makes the pipeline faster but drops 40% of the characters, the change is not an
optimisation. Establishing true accuracy needs a labelled ground-truth set, which
this harness does not have and does not pretend to have.

Nothing here produces or influences a legal finding. Unread regions are
NOT_OBSERVED; that is a coverage statement about the photograph, never evidence
that a declaration is absent.

USAGE
-----
    python backend/tools/bench_ocr.py                 # first 5 images
    python backend/tools/bench_ocr.py --indices 0 3 7
    python backend/tools/bench_ocr.py --limit 10 --json out.json
    python backend/tools/bench_ocr.py --indices 3 --text   # dump what was read
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import cv2  # noqa: E402

import ocr_engine  # noqa: E402

_ROOT = _BACKEND.parent
DEFAULT_DATASET = _ROOT / "images dataset" if (_ROOT / "images dataset").exists() else _ROOT / "DEPENDENCIES" / "images dataset"


def dataset_images(folder: Path) -> List[Path]:
    """Return dataset photographs in stable filename order."""
    if not folder.is_dir():
        raise SystemExit(f"Dataset folder not found: {folder}")
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in exts)
    if not files:
        raise SystemExit(f"No images found in {folder}")
    return files


def bench_one(path: Path, *, dump_text: bool = False) -> Dict[str, object]:
    """Read one photograph and summarise the run."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return {"file": path.name, "error": "unreadable image"}

    reading = ocr_engine.read_image(image)

    usable = [o for o in reading.observations if o.usable_for_extraction]
    withheld = [o for o in reading.observations if not o.usable_for_extraction]

    detected = len(reading.detection.text_regions())
    # Recover the routing split from the notes the reader emitted, so the harness
    # reports what the pipeline actually did rather than recomputing it.
    unread = _note_count(reading.engine_notes, "but not read")
    calls = _note_count(reading.engine_notes, "OCR call(s) issued")

    row: Dict[str, object] = {
        "file": path.name,
        "shape": f"{image.shape[1]}x{image.shape[0]}",
        "seconds": round(float(reading.elapsed_seconds), 2),
        "ocr_calls": calls,
        "regions_detected": detected,
        "regions_read": detected - unread,
        "regions_unread": unread,
        "usable_observations": len(usable),
        "withheld_observations": len(withheld),
        "usable_chars": sum(len(o.text.strip()) for o in usable),
        "conflicts": len(reading.conflicts),
    }
    if dump_text:
        row["usable_text"] = [
            {"text": o.text.strip(), "conf": round(float(o.confidence), 2)}
            for o in usable
        ]
        row["withheld_text"] = [o.text.strip() for o in withheld]
    return row


def _note_count(notes, needle: str) -> int:
    """Pull the leading integer out of the first note containing `needle`."""
    for note in notes:
        if needle in note:
            head = note.split(None, 1)[0]
            if head.isdigit():
                return int(head)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--indices", type=int, nargs="*", help="0-based indices into the sorted list"
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", type=Path, help="write the full result set here")
    parser.add_argument(
        "--text", action="store_true", help="include the text that was read"
    )
    args = parser.parse_args(argv)

    files = dataset_images(args.dataset)
    if args.indices:
        chosen = [files[i] for i in args.indices if 0 <= i < len(files)]
    else:
        chosen = files[: max(1, args.limit)]

    header = (
        f"{'idx':>3}  {'seconds':>7}  {'calls':>5}  {'det':>4}  {'read':>4}  "
        f"{'unread':>6}  {'usable':>6}  {'held':>4}  {'confl':>5}  {'chars':>6}  file"
    )
    print(header)
    print("-" * len(header))

    rows: List[Dict[str, object]] = []
    for path in chosen:
        idx = files.index(path)
        row = bench_one(path, dump_text=args.text)
        row["index"] = idx
        rows.append(row)
        if "error" in row:
            print(f"{idx:>3}  ERROR: {row['error']}  {row['file']}")
            continue
        print(
            f"{idx:>3}  {row['seconds']:>7}  {row['ocr_calls']:>5}  "
            f"{row['regions_detected']:>4}  {row['regions_read']:>4}  "
            f"{row['regions_unread']:>6}  "
            f"{row['usable_observations']:>6}  {row['withheld_observations']:>4}  "
            f"{row['conflicts']:>5}  "
            f"{row['usable_chars']:>6}  {row['file'][:34]}"
        )

    ok = [r for r in rows if "error" not in r]
    if ok:
        total_s = sum(float(r["seconds"]) for r in ok)
        total_c = sum(int(r["usable_chars"]) for r in ok)
        print("-" * len(header))
        print(
            f"TOTAL {total_s:.1f}s over {len(ok)} image(s); "
            f"mean {total_s / len(ok):.1f}s; {total_c} usable chars. "
            "usable_chars is a recall PROXY, not an accuracy measure."
        )

    if args.json:
        args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"Wrote {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
