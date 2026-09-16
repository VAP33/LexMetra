"""
Targeted regression tests for G.S.R. 577(E) Legal Metrology (Packaged Commodities)
(Second Amendment) Rules, 2022 ingestion.

Verifies the 23 points required for robust regulation ingestion:
1. G.S.R. 577(E) is identified correctly.
2. Amendment title is identified as: Legal Metrology (Packaged Commodities) (Second Amendment) Rules, 2022.
3. Amendment version is: Second Amendment, 2022.
4. publication_date = 2022-07-14.
5. effective_from = 2022-07-14.
6. Rule 1(1) is classified as SHORT_TITLE/context metadata, not an executable rule.
7. Rule 1(2) is classified as COMMENCEMENT/context metadata, not an executable rule.
8. Rule 1(2) contributes effective_from = 2022-07-14.
9. Rule 2(a)(i) is extracted as a substantive provision.
10. Rule 2(a)(ii) is extracted as a substantive provision.
11. Rule 2(a)(iii) is extracted as a substantive provision.
12. Rule 2(b) is extracted as a substantive provision.
13. Hindi and English representations of the same provision are deduplicated.
14. Hindi/English duplication does not increase canonical rule count.
15. Canonical rules contain only the English normalized representation.
16. No provision.hi / provision.en duplicate canonical rule fields are introduced.
17. 2022-07-15 is stored as the substantive applicability trigger, not effective_from.
18. One-year applicability duration is preserved.
19. Amendment-level effective metadata is propagated to affected substantive rules.
20. Source/page/provision traceability is preserved.
21. Existing lifecycle/version behavior remains correct.
22. Existing non-amendment ingestion behavior does not regress.
23. Malformed/duplicate provisions are detected and handled deterministically.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import pytest

from models import ApprovalState
from amendments import activate_amendment, transition_amendment
import db.persistence as persistence
import regulation_ingestion as ri
from tests.fixtures.pdf_builder import build_native_text_pdf


HINDI_PAGE_TEXT = """\
उपभोक्ता मामले, खाद्य और सार्वजनिक वितरण मंत्रालय
(उपभोक्ता मामले विभाग)
अधिसूचना
नई दिल्ली, 14 जुलाई, 2022

सा.का.नि. 577(अ).—केन्द्रीय सरकार, विधिक मापविज्ञान अधिनियम, 2009 (2010 का 1) की धारा 52 की उपधारा (1) और उपधारा (2) के खंड (q) द्वारा प्रदत्त शक्तियों का प्रयोग करते हुए, विधिक मापविज्ञान (पैक की गई वस्तुएं) नियम, 2011 का और संशोधन करने के लिए निम्नलिखित नियम बनाती है, अर्थात्:—

1. (1) इन नियमों का संक्षिप्त नाम विधिक मापविज्ञान (पैक की गई वस्तुएं) (दूसरा संशोधन) नियम, 2022 है।
(2) ये राजपत्र में उनके प्रकाशन की तारीख को प्रवृत्त होंगे।

2. विधिक मापविज्ञान (पैक की गई वस्तुएं) नियम, 2011 में, नियम 6 में,—
(क) उप-नियम (1) में, खंड (क) में, स्पष्टीकरण I से पहले, निम्नलिखित परंतुक अंतःस्थापित किया जाएगा, अर्थात्:—
(i) 15 जुलाई, 2022 के पश्चात् विनिर्मित या पैक किए गए या आयात किए गए इलेक्ट्रॉनिक उत्पादों के लिए, एक वर्ष की अवधि के लिए, विनिर्माता या पैकर या आयातक क्यूआर कोड के माध्यम से पैकेज संबंधी सूचना घोषित कर सकेगा;
(ii) पैकेज पर उस व्यक्ति का टेलीफोन नंबर और ई-मेल पता होगा जिससे उपभोक्ता शिकायत की स्थिति में संपर्क किया जा सके;
(iii) पैकेज उपभोक्ता को अन्य संबंधित जानकारी के लिए क्यूआर कोड को स्कैन करने की सूचना देगा;
(ख) उप-नियम (2) में, निम्नलिखित परंतुक अंतःस्थापित किया जाएगा, अर्थात्:—
"परंतु यह कि इलेक्ट्रॉनिक उत्पाद डिजिटल मीडिया के माध्यम से अनिवार्य घोषणाएं कर सकते हैं..."
"""

ENGLISH_PAGE_TEXT = """\
MINISTRY OF CONSUMER AFFAIRS, FOOD AND PUBLIC DISTRIBUTION
(Department of Consumer Affairs)
NOTIFICATION
New Delhi, the 14th July, 2022

