import json

from lexmetra_rules.cli import main
from tests.fixtures.pdf_builder import build_native_text_pdf


def _build_test_pdf(tmp_path):
    texts = [
        "1. Short title and commencement.—These rules come into force from 1 April 2011.",
        "2. Definitions.—In these rules certain terms are defined for clarity purposes.",
        "3. Exemption in respect of certain packages.—Nothing shall apply to small packs.",
    ]
    return build_native_text_pdf(tmp_path / "reg.pdf", texts)


def test_cli_runs_and_writes_output_file(tmp_path, capsys):
    pdf_path = _build_test_pdf(tmp_path)
    out_path = tmp_path / "out.json"
    exit_code = main([str(pdf_path), "--out", str(out_path), "--source", "Test Regulation"])
    assert exit_code == 0
    assert out_path.exists()

    data = json.loads(out_path.read_text())
    assert data["rule_count"] == 3
    assert data["source"] == "Test Regulation"
    assert "rules_json_preview" in data
    assert "amendment_draft" in data


def test_cli_supports_page_range_flags(tmp_path):
    pdf_path = _build_test_pdf(tmp_path)
    out_path = tmp_path / "out.json"
    exit_code = main([str(pdf_path), "--start", "1", "--end", "2", "--out", str(out_path)])
    assert exit_code == 0
    data = json.loads(out_path.read_text())
    assert data["page_range"] == [1, 2]
    assert data["rule_count"] == 2


def test_cli_uses_out_flag_not_output(tmp_path):
    """The brief is explicit: --out, not --output."""
    parser_help = _capture_help()
    assert "--out " in parser_help or "--out\n" in parser_help or "--out OUT" in parser_help
    assert "--output" not in parser_help


def _capture_help():
    from lexmetra_rules.cli import build_arg_parser
    return build_arg_parser().format_help()


def test_cli_errors_cleanly_on_missing_pdf(tmp_path, capsys):
    exit_code = main([str(tmp_path / "does_not_exist.pdf")])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_cli_format_flag_can_select_only_rules_json(tmp_path):
    pdf_path = _build_test_pdf(tmp_path)
    out_path = tmp_path / "out.json"
    main([str(pdf_path), "--out", str(out_path), "--format", "rules_json"])
    data = json.loads(out_path.read_text())
    assert "rules_json_preview" in data
    assert "amendment_draft" not in data


def test_cli_prints_to_stdout_when_no_out_given(tmp_path, capsys):
    pdf_path = _build_test_pdf(tmp_path)
    exit_code = main([str(pdf_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["rule_count"] == 3
