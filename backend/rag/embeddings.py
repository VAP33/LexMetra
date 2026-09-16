"""Optional semantic embeddings for RAG-02.

BGE-M3 / sentence-transformers is the vision target. It is NOT a required
runtime dependency. When the extra is missing we use a deterministic hashing
trick ONLY so the hybrid fusion code can be unit-tested. That hash vector is
not a semantic embedding and must never be reported as BGE-M3.
"""
from __future__ import annotations

import hashlib
from typing import List, Sequence

VECTOR_SIZE = 64


def embedding_backend() -> str:
    try:
        import sentence_transformers  # noqa: F401

        return "sentence-transformers"
    except Exception:
        return "hash_fallback_not_semantic"


def hash_embed(text: str, *, size: int = VECTOR_SIZE) -> List[float]:
    digest = hashlib.sha256((text or "").encode("utf-8")).digest()
    # Expand deterministically.
    raw = digest
    while len(raw) < size:
        raw += hashlib.sha256(raw).digest()
    values = [((raw[i] / 255.0) * 2.0) - 1.0 for i in range(size)]
    norm = sum(v * v for v in values) ** 0.5 or 1.0
    return [v / norm for v in values]


def embed_text(text: str) -> List[float]:
    if embedding_backend() == "sentence-transformers":
        try:
            from sentence_transformers import SentenceTransformer

            model = _model()
            vector = model.encode([text], normalize_embeddings=True)[0]
            return [float(x) for x in vector]
        except Exception:
            pass
    return hash_embed(text)


_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        # Named vision target; load only if the extra is installed.
        try:
            _MODEL = SentenceTransformer("BAAI/bge-m3")
        except Exception:
            _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _MODEL


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = sum(float(a[i]) ** 2 for i in range(n)) ** 0.5
    nb = sum(float(b[i]) ** 2 for i in range(n)) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
