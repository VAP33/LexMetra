"""
Unit tests for capture_session.py — no database required.
"""

import capture_session as cs
from schema import EvidenceStatus, ImageQuality


def _field(value, confidence=0.9):
    return {"value": value, "confidence": confidence}


def test_bridge_maps_manufacturer_name_to_combined_field():
    classified = {"manufacturer_name": _field("ACME Pvt Ltd, Pune")}
    bridged = cs.bridge_classified_fields(classified)
    assert "manufacturer_name_address" in bridged
    assert bridged["manufacturer_name_address"]["value"] == "ACME Pvt Ltd, Pune"


def test_bridge_maps_expiry_date_to_best_before():
    classified = {"expiry_date": _field("12/2026")}
    bridged = cs.bridge_classified_fields(classified)
    assert bridged["best_before_use_by"]["value"] == "12/2026"


def test_bridge_does_not_overwrite_existing_direct_field():
    classified = {
        "manufacturer_name": _field("wrong source"),
        "manufacturer_name_address": _field("correct direct value"),
    }
    bridged = cs.bridge_classified_fields(classified)
    assert bridged["manufacturer_name_address"]["value"] == "correct direct value"


def test_merge_keeps_higher_confidence_observation():
    accumulated = {"mrp": _field("MRP 45", confidence=0.4)}
    new = {"mrp": _field("MRP Rs 50", confidence=0.9)}
    merged = cs.merge_classified_fields(accumulated, new)
    assert merged["mrp"]["value"] == "MRP Rs 50"


def test_merge_does_not_downgrade_existing_good_reading():
    accumulated = {"mrp": _field("MRP Rs 50", confidence=0.9)}
    new = {"mrp": _field("blurry guess", confidence=0.2)}
    merged = cs.merge_classified_fields(accumulated, new)
    assert merged["mrp"]["value"] == "MRP Rs 50"


def test_compute_coverage_reflects_bridged_fields_not_raw_ocr_names():
    """
    Regression test: coverage must use the SAME field-name bridge as the
    final rule engine (manufacturer_name -> manufacturer_name_address),
    otherwise the capture UI would perpetually report a field as "missing"
    even though it has already been extracted under its OCR name.
    """
    merged_fields = {
        "manufacturer_name": _field("ACME Pvt Ltd, Pune", confidence=0.9),
        "common_name": _field("Refined Wheat Flour", confidence=0.9),
        "net_quantity": _field("100 g", confidence=0.9),
        "mrp": _field("Rs 50", confidence=0.9),
        "mfg_date": _field("08/2026", confidence=0.9),
        "consumer_care": _field("1800-000-000", confidence=0.9),
        "unit_sale_price": _field("Rs 50/100g", confidence=0.9),
    }
    context = {
        "is_imported": False,
        "best_before_applicable": False,  # household, not perishable
        "unit_price_rule_applies": True,
    }
    coverage, missing = cs.compute_coverage("retail", context, merged_fields)
    assert "manufacturer_name_address" not in missing
    assert coverage == 1.0


def test_guidance_reports_sufficient_when_coverage_high():
    quality = ImageQuality(status=EvidenceStatus.USABLE)
    messages = cs.guidance_messages(quality, 0.9, [])
    assert any("sufficient" in m.lower() for m in messages)


def test_guidance_suggests_specific_missing_fields():
    quality = ImageQuality(status=EvidenceStatus.USABLE)
    messages = cs.guidance_messages(quality, 0.3, ["mrp", "common_name"])
    joined = " ".join(messages).lower()
    assert "mrp" in joined or "maximum retail price" in joined


def test_parse_surface_type_unknown_falls_back():
    from schema import SurfaceType
    assert cs.parse_surface_type("front").name == "FRONT"
    assert cs.parse_surface_type("not-a-real-surface") == SurfaceType.UNKNOWN
    assert cs.parse_surface_type(None) == SurfaceType.UNKNOWN


# ---------------------------------------------------------------------------
# EVIDENCE INTEGRITY (P0-1): a finding must be traceable to its source image
# and to the region within that image.
#
# These pin the repair of a measured break in the chain. OCR produced bboxes in
# original-image coordinates, schema.py had somewhere to put them, and the
# database had an evidence_json column — but the function joining OCR output to
# the rule engine passed neither `bbox` nor `evidence`, so every fact the live
# API produced carried no region at all. Verified with
# backend/tools/probe_evidence_chain.py: 0 of 10 facts locatable before, 5 of 10
# after (the other 5 are declarations never observed, which correctly have no
# region to point at).
# ---------------------------------------------------------------------------

import rule_engine as _re
from schema import BBox, MeasurementMode, UNATTRIBUTED_IMAGE_ID


