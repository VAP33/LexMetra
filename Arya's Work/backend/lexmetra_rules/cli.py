"""
CLI for Module 1.

Usage:
    python -m lexmetra_rules.cli regulation.pdf
    python -m lexmetra_rules.cli regulation.pdf --start 37 --end 50
    python -m lexmetra_rules.cli regulation.pdf --out extracted_rules.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import pdf_intake
from . import llm_assist
from .adapters import to_amendment_draft, to_rules_json_dict
from .config import MissingTesseractError
from .pipeline import run_pipeline


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lexmetra_rules.cli",
        description="Module 1: extract structured regulatory rules from a PDF.",
    )
    parser.add_argument("pdf", help="Path to the regulation PDF.")
    parser.add_argument("--start", type=int, default=None, help="First page to process (1-based, inclusive).")
    parser.add_argument("--end", type=int, default=None, help="Last page to process (1-based, inclusive).")
    parser.add_argument("--out", type=str, default=None, help="Write structured rules JSON to this path.")
    parser.add_argument("--source", type=str, default=None, help="Regulation/document name for provenance.")
    parser.add_argument("--version", type=str, default=None, help="Regulation version/year, if known.")
    parser.add_argument("--lang", type=str, default="eng", help="Tesseract language code(s), e.g. 'eng' or 'eng+osd'.")
    parser.add_argument("--dpi", type=int, default=300, help="Rendering DPI for OCR fallback pages.")
    parser.add_argument("--psm", type=int, default=6, help="Tesseract page segmentation mode.")
    parser.add_argument("--tesseract-cmd", type=str, default=None, help="Explicit path to the tesseract binary.")
    parser.add_argument("--force-ocr", action="store_true", help="OCR every page even if a native text layer exists.")
    parser.add_argument(
        "--no-ocr-preprocess", action="store_true",
        help="Disable deskew/denoise/contrast/adaptive-threshold preprocessing before OCR (on by default).",
    )
    parser.add_argument(
        "--llm-assist", action="store_true",
        help="Enable optional local Ollama semantic assist for low-confidence clauses only "
        "(off by default; degrades gracefully if Ollama is unreachable).",
    )
    parser.add_argument("--ollama-url", type=str, default=llm_assist.DEFAULT_OLLAMA_URL, help="Ollama base URL.")
    parser.add_argument("--ollama-model", type=str, default=llm_assist.DEFAULT_OLLAMA_MODEL, help="Ollama model name.")
    parser.add_argument(
        "--format", choices=["rules_json", "amendment_draft", "both"], default="both",
        help="Output shape(s) to write.",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        print(f"error: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    info = pdf_intake.get_pdf_info(pdf_path)
    source = args.source or pdf_path.stem
    document_id = pdf_path.stem

    start = args.start or 1
    end = args.end or info.page_count
    print(f"Document: {pdf_path.name} ({info.page_count} pages total)", file=sys.stderr)
    print(f"Processing pages {start}-{end}...", file=sys.stderr)

    try:
        result = run_pipeline(
            pdf_path,
            document_id=document_id,
            source=source,
            version=args.version,
            start=args.start,
            end=args.end,
            lang=args.lang,
            dpi=args.dpi,
            psm=args.psm,
            force_ocr=args.force_ocr,
            explicit_tesseract_cmd=args.tesseract_cmd,
            preprocess_ocr=not args.no_ocr_preprocess,
            use_llm_assist=args.llm_assist,
            ollama_base_url=args.ollama_url,
            ollama_model=args.ollama_model,
        )
    except MissingTesseractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    print(
        f"Detected {len(result.rules)} rule(s); "
        f"{result.rejected_count} candidate(s) rejected as non-rules.",
        file=sys.stderr,
    )
    needs_review = sum(1 for r in result.rules if r.review_status.value != "auto_accepted")
    if needs_review:
        print(f"{needs_review} rule(s) flagged for review.", file=sys.stderr)
    total_errors = sum(len(r.validation_errors) for r in result.rules)
    total_warnings = sum(len(r.validation_warnings) for r in result.rules)
    if total_errors or total_warnings:
        print(
            f"Validation: {total_errors} error(s), {total_warnings} warning(s) across all rules.",
            file=sys.stderr,
        )
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    output = {
        "document_id": result.document_id,
        "source": result.source,
        "page_range": result.page_range,
        "rule_count": len(result.rules),
        "rejected_candidate_count": result.rejected_count,
    }
    if args.format in ("rules_json", "both"):
        output["rules_json_preview"] = [to_rules_json_dict(r) for r in result.rules]
    if args.format in ("amendment_draft", "both"):
        output["amendment_draft"] = to_amendment_draft(result.rules, source_document_id=document_id)

    payload = json.dumps(output, indent=2, ensure_ascii=False)

    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"Wrote structured rules to {args.out}", file=sys.stderr)
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
