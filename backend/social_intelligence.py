"""
backend/social_intelligence.py
Social Media & Public Complaint Intelligence Engine (USP 5 & 6).

Pipeline:
SIMULATED PUBLIC POSTS
  -> INGESTION
  -> CLEANING
  -> NORMALIZATION
  -> DEDUPLICATION
  -> RELEVANCE CLASSIFICATION
  -> COMPLAINT CLASSIFICATION
  -> REGULATORY DOMAIN CLASSIFICATION
  -> PRODUCT / BRAND EXTRACTION
  -> LOCATION EXTRACTION
  -> AUTHORITY / ORGANIZATION EXTRACTION
  -> SEVERITY & DYNAMIC PRIORITIZATION
  -> EVIDENCE DETECTION
  -> CLUSTERING
  -> HUMAN REVIEW QUEUE
  -> AUTHORITY / SENIOR INSPECTOR DASHBOARD

Invariants:
- Clearly marked: SIMULATED PUBLIC INTELLIGENCE / DEMO DATA.
- Dynamic calculation: Prioritization score is NOT hardcoded; computed via multi-factor heuristic.
- Clean modular design: Ingestion layer can be swapped with live social APIs without refactoring the engine.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("lexmetra.social_intelligence")

STORE_FILE = Path(__file__).resolve().parent / "db" / "data_local" / "social_intelligence_posts.json"
STORE_FILE.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class RawPublicPost:
    """Simulated or live public stream intake record."""
    raw_id: str
    platform: str  # "X/Twitter", "Instagram", "National Consumer Helpline", "FoSCoS Portal", "Public Forum"
    author_handle: str
    author_follower_count: int
    posted_at: str
    text_content: str
    media_urls: List[str] = field(default_factory=list)
    location_tag: Optional[str] = None
    tagged_handles: List[str] = field(default_factory=list)


@dataclass
class ProcessedPublicSignal:
    """Fully parsed, classified, clustered, and prioritized intelligence case."""
    mention_id: str
    raw_id: str
    source_platform: str
    author_handle: str
    posted_at: str
    ingested_at: str
    raw_text: str
    clean_text: str
    
    # Classification & Entities
    is_relevant: bool
    is_complaint: bool
    regulatory_domain: str  # "LMPC (Metrology)", "FSSAI (Food Safety)", "DUAL_MRP", "COUNTERFEIT / ALTERATION", "CONSUMER_AFFAIRS"
    complaint_category: str  # "Overcharging / Dual MRP", "Underweight / Shortage", "Missing Unit Sale Price (USP)", "Expired / Tampered Date", "Missing Declarations", "FSSAI Unlicensed / Quality Hazard"
    product_brand: Optional[str]
    product_name: Optional[str]
    extracted_location: str
    district_or_city: str
    state: str
    geo_lat: float
    geo_lng: float
    tagged_authorities: List[str]
    
    # Evidence & Verification
    has_evidence: bool
    evidence_urls: List[str]
    evidence_type: str  # "PHOTO_PRODUCT", "PHOTO_BILL_RECEIPT", "PHOTO_SCALE", "NONE"
    
    # Dynamic Scoring & Prioritization
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    priority_score: int  # 0 to 100, calculated dynamically
    prioritization_rationale: str
    confidence_score: float  # 0.0 - 1.0
    
    # Clustering & Duplication
    cluster_id: Optional[str] = None
    cluster_label: Optional[str] = None
    cluster_size: int = 1
    is_duplicate: bool = False
    duplicate_of_id: Optional[str] = None
    
    # Correlated Official Inspections
    related_inspection_id: Optional[str] = None
    
    # Review Workflow
    review_status: str = "SHORTLISTED"  # "SHORTLISTED", "ASSIGNED_TO_INSPECTOR", "CONVERTED_TO_CASE", "DISMISSED"
    assigned_officer: Optional[str] = None
    officer_notes: Optional[str] = None
    data_classification: str = "SIMULATED PUBLIC INTELLIGENCE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# In-Memory Cache
# ---------------------------------------------------------------------------

_SIGNALS_CACHE: Dict[str, ProcessedPublicSignal] = {}
_CLUSTERS_CACHE: Dict[str, List[str]] = {}


# ---------------------------------------------------------------------------
# Location & Coordinates Mapping (Maharashtra & Key Hubs)
# ---------------------------------------------------------------------------

GEO_MAP: Dict[str, Tuple[str, str, float, float]] = {
    "pune": ("Pune", "Maharashtra", 18.5204, 73.8567),
    "mumbai": ("Mumbai", "Maharashtra", 19.0760, 72.8777),
    "nashik": ("Nashik", "Maharashtra", 19.9975, 73.7898),
    "nagpur": ("Nagpur", "Maharashtra", 21.1458, 79.0882),
    "aurangabad": ("Chhatrapati Sambhajinagar", "Maharashtra", 19.8762, 75.3433),
    "sambhajinagar": ("Chhatrapati Sambhajinagar", "Maharashtra", 19.8762, 75.3433),
    "thane": ("Thane", "Maharashtra", 19.2183, 72.9781),
    "gurugram": ("Gurugram", "Haryana", 28.4595, 77.0266),
    "delhi": ("Delhi", "Delhi NCT", 28.6139, 77.2090),
    "bangalore": ("Bengaluru", "Karnataka", 12.9716, 77.5946),
    "bengaluru": ("Bengaluru", "Karnataka", 12.9716, 77.5946),
    "hyderabad": ("Hyderabad", "Telangana", 17.3850, 78.4867),
}


# ---------------------------------------------------------------------------
# The 13-Stage NLP & Heuristic Intelligence Pipeline
# ---------------------------------------------------------------------------

def _clean_and_normalize_text(raw_text: str) -> str:
    """Stage 3 & 4: Cleans URLs, redundant symbols, standardizes currency and spacing."""
    text = re.sub(r"https?://\S+|www\.\S+", "", raw_text)
    # Currency standardization (Rs., Rs, INR, /- -> Rs)
    text = re.sub(r"(?:₹|INR|Rs\.|Rs)\s*(\d+)", r"Rs \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_authority_tags(text: str, tags: List[str]) -> List[str]:
    """Stage 11: Identifies regulatory authority handles mentioned or tagged."""
    found: Set[str] = set(tags)
    patterns = {
        r"@jagograhakjago": "@jagograhakjago (DoCA)",
        r"@fssaiindia": "@fssaiindia (FSSAI)",
        r"@consumeraffairs": "@consumeraffairs (DoCA)",
        r"@legalmetrology": "@legalmetrology (LMPC)",
        r"@foodsafety_mah": "@foodsafety_mah (FDA Maharashtra)",
        r"@docagov": "@docagov (DoCA)",
    }
    t_lower = text.lower()
    for pattern, label in patterns.items():
        if re.search(pattern, t_lower):
            found.add(label)
    if "nch" in t_lower or "national consumer helpline" in t_lower:
        found.add("National Consumer Helpline (NCH)")
    return sorted(list(found))


def _extract_location_geo(text: str, loc_tag: Optional[str]) -> Tuple[str, str, str, float, float]:
    """Stage 10: Location extraction with geo-coordinates."""
    combined = f"{text} {loc_tag or ''}".lower()
    for key, (city, state, lat, lng) in GEO_MAP.items():
        if key in combined:
            return f"{city}, {state}", city, state, lat, lng
    return "Other / Pan-India", "Unspecified District", "India", 20.5937, 78.9629


def _extract_brand_product(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Stage 9: Product & brand extraction."""
    t_lower = text.lower()
    brands = {
        "cadbury gems": ("GEMS", "Cadbury Gems Pouch"),
        "gems": ("GEMS", "Cadbury Gems Pouch"),
        "cadbury": ("CADBURY", "Cadbury Confectionery"),
        "bru coffee": ("BRU", "BRU Instant Coffee 150g"),
        "bru": ("BRU", "BRU Instant Coffee 150g"),
        "amul gold": ("AMUL", "Amul Gold Pasteurized Milk"),
        "amul": ("AMUL", "Amul Dairy Commodity"),
        "traya": ("TRAYA", "Traya Hair Serum & Actives 30ml"),
        "vaseline": ("VASELINE", "Vaseline Deep Restore Lotion"),
        "good knight": ("GOOD KNIGHT", "Good Knight Liquid Mosquito Refill"),
        "haldiram": ("HALDIRAM", "Haldiram Bhujia Sev"),
        "maggi": ("NESTLE", "Nestle Maggi 2-Minute Noodles"),
        "nestle": ("NESTLE", "Nestle Food Commodity"),
        "patanjali": ("PATANJALI", "Patanjali Cow Ghee"),
        "britannia": ("BRITANNIA", "Britannia Good Day Biscuits"),
        "tata salt": ("TATA", "Tata Salt 1kg"),
        "real juice": ("DABUR", "Real Fruit Power Juice 1L"),
    }
    for key, (brand, prod) in brands.items():
        if key in t_lower:
            return brand, prod
    return None, "Packaged Commodity"


