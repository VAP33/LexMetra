from __future__ import annotations
import re

# LEFT fragment short (1-3 letters) + RIGHT fragment (>=2 letters).
_SHORT_LEFT_RE = re.compile(r"\b([A-Za-z]{1,3}) ([A-Za-z]{2,})\b")

# LEFT fragment (>=2 letters) + RIGHT fragment short (1-3 letters).
_SHORT_RIGHT_RE = re.compile(r"\b([A-Za-z]{2,}) ([A-Za-z]{1,3})\b")

# RIGHT fragment is a common English SUFFIX STUB that cannot start a word.
# Catches "manufac tured", "distribu tion", "composi te" etc.
_SUFFIX_STUB_RE = re.compile(
    r"\b([A-Za-z]{3,}) "
    r"(tured|tion|tions|ment|ments|ness|ity|ities|ing|ings"
    r"|ised|ized|ise|ize|ated|ates|able|ible|ful|less"
    r"|ship|ward|wards|wise|ery|ary|ory)\b",
    re.IGNORECASE,
)

# Ordinal suffix: "15 th" -> "15th"
_ORDINAL_RE = re.compile(r"\b(\d+) (st|nd|rd|th)\b", re.IGNORECASE)

_STANDALONE_SINGLES = frozenset("aAiI")
_STANDALONE_DOUBLES = frozenset({
    "of", "in", "to", "at", "by", "on", "or", "an", "as", "be",
    "do", "go", "he", "if", "is", "it", "my", "no", "so", "up", "us", "we",
})

# Three-char words safe as LEFT fragment -- commonly sentence starters,
# articles, prepositions that would never be the start of a split word.
_STANDALONE_TRIPLES_LEFT = frozenset({
    "the", "and", "for", "not", "but", "are", "was", "has",
    "had", "its", "our", "any", "per", "sub", "non",
    "nor", "yet", "due", "viz", "etc", "two",
})

# Three-char words safe as RIGHT fragment -- only truly unambiguous ones
# that can never be the tail of a split word.  "all", "can", "not", "may",
# "act" etc. are EXCLUDED from blocking the SHORT-LEFT pass because OCR
# genuinely produces "sh all", "s can".  However they ARE protected in the
# SHORT-RIGHT pass (where left is long, e.g. "shall not") because a long
# real word followed by these is almost certainly a real word boundary.
_STANDALONE_TRIPLES_RIGHT = frozenset({
    "the", "and", "for", "not", "but", "all", "are", "was", "has",
    "had", "its", "our", "any", "can", "may", "per", "sub", "non",
    "act", "nor", "yet", "due", "viz", "etc", "two",
})


def _is_standalone_left(tok: str) -> bool:
    """True when tok is a known standalone word that should NOT be merged as a left fragment."""
    if tok in _STANDALONE_SINGLES:
        return True
    t = tok.lower()
    if len(tok) == 2 and t in _STANDALONE_DOUBLES:
        return True
    if len(tok) == 3 and t in _STANDALONE_TRIPLES_LEFT:
        return True
    return False


def _is_standalone_right(tok: str) -> bool:
    """True when tok is a known standalone word that should NOT be merged as a right fragment."""
    if tok in _STANDALONE_SINGLES:
        return True
    t = tok.lower()
    if len(tok) == 2 and t in _STANDALONE_DOUBLES:
        return True
    if len(tok) == 3 and t in _STANDALONE_TRIPLES_RIGHT:
        return True
    return False


def _merge_left_short(m):
    left, right = m.group(1), m.group(2)
    if _is_standalone_left(left):
        return m.group(0)
    # When left is a very short stub (1-2 chars), only block on 2-char
    # standalone words -- allow merging with 3-char words like "all", "can"
    # because OCR genuinely produces "sh all", "s can" etc.
    if len(left) <= 2:
        r = right.lower()
        if right in _STANDALONE_SINGLES:
            return m.group(0)
        if len(right) == 2 and r in _STANDALONE_DOUBLES:
            return m.group(0)
        return left + right
    # For 3-char left stubs, apply the full right safelist.
    if _is_standalone_right(right):
        return m.group(0)
    return left + right


def _merge_right_short(m):
    left, right = m.group(1), m.group(2)
    if _is_standalone_right(right):
        return m.group(0)
    # Only merge when left is also short-ish (<=6 chars) to avoid
    # merging long real words with short right tokens not in safelist.
    if len(left) > 6:
        # Allow only single-char stubs after long words.
        if len(right) > 1:
            return m.group(0)
    return left + right


def _merge_suffix_stub(m):
    # Suffix stubs cannot start a word -- always merge.
    return m.group(1) + m.group(2)


def normalize_ocr_text(text: str) -> str:
    """Repair intra-word spaces in raw Tesseract OCR output.

    Only call on OCR-sourced text.  Native text and raw_ocr_text
    provenance strings are left unchanged by the caller.
    """
    if not text:
        return text

    # Pass 1: ordinal suffixes ("15 th" -> "15th")
    result = _ORDINAL_RE.sub(lambda m: m.group(1) + m.group(2), text)

    # Pass 2: suffix stub merges ("manufac tured" -> "manufactured").
    for _ in range(3):
        new = _SUFFIX_STUB_RE.sub(_merge_suffix_stub, result)
        if new == result:
            break
        result = new

    # Pass 3: short-LEFT merges (iterate to handle chains).
    for _ in range(5):
        new = _SHORT_LEFT_RE.sub(_merge_left_short, result)
        if new == result:
            break
        result = new

    # Pass 4: short-RIGHT merges (single pass, conservative).
    result = _SHORT_RIGHT_RE.sub(_merge_right_short, result)

    return result