def _ocr_field(value, confidence=0.9, bbox=(120, 640, 300, 28), **extra):
    """Shaped like classify_fields() output: bbox is (x, y, w, h)."""
    data = {"value": value, "confidence": confidence, "bbox": bbox}
    data.update(extra)
    return data


def test_a_stamped_observation_becomes_locatable_evidence():
    classified = cs.stamp_provenance(
        {"mrp": _ocr_field("MRP Rs 50.00")},
        image_id="front_7f3a.jpg",
        surface_id="surf-1",
    )
    extraction = cs.build_raw_extraction("mrp", classified["mrp"])

    assert extraction.evidence, "evidence list must not be empty"
    ref = extraction.evidence[0]
    assert ref.image_id == "front_7f3a.jpg"
    assert ref.surface_id == "surf-1"
    assert ref.bbox == BBox(x=120, y=640, width=300, height=28)
    assert ref.is_locatable()


def test_the_bbox_actually_reaches_the_rule_engine_fact():
    """
    The specific regression. `bbox` was computed by OCR and then dropped one
    call before the rule engine, so ExtractedFact.bbox was always None.
    """
    classified = cs.stamp_provenance(
        {"mrp": _ocr_field("MRP Rs 50.00", numeric_value=50.0)},
        image_id="front_7f3a.jpg",
    )
    extractions = {
        "mrp": cs.build_raw_extraction("mrp", classified["mrp"]),
    }
    inspection = _re.run_inspection(
        inspection_id="t-1",
        product_category="food",
        sale_type="retail",
        net_quantity_value=100.0,
        net_quantity_unit="g",
        mrp=50.0,
        extractions=extractions,
    )

    mrp_facts = [f for f in inspection.facts if f.field == "mrp"]
    assert mrp_facts, "expected an mrp fact"
    fact = mrp_facts[0]

    assert fact.bbox is not None, "fact lost the OCR region"
    assert fact.evidence_image == "front_7f3a.jpg", "fact lost its source image"
    assert any(ref.is_locatable() for ref in fact.evidence)


def test_provenance_travels_with_the_observation_that_wins_the_merge():
    """
    In a multi-surface session the winning reading of one field may come from a
    different photograph than the winning reading of another. Attributing every
    finding to a single request-level image id would send a reviewer to a photo
    that does not contain the text — worse than no attribution at all.
    """
    front = cs.stamp_provenance(
        {
            "mrp": _ocr_field("MRP 45", confidence=0.35),
            "net_quantity": _ocr_field("Net Wt 100 g", confidence=0.92),
        },
        image_id="front.jpg",
        surface_id="surf-front",
    )
    back = cs.stamp_provenance(
        {
            "mrp": _ocr_field("MRP Rs 50.00", confidence=0.95),
            "net_quantity": _ocr_field("Net Wt 1OO g", confidence=0.40),
        },
        image_id="back.jpg",
        surface_id="surf-back",
    )

    merged = cs.merge_classified_fields(front, back)

    mrp_ref = cs.build_raw_extraction("mrp", merged["mrp"]).evidence[0]
    qty_ref = cs.build_raw_extraction(
        "net_quantity", merged["net_quantity"]
    ).evidence[0]

    assert mrp_ref.image_id == "back.jpg", "clearer MRP came from the back panel"
    assert qty_ref.image_id == "front.jpg", "clearer quantity came from the front"


def test_stamping_never_overwrites_provenance_already_recorded():
    already = {"mrp": _ocr_field("MRP Rs 50.00")}
    already["mrp"]["image_id"] = "original.jpg"

    stamped = cs.stamp_provenance(already, image_id="later.jpg")

    assert stamped["mrp"]["image_id"] == "original.jpg"


def test_an_unattributed_observation_is_not_given_a_plausible_filename():
    """
    The old code recorded image_id="unknown", which is indistinguishable from a
    photograph actually named unknown.jpg once it reaches a database row or a
    printed report. A break in the chain has to be conspicuous.
    """
    extraction = cs.build_raw_extraction("mrp", _ocr_field("MRP Rs 50.00"))

    ref = extraction.evidence[0]
    assert ref.image_id == UNATTRIBUTED_IMAGE_ID
    assert ref.image_id != "unknown"
    assert not ref.is_attributed()
    assert not ref.is_locatable(), "no source image means not reviewable"
    assert "provenance is incomplete" in ref.evidence_note.lower()


def test_an_unattributed_reference_is_never_promoted_to_the_fact_header():
    """
    ExtractedFact.evidence_image is what the report layer reads first. A
    sentinel copied up there would read as a real image name.
    """
    extractions = {
        "mrp": cs.build_raw_extraction("mrp", _ocr_field("MRP Rs 50.00", numeric_value=50.0)),
    }
    inspection = _re.run_inspection(
        inspection_id="t-2",
        product_category="food",
        sale_type="retail",
        net_quantity_value=100.0,
        net_quantity_unit="g",
        mrp=50.0,
        extractions=extractions,
    )
    for fact in inspection.facts:
        assert fact.evidence_image != UNATTRIBUTED_IMAGE_ID
        assert fact.evidence_image != "unknown"


