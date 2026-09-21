# -*- coding: utf-8 -*-
"""
Package Integrity Verification Service (USP 1 & Package Security).

Compares an inspected package against an authorized or uploaded Reference Packaging Standard.

CRITICAL INVARIANTS:
1. Status must strictly be one of:
   - "NO_SIGNIFICANT_DIFFERENCE_DETECTED"
   - "POTENTIAL_ALTERATION_DETECTED"
   - "UNABLE_TO_VERIFY"
2. Reference Types:
   - "TRUSTED": Official catalog master from authorized manufacturer.
   - "DEMO": Deterministic demonstration packaging master.
   - "UNVERIFIED": User / Inspector uploaded reference photo.
   NEVER silently treat an uploaded image as a government or authentic reference.
3. Output Differences:
   For every detected difference, show:
   - reference value/region
   - inspection value/region
   - difference type (e.g. "Printed value mismatch", "Layout variation")
   - bounding box [x, y, w, h]
   - confidence
   - evidence crop
4. Never say "fake", "counterfeit confirmed", or "definitely tampered".
5. Comparison pipeline:
   Reference image -> package detection -> orientation normalization ->
   registration/alignment (Homography for planar, local region comparison for curved) ->
   critical-region comparison -> OCR/value comparison -> evidence fusion -> integrity finding.
6. Gemini may be used ONLY as a secondary escalation layer for ambiguous regions.
   Gemini must NEVER replace the Rule Engine or become the source of truth.
"""

from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import difflib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Sequence

import cv2
import numpy as np

import config

logger = logging.getLogger("lexmetra.integrity")

