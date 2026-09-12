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

scan_start = text.find('@app.post("/scan")')
if scan_start < 0:
    raise SystemExit("Could not locate /scan endpoint.")

scan_end = text.find("\n\n# ---------------------------------------------------------------------------\n# Multi-surface inspection sessions", scan_start)
if scan_end < 0:
    raise SystemExit("Could not locate end of /scan endpoint.")

scan = text[scan_start:scan_end]

needle = """        classified = classify_fields(ocr_lines)
        surface_id = capture_session.new_surface_id()
        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)
        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)
"""

if needle not in scan:
    raise SystemExit("Expected /scan OCR merge seam was not found.")

replacement = """        classified = classify_fields(ocr_lines)
        surface_id = capture_session.new_surface_id()
        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)

        # Recover weak/absent visual declarations before legal evaluation.
        # VLM output is evidence only: strong OCR is retained and conflicts
        # remain explicit for the deterministic rule engine/human reviewer.
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
                    # Provider failure must not break deterministic inspection.
                    pass

        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)
"""

scan2 = scan.replace(needle, replacement, 1)
text = text[:scan_start] + scan2 + text[scan_end:]
MAIN.write_text(text, encoding="utf-8")
print("Build 03 fixed applied to /scan.")
