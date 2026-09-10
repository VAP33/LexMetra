"""Regulatory knowledge storage interfaces.

PostgreSQL is authoritative in production. In-memory storage is deliberately
limited to deterministic unit/integration tests and local indexing previews.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional

from regulatory.models import KnowledgeChunk


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
        for chunk in chunks:
            self._chunks[chunk.id] = chunk

    def list_chunks(self) -> List[KnowledgeChunk]:
        return list(self._chunks.values())

    def get(self, chunk_id: str) -> Optional[KnowledgeChunk]:
        return self._chunks.get(chunk_id)


class PostgresKnowledgeStore(KnowledgeStore):
    """Persist regulatory chunks in the project's PostgreSQL database."""

    def __init__(self, get_conn) -> None:
        self._get_conn = get_conn

    def upsert_chunks(self, chunks: Iterable[KnowledgeChunk]) -> None:
        rows = list(chunks)
        if not rows:
            return
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for c in rows:
                    cur.execute(
                        """
                        INSERT INTO regulatory_knowledge_chunks (
                            chunk_id, module, department, regulation, document_id,
                            document_version, rule_version, rule_id, effective_from,
                            effective_to, index_version, page, section, clause,
                            language, commodity, jurisdiction, text, source_url,
                            source_reference, metadata_json
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            module=EXCLUDED.module,
                            department=EXCLUDED.department,
                            regulation=EXCLUDED.regulation,
                            document_version=EXCLUDED.document_version,
                            rule_version=EXCLUDED.rule_version,
                            rule_id=EXCLUDED.rule_id,
                            effective_from=EXCLUDED.effective_from,
                            effective_to=EXCLUDED.effective_to,
                            index_version=EXCLUDED.index_version,
                            page=EXCLUDED.page,
                            section=EXCLUDED.section,
                            clause=EXCLUDED.clause,
                            language=EXCLUDED.language,
                            commodity=EXCLUDED.commodity,
                            jurisdiction=EXCLUDED.jurisdiction,
                            text=EXCLUDED.text,
                            source_url=EXCLUDED.source_url,
                            source_reference=EXCLUDED.source_reference,
                            metadata_json=EXCLUDED.metadata_json
                        """,
                        (
                            c.id, c.module, c.department, c.regulation, c.document_id,
                            c.document_version, c.rule_version, c.rule_id,
                            c.effective_from, c.effective_to, c.index_version, c.page,
                            c.section, c.clause, c.language, c.commodity, c.jurisdiction,
                            c.text, c.source_url, c.source_reference,
                            json.dumps(c.metadata, ensure_ascii=False),
                        ),
                    )

    def list_chunks(self) -> List[KnowledgeChunk]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT chunk_id,module,department,regulation,document_id,document_version,"
                    "rule_version,rule_id,effective_from,effective_to,index_version,page,section,clause,"
                    "language,commodity,jurisdiction,text,source_url,source_reference,metadata_json "
                    "FROM regulatory_knowledge_chunks"
                )
                rows = cur.fetchall()
        result = []
        for row in rows:
            metadata = row[-1] if isinstance(row[-1], dict) else json.loads(row[-1] or "{}")
            result.append(KnowledgeChunk(
                id=row[0], module=row[1], department=row[2], regulation=row[3], document_id=row[4],
                document_version=row[5], rule_version=row[6], rule_id=row[7], effective_from=row[8],
                effective_to=row[9], index_version=row[10], page=row[11], section=row[12], clause=row[13],
                language=row[14], commodity=row[15], jurisdiction=row[16], text=row[17],
                source_url=row[18], source_reference=row[19], metadata=metadata,
            ))
        return result

    def get(self, chunk_id: str) -> Optional[KnowledgeChunk]:
        return next((c for c in self.list_chunks() if c.id == chunk_id), None)
