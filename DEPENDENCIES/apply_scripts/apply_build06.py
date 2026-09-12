from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent
RULE_ENGINE = ROOT / "backend" / "rule_engine.py"
RUNTIME = ROOT / "backend" / "regulatory" / "runtime.py"
VERSIONS = ROOT / "backend" / "regulatory" / "versions.py"
MODELS = ROOT / "backend" / "regulatory" / "models.py"

for required in (RULE_ENGINE, RUNTIME, VERSIONS, MODELS):
    if not required.exists():
        raise SystemExit(f"Build 06 requires Build 05 first: missing {required}")

actual_rule_engine_sha = hashlib.sha1(RULE_ENGINE.read_bytes()).hexdigest()
text = RULE_ENGINE.read_text(encoding="utf-8")

# Build 05 was verified on GitHub at one SHA, but the user's verified local
# checkout may legitimately have a different blob SHA because of a local
# correction/re-save. Do not use a brittle whole-file hash gate here. Instead
# require the exact structural anchors that this patch needs, and refuse to
# continue if those anchors are absent. This keeps the patch safe without
# rejecting a valid Build 05 checkout.
required_anchors = (
    "def run_inspection(",
    "rules = load_rules()",
    "dimensions_relevant: bool = False,",
    "best_before_applicable: bool = False,",
    "geometry: GeometryType = GeometryType.UNKNOWN,",
    "from unit_price import (",
)
missing = [anchor for anchor in required_anchors if anchor not in text]
if missing:
    raise SystemExit(
        "Refusing to patch rule_engine.py because required Build 05 structural "
        f"anchors are missing: {missing}. Current SHA: {actual_rule_engine_sha}. "
        "Use the matching Build 05 source before applying Build 06."
    )


import_marker = "from unit_price import (\n"
import_line = "from regulatory.runtime import apply_rule_versions, version_label\n"
if import_line not in text:
    if import_marker not in text:
        raise SystemExit("Could not find rule_engine unit_price import marker")
    text = text.replace(import_marker, import_line + "\n" + import_marker, 1)

old_sig = """    dimensions_relevant: bool = False,\n    best_before_applicable: bool = False,\n    geometry: GeometryType = GeometryType.UNKNOWN,\n) -> ProductInspection:\n"""
new_sig = """    dimensions_relevant: bool = False,\n    best_before_applicable: bool = False,\n    geometry: GeometryType = GeometryType.UNKNOWN,\n    inspection_date: Optional[Any] = None,\n    rule_versions: Optional[Iterable[Any]] = None,\n    regulatory_module: str = \"lmpc\",\n) -> ProductInspection:\n"""
if old_sig not in text:
    raise SystemExit("run_inspection signature marker not found")
text = text.replace(old_sig, new_sig, 1)

old_load = """    captures = captures or []\n    rules = load_rules()\n    facts: List[ExtractedFact] = []\n    findings: List[RuleFinding] = []\n"""
new_load = """    captures = captures or []\n    rules = load_rules()\n\n    # A dated inspection MUST resolve against the authoritative RuleVersion\n    # registry. Falling back to today's rules.json for a historical date would\n    # make an otherwise correct inspection legally time-travelling. Conversely,\n    # the legacy undated API path remains unchanged for existing callers.\n    selected_versions = {}\n    inspection_date_value = None\n    if inspection_date is not None:\n        if rule_versions is None:\n            from regulatory.versions import RuleVersionSelectionError\n            raise RuleVersionSelectionError(\n                \"A dated inspection requires an explicit RuleVersion registry; \"\n                \"the engine will not fall back to rules.json.\"\n            )\n        rules, selected_versions = apply_rule_versions(\n            rules,\n            rule_versions,\n            module=regulatory_module,\n            inspection_date=inspection_date,\n        )\n        from regulatory.runtime import coerce_inspection_date\n        inspection_date_value = coerce_inspection_date(inspection_date).isoformat()\n\n    applicable_rule_version = version_label(selected_versions)\n    facts: List[ExtractedFact] = []\n    findings: List[RuleFinding] = []\n"""
if old_load not in text:
    raise SystemExit("rules load marker not found")
text = text.replace(old_load, new_load, 1)

old_exempt = """            evidence_complete=bool(captures),\n            review_required=False,\n        )\n"""
new_exempt = """            evidence_complete=bool(captures),\n            review_required=False,\n            inspection_date=inspection_date_value,\n            applicable_rule_version=applicable_rule_version,\n        )\n"""
if old_exempt not in text:
    raise SystemExit("exemption ProductInspection marker not found")
text = text.replace(old_exempt, new_exempt, 1)

old_final = """        review_required=(\n            summary_data[\"review_required\"] > 0\n            or overall == FactStatus.UNCERTAIN\n        ),\n    )\n"""
new_final = """        review_required=(\n            summary_data[\"review_required\"] > 0\n            or overall == FactStatus.UNCERTAIN\n        ),\n        inspection_date=inspection_date_value,\n        applicable_rule_version=applicable_rule_version,\n    )\n"""
if old_final not in text:
    raise SystemExit("final ProductInspection marker not found")
text = text.replace(old_final, new_final, 1)

RULE_ENGINE.write_text(text, encoding="utf-8")
print("Build 06 applied: dated RuleVersion selection is integrated into run_inspection().")
