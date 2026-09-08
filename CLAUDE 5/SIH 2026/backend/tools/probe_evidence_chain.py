"""
Prove that a legal finding can be traced back to its source image and region.

WHY THIS EXISTS.
The evidence contract had every piece in place except the join. OCR produced
bboxes in original-image coordinates, `schema.py` had `ExtractedFact.bbox`,
`ExtractedFact.evidence` and `EvidenceReference`, and the database had an
`evidence_json` column — but `main._field_to_raw_extraction` never passed `bbox`
or `evidence`, so `RawExtraction.bbox` was None for every field in the live
pipeline and `rule_engine._evidence_for_extraction` returned an empty list.
Every finding the API produced was therefore untraceable to any image region.

A unit test can assert the fixed behaviour, but it cannot show the SHAPE of what
a reviewer receives. This probe walks the real chain a request walks —
classified OCR fields -> provenance stamp -> RawExtraction -> run_inspection ->
facts and findings — and prints, per fact, whether a reviewer could actually be
shown the evidence.

Run:
    python backend/tools/probe_evidence_chain.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
for _p in (str(_BACKEND), str(_BACKEND / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import pydantic  # noqa: F401
except ModuleNotFoundError:
    import pydantic_shim

    pydantic_shim.install()

import capture_session  # noqa: E402
import rule_engine  # noqa: E402
from schema import UNATTRIBUTED_IMAGE_ID  # noqa: E402


# Shaped exactly like `ocr_extraction.classify_fields()` output: bbox is the
# (x, y, w, h) tuple `OcrLine` carries, already in ORIGINAL image coordinates.
CLASSIFIED = {
    "mrp": {
        "value": "MRP Rs 50.00 (incl. of all taxes)",
        "confidence": 0.91,
        "bbox": (120, 640, 300, 28),
        "numeric_value": 50.0,
    },
    "net_quantity": {
        "value": "Net Wt 100 g",
        "confidence": 0.88,
        "bbox": (118, 600, 210, 26),
        "numeric_value": 100.0,
        "numeric_unit": "g",
    },
    "manufacturer_name": {
        "value": "Acme Foods Pvt Ltd, Pune 411001",
        "confidence": 0.84,
        "bbox": (115, 700, 420, 52),
    },
    "mfg_date": {
        "value": "Mfg 04/2026",
        "confidence": 0.79,
        "bbox": (118, 560, 190, 24),
    },
    # Extractor diagnostic, not a declaration: a list, not a dict. The stamp
    # must pass it through untouched rather than assuming a shape.
    "_auxiliary_dates": ["04/2026", "18/08/2026"],
}


def _run(stamped: bool) -> None:
    classified = dict(CLASSIFIED)
    label = "WITH provenance stamp" if stamped else "WITHOUT provenance stamp"

    if stamped:
        classified = capture_session.stamp_provenance(
            classified, image_id="front_panel_7f3a.jpg", surface_id="surf-abc123"
        )

    bridged = capture_session.bridge_classified_fields(classified)
    extractions = {
        field: capture_session.build_raw_extraction(field, data)
        for field, data in bridged.items()
    }

    inspection = rule_engine.run_inspection(
        inspection_id="probe-001",
        product_category="food",
        sale_type="retail",
        net_quantity_value=100.0,
        net_quantity_unit="g",
        mrp=50.0,
        extractions=extractions,
    )

    locatable = 0
    unattributed = 0
    no_evidence = 0

    print(f"--- {label}")
    for fact in inspection.facts:
        refs = fact.evidence or []
        if not refs:
            no_evidence += 1
            print(f"    {fact.field:34s} {fact.status.value:9s} NO EVIDENCE")
            continue

        for ref in refs:
            if ref.image_id == UNATTRIBUTED_IMAGE_ID:
                unattributed += 1
                print(
                    f"    {fact.field:34s} {fact.status.value:9s} "
                    f"UNATTRIBUTED bbox={_bbox(ref)}"
                )
            elif ref.is_locatable():
                locatable += 1
                print(
                    f"    {fact.field:34s} {fact.status.value:9s} "
                    f"image={ref.image_id} surface={ref.surface_id} "
                    f"bbox={_bbox(ref)}"
                )
            else:
                print(
                    f"    {fact.field:34s} {fact.status.value:9s} "
                    f"image={ref.image_id} NO REGION"
                )

    total = len(inspection.facts)
    print(
        f"    => {total} facts: {locatable} locatable, "
        f"{unattributed} unattributed, {no_evidence} with no evidence at all"
    )
    print()


def _bbox(ref) -> str:
    if ref.bbox is None:
        return "None"
    b = ref.bbox
    return f"({b.x:.0f},{b.y:.0f},{b.width:.0f},{b.height:.0f})"


def main() -> int:
    _run(stamped=False)
    _run(stamped=True)
    print(
        "A fact is only reviewable when it names BOTH a source image and a "
        "region within it. 'Locatable' counts those; anything else is a break "
        "in the traceability chain."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
