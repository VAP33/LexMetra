from lexmetra_rules.pipeline import run_pipeline, run_pipeline_from_pages
from tests.fixtures.pdf_builder import build_native_text_pdf


def test_full_pipeline_on_synthetic_pages_end_to_end(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    assert len(result.rules) == 10
    assert result.rejected_count >= 1  # the '44.' / '2011.' decoys
    rule_ids = [r.rule_id for r in result.rules]
    assert rule_ids == [str(n) for n in range(1, 11)]


def test_pipeline_from_real_pdf_with_page_range(tmp_path):
    texts = [f"{i}. Rule number {i} text that is long enough to be a heading." for i in range(1, 6)]
    path = build_native_text_pdf(tmp_path / "reg.pdf", texts)

    result = run_pipeline(path, document_id="doc-x", source="Test PDF", start=2, end=4)
    assert result.page_range == [2, 4]
    assert {p.page_no for p in result.pages} == {2, 3, 4}
    assert {r.rule_id for r in result.rules} == {"2", "3", "4"}


def test_pipeline_does_not_render_full_document_for_small_range(tmp_path, monkeypatch):
    """Requesting pages 2-2 of a 5-page doc must only touch page 2."""
    import lexmetra_rules.pdf_intake as pdf_intake_module

    texts = [f"{i}. Rule number {i} text that is long enough to be a heading." for i in range(1, 6)]
    path = build_native_text_pdf(tmp_path / "reg.pdf", texts)

    touched_pages = []
    original_extract = pdf_intake_module.extract_native_text

    def spy_extract(doc, page_no):
        touched_pages.append(page_no)
        return original_extract(doc, page_no)

    monkeypatch.setattr(pdf_intake_module, "extract_native_text", spy_extract)

    run_pipeline(path, document_id="doc-x", source="Test PDF", start=2, end=2)
    assert touched_pages == [2]


def test_pipeline_reports_source_confidence_reflected_in_rules(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    for rule in result.rules:
        assert 0.0 <= rule.extraction_confidence <= 1.0


def test_pipeline_result_page_range_none_for_whole_document(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    assert result.page_range is None