def _classify_complaint_and_domain(text: str) -> Tuple[bool, bool, str, str, float]:
    """Stages 6, 7, 8: Relevance, Complaint Type, Regulatory Domain, and Category."""
    t_lower = text.lower()

    # Noise filter
    consumer_keywords = [
        "mrp", "rupees", "charge", "weight", "net wt", "gram", "kg", "ml", "expiry",
        "best before", "fssai", "license", "fungus", "expired", "fake", "tampered",
        "sticker", "underweight", "shortage", "overcharge", "dual mrp", "consumer court",
        "legal metrology", "jagograhakjago", "cheated", "fraud", "packet", "commodity"
    ]
    is_relevant = any(k in t_lower for k in consumer_keywords)
    if not is_relevant:
        return False, False, "GENERAL", "Irrelevant / Non-Regulatory Noise", 0.40

    is_complaint = any(c in t_lower for c in [
        "overcharge", "extra", "violation", "fake", "bad", "expired", "complaint",
        "cheating", "shortage", "tampered", "please inspect", "look into", "illegal",
        "looting", "wrong", "underweight", "less weight"
    ])

    # Domain & category mapping
    if any(k in t_lower for k in ["dual mrp", "overcharge", "overcharging", "higher price", "sticker over mrp", "extra charge", "above mrp", "mrp se jyada"]):
        return True, is_complaint, "LMPC (Metrology)", "Overcharging / Dual MRP", 0.95
    elif any(k in t_lower for k in ["underweight", "less weight", "shortage", "kam wajan", "kam quantity", "net weight", "digital scale"]):
        return True, is_complaint, "LMPC (Metrology)", "Underweight / Shortage", 0.93
    elif any(k in t_lower for k in ["fssai", "fungus", "food safety", "adulteration", "spoiled", "poison", "insect", "unhygienic", "smell"]):
        return True, is_complaint, "FSSAI (Food Safety)", "FSSAI Unlicensed / Quality Hazard", 0.96
    elif any(k in t_lower for k in ["expired", "best before", "date rubbed", "date tampered", "solvent"]):
        return True, is_complaint, "FSSAI (Food Safety)", "Expired / Tampered Date", 0.94
    elif any(k in t_lower for k in ["fake", "counterfeit", "tampered", "duplicate", "duplicate barcode"]):
        return True, is_complaint, "COUNTERFEIT / ALTERATION", "Counterfeit Packaging / Tampering", 0.89
    elif any(k in t_lower for k in ["usp", "unit price", "unit sale price", "per gram", "per ml"]):
        return True, is_complaint, "LMPC (Metrology)", "Missing Unit Sale Price (USP)", 0.88
    else:
        return True, is_complaint, "LMPC (Metrology)", "Missing Declarations", 0.82


