# GEOMETRY_MODULE_NOTES.md
## Package geometry / PDP detection / calibration / physical measurement subsystem

Delivered by the geometry/PDP/calibration/measurement specialist track. This
document is the handoff record for Claude 3 (principal integrator).

---

## 1. What this adds

Before this change, the repository had:
- `image_quality.estimate_pdp_bbox()` — an **informational** PDP bbox guess
  from OCR text clustering, explicitly documented as never feeding a
  calibrated measurement.
- `rule_engine._evaluate_font_height()` — a Rule 7(2) evaluator that already
  expects a *calibrated* `pdp_area_cm2` and a `measured_height_mm` +
  `measurement_mode`, but nothing in the repo produced either automatically;
  `pdp_area_cm2` was a manually-typed inspector field (`main.py`).

This change adds the missing middle: a real, tested pixel→physical-unit
pipeline, entirely as new, additive modules and schema fields. **No existing
file's behavior was changed** except `schema.py`, which only gained new
optional fields/enum members/models (see below).

```
IMAGE
 -> detect_package_geometry()          (geometry.py)   package boundary, NOT the PDP
 -> detect_pdp_geometry()               (geometry.py)   PDP candidate, distinct from package boundary
 -> rectify_pdp()                       (geometry.py)   perspective correction for planar PDPs
 -> calibrate_from_*()                  (calibration.py) explicit calibration evidence
 -> measure_bbox() / measure_pdp_area() (calibration.py) pixels -> mm/cm2 + uncertainty
 -> map_region_coordinates()            (geometry.py)   OCR-region <-> rectified <-> original coordinate mapping
 -> lightweight_geometry_check()        (geometry.py)   live-capture-friendly readiness signal
```

---

## 2. FILES CREATED

- `backend/geometry.py` — package boundary detection, shape classification
  (classical CV: contours, `approxPolyDP`, ellipse fitting, solidity),
  PDP candidate detection, perspective validation/rectification, coordinate
  mapping (pixel/normalized/rectified), lightweight live-capture readiness
  checks, multi-image overlap recommendation, ORB+RANSAC multi-image
  alignment.
- `backend/calibration.py` — calibration evidence construction (reference
  object, known package dimension, user-entered reference, depth sensor),
  pixel→mm measurement with propagated uncertainty, and PDP-area computation
  that mirrors the Rule 7(1) shape formula already encoded in
  `rules/rules.json` (`LMPC-2011-R7-PDP-AREA`).
- `backend/tests/test_geometry.py` — 23 tests on synthetic images (see §7).
- `backend/tests/test_calibration.py` — 19 tests, including a regression
  guard that fails if `calibration.PDP_AREA_CYLINDRICAL_FACTOR` and
  `rules.json`'s cylindrical PDP-area factor (0.40) ever diverge.
- `GEOMETRY_MODULE_NOTES.md` — this file.

## 3. FILES MODIFIED

- `backend/schema.py` — **additive only**:
  - `MeasurementMode` gained one new member, `NOT_OBSERVED` (existing
    `!= MeasurementMode.VERIFIED` comparisons in `rule_engine.py` are
    unaffected).
  - New enums: `PackageShapeHint`, `CalibrationMethod`,
    `PDPObservationStatus`, `GeometryReadiness`.
  - `CalibrationInfo` gained new *optional* fields (`method`, `source_image`,
    `scale_uncertainty_relative`, `confidence`); all default to `None`, so
    every existing construction of `CalibrationInfo` in the codebase still
    works unchanged.
  - New models: `PackageGeometry`, `PDPGeometry`, `RectificationResult`,
    `PhysicalMeasurement`, `GeometryReadinessResult`.
  - Nothing pre-existing in `schema.py` was renamed, removed, or had its
    validation tightened.

No other file (`main.py`, `rule_engine.py`, `capture_session.py`,
`image_quality.py`, `ocr_extraction.py`, `sticker_detection.py`,
`unit_price.py`, `exemption.py`, `auth.py`, frontend, rules.json) was
touched.

## 4. APIs ADDED

