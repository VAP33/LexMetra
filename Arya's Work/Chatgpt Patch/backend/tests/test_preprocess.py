"""
Regression tests for the preprocessing pipeline (`backend/preprocess.py`).

These tests are deliberately dependency-light (cv2 + numpy only) so they run in
any environment where OpenCV is importable, including environments where
FastAPI/pydantic/PostgreSQL are unavailable.

Two families of assertion live here:

1. BEHAVIOURAL — a chosen recipe actually improves the measured condition it
   targets (CLAHE raises contrast, upscaling enlarges tiny text, chrome
   detection removes chrome), and variant selection stays bounded.

2. LEGAL-SAFETY INVARIANTS — preprocessing never mutates the original, never
   loses the ability to map coordinates back to the original, and never claims
   to have recovered saturated (glare) pixels. These protect the rule that
   evidence quality problems must surface as UNCERTAIN / NEEDS_RECAPTURE and
   never as a compliance FAIL.

Synthetic fixtures are used here on purpose: they isolate one defect at a time.
Real-photo behaviour is covered separately by the dataset benchmark.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import preprocess as pp  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic fixtures — one defect per image
# ---------------------------------------------------------------------------


def _text_image(
    text: str = "MRP Rs 420.00",
    *,
    width: int = 640,
    height: int = 220,
    scale: float = 2.0,
    thickness: int = 3,
    fg: int = 20,
    bg: int = 235,
) -> np.ndarray:
    """A clean synthetic label: dark text on a light background, BGR."""
    img = np.full((height, width, 3), bg, dtype=np.uint8)
    cv2.putText(
        img,
        text,
        (24, int(height * 0.62)),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (fg, fg, fg),
        thickness,
        cv2.LINE_AA,
    )
    return img


def _blurred(img: np.ndarray, sigma: float = 4.0) -> np.ndarray:
    return cv2.GaussianBlur(img, (0, 0), sigmaX=sigma)


def _low_contrast(img: np.ndarray) -> np.ndarray:
    """Compress the dynamic range into a narrow mid-grey band."""
    return np.clip(img.astype(np.float32) * 0.16 + 112.0, 0, 255).astype(np.uint8)


def _with_glare(img: np.ndarray, *, radius: int = 70) -> np.ndarray:
    """Add a saturated specular blob over part of the text."""
    out = img.copy()
    centre = (int(out.shape[1] * 0.45), int(out.shape[0] * 0.55))
    cv2.circle(out, centre, radius, (255, 255, 255), -1)
    return out


def _uneven_illumination(img: np.ndarray) -> np.ndarray:
    """Apply a strong left-to-right lighting gradient."""
    height, width = img.shape[:2]
    ramp = np.linspace(0.28, 1.35, width, dtype=np.float32)
    gain = np.repeat(ramp[None, :], height, axis=0)[:, :, None]
    return np.clip(img.astype(np.float32) * gain, 0, 255).astype(np.uint8)


def _light_on_dark(text: str = "NET WT 100 g") -> np.ndarray:
    return _text_image(text, fg=245, bg=25)


def _tiny_text(text: str = "Batch HF130526") -> np.ndarray:
    return _text_image(text, width=300, height=54, scale=0.42, thickness=1)