def _detect_evidence(post: RawPublicPost, text: str) -> Tuple[bool, List[str], str]:
    """Stage 12: Evidence detection."""
    evidence_urls = list(post.media_urls)
    has_evidence = len(evidence_urls) > 0
    t_lower = text.lower()

    if any(k in t_lower for k in ["scale", "weighing", "kitchen scale", "digital scale", "grams"]):
        evidence_type = "PHOTO_SCALE" if has_evidence else "SCALE_CLAIM"
    elif any(k in t_lower for k in ["bill", "invoice", "receipt", "slip", "counter"]):
        evidence_type = "PHOTO_BILL_RECEIPT" if has_evidence else "RECEIPT_CLAIM"
    elif has_evidence:
        evidence_type = "PHOTO_PRODUCT"
    else:
        evidence_type = "NONE"

    return has_evidence, evidence_urls, evidence_type


def _calculate_priority(
    regulatory_domain: str,
    complaint_category: str,
    has_evidence: bool,
    evidence_type: str,
    tagged_authorities: List[str],
    author_followers: int,
    cluster_frequency: int,
) -> Tuple[str, int, str]:
    """
    Stage 13: Dynamic priority scoring (0 - 100).
    NEVER hardcoded. Evaluated on:
    - Base statutory risk (Food safety/adulteration > Dual MRP > Missing USP)
    - Corroborating physical evidence (scale, bill, photo)
    - Recurrence / cluster volume in the region
    - Authority escalation tags
    """
    score = 40  # base

    # 1. Statutory Severity
    domain_weight = {
        "FSSAI (Food Safety)": 28,
        "COUNTERFEIT / ALTERATION": 25,
        "LMPC (Metrology)": 20,
        "GENERAL": 10,
    }
    score += domain_weight.get(regulatory_domain, 15)

    if complaint_category in ["Overcharging / Dual MRP", "Underweight / Shortage", "Expired / Tampered Date"]:
        score += 15

    # 2. Evidence Corroboration
    if has_evidence:
        score += 15
        if evidence_type in ["PHOTO_SCALE", "PHOTO_BILL_RECEIPT"]:
            score += 8

    # 3. Escalation / Tagging
    if len(tagged_authorities) > 0:
        score += min(len(tagged_authorities) * 4, 10)

    # 4. Cluster Volume
    if cluster_frequency > 1:
        score += min(cluster_frequency * 6, 18)

    # 5. Follower Reach / Virality
    if author_followers > 10000:
        score += 5

    # Bound
    final_score = max(10, min(final_score_val := score, 99))

    # Severity Tier
    if final_score >= 82:
        severity = "CRITICAL"
        rationale = f"Priority Score {final_score}/100: Critical hazard or multi-post recurrent cluster with attached physical evidence."
    elif final_score >= 65:
        severity = "HIGH"
        rationale = f"Priority Score {final_score}/100: Statutory non-compliance with verified location and clear regulatory violation markers."
    elif final_score >= 45:
        severity = "MEDIUM"
        rationale = f"Priority Score {final_score}/100: Single consumer grievance regarding missing declarations or unverified weight claim."
    else:
        severity = "LOW"
        rationale = f"Priority Score {final_score}/100: Low confidence or generic consumer discussion without corroborating details."

    return severity, final_score, rationale


