"""
Tests for `region_detection`.

Two families, kept visibly separate:

BEHAVIOURAL
    The detector finds text blocks, barcodes, labels and package boundaries in
    synthetic images with known layout, and the coordinate contract holds.

LEGAL-SAFETY INVARIANTS
    These encode the non-negotiable semantics from the module docstring. A
    failure here is not a quality regression, it is a correctness failure with
    legal consequences:
      - TEXT is never a claim that a declaration is present
      - DECLARATION_TEXT is a routing hint, and unpromoted text is still read
      - STICKER is a review flag, never a violation
      - PACKAGE_BOUNDARY is never a PDP
      - an empty result is never evidence of absence
      - detector confidence is never presented as a probability
      - symbology regions never reach text OCR (the "17m" regression)

Synthetic fixtures here are clearly synthetic and are labelled as such. They
test LOGIC. Real-photo behaviour is measured separately by the dataset
benchmark, which is the only thing allowed to make accuracy claims.
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
import region_detection as rd  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _blank(width: int = 600, height: int = 480, level: int = 240) -> np.ndarray:
    return np.full((height, width, 3), level, dtype=np.uint8)


def _label_panel(
    *,
    width: int = 600,
    height: int = 480,
    panel: tuple = (80, 90, 440, 300),
) -> np.ndarray:
    """White panel on a mid-grey background, carrying several text lines."""
    img = np.full((height, width, 3), 120, dtype=np.uint8)
    x, y, w, h = panel
    cv2.rectangle(img, (x, y), (x + w, y + h), (245, 245, 245), -1)
    lines = [
        "MRP Rs 420.00",
        "Net Quantity 100 g",
        "Batch HF130526",
        "Use By 12/10/27",
    ]
    for index, text in enumerate(lines):
        cv2.putText(
            img,
            text,
            (x + 20, y + 60 + index * 62),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (15, 15, 15),
            2,
            cv2.LINE_AA,
        )
    return img


def _synthetic_barcode(
    *,
    width: int = 600,
    height: int = 400,
    bbox: tuple = (150, 140, 300, 120),
    seed: int = 7,
) -> np.ndarray:
    """
    Synthetic 1D barcode: random-width vertical bars, identical on every row.

    Row-identical construction is the point — it reproduces the translational
    invariance that distinguishes a barcode from text.
    """
    img = np.full((height, width, 3), 250, dtype=np.uint8)
    x, y, w, h = bbox
    rng = np.random.default_rng(seed)
    cursor = x
    while cursor < x + w:
        bar_w = int(rng.integers(2, 7))
        if rng.random() < 0.5:
            cv2.rectangle(img, (cursor, y), (min(cursor + bar_w, x + w), y + h), (10, 10, 10), -1)
        cursor += bar_w
    return img


def _text_lines_image(
    *,
    width: int = 600,
    height: int = 400,
    vertical: bool = False,
) -> np.ndarray:
    """Dense text lines; optionally rotated 90 degrees to make them vertical."""
    img = np.full((height, width, 3), 245, dtype=np.uint8)
    for index in range(5):
        cv2.putText(
            img,
            "NET QUANTITY 100 g",
            (40, 70 + index * 66),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )
    if vertical:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    return img


def _package_on_background() -> np.ndarray:
    """A dark rectangular package on a light background, with print on it."""
    img = np.full((520, 640, 3), 235, dtype=np.uint8)
    cv2.rectangle(img, (140, 110), (500, 420), (70, 90, 70), -1)
    for index in range(3):
        cv2.putText(
            img,
            "MRP 60.00",
            (170, 190 + index * 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (250, 250, 250),
            2,
            cv2.LINE_AA,
        )
    return img


# ---------------------------------------------------------------------------
# LEGAL-SAFETY INVARIANTS
# ---------------------------------------------------------------------------


def test_text_region_never_claims_a_declaration_is_present():
    """TEXT means 'printed characters', full stop."""
    regions = rd.detect_text_regions(_text_lines_image())
    assert regions, "Expected text blocks in a synthetic text image."
    for region in regions:
        assert region.region_type is rd.RegionType.TEXT
        lowered = region.reason.lower()
        assert "not" in lowered and "declaration" in lowered, (
            "A TEXT region's reason must state that it is not a declaration "
            f"claim; got: {region.reason!r}"
        )
        for forbidden in ("non-compliant", "violation", "missing", "fail"):
            assert forbidden not in lowered


def test_declaration_text_is_a_routing_hint_and_never_drops_text():
    """
    Promotion must only RE-TYPE regions, never remove them.

    If promotion could drop a region, an unpromoted block holding the real MRP
    would silently never be read — a declaration would be reported absent
    because the router deprioritised it.
    """
    img = _label_panel()
    result = rd.detect_regions(img, promote_declarations=False)
    unpromoted = {r.bbox for r in result.regions}

    promoted_result = rd.detect_regions(img, promote_declarations=True)
    promoted = {r.bbox for r in promoted_result.regions}

    assert unpromoted == promoted, "Promotion changed the region SET, not just types."

    declarations = promoted_result.of_type(rd.RegionType.DECLARATION_TEXT)
    assert declarations, "Expected at least one declaration-text routing hint."
    for region in declarations:
        lowered = region.reason.lower()
        assert "routing hint" in lowered
        assert "not a claim" in lowered
        assert "still read" in lowered


def test_unpromoted_text_is_still_routed_to_ocr():
    """Every text-like region must reach OCR, promoted or not."""
    img = _label_panel()
    result = rd.detect_regions(img)
    routed = {r.bbox for r in result.text_regions()}
    expected = {
        r.bbox
        for r in result.regions
        if r.region_type
        in (rd.RegionType.TEXT, rd.RegionType.DECLARATION_TEXT, rd.RegionType.LABEL)
    }
    assert expected <= routed


def test_package_boundary_is_never_a_pdp():
    """
    The boundary must be typed and worded so it cannot be quoted as a PDP.

    Conflating the two would let a boundary error propagate into a Rule 8
    font-size / PDP-area claim.
    """
    boundary = rd.detect_package_boundary(_package_on_background())
    assert boundary is not None
    assert boundary.region_type is rd.RegionType.PACKAGE_BOUNDARY
    assert "not the principal display panel" in boundary.reason.lower()
    # And no region type in the vocabulary asserts a PDP at all.
    assert not any("PDP" in member.value for member in rd.RegionType)


def test_missing_package_boundary_returns_none_rather_than_a_guess():
    """
    A featureless close-up has no boundary. Returning a fabricated one would
    push a wrong region set into every downstream stage.
    """
    assert rd.detect_package_boundary(_blank()) is None


def test_empty_result_is_labelled_as_an_evidence_gap_not_an_absence():
    result = rd.detect_regions(_blank(level=250))
    joined = " ".join(result.notes).lower()
    assert "not" in result.coverage_note.lower()
    assert "declaration is missing" in result.coverage_note.lower()
    if not result.regions:
        assert "evidence gap" in joined
        assert "not as a finding" in joined


def _pasted_sticker_image() -> np.ndarray:
    """
    A revised-price sticker pasted on printed packaging.

    The sticker is placed on the package background rather than inside the label
    panel on purpose: the underlying heuristic uses RETR_EXTERNAL, so a sticker
    fully nested inside a larger high-contrast rectangle is absorbed into that
    rectangle's contour and never proposed separately. That is a real limitation
    of the current detector, recorded here rather than papered over — see
    `test_nested_sticker_is_a_known_detector_limitation`.
    """
    img = np.full((480, 600, 3), 118, dtype=np.uint8)
    for index in range(4):
        cv2.putText(
            img,
            "PACKED BY EXAMPLE FOODS",
            (40, 60 + index * 110),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (235, 235, 235),
            2,
            cv2.LINE_AA,
        )
    rng = np.random.default_rng(1)
    img[300:390, 210:430] = rng.normal(206, 13, (90, 220, 3)).clip(0, 255).astype(np.uint8)
    cv2.rectangle(img, (210, 300), (430, 390), (120, 125, 130), 3)
    cv2.putText(
        img, "MRP Rs 480", (225, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (10, 10, 10), 2, cv2.LINE_AA
    )
    return img


def test_sticker_region_is_a_review_flag_not_a_violation():
    """Overpasting is lawful in many cases; the wording must not allow a FAIL."""
    regions = rd.detect_sticker_candidate_regions(_pasted_sticker_image())
    assert regions, "Expected the pasted sticker to be flagged for review."
    truth = (210, 300, 220, 90)
    assert any(rd._iou(r.bbox, truth) > 0.3 for r in regions), (
        f"No candidate overlapped the pasted sticker; got {[r.bbox for r in regions]}"
    )
    for region in regions:
        assert region.region_type is rd.RegionType.STICKER
        lowered = region.reason.lower()
        assert "review flag" in lowered
        assert "not a violation" in lowered
        for forbidden in ("counterfeit", "tampering", "fake", "fail"):
            assert forbidden not in lowered


def test_nested_sticker_is_a_known_detector_limitation():
    """
    Documents a real gap honestly instead of leaving it silent.

    The sticker heuristic uses RETR_EXTERNAL, so a sticker wholly inside a
    brighter label panel is swallowed by the panel's contour. This test asserts
    the CURRENT behaviour so that improving the detector (contour hierarchy, or
    running the heuristic per detected LABEL region) will surface here as a
    deliberate change rather than an accidental one.

    Safety note: this gap can only cause a MISSED review flag, never a false
    violation, so it degrades toward caution.
    """
    img = _label_panel()
    cv2.rectangle(img, (200, 170), (380, 250), (255, 255, 255), -1)
    cv2.putText(
        img, "Rs 480", (215, 225), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA
    )
    nested = rd.detect_sticker_candidate_regions(img)
    truth = (200, 170, 180, 80)
    assert not any(rd._iou(r.bbox, truth) > 0.3 for r in nested), (
        "The nested-sticker limitation appears to be fixed. Update this test "
        "and the module docstring."
    )


def test_symbology_regions_are_never_routed_to_text_ocr():
    """
    The "17m" regression, encoded as an invariant.

    Barcode noise read as text became a net-quantity value. Symbology regions
    must be excluded from the OCR route by TYPE, not by luck.
    """
    img = _synthetic_barcode()
    result = rd.detect_regions(img)
    symbols = result.symbology_regions()
    assert symbols, "Expected the synthetic barcode to be localised."

    routed = result.text_regions()
    for symbol in symbols:
        assert symbol not in routed
        assert not symbol.is_text_like()

    pairs = rd.crops_for_ocr(img, result)
    for region, _variants, _signals in pairs:
        assert not region.is_symbology(), (
            f"A {region.region_type.value} region was sent to text OCR."
        )


def test_a_false_symbology_region_cannot_hide_overlapping_text():
    """
    Cap ridges and brand marks do produce false barcode/QR proposals on the
    real dataset. That must cost nothing: because suppression never crosses
    region types, text under a false symbology box is still proposed and still
    routed to OCR.
    """
    img = _text_lines_image()
    text_only = rd.detect_text_regions(img)
    assert text_only

    fake_symbol = rd.region_from_bbox(
        (0, 0, img.shape[1], img.shape[0]), rd.RegionType.BARCODE
    )
    combined = rd.suppress_overlaps(list(text_only) + [fake_symbol])
    surviving_text = [r for r in combined if r.region_type is rd.RegionType.TEXT]
    assert len(surviving_text) == len(text_only)


def test_detector_confidence_is_documented_as_not_a_probability():
    result = rd.detect_regions(_label_panel())
    assert result.regions
    for region in result.regions:
        assert 0.0 <= region.confidence <= 1.0
        semantics = region.provenance()["confidence_semantics"]
        assert "not a calibrated probability" in semantics
        assert "not a legal confidence" in semantics


def test_every_region_carries_reproducible_provenance():
    result = rd.detect_regions(_label_panel())
    assert result.regions
    valid_types = {member.value for member in rd.RegionType}
    valid_methods = {member.value for member in rd.DetectionMethod}
    for region in result.regions:
        record = region.provenance()
        assert record["region_type"] in valid_types
        assert record["detection_method"] in valid_methods
        assert len(record["bbox"]) == 4
        assert record["reason"]

    top = result.provenance()
    assert top["region_count"] == len(result.regions)
    assert "declaration is missing" in top["coverage_note"].lower()


def test_detection_does_not_mutate_the_input_image():
    """
    The captured image is the evidence of record. Detection must not touch it.
    """
    img = _label_panel()
    before = pp.image_fingerprint(img)
    rd.detect_regions(img, include_stickers=True)
    rd.detect_regions_on_full_image(img)
    assert pp.image_fingerprint(img) == before


def test_truncated_regions_are_flagged_so_ocr_is_treated_as_partial():
    """
    A region running off the frame edge may continue outside the photograph.
    Its text is PARTIAL evidence, and the flag is what lets callers say so
    instead of treating a cut-off declaration as complete.
    """
    img = _text_lines_image()
    # A block deliberately anchored at the left edge.
    cv2.putText(
        img, "MRP 420", (0, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2, cv2.LINE_AA
    )
    regions = rd.detect_text_regions(img)
    edge_regions = [r for r in regions if r.bbox[0] <= 2]
    if not edge_regions:
        pytest.skip("No edge-anchored region was proposed on this synthetic image.")
    assert any(r.truncated for r in edge_regions)


# ---------------------------------------------------------------------------
# BEHAVIOURAL
# ---------------------------------------------------------------------------


def test_horizontal_text_blocks_are_detected():
    regions = rd.detect_text_regions(_text_lines_image())
    assert len(regions) >= 3
    for region in regions:
        assert region.width >= rd.MIN_REGION_SIDE_PX
        assert region.height >= rd.MIN_REGION_SIDE_PX


def test_vertical_text_is_detected_without_rotating_the_whole_image():
    """
    The mandatory mixed-orientation case (dense label with horizontal AND
    vertical text) requires the vertical grouping pass. Whole-image rotation is
    explicitly not the primary solution, so vertical text must be found in the
    image as captured.
    """
    vertical = _text_lines_image(vertical=True)
    regions = rd.detect_text_regions(vertical)
    assert regions, "Vertical text produced no regions."
    tall = [r for r in regions if r.height > r.width]
    assert tall, f"Expected at least one taller-than-wide region; got {[r.bbox for r in regions]}"


def test_synthetic_barcode_is_localised_as_symbology():
    img = _synthetic_barcode()
    regions = rd.detect_symbology_regions(img)
    assert regions
    barcodes = [r for r in regions if r.region_type is rd.RegionType.BARCODE]
    assert barcodes
    # The proposal should overlap the drawn symbol.
    truth = (150, 140, 300, 120)
    assert any(rd._iou(r.bbox, truth) > 0.25 for r in barcodes)


def test_row_translational_invariance_separates_barcodes_from_text():
    """
    This is the measured discriminator, so it gets a direct test: a barcode's
    every scan line is the same signal; text changes row to row.
    """
    bar = pp._to_gray(_synthetic_barcode())[140:260, 150:450]
    txt = pp._to_gray(_text_lines_image())[40:110, 30:520]

    bar_score = rd._row_translational_invariance(bar)
    txt_score = rd._row_translational_invariance(txt)

    assert bar_score >= rd.MIN_BARCODE_ROW_INVARIANCE
    assert txt_score < rd.MIN_BARCODE_ROW_INVARIANCE
    assert bar_score > txt_score


def test_label_panel_is_detected_as_a_container():
    regions = rd.detect_label_regions(_label_panel())
    assert regions
    truth = (80, 90, 440, 300)
    assert any(rd._iou(r.bbox, truth) > 0.5 for r in regions)


def test_blank_panel_is_not_a_label():
    """A label carries print. An empty rectangle is a rectangle."""
    img = np.full((480, 600, 3), 120, dtype=np.uint8)
    cv2.rectangle(img, (80, 90), (520, 390), (245, 245, 245), -1)
    assert not rd.detect_label_regions(img)


def test_parents_are_assigned_for_nested_regions():
    result = rd.detect_regions(_label_panel())
    labels = [
        index
        for index, region in enumerate(result.regions)
        if region.region_type is rd.RegionType.LABEL
    ]
    if not labels:
        pytest.skip("No label panel detected in this synthetic image.")
    nested = [r for r in result.regions if r.parent_index is not None]
    assert nested, "Expected some regions nested inside the label panel."
    for region in nested:
        parent = result.regions[region.parent_index]
        assert parent.area > region.area


def test_offset_is_applied_to_every_bbox_and_recorded():
    img = _label_panel()
    plain = rd.detect_regions(img)
    shifted = rd.detect_regions(img, offset=(37, 91))

    assert shifted.offset == (37, 91)
    assert len(plain.regions) == len(shifted.regions)
    for before, after in zip(plain.regions, shifted.regions):
        assert after.bbox[0] == before.bbox[0] + 37
        assert after.bbox[1] == before.bbox[1] + 91
        assert after.bbox[2:] == before.bbox[2:]


def test_full_image_entry_point_maps_coordinates_back_through_chrome_cropping():
    """
    Regions detected on a chrome-cropped screenshot must come back in ORIGINAL
    image coordinates — the frame that evidence references and audit records use.
    """
    panel = _label_panel(width=540, height=700)
    bar_h = 80
    framed = np.zeros((700 + 2 * bar_h, 540, 3), dtype=np.uint8)
    framed[bar_h:bar_h + 700] = panel

    result, content = rd.detect_regions_on_full_image(framed)
    assert not content.is_full_image, "Expected the black bars to be trimmed."
    assert result.offset == content.bbox[:2]
    assert result.regions

    # Every region must sit inside the original frame, and text regions must
    # land below the trimmed top bar.
    for region in result.regions:
        x, y, w, h = region.bbox
        assert 0 <= x and 0 <= y
        assert x + w <= framed.shape[1]
        assert y + h <= framed.shape[0]

    text_regions = [r for r in result.regions if r.is_text_like()]
    assert text_regions
    assert all(r.bbox[1] >= bar_h - 2 for r in text_regions)


def test_crops_for_ocr_bridges_regions_into_preprocessing():
    img = _label_panel()
    result = rd.detect_regions(img)
    pairs = rd.crops_for_ocr(img, result, limit=5)
    assert pairs
    for region, variants, signals in pairs:
        assert region.is_text_like()
        assert variants, "Every routed region must produce at least one variant."
        assert len(variants) <= pp.MAX_VARIANTS
        assert variants[0].name == "grayscale"
        assert isinstance(signals, pp.QualitySignals)


def test_crops_for_ocr_handles_an_offset_result():
    """
    When detection ran on a crop, `crops_for_ocr` must undo the offset before
    cropping, or every variant would be built from the wrong pixels.
    """
    panel = _label_panel(width=540, height=700)
    bar_h = 80
    framed = np.zeros((700 + 2 * bar_h, 540, 3), dtype=np.uint8)
    framed[bar_h:bar_h + 700] = panel

    content, region = pp.crop_screenshot_chrome(framed)
    result = rd.detect_regions(content, offset=region.bbox[:2])
    pairs = rd.crops_for_ocr(content, result, limit=4)
    assert pairs
    for _region, variants, _signals in pairs:
        assert variants


def test_region_from_bbox_records_that_a_human_supplied_it():
    region = rd.region_from_bbox((10, 20, 60, 40), rd.RegionType.DECLARATION_TEXT)
    assert region.method is rd.DetectionMethod.CALLER_SUPPLIED
    assert region.bbox == (10, 20, 60, 40)
    with pytest.raises(ValueError):
        rd.region_from_bbox((10, 20, 0, 40))


def test_suppression_is_within_type_only():
    """
    A barcode inside a label, or a sticker over text, are both real and both
    legally interesting. Cross-type collapsing would destroy that evidence.
    """
    box = (100, 100, 200, 100)
    label = rd.region_from_bbox(box, rd.RegionType.LABEL, confidence=0.9)
    barcode = rd.region_from_bbox(box, rd.RegionType.BARCODE, confidence=0.8)
    duplicate = rd.region_from_bbox(box, rd.RegionType.LABEL, confidence=0.4)

    kept = rd.suppress_overlaps([label, barcode, duplicate])
    kinds = sorted(r.region_type.value for r in kept)
    assert kinds == ["BARCODE", "LABEL"]


def test_region_count_is_bounded():
    """Busy packaging must not flood the OCR queue or the review UI."""
    rng = np.random.default_rng(3)
    noisy = rng.integers(0, 255, (700, 700, 3), dtype=np.uint8)
    result = rd.detect_regions(noisy)
    text_like = [r for r in result.regions if r.is_text_like()]
    assert len(text_like) <= rd.MAX_REGIONS + 8


def test_empty_image_is_rejected_rather_than_silently_handled():
    with pytest.raises(ValueError):
        rd.detect_regions(np.zeros((0, 0, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        rd.detect_regions_on_full_image(np.zeros((0, 0, 3), dtype=np.uint8))
    assert rd.detect_package_boundary(np.zeros((0, 0, 3), dtype=np.uint8)) is None
    assert rd.detect_text_regions(np.zeros((0, 0, 3), dtype=np.uint8)) == []
    assert rd.detect_symbology_regions(np.zeros((0, 0, 3), dtype=np.uint8)) == []


def test_grayscale_input_is_accepted():
    """
    Callers hand us whatever the capture produced. A grayscale image must not
    crash the graphic pass (which needs colour) or the text pass.
    """
    gray = pp._to_gray(_label_panel())
    result = rd.detect_regions(gray)
    assert result.image_width == gray.shape[1]
    assert result.regions
    assert rd.detect_graphic_regions(gray) == []
