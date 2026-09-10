"""Hybrid sparse retrieval with strict legal metadata filtering.

The first production-safe implementation uses BM25 plus TF-IDF cosine as a
local lexical/dense proxy. The retriever is intentionally provider-neutral so a
real embedding provider (Gemini or a local embedding model) can be added without
changing legal filtering or citation semantics.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from regulatory.models import KnowledgeChunk, RegulatoryContext, RAGSource

TOKEN_RE = re.compile(r"[\w()/-]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [t.casefold() for t in TOKEN_RE.findall(text)]


@dataclass(frozen=True)
class RetrievalHit:
    chunk: KnowledgeChunk
    score: float
    method: str


class HybridRetriever:
    def __init__(self, chunks: Iterable[KnowledgeChunk]) -> None:
        self.chunks = list(chunks)
        self._bm25_docs = [tokenize(c.text) for c in self.chunks]
        self._tfidf = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False)
        self._matrix = self._tfidf.fit_transform([c.text for c in self.chunks]) if self.chunks else None

        df = Counter()
        for doc in self._bm25_docs:
            df.update(set(doc))
        self._df = df
        self._avgdl = sum(len(d) for d in self._bm25_docs) / max(len(self._bm25_docs), 1)

    def _eligible(self, context: RegulatoryContext, chunk: KnowledgeChunk) -> bool:
        if chunk.module not in set(context.regulatory_modules or [chunk.module]):
            return False
        if context.department and chunk.department.casefold() != context.department.casefold():
            return False
        if context.jurisdiction and chunk.jurisdiction.casefold() != context.jurisdiction.casefold():
            return False
        if chunk.effective_from > context.inspection_date:
            return False
        if chunk.effective_to is not None and context.inspection_date >= chunk.effective_to:
            return False
        if context.commodity_type and chunk.commodity:
            if chunk.commodity.casefold() != context.commodity_type.casefold():
                return False
        return True

    def _bm25_score(self, query_tokens: list[str], index: int) -> float:
        doc = self._bm25_docs[index]
        if not doc:
            return 0.0
        counts = Counter(doc)
        k1, b = 1.5, 0.75
        n = len(self._bm25_docs)
        score = 0.0
        for term in query_tokens:
            if term not in counts:
                continue
            df = self._df.get(term, 0)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            tf = counts[term]
            denom = tf + k1 * (1 - b + b * len(doc) / max(self._avgdl, 1e-9))
            score += idf * ((tf * (k1 + 1)) / denom)
        return score

    def retrieve(self, query: str, context: RegulatoryContext, top_k: int = 8) -> List[RetrievalHit]:
        if not query.strip() or not self.chunks:
            return []
        q_tokens = tokenize(query)
        eligible_indices = [i for i, c in enumerate(self.chunks) if self._eligible(context, c)]
        if not eligible_indices:
            return []

        bm = {i: self._bm25_score(q_tokens, i) for i in eligible_indices}
        dense = {i: 0.0 for i in eligible_indices}
        if self._matrix is not None:
            qv = self._tfidf.transform([query])
            sims = cosine_similarity(qv, self._matrix)[0]
            dense = {i: float(sims[i]) for i in eligible_indices}

        def norm(values: dict[int, float]) -> dict[int, float]:
            if not values:
                return values
            mx = max(values.values())
            return {i: (v / mx if mx > 0 else 0.0) for i, v in values.items()}

        bm_n, dense_n = norm(bm), norm(dense)
        # Legal identifiers are exact anchors. If the query contains Rule 6,
        # Rule 6(11), etc., prefer chunks carrying that same rule identifier
        # over semantically similar neighbouring rules.
        query_rule = re.search(r"\brule\s+(\d+[a-z]?)(?:\s*\((\d+[a-z]?)\))?", query, re.I)
        requested_rule = None
        if query_rule:
            requested_rule = f"R{query_rule.group(1)}"
            if query_rule.group(2):
                requested_rule = f"{requested_rule}({query_rule.group(2)})"

        def final_score(i: int) -> float:
            score = 0.55 * bm_n[i] + 0.45 * dense_n[i]
            if requested_rule and self.chunks[i].rule_id:
                candidate = self.chunks[i].rule_id.casefold()
                wanted = requested_rule.casefold()
                if candidate == wanted:
                    score += 0.5
                elif candidate.startswith(wanted + "-"):
                    score += 0.25
            return score

        if requested_rule:
            exact = [i for i in eligible_indices if (self.chunks[i].rule_id or "").casefold() == requested_rule.casefold()]
            if exact:
                eligible_indices = exact

        ranked = sorted(eligible_indices, key=final_score, reverse=True)[:top_k]
        return [
            RetrievalHit(
                chunk=self.chunks[i],
                score=round(final_score(i), 6),
                method="hybrid_bm25_tfidf",
            )
            for i in ranked
        ]

    def to_sources(self, hits: Iterable[RetrievalHit]) -> List[RAGSource]:
        return [
            RAGSource(
                chunk_id=h.chunk.id,
                document_id=h.chunk.document_id,
                rule_id=h.chunk.rule_id,
                page=h.chunk.page,
                effective_from=h.chunk.effective_from,
                effective_to=h.chunk.effective_to,
                score=h.score,
                retrieval_method=h.method,
                source_reference=h.chunk.source_reference,
            )
            for h in hits
        ]