# ---------------------------------------------------------------------------
# Realistic Multi-Region Simulated Public Dataset
# ---------------------------------------------------------------------------

def _get_raw_simulated_posts() -> List[RawPublicPost]:
    """Generates realistic public posts across Maharashtra & India with clustering."""
    now_iso = datetime.now().isoformat()
    return [
        RawPublicPost(
            raw_id="RAW-PUNE-01",
            platform="X/Twitter",
            author_handle="@Punit_ConsumerVoice",
            author_follower_count=14200,
            posted_at=now_iso,
            text_content="@jagograhakjago @fssaiindia Bought Cadbury Gems packet from market in Pune. MRP sticker Rs 25 pasted over original printed MRP Rs 20! Total overcharging under Section 36(1) LM Act! Please inspect!",
            media_urls=["/uploads/GEMS.jpg"],
            location_tag="Pune, Camp Area",
            tagged_handles=["@jagograhakjago", "@fssaiindia"],
        ),
        RawPublicPost(
            raw_id="RAW-PUNE-02",
            platform="Public Forum",
            author_handle="PuneConsumerForum#441",
            author_follower_count=50,
            posted_at=now_iso,
            text_content="Multiple grocery stores in Kothrud Pune are selling Cadbury Gems 25g pouch with illegal stickers pasted on the MRP. Original says ₹20, they charge ₹25! Section 36 violation.",
            media_urls=[],
            location_tag="Kothrud, Pune",
            tagged_handles=["@legalmetrology"],
        ),
        RawPublicPost(
            raw_id="RAW-PUNE-03",
            platform="Instagram",
            author_handle="@foodie_punekar",
            author_follower_count=8900,
            posted_at=now_iso,
            text_content="Hey @consumeraffairs Cadbury Gems at Pune station shop has double MRP sticker! Bill slip says 25, printed box says 20. Attaching photo proof! #LMPC #Overcharging",
            media_urls=["/uploads/GEMS.jpg"],
            location_tag="Pune Railway Station",
            tagged_handles=["@consumeraffairs"],
        ),
        RawPublicPost(
            raw_id="RAW-GUR-01",
            platform="National Consumer Helpline",
            author_handle="Consumer #994821",
            author_follower_count=10,
            posted_at=now_iso,
            text_content="BRU instant coffee packet purchased in Gurugram says 150g Net Weight, but kitchen digital scale repeatedly weighs only 108g gross including packaging. Shortage violation Rule 6(1)(e).",
            media_urls=[],
            location_tag="Sector 14, Gurugram",
            tagged_handles=[],
        ),
        RawPublicPost(
            raw_id="RAW-GUR-02",
            platform="X/Twitter",
            author_handle="@HaryanaAlerts",
            author_follower_count=21500,
            posted_at=now_iso,
            text_content="@docagov BRU Instant Coffee shortage in Gurugram! Bought 150g pack, weighs 110g on verified electronic balance. Massive 40g shortage on packaged coffee. Please dispatch inspector.",
            media_urls=["/uploads/Screenshot_2026-09-06-22-06-12-38_92460851df6f172a4592fca41cc2d2e6.jpg"],
            location_tag="Gurugram Cyber Hub",
            tagged_handles=["@docagov"],
        ),
        RawPublicPost(
            raw_id="RAW-MUM-01",
            platform="FoSCoS Portal",
            author_handle="Rakesh K. (Chembur)",
            author_follower_count=15,
            posted_at=now_iso,
            text_content="Retail store in Mumbai selling expired juice bottles. Best Before date has been rubbed off with chemical solvent and stamped with fake 2027 date. FoSCoS license invalid.",
            media_urls=[],
            location_tag="Chembur, Mumbai",
            tagged_handles=["@fssaiindia"],
        ),
        RawPublicPost(
            raw_id="RAW-MUM-02",
            platform="X/Twitter",
            author_handle="@MumbaiWatchdog",
            author_follower_count=35400,
            posted_at=now_iso,
            text_content="Major food safety issue in Dadar Mumbai! Amul milk packets sold after Best Before date with altered ink jet stamps. Severe health risk @foodsafety_mah @fssaiindia",
            media_urls=["/uploads/Screenshot_2026-09-06-22-06-12-38_92460851df6f172a4592fca41cc2d2e6.jpg"],
            location_tag="Dadar, Mumbai",
            tagged_handles=["@foodsafety_mah", "@fssaiindia"],
        ),
        RawPublicPost(
            raw_id="RAW-NASHIK-01",
            platform="X/Twitter",
            author_handle="@Nashik_Civic",
            author_follower_count=4200,
            posted_at=now_iso,
            text_content="Wholesale grain packets in Nashik APMC market found underweight by 800g per 10kg bag. Net quantity declaration missing standard metric symbols under Rule 13. @legalmetrology look into APMC Nashik.",
            media_urls=[],
            location_tag="APMC Market, Nashik",
            tagged_handles=["@legalmetrology"],
        ),
        RawPublicPost(
            raw_id="RAW-NASHIK-02",
            platform="Public Forum",
            author_handle="NashikConsumerHelp",
            author_follower_count=120,
            posted_at=now_iso,
            text_content="Packaged edible oil pouches in Nashik missing mandatory Unit Sale Price (USP) per 100ml. Violation of GSR 779(E) amendment. Retailers charging Rs 165 arbitrary price.",
            media_urls=[],
            location_tag="College Road, Nashik",
            tagged_handles=[],
        ),
        RawPublicPost(
            raw_id="RAW-NAGPUR-01",
            platform="National Consumer Helpline",
            author_handle="Vidarbha Trader Alert",
            author_follower_count=340,
            posted_at=now_iso,
            text_content="In Nagpur Sitabuldi market, Haldiram bhujia snacks being sold with dual MRP tags for train passengers. MRP Rs 50 crossed out with marker, charged Rs 65. Blatant Section 36 overcharging.",
            media_urls=[],
            location_tag="Sitabuldi, Nagpur",
            tagged_handles=[],
        ),
        RawPublicPost(
            raw_id="RAW-NAGPUR-02",
            platform="X/Twitter",
            author_handle="@NagpurCitizenPulse",
            author_follower_count=7800,
            posted_at=now_iso,
            text_content="@jagograhakjago @docagov Haldiram Bhujia snack packets sold above printed MRP at Nagpur Railway platform shop. Stalls refusing to sell at Rs 50 MRP. Please penalize.",
            media_urls=[],
            location_tag="Nagpur Railway Junction",
            tagged_handles=["@jagograhakjago", "@docagov"],
        ),
        RawPublicPost(
            raw_id="RAW-AUR-01",
            platform="X/Twitter",
            author_handle="@MarathwadaVoice",
            author_follower_count=11200,
            posted_at=now_iso,
            text_content="Fake cosmetic hair serums circulating in Chhatrapati Sambhajinagar pharmacies. Packaging mimics Traya Hair Actives but barcode fails check and manufacturer address is fictitious.",
            media_urls=["/uploads/TRAYA BACK.jpg"],
            location_tag="Chhatrapati Sambhajinagar (Aurangabad)",
            tagged_handles=["@consumeraffairs"],
        ),
        RawPublicPost(
            raw_id="RAW-THANE-01",
            platform="X/Twitter",
            author_handle="@ThaneUpdates",
            author_follower_count=18900,
            posted_at=now_iso,
            text_content="Vaseline lotion 400ml bottles sold at Ghodbunder Road supermarket in Thane without Consumer Care toll free number or email. Mandatory under Legal Metrology Rule 6(1)(f).",
            media_urls=[],
            location_tag="Ghodbunder Road, Thane",
            tagged_handles=["@legalmetrology"],
        ),
        RawPublicPost(
            raw_id="RAW-BLR-01",
            platform="X/Twitter",
            author_handle="@LegalConsumer_Ind",
            author_follower_count=9800,
            posted_at=now_iso,
            text_content="New cosmetic hair active lotions being sold across Bangalore retail pharmacies without mandatory Unit Sale Price (USP) per ml. Mandatory under GSR 779(E). Action needed by DLMO.",
            media_urls=[],
            location_tag="Indiranagar, Bangalore",
            tagged_handles=[],
        ),
        RawPublicPost(
            raw_id="RAW-DEL-01",
            platform="National Consumer Helpline",
            author_handle="NCH Grievance #88219",
            author_follower_count=1,
            posted_at=now_iso,
            text_content="Good Knight liquid mosquito refill packs sold at Connaught Place Delhi with tampered hologram and missing month and year of manufacture (MFD).",
            media_urls=[],
            location_tag="Connaught Place, Delhi",
            tagged_handles=[],
        ),
        # Coordinated duplicate to test Deduplication
        RawPublicPost(
            raw_id="RAW-PUNE-01-DUP",
            platform="X/Twitter",
            author_handle="@BotSpamAccount",
            author_follower_count=3,
            posted_at=now_iso,
            text_content="@jagograhakjago @fssaiindia Bought Cadbury Gems packet from market in Pune. MRP sticker Rs 25 pasted over original printed MRP Rs 20! Total overcharging under Section 36(1) LM Act! Please inspect!",
            media_urls=[],
            location_tag="Pune",
            tagged_handles=["@jagograhakjago"],
        ),
    ]


