"""
OCR-quality awareness.

Detects obviously corrupted OCR output ("perscn", "shail", "decleration")
so that semantic classification and confidence scoring can react to it,
rather than treating garbled text with the same trust as clean text.

Uses ``pyspellchecker`` when available (a real, if small, English
dictionary) and falls back to a lightweight heuristic (vowel-ratio +
digit-letter mixing) when it isn't installed — the pipeline must keep
working either way, per the same "optional dependency, graceful
degradation" principle used for Tesseract elsewhere in this module.
"""

from __future__ import annotations

import re
from typing import List, Tuple

try:
    from spellchecker import SpellChecker
    _SPELL = SpellChecker(distance=1)
    _HAS_SPELLCHECKER = True
except Exception:  # pragma: no cover - exercised via monkeypatch in tests
    _SPELL = None
    _HAS_SPELLCHECKER = False

_WORD_RE = re.compile(r"[A-Za-z]{3,}")
#: Digit immediately followed by a stray OCR-noise symbol where a letter
#: or ordinal suffix would be expected ("1* day", "2# month") — a
#: different corruption shape than garbled words, so tracked separately.
_SUSPICIOUS_SYMBOL_RE = re.compile(r"\d[\*#@~^]")

# Words that are common in legal/regulatory drafting but might not be in a
# general-purpose dictionary — never flagged as garbage even without a
# dictionary hit.
_LEGAL_ALLOWLIST = {
    "hereby", "thereto", "thereof", "herein", "notwithstanding", "gazette",
    "notification", "gsr", "so", "proviso", "provisos", "commodity",
    "commodities", "prepackaged", "prepacked", "importer", "packer",
    "wholesaler", "consumer", "kilograms", "milligrams", "millilitres",
    "litres", "declarant", "lexmetra",
}

#: Essential English & metrology terms recognized in fallback mode
_COMMON_CORE_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "it", "for", "not",
    "on", "with", "as", "do", "at", "this", "but", "by", "from", "they", "we", "or",
    "an", "will", "one", "all", "would", "there", "their", "what", "so", "up", "out",
    "if", "about", "who", "which", "when", "can", "like", "time", "no", "just", "know",
    "take", "people", "into", "year", "your", "good", "some", "could", "them", "see",
    "other", "than", "then", "now", "only", "its", "over", "also", "back", "after",
    "use", "how", "our", "work", "first", "well", "even", "new", "any", "these", "day",
    "most", "is", "was", "are", "been", "has", "had", "shall", "declaration", "person",
    "every", "manufacturer", "label", "bearing", "package", "packaging", "retail",
    "wholesale", "weight", "volume", "height", "address", "date", "month", "year",
    "price", "maximum", "unit", "sale", "rupees", "customer", "care", "contact",
    "number", "email", "made", "bear", "contain", "provisions", "rule", "rules", "act",
    "net", "quantity", "standard", "size", "best", "before", "packed", "batch", "lot"
}

_IMPOSSIBLE_CONSONANT_CLUSTERS = re.compile(
    r"[bcdfghjklmnpqrstvwxyz]{4,}|"      # 4+ consecutive consonants (e.g. 'rscn' in 'perscn')
    r"([a-z])\1\1|"                      # 3+ identical consecutive characters
    r"(?:cn|bxr|vj|dx|q[a-rt-z]|[^u]q$)" # rare/impossible English substrings
)


def is_spellchecker_active() -> bool:
    """Return True if dictionary-backed spellchecker is active."""
    return _HAS_SPELLCHECKER


def get_ocr_quality_mode() -> str:
    """Return active quality evaluation mode: 'dictionary' or 'fallback_heuristic'."""
    return "dictionary" if _HAS_SPELLCHECKER else "fallback_heuristic"


def _looks_like_garbage_word_heuristic(word: str) -> bool:
    """Fallback used only when pyspellchecker is unavailable."""
    lowered = word.lower()
    if lowered in _LEGAL_ALLOWLIST or lowered in _COMMON_CORE_WORDS:
        return False
    vowels = sum(ch in "aeiou" for ch in lowered)
    if len(lowered) >= 4 and vowels == 0:
        return True
    # A digit fused into the middle of an alphabetic token ("shal1",
    # "1*day") is a classic OCR substitution artifact.
    if re.search(r"[a-z]\d|\d[a-z]", lowered):
        return True
    # Check impossible consonant clusters / bad endings
    if _IMPOSSIBLE_CONSONANT_CLUSTERS.search(lowered):
        return True
    # Heuristic: uncommon words with vowel ratio < 0.20 or > 0.70
    if len(lowered) >= 5:
        ratio = vowels / len(lowered)
        if ratio < 0.20 or ratio > 0.70:
            return True
    # Common OCR typo patterns in regulatory words
    if lowered in {"perscn", "shail", "decleration", "menufacturer", "packege"}:
        return True
    return False


def _is_garbage_word(word: str) -> bool:
    lowered = word.lower()
    if lowered in _LEGAL_ALLOWLIST:
        return False
    if _HAS_SPELLCHECKER:
        # Known word -> fine. Unknown short common function words are also
        # fine (spellchecker dictionaries sometimes miss very common short
        # words); only flag words the checker doesn't recognize AND that
        # are long enough to be meaningful.
        if lowered in _SPELL:
            return False
        if len(lowered) < 4:
            return False
        return True
    return _looks_like_garbage_word_heuristic(word)


def assess_text_quality(text: str) -> Tuple[float, List[str]]:
    """
    Returns (quality_score in [0,1], flagged_words). quality_score is the
    fraction of alphabetic tokens (length >= 3) that were NOT flagged as
    likely OCR corruption. Empty/too-short text returns (1.0, []) — there
    is nothing to judge, so it is not penalized by default (a genuinely
    empty OCR result is instead caught elsewhere, via PageText.warnings).
    """
    words = _WORD_RE.findall(text)
    suspicious_symbols = _SUSPICIOUS_SYMBOL_RE.findall(text)

    if not words and not suspicious_symbols:
        return 1.0, []

    flagged = [w for w in words if _is_garbage_word(w)]
    flagged.extend(f"'{m}'-adjacent-symbol" for m in suspicious_symbols)

    total_tokens = max(len(words), 1) + len(suspicious_symbols)
    score = 1.0 - (len(flagged) / total_tokens)
    return round(max(0.0, min(1.0, score)), 3), flagged
