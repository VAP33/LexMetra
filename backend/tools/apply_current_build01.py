"""Apply Build 01 safely to the current LexMetra checkout.

Refuses to patch if the expected current source shape is missing.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

HELPER = r'''def _recover_weak_fields_with_vlm(
    pil_img: Image.Image,
    classified: Dict[str, dict],
    *,
    image_id: str,
    surface_id: str,
) -> list[dict]:
    """Recover weak visual declarations from the actual image only."""
    if not config.VLM_VERIFICATION_ENABLED:
        return []
    weak_fields = {
        k: v for k, v in classified.items()
        if k in {
            "common_name", "net_quantity", "mrp", "mfg_date", "expiry_date",
            "manufacturer_name", "packer_name", "importer_name", "consumer_care",
            "country_of_origin",
        }
        and (not v.get("value") or float(v.get("confidence", 0.0) or 0.0) < 0.62)
    }
    if not weak_fields:
        return []
    candidates = recover_fields_from_image(
        pil_img, weak_fields, image_id=image_id, surface_id=surface_id
    )
    for candidate in candidates:
        field, value = candidate.get("field"), candidate.get("value")
        if not field or not value:
            continue
        existing = classified.get(field)
        if existing and existing.get("value"):
            if str(existing.get("value")).strip().casefold() != str(value).strip().casefold():
                existing.setdefault("alternative_values", []).append(str(value))
                existing["agreement"] = "CONFLICTING"
                existing["agreement_note"] = "OCR and visual VLM recovery disagree; human review required."
                existing["status"] = "REVIEW_REQUIRED"
                existing["review_required"] = True
            continue
        classified[field] = {
            **candidate,
            "source": "vlm_visual_recovery",
            "confidence": min(0.92, max(0.0, float(candidate.get("confidence", 0.0) or 0.0))),
        }
    return candidates

'''


def main() -> None:
    main_py = BACKEND / "main.py"
    text = main_py.read_text(encoding="utf-8")

    import_marker = "from report import build_inspection_report_pdf\n"
    if "from regulatory.router import router as regulatory_router" not in text:
        if import_marker not in text:
            raise RuntimeError("Main import marker not found. Refusing to patch.")
        text = text.replace(import_marker, import_marker + "from regulatory.router import router as regulatory_router\n", 1)

    if "app.include_router(regulatory_router)" not in text:
        cors_marker = "# CORS origins are read from configuration (ALLOWED_ORIGINS env var). Do not\n"
        if cors_marker not in text:
            raise RuntimeError("CORS marker not found. Refusing to patch.")
        text = text.replace(cors_marker, "app.include_router(regulatory_router)\n\n" + cors_marker, 1)

    if "def _recover_weak_fields_with_vlm(" not in text:
        marker = "# ---------------------------------------------------------------------------\n# Full scan endpoint\n# ---------------------------------------------------------------------------\n"
        if marker not in text:
            raise RuntimeError("Expected current /scan marker was not found. Refusing to patch.")
        text = text.replace(marker, HELPER + marker, 1)

    old_call = (
        '        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)\n'
        '        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)\n'
    )
    new_call = (
        '        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)\n'
        '        _recover_weak_fields_with_vlm(pil_img, classified, image_id=image_id, surface_id=surface_id)\n'
        '        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)\n'
    )
    if old_call not in text:
        raise RuntimeError("Expected current /scan evidence marker was not found. Refusing to patch.")
    text = text.replace(old_call, new_call, 1)

    old_calib = '''            calib = None

            if calib:
                circ_bbox = None
                if pkg_geom.shape in (schema.GeometryType.CYLINDRICAL, schema.GeometryType.NEAR_CYLINDRICAL) and pkg_geom.bbox:
                    circ_bbox = schema.BBox(x=0, y=0, width=max(1, int(math.pi * pkg_geom.bbox.width)), height=1)
                pdp_meas = calibration.measure_pdp_area(pdp_geom, pkg_geom.shape, calib, circumference_bbox=circ_bbox)
                if pdp_meas and pdp_meas.value is not None and pdp_meas.value > 0:
                    computed_pdp_area_cm2 = round(float(pdp_meas.value), 2)
'''
    new_calib = '''            # No calibration is inferred from an ordinary photograph.
            # Real-world scale requires an explicit, verified calibration workflow.
'''
    if old_calib not in text:
        raise RuntimeError("Expected current calibration block was not found. Refusing to patch.")
    text = text.replace(old_calib, new_calib, 1)
    main_py.write_text(text, encoding="utf-8")

    req = BACKEND / "requirements.txt"
    req_text = req.read_text(encoding="utf-8")
    if "scikit-learn>=" not in req_text:
        marker = "# Optional VLM Provider (Gemini)\ngoogle-generativeai>=0.8.0"
        if marker not in req_text:
            raise RuntimeError("Requirements marker not found.")
        req_text = req_text.replace(
            marker,
            "# Retrieval / regulatory document ingestion\nscikit-learn>=1.5,<2.0\npypdf>=5.0,<7.0\n\n" + marker,
            1,
        )
        req.write_text(req_text, encoding="utf-8")

    schema = BACKEND / "db" / "schema.sql"
    schema_text = schema.read_text(encoding="utf-8")
    if "-- Regulatory knowledge / amendment platform" not in schema_text:
        addon = BACKEND / "tools" / "regulatory_schema_addon.sql"
        schema.write_text(schema_text.rstrip() + "\n\n" + addon.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    print("Build 01 applied safely. Run the regression suite before committing.")


if __name__ == "__main__":
    main()