# ---------------------------------------------------------------------------
# Engine Execution: Ingest, Process, Cluster, Prioritize
# ---------------------------------------------------------------------------

def run_intelligence_pipeline() -> List[ProcessedPublicSignal]:
    """
    Executes the entire 13-stage intelligence engine pipeline across the simulated stream.
    Updates in-memory caches and persists state.
    """
    global _SIGNALS_CACHE, _CLUSTERS_CACHE
    _SIGNALS_CACHE.clear()
    _CLUSTERS_CACHE.clear()

    raw_posts = _get_raw_simulated_posts()
    logger.info("Executing Social Intelligence Pipeline on %d public mentions...", len(raw_posts))

    # Pass 1: Text cleaning, NLP classification, entity extraction & deduplication
    seen_hashes: Dict[str, str] = {}  # text_hash -> first mention_id
    cluster_accumulator: Dict[str, List[str]] = {}  # cluster_key -> list of mention_ids
    temp_processed: List[Dict[str, Any]] = []

    for post in raw_posts:
        clean = _clean_and_normalize_text(post.text_content)
        
        # Deduplication check via MD5 normalized text hash
        text_hash = hashlib.md5(re.sub(r"[^\w]", "", clean.lower()).encode("utf-8")).hexdigest()
        is_dup = text_hash in seen_hashes
        parent_id = seen_hashes.get(text_hash)

        m_id = f"SOC-{uuid.uuid4().hex[:6].upper()}"
        if not is_dup:
            seen_hashes[text_hash] = m_id

        # Stages 6, 7, 8: Domain & complaint classification
        is_rel, is_comp, domain, category, conf = _classify_complaint_and_domain(clean)

        # Stage 9: Brand & Product
        brand, prod_name = _extract_brand_product(clean)

        # Stage 10: Location & Geo-Coordinates
        loc_str, city, state, lat, lng = _extract_location_geo(clean, post.location_tag)

        # Stage 11: Authority Tagging
        auth_tags = _extract_authority_tags(clean, post.tagged_handles)

        # Stage 12: Evidence Detection
        has_ev, ev_urls, ev_type = _detect_evidence(post, clean)

        # Cluster Key formulation (brand + city + category)
        cluster_key = f"{city}_{brand or 'COMMODITY'}_{category}".upper().replace(" ", "_")
        if cluster_key not in cluster_accumulator:
            cluster_accumulator[cluster_key] = []
        cluster_accumulator[cluster_key].append(m_id)

        # Correlated Inspection Linking (matching known demo inspection IDs)
        related_insp_id = None
        if brand == "BRU":
            related_insp_id = "64934436:scan-1e48cc41"
        elif brand == "TRAYA":
            related_insp_id = "INSP-88219401"
        elif brand == "GEMS":
            related_insp_id = "INSP-GEMS-PUNE-01"

        temp_processed.append({
            "m_id": m_id,
            "raw_id": post.raw_id,
            "post": post,
            "clean": clean,
            "is_relevant": is_rel,
            "is_complaint": is_comp,
            "domain": domain,
            "category": category,
            "conf": conf,
            "brand": brand,
            "prod_name": prod_name,
            "loc_str": loc_str,
            "city": city,
            "state": state,
            "lat": lat,
            "lng": lng,
            "auth_tags": auth_tags,
            "has_ev": has_ev,
            "ev_urls": ev_urls,
            "ev_type": ev_type,
            "cluster_key": cluster_key,
            "is_dup": is_dup,
            "parent_id": parent_id,
            "related_insp_id": related_insp_id,
        })

    # Pass 2: Dynamic Priority Scoring & Cluster Labeling
    results: List[ProcessedPublicSignal] = []

    for item in temp_processed:
        cluster_key = item["cluster_key"]
        cluster_members = cluster_accumulator.get(cluster_key, [])
        cluster_size = len(cluster_members)
        
        cluster_label = None
        if cluster_size > 1:
            cluster_label = f"Cluster #{cluster_key} ({cluster_size} Public Grievances)"

        # Stage 13: Dynamic priority scoring
        sev, p_score, rationale = _calculate_priority(
            regulatory_domain=item["domain"],
            complaint_category=item["category"],
            has_evidence=item["has_ev"],
            evidence_type=item["ev_type"],
            tagged_authorities=item["auth_tags"],
            author_followers=item["post"].author_follower_count,
            cluster_frequency=cluster_size,
        )

        signal = ProcessedPublicSignal(
            mention_id=item["m_id"],
            raw_id=item["raw_id"],
            source_platform=item["post"].platform,
            author_handle=item["post"].author_handle,
            posted_at=item["post"].posted_at,
            ingested_at=datetime.now().isoformat(),
            raw_text=item["post"].text_content,
            clean_text=item["clean"],
            is_relevant=item["is_relevant"],
            is_complaint=item["is_complaint"],
            regulatory_domain=item["domain"],
            complaint_category=item["category"],
            product_brand=item["brand"],
            product_name=item["prod_name"],
            extracted_location=item["loc_str"],
            district_or_city=item["city"],
            state=item["state"],
            geo_lat=item["lat"],
            geo_lng=item["lng"],
            tagged_authorities=item["auth_tags"],
            has_evidence=item["has_ev"],
            evidence_urls=item["ev_urls"],
            evidence_type=item["ev_type"],
            severity=sev,
            priority_score=p_score,
            prioritization_rationale=rationale,
            confidence_score=item["conf"],
            cluster_id=f"CL-{hashlib.md5(cluster_key.encode()).hexdigest()[:6].upper()}" if cluster_size > 1 else None,
            cluster_label=cluster_label,
            cluster_size=cluster_size,
            is_duplicate=item["is_dup"],
            duplicate_of_id=item["parent_id"],
            related_inspection_id=item["related_insp_id"],
            review_status="SHORTLISTED",
            assigned_officer="inspector",
            data_classification="SIMULATED PUBLIC INTELLIGENCE",
        )

        _SIGNALS_CACHE[signal.mention_id] = signal
        results.append(signal)

    # Sort descending by calculated dynamic priority score
    results.sort(key=lambda s: s.priority_score, reverse=True)

    _save_signals()
    logger.info("Pipeline completed. Generated %d prioritized intelligence signals.", len(results))
    return results


