from datetime import date

from rag.default_corpus import build_default_chunks
from rag.embeddings import cosine, embed_text, embedding_backend, hash_embed
from rag.legal_sources import provenance_for_rule
from rag.retriever import HybridRetriever, reciprocal_rank_fusion
from regulatory.models import KnowledgeChunk, RegulatoryContext


def test_bootstrap_chunks_are_marked_unsourced():
    chunks = build_default_chunks()
    assert chunks
    assert all(c.metadata.get("sourced") is False for c in chunks)
    assert all(c.metadata.get("placeholder") is True for c in chunks)
    prov = provenance_for_rule("LMPC-2011-R3-SCOPE")
    assert prov["sourced"] is False
    assert prov["intended_urls"]


def test_rrf_and_hash_embed_are_deterministic():
    assert embedding_backend() in {"hash_fallback_not_semantic", "sentence-transformers"}
    a = hash_embed("numeral height under 200g")
    b = hash_embed("numeral height under 200g")
    assert a == b
    assert cosine(a, a) > 0.99
    fused = reciprocal_rank_fusion([["x", "y"], ["y", "x"]])
    assert fused["x"] > 0 and fused["y"] > 0


def test_retrieve_with_vectors_keeps_bm25():
    chunks = [
        KnowledgeChunk(
            id="c1", module="LMPC", department="DCA", regulation="LMPC",
            document_id="d", document_version="v1", rule_version="v1", rule_id="R7",
            effective_from=date(2011, 4, 1), index_version="i",
            language="en", jurisdiction="IN",
            text="The height of the principal display panel numerals shall not be less than the specified millimetres for a package under 200 g.",
            source_reference="rules.json:R7",
            metadata={"sourced": False},
        )
    ]
    context = RegulatoryContext(inspection_date=date(2025, 1, 1), regulatory_modules=["LMPC"], jurisdiction="IN")
    retriever = HybridRetriever(chunks)
    lexical = retriever.retrieve("minimum numeral height for a package under 200g", context)
    hybrid = retriever.retrieve_with_vectors(
        "minimum numeral height for a package under 200g",
        context,
        vectors={"c1": embed_text(chunks[0].text)},
    )
    assert lexical
    assert hybrid
    assert hybrid[0].method.endswith("semantic") or "bm25" in hybrid[0].method
