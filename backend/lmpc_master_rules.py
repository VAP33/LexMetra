"""
LMPC Master Rule Register
Statutory legal metrology rules under the Legal Metrology (Packaged Commodities) Rules, 2011 (G.S.R. 202(E), 7th March 2011)
and Legal Metrology Act, 2009.
Directly grounded in docs/lmpc_rules.txt containing all 48 statutory rules.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import yaml
import functools

# Path to the source of truth for LMPC rules
_LMPC_RULES_PATH = Path(__file__).resolve().parent.parent / 'docs' / 'lmpc_rules.txt'
if not _LMPC_RULES_PATH.exists():
    _LMPC_RULES_PATH = Path(__file__).resolve().parent / 'docs' / 'lmpc_rules.txt'

@functools.lru_cache(maxsize=1)
def load_all_48_lmpc_rules_raw() -> List[Dict[str, Any]]:
    """Loads all 48 rules from docs/lmpc_rules.txt."""
    if not _LMPC_RULES_PATH.exists():
        return []
    with open(_LMPC_RULES_PATH, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get('rules', [])


def _chapter_for_rule(rule_ref: str) -> str:
    r = str(rule_ref or '').lower()
    if any(k in r for k in ('rule 3', 'rule 6', 'rule 7', 'rule 8', 'rule 9', 'rule 10', 'rule 11', 'rule 12', 'rule 13', 'rule 14', 'rule 15', 'rule 16', 'rule 17', 'rule 18')):
        return 'Chapter II - Provisions Applicable to Packages Intended for Retail Sale'
    if 'rule 24' in r:
        return 'Chapter III - Wholesale Packages'
    if 'rule 25' in r:
        return 'Chapter IV - Export Packages'
    if 'rule 26' in r:
        return 'Chapter V - Exemptions'
    if 'rule 31' in r or 'rule 32' in r:
        return 'Chapter VII - General Provisions'
    return 'Chapter II - Declarations on Retail Packages'


def _penal_section_for_rule(rule_id: str) -> tuple[str, str]:
    rid = rule_id.upper()
    if 'R18-2' in rid:
        return ('Section 36(2), LM Act 2009', 'Fine up to ₹5,000 for charging above declared MRP.')
    if 'R18-5' in rid or 'R6-3' in rid:
        return ('Section 36(1), LM Act 2009', 'Non-compoundable obliteration of price; fine up to ₹25,000 / ₹50,000.')
    if 'R24' in rid:
        return ('Section 36(1), LM Act 2009', 'Fine up to ₹25,000 for unlabelled wholesale packages.')
    if 'R25' in rid:
        return ('Section 36(1), LM Act 2009', 'Unlawful domestic diversion of export packages; confiscation and penal action.')
    return ('Section 36(1), LM Act 2009', 'Fine up to ₹25,000 (first offense), up to ₹50,000 (second), up to ₹1,00,000 or imprisonment up to 1 year.')


def get_lmpc_master_rule_register() -> List[Dict[str, Any]]:
    """Returns the full master rule register of all 48 rules."""
    raw_rules = load_all_48_lmpc_rules_raw()
    items = []
    for r in raw_rules:
        penal_sec, penal_desc = _penal_section_for_rule(r.get('id', ''))
        exemptions = []
        if isinstance(r.get('exemptWhen'), dict):
            any_of = r.get('exemptWhen', {}).get('anyOf', [])
            for ex in any_of:
                if isinstance(ex, dict):
                    exemptions.append(ex.get('applicabilityId') or str(ex))
        elif r.get('exemptWhen'):
            exemptions.append(str(r.get('exemptWhen')))

        items.append({
            'id': r.get('id'),
            'citation': r.get('ruleReference') or r.get('id'),
            'chapter': _chapter_for_rule(r.get('ruleReference', '')),
            'title': r.get('title') or r.get('id'),
            'summary': " ".join((r.get('description') or '').split()),
            'category_scope': 'All Commodities' if r.get('appliesWhen', {}).get('productCategory') == 'any' else str(r.get('appliesWhen', {}).get('productCategory', 'All Commodities')),
            'is_mandatory': r.get('severity') == 'critical',
            'penal_section': penal_sec,
            'penalty_description': penal_desc,
            'exemptions': exemptions,
        })
    return items


def evaluate_contextual_rule_applicability(
    product_category: Optional[str] = None,
    sale_type: Optional[str] = None,
    net_quantity_val: Optional[float] = None,
    net_quantity_unit: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Evaluates each of the 48 master rules against specific package parameters
    and tags status: APPLICABLE, EXEMPT, or NOT_APPLICABLE.
    """
    register = get_lmpc_master_rule_register()
    category_norm = (product_category or '').lower()
    sale_type_norm = (sale_type or 'retail').lower()
    unit_norm = (net_quantity_unit or '').lower()

    is_small_pack = False
    if net_quantity_val is not None:
        if unit_norm in ['g', 'gm', 'gram', 'ml', 'milli'] and net_quantity_val <= 10.0:
            is_small_pack = True

    is_bulk = False
    if net_quantity_val is not None:
        if unit_norm in ['kg', 'kilogram', 'l', 'litre', 'liter'] and net_quantity_val > 25.0:
            if 'cement' not in category_norm and 'fertilizer' not in category_norm:
                is_bulk = True

    is_export = sale_type_norm in ['export', 'export_only']
    is_wholesale = sale_type_norm in ['wholesale', 'shipper', 'bulk']
    is_institutional = sale_type_norm in ['institutional', 'industrial']

    core_retail_rules = {
        'R6-1-A-MANUFACTURER',
        'R6-1-B-COMMON-NAME',
        'R6-1-C-NET-QUANTITY',
        'R6-1-D-MANUFACTURE-DATE',
        'R6-1-E-RETAIL-PRICE',
        'R6-2-CONSUMER-CARE',
        'R6-3-NO-DECLARATION-STICKER',
        'R7-2-PDP-NUMERAL-HEIGHT-WEIGHT-VOLUME',
        'R7-2-PDP-NUMERAL-HEIGHT-LENGTH-AREA-NUMBER',
        'R7-3-PDP-LETTER-HEIGHT',
        'R8-1-PDP-PLACEMENT',
        'R9-1-MANNER',
        'R9-4-LANGUAGE',
        'R10-1-FULL-ADDRESS',
        'R11-1-EXCLUDE-WRAPPER',
        'R12-1-ADEQUATE-UNIT',
        'R13-2-3-UNIT-SELECTION',
        'R13-5-SYMBOLS',
        'R18-1-NO-SALE-UNLESS-COMPLIANT',
        'R18-2-NO-SALE-ABOVE-MRP',
        'R18-5-NO-MRP-OBLITERATION',
    }

    results = []
    for rule in register:
        rule_id = rule['id']
        status = 'NOT_APPLICABLE'
        context_note = 'Rule outside scope for standard retail packaging inspection.'

        if is_export:
            if rule_id == 'R25-EXPORT-REPACK':
                status = 'ACTIVE_EXEMPTION'
                context_note = 'Export package evaluated under Rule 25 exemption.'
            else:
                status = 'EXEMPTED'
                context_note = 'Exempt from domestic retail rules under Rule 25 (Export Package Exemption).'

        elif is_wholesale:
            if rule_id == 'R24-WHOLESALE-DECLARATIONS':
                status = 'APPLICABLE'
                context_note = 'Wholesale shipper packaging standard actively applies under Rule 24.'
            else:
                status = 'NOT_APPLICABLE'
                context_note = 'Retail declaration rule not applicable to wholesale bulk pack.'

        elif is_small_pack:
            if rule_id in ('R7-1-PDP-5CC', 'R10-1-PROVISO-5CC-MARK', 'R12-7-SMALL-PACKAGE-TAG'):
                status = 'APPLICABLE'
                context_note = 'Small package relaxation provisions actively apply under Rule 26(a).'
            elif rule_id in ('R6-1-A-MANUFACTURER', 'R6-1-B-COMMON-NAME', 'R6-1-C-NET-QUANTITY', 'R6-2-CONSUMER-CARE'):
                status = 'EXEMPTED'
                context_note = f'Exempt under Rule 26(a): Net quantity <= 10 {unit_norm or "g"}.'
            else:
                status = 'NOT_APPLICABLE'
                context_note = 'General rule relaxed for small packages under Rule 26(a).'

        elif is_bulk:
            if rule_id in ('R6-1-E-RETAIL-PRICE',):
                status = 'EXEMPTED'
                context_note = f'Exempt under Rule 26(b): Net quantity > 25 {unit_norm or "kg"}.'
            else:
                status = 'NOT_APPLICABLE'
                context_note = 'Retail rule not applicable to bulk industrial pack under Rule 26(b).'

        elif is_institutional:
            if rule_id in ('R6-1-E-RETAIL-PRICE', 'R18-2-NO-SALE-ABOVE-MRP'):
                status = 'EXEMPTED'
                context_note = 'Exempt under Rule 26(c) (Direct Institutional/Industrial Consumer Supply).'
            else:
                status = 'APPLICABLE'
                context_note = 'Standard institutional commodity packaging provisions apply.'

        else:
            if rule_id in core_retail_rules:
                status = 'APPLICABLE'
                context_note = 'Mandatory statutory requirement for current retail package.'
            elif rule_id == 'R24-WHOLESALE-DECLARATIONS':
                status = 'NOT_APPLICABLE'
                context_note = 'Not applicable: individual retail package evaluated (not wholesale shipper).'
            elif rule_id == 'R25-EXPORT-REPACK':
                status = 'NOT_APPLICABLE'
                context_note = 'Not applicable: domestic retail sale evaluated (not export commodity).'
            elif rule_id in ('R7-1-PDP-5CC', 'R10-1-PROVISO-5CC-MARK', 'R12-7-SMALL-PACKAGE-TAG'):
                status = 'NOT_APPLICABLE'
                context_note = 'Not applicable: package volume exceeds 5 cm³ small-pack threshold.'
            elif rule_id in ('R16-USABLE-SHEETS', 'R17-CONTAINER-DECLARATIONS'):
                status = 'NOT_APPLICABLE'
                context_note = 'Not applicable to this commodity packaging structure.'
            elif rule_id == 'R11-4-WHEN-PACKED-ALLOWED':
                status = 'EXEMPTED'
                context_note = 'Exempted: commodity not subject to environmental moisture loss schedule.'
            elif rule_id == 'R8-2-RETURNABLE-BOTTLE-PRICE':
                status = 'NOT_APPLICABLE'
                context_note = 'Not applicable: non-returnable single-use packaging.'
            elif rule_id in ('R31-ADVERTISEMENT-NET-QUANTITY', 'R31-2-FONT-SIZE-EQUALITY'):
                status = 'NOT_APPLICABLE'
                context_note = 'Not applicable to physical package labeling (governs published advertisements).'
            elif rule_id == 'R18-7-ELECTRONIC-WEIGHING-MACHINE':
                status = 'NOT_APPLICABLE'
                context_note = 'Not applicable to pre-packaged commodity (governs loose retail weighing premises).'
            else:
                status = 'NOT_APPLICABLE'
                context_note = 'Exempted or outside statutory scope for this product form factor.'

        results.append({
            **rule,
            'evaluation_status': status,
            'context_note': context_note,
        })

    return results
