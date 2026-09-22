"""
Product similarity and inspection-history matching.

This module performs visual nearest-neighbor retrieval for previously scanned
products. It is NOT RAG and it does not make legal-compliance decisions.

MVP design:
- deterministic, dependency-light visual descriptors;
- pHash for coarse structural similarity;
- HSV histogram for appearance similarity;
- flat JSON index for small demo datasets;
- explicit score semantics and conservative match thresholds.

Important:
A visual match is evidence that two images may represent the same product,
not proof of product identity. MRP changes are reported as a HISTORY FLAG only.
They must never become a legal FAIL verdict automatically.

Upgrade path:
Replace embed_image() with a pretrained visual embedding model such as a
CLIP-family encoder and replace the JSON scan with FAISS/vector search when
the dataset grows. Keep the public function signatures where practical.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import cv2
import imagehash
import numpy as np
from PIL import Image


INDEX_PATH = Path(__file__).parent / "product_index.json"

# Keep the MVP index deliberately small and transparent.
DEFAULT_TOP_K = 5
MAX_TOP_K = 50

# Scores below this are not useful enough to expose as "similar products".
# This is a retrieval threshold, not a product-identity probability.
DEFAULT_MIN_MATCH_SCORE = 0.55


@dataclass
class ProductEmbedding:
    product_id: str
    image_id: str
    phash: str
    hist: List[float]
    mrp: Optional[float] = None
    scanned_at: Optional[str] = None


@dataclass
class MatchResult:
    product_id: str
    image_id: str
    combined_score: float
    phash_score: float
    hist_score: float
    mrp: Optional[float]
    scanned_at: Optional[str]

    # Explicitly communicate that this is retrieval evidence, not identity.
    match_type: str = "VISUAL_CANDIDATE"


def _validate_image(image_bgr: np.ndarray) -> bool:
    return (
        isinstance(image_bgr, np.ndarray)
        and image_bgr.size > 0
        and image_bgr.ndim == 3
        and image_bgr.shape[2] in (3, 4)
        and image_bgr.shape[0] >= 16
        and image_bgr.shape[1] >= 16
    )


def _to_bgr(image: np.ndarray) -> np.ndarray:
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def _normalized_hsv_histogram(image_bgr: np.ndarray) -> List[float]:
    """
    Build a normalized hue/saturation histogram.

    Histogram similarity is used only as a secondary appearance signal.
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    # Mild blur reduces sensitivity to individual compression artifacts and
    # tiny text differences while preserving package-level appearance.
    hsv = cv2.GaussianBlur(hsv, (3, 3), 0)

    hist = cv2.calcHist(
        [hsv],
        [0, 1],
        None,
        [32, 32],
        [0, 180, 0, 256],
    )

    norm = cv2.normalize(hist, hist, alpha=1.0, beta=0.0, norm_type=cv2.NORM_L1)
    return norm.astype(np.float32).flatten().tolist()


def embed_image(
    image_bgr: np.ndarray,
    product_id: str,
    image_id: str,
    mrp: Optional[float] = None,
    scanned_at: Optional[str] = None,
) -> ProductEmbedding:
    """
    Create the MVP visual descriptor.

    The descriptor is intentionally not called a "product identity embedding":
    the same SKU photographed from different angles can look different, while
    different SKUs can look deceptively similar.
    """
    if not _validate_image(image_bgr):
        raise ValueError("image_bgr must be a valid BGR/BGRA image of at least 16x16 pixels")

    image_bgr = _to_bgr(image_bgr)

    # pHash captures broad visual structure and is reasonably robust to small
    # scale/compression changes.
    pil_img = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    phash = imagehash.phash(pil_img, hash_size=16)

    hist = _normalized_hsv_histogram(image_bgr)

    normalized_mrp: Optional[float]
    if mrp is None:
        normalized_mrp = None
    else:
        normalized_mrp = float(mrp)
        if normalized_mrp < 0:
            raise ValueError("mrp cannot be negative")

    return ProductEmbedding(
        product_id=str(product_id),
        image_id=str(image_id),
        phash=str(phash),
        hist=hist,
        mrp=normalized_mrp,
        scanned_at=scanned_at,
    )