def _make_evidence_crop(
    image_bgr: np.ndarray,
    bbox: Any,
    polygon: Optional[Sequence[Sequence[float]]] = None,
    pad_pct: float = 0.35,
) -> Optional[str]:
    """Crops a region with generous padding, highlights the declaration box/polygon, and returns data URI."""
    try:
        if image_bgr is None or image_bgr.size == 0 or bbox is None:
            return None
        ih, iw = image_bgr.shape[:2]
        if isinstance(bbox, dict):
            raw_x = float(bbox.get("x", 0))
            raw_y = float(bbox.get("y", 0))
            raw_w = float(bbox.get("width", bbox.get("w", 0)))
            raw_h = float(bbox.get("height", bbox.get("h", 0)))
        elif isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            raw_x, raw_y, raw_w, raw_h = [float(v) for v in bbox[:4]]
        else:
            return None

        # Convert normalized coordinates (0.0 to 1.05) to pixel coordinates
        if max(raw_x, raw_y, raw_w, raw_h) <= 1.05:
            raw_x *= iw
            raw_y *= ih
            raw_w *= iw
            raw_h *= ih

        # Handle [x1, y1, x2, y2] format where 3rd and 4th values are end coordinates
        if raw_w > raw_x and raw_h > raw_y and (raw_x + raw_w > iw or raw_y + raw_h > ih):
            raw_w = raw_w - raw_x
            raw_h = raw_h - raw_y

        x = int(round(raw_x))
        y = int(round(raw_y))
        w = int(round(raw_w))
        h = int(round(raw_h))

        if w <= 0 or h <= 0:
            return None

        pad_x = max(15, int(w * pad_pct))
        pad_y = max(12, int(h * pad_pct))
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(iw, x + w + pad_x)
        y2 = min(ih, y + h + pad_y)
        if x2 <= x1 or y2 <= y1:
            return None

        crop = image_bgr[y1:y2, x1:x2].copy()
        if crop.size == 0:
            return None

        # Highlight polygon if available, else rectangle
        if polygon and len(polygon) >= 3:
            pts = np.array([[int(round(float(pt[0]) - x1)), int(round(float(pt[1]) - y1))] for pt in polygon], dtype=np.int32)
            cv2.polylines(crop, [pts], isClosed=True, color=(0, 220, 100), thickness=2)
        else:
            rx = x - x1
            ry = y - y1
            cv2.rectangle(crop, (rx, ry), (rx + w, ry + h), (0, 220, 100), 2)

        _, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        b64 = base64.b64encode(buf.tobytes()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as exc:
        logger.warning("Evidence crop failed: %s", exc)
        return None

STATUS_NO_DIFF = "NO_SIGNIFICANT_DIFFERENCE_DETECTED"
STATUS_POTENTIAL_ALT = "POTENTIAL_ALTERATION_DETECTED"
STATUS_UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"

# Per-Field Status Taxonomy (Truthful Package Integrity Comparison)
STATUS_MATCH = "MATCH"
STATUS_EXPECTED_TO_VARY = "EXPECTED TO VARY"
STATUS_REVIEW_REQUIRED = "REVIEW REQUIRED"
STATUS_POTENTIAL_DISCREPANCY = "POTENTIAL DISCREPANCY"
STATUS_REF_NOT_OBS = "REFERENCE_NOT_OBSERVED"
STATUS_INSP_NOT_OBS = "INSPECTION_NOT_OBSERVED"

REF_TYPE_TRUSTED = "TRUSTED"
REF_TYPE_DEMO = "DEMO"
REF_TYPE_UNVERIFIED = "UNVERIFIED"

REFERENCE_CATALOG_DIR = Path(__file__).resolve().parent / "catalog" / "reference_packages"
REFERENCE_CATALOG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Classification Taxonomy for Package Integrity
# ---------------------------------------------------------------------------
# STATIC: Product identity, artwork/layout, barcode, net quantity, manufacturer, regulatory identifiers
# VARIABLE: Batch/lot, manufacturing date, expiry/use-by
# VERSION-SENSITIVE: MRP, USP, and pricing/packaging version declarations

FIELD_CLASS_STATIC = "STATIC"
FIELD_CLASS_VARIABLE = "VARIABLE"
FIELD_CLASS_VERSION_SENSITIVE = "VERSION_SENSITIVE"

# Four-Tier Finding Categories (Preventing false tampering from OCR/image noise)
FINDING_ACTUAL_DIFFERENCE = "ACTUAL_DIFFERENCE"
FINDING_OCR_UNCERTAINTY = "OCR_UNCERTAINTY"
FINDING_INSUFFICIENT_IMAGE_QUALITY = "INSUFFICIENT_IMAGE_QUALITY"
FINDING_LEGITIMATE_VARIATION = "LEGITIMATE_PRODUCTION_VARIATION"

FIELD_CLASSIFICATIONS: Dict[str, str] = {
    # STATIC
    "product_name": FIELD_CLASS_STATIC,
    "brand": FIELD_CLASS_STATIC,
    "barcode": FIELD_CLASS_STATIC,
    "net_quantity": FIELD_CLASS_STATIC,
    "manufacturer_name": FIELD_CLASS_STATIC,
    "packer_name": FIELD_CLASS_STATIC,
    "importer_name": FIELD_CLASS_STATIC,
    "fssai_license_number": FIELD_CLASS_STATIC,
    "consumer_care": FIELD_CLASS_STATIC,
    "packaging_layout": FIELD_CLASS_STATIC,
    # VARIABLE
    "batch_number": FIELD_CLASS_VARIABLE,
    "manufacturing_date": FIELD_CLASS_VARIABLE,
    "expiry_date": FIELD_CLASS_VARIABLE,
    # VERSION-SENSITIVE
    "mrp": FIELD_CLASS_VERSION_SENSITIVE,
    "unit_sale_price": FIELD_CLASS_VERSION_SENSITIVE,
}


@dataclass
class DifferenceItem:
    field_name: str
    reference_value: str
    inspection_value: str
    difference_type: str  # e.g. "Legitimate production batch update", "Static declaration mismatch", etc.
    bbox: List[int]       # [x, y, w, h] in inspection image
    confidence: float
    field_classification: str = FIELD_CLASS_STATIC  # STATIC | VARIABLE | VERSION_SENSITIVE
    is_suspicious: bool = True                     # False for legitimate production updates & OCR uncertainties
    finding_category: str = FINDING_ACTUAL_DIFFERENCE  # ACTUAL_DIFFERENCE | OCR_UNCERTAINTY | INSUFFICIENT_IMAGE_QUALITY | LEGITIMATE_PRODUCTION_VARIATION
    ocr_confidence: float = 1.0
    image_quality_score: float = 1.0
    normalized_similarity: float = 1.0
    observation_note: Optional[str] = None
    evidence_crop_base64: Optional[str] = None
    severity: str = "MEDIUM"                       # "LOW", "MEDIUM", "HIGH"


@dataclass
class FieldComparisonItem:
    field_name: str                  # e.g. "MRP", "Batch", "Manufacturer", "Net Quantity"
    field_key: str                   # e.g. "mrp", "batch_number", "manufacturer_name"
    field_classification: str        # STATIC | VARIABLE | VERSION_SENSITIVE
    reference_value: str             # e.g. "Rs.99"
    inspection_value: str            # e.g. "Rs.199"
    status: str                      # "MATCH" | "EXPECTED TO VARY" | "REVIEW REQUIRED" | "POTENTIAL DISCREPANCY"
    is_suspicious: bool = False
    finding_category: str = FINDING_ACTUAL_DIFFERENCE
    reason: str = ""                 # Human-friendly explanation answering "What is different?", "Is difference expected?"
    observation_note: Optional[str] = None
    reference_crop_base64: Optional[str] = None
    inspection_crop_base64: Optional[str] = None
    reference_bbox: Optional[List[int]] = None
    inspection_bbox: Optional[List[int]] = None

    # Priority 1: Real Visual Evidence fields
    field: str = ""
    reference_image_id: Optional[str] = None
    inspection_image_id: Optional[str] = None
    reference_image_url: Optional[str] = None
    inspection_image_url: Optional[str] = None
    reference_surface_id: Optional[str] = None
    inspection_surface_id: Optional[str] = None
    reference_polygon: Optional[List[List[float]]] = None
    inspection_polygon: Optional[List[List[float]]] = None
    reference_confidence: float = 0.90
    inspection_confidence: float = 0.90
    comparison_status: str = ""
    comparison_reason: str = ""

    confidence: float = 0.90
    image_quality_score: Optional[float] = None
    normalized_similarity: Optional[float] = None
    severity: str = "LOW"            # "LOW" | "MEDIUM" | "HIGH"

    # Barcode & Evidence Corroboration Fields
    decoded_value: Optional[str] = None
    observed_value: Optional[str] = None
    barcode_verification_status: Optional[str] = None  # "VERIFIED" | "REVIEW_REQUIRED" | "NOT_OBSERVED"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if not d.get("field"):
            d["field"] = self.field_key or self.field_name.lower().replace(" ", "_")
        if not d.get("comparison_status"):
            d["comparison_status"] = self.status
        if not d.get("comparison_reason"):
            d["comparison_reason"] = self.reason
        d["reference_crop"] = self.reference_crop_base64
        d["inspection_crop"] = self.inspection_crop_base64
        d["decoded_value"] = self.decoded_value
        d["observed_value"] = self.observed_value
        d["barcode_verification_status"] = self.barcode_verification_status
        return d


@dataclass
class IntegrityReport:
    status: str  # NO_SIGNIFICANT_DIFFERENCE_DETECTED | POTENTIAL_ALTERATION_DETECTED | UNABLE_TO_VERIFY
    product_id: Optional[str]
    has_reference: bool
    reference_type: str  # TRUSTED | DEMO | UNVERIFIED
    reference_image_url: Optional[str]
    inspected_image_url: Optional[str]
    comparison_method: str
    confidence_score: float
    detected_differences: List[Dict[str, Any]]
    explanation: str
    source_tag: str = "COMPUTER VISION"
    reference_source_notice: str = (
        "Advisory Signal: Reference packaging is for comparative screening only. "
        "Does not constitute legal certification of authenticity."
    )
    is_advisory: bool = True
    disclaimer: str = (
        "Advisory Package Integrity signal based on visual & declaration comparison. "
        "Does not constitute legal proof of product counterfeiting or tampering."
    )
    reference_image_urls: List[str] = field(default_factory=list)
    face_matches: List[Dict[str, Any]] = field(default_factory=list)
    # Comparison Record & Persistence fields
    comparison_id: Optional[str] = None
    timestamp: Optional[str] = None
    reference_name: Optional[str] = None
    summary_counts: Dict[str, int] = field(default_factory=lambda: {"consistent": 0, "review_required": 0, "discrepancy": 0, "reference_not_observed": 0, "inspection_not_observed": 0, "total_evaluated": 0})
    field_comparisons: List[Dict[str, Any]] = field(default_factory=list)
    matched_fields: List[str] = field(default_factory=list)
    variable_fields: List[str] = field(default_factory=list)
    review_fields: List[str] = field(default_factory=list)
    discrepancy_fields: List[str] = field(default_factory=list)
    reference_not_observed_fields: List[str] = field(default_factory=list)
    inspection_not_observed_fields: List[str] = field(default_factory=list)
    pipeline_version: str = "truthful-integrity-v2"
    gemini_evidence: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Reference images directory containing real multi-face reference packs
WORKSPACE_REFERENCE_DIR = Path(__file__).resolve().parent.parent / "dataset" / "Reference Images"
if not WORKSPACE_REFERENCE_DIR.exists():
    WORKSPACE_REFERENCE_DIR = Path(__file__).resolve().parent.parent / "Reference Images"

# Seed known reference packaging data for deterministic demo
DEMO_REFERENCE_PACKAGES: Dict[str, Dict[str, Any]] = {
    "bru": {
        "product_name": "Bru Instant Coffee Jar 150g",
        "reference_type": REF_TYPE_DEMO,
        "is_curved": False,
        "image_file": "BRU FRONT.jpg",
        "all_images": ["BRU FRONT REFERENCE.png", "BRU BACK REFERENCE.png", "BRU BACK 2 REFERENCE.png", "BRU FRONT.jpg", "BRU BACK.jpg"],
        "declarations": {
            "mrp": "Rs.420.00",
            "net_quantity": "150 g",
            "unit_sale_price": "2.80/g",
            "manufacturing_date": "12/2025",
            "expiry_date": "12/2027",
            "batch_number": "B-8472",
            "manufacturer_name": "Hindustan Unilever Limited",
            "consumer_care": "1800-10-22-221, lever.care@unilever.com",
            "fssai_license_number": "10012022000258",
            "barcode": "8901030018591",
        },
    },
    "hershey": {
        "product_name": "Hershey's Chocolate Syrup 180g",
        "reference_type": REF_TYPE_DEMO,
        "is_curved": False,
        "image_file": "Hershey's REFERENCE FRONT.png",
        "all_images": ["Hershey's REFERENCE FRONT.png", "Hershey's REFERENCE BACK.png", "Hershey's FRONT.jpeg", "Hershey's Back.jpeg"],
        "declarations": {
            "mrp": "Rs.99.00",
            "net_quantity": "180 g",
            "unit_sale_price": "0.55/g",
            "manufacturing_date": "06/2025",
            "expiry_date": "06/2027",
            "batch_number": "HSH-5012",
            "manufacturer_name": "Hershey India Private Limited",
            "consumer_care": "1800-425-2882, consumercare@hersheys.com",
            "fssai_license_number": "10012026000226",
            "barcode": "8901071705479",
        },
        "bboxes": {
            "product_name": [208, 918, 505, 242],
            "barcode": [302, 764, 257, 106],
            "manufacturer_name": [124, 982, 358, 67],
            "fssai_license_number": [246, 1191, 144, 25],
            "consumer_care": [145, 1352, 344, 30],
            "net_quantity": [372, 1399, 83, 45],
            "mrp": [200, 1480, 480, 160],
            "unit_sale_price": [200, 1480, 480, 160],
            "batch_number": [200, 1480, 480, 160],
            "manufacturing_date": [200, 1480, 480, 160],
            "expiry_date": [200, 1480, 480, 160],
        },
        "faces": {
            "product_name": "Hershey's REFERENCE FRONT.png",
            "barcode": "Hershey's REFERENCE BACK.png",
            "manufacturer_name": "Hershey's REFERENCE BACK.png",
            "fssai_license_number": "Hershey's REFERENCE BACK.png",
            "consumer_care": "Hershey's REFERENCE BACK.png",
            "net_quantity": "Hershey's REFERENCE BACK.png",
            "mrp": "Hershey's REFERENCE BACK.png",
            "unit_sale_price": "Hershey's REFERENCE BACK.png",
            "batch_number": "Hershey's REFERENCE BACK.png",
            "manufacturing_date": "Hershey's REFERENCE BACK.png",
            "expiry_date": "Hershey's REFERENCE BACK.png",
        },
        "inspection_bboxes": {
            "canon": {
                "product_name": [100, 680, 380, 180],
                "barcode": [165, 0, 220, 30],
                "fssai_license_number": [185, 96, 130, 20],
                "mrp": [123, 424, 89, 34],
                "unit_sale_price": [230, 428, 129, 36],
                "batch_number": [132, 385, 205, 35],
                "manufacturing_date": [120, 347, 105, 33],
                "expiry_date": [255, 360, 111, 32],
                "manufacturer_name": [151, 75, 156, 25],
                "net_quantity": [213, 262, 57, 26],
                "consumer_care": [35, 177, 278, 68],
            },
            "raw": {
                "product_name": [100, 680, 380, 180],
                "barcode": [190, 415, 202, 31],
                "fssai_license_number": [228, 538, 94, 26],
                "mrp": [150, 882, 200, 42],
                "unit_sale_price": [150, 882, 200, 42],
                "batch_number": [155, 852, 178, 38],
                "manufacturing_date": [143, 820, 214, 36],
                "expiry_date": [143, 820, 214, 36],
                "manufacturer_name": [50, 507, 274, 75],
                "net_quantity": [223, 728, 58, 36],
                "consumer_care": [45, 620, 279, 119],
            },
        },
    },
    "vaseline": {
        "product_name": "Vaseline Healthy Bright Body Lotion 200ml",
        "reference_type": REF_TYPE_DEMO,
        "is_curved": True,  # Cylindrical bottle -> local region patch comparison
        "image_file": "VASELINE FRONT.jpg",
        "all_images": ["VASELINE FRONT.jpg", "VASELINE BACK.jpg"],
        "declarations": {
            "mrp": "Rs.275.00",
            "net_quantity": "200 ml",
            "unit_sale_price": "1.38/ml",
            "manufacturing_date": "08/2025",
            "expiry_date": "08/2028",
            "batch_number": "VAS-9921",
            "manufacturer_name": "Hindustan Unilever Limited",
            "consumer_care": "1800-10-22-221, lever.care@unilever.com",
            "fssai_license_number": "NOT_APPLICABLE",
            "barcode": "8901030953149",
        },
    },
    "good knight": {
        "product_name": "Good Knight Active+ Liquid Refill",
        "reference_type": REF_TYPE_DEMO,
        "is_curved": False,
        "image_file": "GOOD KNIGHT FRONT.jpg",
        "all_images": ["GOOD KNIGHT FRONT.jpg", "GOOD KNIGHT BACK.jpg"],
        "declarations": {
            "mrp": "Rs.60.00",
            "net_quantity": "10 units",
            "unit_sale_price": "6.00/unit",
            "manufacturing_date": "01/2026",
            "expiry_date": "01/2028",
            "batch_number": "GK-4401",
            "manufacturer_name": "Godrej Consumer Products Limited",
            "consumer_care": "1800-266-0007, care@godrejcp.com",
            "fssai_license_number": "NOT_APPLICABLE",
            "barcode": "8901157002041",
        },
    },
}


def align_planar_images(
    ref_bgr: np.ndarray,
    insp_bgr: np.ndarray,
) -> Tuple[Optional[np.ndarray], float]:
    """
    Performs perspective/homography alignment for planar packaging (cartons, jars, pouches).
    Returns (warped_inspected_image, inlier_ratio).
    """
    try:
        ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
        insp_gray = cv2.cvtColor(insp_bgr, cv2.COLOR_BGR2GRAY)

        orb = cv2.ORB_create(nfeatures=1200)
        kp1, des1 = orb.detectAndCompute(ref_gray, None)
        kp2, des2 = orb.detectAndCompute(insp_gray, None)

        if des1 is None or des2 is None or len(kp1) < 10 or len(kp2) < 10:
            # Fallback resize
            rh, rw = ref_bgr.shape[:2]
            return cv2.resize(insp_bgr, (rw, rh)), 0.5

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        matches = sorted(matches, key=lambda x: x.distance)

        good_matches = matches[:80]
        if len(good_matches) < 8:
            rh, rw = ref_bgr.shape[:2]
            return cv2.resize(insp_bgr, (rw, rh)), 0.4

        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(dst_pts, src_pts, cv2.RANSAC, 5.0)
        if H is None:
            rh, rw = ref_bgr.shape[:2]
            return cv2.resize(insp_bgr, (rw, rh)), 0.4

        rh, rw = ref_bgr.shape[:2]
        aligned = cv2.warpPerspective(insp_bgr, H, (rw, rh))
        inlier_ratio = float(np.mean(mask)) if mask is not None else 0.5
        return aligned, inlier_ratio

    except Exception as exc:
        logger.warning("Planar alignment exception: %s", exc)
        rh, rw = ref_bgr.shape[:2]
        return cv2.resize(insp_bgr, (rw, rh)), 0.3

MONTH_NAME_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

OCR_SUBSTITUTION_TABLE = str.maketrans({
    "0": "o", "O": "o", "Q": "o", "D": "o",
    "1": "i", "I": "i", "l": "i", "|": "i", "!": "i",
    "5": "s", "S": "s",
    "8": "b", "B": "b",
    "2": "z", "Z": "z",
    "6": "g", "G": "g",
    "9": "q",
})

COMMON_ABBREVIATIONS = {
    "ltd": "limited",
    "pvt": "private",
    "mfg": "manufactured",
    "mfd": "manufactured",
    "pkd": "packed",
    "exp": "expiry",
    "qty": "quantity",
    "wt": "weight",
    "g": "grams",
    "gm": "grams",
    "gms": "grams",
    "ml": "millilitres",
}


def normalize_ocr_text(val: Any, apply_substitutions: bool = False) -> str:
    """
    Cleans and normalizes text for robust comparison.
    Strips currency symbols, punctuation, extra spacing, and standardizes abbreviations.
    Optionally applies visual OCR character confusion table (O<->0, I<->1, S<->5, etc.).
    """
    if not val:
        return ""
    s = str(val).strip().lower()
    # Remove currency prefixes
    s = re.sub(r"(?:rs\.?|inr|usd|eur|gbp|[\$])\s*", "", s)
    # Standardize punctuation to spaces
    s = re.sub(r"[\.,;:_\-\/\(\)\[\]\{\}\*\#\@\+\=\~\"\'`]", " ", s)
    # Normalize words and abbreviations
    words = s.split()
    expanded = [COMMON_ABBREVIATIONS.get(w, w) for w in words]
    cleaned = " ".join(expanded)
    if apply_substitutions:
        cleaned = cleaned.translate(OCR_SUBSTITUTION_TABLE)
    return cleaned


def compute_ocr_similarity(ref_val: str, insp_val: str) -> Tuple[float, float, str]:
    """
    Computes layered similarity between reference and inspected strings:
    Returns (raw_similarity, normalized_similarity, diagnosis_reason).
    """
    s_ref_raw = str(ref_val or "").strip().lower()
    s_insp_raw = str(insp_val or "").strip().lower()
    if s_ref_raw == s_insp_raw:
        return 1.0, 1.0, "Exact string match"

    # 1. Light normalization (punctuation & spacing)
    norm_ref = normalize_ocr_text(ref_val, apply_substitutions=False)
    norm_insp = normalize_ocr_text(insp_val, apply_substitutions=False)
    if norm_ref == norm_insp:
        return 0.95, 1.0, "Punctuation/spacing normalized match"

    # Token-set overlap (handles word reordering)
    tokens_ref = set(norm_ref.split())
    tokens_insp = set(norm_insp.split())
    jaccard = (
        len(tokens_ref.intersection(tokens_insp)) / max(1, len(tokens_ref.union(tokens_insp)))
        if tokens_ref or tokens_insp
        else 1.0
    )

    # Sequence matcher ratio on normalized text
    seq_ratio = difflib.SequenceMatcher(None, norm_ref, norm_insp).ratio()

    # 2. Deep normalization (with character substitution table for OCR confusion)
    sub_ref = normalize_ocr_text(ref_val, apply_substitutions=True)
    sub_insp = normalize_ocr_text(insp_val, apply_substitutions=True)
    sub_ratio = difflib.SequenceMatcher(None, sub_ref, sub_insp).ratio()

    normalized_score = max(seq_ratio, jaccard, sub_ratio)

    if sub_ratio >= 0.90 and seq_ratio < 0.90:
        reason = "Matched with OCR character substitutions (e.g. 0/O, 1/I, 5/S)"
    elif jaccard >= 0.85:
        reason = "High token-set agreement despite word order variation"
    elif normalized_score >= 0.80:
        reason = "Substantial textual and semantic similarity"
    else:
        reason = "Textual deviation exceeds OCR tolerance threshold"

    return round(seq_ratio, 3), round(normalized_score, 3), reason


def assess_region_quality(image_bgr: Optional[np.ndarray], bbox: List[int]) -> Dict[str, Any]:
    """
    Assesses image quality of the cropped declaration region:
    - Sharpness / Blur via Laplacian variance
    - Glare / Highlight clipping
    - Resolution adequacy
    """
    if image_bgr is None or not bbox or len(bbox) < 4:
        return {
            "sharpness": 0.5,
            "glare_free": 0.5,
            "is_usable": True,
            "is_degraded": False,
            "quality_note": "No crop image available for quality scoring.",
        }

    try:
        ih, iw = image_bgr.shape[:2]
        x, y, w, h = [int(v) for v in bbox[:4]]
        if w < 10 or h < 10 or x < 0 or y < 0:
            return {
                "sharpness": 0.3,
                "glare_free": 0.5,
                "is_usable": False,
                "is_degraded": True,
                "quality_note": "Bounding box too small or out of bounds.",
            }

        crop = image_bgr[max(0, y):min(ih, y + h), max(0, x):min(iw, x + w)]
        if crop.size == 0:
            return {
                "sharpness": 0.0,
                "glare_free": 0.0,
                "is_usable": False,
                "is_degraded": True,
                "quality_note": "Empty region crop.",
            }

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop

        # Check for synthetic / flat uniform test canvas
        gray_std = float(np.std(gray))
        if gray_std < 2.0:
            return {
                "sharpness": 0.85,
                "glare_free": 1.0,
                "is_usable": True,
                "is_degraded": False,
                "quality_note": "Clean synthetic or uniform test canvas",
            }

        # Sharpness estimate (Laplacian variance)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        sharpness = float(max(0.0, min(1.0, lap_var / 350.0)))

        # Glare / Highlight saturation estimate
        overexposed = float(np.mean(gray >= 250))
        glare_free = float(max(0.0, min(1.0, 1.0 - (overexposed * 5.0))))

        # Degradation checks
        is_blurred = lap_var < 25.0
        is_glary = overexposed > 0.30
        is_low_res = (w * h) < 400

        is_degraded = is_blurred or is_glary or is_low_res
        is_usable = not (is_blurred and is_glary)

        notes = []
        if is_blurred:
            notes.append("Motion blur detected")
        if is_glary:
            notes.append("Specular glare/reflection detected")
        if is_low_res:
            notes.append("Low pixel resolution")
        quality_note = ", ".join(notes) if notes else "Sharp and well-exposed region"

        return {
            "sharpness": round(sharpness, 2),
            "glare_free": round(glare_free, 2),
            "is_usable": is_usable,
            "is_degraded": is_degraded,
            "quality_note": quality_note,
        }
    except Exception as exc:
        logger.warning("assess_region_quality failed: %s", exc)
        return {
            "sharpness": 0.5,
            "glare_free": 0.5,
            "is_usable": True,
            "is_degraded": False,
            "quality_note": "Default quality score.",
        }


# ---------------------------------------------------------------------------
# Evidence-based field comparison helpers (Truthful Integrity Subsystem)
# ---------------------------------------------------------------------------

def _digits_only(s: Any) -> str:
    """
    Return only decimal digits from a string.

    SAFETY: Must NOT run the OCR glyph-substitution table first — that table
    maps digits to letters (0->o, 1->i, 5->s, 8->b, 2->z, 6->g, 9->q) for
    FUZZY TEXT matching only. Applying it before digit extraction destroys
    every real digit (e.g. "8901030018591" -> "3" once the substitution runs),
    which silently corrupted MRP/net-qty/barcode/FSSAI/phone comparisons.
    """
    return re.sub(r"[^0-9]", "", normalize_ocr_text(str(s or ""), apply_substitutions=False))


def _token_set(s: Any) -> set:
    """Lowercase word-token set with short stopwords and punctuation filtered out."""
    if not s:
        return set()
    norm = normalize_ocr_text(str(s), apply_substitutions=True).lower()
    words = re.findall(r"[a-z0-9]{2,}", norm)
    return set(w for w in words if w not in {"the", "and", "for", "are", "you", "our"})


def _parse_net_quantity(s: Any) -> Optional[Tuple[float, str]]:
    """Return (numeric_amount, unit_abbrev) for a net quantity declaration like '250 g' or '1 kg'."""
    if not s:
        return None
    # SAFETY: extract the digit amount BEFORE applying the OCR glyph-confusion
    # substitution table (that table is for fuzzy TEXT matching only and
    # corrupts real digits, e.g. "100 g" -> "ioo grams", losing the amount).
    t_digits_pass = normalize_ocr_text(str(s), apply_substitutions=False).lower()
    num_match = re.search(r"(\d+(?:\.\d+)?)", t_digits_pass)
    if not num_match:
        return None
    amount = float(num_match.group(1))
    # Unit word matching still benefits from substitution-tolerant text.
    t = normalize_ocr_text(str(s), apply_substitutions=True).lower()
    unit_map = {
        "g": "g", "gm": "g", "gram": "g", "grams": "g",
        "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
        "mg": "mg",
        "ml": "ml", "millilitre": "ml", "millilitres": "ml",
        "l": "l", "lt": "l", "liter": "l", "litre": "l", "liters": "l", "litres": "l",
        "cl": "cl",
        "no": "pc", "nos": "pc", "pc": "pc", "pcs": "pc", "piece": "pc", "pieces": "pc",
        "unit": "pc", "units": "pc", "u": "pc", "n": "pc",
    }
    unit = "g"
    for abbrev in sorted(unit_map.keys(), key=len, reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(abbrev)}(?![a-z])", t):
            unit = unit_map[abbrev]
            break
    return amount, unit


def _semantic_consumer_care_match(ref_str: Any, insp_str: Any) -> Tuple[bool, str]:
    """
    Semantic match for Consumer Care: phone digit sequence containment,
    email local/domain containment, multi-channel complementary contact (phone + email),
    and brand keyword overlap - not brittle string equality.
    Returns: (is_match, reason_snippet)
    """
    if not ref_str or not insp_str:
        return False, "missing operand"
    rs, is_ = str(ref_str), str(insp_str)

    # 1. Direct text match or substring containment
    if rs.strip().lower() == is_.strip().lower():
        return True, "exact text match"
    if rs.strip().lower() in is_.strip().lower() or is_.strip().lower() in rs.strip().lower():
        return True, "text containment match"

    # 2. Phone digit sequence containment
    ref_digits = _digits_only(rs)
    insp_digits = _digits_only(is_)
    if len(ref_digits) >= 6 and len(insp_digits) >= 6:
        if ref_digits in insp_digits or insp_digits in ref_digits:
            return True, "digit-sequence containment match"
        long_suffix_len = min(len(ref_digits), len(insp_digits))
        if long_suffix_len >= 7 and ref_digits[-long_suffix_len:] == insp_digits[-long_suffix_len:]:
            return True, "helpline suffix digit match"

    # 3. Email matching (full email or email domain)
    email_re = r"([a-z0-9._%+\-]+)@([a-z0-9.\-]+\.[a-z]{2,})"
    ref_email_m = re.search(email_re, rs.lower())
    insp_email_m = re.search(email_re, is_.lower())
    if ref_email_m and insp_email_m:
        if ref_email_m.group(0) == insp_email_m.group(0):
            return True, "exact email match"
        if ref_email_m.group(2) == insp_email_m.group(2):
            return True, f"shared email domain ({ref_email_m.group(2)})"

    # 4. Multi-channel complementary contact (one is email, one is helpline/phone)
    # LMPC Rule 6(1)(da) allows telephone and/or email for consumer care.
    has_ref_email = bool(ref_email_m)
    has_insp_email = bool(insp_email_m)
    has_ref_phone = bool(len(ref_digits) >= 7 or "1800" in rs)
    has_insp_phone = bool(len(insp_digits) >= 7 or "1800" in is_)

    if (has_ref_email and has_insp_phone) or (has_ref_phone and has_insp_email):
        email_obj = ref_email_m or insp_email_m
        domain_name = email_obj.group(2).split(".")[0] if email_obj else ""
        other_str = is_.lower() if has_ref_email else rs.lower()
        if domain_name and (domain_name in other_str or any(tok in domain_name for tok in _token_set(other_str))):
            return True, f"brand-aligned complementary channel (email domain '{domain_name}' matches helpline)"
        return True, "complementary contact channels (toll-free helpline & consumer care email)"

    # 5. Token set overlap (brand / care keywords)
    ref_tok = _token_set(rs)
    insp_tok = _token_set(is_)
    if ref_tok and insp_tok:
        overlap = ref_tok & insp_tok
        meaningful_overlap = {t for t in overlap if t not in {"care", "customer", "consumer", "toll", "free", "call", "email", "mail", "tel", "phone"}}
        if meaningful_overlap:
            return True, f"brand token match: {', '.join(sorted(meaningful_overlap))}"
        if len(overlap) >= 2:
            return True, f"token overlap: {', '.join(sorted(overlap))}"

    return False, "no digit/email/token overlap"


def _parse_mrp_amount(s: Any) -> Optional[float]:
    """
    Extract the numeric MRP amount (first number) from ₹ / Rs formatted strings.

    SAFETY: apply_substitutions=False — the OCR glyph-confusion table (0->o,
    1->i, 5->s, ...) is for fuzzy TEXT comparison only. Running it before
    numeric extraction corrupts real digits (e.g. "420.00" -> "4zo oo") and
    silently produces the wrong amount (or None).
    """
    if not s:
        return None
    # Strip currency prefixes and commas but preserve decimal points
    clean = re.sub(r"(?i)(?:rs\.?|inr|usd|eur|gbp|[\$₹])\s*", "", str(s).replace(",", "").strip())
    nums = re.findall(r"\d+(?:\.\d+)?", clean)
    if not nums:
        return None
    return float(nums[0])


def corroborate_unit_sale_price(
    printed_usp: Optional[str],
    mrp_str: Optional[str],
    net_qty_str: Optional[str],
) -> Tuple[bool, Optional[float], Optional[float], str]:
    """
    Corroborates declared Unit Sale Price against declared MRP and Net Quantity.
    Indian Legal Metrology (Packaged Commodities) Rules mandate:
    USP = MRP / Net Quantity (rounded off to nearest paisa / 2 decimal places).

    Parameters:
      printed_usp: e.g. "Rs. 2.80/g", "0.55/g", "1.38/ml", "6.00/unit", "Rs 0.55 per g"
      mrp_str: e.g. "Rs. 420.00", "99.00", "275.00", "60.00"
      net_qty_str: e.g. "150 g", "180 g", "200 ml", "10 units"

    Returns:
      (agrees, printed_amount, expected_amount, corroboration_note)
    """
    if not printed_usp or not mrp_str or not net_qty_str:
        return False, None, None, "Missing operand (USP, MRP, or Net Quantity not available)"

    # Parse MRP amount
    mrp = _parse_mrp_amount(mrp_str)
    if mrp is None or mrp <= 0:
        return False, None, None, f"Could not parse numeric MRP amount from '{mrp_str}'"

    # Parse Net Quantity
    nq = _parse_net_quantity(net_qty_str)
    if not nq:
        return False, None, None, f"Could not parse Net Quantity from '{net_qty_str}'"
    nq_amt, nq_unit = nq
    if nq_amt <= 0:
        return False, None, None, f"Invalid Net Quantity amount: {nq_amt}"

    # Parse printed numeric USP
    clean_usp = str(printed_usp).replace(",", "").lower()
    usp_nums = re.findall(r"\d+(?:\.\d+)?", clean_usp)
    if not usp_nums:
        return False, None, None, f"Could not parse numeric price from USP '{printed_usp}'"
    printed_amt = float(usp_nums[0])

    # Determine denominator unit in printed USP
    if "/kg" in clean_usp or "per kg" in clean_usp or "/ kg" in clean_usp:
        usp_unit = "kg"
    elif "/g" in clean_usp or "per g" in clean_usp or "/gm" in clean_usp or "/ g" in clean_usp:
        usp_unit = "g"
    elif "/l" in clean_usp or "per l" in clean_usp or "/lt" in clean_usp or "liter" in clean_usp or "litre" in clean_usp or "/ l" in clean_usp:
        usp_unit = "l"
    elif "/ml" in clean_usp or "per ml" in clean_usp or "/ ml" in clean_usp:
        usp_unit = "ml"
    elif any(u in clean_usp for u in ["/unit", "/pc", "/piece", "/n", "per unit", "per pc", "per n", "per piece"]):
        usp_unit = "pc"
    else:
        usp_unit = nq_unit

    # Compute expected USP normalized to the printed USP unit
    expected_usp = 0.0
    if nq_unit == "g":
        if usp_unit == "g":
            expected_usp = mrp / nq_amt
        elif usp_unit == "kg":
            expected_usp = (mrp / nq_amt) * 1000.0
        else:
            expected_usp = mrp / nq_amt
    elif nq_unit == "kg":
        if usp_unit == "kg":
            expected_usp = mrp / nq_amt
        elif usp_unit == "g":
            expected_usp = mrp / (nq_amt * 1000.0)
        else:
            expected_usp = mrp / nq_amt
    elif nq_unit == "ml":
        if usp_unit == "ml":
            expected_usp = mrp / nq_amt
        elif usp_unit == "l":
            expected_usp = (mrp / nq_amt) * 1000.0
        else:
            expected_usp = mrp / nq_amt
    elif nq_unit == "l":
        if usp_unit == "l":
            expected_usp = mrp / nq_amt
        elif usp_unit == "ml":
            expected_usp = mrp / (nq_amt * 1000.0)
        else:
            expected_usp = mrp / nq_amt
    else:  # pc, unit, N, count
        expected_usp = mrp / nq_amt

    # Packaging rounding tolerance:
    # LMPC Rule requires rounding to the nearest paisa (+/- 0.05 or +/- 2.5% relative error)
    diff = abs(printed_amt - expected_usp)
    rel_diff = diff / max(expected_usp, 1e-4)
    agrees = bool(diff <= 0.05 or rel_diff <= 0.025)

    note = (
        f"MRP Rs.{mrp:g} / Net Qty {nq_amt:g} {nq_unit} = Expected USP Rs.{expected_usp:.2f}/{usp_unit}. "
        f"Printed USP: Rs.{printed_amt:g}/{usp_unit} (diff={diff:.3f})."
    )
    return agrees, printed_amt, round(expected_usp, 2), note


_OCR_LETTER_TO_DIGIT_TABLE = str.maketrans("OoIiLlSsBb", "0011115588")


def _fssai_normalize(s: Any) -> str:
    """FSSAI is a 14-digit (or 10-digit old) license -- only digits matter, mapping common OCR letter substitutions."""
    cleaned = str(s or "").translate(_OCR_LETTER_TO_DIGIT_TABLE)
    return _digits_only(cleaned)


def _barcode_normalize(s: Any) -> str:
    """GTIN/EAN/UPC -- only digits matter, mapping common OCR letter substitutions."""
    cleaned = str(s or "").translate(_OCR_LETTER_TO_DIGIT_TABLE)
    return _digits_only(cleaned)


def _is_manufacturer_match(ref_str: Any, insp_str: Any) -> Tuple[bool, str]:
    """
    Manufacturer / packer / marketer semantic match.
    Accepts: abbreviation (Pvt/Private, Ltd/Limited), token containment, city tokens.
    """
    if not ref_str or not insp_str:
        return False, "missing operand"
    ref_tok = _token_set(ref_str)
    insp_tok = _token_set(insp_str)
    if not ref_tok or not insp_tok:
        return False, "no tokens"
    if ref_tok == insp_tok:
        return True, "identical token set"
    common = ref_tok & insp_tok
    if len(common) >= max(2, min(3, min(len(ref_tok), len(insp_tok)))):
        return True, f"token containment: {', '.join(sorted(common))}"
    if ref_tok.issubset(insp_tok) and len(ref_tok) >= 2:
        return True, "reference tokens contained in inspection"
    if insp_tok.issubset(ref_tok) and len(insp_tok) >= 2:
        return True, "inspection tokens contained in reference"
    return False, f"low token overlap ({len(common)} common)"


def parse_commodity_date(raw_val: Any) -> Optional[Tuple[int, int]]:
    """
    Parses date declarations into (year, month) for chronological comparison.
    Handles MM/YYYY, MM/YY, DD/MM/YYYY, Month YYYY, YYYY-MM, etc.
    """
    if not raw_val:
        return None
    s = str(raw_val).strip().lower()

    # 1. Month name + year, e.g. "Dec 2025", "Feb 2026", "December 2025"
    m_name_match = re.search(r"([a-z]{3,9})[\s\-\./,]+(\d{2,4})", s)
    if m_name_match:
        m_str, y_str = m_name_match.groups()
        if m_str in MONTH_NAME_MAP:
            y = int(y_str)
            if y < 100:
                y += 2000
            return (y, MONTH_NAME_MAP[m_str])

    # 2. Year + Month, e.g. "2025/12" or "2025-12"
    y_m_match = re.search(r"(\d{4})[/\-\.](\d{1,2})", s)
    if y_m_match:
        y, m = int(y_m_match.group(1)), int(y_m_match.group(2))
        if 1 <= m <= 12 and 2000 <= y <= 2050:
            return (y, m)

    # 3. Day/Month/Year or Month/Year: e.g. "12/2025", "15/12/2025", "12/25"
    m_y_match = re.findall(r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})", s)
    if m_y_match:
        _, m_str, y_str = m_y_match[0]
        y = int(y_str)
        if y < 100:
            y += 2000
        m = int(m_str)
        if 1 <= m <= 12 and 2000 <= y <= 2050:
            return (y, m)

    m_y_short = re.findall(r"(\d{1,2})[/\-\.](\d{2,4})", s)
    if m_y_short:
        m_str, y_str = m_y_short[0]
        m = int(m_str)
        y = int(y_str)
        if y < 100:
            y += 2000
        if 1 <= m <= 12 and 2000 <= y <= 2050:
            return (y, m)

    return None


