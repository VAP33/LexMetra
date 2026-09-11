"""Structure-aware regulatory document ingestion."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import List, Optional

from regulatory.models import KnowledgeChunk

RULE_RE = re.compile(r"\bRule\s+(\d+[A-Za-z]?)(?:\s*\((\d+[A-Za-z]?)\))?", re.I)


def _chunk_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def _split_legal_text(text: str, max_chars: int = 1800):
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    for para in paragraphs:
        rule_match = RULE_RE.search(para)
        rule_id = None
        clause = None
        if rule_match:
            rule_id = f"R{rule_match.group(1)}"
            if rule_match.group(2):
                clause = f"{rule_id}({rule_match.group(2)})"
        if len(para) <= max_chars:
            chunks.append((para, rule_id, clause))
            continue
        words, buf, size = para.split(), [], 0
        for word in words:
            if size + len(word) + 1 > max_chars and buf:
                chunks.append((" ".join(buf), rule_id, clause))
                buf, size = [], 0
            buf.append(word)
            size += len(word) + 1
        if buf:
            chunks.append((" ".join(buf), rule_id, clause))
    return chunks


def extract_pdf_pages(path: Path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((index, text))
    return pages


def ingest_pdf(
    path: Path,
    *,
    module: str,
    department: str,
    regulation: str,
    document_id: str,
    document_version: str,
    effective_from: date,
    index_version: str,
    source_url: Optional[str] = None,
    language: str = "en",
) -> List[KnowledgeChunk]:
    chunks = []
    for page_no, text in extract_pdf_pages(path):
        for ordinal, (chunk_text, rule_id, clause) in enumerate(_split_legal_text(text)):
            cid = _chunk_id(document_id, document_version, str(page_no), str(ordinal), chunk_text)
            chunks.append(KnowledgeChunk(
                id=cid,
                module=module,
                department=department,
                regulation=regulation,
                document_id=document_id,
                document_version=document_version,
                rule_version=document_version,
                rule_id=rule_id,
                effective_from=effective_from,
                index_version=index_version,
                page=page_no,
                clause=clause,
                language=language,
                text=chunk_text,
                source_url=source_url,
                source_reference=f"{document_id}:page:{page_no}:chunk:{ordinal}",
            ))
    return chunks