`geometry.py`:
- `detect_package_geometry(img_bgr, source_image, image_quality=None) -> PackageGeometry`
- `classify_package_shape(contour, image_shape) -> (GeometryType, PackageShapeHint, confidence, notes)`
- `detect_pdp_geometry(img_bgr, source_image, package_geometry=None, ocr_boxes=None, image_quality=None) -> PDPGeometry`
- `validate_quadrilateral(polygon) -> (ok, notes)`
- `rectify_pdp(img_bgr, source_image, polygon, output_width=None, output_height=None) -> (rectified_image_or_None, RectificationResult_or_None)`
- `map_point_through_homography(x, y, homography, invert=False) -> (x, y)`
- `map_region_coordinates(bbox, homography, invert=False) -> BBox`
- `normalize_bbox(bbox, image_width, image_height) -> BBox`
- `denormalize_bbox(bbox, image_width, image_height) -> BBox`
- `lightweight_geometry_check(img_bgr, image_quality=None, calibration_available=False) -> GeometryReadinessResult`
- `bbox_overlap_fraction(a, b) -> float`
- `overlap_recommendation(overlap_fraction) -> str`
- `align_multi_image_surfaces(img_a_bgr, img_b_bgr, ...) -> homography_or_None`

`calibration.py`:
- `calibrate_from_reference_object(reference_pixel_length, reference_dimension_mm, source_image, ...) -> CalibrationInfo`
- `calibrate_from_known_package_dimension(known_pixel_length, known_dimension_mm, source_image, dimension_source_note, ...) -> CalibrationInfo`
- `calibrate_from_user_reference(reference_pixel_length, reference_dimension_mm, source_image, ...) -> CalibrationInfo`
- `calibrate_from_depth(pixels_per_mm, depth_confidence, source_image) -> CalibrationInfo`
- `estimate_measurement_uncertainty(pixel_length, calibration, pixel_localization_uncertainty_px=1.5) -> float | None`
- `measure_length_px(pixel_length, calibration, quantity, source_image=None, source_region=None) -> PhysicalMeasurement`
- `measure_bbox(bbox, calibration, source_image=None) -> [PhysicalMeasurement, PhysicalMeasurement]` (width, height)
- `measure_pdp_area(pdp, shape, calibration, circumference_bbox=None) -> PhysicalMeasurement`

## 5. SCHEMAS ADDED

See §3. Summary table:

| Model | Purpose |
|---|---|
| `PackageGeometry` | Package-boundary evidence (bbox/polygon/shape/confidence) for one image |
| `PDPGeometry` | PDP-candidate evidence, explicitly distinct from `PackageGeometry` |
| `RectificationResult` | Homography + source polygon provenance for a rectified PDP image |
| `PhysicalMeasurement` | One pixel->physical-unit measurement with uncertainty + status |
| `GeometryReadinessResult` | Live-capture geometry signal (never a compliance signal) |

## 6. TESTS ADDED

`backend/tests/test_geometry.py` (23 tests) and
`backend/tests/test_calibration.py` (19 tests) = **42 new tests, all
passing**, covering every item in the brief's test list:

1. Rectangular box — `test_rectangular_box_detected_as_flat`
2. Perspective-distorted box — `test_perspective_box_still_detected_with_reasonable_bbox`, `test_rectify_pdp_produces_valid_homography_for_reasonable_quad`
3. Cylindrical package — `test_cylindrical_package_classified_as_cylindrical_or_near`
4. Partial package — `test_partial_package_flagged_as_touching_border`, `test_lightweight_check_partially_out_of_frame`
5. Cluttered background — `test_cluttered_background_still_finds_largest_contour`
6. Calibration reference — `test_calibrate_from_reference_object_computes_pixels_per_mm`
7. Known physical scale — `test_calibrate_from_known_package_dimension_is_unvalidated`
8. Pixel -> mm conversion — `test_measure_length_px_converts_correctly`, `test_measure_bbox_returns_width_and_height`
9. Measurement uncertainty — `test_uncertainty_increases_as_pixel_length_shrinks`, `test_verified_measurement_carries_lower_relative_uncertainty_than_estimated`
10. PDP != package boundary — `test_pdp_not_confused_with_package_boundary_when_ocr_available`, `test_pdp_falls_back_to_package_boundary_with_low_confidence_when_no_ocr`
11. OCR region coordinate mapping — `test_map_region_coordinates_round_trips_through_homography`, `test_normalize_and_denormalize_bbox_round_trip`
12. Multi-image geometry — `test_align_multi_image_surfaces_aligns_shifted_textured_image`, `test_bbox_overlap_fraction_basic`
13. Insufficient calibration -> UNCERTAIN — `test_pdp_area_uncertain_without_calibration`, `test_measure_length_px_without_calibration_is_uncertain`
14. Extreme perspective -> UNCERTAIN-equivalent — `test_lightweight_check_flags_extreme_perspective_as_too_oblique`
15. Glare-obscured geometry -> confidence reduction — `test_glare_reduces_geometry_confidence`, `test_invalid_image_quality_forces_zero_confidence`

