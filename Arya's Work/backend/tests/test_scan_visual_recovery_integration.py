from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def _scan_source():
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(text)

    scan = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "scan"
    )

    source = ast.get_source_segment(text, scan)
    assert source is not None
    return source


def test_scan_uses_visual_recovery_before_legal_evaluation():
    source = _scan_source()

    assert "recover_fields_from_image" in source
    assert "merge_visual_candidates" in source
    assert source.index("recover_fields_from_image") < source.index(
        "run_inspection("
    )


def test_scan_visual_recovery_is_not_just_extract_preview_code():
    text = (ROOT / "main.py").read_text(encoding="utf-8")

    scan_start = text.find('@app.post("/scan")')
    scan_end = text.find(
        "\n\n# ---------------------------------------------------------------------------\n"
        "# Multi-surface inspection sessions",
        scan_start,
    )

    assert scan_start >= 0
    assert scan_end >= 0

    scan = text[scan_start:scan_end]

    assert scan.count("recover_fields_from_image") == 1
    assert scan.count("merge_visual_candidates") == 1