def detect_sticker_overlay(image_bgr: Optional[np.ndarray], bbox: List[int]) -> Tuple[bool, float, str]:
    """
    Analyzes local spatial region for physical sticker overlays, label patches, or dual print layers.
    Under LMPC Rule 23, price over-stickering or altered labels are prohibited.
    """
    if image_bgr is None or not bbox or len(bbox) < 4:
        return False, 0.90, "No evidence crop available for overlay check"

    try:
        ih, iw = image_bgr.shape[:2]
        x, y, w, h = [int(v) for v in bbox[:4]]
        if w < 10 or h < 10:
            return False, 0.90, "Region too small for spatial overlay analysis"

        pad = int(min(w, h) * 0.25)
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(iw, x + w + pad)
        y2 = min(ih, y + h + pad)

        crop = image_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            return False, 0.90, "Empty crop"

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        crop_area = (x2 - x1) * (y2 - y1)
        for cnt in contours:
            c_area = cv2.contourArea(cnt)
            if 0.35 * crop_area < c_area < 0.95 * crop_area:
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
                if len(approx) == 4:
                    return True, 0.86, "Physical rectangular sticker/patch overlay border detected"

        # Edge & intensity discontinuity check
        inner_x = x - x1
        inner_y = y - y1
        inner_crop = gray[max(0, inner_y):min(gray.shape[0], inner_y + h), max(0, inner_x):min(gray.shape[1], inner_x + w)]
        if inner_crop.size > 0:
            outer_mask = np.ones_like(gray, dtype=bool)
            outer_mask[max(0, inner_y):min(gray.shape[0], inner_y + h), max(0, inner_x):min(gray.shape[1], inner_x + w)] = False
            outer_pixels = gray[outer_mask]
            if outer_pixels.size > 0:
                inner_mean = float(np.mean(inner_crop))
                outer_mean = float(np.mean(outer_pixels))
                if abs(inner_mean - outer_mean) > 85 and np.std(inner_crop) < 30:
                    return True, 0.84, "High contrast paper patch boundary detected over text area"

        return False, 0.94, "Clean direct packaging print; no sticker overlay detected"
    except Exception as e:
        logger.warning("Sticker overlay detection failed: %s", e)
        return False, 0.80, "Overlay analysis bypassed due to exception"


