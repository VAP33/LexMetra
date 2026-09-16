"""Provenance catalog for Legal Metrology knowledge chunks (RAG-01).

This module does NOT fabricate gazette body text. Chunks built from
``rules/rules.json`` are implementation encodings and must be marked
unsourced. Official URLs are recorded so a human Legal Lead can replace
them with verbatim gazette text later.
"""
from __future__ import annotations

from typing import Any, Dict

INDIA_CODE_LMA_2009 = "https://www.indiacode.nic.in/handle/123456789/2154"
EGAZETTE = "https://egazette.gov.in/"
CONSUMER_AFFAIRS_LMPC = (
    "https://consumeraffairs.nic.in/en/organisation-and-units/"
    "legal-metrology/the-legal-metrology-act-2009"
)

RULE_SOURCE_INTENTS: Dict[str, Dict[str, Any]] = {
    "LMPC-2011-R3-SCOPE": {
        "intended_instrument": "Legal Metrology (Packaged Commodities) Rules, 2011, Rule 3",
        "intended_urls": [CONSUMER_AFFAIRS_LMPC, EGAZETTE],
    },
    "LMPC-2011-R6-DECLARATIONS": {
        "intended_instrument": "LMPC Rules 2011, Rule 6 (declarations to be made on every package)",
        "intended_urls": [CONSUMER_AFFAIRS_LMPC, EGAZETTE],
    },
    "LMPC-2011-R7-NUMERAL-HEIGHT": {
        "intended_instrument": "LMPC Rules 2011, Rule 7 (height of numerals)",
        "intended_urls": [CONSUMER_AFFAIRS_LMPC, EGAZETTE],
    },
    "LMPC-2011-R8-PDP": {
        "intended_instrument": "LMPC Rules 2011, Rule 8 / Rule 2(h) Principal Display Panel",
        "intended_urls": [CONSUMER_AFFAIRS_LMPC, EGAZETTE],
    },
    "LMPC-2011-R26-SMALL-PACKS": {
        "intended_instrument": "LMPC Rules 2011, Rule 26 (exemptions / small packs)",
        "intended_urls": [CONSUMER_AFFAIRS_LMPC, EGAZETTE],
    },
    "LMPC-2011-R24-WHOLESALE": {
        "intended_instrument": "LMPC Rules 2011, Rule 24 (wholesale packages)",
        "intended_urls": [CONSUMER_AFFAIRS_LMPC, EGAZETTE],
    },
    "LMA-2009": {
        "intended_instrument": "Legal Metrology Act, 2009",
        "intended_urls": [INDIA_CODE_LMA_2009],
    },
}


def provenance_for_rule(rule_id: str) -> Dict[str, Any]:
    intent = RULE_SOURCE_INTENTS.get(rule_id, {
        "intended_instrument": "Legal Metrology (Packaged Commodities) Rules, 2011",
        "intended_urls": [CONSUMER_AFFAIRS_LMPC, EGAZETTE],
    })
    return {
        "sourced": False,
        "source_kind": "rules.json_implementation_encoding",
        "placeholder": True,
        "intended_instrument": intent["intended_instrument"],
        "intended_urls": intent["intended_urls"],
        "note": (
            "Chunk text is derived from the implementation dataset rules.json, "
            "not from ingested gazette PDF/HTML. Do not treat it as verbatim law."
        ),
    }
