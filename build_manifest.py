"""One-shot script to write PROJECT_MANIFEST.json. Delete after running."""
import json

manifest = {
  "_meta": {
    "manifest_version": "2.0",
    "project": "SIH 2026 - PS 26034 - Legal Metrology Packaged Commodities Compliance Platform",
    "audit_date": "2026-09-06",
    "audit_pass": "Post-Session-1",
    "auditor": "Kiro - read-only audit, no project files modified",
    "overall_readiness_pct": 55,
    "readiness_label": "Alpha / Working Prototype",
    "previous_readiness_pct": 35,
    "delta_from_previous": "+20 percentage points",
    "session_1_summary": (
      "Auth/RBAC (inspector/reviewer/admin), audit trail, PDF reports (ReportLab), "
      "Rule 24 wholesale evaluator, multi-surface session API, evidence image retention, "
      "VLM wired and gated, best_before/is_imported inference fixed, field-name bridge "
      "centralized, 34 tests passing, Docker files present (unverified). "
      "Dashboard broken against secured backend - P0 demo blocker."
    )
  },

  "repository_tree": {
    "root": "c:/Users/HP/SIH 2026",
    "new_files_session_1": [
      "backend/auth.py",
      "backend/capture_session.py",
      "backend/config.py",
      "backend/image_quality.py",
      "backend/report.py",
      "backend/Dockerfile",
      "backend/.env.example",
      "backend/tests/conftest.py",
      "backend/tests/test_api_integration.py",
      "backend/tests/test_auth.py",
      "backend/tests/test_capture_session.py",
      "backend/tests/test_exemption.py",
      "backend/tests/test_rule_engine.py",
      "docker-compose.yml",
      ".dockerignore",
      "IMPLEMENTATION_STATUS.md"
    ],
    "modified_files_session_1": [
      "backend/main.py",
      "backend/rule_engine.py",
      "backend/db/schema.sql",
      "backend/db/persistence.py",
      "backend/requirements.txt",
      "backend/vlm_verifier.py"
    ],
    "unchanged_files": [
      "backend/schema.py",
      "backend/ocr_extraction.py",
      "backend/sticker_detection.py",
      "backend/product_similarity.py",
      "backend/unit_price.py",
      "backend/exemption.py",
      "frontend/dashboard.html",
      "frontend/capture.html",
      "rules/rules.json",
      "dataset/generate_dataset.py",
      "dataset/images/",
      "dataset/annotations/annotations.json"
    ],
    "files": [
      {"path": ".dockerignore",                         "type": "config",           "in_git": True},
      {"path": ".gitignore",                            "type": "config",           "in_git": True},
      {"path": "CLAUDE MASTERPROMPT.txt",               "type": "non_source",       "in_git": True,  "note": "AI architect prompt - should be gitignored or moved to docs/"},
      {"path": "docker-compose.yml",                    "type": "config",           "in_git": True,  "session": "NEW Session 1", "note": "backend + Postgres 16, unverified"},
      {"path": "ENGINE_UPGRADE_NOTES.md",               "type": "docs",             "in_git": True},
      {"path": "IMPLEMENTATION_STATUS.md",              "type": "docs",             "in_git": True,  "session": "NEW Session 1"},
      {"path": "PROJECT_MANIFEST.json",                 "type": "generated_audit",  "in_git": False},
      {"path": "PROJECT_STATE.md",                      "type": "generated_audit",  "in_git": False},
      {"path": "README.md",                             "type": "docs",             "in_git": True},
      {"path": "SETUP.md",                              "type": "docs",             "in_git": True},
      {"path": "backend/auth.py",                       "type": "source",           "in_git": True,  "session": "NEW Session 1", "note": "bcrypt+JWT+RBAC"},
      {"path": "backend/capture_session.py",            "type": "source",           "in_git": True,  "session": "NEW Session 1", "note": "multi-surface evidence merge, coverage, guidance"},
      {"path": "backend/config.py",                     "type": "source",           "in_git": True,  "session": "NEW Session 1", "note": "centralized env-var config"},
      {"path": "backend/Dockerfile",                    "type": "config",           "in_git": True,  "session": "NEW Session 1", "note": "python:3.12-slim + tesseract-ocr, UNVERIFIED"},
      {"path": "backend/.env.example",                  "type": "config",           "in_git": True,  "session": "NEW Session 1"},
      {"path": "backend/exemption.py",                  "type": "source",           "in_git": True},
      {"path": "backend/image_quality.py",              "type": "source",           "in_git": True,  "session": "NEW Session 1", "note": "classical CV quality assessment + PDP bbox estimate (heuristic)"},
      {"path": "backend/main.py",                       "type": "source",           "in_git": True,  "session": "MODIFIED Session 1", "note": "auth endpoints, sessions, PDF endpoint, VLM wired"},
      {"path": "backend/ocr_extraction.py",             "type": "source",           "in_git": True},
      {"path": "backend/product_similarity.py",         "type": "source",           "in_git": True},
      {"path": "backend/report.py",                     "type": "source",           "in_git": True,  "session": "NEW Session 1", "note": "ReportLab PDF generation"},
      {"path": "backend/requirements.txt",              "type": "config",           "in_git": True,  "session": "FIXED Session 1", "note": "pytesseract added; auth/test/PDF/dotenv deps added"},
      {"path": "backend/rule_engine.py",                "type": "source",           "in_git": True,  "session": "MODIFIED Session 1", "note": "Rule 24 evaluator, required_declaration_fields, best_before/is_imported params"},
      {"path": "backend/schema.py",                     "type": "source",           "in_git": True},
      {"path": "backend/sticker_detection.py",          "type": "source",           "in_git": True},
      {"path": "backend/unit_price.py",                 "type": "source",           "in_git": True},
      {"path": "backend/vlm_verifier.py",               "type": "source",           "in_git": True,  "session": "WIRED Session 1", "note": "now called from /scan pipeline, gated behind VLM_VERIFICATION_ENABLED"},
      {"path": "backend/product_index.json",            "type": "runtime_generated","in_git": False, "note": "flat JSON similarity index, empty on fresh clone"},
      {"path": "backend/uploads/",                      "type": "runtime_generated","in_git": False, "note": "NEW Session 1 - uploaded evidence images (gitignored)"},
      {"path": "backend/reports/",                      "type": "runtime_generated","in_git": False, "note": "NEW Session 1 - generated PDF reports (gitignored)"},
      {"path": "backend/db/__init__.py",                "type": "source",           "in_git": True,  "note": "empty package marker"},
      {"path": "backend/db/schema.sql",                 "type": "source",           "in_git": True,  "session": "MODIFIED Session 1", "note": "users, audit_log, inspection_sessions, session_captures added"},
      {"path": "backend/db/persistence.py",             "type": "source",           "in_git": True,  "session": "MODIFIED Session 1", "note": "user/auth CRUD, audit log, session CRUD, JSONB double-decode fix"},
      {"path": "backend/tests/conftest.py",             "type": "test",             "in_git": True,  "session": "NEW Session 1"},
      {"path": "backend/tests/test_api_integration.py", "type": "test",             "in_git": True,  "session": "NEW Session 1"},
      {"path": "backend/tests/test_auth.py",            "type": "test",             "in_git": True,  "session": "NEW Session 1"},
      {"path": "backend/tests/test_capture_session.py", "type": "test",             "in_git": True,  "session": "NEW Session 1"},
      {"path": "backend/tests/test_exemption.py",       "type": "test",             "in_git": True,  "session": "NEW Session 1"},
      {"path": "backend/tests/test_rule_engine.py",     "type": "test",             "in_git": True,  "session": "NEW Session 1"},
      {"path": "frontend/dashboard.html",               "type": "source",           "in_git": True,  "note": "UNCHANGED - BROKEN against secured backend (no auth header)"},
      {"path": "frontend/capture.html",                 "type": "source",           "in_git": True,  "note": "UNCHANGED - manual calibration tool, disconnected from session API"},
      {"path": "rules/rules.json",                      "type": "source",           "in_git": True,  "note": "UNCHANGED - 19 versioned LMPC rules"},
      {"path": "dataset/generate_dataset.py",           "type": "source",           "in_git": True},
      {"path": "dataset/images/",                       "type": "generated_assets", "in_git": True,  "count": 50, "note": "synthetic PNG images"},
      {"path": "dataset/annotations/annotations.json",  "type": "generated",        "in_git": True},
      {"path": "sample data/",                          "type": "real_assets",      "in_git": True,  "note": "2 JPG + 13 MP4 + 3 pickle PNG - NOT wired into pipeline"}
    ]
  },

  "modules": [
    {
      "name": "config", "path": "backend/config.py",
      "session": "NEW Session 1",
      "type": "configuration",
      "public_symbols": ["DATABASE_URL","JWT_SECRET_KEY","JWT_ALGORITHM","JWT_EXPIRE_MINUTES","DEV_MODE","ALLOWED_ORIGINS","UPLOAD_DIR","REPORT_DIR","ANTHROPIC_API_KEY","VLM_VERIFICATION_ENABLED"],
      "status": "working",
      "known_issues": ["DEV_MODE defaults to True - misconfigured prod uses insecure JWT secret silently"]
    },
    {
      "name": "auth", "path": "backend/auth.py",
      "session": "NEW Session 1",
      "type": "authentication_rbac",
      "roles": {"inspector": 0, "reviewer": 1, "admin": 2},
      "public_symbols": ["ROLE_HIERARCHY","TokenData","CurrentUser","hash_password","verify_password","create_access_token","decode_access_token","authenticate_user","get_current_user","require_role","require_inspector","require_reviewer","require_admin"],
      "status": "working",
      "known_issues": ["No token refresh endpoint","No token revocation","No rate limiting on /auth/login"]
    },
    {
      "name": "capture_session", "path": "backend/capture_session.py",
      "session": "NEW Session 1",
      "type": "multi_surface_orchestration",
      "public_symbols": ["bridge_classified_fields","merge_classified_fields","compute_coverage","guidance_messages","build_surface_observation","parse_surface_type","CaptureResult","EVIDENCE_SUFFICIENT_COVERAGE"],
      "field_bridge_aliases": {
        "manufacturer_name|packer_name|importer_name": "manufacturer_name_address",
        "expiry_date": "best_before_use_by",
        "net_quantity": "wholesale_count_or_net_quantity"
      },
      "status": "working",
      "known_issues": ["compute_coverage calls load_rules() disk read on every call","EVIDENCE_SUFFICIENT_COVERAGE=0.70 is empirical not legally defined"]
    },
    {
      "name": "image_quality", "path": "backend/image_quality.py",
      "session": "NEW Session 1",
      "type": "cv_heuristic",
      "public_symbols": ["assess_image_quality","estimate_pdp_bbox"],
      "metrics": ["blur_score (Laplacian variance)","exposure_score (midtone)","glare_score (highlight clipping)"],
      "status": "working_heuristic",
      "known_issues": ["All thresholds are empirical heuristics","estimate_pdp_bbox is informational only - never fed into font-height legal check"]
    },
    {
      "name": "report", "path": "backend/report.py",
      "session": "NEW Session 1",
      "type": "pdf_generator",
      "library": "reportlab (pure Python)",
      "public_symbols": ["build_inspection_report_pdf"],
      "status": "working",
      "known_issues": ["No surface thumbnails","No bbox overlays","No reviewer note in PDF","Finding reason truncated at 220 chars","No digital signature"]
    },
    {
      "name": "main", "path": "backend/main.py",
      "session": "MODIFIED Session 1",
      "type": "fastapi_entrypoint",
      "auth_added_to_all_endpoints": True,
      "new_endpoints": ["/auth/register","/auth/register/admin","/auth/login","/auth/me","/audit-log","/sessions","/sessions/{id}/captures","/sessions/{id}","/sessions/{id}/finalize","/inspections/{id}/report.pdf"],
      "status": "working",
      "known_issues": ["register() bootstrap ternary is inverted (behavior correct, reads backwards)","No IP address in audit events","GET /sessions/{id} O(n) recomputation","No token refresh"]
    },
    {
      "name": "rule_engine", "path": "backend/rule_engine.py",
      "session": "MODIFIED Session 1",
      "type": "legal_evaluator",
      "new_in_session_1": ["required_declaration_fields() public helper","_evaluate_rule24_wholesale_declarations()","_evaluate_declaration_rule() generalized","run_inspection() best_before_applicable + is_imported params"],
      "rules_evaluated": ["LMPC-2011-R3-SCOPE","LMPC-2011-R26-SMALL-PACKS","LMPC-2011-R6-DECLARATIONS","LMPC-2011-R6-11-UNIT-PRICE","LMPC-2011-R7-2-FONT","LMPC-2011-R8-PLACEMENT","LMPC-2011-R24-WHOLESALE"],
      "rules_not_evaluated": ["LMPC-2011-R4-MULTIPACK","LMPC-2011-R5-STANDARD-PACK","LMPC-2011-R6-10-ECOMMERCE","LMPC-2011-R7-PDP-AREA","LMPC-2011-R8-2-RETURNABLE-BOTTLE","LMPC-2011-R25-EXPORT","LMPC-2011-R26-B-FAST-FOOD","LMPC-2011-R26-C-DRUG-FORMULATIONS","LMPC-2011-R27-REGISTRATION","LMPC-2011-R31-ADVERTISEMENT","LMPC-2011-R32-PENALTY","LMPC-2011-SCHEDULE-II"],
      "status": "working_retail_and_wholesale",
      "known_issues": ["R4/R5/R25/R26b/R26c/R27/R31 have no evaluators","R7 font-width ratio not evaluated","10-20g partial relaxation not evaluated","_evaluate_placement() shallow"]
    },
    {
      "name": "exemption", "path": "backend/exemption.py",
      "session": "unchanged",
      "type": "scope_classifier",
      "public_symbols": ["ExemptionInput","ExemptionResult","classify_exemption"],
      "status": "working",
      "known_issues": ["R26b/R26c exemption paths not implemented","10-20g returns None with no downstream partial-requirement evaluator"]
    },
    {
      "name": "ocr_extraction", "path": "backend/ocr_extraction.py",
      "session": "unchanged",
      "type": "ocr_pipeline",
      "ocr_backend": "Tesseract (pretrained general)",
      "field_patterns_count": 13,
      "preprocessing_variants": ["RGB original","2x upscaled grayscale with autocontrast"],
      "psm_modes": [6, 11],
      "status": "working_with_caveats",
      "known_issues": ["No trained layout model - pure regex","Degrades on cramped/low-contrast labels","No multilingual support","No font-height measurement"]
    },
    {
      "name": "sticker_detection", "path": "backend/sticker_detection.py",
      "session": "unchanged",
      "type": "cv_heuristic",
      "status": "working_advisory_only",
      "known_issues": ["No trained model","False positives on packaging artwork edges"]
    },
    {
      "name": "product_similarity", "path": "backend/product_similarity.py",
      "session": "unchanged",
      "type": "visual_retrieval",
      "descriptor": "pHash (16x16) + HSV histogram (32x32 bins)",
      "index_file": "backend/product_index.json",
      "index_in_git": False,
      "status": "working",
      "known_issues": ["O(n) linear scan - not scalable beyond ~500 entries","index empty on fresh clone","Not a trained deep embedding - needs FAISS + CLIP"]
    },
    {
      "name": "vlm_verifier", "path": "backend/vlm_verifier.py",
      "session": "WIRED Session 1",
      "type": "vlm_secondary_checker",
      "provider": "Anthropic Claude",
      "model_default": "claude-sonnet-4-6",
      "pipeline_integration": "Called from main._apply_vlm_verification() for UNCERTAIN facts; gated behind VLM_VERIFICATION_ENABLED=true + ANTHROPIC_API_KEY",
      "status": "wired_gated_untested_live",
      "known_issues": ["Never tested against live API","Advisory only - never changes PASS/FAIL","Model name should be verified"]
    },
    {
      "name": "unit_price", "path": "backend/unit_price.py",
      "session": "unchanged",
      "type": "arithmetic_calculator",
      "arithmetic": "Decimal ROUND_HALF_UP",
      "quantity_families": ["weight g/kg","volume ml/l","length cm/m","number"],
      "status": "working",
      "known_issues": ["Area m2 unit family not implemented"]
    },
    {
      "name": "schema", "path": "backend/schema.py",
      "session": "unchanged",
      "type": "pydantic_contracts",
      "status": "working"
    },
    {
      "name": "db.persistence", "path": "backend/db/persistence.py",
      "session": "MODIFIED Session 1",
      "type": "database_layer",
      "new_functions_session_1": ["create_user","get_user_by_username","list_users","any_user_exists","record_audit_event","list_audit_log","set_inspection_attribution","create_session","get_session","add_session_capture","list_session_captures","finalize_session","truncate_all_data","list_sessions"],
      "bugs_fixed_session_1": ["JSONB double-decode bug - psycopg2 already decodes JSONB; calling json.loads() on the decoded object raised TypeError and silently reset evidence/coverage to None"],
      "status": "working",
      "known_issues": ["No connection pooling","product_id from colon-split breaks if product_id contains colon","audit_log.ip_address always NULL","Runtime column detection via information_schema adds latency"]
    }
  ],

  "endpoints": [
    {"method": "POST", "path": "/auth/register",               "role_required": None,        "auth": "none (bootstrap once)", "status": "implemented"},
    {"method": "POST", "path": "/auth/register/admin",         "role_required": "admin",     "auth": "Bearer JWT",            "status": "implemented"},
    {"method": "POST", "path": "/auth/login",                  "role_required": None,        "auth": "none",                  "status": "implemented", "request": "OAuth2 password form", "response": "access_token + role"},
    {"method": "GET",  "path": "/auth/me",                     "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented"},
    {"method": "GET",  "path": "/audit-log",                   "role_required": "admin",     "auth": "Bearer JWT",            "status": "implemented"},
    {"method": "POST", "path": "/scan",                        "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented_tested", "request": "multipart/form-data"},
    {"method": "POST", "path": "/inspect",                     "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented"},
    {"method": "POST", "path": "/analyze-image",               "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented"},
    {"method": "GET",  "path": "/inspections",                 "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented"},
    {"method": "GET",  "path": "/inspections/{id}",            "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented"},
    {"method": "POST", "path": "/inspections/{id}/review",     "role_required": "reviewer",  "auth": "Bearer JWT",            "status": "implemented"},
    {"method": "GET",  "path": "/inspections/{id}/report.pdf", "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented_tested", "response": "application/pdf"},
    {"method": "GET",  "path": "/products/{id}/history",       "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented"},
    {"method": "POST", "path": "/sessions",                    "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented_tested"},
    {"method": "POST", "path": "/sessions/{id}/captures",      "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented_tested", "request": "multipart/form-data + surface_type"},
    {"method": "GET",  "path": "/sessions/{id}",               "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented_tested"},
    {"method": "POST", "path": "/sessions/{id}/finalize",      "role_required": "inspector", "auth": "Bearer JWT",            "status": "implemented_tested", "errors": ["409 already finalized","400 zero captures"]},
    {"method": "GET",  "path": "/health",                      "role_required": None,        "auth": "none",                  "status": "implemented"}
  ],

  "database": {
    "technology": "PostgreSQL 16",
    "driver": "psycopg2-binary",
    "connection_env_var": "DATABASE_URL",
    "connection_pooling": False,
    "auto_init_on_startup": True,
    "migration_strategy": "idempotent CREATE TABLE IF NOT EXISTS + DO $$ ALTER TABLE IF NOT EXISTS $$",
    "total_tables": 7,
    "tables": [
      {"name": "users",                "pk": "user_id SERIAL",    "session": "NEW Session 1"},
      {"name": "products",             "pk": "product_id TEXT"},
      {"name": "inspections",          "pk": "inspection_id TEXT",  "new_columns_s1": ["image_path","created_by","reviewed_by"]},
      {"name": "inspection_facts",     "pk": "id SERIAL"},
      {"name": "audit_log",            "pk": "id SERIAL",           "session": "NEW Session 1", "note": "append-only"},
      {"name": "inspection_sessions",  "pk": "session_id TEXT",     "session": "NEW Session 1"},
      {"name": "session_captures",     "pk": "id SERIAL",           "session": "NEW Session 1"}
    ]
  },

  "legal_rules": [
    {"rule_id": "LMPC-2011-R3-SCOPE",               "clause": "Rule 3",         "evaluator": "exemption.classify_exemption",                         "status": "IMPLEMENTED",            "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R4-MULTIPACK",            "clause": "Rule 4",         "evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R5-STANDARD-PACK",        "clause": "Rule 5",         "evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R6-DECLARATIONS",         "clause": "Rule 6(1)",      "evaluator": "rule_engine._evaluate_declaration_rule",               "status": "IMPLEMENTED",            "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R6-10-ECOMMERCE",         "clause": "Rule 6(10)",     "evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R6-11-UNIT-PRICE",        "clause": "Rule 6(11)",     "evaluator": "rule_engine._evaluate_unit_sale_price",                "status": "IMPLEMENTED",            "verification": "verified_doca_faq_2022_amendment_audit_required"},
    {"rule_id": "LMPC-2011-R7-PDP-AREA",             "clause": "Rule 7(1)",      "evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "verified_available_text_amendment_audit_required"},
    {"rule_id": "LMPC-2011-R7-2-FONT",               "clause": "Rule 7(2)",      "evaluator": "rule_engine._evaluate_font_height",                    "status": "ALWAYS_UNCERTAIN",       "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R8-PLACEMENT",            "clause": "Rule 8(1)",      "evaluator": "rule_engine._evaluate_placement (shallow)",            "status": "SHALLOW",                "verification": "verified_available_text_amendment_audit_required"},
    {"rule_id": "LMPC-2011-R8-2-RETURNABLE-BOTTLE",  "clause": "Rule 8(2)",      "evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "verified_available_text_amendment_audit_required"},
    {"rule_id": "LMPC-2011-R24-WHOLESALE",           "clause": "Rule 24",        "evaluator": "rule_engine._evaluate_rule24_wholesale_declarations",  "status": "IMPLEMENTED_NEW_S1",     "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R25-EXPORT",              "clause": "Rule 25",        "evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R26-SMALL-PACKS",         "clause": "Rule 26(a)",     "evaluator": "exemption._rule26_small_pack_status",                  "status": "IMPLEMENTED",            "verification": "verified_2025_amendment_audit_required"},
    {"rule_id": "LMPC-2011-R26-B-FAST-FOOD",         "clause": "Rule 26(b)",     "evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R26-C-DRUG-FORMULATIONS", "clause": "Rule 26(c)",     "evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R27-REGISTRATION",        "clause": "Rule 27",        "evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R31-ADVERTISEMENT",       "clause": "Rule 31",        "evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-R32-PENALTY",             "clause": "Rule 32",        "evaluator": None,                                                   "status": "INFORMATIONAL_ONLY",     "verification": "needs_official_verification"},
    {"rule_id": "LMPC-2011-SCHEDULE-II",             "clause": "Second Schedule","evaluator": None,                                                   "status": "NO_EVALUATOR",           "verification": "needs_official_verification"}
  ],

  "ml_ai_features": [
    {"feature": "OCR text extraction",          "technology": "Tesseract pretrained general",  "status": "REAL",          "note": "Not fine-tuned for Indian labels"},
    {"feature": "OCR field classification",     "technology": "Regex heuristics",              "status": "REAL_HEURISTIC","note": "No ML"},
    {"feature": "Image quality assessment",     "technology": "Classical CV Laplacian+hist",   "status": "REAL_HEURISTIC","note": "Not calibrated against ground truth"},
    {"feature": "Sticker/alteration detection", "technology": "Classical CV Canny+gradient",   "status": "FALLBACK",      "note": "Advisory only, no trained model"},
    {"feature": "Product similarity retrieval", "technology": "pHash + HSV histogram",         "status": "FALLBACK",      "note": "Flat JSON index; not FAISS/CLIP"},
    {"feature": "VLM ambiguity verification",   "technology": "Anthropic Claude",              "status": "WIRED_UNTESTED","note": "Gated VLM_VERIFICATION_ENABLED; never tested live"},
    {"feature": "PDP bbox estimation",          "technology": "OCR text cluster heuristic",    "status": "HEURISTIC",     "note": "Informational only"},
    {"feature": "Font-height measurement",      "technology": "Manual capture.html",           "status": "MANUAL"},
    {"feature": "Trained layout detector",      "technology": None,                            "status": "MISSING"},
    {"feature": "Barcode/QR reading",           "technology": None,                            "status": "MISSING"},
    {"feature": "Multilingual OCR",             "technology": None,                            "status": "MISSING"},
    {"feature": "FSSAI cross-verification",     "technology": None,                            "status": "MISSING"}
  ],

  "test_suite": {
    "framework": "pytest",
    "total_tests": 34,
    "total_passed": 34,
    "total_failed": 0,
    "verified_live": True,
    "files": [
      {"file": "test_auth.py",            "type": "unit",        "requires_db": False, "covers": "bcrypt, JWT, role hierarchy"},
      {"file": "test_exemption.py",       "type": "unit",        "requires_db": False, "covers": "Rule 3, Rule 26a, export, industrial"},
      {"file": "test_rule_engine.py",     "type": "unit",        "requires_db": False, "covers": "Rule 6, Rule 24, UNCERTAIN invariant"},
      {"file": "test_capture_session.py", "type": "unit",        "requires_db": False, "covers": "merge, coverage, guidance"},
      {"file": "test_api_integration.py", "type": "integration", "requires_db": True,  "covers": "auth flow, /scan, /sessions, /report.pdf, RBAC"}
    ],
    "known_gaps": [
      "Session tests use same product twice, not genuine disjoint front/back",
      "No test for PDF content validation",
      "No test for VLM path",
      "No test for sticker detection or product similarity"
    ]
  },

  "dependencies": {
    "python_packages": [
      {"package": "fastapi",                   "version": ">=0.110,<1.0", "status": "ok"},
      {"package": "uvicorn[standard]",         "version": ">=0.29,<1.0",  "status": "ok"},
      {"package": "pydantic",                  "version": ">=2.6,<3.0",   "status": "ok"},
      {"package": "python-multipart",          "version": ">=0.0.9,<1.0", "status": "ok"},
      {"package": "opencv-python-headless",    "version": ">=4.9,<5.0",   "status": "ok"},
      {"package": "numpy",                     "version": ">=1.26,<3.0",  "status": "ok"},
      {"package": "Pillow",                    "version": ">=10.0,<12.0", "status": "ok"},
      {"package": "imagehash",                 "version": ">=4.3,<5.0",   "status": "ok"},
      {"package": "httpx",                     "version": ">=0.27,<1.0",  "status": "declared_unused_runtime"},
      {"package": "psycopg2-binary",           "version": ">=2.9,<3.0",   "status": "ok"},
      {"package": "python-dotenv",             "version": ">=1.0,<2.0",   "status": "ok", "session": "NEW S1"},
      {"package": "python-jose[cryptography]", "version": ">=3.3,<4.0",   "status": "ok", "session": "NEW S1"},
      {"package": "passlib[bcrypt]",           "version": ">=1.7,<2.0",   "status": "ok", "session": "NEW S1"},
      {"package": "bcrypt",                    "version": ">=4.0,<5.0",   "status": "ok", "session": "NEW S1"},
      {"package": "reportlab",                 "version": ">=4.0,<5.0",   "status": "ok", "session": "NEW S1"},
      {"package": "pytesseract",               "version": ">=0.3.10,<1.0","status": "ok", "session": "FIXED S1"},
      {"package": "pytest",                    "version": ">=8.0,<9.0",   "status": "ok", "session": "NEW S1"},
      {"package": "pytest-cov",               "version": ">=5.0,<6.0",   "status": "ok", "session": "NEW S1"},
      {"package": "anthropic",                 "version": ">=0.34,<1.0",  "status": "optional"}
    ],
    "external_runtime": [
      {"name": "Tesseract OCR binary", "documented_in": ["requirements.txt inline","SETUP.md","Dockerfile"]},
      {"name": "PostgreSQL 16",        "documented_in": ["SETUP.md","docker-compose.yml"]},
      {"name": "Python 3.12",          "documented_in": ["Dockerfile"], "note": "Not stated in requirements.txt"}
    ]
  },

  "environment_variables": [
    {"name": "DATABASE_URL",             "required": False, "default": "postgresql://lmpc_app:lmpc_dev_pw@localhost:5432/lmpc", "risk": "LOW dev fallback"},
    {"name": "JWT_SECRET_KEY",           "required": True,  "default": "dev-only-insecure-secret-change-me when DEV_MODE=true",  "risk": "HIGH - must be set in production"},
    {"name": "LMPC_DEV_MODE",            "required": False, "default": "true", "risk": "HIGH - defaults to insecure; must be false in production"},
    {"name": "ALLOWED_ORIGINS",          "required": False, "default": "localhost dev ports",  "risk": "MEDIUM - lock to deployed frontend URL"},
    {"name": "UPLOAD_DIR",               "required": False, "default": "backend/uploads",      "risk": "LOW - must be persistent volume in Docker"},
    {"name": "REPORT_DIR",               "required": False, "default": "backend/reports",      "risk": "LOW - must be persistent volume in Docker"},
    {"name": "ANTHROPIC_API_KEY",        "required": False, "default": "",     "risk": "LOW - VLM disabled if absent"},
    {"name": "VLM_VERIFICATION_ENABLED", "required": False, "default": "false","risk": "LOW"},
    {"name": "JWT_ALGORITHM",            "required": False, "default": "HS256","risk": "LOW"},
    {"name": "JWT_EXPIRE_MINUTES",       "required": False, "default": "480",  "risk": "LOW"},
    {"name": "LMPC_TEST_RESET_DB",       "required": False, "default": "true", "risk": "DANGER - truncates all data; test DB only"}
  ],

  "dataset": {
    "total_committed_images": 55,
    "synthetic_images": 50,
    "real_images": 5,
    "real_videos": 13,
    "real_assets_wired": False,
    "real_assets_location": "sample data/",
    "indian_product_coverage_in_synthetic": "None",
    "model_training_status": "No training; no scripts; no weights"
  },

  "known_issues": [
    {"id": "KI-001", "priority": "P0",  "title": "dashboard.html broken against secured backend",     "description": "All fetch() calls send no Authorization header. Every API call returns 401. Demo frontend completely non-functional.", "fix": "Add login screen + sessionStorage JWT + Authorization header. 2-3 hours."},
    {"id": "KI-002", "priority": "P0",  "title": "Docker build unverified",                           "description": "Dockerfile + docker-compose.yml written but docker compose up --build never executed.", "fix": "Run in Docker environment. 1 hour."},
    {"id": "KI-003", "priority": "P1",  "title": "LMPC_DEV_MODE defaults to true",                   "description": "config.py DEV_MODE default is True. Misconfigured prod uses insecure JWT secret.", "fix": "Change default to False. 1 line."},
    {"id": "KI-004", "priority": "P1",  "title": "register() bootstrap ternary inverted (cosmetic)",  "description": "role = req.role if db.any_user_exists() else admin - reads backwards but behavior is correct.", "fix": "Flip condition. 5 min."},
    {"id": "KI-005", "priority": "P1",  "title": "audit_log.ip_address always NULL",                  "description": "ip_address field exists but record_audit_event() called with ip_address=None everywhere.", "fix": "Pass request.client.host from FastAPI Request. 30 min."},
    {"id": "KI-006", "priority": "P1",  "title": "No mobile application",                             "description": "Zero Android/React Native/Kotlin code. Primary SIH requirement unmet.", "fix": "React Native guided-camera app."},
    {"id": "KI-007", "priority": "P1",  "title": "Rule 25 export evaluator missing",                  "description": "Export packages re-sold domestically not flagged.", "fix": "_evaluate_rule25_export() in rule_engine.py. 2 hours."},
    {"id": "KI-008", "priority": "P1",  "title": "No CSV/editable export",                            "description": "SIH requires export to editable formats. Only PDF exists.", "fix": "GET /inspections/export.csv. 2 hours."},
    {"id": "KI-009", "priority": "P1",  "title": "Real product photos not in pipeline",               "description": "5 real images + 13 videos in sample data/ not wired into pipeline.", "fix": "Move to dataset/real_samples/; run through /scan; annotate."},
    {"id": "KI-010", "priority": "P2",  "title": "Font-height check always UNCERTAIN",                "description": "No automatic pixel-to-mm path.", "fix": "Wire capture.html calibration into session API."},
    {"id": "KI-011", "priority": "P2",  "title": "Rules R4/R5/R26b/R26c/R27 have no evaluator",      "description": "5 rules in rules.json with no Python code.", "fix": "Implement evaluators."},
    {"id": "KI-012", "priority": "P2",  "title": "product_index.json empty on fresh clone",           "description": "Similarity index not in git.", "fix": "Seed with synthetic embeddings or document."},
    {"id": "KI-013", "priority": "P2",  "title": "O(n) product similarity scan",                     "description": "Not scalable beyond ~500 entries.", "fix": "FAISS IndexFlatL2. 3-4 hours."},
    {"id": "KI-014", "priority": "P2",  "title": "No connection pooling",                             "description": "New DB connect per request.", "fix": "psycopg2.pool.SimpleConnectionPool."},
    {"id": "KI-015", "priority": "P2",  "title": "GET /sessions/{id} O(n) recomputation",            "description": "Re-reads and merges all captures on every GET.", "fix": "Cache accumulated fields in sessions table."},
    {"id": "KI-016", "priority": "P3",  "title": "No trained OCR layout model",                      "description": "Tesseract+regex degrades on real Indian labels.", "fix": "Fine-tune LayoutLM/YOLO on real labeled photos."},
    {"id": "KI-017", "priority": "P3",  "title": "No mobile app (detailed)",                         "description": "No guided camera, offline capture, sync, or ARCore.", "fix": "React Native + Android camera + offline SQLite + sync."},
    {"id": "KI-018", "priority": "P3",  "title": "FSSAI cross-verification absent",                  "description": "Zero FSSAI module code.", "fix": "FSSAI sector compliance module as parallel findings."},
    {"id": "KI-019", "priority": "P3",  "title": "CLAUDE MASTERPROMPT.txt in repo root",             "description": "Non-source artifact committed to repo.", "fix": "Add to .gitignore or move to docs/."}
  ],

  "ownership_recommendations": [
    {"path": "rules/rules.json",                "workstream": "A - Legal/Compliance",        "action": "MODIFY"},
    {"path": "backend/rule_engine.py",          "workstream": "A - Legal/Compliance",        "action": "MODIFY"},
    {"path": "backend/exemption.py",            "workstream": "A - Legal/Compliance",        "action": "MODIFY"},
    {"path": "backend/unit_price.py",           "workstream": "A - Legal/Compliance",        "action": "MODIFY"},
    {"path": "backend/ocr_extraction.py",       "workstream": "B - OCR/Computer Vision",     "action": "MODIFY"},
    {"path": "backend/sticker_detection.py",    "workstream": "B+C - OCR/CV + ML",           "action": "KEEP_THEN_REWRITE"},
    {"path": "backend/image_quality.py",        "workstream": "B - OCR/Computer Vision",     "action": "MODIFY"},
    {"path": "backend/capture_session.py",      "workstream": "B+D - OCR/CV + Platform",    "action": "MODIFY"},
    {"path": "backend/product_similarity.py",   "workstream": "C - ML/Intelligence",         "action": "MODIFY"},
    {"path": "backend/vlm_verifier.py",         "workstream": "C - ML/Intelligence",         "action": "KEEP"},
    {"path": "backend/schema.py",               "workstream": "D - Platform",               "action": "KEEP"},
    {"path": "backend/main.py",                 "workstream": "D - Platform",               "action": "MODIFY"},
    {"path": "backend/auth.py",                 "workstream": "D - Platform",               "action": "MODIFY"},
    {"path": "backend/config.py",               "workstream": "D - Platform",               "action": "MODIFY", "note": "Change DEV_MODE default to False"},
    {"path": "backend/report.py",               "workstream": "D - Platform",               "action": "MODIFY"},
    {"path": "backend/db/schema.sql",           "workstream": "D - Platform",               "action": "MODIFY"},
    {"path": "backend/db/persistence.py",       "workstream": "D - Platform",               "action": "MODIFY"},
    {"path": "backend/db/__init__.py",          "workstream": "D - Platform",               "action": "KEEP"},
    {"path": "backend/requirements.txt",        "workstream": "D - Platform",               "action": "KEEP"},
    {"path": "backend/Dockerfile",              "workstream": "D - Platform",               "action": "KEEP"},
    {"path": "backend/.env.example",            "workstream": "D - Platform",               "action": "KEEP"},
    {"path": "docker-compose.yml",              "workstream": "D - Platform",               "action": "KEEP"},
    {"path": "frontend/dashboard.html",         "workstream": "D - Platform",               "action": "MODIFY", "note": "P0 - add auth/token logic immediately"},
    {"path": "frontend/capture.html",           "workstream": "D - Platform",               "action": "MODIFY"},
    {"path": "backend/tests/",                  "workstream": "D - Platform",               "action": "MODIFY"},
    {"path": "dataset/generate_dataset.py",     "workstream": "C - ML/Intelligence",        "action": "KEEP"},
    {"path": "dataset/images/",                 "workstream": "C - ML/Intelligence",        "action": "KEEP"},
    {"path": "dataset/annotations/",            "workstream": "C - ML/Intelligence",        "action": "KEEP"},
    {"path": "sample data/",                    "workstream": "C - ML/Intelligence",        "action": "MOVE", "note": "Move to dataset/real_samples/; wire into pipeline"},
    {"path": "README.md",                       "workstream": "D - Platform",               "action": "KEEP"},
    {"path": "SETUP.md",                        "workstream": "D - Platform",               "action": "MODIFY"},
    {"path": "IMPLEMENTATION_STATUS.md",        "workstream": "D - Platform",               "action": "KEEP"},
    {"path": ".gitignore",                      "workstream": "D - Platform",               "action": "MODIFY", "note": "Add CLAUDE MASTERPROMPT.txt"},
    {"path": "CLAUDE MASTERPROMPT.txt",         "workstream": "D - Platform",               "action": "DELETE_FROM_GIT"}
  ],

  "next_10_steps": [
    {"step": 1, "priority": "P0", "effort": "2-3h",     "title": "Fix dashboard.html - add auth header to all fetch() calls", "description": "Add login screen, store JWT in sessionStorage, attach Authorization: Bearer to all API calls. Demo blocker."},
    {"step": 2, "priority": "P0", "effort": "1h",       "title": "Verify Docker: docker compose up --build + curl /health"},
    {"step": 3, "priority": "P1", "effort": "5min",     "title": "Change LMPC_DEV_MODE default to False in config.py"},
    {"step": 4, "priority": "P1", "effort": "30min",    "title": "Populate audit_log.ip_address from request.client.host"},
    {"step": 5, "priority": "P1", "effort": "5min",     "title": "Fix register() bootstrap ternary: role = 'admin' if not db.any_user_exists() else req.role"},
    {"step": 6, "priority": "P1", "effort": "3-4h",     "title": "Build minimal guided-capture web client consuming /sessions/* API"},
    {"step": 7, "priority": "P1", "effort": "2h",       "title": "Implement Rule 25 export repack evaluator in rule_engine.py"},
    {"step": 8, "priority": "P1", "effort": "real-world","title": "Wire sample data/ real photos into pipeline; document results"},
    {"step": 9, "priority": "P1", "effort": "2h",       "title": "Add GET /inspections/export.csv (SIH requires editable export)"},
    {"step": 10,"priority": "P2", "effort": "3-4h",     "title": "Replace product_index.json flat scan with FAISS IndexFlatL2"}
  ]
}

with open(r"c:\Users\HP\SIH 2026\PROJECT_MANIFEST.json", "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

size = len(json.dumps(manifest, ensure_ascii=False))
print(f"written ok - {size} chars")
