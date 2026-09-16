"""
Deterministic, explainable, multi-label rule classification.

No LLM is used. Classification is a transparent keyword/vocabulary match so
that every assigned category can be explained by the exact terms that
triggered it (the ``signals`` field), matching the schema you specified.

Category vocabulary
--------------------
This is a NEW field relative to the existing LexMetra project. The existing
``rules.json`` only has a narrow ``applies_to.product_category`` list
(currently: all / soft_drink / drug_formulation / scheduled_commodities /
like_commodity / ready_to_serve_fruit_beverage / fast_food) used for
exemption scoping, not a GENERAL/FOOD/COSMETICS/DRUGS/... domain taxonomy.
Rather than overload that narrower existing field, this module introduces
``category`` as its own field; ``adapters/rules_json_adapter.py`` keeps the
two separate and documents the (non-authoritative) best-effort mapping
between them.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .models import ClassificationResult, ReviewStatus

# category -> list of (term, weight). Longer/more specific phrases carry
# more weight than single generic words.
CATEGORY_VOCABULARY: Dict[str, List[Tuple[str, float]]] = {
    "GENERAL": [
        ("packaged commodity", 1.0), ("pre-packaged", 1.0), ("prepackaged", 1.0),
        ("principal display panel", 1.2), ("net quantity", 1.0),
        ("declaration", 0.6), ("manufacturer", 0.5), ("packer", 0.5),
        ("importer", 0.5), ("retail sale price", 0.9), ("maximum retail price", 0.9),
        ("label", 0.4), ("package", 0.4), ("commodity", 0.4),
    ],
    "FOOD": [
        ("food", 1.0), ("foodstuff", 1.2), ("human consumption", 1.2),
        ("edible", 1.0), ("nutrition", 0.8), ("ingredient", 0.6),
        ("fssai", 1.3), ("perishable", 0.7), ("dairy", 0.7), ("bakery", 0.6),
        ("confectionery", 0.6), ("beverage", 0.5),
    ],
    "COSMETICS": [
        ("cosmetic", 1.3), ("cosmetics", 1.3), ("toiletry", 1.0),
        ("toiletries", 1.0), ("fragrance", 0.7), ("perfume", 0.7),
        ("skin", 0.5), ("soap", 0.6), ("shampoo", 0.8), ("talcum", 0.7),
    ],
    "DRUGS": [
        ("drug", 1.2), ("drugs", 1.2), ("pharmaceutical", 1.2),
        ("medicine", 1.0), ("medicament", 1.0), ("formulation", 0.6),
        ("dosage", 0.8), ("schedule h", 1.2), ("ayurvedic", 0.9),
        ("patent and proprietary medicine", 1.3),
    ],
    "SOFT_DRINK": [
        ("soft drink", 1.4), ("aerated water", 1.3), ("carbonated", 1.0),
        ("fruit beverage", 1.1), ("ready to serve", 0.8),
    ],
    "PACKAGED_COMMODITIES": [
        ("packaged commodity", 1.3), ("packaged commodities", 1.3),
        ("pre-packaged commodity", 1.3), ("wholesale package", 0.8),
        ("retail package", 0.8),
    ],
    "IMPORT": [
        ("import", 1.0), ("imported", 1.1), ("importer", 0.8),
        ("country of origin", 1.2), ("customs", 0.9), ("foreign", 0.4),
    ],
}

#: Absolute score below which a category is not included at all.
MIN_CATEGORY_SCORE = 0.5
#: A category is included if its score is at least this fraction of the
#: single highest-scoring category's score (keeps multi-label output from
#: including every category that matched even one weak keyword).
RELATIVE_INCLUSION_RATIO = 0.25

AUTO_ACCEPT_CONFIDENCE = 0.75
UNCERTAIN_CONFIDENCE = 0.35


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def classify(text: str) -> ClassificationResult:
    """
    Score every category against `text`, return the categories that clear
    both an absolute and a relative threshold, with the matched terms kept
    as `signals` for explainability.
    """
    normalized = _normalize(text)

    scores: Dict[str, float] = {}
    signals: Dict[str, List[str]] = {}

    for category, vocab in CATEGORY_VOCABULARY.items():
        matched_terms: List[str] = []
        score = 0.0
        for term, weight in vocab:
            if term in normalized:
                score += weight
                matched_terms.append(term)
        if score > 0:
            scores[category] = score
            signals[category] = matched_terms

    if not scores:
        return ClassificationResult(
            categories=["GENERAL"],
            confidence=0.2,
            signals={},
            review_status=ReviewStatus.NEEDS_REVIEW,
        )

    max_score = max(scores.values())
    selected = [
        category for category, score in scores.items()
        if score >= MIN_CATEGORY_SCORE and score >= max_score * RELATIVE_INCLUSION_RATIO
    ]
    if not selected:
        # Nothing cleared the absolute floor even though something matched
        # a little; treat as GENERAL with low confidence rather than
        # confidently asserting a specific narrow category off weak signal.
        selected = ["GENERAL"]

    selected_signals = {c: signals[c] for c in selected if c in signals}

    # Confidence: normalize the top selected score into [0,1] with a
    # deliberately gentle curve (diminishing returns) so it never claims
    # near-1.0 confidence off a handful of keyword hits.
    top_score = max(scores[c] for c in selected)
    confidence = min(0.97, top_score / (top_score + 2.0) * 2.0)
    confidence = round(max(0.0, min(1.0, confidence)), 3)

    if confidence >= AUTO_ACCEPT_CONFIDENCE:
        review_status = ReviewStatus.AUTO_ACCEPTED
    elif confidence < UNCERTAIN_CONFIDENCE:
        review_status = ReviewStatus.UNCERTAIN
    else:
        review_status = ReviewStatus.NEEDS_REVIEW

    return ClassificationResult(
        categories=selected,
        confidence=confidence,
        signals=selected_signals,
        review_status=review_status,
    )
