"""Shared sentence-splitting helper for the extraction submodules.

Deliberately simple and conservative: legal text has enough irregular
punctuation (sub-clause markers, abbreviations, section symbols) that a
"correct" sentence splitter is out of scope here. This splits on
period/semicolon followed by whitespace, which is good enough to isolate
one clause/sentence per condition, requirement, threshold or exemption
match while keeping the surrounding text as its `source_text` for
traceability.
"""

from __future__ import annotations

import re
from typing import List

_SPLIT_RE = re.compile(r"(?<=[.;])\s+")


def split_sentences(text: str) -> List[str]:
    # Normalize whitespace/newlines first so wrapped lines don't break a
    # sentence in the middle.
    joined = re.sub(r"\s+", " ", text).strip()
    if not joined:
        return []
    parts = [p.strip() for p in _SPLIT_RE.split(joined) if p.strip()]
    return parts