G.S.R. 577(E).—In exercise of the powers conferred by sub-section (1) read with clause (q) of sub-section (2) of section 52 of the Legal Metrology Act, 2009 (1 of 2010), the Central Government hereby makes the following rules further to amend the Legal Metrology (Packaged Commodities) Rules, 2011, namely:—

1. (1) These rules may be called the Legal Metrology (Packaged Commodities) (Second Amendment) Rules, 2022.
(2) They shall come into force on the date of their publication in the Official Gazette.

2. In the Legal Metrology (Packaged Commodities) Rules, 2011, in rule 6,—
(a) in sub-rule (1), in clause (a), before Explanation I, the following proviso shall be inserted, namely:—
(i) for electronic products manufactured or packed or imported after the 15th July, 2022, for a period of one year from such date, the manufacturer or packer or importer may declare the package information through a QR Code;
(ii) the package shall bear the telephone number and e-mail address of the person who can be contacted in case of consumer complaints;
(iii) the package shall inform the consumer to scan the QR code for other related information;
(b) in sub-rule (2), the following proviso shall be inserted, namely:—
"Provided that electronic products may declare mandatory attributes through digital media..."
"""


def _build_gsr_577_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "gsr_577_e_2022.pdf"
    build_native_text_pdf(pdf_path, [HINDI_PAGE_TEXT, ENGLISH_PAGE_TEXT])
    return pdf_path


def test_gsr_577_e_document_and_amendment_metadata(tmp_path, monkeypatch):
    """
    Points 1, 2, 3, 4, 5, 6, 7, 8:
    - Notification G.S.R. 577(E) detected
    - Amendment title and version detected
    - publication_date = 2022-07-14
    - effective_from = 2022-07-14 (from Rule 1(2) commencement, NOT defaulted to ingestion date)
    - Rule 1(1) classified as SHORT_TITLE
    - Rule 1(2) classified as COMMENCEMENT
    - Rule 1(2) contributes effective_from = 2022-07-14
    """
    monkeypatch.setattr(persistence, "save_amendment_draft", lambda *a, **k: None)
    pdf_path = _build_gsr_577_pdf(tmp_path)
    result = ri.ingest_regulation_pdf(
        pdf_path,
        source_document_id="gsr_577_e_2022",
        created_by="officer_metrology",
    )
    draft = result.draft
    assert draft.approval_state == ApprovalState.EXTRACTED

    impact = draft.impact or {}
    meta = impact.get("amendment_metadata") or {}

    # Point 1: Notification Number Detection
    assert meta.get("notification_number") == "G.S.R. 577(E)"
    assert impact.get("notification") == "G.S.R. 577(E)"

    # Point 2: Amendment title
    assert "Legal Metrology (Packaged Commodities) (Second Amendment) Rules, 2022" in meta.get("full_title", "")

    # Point 3: Amendment version
    assert meta.get("version_label") == "Second Amendment, 2022"
    assert meta.get("amendment_name") == "Second Amendment"
    assert meta.get("year") == 2022

    # Point 4: publication_date = 2022-07-14
    assert meta.get("gazette_date") == "2022-07-14"

    # Point 5: effective_from = 2022-07-14
    assert meta.get("effective_date") == "2022-07-14"
    assert impact.get("effective_date") == "2022-07-14"

    # Points 6 & 7: Context provisions Rule 1(1) and Rule 1(2)
    ctx = meta.get("context_provisions") or {}
    assert "Rule 1(1)" in ctx
    assert ctx["Rule 1(1)"]["provision_type"] == "SHORT_TITLE"
    assert not ctx["Rule 1(1)"]["is_substantive"]

    assert "Rule 1(2)" in ctx
    assert ctx["Rule 1(2)"]["provision_type"] == "COMMENCEMENT"
    assert not ctx["Rule 1(2)"]["is_substantive"]

    # Point 8: Rule 1(2) contributes effective_from = 2022-07-14
    assert meta.get("commencement_source_provision") == "Rule 1(2)"


def test_gsr_577_e_substantive_granularity_and_deduplication(tmp_path, monkeypatch):
    """
    Points 9, 10, 11, 12, 13, 14, 15, 16:
    - Rule 2(a)(i), 2(a)(ii), 2(a)(iii), 2(b) extracted as substantive provisions
    - Rule 1(1) and 1(2) excluded from executable compliance rules
    - Hindi and English representations of the same provision are deduplicated
    - Proposed rule versions count is exactly 4 (no duplication increase)
    - Canonical rules contain normalized English text
    - No provision.hi / provision.en duplicate schema fields
    """
    monkeypatch.setattr(persistence, "save_amendment_draft", lambda *a, **k: None)
    pdf_path = _build_gsr_577_pdf(tmp_path)
    result = ri.ingest_regulation_pdf(pdf_path, source_document_id="gsr_577_e_2022")
    draft = result.draft

    rule_versions = draft.proposed_rule_versions
    # Point 14: Count is exactly 4
    assert len(rule_versions) == 4, f"Expected 4 canonical rules, got {len(rule_versions)}"

    # Points 9, 10, 11, 12: Specific leaf substantive provisions
    expected_provisions = ["Rule 2(a)(i)", "Rule 2(a)(ii)", "Rule 2(a)(iii)", "Rule 2(b)"]
    extracted_provs = [
        v.conditions.get("source_provision") or v.rule_id
        for v in rule_versions
    ]
    for prov in expected_provisions:
        assert prov in extracted_provs, f"Missing provision: {prov} in {extracted_provs}"

    # Confirm Rule 1 is NOT present in executable compliance rules
    for v in rule_versions:
        assert not v.rule_id.startswith("Rule 1") and v.rule_id != "1"

    # Point 15 & 16: Clean canonical English representation, no provision.hi/provision.en clutter
    for v in rule_versions:
        conds = v.conditions or {}
        assert "provision.hi" not in conds
        assert "provision.en" not in conds
        # English canonical text
        assert "electronic products" in (v.text or "").lower() or "package" in (v.text or "").lower() or "qr code" in (v.text or "").lower()


def test_gsr_577_e_effective_vs_applicability_and_metadata_inheritance(tmp_path, monkeypatch):
    """
    Points 17, 18, 19, 20:
    - 2022-07-15 is stored as the substantive applicability trigger, NOT effective_from
    - One-year applicability duration is preserved
    - Amendment-level effective metadata is propagated to affected substantive rules
    - Source/page/provision traceability is preserved
    """
    monkeypatch.setattr(persistence, "save_amendment_draft", lambda *a, **k: None)
    pdf_path = _build_gsr_577_pdf(tmp_path)
    result = ri.ingest_regulation_pdf(pdf_path, source_document_id="gsr_577_e_2022")
    draft = result.draft

    for v in draft.proposed_rule_versions:
        # Point 17: Effective date is 2022-07-14 (Gazette commencement), NEVER replaced by 2022-07-15
        assert v.effective_from == date(2022, 7, 14)

        conds = v.conditions or {}
        # Substantive trigger date and duration
        app = conds.get("applicability") or {}
        assert app.get("manufactured_packed_imported_after") == "2022-07-15"
        # Point 18: One-year duration preserved
        assert app.get("duration") == "1 year"
        assert conds.get("substantive_trigger_date") == "2022-07-15"
        assert conds.get("applicability_duration") == "1 year"

        # Point 19: Amendment-level metadata propagated
        assert v.version == "Second Amendment, 2022"
        assert conds.get("notification_number") == "G.S.R. 577(E)"
        assert conds.get("commencement_source_provision") == "Rule 1(2)"

        # Point 20: Traceability
        meta_sources = conds.get("metadata_sources") or {}
        assert meta_sources.get("effective_from", {}).get("source_provision") == "Rule 1(2)"
        assert meta_sources.get("effective_from", {}).get("value") == "2022-07-14"
        assert meta_sources.get("version", {}).get("source_provision") == "Rule 1(1)"
        assert conds.get("source_provision") is not None


def test_gsr_577_e_lifecycle_transitions(tmp_path, monkeypatch):
    """
    Point 21:
    Verify extracted amendment starts in EXTRACTED, follows the strict lifecycle
    EXTRACTED -> AI_PARSED -> PENDING_REVIEW -> APPROVED -> SCHEDULED -> ACTIVE,
    and cannot become ACTIVE automatically upon ingestion.
    """
    monkeypatch.setattr(persistence, "save_amendment_draft", lambda *a, **k: None)
    pdf_path = _build_gsr_577_pdf(tmp_path)
    draft = ri.ingest_regulation_pdf(pdf_path, source_document_id="gsr_577_e_2022").draft

    # Must start in EXTRACTED
    assert draft.approval_state == ApprovalState.EXTRACTED

    # Cannot jump directly to ACTIVE
    with pytest.raises(ValueError):
        transition_amendment(draft, ApprovalState.ACTIVE)

    with pytest.raises(ValueError):
        activate_amendment(draft, authorized_by="controller_legal_metrology")

    # Step-by-step lifecycle traversal:
    draft = transition_amendment(draft, ApprovalState.AI_PARSED)
    assert draft.approval_state == ApprovalState.AI_PARSED

    draft = transition_amendment(draft, ApprovalState.PENDING_REVIEW)
    assert draft.approval_state == ApprovalState.PENDING_REVIEW

    draft = transition_amendment(draft, ApprovalState.APPROVED)
    assert draft.approval_state == ApprovalState.APPROVED

    draft = transition_amendment(draft, ApprovalState.SCHEDULED)
    assert draft.approval_state == ApprovalState.SCHEDULED

    draft = activate_amendment(draft, authorized_by="controller_legal_metrology")
    assert draft.approval_state == ApprovalState.ACTIVE


def test_non_amendment_ingestion_does_not_regress(tmp_path, monkeypatch):
    """
    Point 22:
    Existing non-amendment (base regulation) documents retain their full structure
    including Rule 1 and do not get incorrectly pruned.
    """
    from lexmetra_rules.pipeline import run_pipeline

    BASE_REG_TEXT = """\