def _screenshot_with_chrome(photo_height: int = 900) -> np.ndarray:
    """
    Synthesised phone screenshot: dark status bar, photo, dark filmstrip row.

    Mirrors the structure of the real dataset's gallery screenshots: flat dark
    chrome at the top, photographic content in the middle, and a bottom band
    that mixes dark control rows with a colourful thumbnail strip.
    """
    width = 540
    status_h, action_h, strip_h = 90, 70, 120
    total = status_h + photo_height + action_h + strip_h
    img = np.zeros((total, width, 3), dtype=np.uint8)

    # Status bar: flat dark grey with a little text.
    img[:status_h] = (18, 18, 18)
    cv2.putText(img, "10:10", (16, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (230, 230, 230), 2)

    # Photographic content: textured, mid-bright.
    rng = np.random.default_rng(7)
    photo = rng.integers(70, 210, size=(photo_height, width, 3), dtype=np.uint16).astype(np.uint8)
    photo = cv2.GaussianBlur(photo, (0, 0), sigmaX=2.5)
    cv2.putText(photo, "MRP 250", (40, 400), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (10, 10, 10), 4)
    img[status_h : status_h + photo_height] = photo

    # Action row: flat dark.
    y0 = status_h + photo_height
    img[y0 : y0 + action_h] = (12, 12, 12)

    # Filmstrip: dark background with small colourful thumbnails.
    y1 = y0 + action_h
    img[y1 : y1 + strip_h] = (8, 8, 8)
    for index in range(6):
        x = 10 + index * 88
        thumb = rng.integers(40, 240, size=(70, 70, 3), dtype=np.uint16).astype(np.uint8)
        img[y1 + 25 : y1 + 95, x : x + 70] = thumb

    return img, status_h, photo_height


# ---------------------------------------------------------------------------
# Legal-safety invariants
# ---------------------------------------------------------------------------


def test_build_variants_never_mutates_the_original_image():
    """
    CRITICAL: the original capture is the evidence of record. Preprocessing must
    never write into it, or the stored original would no longer match what the
    inspector photographed.
    """
    original = _with_glare(_uneven_illumination(_text_image()))
    before = pp.image_fingerprint(original)

    variants = pp.build_variants(original)

    assert pp.image_fingerprint(original) == before
    for variant in variants:
        assert not np.shares_memory(variant.image, original), (
            f"Variant {variant.name} aliases the original image buffer."
        )


def test_crop_screenshot_chrome_does_not_mutate_or_alias_the_original():
    img, _status_h, _photo_h = _screenshot_with_chrome()
    before = pp.image_fingerprint(img)

    cropped, region = pp.crop_screenshot_chrome(img)

    assert pp.image_fingerprint(img) == before
    assert not np.shares_memory(cropped, img)
    assert region.bbox[2] > 0 and region.bbox[3] > 0


def test_every_variant_carries_reproducible_provenance():
    """
    Each derived image must record how it was produced. Without this, an
    extracted value cannot be traced back through the transformation chain
    during review or audit.
    """
    variants = pp.build_variants(_low_contrast(_text_image()))
    assert variants

    for variant in variants:
        record = variant.provenance()
        assert record["variant_name"] == variant.name
        assert record["recipe"], f"{variant.name} has an empty recipe."
        assert all(isinstance(step, str) for step in record["recipe"])
        assert record["scale_x"] > 0 and record["scale_y"] > 0
        assert isinstance(record["is_binary"], bool)
        # Recipe entries must be members of the stable vocabulary.
        for step in record["recipe"]:
            pp.RecipeStep(step)


def test_upscaled_variant_maps_coordinates_back_to_source():
    """
    Coordinates found in an upscaled variant must divide back to source pixels,
    otherwise stored evidence bboxes would point at the wrong part of the image.
    """
    tiny = _tiny_text()
    variants = pp.build_variants(tiny, purpose="text")
    upscaled = [v for v in variants if v.name == "upscaled"]
    assert upscaled, "A tiny-text region should produce an upscaled variant."

    variant = upscaled[0]
    assert variant.scale_x > 1.0

    # A box at 4x the origin in the variant maps back to 4x/scale in source.
    x, y, w, h = variant.map_bbox_to_source((40.0, 20.0, 80.0, 30.0))
    assert x == pytest.approx(round(40.0 / variant.scale_x), abs=1)
    assert y == pytest.approx(round(20.0 / variant.scale_y), abs=1)
    assert 0 < w <= tiny.shape[1]
    assert 0 < h <= tiny.shape[0]


def test_glare_suppression_does_not_claim_to_recover_saturated_pixels():
    """
    CRITICAL: saturated highlight pixels carry no information. Suppressing them
    must not be presented as recovery — the variant has to keep the warning
    that text under glare stays UNCERTAIN, and the glare mask must still mark
    the affected area so the evidence layer can gate on it.
    """
    glared = _with_glare(_text_image())
    signals = pp.measure_quality(glared)
    assert signals.has_glare_problem

    variants = pp.build_variants(glared, signals=signals)
    suppressed = [v for v in variants if v.name == "glare_suppressed"]
    assert suppressed, "A glared image should produce a glare-suppressed variant."

    warning = str(suppressed[0].params.get("warning", "")).lower()
    assert "uncertain" in warning

    mask = pp.glare_mask(pp._to_gray(glared))
    assert mask.max() == 255, "Glare mask must flag the saturated region."
    assert float(np.mean(mask > 0)) > 0.01


def test_recapture_guidance_is_capture_advice_not_a_legal_conclusion():
    """
    Guidance text is shown to inspectors. It must never imply that a
    declaration is missing or non-compliant just because the photo is poor.
    """
    bad = _blurred(_with_glare(_low_contrast(_text_image())), sigma=6.0)
    signals = pp.measure_quality(bad)
    advice = pp.recapture_guidance(signals, field_label="the MRP declaration")

    assert advice, "A badly degraded region must produce recapture guidance."
    forbidden = ("non-compliant", "noncompliant", "violation", "missing", "fail", "illegal")
    for line in advice:
        lowered = line.lower()
        for term in forbidden:
            assert term not in lowered, f"Guidance must not assert legality: {line!r}"


def test_variant_count_is_bounded():
    """
    Combinatorial explosion is both a performance problem and a false-positive
    problem: every extra variant is another chance for one engine pass to emit
    a plausible-looking wrong number that fusion then has to arbitrate.
    """
    worst_case = _blurred(
        _with_glare(_uneven_illumination(_low_contrast(_tiny_text()))), sigma=3.0
    )
    variants = pp.build_variants(worst_case)
    assert 0 < len(variants) <= pp.MAX_VARIANTS

    names = [v.name for v in variants]
    assert len(names) == len(set(names)), "Variants must be unique."


# ---------------------------------------------------------------------------
# Quality measurement
# ---------------------------------------------------------------------------


def test_blur_is_detected_and_sharpening_is_attempted_once_only():
    sharp = _text_image()
    blurry = _blurred(sharp, sigma=5.0)

    sharp_signals = pp.measure_quality(sharp)
    blurry_signals = pp.measure_quality(blurry)

    assert blurry_signals.sharpness < sharp_signals.sharpness
    assert blurry_signals.has_blur_problem
    assert not sharp_signals.has_blur_problem

    plan = pp.plan_recipes(blurry_signals)
    assert plan.count("sharpened") == 1, (
        "Blur must trigger exactly one bounded sharpening attempt; a still "
        "unreadable region should be recaptured instead."
    )


def test_glare_is_detected_by_quality_signals():
    clean = _text_image()
    glared = _with_glare(clean)

    assert not pp.measure_quality(clean).has_glare_problem
    glare_signals = pp.measure_quality(glared)
    assert glare_signals.has_glare_problem
    assert glare_signals.glare_fraction > pp.measure_quality(clean).glare_fraction


def test_low_contrast_is_detected_and_clahe_is_selected():
    faded = _low_contrast(_text_image())
    signals = pp.measure_quality(faded)

    assert signals.has_contrast_problem
    assert "clahe" in pp.plan_recipes(signals)


def test_clahe_increases_measured_local_contrast():
    faded = _low_contrast(_text_image())
    before = pp.measure_quality(faded).contrast
    enhanced = pp.apply_clahe(pp._to_gray(faded))
    after = pp.measure_quality(enhanced).contrast

    assert after > before, "CLAHE should raise measured local contrast."


def test_uneven_illumination_is_detected_and_normalisation_flattens_it():
    uneven = _uneven_illumination(_text_image())
    signals = pp.measure_quality(uneven)

    assert signals.has_uneven_illumination
    assert "illumination" in pp.plan_recipes(signals)

    flattened = pp.normalize_illumination(pp._to_gray(uneven))
    assert (
        pp.measure_quality(flattened).illumination_unevenness
        < signals.illumination_unevenness
    ), "Illumination normalisation should reduce the measured lighting gradient."


def test_dark_and_light_text_polarity_is_distinguished():
    dark_on_light = pp.measure_quality(_text_image())
    light_on_dark = pp.measure_quality(_light_on_dark())

    assert dark_on_light.polarity in (pp.TextPolarity.DARK_ON_LIGHT, pp.TextPolarity.MIXED)
    assert light_on_dark.polarity == pp.TextPolarity.LIGHT_ON_DARK

    # Light-on-dark must get an inverted binarisation, not the standard one.
    plan = pp.plan_recipes(light_on_dark)
    assert "adaptive_inverted" in plan
    assert "adaptive" not in plan


def test_tiny_text_is_detected_and_upscaled():
    tiny = _tiny_text()
    signals = pp.measure_quality(tiny)

    assert signals.has_tiny_text
    plan = pp.plan_recipes(signals)
    assert "upscaled" in plan

    variants = {v.name: v for v in pp.build_variants(tiny, signals=signals)}
    assert "upscaled" in variants
    assert variants["upscaled"].image.shape[0] > tiny.shape[0]


def test_upscaling_targets_a_text_height_instead_of_a_fixed_multiplier():
    """
    Regression for a real-dataset failure: applying a fixed 2x to a region whose
    text was ALREADY large enough turned a correct reading ("MRP ... 420" on the
    Bru jar) into an unreadable one. Upscaling must aim at the OCR sweet spot
    and leave already-large text alone.
    """
    tiny = pp.measure_quality(_tiny_text())
    assert tiny.estimated_text_height_px is not None
    assert tiny.estimated_text_height_px < pp.TARGET_TEXT_HEIGHT_PX

    tiny_factor = tiny.upscale_factor_for_text()
    assert tiny_factor > 1.0
    assert tiny_factor <= pp.MAX_UPSCALE_FACTOR
    # The factor should land the text near the target, not overshoot it.
    projected = tiny.estimated_text_height_px * tiny_factor
    assert projected <= pp.TARGET_TEXT_HEIGHT_PX + 1.0

    large = pp.measure_quality(_text_image(scale=3.0, thickness=5, height=300))
    assert large.estimated_text_height_px is not None
    assert large.estimated_text_height_px >= pp.TARGET_TEXT_HEIGHT_PX
    assert large.upscale_factor_for_text() == 1.0
    assert not large.has_tiny_text
    assert "upscaled" not in pp.plan_recipes(large)


def test_selected_colour_channel_is_offered_as_its_own_variant():
    """
    Regression for a real-dataset finding: on the white-on-green Bru label the
    blue plane alone read "MRP" and "420" where luminance read neither, but
    every other planned variant applied a further transform that lost the
    reading again. The plain selected channel must stay in the ensemble.
    """
    img = np.full((240, 640, 3), (40, 120, 40), dtype=np.uint8)
    cv2.putText(
        img, "MRP 420", (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (250, 250, 250), 4, cv2.LINE_AA
    )

    variants = pp.build_variants(img)
    names = [v.name for v in variants]

    channel_variants = [n for n in names if n.startswith("channel_")]
    assert channel_variants, f"Expected a plain channel variant, got {names}"

    variant = next(v for v in variants if v.name == channel_variants[0])
    assert variant.recipe == (pp.RecipeStep.CHANNEL_SELECT,)
    assert variant.image.ndim == 2
    assert not variant.is_binary
    # The untransformed grayscale baseline must still be present alongside it.
    assert "grayscale" in names


def test_estimated_text_height_is_not_a_legal_measurement():
    """
    `estimated_text_height_px` exists to decide upscaling. It is in pixels with
    no physical calibration, so it must never be mistaken for a Rule 7(2) font
    height. This test documents that contract by asserting the value scales with
    image resolution — i.e. it is not a physical quantity.
    """
    base = _text_image()
    doubled = cv2.resize(base, (base.shape[1] * 2, base.shape[0] * 2), interpolation=cv2.INTER_CUBIC)

    base_height = pp.measure_quality(base).estimated_text_height_px
    doubled_height = pp.measure_quality(doubled).estimated_text_height_px

    assert base_height is not None and doubled_height is not None
    assert doubled_height > base_height * 1.4


# ---------------------------------------------------------------------------
# Recipe selection behaviour
# ---------------------------------------------------------------------------


def test_clean_image_gets_a_minimal_plan():
    clean = _text_image()
    plan = pp.plan_recipes(pp.measure_quality(clean))

    assert plan[0] == "grayscale"
    assert "sharpened" not in plan
    assert "glare_suppressed" not in plan
    assert len(plan) <= 4, f"A clean capture should not need a large plan: {plan}"


def test_barcode_purpose_never_binarises():
    """
    Binarisation destroys the module-width gradients a barcode decoder needs,
    and a mis-binarised barcode is a documented source of junk text (the
    dataset's '17m' sidecar noise). The barcode plan must stay non-binary.
    """
    signals = pp.measure_quality(_with_glare(_text_image()))
    plan = pp.plan_recipes(signals, purpose="barcode")

    for name in ("adaptive", "adaptive_inverted", "otsu"):
        assert name not in plan, f"Barcode plan must not include {name}."

    variants = pp.build_variants(
        _with_glare(_text_image()), signals=signals, purpose="barcode"
    )
    assert variants
    assert not any(v.is_binary for v in variants)


def test_numeric_purpose_adds_a_global_threshold_variant():
    signals = pp.measure_quality(_text_image())
    plan = pp.plan_recipes(signals, purpose="numeric")
    assert "otsu" in plan


def test_explicit_plan_overrides_automatic_selection():
    """Determinism hook used by the benchmark harness and by these tests."""
    variants = pp.build_variants(_text_image(), plan=["grayscale", "otsu"])
    assert [v.name for v in variants] == ["grayscale", "otsu"]


# ---------------------------------------------------------------------------
# Region-first preprocessing
# ---------------------------------------------------------------------------


def test_preprocess_region_returns_offset_for_coordinate_mapping():
    """
    A region crop plus its variant scaling forms a two-step coordinate mapping.
    Both steps must be exposed or provenance breaks.
    """
    img = _text_image(width=800, height=400)
    bbox = (300, 120, 260, 150)

    variants, signals, offset = pp.preprocess_region(img, bbox, pad=4)

    assert variants
    assert signals.width <= 260 + 8 and signals.height <= 150 + 8
    assert offset == (bbox[0] - 4, bbox[1] - 4)

    variant = variants[0]
    vx, vy, vw, vh = variant.map_bbox_to_source((10.0, 12.0, 40.0, 20.0))
    source_x = vx + offset[0]
    source_y = vy + offset[1]
    assert bbox[0] - 4 <= source_x <= bbox[0] + bbox[2]
    assert bbox[1] - 4 <= source_y <= bbox[1] + bbox[3]


def test_preprocess_region_selects_per_region_recipes():
    """
    The whole point of region-first preprocessing: two regions of the SAME image
    can need different treatment. Here the left half is glared and the right
    half is a clean dark-on-light block.
    """
    img = _text_image(width=900, height=300)
    img[:, :450] = _with_glare(img[:, :450].copy(), radius=90)

    left_variants, left_signals, _ = pp.preprocess_region(img, (0, 0, 440, 300))
    right_variants, right_signals, _ = pp.preprocess_region(img, (460, 0, 430, 300))

    assert left_signals.has_glare_problem
    assert not right_signals.has_glare_problem

    left_names = {v.name for v in left_variants}
    right_names = {v.name for v in right_variants}
    assert "glare_suppressed" in left_names
    assert "glare_suppressed" not in right_names


def test_preprocess_region_rejects_a_degenerate_region():
    img = _text_image()
    with pytest.raises(ValueError):
        pp.preprocess_region(img, (10, 10, 1, 1), pad=0)


# ---------------------------------------------------------------------------
# Screenshot / letterbox chrome removal
# ---------------------------------------------------------------------------


def test_screenshot_chrome_and_filmstrip_are_removed():
    """
    Gallery UI text ("10:10", location labels, thumbnail contents) is confident
    junk to an OCR engine. It has to be cropped before field classification,
    including the colourful filmstrip that sits between two dark control rows.
    """
    img, status_h, photo_h = _screenshot_with_chrome()
    region = pp.detect_content_region(img)

    assert region.removed_ui_chrome
    x, y, w, h = region.bbox

    # Top boundary should land at or below the status bar.
    assert y >= status_h - 8
    # Bottom boundary should exclude the action row and the filmstrip.
    assert y + h <= status_h + photo_h + 24
    # And it must keep the great majority of the photograph.
    assert h >= photo_h * 0.85


def test_uniform_letterbox_bars_are_removed():
    photo = _text_image(width=400, height=300)
    bar = np.zeros((120, 400, 3), dtype=np.uint8)
    img = np.vstack([bar, photo, bar])

    region = pp.detect_content_region(img)
    assert region.removed_letterbox
    _x, y, _w, h = region.bbox
    assert 100 <= y <= 130
    assert 280 <= h <= 320


def test_a_plain_photograph_is_left_untouched():
    """
    Conservatism check: a wrong crop silently discards evidence, so an image
    with no chrome must be returned whole.
    """
    rng = np.random.default_rng(3)
    photo = rng.integers(60, 200, size=(600, 480, 3), dtype=np.uint16).astype(np.uint8)
    photo = cv2.GaussianBlur(photo, (0, 0), sigmaX=2.0)

    region = pp.detect_content_region(photo)
    assert region.is_full_image
    assert region.bbox == (0, 0, 480, 600)


def test_mid_grey_uniform_band_is_not_mistaken_for_a_letterbox():
    """A plain wall or shelf edge is photograph, not chrome."""
    photo = _text_image(width=400, height=300)
    band = np.full((100, 400, 3), 128, dtype=np.uint8)
    img = np.vstack([band, photo])

    region = pp.detect_content_region(img)
    assert not region.removed_letterbox


def test_chrome_trim_is_abandoned_when_it_would_destroy_the_image():
    """A nearly all-black frame must not be trimmed down to nothing."""
    img = np.zeros((400, 300, 3), dtype=np.uint8)
    img[190:210, 140:160] = 255

    region = pp.detect_content_region(img)
    _x, _y, w, h = region.bbox
    assert w >= 32 and h >= 32


# ---------------------------------------------------------------------------
# Perspective rectification
# ---------------------------------------------------------------------------


def test_rectify_perspective_inverse_maps_back_to_original_coordinates():
    """
    Rectification is only acceptable if the mapping is invertible, because
    stored evidence must point at pixels in the ORIGINAL image.
    """
    img = _text_image(width=600, height=400)
    corners = [(80, 60), (520, 30), (560, 350), (60, 380)]

    rectified, inverse = pp.rectify_perspective(img, corners)
    assert rectified.shape[0] > 8 and rectified.shape[1] > 8

    # The rectified corners must invert back onto the supplied quad.
    ordered = pp.order_corners(np.array(corners, dtype=np.float32))
    h, w = rectified.shape[:2]
    rect_corners = np.array(
        [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32
    ).reshape(-1, 1, 2)

    mapped = cv2.perspectiveTransform(rect_corners, inverse).reshape(4, 2)
    assert np.allclose(mapped, ordered, atol=1.5)


def test_order_corners_produces_a_consistent_ordering():
    quad = np.array([[520, 350], [80, 60], [60, 380], [520, 30]], dtype=np.float32)
    ordered = pp.order_corners(quad)

    top_left, top_right, bottom_right, bottom_left = ordered
    assert top_left[0] < top_right[0]
    assert bottom_left[0] < bottom_right[0]
    assert top_left[1] < bottom_left[1]
    assert top_right[1] < bottom_right[1]


# ---------------------------------------------------------------------------
# Channel selection
# ---------------------------------------------------------------------------


def test_best_channel_selection_beats_luminance_on_a_colour_label():
    """
    White text on a saturated green label (the Bru jar case) separates better in
    a single colour channel than in luminance. The selector should not simply
    fall back to grayscale on such an image.
    """
    img = np.full((240, 640, 3), (40, 120, 40), dtype=np.uint8)  # BGR green
    cv2.putText(
        img, "MRP 420", (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (250, 250, 250), 4, cv2.LINE_AA
    )

    plane, name = pp.select_best_channel(img)
    assert plane.ndim == 2
    assert plane.dtype == np.uint8

    gray = pp._to_gray(img)

    def local_contrast(single: np.ndarray) -> float:
        blurred = cv2.GaussianBlur(single, (0, 0), sigmaX=3)
        return float((single.astype(np.float32) - blurred.astype(np.float32)).std())

    assert local_contrast(plane) >= local_contrast(gray) - 1e-6, (
        f"Selected channel {name!r} should be at least as contrastive as luminance."
    )


def test_select_best_channel_passes_grayscale_through():
    gray = pp._to_gray(_text_image())
    plane, name = pp.select_best_channel(gray)
    assert name == "gray"
    assert np.array_equal(plane, gray)
    assert not np.shares_memory(plane, gray)


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------


def test_fingerprint_detects_any_mutation():
    img = _text_image()
    before = pp.image_fingerprint(img)

    mutated = img.copy()
    mutated[5, 5, 0] = np.uint8((int(mutated[5, 5, 0]) + 40) % 256)

    assert pp.image_fingerprint(mutated) != before
    assert pp.image_fingerprint(img.copy()) == before


def test_empty_input_is_rejected_rather_than_silently_handled():
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        pp.measure_quality(empty)
    with pytest.raises(ValueError):
        pp.build_variants(empty)
    with pytest.raises(ValueError):
        pp.detect_content_region(empty)
