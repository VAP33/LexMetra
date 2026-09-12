from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "backend" / "main.py"
text = MAIN.read_text(encoding="utf-8")

old_import = "from vlm_verifier import verify_ambiguous_field, verify_ambiguous_field_gemini, recover_fields_from_image"
new_import = old_import + "\nfrom visual_recovery import merge_visual_candidates"
if "from visual_recovery import merge_visual_candidates" not in text:
    if old_import not in text:
        raise SystemExit("Expected vlm_verifier import not found.")
    text = text.replace(old_import, new_import, 1)

needle = """        classified = classify_fields(ocr_lines)
        surface_id = capture_session.new_surface_id()
        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)
        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)
"""

replacement = """        classified = classify_fields(ocr_lines)
        surface_id = capture_session.new_surface_id()
        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)

        # Visual recovery is evidence extraction only and runs before legal evaluation.
        if config.VLM_VERIFICATION_ENABLED:
            weak_fields = {
                k: v for k, v in classified.items()
                if k in {
                    "common_name", "net_quantity", "mrp", "mfg_date",
                    "expiry_date", "manufacturer_name", "packer_name",
                    "importer_name", "consumer_care", "country_of_origin",
                }
                and (not v.get("value") or float(v.get("confidence", 0.0) or 0.0) < 0.62)
            }
            if weak_fields:
                try:
                    visual_candidates = recover_fields_from_image(
                        pil_img, weak_fields, image_id=image_id, surface_id=surface_id
                    )
                    classified = merge_visual_candidates(classified, visual_candidates)
                except Exception:
                    pass

        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)
"""

marker = """        # ------------------------- Evidence retention -------------------------"""
pos = text.find(marker)
if pos < 0:
    raise SystemExit("Could not locate /scan evidence-retention block.")
before, after = text[:pos], text[pos:]
if needle not in after:
    raise SystemExit("Could not locate the /scan OCR merge seam.")
after = after.replace(needle, replacement, 1)
MAIN.write_text(before + after, encoding="utf-8")
print("Build 03 applied.")
