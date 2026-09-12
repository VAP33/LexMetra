from pathlib import Path

ROOT = Path(__file__).resolve().parent
main = ROOT / "backend" / "main.py"
s = main.read_text(encoding="utf-8")
start = s.index('@app.post("/scan")')
end = s.index('# 1. Barcode decoding across uploaded surfaces', start)
section = s[start:end]

old_import = 'from vlm_verifier import verify_ambiguous_field, verify_ambiguous_field_gemini, recover_fields_from_image\n'
new_import = old_import + 'from visual_recovery import merge_visual_candidates\n'
if old_import in s and 'from visual_recovery import merge_visual_candidates' not in s:
    s = s.replace(old_import, new_import, 1)
    section = s[s.index('@app.post("/scan")'):s.index('# 1. Barcode decoding across uploaded surfaces', s.index('@app.post("/scan")'))]

needle = '''        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)\n        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)\n'''
replacement = '''        classified = capture_session.stamp_provenance(classified, image_id=image_id, surface_id=surface_id)\n\n        # Build 02: visual recovery is evidence extraction only. It runs before\n        # legal evaluation, fills genuinely weak fields, and preserves any\n        # OCR/VLM disagreement as explicit conflicting evidence for review.\n        if config.VLM_VERIFICATION_ENABLED:\n            weak_fields = {\n                k: v for k, v in classified.items()\n                if k in {\n                    "common_name", "net_quantity", "mrp", "mfg_date",\n                    "expiry_date", "manufacturer_name", "packer_name",\n                    "importer_name", "consumer_care", "country_of_origin",\n                }\n                and (not v.get("value") or float(v.get("confidence", 0.0) or 0.0) < 0.62)\n            }\n            if weak_fields:\n                try:\n                    visual_candidates = recover_fields_from_image(\n                        pil_img, weak_fields, image_id=image_id, surface_id=surface_id\n                    )\n                    classified = merge_visual_candidates(classified, visual_candidates)\n                except Exception:\n                    # Visual recovery is advisory evidence. OCR/CV and the\n                    # deterministic rule engine remain fully functional if the\n                    # model is unavailable, times out, or returns bad JSON.\n                    pass\n\n        accumulated_fields = capture_session.merge_classified_fields(accumulated_fields, classified)\n'''
if section.count(needle) != 1:
    raise SystemExit(f"Expected exactly one /scan insertion point, found {section.count(needle)}")
section = section.replace(needle, replacement, 1)
s = s[:s.index('@app.post("/scan")')] + section + s[s.index('# 1. Barcode decoding across uploaded surfaces', start):]
main.write_text(s, encoding="utf-8")
print("Build 02 patch applied to backend/main.py")