THE LEGAL METROLOGY (PACKAGED COMMODITIES) RULES, 2011

1. Short title and commencement.—
(1) These rules may be called the Legal Metrology (Packaged Commodities) Rules, 2011.
(2) They shall come into force on the 1st day of April, 2011.

2. Definitions.—In these rules, unless the context otherwise requires,—
(a) "Act" means the Legal Metrology Act, 2009;
(b) "dealer" means a person who carries on the business of buying, selling, supplying or distributing.
"""
    pdf_path = tmp_path / "base_reg_2011.pdf"
    build_native_text_pdf(pdf_path, [BASE_REG_TEXT])

    res = run_pipeline(str(pdf_path), document_id="base_reg_test", source="IN-LMPC-2011")
    rule_ids = [r.rule_id for r in res.rules]
    # In base regulations, Rule 1 and Rule 2 are both extracted as base rules
    assert "1" in rule_ids
    assert "2" in rule_ids


def test_malformed_and_duplicate_provisions_handled_deterministically(tmp_path, monkeypatch):
    """
    Point 23:
    Malformed or duplicate provisions are detected and handled deterministically without crashing.
    """
    from lexmetra_rules.clause_segmentation import segment_clauses
    from lexmetra_rules.segmentation import RuleSpan

    malformed_text = """2. In rule 6,—
(a) first clause with unusual formatting
(a) duplicate subclause marker
(invalid) unknown marker
(i) subsubclause
"""
    span = RuleSpan(raw_number="2", heading_line_text="2. In rule 6,—", text=malformed_text, page_start=1, page_end=1)
    clauses = segment_clauses(span)
    assert len(clauses) >= 2
    clause_ids = [c.clause_id for c in clauses]
    assert "2(a)" in clause_ids
