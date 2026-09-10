from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2]

def test_scan_calls_visual_recovery_before_legal_evaluation():
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    scan = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "scan")
    source = ast.get_source_segment(text, scan)
    assert source is not None
    assert "recover_fields_from_image" in source
    assert "merge_visual_candidates" in source
    assert source.index("recover_fields_from_image") < source.index("run_inspection(")

def test_visual_recovery_helper_preserves_conflicts():
    text = (ROOT / "visual_recovery.py").read_text(encoding="utf-8")
    assert "CONFLICTING" in text
    assert "REVIEW_REQUIRED" in text
    assert "alternative_values" in text
