"""
Generic deterministic provision classification for statutory and amendment documents.

Distinguishes:
1. Document metadata / context provisions (SHORT_TITLE, COMMENCEMENT)
2. Substantive provisions (SUBSTANTIVE_AMENDMENT, DEFINITION, SCOPE, APPLICABILITY,
   EXEMPTION, EXCEPTION, TRANSITIONAL, PROCEDURAL, PENALTY, REPEAL, OTHER)

Controlled Vocabulary:
- SHORT_TITLE
- COMMENCEMENT
- DEFINITION
- SCOPE
- SUBSTANTIVE_AMENDMENT
- APPLICABILITY
- EXEMPTION
- EXCEPTION
- TRANSITIONAL
- PROCEDURAL
- PENALTY
- REPEAL
- OTHER
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from .models import ProvisionType

NON_SUBSTANTIVE_PROVISION_TYPES = {
    ProvisionType.SHORT_TITLE,
    ProvisionType.COMMENCEMENT,
}

# These patterns identify source/document metadata that must never become an
# executable legal rule merely because it contains numbers or legal verbs.
_METADATA_PATTERNS = [
    r"\bg\.s\.r\.\s*\d+\s*\(e\)?\b",
    r"\bnotification\s+no\.?\s*[:\-]?",
    r"\bcg[-\s]*dl[-\s]*[ea][-\s]*\d{6,}",
    r"\bnew\s+delhi\b.*\b(thursday|monday|tuesday|wednesday|friday|saturday|sunday)\b",
    r"\bthe\s+principal\s+rules\s+were\s+published\b",
    r"\bwas\s+last\s+amended\b",
    r"\bpublished\s+by\s+the\s+controller\s+of\s+publications\b",
    r"\buploaded\s+by\s+dte\.\s+of\s+printing\b",
    r"^\s*(note|notes|illustration)\s*[:.\u2014-]",
    r"^\s*(explanation|note|illustration)\b",
]

_COMPILED_METADATA = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _METADATA_PATTERNS]

_METADATA_REFERENCE_PATTERNS = [
    re.compile(r"\.(?:table|explanation|note|illustration)\d*$", re.IGNORECASE),
    re.compile(r"\b(?:table|explanation|note|illustration)\b", re.IGNORECASE),
]

def _is_metadata_provision(text: str, reference: Optional[str] = None) -> bool:
    normalized = " ".join((text or "").split())
    if not normalized:
        return True
    if reference:
        ref = str(reference).strip()
        if any(p.search(ref) for p in _METADATA_REFERENCE_PATTERNS):
            return True
    return any(p.search(normalized) for p in _COMPILED_METADATA)


def is_executable_provision(
    text: str,
    reference: Optional[str] = None,
    *,
    amendment: bool = False,
    provision_type: Optional[ProvisionType] = None,
) -> bool:
    """Conservative executable-rule gate.

    Context/document metadata is never executable. For amendment documents,
    an ordinary/unknown clause is executable only when it contains a
    deterministic substantive legal signal; this prevents Gazette IDs,
    notes/explanations, and structural artifacts from becoming rules.
    """
    if _is_metadata_provision(text, reference):
        return False

    ptype = provision_type
    if ptype in NON_SUBSTANTIVE_PROVISION_TYPES:
        return False

    if reference:
        ref = str(reference).lower().strip()
        if re.search(r"\.(?:table|explanation|note|illustration)\d*$", ref):
            return False

    if ptype is not None and ptype != ProvisionType.OTHER:
        return True

    if amendment:
        normalized = " ".join((text or "").split()).lower()
        substantive_signals = (
            "shall be inserted", "shall be substituted", "shall be omitted",
            "shall be added", "shall apply", "shall declare", "shall inform",
            "shall ensure", "shall provide", "shall display", "shall mention",
            "shall bear", "may declare", "may provide", "shall contain",
            "provided that", "shall not", "must ",
            "अंतःस्थापित", "अंत:स्थापित", "प्रतिस्थापित", "लोप",
            "जोड़ा", "घोषित", "सूचित", "कर सकेगा", "होगा",
        )
        return any(signal in normalized for signal in substantive_signals)

    return True


# Regex patterns for deterministic provision classification (English + Hindi)
_SHORT_TITLE_PATTERNS = [
    r"\bthese\s+rules\s+may\s+be\s+called\b",
    r"\bthis\s+act\s+may\s+be\s+called\b",
    r"\bshall\s+be\s+called\s+the\b",
    r"\bshort\s+title\b",
    r"इन\s+नियमों\s+का\s+संक्षिप्त\s+नाम",
    r"संक्षिप्त\s+नाम",
]

_COMMENCEMENT_PATTERNS = [
    r"\bshall\s+come\s+into\s+force\b",
    r"\bcome\s+into\s+force\s+on\b",
    r"\bshall\s+take\s+effect\b",
    r"\bcome\s+into\s+operation\b",
    r"\bwith\s+effect\s+from\b",
    r"प्रकाशन\s+की\s+तारीख\s+को\s+प्रवृत्त\s+होंगे",
    r"प्रवृत्त\s+होंगे",
    r"लागू\s+होंगे",
]

_SUBSTANTIVE_AMENDMENT_PATTERNS = [
    r"\bshall\s+be\s+inserted\b",
    r"\bshall\s+be\s+substituted\b",
    r"\bshall\s+be\s+omitted\b",
    r"\bshall\s+be\s+added\b",
    r"\bfollowing\s+(?:proviso|sub-rule|clause|sub-clause)\s+shall\s+be\b",
    r"\bthe\s+following\s+proviso\s+shall\s+be\s+inserted\b",
    r"अंतःस्थापित\s+किया\s+जाएगा",
    r"प्रतिस्थापित\s+किया\s+जाएगा",
    r"लोप\s+किया\s+जाएगा",
    r"जोड़ा\s+जाएगा",
]

_EXEMPTION_PATTERNS = [
    r"\bshall\s+not\s+apply\s+to\b",
    r"\bexempt(?:ed)?\s+from\b",
    r"\bshall\s+be\s+exempt\b",
    r"\bexemption\b",
    r"छूट\s+दी\s+जाएगी",
]

_EXCEPTION_PATTERNS = [
    r"\bprovided\s+that\b",
    r"\bprovided\s+further\s+that\b",
    r"\bsave\s+as\s+otherwise\s+provided\b",
    r"\bexcept\s+where\b",
    r"परंतु\s+यह\s+कि",
]

_PENALTY_PATTERNS = [
    r"\bpunishable\s+with\b",
    r"\bpenalty\s+of\b",
    r"\bfine\s+which\s+may\s+extend\b",
    r"\bimprisonment\b",
    r"दंडनीय\s+होगा",
    r"जुर्माना",
]

_REPEAL_PATTERNS = [
    r"\bis\s+hereby\s+repealed\b",
    r"\bshall\s+stand\s+repealed\b",
    r"\brepeal\s+and\s+savings\b",
    r"निरसित\s+किया\s+जाता\s+है",
]

_DEFINITION_PATTERNS = [
    r"\bmeans\b",
    r"\bincludes\b",
    r"\bunless\s+the\s+context\s+otherwise\s+requires\b",
    r"से\s+अभिप्रेत\s+है",
    r"के\s+अंतर्गत\s+आता\s+है",
]

_APPLICABILITY_PATTERNS = [
    r"\bshall\s+apply\s+to\b",
    r"\bapplicable\s+to\b",
    r"\bapplicability\b",
    r"लागू\s+होगा",
]

_SCOPE_PATTERNS = [
    r"\bshall\s+extend\s+to\b",
    r"\bterritorial\s+extent\b",
    r"\bscope\s+of\b",
    r"क्षेत्रीय\s+विस्तार",
]

_TRANSITIONAL_PATTERNS = [
    r"\btransitional\s+provisions?\b",
    r"\btransitional\s+period\b",
    r"\bexisting\s+stocks\s+may\s+be\s+sold\b",
]

_PROCEDURAL_PATTERNS = [
    r"\bapplication\s+shall\s+be\s+made\b",
    r"\bmanner\s+of\s+inspection\b",
    r"\bprocedure\s+for\b",
    r"\bin\s+form\s+[A-Z0-9]+\b",
]

_COMPILED_MATCHERS = [
    (ProvisionType.SHORT_TITLE, [re.compile(p, re.IGNORECASE) for p in _SHORT_TITLE_PATTERNS], 0.95),
    (ProvisionType.COMMENCEMENT, [re.compile(p, re.IGNORECASE) for p in _COMMENCEMENT_PATTERNS], 0.95),
    (ProvisionType.SUBSTANTIVE_AMENDMENT, [re.compile(p, re.IGNORECASE) for p in _SUBSTANTIVE_AMENDMENT_PATTERNS], 0.90),
    (ProvisionType.REPEAL, [re.compile(p, re.IGNORECASE) for p in _REPEAL_PATTERNS], 0.90),
    (ProvisionType.PENALTY, [re.compile(p, re.IGNORECASE) for p in _PENALTY_PATTERNS], 0.90),
    (ProvisionType.EXEMPTION, [re.compile(p, re.IGNORECASE) for p in _EXEMPTION_PATTERNS], 0.85),
    (ProvisionType.EXCEPTION, [re.compile(p, re.IGNORECASE) for p in _EXCEPTION_PATTERNS], 0.85),
    (ProvisionType.APPLICABILITY, [re.compile(p, re.IGNORECASE) for p in _APPLICABILITY_PATTERNS], 0.85),
    (ProvisionType.SCOPE, [re.compile(p, re.IGNORECASE) for p in _SCOPE_PATTERNS], 0.85),
    (ProvisionType.TRANSITIONAL, [re.compile(p, re.IGNORECASE) for p in _TRANSITIONAL_PATTERNS], 0.85),
    (ProvisionType.PROCEDURAL, [re.compile(p, re.IGNORECASE) for p in _PROCEDURAL_PATTERNS], 0.85),
    (ProvisionType.DEFINITION, [re.compile(p, re.IGNORECASE) for p in _DEFINITION_PATTERNS], 0.80),
]


def classify_provision(
    text: str,
    reference: Optional[str] = None,
) -> Tuple[ProvisionType, float]:
    """
    Classify a provision text into the controlled ProvisionType vocabulary.
    Considers semantic/legal function rather than mere numbering.
    """
    normalized = " ".join((text or "").split())

    # Document/Gazette metadata is context, never an executable rule.
    if _is_metadata_provision(normalized, reference):
        return ProvisionType.OTHER, 0.98

    # Check for short title or commencement first:
    for ptype, regex_list, conf in _COMPILED_MATCHERS:
        for reg in regex_list:
            if reg.search(normalized):
                return ptype, conf

    # Contextual check: if reference specifically indicates sub-rule 1(1) or 1(2)
    if reference:
        ref_norm = reference.lower().replace("rule", "").strip()
        if ref_norm in ("1(1)", "1.(1)") and "called" in normalized.lower():
            return ProvisionType.SHORT_TITLE, 0.90
        if ref_norm in ("1(2)", "1.(2)") and ("force" in normalized.lower() or "gazette" in normalized.lower()):
            return ProvisionType.COMMENCEMENT, 0.90

    return ProvisionType.OTHER, 0.40


def is_substantive_provision(
    provision_type: ProvisionType,
    text: Optional[str] = None,
    reference: Optional[str] = None,
    *,
    amendment: bool = False,
) -> bool:
    """
    Return whether a provision can participate in executable-rule creation.

    ``OTHER`` is not automatically executable for amendment documents: the
    text/reference must pass the conservative executable gate. Existing
    callers that only provide a ProvisionType retain the historical behavior.
    """
    if provision_type in NON_SUBSTANTIVE_PROVISION_TYPES:
        return False
    if text is None and reference is None:
        return True
    return is_executable_provision(
        text or "",
        reference=reference,
        amendment=amendment,
        provision_type=provision_type,
    )


# ---------------------------------------------------------------------------
# Amendment Operation Classification
# ---------------------------------------------------------------------------
# Deterministic detection of what type of amendment operation a clause performs.
#
# Operation vocabulary:
#   INSERT    — a proviso / sub-clause / word is being added without removing
#               an existing one.  Keywords: "shall be inserted", "following
#               proviso shall be inserted", "shall be added", etc.
#   REMOVE    — an existing provision is deleted / omitted.  Keywords:
#               "shall be omitted", "shall stand omitted", "shall be deleted".
#   SUBSTITUTE — existing text is replaced by new text.  Keywords:
#               "shall be substituted", "shall stand substituted".
#   NEW_RULE  — an entirely new top-level rule/section is inserted.  Keywords:
#               "following rule shall be inserted", "following section shall be
#               inserted", "new rule", "new section inserted".
#   UNKNOWN   — cannot be determined from text alone.

_OPERATION_MATCHERS: list[tuple[str, list[re.Pattern[str]]]] = [
    # NEW_RULE must be checked before INSERT because a new rule is a special
    # kind of insertion at section level rather than proviso/clause level.
    ("NEW_RULE", [
        re.compile(r"\bfollowing\s+rule\s+shall\s+be\s+inserted\b", re.IGNORECASE),
        re.compile(r"\bfollowing\s+section\s+shall\s+be\s+inserted\b", re.IGNORECASE),
        re.compile(r"\bfollowing\s+new\s+rule\b", re.IGNORECASE),
        re.compile(r"\bfollowing\s+new\s+section\b", re.IGNORECASE),
        re.compile(r"\bnew\s+rule\s+(?:is|shall\s+be)\s+inserted\b", re.IGNORECASE),
        # Hindi equivalents
        re.compile(r"निम्नलिखित\s+नियम\s+अंतःस्थापित\s+किया\s+जाएगा", re.IGNORECASE),
    ]),
    ("REMOVE", [
        re.compile(r"\bshall\s+be\s+omitted\b", re.IGNORECASE),
        re.compile(r"\bshall\s+stand\s+omitted\b", re.IGNORECASE),
        re.compile(r"\bshall\s+be\s+deleted\b", re.IGNORECASE),
        re.compile(r"\bshall\s+stand\s+deleted\b", re.IGNORECASE),
        re.compile(r"\bshall\s+be\s+removed\b", re.IGNORECASE),
        # Hindi
        re.compile(r"लोप\s+किया\s+जाएगा"),
        re.compile(r"लोप\s+किए\s+जाएंगे"),
    ]),
    ("SUBSTITUTE", [
        re.compile(r"\bshall\s+be\s+substituted\b", re.IGNORECASE),
        re.compile(r"\bshall\s+stand\s+substituted\b", re.IGNORECASE),
        re.compile(r"\bshall\s+be\s+replaced\b", re.IGNORECASE),
        # Hindi
        re.compile(r"प्रतिस्थापित\s+किया\s+जाएगा"),
        re.compile(r"प्रतिस्थापित\s+किए\s+जाएंगे"),
    ]),
    ("INSERT", [
        re.compile(r"\bshall\s+be\s+inserted\b", re.IGNORECASE),
        re.compile(r"\bshall\s+stand\s+inserted\b", re.IGNORECASE),
        re.compile(r"\bshall\s+be\s+added\b", re.IGNORECASE),
        re.compile(r"\bfollowing\s+(?:proviso|sub-rule|sub-clause|clause|word|words|figure|figures|paragraph)\s+shall\s+be\s+inserted\b", re.IGNORECASE),
        re.compile(r"\bfollowing\s+(?:proviso|sub-rule|sub-clause|clause|word|words|figure|figures|paragraph)\s+shall\s+be\s+added\b", re.IGNORECASE),
        re.compile(r"\bfollowing\s+(?:proviso|clause|sub-clause)\s+shall\s+be\s+inserted\b", re.IGNORECASE),
        re.compile(r"\bfollowing\s+proviso\s+shall\s+be\s+inserted\b", re.IGNORECASE),
        # Hindi
        re.compile(r"अंतःस्थापित\s+किया\s+जाएगा"),
        re.compile(r"अंत:स्थापित\s+किया\s+जाएगा"),
        re.compile(r"जोड़ा\s+जाएगा"),
    ]),
]


def classify_amendment_operation(text: str) -> str:
    """Deterministically classify the amendment operation performed by ``text``.

    Returns one of: ``"INSERT"``, ``"REMOVE"``, ``"SUBSTITUTE"``,
    ``"NEW_RULE"``, or ``"UNKNOWN"``.

    The matcher list is ordered so that ``NEW_RULE`` is checked before
    ``INSERT`` (a new-rule insertion is a subset of insertion, so the more
    specific label must win).

    Examples
    --------
    >>> classify_amendment_operation("following proviso shall be inserted")
    'INSERT'
    >>> classify_amendment_operation("shall be omitted")
    'REMOVE'
    >>> classify_amendment_operation("shall be substituted")
    'SUBSTITUTE'
    >>> classify_amendment_operation("the following rule shall be inserted")
    'NEW_RULE'
    """
    normalised = " ".join((text or "").split())
    for operation, patterns in _OPERATION_MATCHERS:
        for pat in patterns:
            if pat.search(normalised):
                return operation
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Amendment Target Extraction
# ---------------------------------------------------------------------------
# Parses the standard Indian statutory drafting formula:
#
#   "In rule 6, in sub-rule (1), in clause (a), ..."
#   → target_rule = "Rule 6(1)(a)"
#
# Also handles simpler forms:
#   "In rule 6, ..."              → "Rule 6"
#   "In rule 6, in clause (a),"  → "Rule 6(a)"
#
# The amendment item (the ordinal marker from the amending document, e.g.
# "(i)", "(ii)", "2(a)(i)") is kept separately and must NOT be used as the
# target.  This function only extracts the TARGET of the amendment.

_IN_RULE_RE = re.compile(
    r"\bin\s+rule\s+"
    r"(?P<rule>[0-9A-Za-z][0-9A-Za-z\-]*)",
    re.IGNORECASE,
)
_IN_SUBRULE_RE = re.compile(
    r"\bin\s+sub[-\s]*rule\s+"
    r"(?P<subrule>\([^)]+\)|\d+)",
    re.IGNORECASE,
)
_IN_CLAUSE_RE = re.compile(
    r"\bin\s+clause\s+"
    r"(?P<clause>\([^)]+\))",
    re.IGNORECASE,
)
_IN_SUBCLAUSE_RE = re.compile(
    r"\bin\s+sub[-\s]*clause\s+"
    r"(?P<subclause>\([^)]+\))",
    re.IGNORECASE,
)


def extract_amendment_target(text: str) -> Optional[str]:
    """Parse the amendment target rule reference from ``text``.

    Returns a canonical string such as ``"Rule 6(1)(a)"`` when the text
    follows the Indian statutory drafting formula ``"In rule 6, in sub-rule
    (1), in clause (a), ..."``.  Returns ``None`` when no target can be
    identified.

    This is DISTINCT from the amendment item's own positional id (e.g.
    ``"2(a)(i)"``), which comes from the amending document's own outline.

    Examples
    --------
    >>> extract_amendment_target(
    ...     "In rule 6, in sub-rule (1), in clause (a), after the existing "
    ...     "proviso, the following proviso shall be inserted")
    'Rule 6(1)(a)'
    >>> extract_amendment_target(
    ...     "In rule 6, in sub-rule (1), in clause (b), after the existing "
    ...     "proviso, the following proviso shall be inserted")
    'Rule 6(1)(b)'
    >>> extract_amendment_target("shall be omitted")
    """
    normalised = " ".join((text or "").split())

    rule_m = _IN_RULE_RE.search(normalised)
    if not rule_m:
        return None

    rule_no = rule_m.group("rule")
    target = f"Rule {rule_no}"

    subrule_m = _IN_SUBRULE_RE.search(normalised)
    if subrule_m:
        sr = subrule_m.group("subrule")
        # Normalise bare digit: "1" → "(1)"
        if not sr.startswith("("):
            sr = f"({sr})"
        target += sr

    clause_m = _IN_CLAUSE_RE.search(normalised)
    if clause_m:
        target += clause_m.group("clause")

    subclause_m = _IN_SUBCLAUSE_RE.search(normalised)
    if subclause_m:
        target += subclause_m.group("subclause")

    return target