Plus additional regression tests: empty-scene handling, degenerate-quad
rejection, PDP-area formula parity with `rules.json`, shape-specific
UNCERTAIN behavior for `IRREGULAR`/`UNKNOWN` geometry, and a structural
assertion that `GeometryReadiness.READY_FOR_CAPTURE`'s value never contains
the word "compliant".

Full backend suite after this change (excluding the two tests that require
a live PostgreSQL instance, `test_auth.py` / `test_api_integration.py`,
which were unaffected and unrun in this sandbox for that reason only):

```
61 passed (19 pre-existing + 23 geometry + 19 calibration)
```

## 7. REAL-PHOTO VALIDATION

The repository does not currently contain real product photographs (jar,
lotion bottle, curved/reflective packaging, Pringles-style tube, etc. — the
brief's suggested validation set). The only image asset present is
`dataset/images/` (50 PNGs), which `dataset/generate_dataset.py` explicitly
labels as **synthetic, programmatically-drawn label mockups** for
pipeline-integration testing, not real photography, and explicitly says not
to present them as product photos.

Ran `detect_package_geometry()` over all 50 synthetic images as a smoke
test:

- Bounding box found: 50/50.
- Classified `GeometryType.FLAT`: 50/50 (expected: every mockup is a flat,
  rectangular label rendered edge-to-edge).
- Shape confidence: min 0.35, max 0.60, mean 0.42 — capped below the
  detector's normal ceiling (~0.9) because most of these mockups fill the
  entire canvas and therefore trip the "contour touches image border ->
  confidence capped" rule. That rule exists for real photos where
  border-touching usually means "package cut off"; for a full-bleed
  synthetic label it's a false positive for that specific note, but the
  confidence cap direction (conservative, not overclaiming) is the correct
  failure mode either way.
- No PDP-area/measurement validation against ground truth was possible,
  because this dataset has no physical reference object or known real-world
  dimension in any image, and no ground-truth mm/cm2 values exist to compare
  against.

**Honest conclusion:** the shape-classification and package-boundary logic
is exercised and passes a plausibility check on the available synthetic
assets, but this subsystem has **not** been validated against real,
photographed packaging, curved surfaces, or reflective materials, and no
accuracy/error numbers can be honestly reported without such data. This is
listed under Known Limitations below — do not present the 50/50 figures
above as detection *accuracy* against real products; they only show the
code runs without crashing/misclassifying shape category on this synthetic
set.

## 8. VERIFIED

- All 42 new tests pass deterministically (no flaky/random-seeded failures;
  numpy RNGs used in tests are seeded).
- `PDP_AREA_CYLINDRICAL_FACTOR` in `calibration.py` is asserted equal to the
  `0.40` factor read live from `rules/rules.json` by a test, so the two
  cannot silently drift apart.
- `MeasurementMode.VERIFIED` is only producible when
  `CalibrationInfo.validated is True`; every calibration constructor that
  defaults to `validated=False` (known-dimension, user-reference) is
  asserted to only ever yield `ESTIMATED`, never `VERIFIED`.
- Schema changes were confirmed non-breaking by re-running the full
  pre-existing backend test suite (61/61, including the 19 pre-existing
  tests) after the schema edits.

## 9. UNVERIFIED / NOT ATTEMPTED

- No validation against real photographs (see §7).
- `align_multi_image_surfaces()` (ORB + RANSAC) is a best-effort classical
  alignment; it is exercised on synthetic textured images only. It has not
  been tested on a genuinely split PDP (e.g. a real Pringles-tube-style
  capture split across two rotated photos), and its inlier-fraction
  threshold (0.4) is a reasonable-but-unvalidated heuristic.
- `calibrate_from_depth()` has no real device/AR depth data to validate
  against; its uncertainty formula (`1 - depth_confidence`) is a documented
  placeholder, not a device-calibrated figure.
- `measure_pdp_area()` for `GeometryType.IRREGULAR` / `UNKNOWN` shapes is
  intentionally **not implemented** (returns `UNCERTAIN`) rather than
  attempting the Rule 7(1) "other shape / total surface area" formula from a
  single 2D image, which this module cannot do responsibly without either a
  3D model or multiple calibrated views.
- No wiring was added into `main.py` to auto-populate the manually-entered
  `pdp_area_cm2` field from `measure_pdp_area()`'s output. This is a
  deliberate scope boundary (see Integration Notes below), not an oversight.

## 10. KNOWN LIMITATIONS

- Classical CV only (contours / `approxPolyDP` / ellipse fitting /
  ORB+RANSAC), per the brief's explicit "do not overfit into a
  machine-learning project" instruction. It will misclassify unusual
  packaging shapes and is not a substitute for human review.
- `detect_package_geometry()` uses a single foreground/background
  segmentation heuristic (border-median background-difference + Canny
  edges); it can under- or over-segment against highly textured or
  multi-object backgrounds beyond what was tested here (a synthetic
  25-rectangle clutter scene).
- Cylindrical PDP-area measurement requires a *separately measured*
  circumference; nothing in this module infers circumference from a single
  frontal photo of a bottle/jar (that would require either a wrap-around
  capture or a depth/diameter estimate this module does not attempt to
  fabricate).
- Rectification quality (`reprojection_error_px`) is a self-consistency
  check of the homography, not an independent accuracy measure of the real
  physical rectangle.
- Uncertainty propagation uses simple quadrature combination of a fixed
  pixel-localization allowance (default 1.5px) and the calibration's stated
  scale uncertainty. This is a standard, conservative approximation, not a
  full covariance-based error model.
- None of the words "exact", "guaranteed", or "100% accurate" are used
  anywhere in `geometry.py` or `calibration.py`, in keeping with the brief.

## 11. INTEGRATION NOTES FOR CLAUDE 3

- **Nothing here calls into `main.py`, `rule_engine.py`, `capture_session.py`,
  or the database.** All functions are pure(ish) — they take images/schema
  models in, return schema models out, with no side effects beyond the
  optional `rectify_pdp()` numpy image return.
- `PhysicalMeasurement.status` reuses `MeasurementMode` (now with
  `NOT_OBSERVED` added) specifically so it can be compared the same way
  `rule_engine._evaluate_font_height()` already compares
  `RawExtraction.measurement_mode` — no adapter needed for that field.
- Suggested (optional) wiring point, left to you rather than done here per
  this agent's brief ("don't rewrite the legal engine architecture", "don't
  rewrite unrelated modules"): in `main.py`, where `pdp_area_cm2` is
  currently a manually-entered `Form`/request field, you could call
  `calibration.measure_pdp_area(...)` to **suggest** a value back to the
  inspector for confirmation, but the manually-entered field should remain
  the one that actually reaches `rule_engine.run_inspection()` unless/until
  you decide the automatic path is trustworthy enough to bypass manual
  confirmation. This subsystem deliberately stops short of that decision.
- `capture_session.build_surface_observation()` currently builds
  `SurfaceObservation.pdp_bbox` from `image_quality.estimate_pdp_bbox()`
  (OCR-clustering only). If you want geometry-aware PDP bboxes in
  `SurfaceObservation`, `geometry.detect_pdp_geometry()` returns a superset
  of that information (confidence, polygon, planarity, package-boundary
  intersection) and can be substituted or run alongside it; the two do not
  conflict, since `detect_pdp_geometry()` already accepts the same
  `ocr_boxes` shape `image_quality.estimate_pdp_bbox()` consumes.
- Live-capture integration (for whoever owns that surface): call
  `geometry.lightweight_geometry_check()` per-frame; it's designed to be
  cheap (no ellipse fitting / shape classification / rectification) and
  returns a `GeometryReadinessResult` whose `status` field is exactly the
  `GeometryReadiness` enum requested in the brief
  (`PACKAGE_NOT_DETECTED` / ... / `READY_FOR_CAPTURE`). Re-emphasizing the
  brief's own warning: `READY_FOR_CAPTURE` must never be surfaced to a user
  or logged as a compliance signal — it is a framing/focus/calibration
  readiness signal only.
- If real product photographs become available, re-run the smoke test in
  §7 against them (`detect_package_geometry`, `detect_pdp_geometry`,
  `classify_package_shape`) before trusting confidence numbers in a demo —
  the current numbers are only validated against synthetic mockups.