def _load_signals() -> None:
    global _SIGNALS_CACHE
    if STORE_FILE.exists():
        try:
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _SIGNALS_CACHE = {d["mention_id"]: ProcessedPublicSignal(**d) for d in data}
        except Exception as e:
            logger.warning("Could not reload social intelligence signals: %s", e)

    if not _SIGNALS_CACHE:
        run_intelligence_pipeline()


def _save_signals() -> None:
    try:
        data = [s.to_dict() for s in _SIGNALS_CACHE.values()]
        with open(STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error("Could not persist social intelligence signals: %s", e)


# ---------------------------------------------------------------------------
# Query & Retrieval Interfaces
# ---------------------------------------------------------------------------

def list_social_mentions(
    domain: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    city: Optional[str] = None,
    include_duplicates: bool = False,
) -> List[Dict[str, Any]]:
    """Lists shortlisted public cases with multi-factor filtering."""
    _load_signals()
    items = list(_SIGNALS_CACHE.values())

    if not include_duplicates:
        items = [i for i in items if not i.is_duplicate]

    if domain and domain != "ALL":
        items = [i for i in items if domain.lower() in i.regulatory_domain.lower()]
    if severity and severity != "ALL":
        items = [i for i in items if i.severity.upper() == severity.upper()]
    if status and status != "ALL":
        items = [i for i in items if i.review_status.upper() == status.upper()]
    if city and city != "ALL":
        items = [i for i in items if city.lower() in i.district_or_city.lower()]

    # Sort by priority score descending
    items.sort(key=lambda x: x.priority_score, reverse=True)
    return [i.to_dict() for i in items]


def update_mention_status(
    mention_id: str,
    new_status: str,
    officer_notes: Optional[str] = None,
    linked_case_id: Optional[str] = None,
    assigned_officer: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Human review decision: convert to formal docket, assign inspector, or dismiss."""
    _load_signals()
    if mention_id not in _SIGNALS_CACHE:
        return None

    m = _SIGNALS_CACHE[mention_id]
    m.review_status = new_status
    if officer_notes:
        m.officer_notes = officer_notes
    if linked_case_id:
        m.related_inspection_id = linked_case_id
    if assigned_officer:
        m.assigned_officer = assigned_officer

    _save_signals()
    return m.to_dict()


# ---------------------------------------------------------------------------
# Grounded AI Regional Intelligence Summary (EN / HI / MR)
# ---------------------------------------------------------------------------

def get_social_intelligence_summary(language: str = "en") -> Dict[str, Any]:
    """
    Computes grounded statistics strictly from the processed dataset.
    Answers:
    - Number of public signals per region
    - Shortlisted cases
    - High-risk clusters
    - Regulatory domain breakdown
    - Grounded AI narrative in EN / HI / MR
    """
    _load_signals()
    signals = [s for s in _SIGNALS_CACHE.values() if not s.is_duplicate]

    total_signals = len(signals)
    city_counts: Dict[str, int] = {}
    domain_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    cluster_groups: Dict[str, List[Dict[str, Any]]] = {}

    for s in signals:
        city_counts[s.district_or_city] = city_counts.get(s.district_or_city, 0) + 1
        domain_counts[s.regulatory_domain] = domain_counts.get(s.regulatory_domain, 0) + 1
        category_counts[s.complaint_category] = category_counts.get(s.complaint_category, 0) + 1

        if s.cluster_label:
            if s.cluster_label not in cluster_groups:
                cluster_groups[s.cluster_label] = []
            cluster_groups[s.cluster_label].append({
                "mention_id": s.mention_id,
                "author": s.author_handle,
                "city": s.district_or_city,
                "brand": s.product_brand,
                "priority_score": s.priority_score,
            })

    top_city = max(city_counts.items(), key=lambda x: x[1])[0] if city_counts else "Pune"
    top_city_count = city_counts.get(top_city, 0)
    top_category = max(category_counts.items(), key=lambda x: x[1])[0] if category_counts else "Overcharging / Dual MRP"

    # Multilingual AI Grounded Narrative
    if language == "mr":
        ai_summary = (
            f"📡 **सार्वजनिक सोशल मीडिया गुप्तवार्ता विश्लेषण (Simulated Public Intelligence)**:\n"
            f"• या कालावधीत एकूण **{total_signals} सार्वजनिक तक्रारी** प्रक्रिया करण्यात आल्या असून त्यापैकी बहुतांश **{top_city}** परिक्षेत्रातून ({top_city_count} तक्रारी) आल्या आहेत.\n"
            f"• **{top_category}** या श्रेणीतील तक्रारींचे प्रमाण सर्वाधिक आहे.\n"
            f"• **{len(cluster_groups)} सक्रिय क्लस्टर** ओळखले गेले आहेत, ज्यामध्ये एकाच ब्रँड आणि किरकोळ विक्रेत्याविरुद्ध वारंवार सार्वजनिक तक्रारी नोंदविल्या गेल्या आहेत.\n"
            f"• वरिष्ठ अधिकाऱ्यांना या क्लस्टर प्रकरणांची तात्काळ खातरजमा करून प्रत्यक्ष तपासणी पथके पाठवण्याची शिफारस करण्यात येत आहे."
        )
    elif language == "hi":
        ai_summary = (
            f"📡 **सार्वजनिक सोशल मीडिया आसूचना विश्लेषण (Simulated Public Intelligence)**:\n"
            f"• इस अवधि के दौरान कुल **{total_signals} सार्वजनिक शिकायत सिग्नल्स** विश्लेषित किए गए, जिनमें सर्वाधिक सिग्नल्स **{top_city}** क्षेत्र ({top_city_count} मामले) से प्राप्त हुए हैं।\n"
            f"• मुख्य श्रेणी: **{top_category}** से संबंधित सार्वजनिक शिकायतें सबसे अधिक हैं।\n"
            f"• प्रणाली ने **{len(cluster_groups)} हॉटस्पॉट क्लस्टर** चिन्हित किए हैं जहाँ एक ही उत्पाद/विक्रेता के विरुद्ध एकाधिक उपभोक्ताओं ने साक्ष्य सहित रिपोर्ट की है।\n"
            f"• विधिक मापविज्ञान अधिकारियों को उच्च प्राथमिकता वाले क्लस्टर मामलों में संज्ञान लेकर औचक निरीक्षण के निर्देश दिए जाते हैं।"
        )
    else:
        ai_summary = (
            f"📡 **Public Grievance & Social Intelligence Synthesis (DEMO INTELLIGENCE)**:\n"
            f"• Most shortlisted signals ({top_city_count} posts) originated from the **{top_city}** region, with **{top_category}** forming the largest complaint category.\n"
            f"• System has isolated **{len(cluster_groups)} distinct grievance clusters** sharing common product, brand, and retail patterns.\n"
            f"• High-priority cases have corroborating physical evidence (weighing scale photos, duplicate MRP stickers) and authority escalations.\n"
            f"• Recommendation: Authorize field inspection squads to verify highlighted retail clusters before formal prosecution under Section 36(1)."
        )

    # Active clusters list for UI
    active_clusters = [
        {
            "cluster_label": lbl,
            "count": len(items),
            "members": items,
        }
        for lbl, items in cluster_groups.items()
    ]

    return {
        "data_classification": "SIMULATED PUBLIC INTELLIGENCE",
        "total_signals_analyzed": total_signals,
        "region_breakdown": [{"city": k, "count": v} for k, v in sorted(city_counts.items(), key=lambda x: x[1], reverse=True)],
        "domain_distribution": domain_counts,
        "category_distribution": category_counts,
        "active_clusters": active_clusters,
        "top_region": top_city,
        "top_category": top_category,
        "ai_regional_summary": ai_summary,
        "timestamp": datetime.now().isoformat(),
    }
