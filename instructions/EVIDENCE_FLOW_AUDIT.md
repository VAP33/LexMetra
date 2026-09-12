# EVIDENCE FLOW AUDIT: END-TO-END TRACEABILITY REPORT

## 1. Traceability Chain Verification

The audit confirms that evidence flows unbroken from physical image pixels through to API responses, database persistence, and PDF report generation.

```
RAW PIXELS ──> PREPROCESSING ──> ORIENTATION ──> OCR DET/REC ──> EXTRACTION ──> PROVENANCE STAMP ──> RULE ENGINE ──> REPORT
```

### Traceability Invariants Verified:

1. **Pixel Coordinates Retained**:
   - `run_ocr()` returns bounding boxes in original image coordinates `(x, y, w, h)`.
   - Bounding boxes are retained through `classify_fields()` and stamped with `image_id` and `surface_id` via `capture_session.stamp_provenance()`.
   - `RawExtraction.bbox` receives `BBox(x, y, width, height)`.
   - `ProductInspection.facts[i].bbox` and `findings[i].evidence[0].bbox` reflect original pixel boundaries.

2. **Cross-Surface Merging & Provenance Attribution**:
   - Observations from Panel 1 (Front) and Panel 2 (Back) are merged using `capture_session.merge_classified_fields()`.
   - Higher-confidence readings win during conflicts, but crucially retain their original source `image_id`.
   - Winning MRP is attributed to `Screenshot_...22-06-12-38.jpg`.
   - Winning Net Quantity is attributed to `Screenshot_...22-06-22-17.jpg`.

3. **Split-Field Reconstruction Provenance**:
   - When a label-only observation on Surface A (e.g. `NET WEIGHT:`) is completed by a bare numeric fragment on Surface B (e.g. `150 g`), `capture_session.reconstruct_split_fields()`:
     - Sets `source_images = [image_a, image_b]`.
     - Sets `spatial_relationship = "cross_image_continuation"`.
     - Sets `verification = "UNCERTAIN"` and `review_required = True`.
     - Records explicit explanatory reason in `reason` attribute.
     - Never silently replaces an existing verified field.

4. **Fabricated Quantity Guard**:
   - Verified that `_resolve_quantity()` in `backend/main.py` does NOT fall back to `1.0 unit`.
   - When net quantity is absent from OCR evidence, `qty_val` is `None`, `qty_unit` is `None`, and `quantity_source` is `"not_observed"`.
   - The Rule Engine returns `FactStatus.UNCERTAIN` under Rule 6(1)(ii) for unobserved quantity.

5. **Database Evidence Serialization**:
   - `db.save_inspection()` serializes `evidence_json` including all bounding boxes, image references, and alternative conflict readings.
   - `db.get_inspection_detail()` restores full evidence objects for review.

6. **PDF Report Rendering**:
   - `build_inspection_report_pdf()` reads exact coordinates and prints:
     `{image_id} @ ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f}px`.
   - When evidence is unobserved, the report explicitly states: `"no evidence recorded"`, rather than manufacturing an imaginary region.
   - Grounded legal standards table renders grounded rule IDs, versions, and official citations.