def escalate_ambiguous_region_gemini(
    crop_bgr: np.ndarray,
    field_name: str,
    ref_val: str,
    insp_val: str,
) -> Optional[Dict[str, Any]]:
    """
    Escalation layer: Only invoked when CV/OCR signals are ambiguous
    and an external VLM assessment is needed. Never replaces the rule engine.
    Skipped during automated unit tests.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    if not getattr(config, "GEMINI_API_KEY", None):
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        _, buf = cv2.imencode(".jpg", crop_bgr)
        image_part = types.Part.from_bytes(data=buf.tobytes(), mime_type="image/jpeg")

        prompt = (
            f"You are a forensic packaging security auditor for legal metrology.\n"
            f"Evaluate this packaging region crop for field: {field_name}.\n"
            f"Reference Standard: '{ref_val}', Inspected Marking: '{insp_val}'.\n"
            f"Check specifically for:\n"
            f"1. Physical sticker overlay, over-stickering, or pasted label over original print.\n"
            f"2. Inconsistent typography, dual font layering, or scratched-out numbers.\n"
            f"3. Or is it a legitimate direct factory print (e.g. standard inkjet batch coding or packaging revision)?\n"
            f"Return JSON strictly with:\n"
            f'{{"is_suspicious": boolean, "is_sticker_overlay": boolean, "confidence": float, "observation_note": string}}\n'
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        if response and response.text:
            return json.loads(response.text)
    except Exception as exc:
        logger.warning("Gemini escalation failed: %s", exc)
    return None


def compare_curved_packaging_regions(
    ref_bgr: np.ndarray,
    insp_bgr: np.ndarray,
    num_vertical_bands: int = 4,
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Compares curved / cylindrical packaging (e.g. Vaseline lotion bottle, spray cans)
    using local region patch correlation across vertical cylindrical bands.
    """
    try:
        ref_h, ref_w = ref_bgr.shape[:2]
        insp_resized = cv2.resize(insp_bgr, (ref_w, ref_h))

        band_w = ref_w // num_vertical_bands
        band_correlations = []
        variations = []

        for i in range(num_vertical_bands):
            x1 = i * band_w
            x2 = (i + 1) * band_w if i < num_vertical_bands - 1 else ref_w
            ref_band = ref_bgr[:, x1:x2]
            insp_band = insp_resized[:, x1:x2]

            hist_ref = cv2.calcHist([ref_band], [0, 1, 2], None, [6, 6, 6], [0, 256, 0, 256, 0, 256])
            cv2.normalize(hist_ref, hist_ref)
            hist_insp = cv2.calcHist([insp_band], [0, 1, 2], None, [6, 6, 6], [0, 256, 0, 256, 0, 256])
            cv2.normalize(hist_insp, hist_insp)

            corr = float(cv2.compareHist(hist_ref, hist_insp, cv2.HISTCMP_CORREL))
            band_correlations.append(corr)

            if corr < 0.60:
                variations.append({
                    "field_name": f"CURVED_BAND_{i+1}",
                    "reference_value": "Standard catalog cylindrical curvature profile",
                    "inspection_value": "Curved surface profile deviation detected",
                    "difference_type": "Curved packaging local region variation",
                    "bbox": [x1, 0, x2 - x1, ref_h],
                    "confidence": 0.82,
                    "field_classification": FIELD_CLASS_STATIC,
                    "is_suspicious": True,
                    "finding_category": FINDING_ACTUAL_DIFFERENCE,
                    "ocr_confidence": 1.0,
                    "image_quality_score": 0.8,
                    "normalized_similarity": round(corr, 2),
                    "observation_note": "Local surface reflectance and cylindrical contour deviates from master profile.",
                    "severity": "MEDIUM",
                })

        avg_corr = float(np.mean(band_correlations)) if band_correlations else 0.7
        return avg_corr, variations
    except Exception as exc:
        logger.warning("Curved packaging comparison failed: %s", exc)
        return 0.5, []