def test_extractor_diagnostics_are_passed_through_untouched():
    """
    `_auxiliary_dates` is a list, not a dict. Assuming a shape here is how an
    earlier diagnostic tool crashed.
    """
    classified = {
        "mrp": _ocr_field("MRP Rs 50.00"),
        "_auxiliary_dates": ["04/2026", "18/08/2026"],
    }
    stamped = cs.stamp_provenance(classified, image_id="front.jpg")

    assert stamped["_auxiliary_dates"] == ["04/2026", "18/08/2026"]
    assert "image_id" not in str(stamped["_auxiliary_dates"])


def test_rich_ocr_text_is_not_reduced_to_a_bare_value():
    data = _ocr_field("MRP Rs 50.00 (incl. of all taxes)")
    data["normalized_value"] = "50.00"

    extraction = cs.build_raw_extraction("mrp", data)

    assert extraction.raw_text == "MRP Rs 50.00 (incl. of all taxes)"
    assert extraction.normalized_value == "50.00"


def test_a_client_supplied_verified_measurement_is_downgraded():
    """
    "A client-supplied VERIFIED measurement flag is not proof of verification."
    Without a validated calibration, VERIFIED must not survive this boundary.
    """
    data = _ocr_field("MRP Rs 50.00")
    data["measurement_mode"] = "VERIFIED"
    data["measured_height_mm"] = 1.2

    extraction = cs.build_raw_extraction("mrp", data)

    assert extraction.measurement_mode == MeasurementMode.ESTIMATED
    assert extraction.measured_height_mm == 1.2, "the measurement itself is kept"


def test_a_validated_calibration_permits_verified():
    """Non-vacuity guard for the downgrade above: it is not a blanket refusal."""
    data = _ocr_field("MRP Rs 50.00")
    data["measurement_mode"] = "VERIFIED"
    data["calibration"] = {"validated": True, "pixels_per_mm": 11.4}

    extraction = cs.build_raw_extraction("mrp", data)

    assert extraction.measurement_mode == MeasurementMode.VERIFIED


def test_an_unvalidated_calibration_does_not_permit_verified():
    data = _ocr_field("MRP Rs 50.00")
    data["measurement_mode"] = "VERIFIED"
    data["calibration"] = {"validated": False, "pixels_per_mm": 11.4}

    assert cs.build_raw_extraction("mrp", data).measurement_mode == (
        MeasurementMode.ESTIMATED
    )


def test_a_scale_factor_alone_does_not_permit_verified():
    """
    pixels_per_mm derived from an assumed reference size is exactly the kind of
    estimate that must not be promoted.
    """
    data = _ocr_field("MRP Rs 50.00")
    data["measurement_mode"] = "VERIFIED"
    data["calibration"] = {"pixels_per_mm": 11.4}

    assert cs.build_raw_extraction("mrp", data).measurement_mode == (
        MeasurementMode.ESTIMATED
    )


def test_a_degenerate_bbox_is_refused_rather_than_misread():
    """
    OCR emits (x, y, w, h). Corner-style (x0, y0, x1, y1) input would yield a
    negative or zero extent; a wrong rectangle is worse than none, because it
    points a reviewer at the wrong part of the label.
    """
    for bad in [(120, 640, 0, 28), (120, 640, 300, 0), (120, 640, -5, 28)]:
        extraction = cs.build_raw_extraction("mrp", _ocr_field("x", bbox=bad))
        assert extraction.bbox is None, f"{bad} should be refused"


def test_a_dict_bbox_is_accepted():
    data = _ocr_field("MRP Rs 50.00", bbox={"x": 1, "y": 2, "width": 3, "height": 4})
    extraction = cs.build_raw_extraction("mrp", data)
    assert extraction.bbox == BBox(x=1, y=2, width=3, height=4)


def test_an_observation_with_no_region_still_records_its_source_image():
    """
    A field read from a photograph but without usable geometry is still
    attributable to that photograph. Losing the image id too would discard
    provenance we actually have.
    """
    data = {"value": "MRP Rs 50.00", "confidence": 0.9}
    stamped = cs.stamp_provenance({"mrp": data}, image_id="front.jpg")

    extraction = cs.build_raw_extraction("mrp", stamped["mrp"])

    assert extraction.evidence
    ref = extraction.evidence[0]
    assert ref.image_id == "front.jpg"
    assert ref.bbox is None
    assert ref.is_attributed()
    assert not ref.is_locatable(), "attributed but not locatable without a region"
