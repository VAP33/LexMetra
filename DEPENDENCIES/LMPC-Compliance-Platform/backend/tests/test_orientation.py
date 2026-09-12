"""
Tests for `orientation`.

Two families, kept visibly separate:

BEHAVIOURAL
    Axis estimation finds the reading direction of synthetic text; rotation is
    lossless; and the coordinate mapping is an exact inverse of the rotation for
    all four orientations.

LEGAL-SAFETY INVARIANTS
    These encode the non-negotiable semantics from the module docstring. A
    failure here is a correctness failure with legal consequences, not a quality
    regression:
      - the ORIGINAL image is never rotated and never mutated
      - an orientation estimate is a ROUTING HINT, never evidence
      - AMBIGUOUS is a first-class answer; the module never silently guesses
      - every estimate offers a way to still read the region, so a bad axis call
        degrades to a slower read and never to an unread region
      - axis confidence is documented as not a probability

THE COORDINATE CONTRACT IS THE POINT OF THIS FILE.
`map_bbox_from_rotated()` is what keeps a vertically-printed net-quantity
declaration pinned to the right pixels of the photograph. A correct reading
attached to the wrong part of the package is an evidence-integrity failure even
though the text is right, so the round-trip is tested exhaustively rather than
by example: every orientation, every box in a grid, plus a pixel-level check
that the mapped box actually contains the ink it claims to.

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

import orientation as ori  # noqa: E402

ALL_ORIENTATIONS = (
    ori.Orientation.DEG_0,
    ori.Orientation.DEG_90,
    ori.Orientation.DEG_180,
    ori.Orientation.DEG_270,
)


# ---------------------------------------------------------------------------
# Synthetic fixtures (clearly synthetic; they test logic, not accuracy)
# ---------------------------------------------------------------------------


def _horizontal_text(width: int = 320, height: int = 120) -> np.ndarray:
    """Three lines of left-to-right synthetic text on a light panel."""
    img = np.full((height, width), 245, np.uint8)
    for i, y in enumerate((28, 58, 88)):
        cv2.putText(
            img,
            "NET QTY 100 g",
            (14, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (20,),
            1,
            cv2.LINE_AA,
        )
    return img


def _vertical_text() -> np.ndarray:
    """
    The same text reading bottom-to-top, as on a cylindrical side panel.

    Produced by rotating the horizontal fixture, so the two fixtures contain
    identical ink and any difference in the measured axis comes from layout
    alone.
    """
    return cv2.rotate(_horizontal_text(), cv2.ROTATE_90_COUNTERCLOCKWISE)


def _blank(width: int = 200, height: int = 200) -> np.ndarray:
    return np.full((height, width), 240, np.uint8)


def _solid() -> np.ndarray:
    return np.full((200, 200), 12, np.uint8)


def _asymmetric_marker(width: int = 90, height: int = 40) -> np.ndarray:
    """
    A crop whose four rotations are all distinguishable.

    A single filled square in one corner plus a bar along one edge means no
    rotation of this image equals any other, so a coordinate-mapping bug cannot
    hide behind a symmetry.
    """
    img = np.full((height, width), 250, np.uint8)
    img[3:12, 3:20] = 0        # bar along the top-left
    img[height - 9:height - 3, width - 12:width - 4] = 0  # bottom-right square
    return img


# ---------------------------------------------------------------------------
# LEGAL-SAFETY INVARIANTS
# ---------------------------------------------------------------------------


def test_rotation_never_mutates_the_source_crop():
    """
    "The preprocessing pipeline must preserve the ORIGINAL IMAGE unchanged."

    Rotation is applied to a COPY. If a crop were rotated in place, every later
    stage would be looking at different pixels than the ones the evidence claims
    to describe.
    """
    crop = _asymmetric_marker()
    before = crop.copy()
    for orientation in ALL_ORIENTATIONS:
        rotated = ori.rotate_crop(crop, orientation)
        assert np.array_equal(crop, before), (
            f"rotate_crop({orientation.label}) modified its input"
        )
        assert rotated is not crop


def test_rotation_is_lossless_and_invents_no_pixel_values():
    """
    Exact transposes only, never an interpolating warp.

    An interpolated rotation invents intermediate grey values, which is the
    image-processing equivalent of inventing evidence. The test asserts the
    multiset of pixel values is preserved exactly.
    """
    crop = _asymmetric_marker()
    original = np.sort(crop.ravel())
    for orientation in ALL_ORIENTATIONS:
        rotated = ori.rotate_crop(crop, orientation)
        assert np.array_equal(np.sort(rotated.ravel()), original), (
            f"{orientation.label} rotation changed the pixel value distribution"
        )


def test_ambiguous_is_a_first_class_answer_not_a_silent_guess():
    """
    "Never average. Never silently choose."

    A blank panel and a solid panel carry no glyph layout. The module must say
    AMBIGUOUS rather than returning whichever score happened to be a hair
    larger.
    """
    for name, fixture in (("blank", _blank()), ("solid", _solid())):
        axis, h, v, conf = ori.estimate_text_axis(fixture)
        assert axis is ori.TextAxis.AMBIGUOUS, f"{name} produced a decided axis"
        assert conf == 0.0

        estimate = ori.estimate_region_orientation(fixture)
        assert estimate.axis is ori.TextAxis.AMBIGUOUS
        assert "inconclusive" in " ".join(estimate.notes).lower()


def test_a_region_is_never_left_unreadable_by_orientation_analysis():
    """
    Failing to orient a region must degrade to a SLOWER READ, never to an
    unread region — because an unread region becomes NOT_OBSERVED, and
    NOT_OBSERVED must never be reported as MISSING.

    So every estimate, whatever the axis, must offer at least one candidate and
    must keep DEG_0 available somewhere in the list.
    """
    fixtures = {
        "horizontal": _horizontal_text(),
        "vertical": _vertical_text(),
        "blank": _blank(),
        "solid": _solid(),
        "tiny": np.full((6, 6), 200, np.uint8),
    }
    for name, crop in fixtures.items():
        estimate = ori.estimate_region_orientation(crop)
        assert estimate.candidates, f"{name}: no orientation candidates offered"
        assert estimate.primary in ALL_ORIENTATIONS
        assert ori.Orientation.DEG_0 in estimate.candidates, (
            f"{name}: upright was dropped, so a wrong axis call could make the "
            "region unreadable"
        )


def test_lower_ranked_candidates_are_retained_not_discarded():
    """A decided axis still offers the other axis as a fallback."""
    for crop in (_horizontal_text(), _vertical_text()):
        estimate = ori.estimate_region_orientation(crop)
        assert len(estimate.candidates) == ori.MAX_ORIENTATION_CANDIDATES
        assert set(estimate.candidates) == set(ALL_ORIENTATIONS), (
            "all four orientations must remain reachable"
        )


def test_geometry_does_not_claim_to_resolve_the_flip():
    """
    Geometry cannot separate 0 from 180, nor 90 from 270 — upside-down text has
    the same ink layout. The module must SAY so rather than implying its primary
    candidate is the answer.
    """
    estimate = ori.estimate_region_orientation(_horizontal_text())
    joined = " ".join(estimate.notes).lower()
    assert "0 from 180" in joined and "90 from 270" in joined
    # The opposite flip must be offered as the immediate fallback.
    assert estimate.candidates[1] in (
        ori.Orientation.DEG_180,
        ori.Orientation.DEG_270,
    )


def test_axis_confidence_is_documented_as_not_a_probability():
    """
    "AI must NEVER directly decide legal compliance."

    The axis score is a ranking heuristic. Presenting it as a probability
    invites it to be combined with legal confidence downstream, so the
    provenance must disclaim it explicitly.
    """
    estimate = ori.estimate_region_orientation(_horizontal_text())
    prov = estimate.provenance()
    semantics = prov["confidence_semantics"].lower()
    assert "not a calibrated probability" in semantics
    assert "not a legal confidence" in semantics
    assert "routing hint" in semantics
    assert 0.0 <= float(prov["axis_confidence"]) <= 1.0


def test_mixed_orientation_image_is_reported_and_the_image_is_never_rotated():
    """
    The mandatory real-photo case: horizontal brand text and vertical side
    declarations in ONE photograph. Rotating the whole image to fix one destroys
    the other, so the summary must report MIXED and state that the original was
    not rotated.
    """
    horizontal = ori.estimate_region_orientation(_horizontal_text())
    vertical = ori.estimate_region_orientation(_vertical_text())
    summary = ori.dominant_axis_summary([horizontal, vertical])

    assert summary["mixed_orientation_image"] is True
    assert summary["regions_analysed"] == 2
    assert "never rotated" in summary["note"].lower()


def test_single_orientation_summary_still_states_the_image_was_not_rotated():
    summary = ori.dominant_axis_summary(
        [ori.estimate_region_orientation(_horizontal_text())]
    )
    assert summary["mixed_orientation_image"] is False
    assert "not\nrotated" in summary["note"].lower().replace(" ", "\n") or (
        "never rotated" in summary["note"].lower()
    )


# ---------------------------------------------------------------------------
# THE COORDINATE CONTRACT
# ---------------------------------------------------------------------------


def test_bbox_round_trip_is_exact_for_every_orientation_and_position():
    """
    Exhaustive round trip: rotate a known box forward by construction, then map
    it back, and require the original box exactly.

    "Forward by construction" means we rotate a MASK containing only that box
    and read the box back out of the rotated mask, so the test does not depend
    on the very arithmetic it is checking.
    """
    src_h, src_w = 61, 97  # deliberately odd, non-square dimensions
    boxes = [
        (x, y, w, h)
        for x in (0, 7, 40, src_w - 12)
        for y in (0, 5, 33, src_h - 9)
        for w, h in ((1, 1), (11, 4), (8, 17))
        if x + w <= src_w and y + h <= src_h
    ]
    assert len(boxes) >= 24, "fixture grid degenerated; the test would be weak"

    for orientation in ALL_ORIENTATIONS:
        for box in boxes:
            x, y, w, h = box
            mask = np.zeros((src_h, src_w), np.uint8)
            mask[y:y + h, x:x + w] = 255

            rotated_mask = ori.rotate_crop(mask, orientation)
            ys, xs = np.nonzero(rotated_mask)
            rotated_box = (
                int(xs.min()),
                int(ys.min()),
                int(xs.max() - xs.min() + 1),
                int(ys.max() - ys.min() + 1),
            )

            recovered = ori.map_bbox_from_rotated(
                rotated_box, orientation, (src_h, src_w)
            )
            assert recovered == box, (
                f"{orientation.label}: {rotated_box} mapped to {recovered}, "
                f"expected {box}"
            )


def test_rotated_shape_matches_the_actual_rotation():
    crop = _asymmetric_marker(width=90, height=40)
    for orientation in ALL_ORIENTATIONS:
        rotated = ori.rotate_crop(crop, orientation)
        assert ori.rotated_shape(crop.shape[:2], orientation) == rotated.shape[:2]


def test_mapped_box_lands_on_the_same_ink_it_was_found_on():
    """
    A stronger claim than arithmetic equality: the ink inside the box in the
    ROTATED crop must be the same ink inside the mapped box in the UNROTATED
    crop. This is what "the reading is attached to the right part of the
    package" actually means.
    """
    crop = _asymmetric_marker()
    src_h, src_w = crop.shape[:2]

    for orientation in ALL_ORIENTATIONS:
        rotated = ori.rotate_crop(crop, orientation)
        rh, rw = rotated.shape[:2]
        # A box around the bar feature, located in rotated coordinates.
        ys, xs = np.nonzero(rotated < 128)
        assert xs.size, "fixture has no ink"
        box = (
            int(xs.min()),
            int(ys.min()),
            int(xs.max() - xs.min() + 1),
            int(ys.max() - ys.min() + 1),
        )
        assert box[0] + box[2] <= rw and box[1] + box[3] <= rh

        mx, my, mw, mh = ori.map_bbox_from_rotated(box, orientation, (src_h, src_w))
        rotated_ink = int(np.count_nonzero(
            rotated[box[1]:box[1] + box[3], box[0]:box[0] + box[2]] < 128
        ))
        source_ink = int(np.count_nonzero(crop[my:my + mh, mx:mx + mw] < 128))
        assert rotated_ink == source_ink, (
            f"{orientation.label}: mapped box covers {source_ink} ink pixels but "
            f"the rotated box covered {rotated_ink}"
        )


def test_compose_to_original_adds_the_crop_offset():
    """
    The final hop: unrotated crop coordinates -> original image coordinates.
    Getting the offset wrong moves a correct reading onto a different surface.
    """
    src_h, src_w = 40, 90
    box = (10, 6, 12, 5)
    offset = (137, 402)
    for orientation in ALL_ORIENTATIONS:
        local = ori.map_bbox_from_rotated(box, orientation, (src_h, src_w))
        composed = ori.compose_to_original(box, orientation, (src_h, src_w), offset)
        assert composed == (
            local[0] + offset[0],
            local[1] + offset[1],
            local[2],
            local[3],
        )


def test_mapping_preserves_box_dimensions_under_axis_swap():
    """Width and height swap for 90/270 and are preserved for 0/180."""
    box = (4, 9, 13, 6)
    shape = (50, 70)
    for orientation in ALL_ORIENTATIONS:
        _x, _y, w, h = ori.map_bbox_from_rotated(box, orientation, shape)
        if orientation in (ori.Orientation.DEG_90, ori.Orientation.DEG_270):
            assert (w, h) == (box[3], box[2])
        else:
            assert (w, h) == (box[2], box[3])


# ---------------------------------------------------------------------------
# BEHAVIOURAL
# ---------------------------------------------------------------------------


def test_horizontal_synthetic_text_is_measured_as_horizontal():
    axis, h_score, v_score, conf = ori.estimate_text_axis(_horizontal_text())
    assert axis is ori.TextAxis.HORIZONTAL, (
        f"h={h_score:.3f} v={v_score:.3f} conf={conf:.3f}"
    )
    assert h_score > v_score


def test_vertical_synthetic_text_is_measured_as_vertical():
    axis, h_score, v_score, conf = ori.estimate_text_axis(_vertical_text())
    assert axis is ori.TextAxis.VERTICAL, (
        f"h={h_score:.3f} v={v_score:.3f} conf={conf:.3f}"
    )
    assert v_score > h_score


def test_the_two_axes_are_separated_by_more_than_the_decision_margin():
    """
    The margin is the whole basis of the AMBIGUOUS/decided split, so the
    measured separation on identical ink in two layouts is asserted rather than
    assumed.
    """
    _a, h_h, h_v, _c = ori.estimate_text_axis(_horizontal_text())
    _b, v_h, v_v, _d = ori.estimate_text_axis(_vertical_text())
    horizontal_margin = abs(h_h - h_v) / max(h_h, h_v, 1e-6)
    vertical_margin = abs(v_h - v_v) / max(v_h, v_v, 1e-6)
    assert horizontal_margin > ori.AXIS_DECISION_MARGIN
    assert vertical_margin > ori.AXIS_DECISION_MARGIN


def test_vertical_axis_prefers_a_clockwise_correction_first():
    """
    Side declarations on Indian retail packaging most often read bottom-to-top,
    which a clockwise 90 fixes. 270 must still be offered immediately after.
    """
    estimate = ori.estimate_region_orientation(_vertical_text())
    assert estimate.primary is ori.Orientation.DEG_90
    assert estimate.candidates[1] is ori.Orientation.DEG_270


def test_horizontal_axis_prefers_upright_first():
    estimate = ori.estimate_region_orientation(_horizontal_text())
    assert estimate.primary is ori.Orientation.DEG_0
    assert estimate.candidates[1] is ori.Orientation.DEG_180


def test_regions_too_small_to_carry_a_signal_are_ambiguous():
    tiny = np.full((ori.MIN_ORIENTABLE_SIDE_PX - 1, 40), 200, np.uint8)
    axis, _h, _v, conf = ori.estimate_text_axis(tiny)
    assert axis is ori.TextAxis.AMBIGUOUS
    assert conf == 0.0


def test_colour_and_grayscale_crops_agree():
    """A BGR crop and its grayscale equivalent must not disagree about the axis."""
    gray = _horizontal_text()
    colour = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    assert ori.estimate_text_axis(gray)[0] is ori.estimate_text_axis(colour)[0]


def test_inverted_polarity_text_is_still_oriented():
    """
    Light text on a dark label is extremely common. The ink mask normalises
    polarity, so the axis must survive inversion.
    """
    normal = _horizontal_text()
    inverted = cv2.bitwise_not(normal)
    assert ori.estimate_text_axis(inverted)[0] is ori.estimate_text_axis(normal)[0]


def test_candidate_limit_is_respected_and_clamped():
    crop = _horizontal_text()
    assert len(ori.estimate_region_orientation(crop, max_candidates=1).candidates) == 1
    assert len(ori.estimate_region_orientation(crop, max_candidates=2).candidates) == 2
    # Out-of-range values are clamped rather than raising or returning nothing.
    assert ori.estimate_region_orientation(crop, max_candidates=99).candidates
    assert ori.estimate_region_orientation(crop, max_candidates=0).candidates


def test_empty_crop_is_rejected_rather_than_silently_handled():
    with pytest.raises(ValueError):
        ori.rotate_crop(np.zeros((0, 0), np.uint8), ori.Orientation.DEG_90)
    # Axis estimation on an empty array answers AMBIGUOUS rather than raising,
    # because the caller still needs a candidate list to attempt a read.
    assert ori.estimate_text_axis(np.zeros((0, 0), np.uint8))[0] is (
        ori.TextAxis.AMBIGUOUS
    )


def test_provenance_is_reproducible_and_json_friendly():
    import json

    estimate = ori.estimate_region_orientation(_vertical_text())
    prov = estimate.provenance()
    json.dumps(prov)  # must not raise
    assert prov["axis"] == ori.TextAxis.VERTICAL.value
    assert prov["candidates"] == [int(c.value) for c in estimate.candidates]
    assert ori.estimate_region_orientation(_vertical_text()).provenance() == prov


def test_orientation_labels_are_stable():
    """Provenance and notes quote these strings, so they are part of the contract."""
    assert [o.label for o in ALL_ORIENTATIONS] == [
        "0deg",
        "90deg",
        "180deg",
        "270deg",
    ]