def load_index() -> List[ProductEmbedding]:
    """Load a tolerant flat-file index. Corrupt entries are skipped."""
    if not INDEX_PATH.exists():
        return []

    try:
        raw = INDEX_PATH.read_text(encoding="utf-8")
        data = __import__("json").loads(raw)
    except (OSError, ValueError, TypeError):
        return []

    if not isinstance(data, list):
        return []

    entries: List[ProductEmbedding] = []

    for item in data:
        if not isinstance(item, dict):
            continue

        try:
            entries.append(
                ProductEmbedding(
                    product_id=str(item["product_id"]),
                    image_id=str(item["image_id"]),
                    phash=str(item["phash"]),
                    hist=[float(v) for v in item["hist"]],
                    mrp=(None if item.get("mrp") is None else float(item["mrp"])),
                    scanned_at=item.get("scanned_at"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    return entries


def save_to_index(entry: ProductEmbedding) -> None:
    """
    Insert or replace one image entry.

    Replacing an existing image_id prevents repeated scans from growing the
    demo index indefinitely.
    """
    if not isinstance(entry, ProductEmbedding):
        raise TypeError("entry must be a ProductEmbedding")

    entries = load_index()

    replaced = False
    for i, existing in enumerate(entries):
        if existing.image_id == entry.image_id:
            entries[i] = entry
            replaced = True
            break

    if not replaced:
        entries.append(entry)

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Atomic-ish write: write a temporary file first, then replace the index.
    tmp_path = INDEX_PATH.with_suffix(".tmp")
    tmp_path.write_text(
        __import__("json").dumps(
            [asdict(e) for e in entries],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp_path.replace(INDEX_PATH)


def _hamming_similarity(hash_a: str, hash_b: str) -> float:
    try:
        a = imagehash.hex_to_hash(hash_a)
        b = imagehash.hex_to_hash(hash_b)
    except (TypeError, ValueError):
        return 0.0

    if a.hash.size != b.hash.size:
        return 0.0

    distance = a - b
    return float(np.clip(1.0 - distance / a.hash.size, 0.0, 1.0))


def _hist_similarity(hist_a: Sequence[float], hist_b: Sequence[float]) -> float:
    try:
        a = np.asarray(hist_a, dtype=np.float32).reshape(-1)
        b = np.asarray(hist_b, dtype=np.float32).reshape(-1)
    except (TypeError, ValueError):
        return 0.0

    if a.size == 0 or a.size != b.size:
        return 0.0

    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        return 0.0

    # Correlation is naturally in [-1, 1]. Map it to [0, 1] instead of simply
    # clipping negative values, so a genuinely dissimilar image is represented
    # as low similarity rather than being conflated with zero after clipping.
    correlation = float(cv2.compareHist(a, b, cv2.HISTCMP_CORREL))
    if not np.isfinite(correlation):
        return 0.0

    return float(np.clip((correlation + 1.0) / 2.0, 0.0, 1.0))


def _combined_similarity(
    phash_score: float,
    hist_score: float,
    phash_weight: float,
) -> float:
    weight = float(np.clip(phash_weight, 0.0, 1.0))
    return float(np.clip(
        weight * phash_score + (1.0 - weight) * hist_score,
        0.0,
        1.0,
    ))


def find_similar(
    query: ProductEmbedding,
    top_k: int = DEFAULT_TOP_K,
    phash_weight: float = 0.65,
    min_score: float = DEFAULT_MIN_MATCH_SCORE,
    same_product_only: bool = False,
) -> List[MatchResult]:
    """
    Retrieve visually similar historical scans.

    Notes:
    - This is nearest-neighbor retrieval, not RAG.
    - Results are visual candidates, not verified SKU identities.
    - By default, low-scoring candidates are omitted.
    - The same product_id may appear more than once because history is
      image/scan based. Use product_id grouping at the UI layer if desired.
    """
    if not isinstance(query, ProductEmbedding):
        raise TypeError("query must be a ProductEmbedding")

    try:
        top_k = max(1, min(int(top_k), MAX_TOP_K))
    except (TypeError, ValueError):
        top_k = DEFAULT_TOP_K

    min_score = float(np.clip(min_score, 0.0, 1.0))

    results: List[MatchResult] = []

    for entry in load_index():
        if entry.image_id == query.image_id:
            continue

        if same_product_only and entry.product_id != query.product_id:
            continue

        phash_score = _hamming_similarity(query.phash, entry.phash)
        hist_score = _hist_similarity(query.hist, entry.hist)

        combined = _combined_similarity(
            phash_score,
            hist_score,
            phash_weight,
        )

        if combined < min_score:
            continue

        results.append(
            MatchResult(
                product_id=entry.product_id,
                image_id=entry.image_id,
                combined_score=round(combined, 4),
                phash_score=round(phash_score, 4),
                hist_score=round(hist_score, 4),
                mrp=entry.mrp,
                scanned_at=entry.scanned_at,
            )
        )

    results.sort(
        key=lambda result: (
            -result.combined_score,
            -result.phash_score,
            -result.hist_score,
        )
    )

    return results[:top_k]


def detect_price_or_label_change(
    query: ProductEmbedding,
    threshold: float = 0.88,
) -> Optional[str]:
    """
    Return a history flag when a very visually similar prior scan has a
    different recorded MRP.

    This function deliberately says "history flag", not "violation":
    a legitimate price update, different package size, market variant, or
    extraction error can all produce a price difference.
    """
    threshold = float(np.clip(threshold, 0.0, 1.0))

    matches = find_similar(
        query,
        top_k=5,
        phash_weight=0.65,
        min_score=threshold,
    )

    if not matches:
        return None

    # Prefer the strongest visually similar candidate that has a usable MRP.
    priced_matches = [
        match
        for match in matches
        if match.mrp is not None and query.mrp is not None
    ]

    if not priced_matches:
        return None

    best = priced_matches[0]

    if abs(float(query.mrp) - float(best.mrp)) <= 0.01:
        return None

    return (
        f"History flag: visually similar prior scan "
        f"(similarity {best.combined_score:.2f}) recorded MRP {best.mrp:.2f}; "
        f"current scan records MRP {float(query.mrp):.2f}. "
        f"This is a price/label history difference, not a legal violation by itself."
    )
