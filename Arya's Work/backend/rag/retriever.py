"""Hybrid sparse retrieval with strict legal metadata filtering."""
from __future__ import annotations
import math, re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, List
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
        for doc in self._bm25_docs: df.update(set(doc))
        self._df = df
        self._avgdl = sum(map(len, self._bm25_docs)) / max(len(self._bm25_docs), 1)

    def _eligible(self, context, chunk):
        if chunk.module not in set(context.regulatory_modules or [chunk.module]): return False
        if context.department and chunk.department.casefold() != context.department.casefold(): return False
        if context.jurisdiction and chunk.jurisdiction.casefold() != context.jurisdiction.casefold(): return False
        # Published amendment chunks may carry an explicit publication state.
        # Scheduled/draft knowledge must never become runtime RAG evidence merely
        # because its effective date has arrived. Legacy bootstrap chunks omit
        # the field and remain eligible under their existing effective-date rules.
        publication_state = (chunk.metadata or {}).get("publication_state")
        if publication_state is not None and str(publication_state).upper() != "ACTIVE": return False
        if chunk.effective_from > context.inspection_date: return False
        if chunk.effective_to is not None and context.inspection_date >= chunk.effective_to: return False
        if context.commodity_type and chunk.commodity and chunk.commodity.casefold() != context.commodity_type.casefold(): return False
        return True

    def _bm25_score(self, q, i):
        doc = self._bm25_docs[i]
        counts = Counter(doc); k1,b,n=1.5,.75,len(self._bm25_docs)
        score=0.0
        for term in q:
            if term not in counts: continue
            df=self._df.get(term,0); idf=math.log(1+(n-df+0.5)/(df+0.5))
            tf=counts[term]; denom=tf+k1*(1-b+b*len(doc)/max(self._avgdl,1e-9))
            score += idf*((tf*(k1+1))/denom)
        return score

    def retrieve(self, query, context, top_k=8):
        if not query.strip() or not self.chunks: return []
        q=tokenize(query)
        eligible=[i for i,c in enumerate(self.chunks) if self._eligible(context,c)]
        if not eligible: return []
        bm={i:self._bm25_score(q,i) for i in eligible}
        dense={i:0.0 for i in eligible}
        if self._matrix is not None:
            sims=cosine_similarity(self._tfidf.transform([query]), self._matrix)[0]
            dense={i:float(sims[i]) for i in eligible}
        def norm(vals):
            mx=max(vals.values(), default=0.0)
            return {i:(v/mx if mx>0 else 0.0) for i,v in vals.items()}
        bm_n,dense_n=norm(bm),norm(dense)
        requested=None
        m=re.search(r"\brule\s+(\d+[a-z]?)(?:\s*\((\d+[a-z]?)\))?",query,re.I)
        if m:
            requested=f"R{m.group(1)}"
            if m.group(2): requested=f"{requested}({m.group(2)})"
        def score(i):
            s=.55*bm_n[i]+.45*dense_n[i]
            if requested and self.chunks[i].rule_id:
                c=self.chunks[i].rule_id.casefold()
                w=requested.casefold()
                if c==w: s+=.5
            return s
        if requested:
            exact=[i for i in eligible if (self.chunks[i].rule_id or "").casefold()==requested.casefold()]
            if exact: eligible=exact
        ranked=sorted(eligible,key=score,reverse=True)[:top_k]
        return [RetrievalHit(self.chunks[i],round(score(self.chunks[i] and i),6),"hybrid_bm25_tfidf") for i in ranked]

    def to_sources(self,hits):
        return [RAGSource(chunk_id=h.chunk.id,document_id=h.chunk.document_id,rule_id=h.chunk.rule_id,page=h.chunk.page,effective_from=h.chunk.effective_from,effective_to=h.chunk.effective_to,score=h.score,retrieval_method=h.method,source_reference=h.chunk.source_reference) for h in hits]
