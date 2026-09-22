"""RAG stores with immutable legal-chunk enforcement."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional

try:
    from ..regulatory.models import KnowledgeChunk
except ImportError:
    from regulatory.models import KnowledgeChunk

from .publication import validate_immutable_version, validate_unique_chunk_batch


class KnowledgeStore(ABC):
    @abstractmethod
    def upsert_chunks(self, chunks: Iterable[KnowledgeChunk]) -> None: ...

    @abstractmethod
    def list_chunks(self) -> List[KnowledgeChunk]: ...

    @abstractmethod
    def get(self, chunk_id: str) -> Optional[KnowledgeChunk]: ...


class InMemoryKnowledgeStore(KnowledgeStore):
    def __init__(self) -> None:
        self._chunks: dict[str, KnowledgeChunk] = {}

    def upsert_chunks(self, chunks: Iterable[KnowledgeChunk]) -> None:
        rows = list(chunks)
        validate_unique_chunk_batch(rows)
        for chunk in rows:
            validate_immutable_version(self._chunks.get(chunk.id), chunk)
        for chunk in rows:
            if chunk.id not in self._chunks:
                self._chunks[chunk.id] = chunk

    def list_chunks(self) -> List[KnowledgeChunk]:
        return list(self._chunks.values())

    def get(self, chunk_id: str) -> Optional[KnowledgeChunk]:
        return self._chunks.get(chunk_id)


class PostgresKnowledgeStore(KnowledgeStore):
    """Persist chunks without ever rewriting an existing legal chunk."""

    _SELECT = (
        "SELECT chunk_id,module,department,regulation,document_id,document_version,"
        "rule_version,rule_id,effective_from,effective_to,index_version,page,section,clause,"
        "language,commodity,jurisdiction,text,source_url,source_reference,metadata_json "
        "FROM regulatory_knowledge_chunks"
    )

    def __init__(self, get_conn) -> None:
        self._get_conn = get_conn

    @staticmethod
    def _hydrate(row) -> KnowledgeChunk:
        metadata = row[-1] if isinstance(row[-1], dict) else json.loads(row[-1] or "{}")
        return KnowledgeChunk(
            id=row[0], module=row[1], department=row[2], regulation=row[3], document_id=row[4],
            document_version=row[5], rule_version=row[6], rule_id=row[7], effective_from=row[8],
            effective_to=row[9], index_version=row[10], page=row[11], section=row[12], clause=row[13],
            language=row[14], commodity=row[15], jurisdiction=row[16], text=row[17],
            source_url=row[18], source_reference=row[19], metadata=metadata,
        )

    def upsert_chunks(self, chunks: Iterable[KnowledgeChunk]) -> None:
        rows = list(chunks)
        if not rows:
            return
        validate_unique_chunk_batch(rows)
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                existing: dict[str, KnowledgeChunk] = {}
                for chunk in rows:
                    cur.execute(self._SELECT + " WHERE chunk_id=%s", (chunk.id,))
                    row = cur.fetchone()
                    if row:
                        existing[chunk.id] = self._hydrate(row)
                for chunk in rows:
                    validate_immutable_version(existing.get(chunk.id), chunk)
                for chunk in rows:
                    if chunk.id in existing:
                        continue
                    cur.execute(
                        """INSERT INTO regulatory_knowledge_chunks (
                            chunk_id,module,department,regulation,document_id,document_version,
                            rule_version,rule_id,effective_from,effective_to,index_version,page,section,
                            clause,language,commodity,jurisdiction,text,source_url,source_reference,metadata_json
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (chunk_id) DO NOTHING""",
                        (
                            chunk.id, chunk.module, chunk.department, chunk.regulation, chunk.document_id,
                            chunk.document_version, chunk.rule_version, chunk.rule_id, chunk.effective_from,
                            chunk.effective_to, chunk.index_version, chunk.page, chunk.section, chunk.clause,
                            chunk.language, chunk.commodity, chunk.jurisdiction, chunk.text, chunk.source_url,
                            chunk.source_reference, json.dumps(chunk.metadata, ensure_ascii=False),
                        ),
                    )

    def list_chunks(self) -> List[KnowledgeChunk]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(self._SELECT)
                rows = cur.fetchall()
        return [self._hydrate(row) for row in rows]

    def get(self, chunk_id: str) -> Optional[KnowledgeChunk]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(self._SELECT + " WHERE chunk_id=%s", (chunk_id,))
                row = cur.fetchone()
        return self._hydrate(row) if row else None
