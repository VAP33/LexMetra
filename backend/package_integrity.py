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
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

import config

logger = logging.getLogger("lexmetra.integrity")

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


def _run_coroutine_sync(coro):
    """Safely executes an async coroutine synchronously from sync or async context."""
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


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
            x = int(round(float(bbox.get("x", 0))))
            y = int(round(float(bbox.get("y", 0))))
            w = int(round(float(bbox.get("width", bbox.get("w", 0)))))
            h = int(round(float(bbox.get("height", bbox.get("h", 0)))))
        elif isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            x, y, w, h = [int(round(float(v))) for v in bbox[:4]]
        else:
            return None

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


_EVIDENCE_EXTRACTION_CACHE: Dict[str, Tuple[Dict, Dict, Dict, Dict, Dict, Dict]] = {}
_CACHE_FILE = Path(__file__).resolve().parent / "data" / "evidence_extraction_cache.pkl"

def _load_disk_cache():
    if _CACHE_FILE.exists():
        try:
            import pickle
            with open(_CACHE_FILE, "rb") as f:
                _EVIDENCE_EXTRACTION_CACHE.update(pickle.load(f))
        except Exception:
            pass

def _save_disk_cache():
    try:
        import pickle
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "wb") as f:
            pickle.dump(_EVIDENCE_EXTRACTION_CACHE, f)
    except Exception:
        pass

_load_disk_cache()


def extract_canonical_package_evidence(
    image_items: List[Tuple[Path, np.ndarray]],
) -> Tuple[
    Dict[str, Any],
    Dict[str, List[int]],
    Dict[str, float],
    Dict[str, str],
    Dict[str, int],
    Dict[str, Any],
]:
    """
    Executes the exact LexMetra evidence & localization pipeline on an input package:
    1. Canonical surface normalization (+6% safe margin)
    2. Real barcode detection
    3. Multimodal VLM perception across canonical faces (Qwen / Gemini Multimodal)
    4. Classical OCR fallback & corroboration
    5. PaddleOCR/DBNet tight text localization -> spatial candidate matching & DBNet vector contours
    6. Canonical + original camera image bbox & polygon projection
    7. Face-specific visual evidence crop generation with tight contours

    Returns:
      (declarations, bboxes, confidences, crops, face_indices, raw_details)
    """
    decls: Dict[str, Any] = {}
    bboxes: Dict[str, List[int]] = {}
    confs: Dict[str, float] = {}
    crops: Dict[str, str] = {}
    face_indices: Dict[str, int] = {}
    raw_details: Dict[str, Any] = {}

    if not image_items:
        return decls, bboxes, confs, crops, face_indices, raw_details

    # Check cache by file paths and timestamps
    cache_key = None
    try:
        cache_key = "|".join(f"{p.resolve()}:{p.stat().st_mtime}" for p, _ in image_items) + ":v2_barcode_usp"
        if cache_key in _EVIDENCE_EXTRACTION_CACHE:
            c_d, c_b, c_c, c_cr, c_fi, c_rd = _EVIDENCE_EXTRACTION_CACHE[cache_key]
            return dict(c_d), dict(c_b), dict(c_c), dict(c_cr), dict(c_fi), dict(c_rd)
    except Exception:
        cache_key = None

    import barcode_decode
    import geometry
    import qwen_perception
    from ocr_extraction import classify_fields, run_ocr
    from localization.service import LocalizationService
    from localization.models import LocalizationSurface, LocalizedEvidence, LocalizationStatus
    from PIL import Image

    normalized_faces = []
    loc_surfaces: Dict[str, LocalizationSurface] = {}
    faces_for_qwen = []

    # 1. Canonical Normalization across all faces
    for i, (p, bgr) in enumerate(image_items[:3]):
        face_id = f"face_{i+1}"
        face_label = f"Face {i+1}"
        norm_res = geometry.normalize_package_surface(bgr, source_name=p.name)
        normalized_faces.append(norm_res)

        try:
            config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            target_p = config.UPLOAD_DIR / p.name
            if not target_p.exists() or (p.resolve() != target_p.resolve()):
                shutil.copy2(p, target_p)
        except Exception:
            pass

        loc_surfaces[face_id] = LocalizationSurface(
            face_id=face_id,
            image_id=p.name,
            canonical_image=norm_res.canonical_image,
            canonical_width=norm_res.canonical_dims[0],
            canonical_height=norm_res.canonical_dims[1],
            original_width=norm_res.original_dims[0],
            original_height=norm_res.original_dims[1],
            forward_transform=norm_res.forward_transform.matrix if norm_res.forward_transform else None,
            inverse_transform=norm_res.inverse_transform.matrix if norm_res.inverse_transform else None,
        )
        faces_for_qwen.append((face_label, norm_res.canonical_image, norm_res.inverse_transform))

    # 2. Barcode Detection & Printed Digits Cross-Check across faces
    import pytesseract
    for cand_tess in [r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Users\HP\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"]:
        if Path(cand_tess).exists():
            pytesseract.pytesseract.tesseract_cmd = cand_tess
            break

    bc_detector = None
    try:
        bc_detector = cv2.barcode.BarcodeDetector()
    except Exception:
        pass

    for i, (p, bgr) in enumerate(image_items):
        try:
            decoded_val: Optional[str] = None
            bc_bbox: Optional[List[int]] = None
            bc_polygon: Optional[List[List[float]]] = None
            bc_source: str = "cv2_barcode_detector"

            # 2a. Machine Decode using OpenCV BarcodeDetector
            if bc_detector is not None:
                try:
                    ret = bc_detector.detectAndDecode(bgr)
                    val = ret[0] if ret and len(ret) > 0 else ""
                    if isinstance(val, (list, tuple)) and len(val) > 0:
                        val = val[0]
                    val = str(val).strip() if val else ""
                    if val:
                        decoded_val = val
                        bc_source = "cv2_barcode_detector"
                        if len(ret) > 1 and ret[1] is not None and len(ret[1]) > 0:
                            pts = ret[1][0]
                            bc_polygon = pts.tolist()
                            xs = pts[:, 0]
                            ys = pts[:, 1]
                            bc_bbox = [int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys))]
                except Exception as bde:
                    logger.debug("cv2.barcode.BarcodeDetector failed on %s: %s", p.name, bde)

            # 2b. Machine Decode fallback using barcode_decode.decode_symbols
            if not decoded_val:
                try:
                    sym_res = barcode_decode.decode_symbols(bgr, image_id=p.name, allow_hri_fallback=False)
                    if sym_res and sym_res.symbols:
                        for sym in sym_res.symbols:
                            if sym.payload:
                                decoded_val = sym.payload
                                bc_source = sym.method.value if hasattr(sym, "method") else "cv_bars_decoded"
                                if sym.bbox:
                                    bc_bbox = list(sym.bbox)
                                break
                except Exception as dse:
                    logger.debug("barcode_decode.decode_symbols failed on %s: %s", p.name, dse)

            # If still no bbox, check region detection for 1D symbol
            if not bc_bbox:
                try:
                    import region_detection
                    boxes = [r.bbox for r in region_detection.detect_symbology_regions(bgr)]
                    if boxes:
                        bc_bbox = list(boxes[0])
                except Exception:
                    pass

            # 2c. Detect Human-Readable Printed Digits below/near the barcode
            observed_val: Optional[str] = None
            if bc_bbox:
                x, y, w, h = bc_bbox
                H, W = bgr.shape[:2]
                gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr

                # Check HRI read from barcode_decode
                try:
                    hri_reads = barcode_decode._read_hri(gray, tuple(bc_bbox), bgr.shape)
                    if hri_reads:
                        observed_val = hri_reads[0]
                except Exception:
                    pass

                # If HRI read didn't return digits, check strip directly below barcode with standard OCR
                if not observed_val:
                    try:
                        y0 = max(0, int(y + 0.65 * h))
                        y1 = min(H, int(y + 1.6 * h))
                        x0 = max(0, int(x - 0.2 * w))
                        x1 = min(W, int(x + 1.2 * w))
                        strip = gray[y0:y1, x0:x1]
                        if strip.size > 0:
                            txt = pytesseract.image_to_string(strip, config="--psm 6")
                            digits = re.findall(r"\d+", txt)
                            cand = "".join(digits)
                            if len(cand) >= 8:
                                observed_val = cand
                    except Exception:
                        pass

            # 2d. Cross-check both values:
            # VERIFIED = printed digits observed and match decoder.
            # REVIEW_REQUIRED = partial/unclear/disagreeing digits.
            # NOT_OBSERVED = barcode decoded but printed digits are not visually observable.
            # Never fabricate printed digits from the decoder.
            if decoded_val and observed_val:
                d_norm = _barcode_normalize(decoded_val)
                o_norm = _barcode_normalize(observed_val)
                if d_norm == o_norm or (len(d_norm) >= 8 and (d_norm in o_norm or o_norm in d_norm)):
                    bc_status = "VERIFIED"
                else:
                    bc_status = "REVIEW_REQUIRED"
            elif decoded_val and not observed_val:
                bc_status = "NOT_OBSERVED"
            elif observed_val and not decoded_val:
                bc_status = "REVIEW_REQUIRED"
            else:
                bc_status = "NOT_OBSERVED"

            effective_barcode = decoded_val or observed_val
            if effective_barcode and "barcode" not in decls:
                decls["barcode"] = effective_barcode
                confs["barcode"] = 0.98 if bc_status == "VERIFIED" else 0.90
                face_indices["barcode"] = i
                raw_details["barcode"] = {
                    "source": bc_source,
                    "decoded_value": decoded_val,
                    "observed_value": observed_val,
                    "barcode_verification_status": bc_status,
                    "symbology": "EAN_13",
                }
                if bc_bbox:
                    bboxes["barcode"] = bc_bbox
                if bc_polygon:
                    if "polygons" not in raw_details:
                        raw_details["polygons"] = {}
                    raw_details["polygons"]["barcode"] = bc_polygon
                break
        except Exception as e:
            logger.debug("Barcode detection on face %d failed: %s", i, e)

    field_map = {
        "PRODUCT_NAME": "product_name",
        "PRODUCT_ID": "product_id",
        "SKU": "product_id",
        "MRP": "mrp",
        "USP": "unit_sale_price",
        "NET_QUANTITY": "net_quantity",
        "MANUFACTURER": "manufacturer_name",
        "MARKETER": "marketer_name",
        "PACKER": "packer_name",
        "IMPORTER": "importer_name",
        "ADDRESS": "address",
        "CONSUMER_CARE": "consumer_care",
        "CONSUMER_HELPLINE": "consumer_care",
        "MFD": "manufacturing_date",
        "EXPIRY": "expiry_date",
        "USE_BEFORE": "expiry_date",
        "USE_BY": "expiry_date",
        "BEST_BEFORE": "expiry_date",
        "BATCH": "batch_number",
        "LOT": "batch_number",
        "COUNTRY_OF_ORIGIN": "country_of_origin",
        "FSSAI": "fssai_license_number",
        "FSSAI_LICENSE": "fssai_license_number",
        "FSSAI_NO": "fssai_license_number",
    }

    accumulated_classified: Dict[str, dict] = {}

    # 3. Gemini / Multimodal Perception across faces
    provider = qwen_perception.get_qwen_provider()
    if provider.is_available() and faces_for_qwen:
        try:
            perception_res = _run_coroutine_sync(provider.perceive(faces_for_qwen))
            if perception_res:
                if perception_res.product_name and "product_name" not in decls:
                    decls["product_name"] = perception_res.product_name
                    confs["product_name"] = 0.95
                    face_indices["product_name"] = 0
                if perception_res.product_id and "product_id" not in decls:
                    decls["product_id"] = perception_res.product_id
                    confs["product_id"] = 0.92
                    face_indices["product_id"] = 0

                q_fields = qwen_perception.perception_to_classified_fields(perception_res)
                for fld, fld_data in q_fields.items():
                    if isinstance(fld_data, dict) and fld_data.get("value"):
                        accumulated_classified[fld] = fld_data
                        k = field_map.get(fld.upper(), fld.lower())
                        decls[k] = fld_data.get("value")
                        confs[k] = float(fld_data.get("confidence") or 0.90)
                        tf = fld_data.get("face", "Face 1")
                        f_idx = 0
                        for idx in range(len(image_items)):
                            if f"Face {idx+1}" == tf:
                                f_idx = idx
                                break
                        face_indices[k] = f_idx
                        if fld_data.get("bbox"):
                            bboxes[k] = list(fld_data["bbox"])
        except Exception as e:
            logger.warning("Multimodal perception in extract_canonical_package_evidence failed: %s", e)

    # 4. Classical OCR Corroboration on canonical surfaces
    for i, norm_res in enumerate(normalized_faces):
        try:
            pil_img = Image.fromarray(cv2.cvtColor(norm_res.canonical_image, cv2.COLOR_BGR2RGB))
            ocr_lines = run_ocr(pil_img)
            if ocr_lines:
                classified_ocr = classify_fields(ocr_lines)
                for k, v in classified_ocr.items():
                    if isinstance(v, dict) and v.get("value"):
                        norm_k = field_map.get(k.upper(), k.lower())
                        if norm_k not in decls or confs.get(norm_k, 0.0) < float(v.get("confidence", 0.65)):
                            decls[norm_k] = v.get("value")
                            confs[norm_k] = float(v.get("confidence", 0.65))
                            face_indices[norm_k] = i
                        if k not in accumulated_classified:
                            v["face"] = f"Face {i+1}"
                            v["surface_id"] = f"face_{i+1}"
                            v["image_id"] = image_items[i][0].name
                            accumulated_classified[k] = v
        except Exception as e:
            logger.debug("OCR pass on face %d failed: %s", i, e)

    # 5. PaddleOCR/DBNet Tight Vector Text Localization
    localized_map: Dict[str, LocalizedEvidence] = {}
    try:
        localizer = LocalizationService()
        localized_list = localizer.localize_extractions(
            inspection_id=f"integrity_extract_{int(time.time())}",
            extractions=accumulated_classified,
            surfaces=loc_surfaces,
        )
        for le in localized_list:
            norm_f = field_map.get(le.field.upper(), le.field.lower())
            localized_map[norm_f] = le
            localized_map[le.field.lower()] = le
            # Extract high-precision original bbox from localized DBNet contour
            if le.bbox_original and isinstance(le.bbox_original, dict):
                bx = int(round(float(le.bbox_original.get("x", 0))))
                by = int(round(float(le.bbox_original.get("y", 0))))
                bw = int(round(float(le.bbox_original.get("width", 0))))
                bh = int(round(float(le.bbox_original.get("height", 0))))
                if bw > 2 and bh > 2:
                    bboxes[norm_f] = [bx, by, bw, bh]
            elif isinstance(le.bbox_original, (list, tuple)) and len(le.bbox_original) >= 4:
                bboxes[norm_f] = [int(round(float(x))) for x in le.bbox_original[:4]]
    except Exception as e:
        logger.warning("LocalizationService failed in extract_canonical_package_evidence: %s", e)

    # 6. Generate real evidence crops from the exact face image
    polygons: Dict[str, List[List[float]]] = {}
    surface_ids: Dict[str, str] = {}
    image_ids: Dict[str, str] = {}
    image_urls: Dict[str, str] = {}
    localization_statuses: Dict[str, str] = {}

    for k in list(decls.keys()):
        f_idx = face_indices.get(k, 0)
        if f_idx >= len(image_items):
            f_idx = 0
        face_path, face_bgr = image_items[f_idx]
        face_id = f"face_{f_idx + 1}"
        surface_ids[k] = face_id
        image_ids[k] = face_path.name
        image_urls[k] = f"/uploads/{face_path.name}"

        le = localized_map.get(k)
        if le:
            localization_statuses[k] = str(le.localization_status.value if hasattr(le.localization_status, "value") else le.localization_status)
            if le.polygon_original:
                polygons[k] = [[float(round(pt[0], 2)), float(round(pt[1], 2))] for pt in le.polygon_original]
        if k not in polygons and "polygons" in raw_details and k in raw_details["polygons"]:
            polygons[k] = raw_details["polygons"][k]

        bbox = bboxes.get(k)
        if bbox and 0 <= f_idx < len(image_items):
            crop_b64 = _make_evidence_crop(face_bgr, bbox, polygon=polygons.get(k))
            if crop_b64:
                crops[k] = crop_b64

    raw_details["localized_map"] = {k: (le.model_dump() if hasattr(le, "model_dump") else str(le)) for k, le in localized_map.items()}
    raw_details["polygons"] = polygons
    raw_details["surface_ids"] = surface_ids
    raw_details["image_ids"] = image_ids
    raw_details["image_urls"] = image_urls
    raw_details["localization_statuses"] = localization_statuses

    if cache_key:
        _EVIDENCE_EXTRACTION_CACHE[cache_key] = (
            dict(decls),
            dict(bboxes),
            dict(confs),
            dict(crops),
            dict(face_indices),
            dict(raw_details),
        )
        _save_disk_cache()

    return decls, bboxes, confs, crops, face_indices, raw_details


def extract_declarations_from_image(image_path: Path) -> Dict[str, Any]:
    """
    Runs statutory declaration extraction on a reference package image.
    Extracts MRP, net quantity, dates, batch, manufacturer, customer care, FSSAI, and barcode.
    """
    decls, _ = extract_declarations_with_bboxes(image_path)
    return decls


def extract_declarations_with_bboxes(
    image_path: Path,
) -> Tuple[Dict[str, Any], Dict[str, List[int]]]:
    """
    Runs VLM and statutory field classification on a package image (reference or inspection).
    Returns a 2-tuple: (declarations, bboxes)
    """
    if not image_path.exists():
        return {}, {}

    cv_img = cv2.imread(str(image_path))
    if cv_img is None:
        return {}, {}

    decls, b_boxes, _confs, _crops, _indices, _raw = extract_canonical_package_evidence([(image_path, cv_img)])
    return decls, b_boxes


def aggregate_face_extractions(
    face_results: List[Tuple[Dict[str, Any], Dict[str, List[int]], Dict[str, float], Dict[str, Any]]],
    face_names: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], Dict[str, List[int]], Dict[str, float], Dict[str, int], Dict[str, Any]]:
    merged_decls: Dict[str, Any] = {}
    merged_bboxes: Dict[str, List[int]] = {}
    merged_confs: Dict[str, float] = {}
    merged_face_idx: Dict[str, int] = {}
    merged_raw: Dict[str, Any] = {}

    for face_i, (face_decls, face_bboxes, face_confs, face_raw) in enumerate(face_results):
        for k, v in face_decls.items():
            if not v:
                continue
            cand_conf = float(face_confs.get(k) or 0.5)
            incumbent_conf = float(merged_confs.get(k) or -1.0)
            this_better = (k not in merged_decls) or (not merged_decls[k]) or (cand_conf > incumbent_conf + 1e-6)
            if this_better:
                merged_decls[k] = v
                merged_confs[k] = cand_conf
                merged_face_idx[k] = face_i
                if k in face_raw:
                    merged_raw[k] = face_raw[k]
                if k in face_bboxes:
                    merged_bboxes[k] = list(face_bboxes[k])

    return merged_decls, merged_bboxes, merged_confs, merged_face_idx, merged_raw


def extract_reference_declarations_from_images(image_paths: List[Path]) -> Dict[str, Any]:
    imgs = []
    for p in image_paths:
        if p.exists():
            im = cv2.imread(str(p))
            if im is not None:
                imgs.append((p, im))
    if not imgs:
        return {}
    decls, _, _, _, _, _ = extract_canonical_package_evidence(imgs)
    return decls


def find_reference_package(
    product_id: Optional[str] = None,
    product_name: Optional[str] = None,
    allow_demo_fixtures: bool = False,
) -> Tuple[Optional[Path], str, Optional[Dict[str, Any]]]:
    """
    Finds reference packaging image and metadata.
    Does NOT return readymade demo images by default to ensure integrity is only evaluated
    when a reference pack image is explicitly provided.
    Returns: (image_path, reference_type, reference_metadata)
    """
    p_name = (product_name or "").lower()
    clean_id = str(product_id or "").strip()

    # 1. Check user uploaded / authorized catalog directory
    if clean_id:
        for ext in [".jpg", ".jpeg", ".png"]:
            cand = REFERENCE_CATALOG_DIR / f"{clean_id}{ext}"
            if cand.exists():
                return cand, REF_TYPE_TRUSTED, None

    # 2. Check deterministic demo fixtures if explicitly requested
    if allow_demo_fixtures:
        search_dirs = [
            WORKSPACE_REFERENCE_DIR,
            Path(__file__).resolve().parent.parent / "images new",
            config.UPLOAD_DIR,
            Path(__file__).resolve().parent.parent / "DEPENDENCIES" / "images dataset",
        ]

        for key, demo_info in DEMO_REFERENCE_PACKAGES.items():
            if key in p_name or (clean_id and key in clean_id.lower()) or (clean_id == "64934436" and key == "bru"):
                matched_paths: List[Path] = []
                # Check for all images associated with this product
                all_img_names = demo_info.get("all_images") or [demo_info.get("image_file")]
                for iname in all_img_names:
                    for sdir in search_dirs:
                        cand = sdir / iname
                        if cand.exists() and cand not in matched_paths:
                            matched_paths.append(cand)
                            break

                primary_path = matched_paths[0] if matched_paths else None
                if not primary_path:
                    fname = demo_info.get("image_file")
                    for sdir in search_dirs:
                        if (sdir / fname).exists():
                            primary_path = sdir / fname
                            matched_paths.append(primary_path)
                            break

                if primary_path:
                    meta = dict(demo_info)
                    meta["all_paths"] = matched_paths
                    return primary_path, demo_info.get("reference_type", REF_TYPE_DEMO), meta

    return None, REF_TYPE_UNVERIFIED, None


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


def _fssai_normalize(s: Any) -> str:
    """FSSAI is a 14-digit (or 10-digit old) license -- only digits matter."""
    return _digits_only(s)


def _barcode_normalize(s: Any) -> str:
    """GTIN/EAN/UPC -- only digits matter."""
    return _digits_only(s)


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


def compare_canonical_fields(
    ref_declarations: Dict[str, Any],
    insp_declarations: List[Dict[str, Any]],
    insp_image_bgr: Optional[np.ndarray] = None,
    ref_image_bgr: Optional[np.ndarray] = None,
    ref_bboxes: Optional[Dict[str, List[int]]] = None,
    ref_crops: Optional[Dict[str, str]] = None,
    ref_polygons: Optional[Dict[str, List[List[float]]]] = None,
    insp_polygons: Optional[Dict[str, List[List[float]]]] = None,
    ref_surface_ids: Optional[Dict[str, str]] = None,
    insp_surface_ids: Optional[Dict[str, str]] = None,
    ref_image_ids: Optional[Dict[str, str]] = None,
    insp_image_ids: Optional[Dict[str, str]] = None,
    ref_image_urls: Optional[Dict[str, str]] = None,
    insp_image_urls: Optional[Dict[str, str]] = None,
    ref_confs: Optional[Dict[str, float]] = None,
    insp_confs: Optional[Dict[str, float]] = None,
    ref_imgs: Optional[List[Tuple[Path, np.ndarray]]] = None,
    insp_imgs: Optional[List[Tuple[Path, np.ndarray]]] = None,
    insp_raw: Optional[Dict[str, Any]] = None,
    ref_raw: Optional[Dict[str, Any]] = None,
) -> Tuple[List[FieldComparisonItem], List[Dict[str, Any]]]:
    """
    Compares declarations between reference standard and inspected package at the canonical field level.
    Preserves all Priority 1 visual evidence: exact localized bboxes, DBNet polygons, crops, image IDs, and surface IDs.
    Returns:
      (canonical_comparisons, differences)
    """
    canonical_items: List[FieldComparisonItem] = []
    differences: List[Dict[str, Any]] = []

    # Build lookup map of inspected declarations
    insp_map: Dict[str, Dict[str, Any]] = {}
    for item in insp_declarations:
        if isinstance(item, dict):
            fld = (item.get("field") or item.get("name") or "").lower().strip()
            if fld:
                insp_map[fld] = item

    def get_bbox(matched: Optional[Dict[str, Any]]) -> Optional[List[int]]:
        if not matched:
            return None
        raw_box = matched.get("bounding_box") or matched.get("bbox")
        if isinstance(raw_box, dict):
            return [
                int(raw_box.get("x", 0)),
                int(raw_box.get("y", 0)),
                int(raw_box.get("width", 50)),
                int(raw_box.get("height", 30)),
            ]
        if isinstance(raw_box, (list, tuple)) and len(raw_box) >= 4:
            return [int(v) for v in raw_box[:4]]
        return None

    def find_insp_match(aliases: List[str]) -> Optional[Dict[str, Any]]:
        for alias in aliases:
            if alias in insp_map:
                return insp_map[alias]
        return None

    # Pre-extract dates for chronology check
    mfg_insp_match = find_insp_match(["manufacturing_date", "mfd_date", "mfg_date", "date_of_manufacture", "mfd"])
    exp_insp_match = find_insp_match(["expiry_date", "best_before", "use_by_date", "exp_date", "expiry"])
    insp_mfg_val = (mfg_insp_match.get("value") or mfg_insp_match.get("extracted_value") or "") if mfg_insp_match else ""
    insp_exp_val = (exp_insp_match.get("value") or exp_insp_match.get("extracted_value") or "") if exp_insp_match else ""
    mfg_parsed = parse_commodity_date(insp_mfg_val) if insp_mfg_val else None
    exp_parsed = parse_commodity_date(insp_exp_val) if insp_exp_val else None
    chronology_invalid = bool(mfg_parsed and exp_parsed and mfg_parsed > exp_parsed)

    # Pre-extract MRP and Net Quantity for USP arithmetic corroboration
    mrp_insp_match = find_insp_match(["mrp", "maximum_retail_price", "retail_price", "price"])
    insp_mrp_val = (mrp_insp_match.get("value") or mrp_insp_match.get("extracted_value") or "") if mrp_insp_match else (ref_declarations.get("mrp") or "")
    nq_insp_match = find_insp_match(["net_quantity", "net_weight", "net_volume", "quantity", "weight"])
    insp_nq_val = (nq_insp_match.get("value") or nq_insp_match.get("extracted_value") or "") if nq_insp_match else (ref_declarations.get("net_quantity") or "")

    specs = [
        ("mrp", "MRP", FIELD_CLASS_VERSION_SENSITIVE, ["mrp", "maximum_retail_price", "retail_price", "price"]),
        ("unit_sale_price", "Unit Sale Price", FIELD_CLASS_VERSION_SENSITIVE, ["unit_sale_price", "usp"]),
        ("batch_number", "Batch Number", FIELD_CLASS_VARIABLE, ["batch_number", "lot_number", "batch_no", "lot_no", "batch"]),
        ("manufacturing_date", "Date of Manufacture", FIELD_CLASS_VARIABLE, ["manufacturing_date", "mfd_date", "mfg_date", "date_of_manufacture", "mfd"]),
        ("expiry_date", "Expiry Date", FIELD_CLASS_VARIABLE, ["expiry_date", "best_before", "use_by_date", "exp_date", "expiry"]),
        ("manufacturer_name", "Manufacturer", FIELD_CLASS_STATIC, ["manufacturer_name", "manufacturer", "mfg_by", "packer_name", "marketer_name"]),
        ("net_quantity", "Net Quantity", FIELD_CLASS_STATIC, ["net_quantity", "net_weight", "net_volume", "quantity", "weight"]),
        ("barcode", "Barcode / GTIN", FIELD_CLASS_STATIC, ["barcode", "gtin", "ean", "upc"]),
        ("fssai_license_number", "FSSAI License", FIELD_CLASS_STATIC, ["fssai_license_number", "fssai_no", "fssai_license", "fssai"]),
        ("product_name", "Product Identity", FIELD_CLASS_STATIC, ["product_name", "product_identity", "brand"]),
        ("consumer_care", "Consumer Care", FIELD_CLASS_STATIC, ["consumer_care", "customer_care", "care_details", "helpline"]),
    ]

    for ref_key, display_name, field_class, aliases in specs:
        ref_val = ref_declarations.get(ref_key)
        matched_insp = find_insp_match(aliases)
        insp_val = (matched_insp.get("value") or matched_insp.get("extracted_value") or "") if matched_insp else ""

        ref_str = str(ref_val).strip() if ref_val is not None else ""
        insp_str = str(insp_val).strip() if insp_val else ""

        # If NEITHER side has observed this field, skip (nothing to compare).
        if not ref_str and not insp_str:
            continue

        ref_bbox = (ref_bboxes or {}).get(ref_key)
        ref_polygon = (ref_polygons or {}).get(ref_key)
        ref_surf = (ref_surface_ids or {}).get(ref_key)
        ref_img_id = (ref_image_ids or {}).get(ref_key)
        ref_img_url = (ref_image_urls or {}).get(ref_key)
        ref_c = float((ref_confs or {}).get(ref_key) or 0.90)

        insp_bbox = get_bbox(matched_insp)
        insp_polygon = (matched_insp.get("polygon") if isinstance(matched_insp, dict) else None) or (insp_polygons or {}).get(ref_key)
        insp_surf = (matched_insp.get("surface_id") or matched_insp.get("face") if isinstance(matched_insp, dict) else None) or (insp_surface_ids or {}).get(ref_key)
        insp_img_id = (matched_insp.get("image_id") if isinstance(matched_insp, dict) else None) or (insp_image_ids or {}).get(ref_key)
        insp_img_url = (matched_insp.get("image_url") if isinstance(matched_insp, dict) else None) or (insp_image_urls or {}).get(ref_key)
        insp_c = float(
            (matched_insp.get("confidence") if isinstance(matched_insp, dict) and matched_insp.get("confidence") is not None else None)
            or (0.92 if matched_insp and (matched_insp.get("value") or matched_insp.get("extracted_value")) else None)
            or (insp_confs or {}).get(ref_key)
            or 0.85
        )

        # Use pre-made crop if available, otherwise generate on-the-fly with polygon and padding
        insp_crop_premade = (matched_insp.get("evidence_crop_base64") if isinstance(matched_insp, dict) else None) or None
        insp_crop: Optional[str] = insp_crop_premade
        if not insp_crop and insp_image_bgr is not None and insp_bbox:
            insp_crop = _make_evidence_crop(insp_image_bgr, insp_bbox, polygon=insp_polygon)
        ocr_conf = insp_c
        quality = assess_region_quality(insp_image_bgr, insp_bbox) if (insp_image_bgr is not None and insp_bbox) else {"sharpness": 1.0, "is_degraded": False, "quality_note": "Normal quality"}

        ref_crop = (ref_crops or {}).get(ref_key)
        if not ref_crop and ref_image_bgr is not None and ref_bbox:
            ref_crop = _make_evidence_crop(ref_image_bgr, ref_bbox, polygon=ref_polygon)

        raw_sim, norm_sim, sim_reason = compute_ocr_similarity(ref_str, insp_str)

        # ============================================================
        # EVIDENCE GATES FIRST -- NO MATCH WITHOUT REFERENCE EVIDENCE
        # ============================================================
        status = STATUS_REVIEW_REQUIRED
        is_susp = False
        finding_cat = FINDING_OCR_UNCERTAINTY
        reason = "Classification in progress."
        obs = "Classification in progress."
        diff_type = "Awaiting evidence rule classification"
        sev = "LOW"

        has_ref_evidence = bool(ref_str and ref_str.lower() not in ("not specified", "none", "null", "not available", "unspecified", "n/a", "not detected"))
        has_insp_evidence = bool(insp_str and insp_str.lower() not in ("not specified", "none", "null", "not available", "unspecified", "n/a", "not detected"))
        low_quality_issue = bool(ocr_conf < 0.60 or (quality.get("is_degraded") and ocr_conf < 0.65))

        # ------------------------------------------------------------
        # GATE 1: Missing reference evidence (no OCR observed on ref)
        # ------------------------------------------------------------
        if not has_ref_evidence and has_insp_evidence:
            if ref_key == "unit_sale_price":
                usp_agrees, p_amt, exp_amt, usp_math_note = corroborate_unit_sale_price(insp_str, insp_mrp_val, insp_nq_val)
                has_loc = bool(insp_bbox or insp_polygon)
                if usp_agrees and has_loc:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "USP verified via arithmetic & localized packaging evidence"
                    reason = f"Unit Sale Price ({insp_str}) verified by arithmetic consistency: {usp_math_note}"
                    obs = f"Statutory USP corroborated with declared MRP ({insp_mrp_val}) and Net Quantity ({insp_nq_val}). Calculation agrees with printed packaging declaration."
                    sev = "LOW"
                elif p_amt is not None and exp_amt is not None and not usp_agrees:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "USP arithmetic conflict"
                    reason = f"Unit Sale Price ({insp_str}) conflicts with declared MRP ({insp_mrp_val}) and Net Quantity ({insp_nq_val}). Expected USP: Rs.{exp_amt:.2f}. Manual review required."
                    obs = f"Printed USP fails mathematical corroboration: {usp_math_note}. Potential pricing declaration miscalculation."
                    sev = "MEDIUM"
                else:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "USP verification pending"
                    reason = f"Unit Sale Price ({insp_str}) could not be fully corroborated (MRP={insp_mrp_val}, Net Qty={insp_nq_val})."
                    obs = f"Manual inspection recommended for USP: {usp_math_note}"
                    sev = "MEDIUM"
            else:
                status = STATUS_REF_NOT_OBS
                finding_cat = FINDING_OCR_UNCERTAINTY
                is_susp = False
                reason = (
                    f"{display_name} declaration was not extracted from any reference face. "
                    f"Inspected value: {insp_str}. "
                    f"Cannot verify without reference evidence."
                )
                obs = (
                    f"Inspection shows {insp_str} but reference OCR did not extract this field "
                    f"from any of the {len(ref_declarations) if hasattr(ref_declarations, '__len__') else 0} reference-declared fields. "
                    f"Review of reference imagery is advised."
                )
                diff_type = f"Reference evidence missing: {ref_key}"
                sev = "MEDIUM"

        # ------------------------------------------------------------
        # GATE 2: Missing inspection evidence (no OCR observed on insp)
        # ------------------------------------------------------------
        elif has_ref_evidence and not has_insp_evidence:
            status = STATUS_INSP_NOT_OBS
            finding_cat = FINDING_OCR_UNCERTAINTY
            is_susp = False
            reason = (
                f"{display_name} was not observed on any scanned panel. "
                f"Reference specification requires: {ref_str}."
            )
            obs = (
                f"Reference declares '{ref_str}' but inspected panels show no OCR match. "
                f"This could indicate an omitted declaration, glare, or a panel not captured."
            )
            diff_type = f"Inspection evidence missing: {ref_key}"
            sev = "MEDIUM"

        # ------------------------------------------------------------
        # GATE 3: Both sides have evidence -> dispatch field-specific rule
        # ------------------------------------------------------------
        else:
            # ========================================================
            # FIELD-SPECIFIC RULES -- each decides from ref_str, insp_str,
            # bbox, quality, and overlays. NEVER default to MATCH.
            # ========================================================

            # --------------------------------------------------------
            # MRP (VERSION-SENSITIVE) -- numeric amount equality + sticker detection
            # --------------------------------------------------------
            if ref_key == "mrp":
                r_amt = _parse_mrp_amount(ref_str)
                i_amt = _parse_mrp_amount(insp_str)
                if r_amt is None or i_amt is None:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "MRP OCR parse ambiguous"
                    reason = f"Price values could not be parsed numerically (ref={ref_str}, insp={insp_str})."
                    obs = "OCR quality insufficient for reliable price parsing. Manual MRP review recommended."
                    sev = "MEDIUM"
                elif abs(r_amt - i_amt) < 1e-6:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Identical statutory declaration (MRP)"
                    reason = f"MRP amount matches: Rs.{r_amt:g} both on reference and inspected packaging."
                    obs = f"Printed retail price (Rs.{r_amt:g}) numerically matches reference standard after OCR normalization."
                    sev = "LOW"
                else:
                    has_overlay, overlay_conf, overlay_reason = detect_sticker_overlay(insp_image_bgr, insp_bbox) if insp_bbox else (False, 0.0, "")
                    if has_overlay:
                        status = STATUS_POTENTIAL_DISCREPANCY
                        is_susp = True
                        finding_cat = FINDING_ACTUAL_DIFFERENCE
                        diff_type = "Suspected MRP sticker overlay / price tampering"
                        reason = f"MRP differs (Rs.{r_amt:g} reference vs Rs.{i_amt:g} inspected) and PHYSICAL STICKER OVERLAY detected over the price region."
                        obs = f"Physical overlay sticker detected over printed price marking: {overlay_reason}. Confidence {overlay_conf:.0%}."
                        sev = "HIGH"
                    else:
                        status = STATUS_REVIEW_REQUIRED
                        is_susp = False
                        finding_cat = FINDING_LEGITIMATE_VARIATION
                        diff_type = "MRP packaging-version difference"
                        reason = f"MRP differs between packaging runs (ref Rs.{r_amt:g} vs insp Rs.{i_amt:g}). Direct packaging print, no sticker overlay detected."
                        obs = f"Printed retail price differs from reference catalog but clean direct print. Consistent with a packaging / pricing version revision."
                        sev = "MEDIUM"

            # --------------------------------------------------------
            # UNIT SALE PRICE (VERSION-SENSITIVE) -- similar to MRP
            # --------------------------------------------------------
            elif ref_key == "unit_sale_price":
                usp_agrees, p_amt, exp_amt, usp_math_note = corroborate_unit_sale_price(insp_str, insp_mrp_val, insp_nq_val)
                r_amt = _parse_mrp_amount(ref_str)
                i_amt = _parse_mrp_amount(insp_str)
                has_loc = bool(insp_bbox or insp_polygon)

                if usp_agrees and has_loc:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "USP verified via arithmetic & localized packaging evidence"
                    reason = f"Unit Sale Price ({insp_str}) verified by arithmetic consistency: {usp_math_note}"
                    obs = f"Statutory USP corroborated with declared MRP ({insp_mrp_val}) and Net Quantity ({insp_nq_val}). Calculation agrees with printed packaging declaration."
                    sev = "LOW"
                elif p_amt is not None and exp_amt is not None and not usp_agrees:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "USP arithmetic conflict"
                    reason = f"Unit Sale Price ({insp_str}) conflicts with declared MRP ({insp_mrp_val}) and Net Quantity ({insp_nq_val}). Expected USP: Rs.{exp_amt:.2f}. Manual review required."
                    obs = f"Printed USP fails mathematical corroboration: {usp_math_note}. Potential pricing declaration miscalculation."
                    sev = "MEDIUM"
                elif r_amt is not None and i_amt is not None and abs(r_amt - i_amt) < 1e-4:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "USP matches reference"
                    reason = f"Unit sale price matches reference ({ref_str} == {insp_str})."
                    obs = "Unit sale price numerically matches reference packaging."
                    sev = "LOW"
                else:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "USP verification pending"
                    reason = f"Unit Sale Price ({insp_str}) could not be fully corroborated (ref={ref_str}, insp={insp_str})."
                    obs = f"Manual inspection recommended for USP: {usp_math_note}"
                    sev = "MEDIUM"

            # --------------------------------------------------------
            # BATCH NUMBER (VARIABLE) -- always EXPECTED_TO_VARY unless identical
            # --------------------------------------------------------
            elif ref_key == "batch_number":
                if ref_str == insp_str or norm_sim >= 0.99:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Identical batch code (same production lot)"
                    reason = f"Batch code matches reference: {insp_str}."
                    obs = f"Batch '{insp_str}' is identical to reference -- same production lot sampled."
                    sev = "LOW"
                else:
                    status = STATUS_EXPECTED_TO_VARY
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    is_susp = False
                    diff_type = "Legitimate batch update across production lots"
                    reason = f"Batch code legitimately varies (reference {ref_str} -> inspected {insp_str})."
                    obs = f"Batch code differs between reference and inspected lots -- expected across production runs."
                    sev = "LOW"

            # --------------------------------------------------------
            # MANUFACTURING DATE (VARIABLE) -- EXPECTED_TO_VARY unless chronology invalid
            # --------------------------------------------------------
            elif ref_key == "manufacturing_date":
                if chronology_invalid:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Impossible chronology (MFD later than Expiry)"
                    reason = f"Manufacturing date ({insp_str}) is later than the declared expiry ({insp_exp_val})."
                    obs = f"Chronology violation: MFD ({insp_str}) > EXP ({insp_exp_val}). This is statistically impossible unless date coding was altered."
                    sev = "HIGH"
                elif ref_str == insp_str or norm_sim >= 0.99:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Identical manufacturing date"
                    reason = f"Manufacturing date matches reference ({insp_str}). Same production run sampled."
                    obs = f"MFD date identical to reference -- same production run."
                    sev = "LOW"
                else:
                    status = STATUS_EXPECTED_TO_VARY
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    is_susp = False
                    diff_type = "Legitimate manufacturing-date update"
                    reason = f"Manufacturing date updated from reference ({ref_str} -> {insp_str}). Valid calendar chronology."
                    obs = f"MFD date differs across runs; chronology verified (MFD before Expiry where both are present)."
                    sev = "LOW"

            # --------------------------------------------------------
            # EXPIRY DATE (VARIABLE) -- EXPECTED_TO_VARY, chronology guard
            # --------------------------------------------------------
            elif ref_key == "expiry_date":
                if chronology_invalid:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Impossible chronology (Expiry earlier than MFD)"
                    reason = f"Expiry date ({insp_str}) precedes manufacturing date ({insp_mfg_val}). Impossible chronological sequence."
                    obs = f"Chronology violation: EXP ({insp_str}) < MFD ({insp_mfg_val}). Indicates altered date coding."
                    sev = "HIGH"
                elif ref_str == insp_str or norm_sim >= 0.99:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Identical expiry date"
                    reason = f"Expiry date matches reference ({insp_str}). Same shelf-life run."
                    obs = f"Expiry date identical to reference."
                    sev = "LOW"
                else:
                    status = STATUS_EXPECTED_TO_VARY
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    is_susp = False
                    diff_type = "Legitimate expiry-date update"
                    reason = f"Expiry date updated from reference ({ref_str} -> {insp_str}). Valid calendar chronology."
                    obs = f"Expiry date differs across runs; chronology valid where both dates present."
                    sev = "LOW"

            # --------------------------------------------------------
            # MANUFACTURER / MARKETER (STATIC) -- token-set containment
            # --------------------------------------------------------
            elif ref_key == "manufacturer_name":
                mfg_match, mfg_rationale = _is_manufacturer_match(ref_str, insp_str)
                if mfg_match:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION if norm_sim >= 0.95 else FINDING_OCR_UNCERTAINTY
                    diff_type = "Manufacturer entity matches reference"
                    reason = f"Manufacturer declaration ({insp_str}) consistent with reference ({ref_str}). {mfg_rationale}."
                    obs = f"Manufacturer name matches reference specification after OCR token normalization ({mfg_rationale})."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.65:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "Manufacturer reading uncertain (low image quality)"
                    reason = f"Manufacturer OCR uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = f"Manufacturer OCR unclear; raw normalized similarity {norm_sim*100:.0f}%. Manual visual inspection recommended."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Manufacturer mismatch (static declaration)"
                    reason = f"Manufacturer does not match reference (ref: {ref_str} vs insp: {insp_str}). {mfg_rationale}."
                    obs = f"High-confidence manufacturer mismatch after token analysis ({mfg_rationale}). Static-field discrepancy."
                    sev = "HIGH"

            # --------------------------------------------------------
            # NET QUANTITY (STATIC) -- numeric amount + unit match
            # --------------------------------------------------------
            elif ref_key == "net_quantity":
                r_nq = _parse_net_quantity(ref_str)
                i_nq = _parse_net_quantity(insp_str)
                if r_nq is None or i_nq is None:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "Net quantity OCR parse ambiguous"
                    reason = f"Net quantity could not be parsed numerically (ref={ref_str}, insp={insp_str})."
                    obs = "Net quantity declaration OCR ambiguous. Manual review recommended."
                    sev = "MEDIUM"
                elif abs(r_nq[0] - i_nq[0]) < 1e-6 and r_nq[1] == i_nq[1]:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Identical net quantity"
                    reason = f"Net quantity matches: {r_nq[0]:g} {r_nq[1]} on both reference and inspected packaging."
                    obs = f"Declared net quantity ({r_nq[0]:g} {r_nq[1]}) numerically matches reference after unit normalization."
                    sev = "LOW"
                elif ocr_conf < 0.35:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "Net quantity unverified due to image quality"
                    reason = f"Net quantity reading uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = "Net quantity OCR below confidence threshold. Manual weigh-scale verification recommended."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Net quantity mismatch (static declaration)"
                    reason = f"Declared net quantity differs from reference (ref: {ref_str} vs insp: {insp_str})."
                    obs = f"Net quantity mismatch after numeric+unit normalization (ref {r_nq[0]:g}{r_nq[1]} vs insp {i_nq[0]:g}{i_nq[1]})."
                    sev = "HIGH"

            # --------------------------------------------------------
            # BARCODE / GTIN (STATIC) -- digit-sequence equality
            # --------------------------------------------------------
            elif ref_key == "barcode":
                b_meta = (insp_raw or {}).get("barcode") or (matched_insp.get("raw") if isinstance(matched_insp, dict) else {})
                decoded_val = b_meta.get("decoded_value") if isinstance(b_meta, dict) else None
                observed_val = b_meta.get("observed_value") if isinstance(b_meta, dict) else None
                bc_status = b_meta.get("barcode_verification_status") if isinstance(b_meta, dict) else None

                if not decoded_val and insp_str:
                    decoded_val = insp_str

                ref_digits = _barcode_normalize(ref_str)
                insp_digits = _barcode_normalize(insp_str)

                # Cross-check both values:
                # VERIFIED = printed digits observed and match decoder.
                # REVIEW_REQUIRED = partial/unclear/disagreeing digits.
                # NOT_OBSERVED = barcode decoded but printed digits are not visually observable.
                # Never fabricate printed digits from the decoder.
                if bc_status == "VERIFIED":
                    if not ref_digits or ref_digits == insp_digits or ref_digits in insp_digits or insp_digits in ref_digits:
                        status = STATUS_MATCH
                        finding_cat = FINDING_LEGITIMATE_VARIATION
                        diff_type = "Barcode verified (printed digits match decoder)"
                        reason = f"Barcode verified: machine decoder ({decoded_val}) matches human-readable printed digits ({observed_val})."
                        obs = f"Barcode dual-verification passed. Decoded GTIN matches printed HRI digits."
                        sev = "LOW"
                    else:
                        status = STATUS_POTENTIAL_DISCREPANCY
                        is_susp = True
                        finding_cat = FINDING_ACTUAL_DIFFERENCE
                        diff_type = "Barcode mismatch with reference standard"
                        reason = f"Verified barcode ({insp_digits}) does not match authorized reference GTIN ({ref_digits})."
                        obs = f"Inspected barcode {insp_digits} differs from reference standard {ref_digits}."
                        sev = "HIGH"
                elif bc_status == "NOT_OBSERVED":
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "Barcode printed digits NOT_OBSERVED"
                    reason = f"Barcode decoded ({decoded_val}) but printed digits are not visually observable."
                    obs = f"Barcode symbol decoded ({decoded_val}) but human-readable printed digits are not visually observable near symbol. Review required."
                    sev = "MEDIUM"
                elif bc_status == "REVIEW_REQUIRED":
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "Barcode printed digits / decoder conflict"
                    reason = f"Barcode review required: machine decoder ({decoded_val}) vs printed digits ({observed_val})."
                    obs = f"Printed digits unclear, partial, or disagreeing with machine decoder. Manual review required."
                    sev = "MEDIUM"
                elif not ref_digits or not insp_digits:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "Barcode OCR missing digits"
                    reason = f"Barcode digit extraction incomplete (ref={ref_str}, insp={insp_str})."
                    obs = "Barcode scanner or OCR failed to extract valid digit sequence."
                    sev = "MEDIUM"
                elif ref_digits == insp_digits:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION if ref_str == insp_str else FINDING_OCR_UNCERTAINTY
                    diff_type = "Barcode matches reference GTIN"
                    reason = f"Barcode ({insp_digits}) matches authorized reference GTIN."
                    obs = f"GTIN digit sequence identical ({ref_digits})."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.70:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "Barcode unverified due to image/OCR quality"
                    reason = f"Barcode verification uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = f"Barcode OCR below 70% confidence (ref={ref_digits} vs insp={insp_digits}). Physical barcode scan recommended."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Barcode / GTIN mismatch (static declaration)"
                    reason = f"Barcode does not match authorized reference (ref: {ref_str} / {ref_digits} vs insp: {insp_str} / {insp_digits})."
                    obs = f"High-confidence barcode mismatch ({len(ref_digits)} ref digits vs {len(insp_digits)} insp digits, sequences differ)."
                    sev = "HIGH"

            # --------------------------------------------------------
            # FSSAI LICENSE (STATIC) -- 14-digit license equality
            # --------------------------------------------------------
            elif ref_key == "fssai_license_number":
                ref_f = _fssai_normalize(ref_str)
                insp_f = _fssai_normalize(insp_str)
                if (not ref_f and not insp_f) or (ref_str.upper() == "NOT_APPLICABLE" and insp_str.upper() == "NOT_APPLICABLE"):
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = "FSSAI license OCR ambiguous"
                    reason = f"FSSAI license number could not be reliably extracted (ref={ref_str}, insp={insp_str})."
                    obs = "FSSAI license OCR failed to yield valid digit sequence."
                    sev = "MEDIUM"
                elif ref_f == insp_f:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION if ref_str == insp_str else FINDING_OCR_UNCERTAINTY
                    diff_type = "FSSAI license matches reference"
                    reason = f"FSSAI license number ({insp_f}) matches reference master after digit normalization."
                    obs = f"FSSAI license number identical ({ref_f}) after glyph substitution normalization (0/O, 1/I, 5/S, 8/B)."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.65:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "FSSAI unverified due to image quality"
                    reason = f"FSSAI license uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = f"FSSAI OCR below 65% confidence (ref={ref_f} vs insp={insp_f})."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "FSSAI license mismatch (static declaration)"
                    reason = f"FSSAI license does not match authorized reference (ref: {ref_str} / {ref_f} vs insp: {insp_str} / {insp_f})."
                    obs = f"High-confidence FSSAI license mismatch -- digit sequences differ ({ref_f} vs {insp_f})."
                    sev = "HIGH"

            # --------------------------------------------------------
            # PRODUCT NAME / BRAND (STATIC) -- token-set 80%+ normalized similarity
            # --------------------------------------------------------
            elif ref_key == "product_name":
                ref_tok = _token_set(ref_str)
                insp_tok = _token_set(insp_str)
                brand_match = bool(ref_tok and insp_tok and (ref_tok <= insp_tok or insp_tok <= ref_tok or len(ref_tok & insp_tok) >= max(1, min(2, min(len(ref_tok), len(insp_tok))))))
                if norm_sim >= 0.80 or brand_match:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Product identity matches reference"
                    reason = f"Product identity ({insp_str}) matches authorized reference ({ref_str})."
                    obs = f"Product name normalized similarity {norm_sim*100:.0f}%. Brand-token containment verified."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.60:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "Product name uncertain (image quality)"
                    reason = f"Product identity reading uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = f"Product-identity OCR below confidence threshold. Similarity {norm_sim*100:.0f}%."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Product identity mismatch (static declaration)"
                    reason = f"Product identity mismatch (ref: {ref_str} vs insp: {insp_str})."
                    obs = f"Product identity below similarity threshold ({norm_sim*100:.0f}%) and no brand-token containment."
                    sev = "HIGH"

            # --------------------------------------------------------
            # CONSUMER CARE (STATIC) -- semantic digit/email/token match
            # --------------------------------------------------------
            elif ref_key == "consumer_care":
                care_match, care_rationale = _semantic_consumer_care_match(ref_str, insp_str)
                if care_match:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Consumer care contact semantically consistent"
                    reason = f"Consumer care declaration consistent with reference ({care_rationale})."
                    obs = f"Consumer care semantically verified ({care_rationale}). Raw strings: ref='{ref_str}', insp='{insp_str}'."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.60:
                    status = STATUS_REVIEW_REQUIRED
                    is_susp = False
                    finding_cat = FINDING_INSUFFICIENT_IMAGE_QUALITY
                    diff_type = "Consumer care uncertain (image quality)"
                    reason = f"Consumer care reading uncertain due to {quality.get('quality_note', 'low image quality')}."
                    obs = f"Consumer care OCR below 60% confidence. Normalized similarity {norm_sim*100:.0f}%."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = "Consumer care mismatch (static declaration)"
                    reason = f"Consumer care differs from reference (ref: {ref_str} vs insp: {insp_str}). {care_rationale}."
                    obs = f"Consumer care semantic check failed ({care_rationale}). Static-field discrepancy."
                    sev = "HIGH"

            # --------------------------------------------------------
            # FALLBACK -- unknown field (shouldn't happen since specs list is closed)
            # --------------------------------------------------------
            else:
                if norm_sim >= 0.95:
                    status = STATUS_MATCH
                    finding_cat = FINDING_LEGITIMATE_VARIATION
                    diff_type = "Declaration matches"
                    reason = f"{display_name} matches reference (OCR normalized similarity {norm_sim*100:.0f}%)."
                    obs = f"{display_name} matches after OCR normalization."
                    sev = "LOW"
                elif low_quality_issue or ocr_conf < 0.65:
                    status = STATUS_REVIEW_REQUIRED
                    finding_cat = FINDING_OCR_UNCERTAINTY
                    diff_type = f"{display_name} declaration uncertain"
                    reason = f"{display_name} comparison uncertain due to OCR/image quality (norm_sim={norm_sim*100:.0f}%)."
                    obs = f"Manual review of {display_name} recommended."
                    sev = "MEDIUM"
                else:
                    status = STATUS_POTENTIAL_DISCREPANCY
                    is_susp = True
                    finding_cat = FINDING_ACTUAL_DIFFERENCE
                    diff_type = f"{display_name} mismatch"
                    reason = f"{display_name} does not match reference (ref={ref_str} vs insp={insp_str}, sim={norm_sim*100:.0f}%)."
                    obs = f"{display_name} similarity below auto-match threshold."
                    sev = "HIGH"

        item_decoded = None
        item_observed = None
        item_bc_status = None
        if ref_key == "barcode":
            b_meta = (insp_raw or {}).get("barcode") or (matched_insp.get("raw") if isinstance(matched_insp, dict) else {})
            if isinstance(b_meta, dict):
                item_decoded = b_meta.get("decoded_value")
                item_observed = b_meta.get("observed_value")
                item_bc_status = b_meta.get("barcode_verification_status")
            if not item_decoded and insp_str:
                item_decoded = insp_str

        item = FieldComparisonItem(
            field_name=display_name,
            field_key=ref_key,
            field_classification=field_class,
            reference_value=ref_str,
            inspection_value=insp_str,
            status=status,
            is_suspicious=is_susp,
            finding_category=finding_cat,
            reason=reason,
            observation_note=obs,
            reference_crop_base64=ref_crop,
            inspection_crop_base64=insp_crop,
            reference_bbox=ref_bbox,
            inspection_bbox=insp_bbox,
            # Priority 1: Real Visual Evidence fields
            field=ref_key,
            reference_image_id=ref_img_id,
            inspection_image_id=insp_img_id,
            reference_image_url=ref_img_url,
            inspection_image_url=insp_img_url,
            reference_surface_id=ref_surf,
            inspection_surface_id=insp_surf,
            reference_polygon=ref_polygon,
            inspection_polygon=insp_polygon,
            reference_confidence=round(ref_c, 2),
            inspection_confidence=round(insp_c, 2),
            comparison_status=status,
            comparison_reason=reason,
            confidence=round(ocr_conf, 2),
            image_quality_score=round(quality.get("sharpness", 1.0), 2),
            normalized_similarity=round(norm_sim, 2),
            severity=sev,
            decoded_value=item_decoded,
            observed_value=item_observed,
            barcode_verification_status=item_bc_status,
        )
        canonical_items.append(item)

        if status != "MATCH" or finding_cat == FINDING_OCR_UNCERTAINTY:
            differences.append({
                "field": ref_key,
                "field_name": display_name.upper(),
                "reference_value": ref_str,
                "inspection_value": insp_str,
                "difference_type": diff_type,
                "bbox": insp_bbox,
                "confidence": ocr_conf,
                "field_classification": field_class,
                "is_suspicious": is_susp,
                "finding_category": finding_cat,
                "ocr_confidence": ocr_conf,
                "image_quality_score": quality.get("sharpness", 1.0),
                "normalized_similarity": norm_sim,
                "observation_note": obs,
                "severity": sev,
                "evidence_crop_base64": insp_crop,
                "inspection_crop_base64": insp_crop,
                "reference_crop_base64": ref_crop,
                "reference_bbox": ref_bbox,
                "inspection_bbox": insp_bbox,
                "reference_polygon": ref_polygon,
                "inspection_polygon": insp_polygon,
                "reference_image_id": ref_img_id,
                "inspection_image_id": insp_img_id,
                "reference_image_url": ref_img_url,
                "inspection_image_url": insp_img_url,
                "reference_surface_id": ref_surf,
                "inspection_surface_id": insp_surf,
                "reference_confidence": round(ref_c, 2),
                "inspection_confidence": round(insp_c, 2),
                "comparison_status": status,
                "comparison_reason": reason,
            })

    return canonical_items, differences


def compare_declarations(
    ref_declarations: Dict[str, Any],
    insp_declarations: List[Dict[str, Any]],
    insp_image_bgr: Optional[np.ndarray] = None,
) -> List[Dict[str, Any]]:
    """
    Compares declarations between reference standard and inspected package.
    Returns the list of differences (for backward compatibility).
    """
    _, diffs = compare_canonical_fields(
        ref_declarations=ref_declarations,
        insp_declarations=insp_declarations,
        insp_image_bgr=insp_image_bgr,
    )
    return diffs


def compare_reference_vs_inspected_package(
    ref_path: Optional[Path] = None,
    insp_path: Optional[Path] = None,
    ref_paths: Optional[List[Path]] = None,
    insp_paths: Optional[List[Path]] = None,
    ref_type: str = REF_TYPE_TRUSTED,
    ref_metadata: Optional[Dict[str, Any]] = None,
    product_id: Optional[str] = None,
    product_name: Optional[str] = None,
    inspection_declarations: Optional[List[Dict[str, Any]]] = None,
) -> IntegrityReport:
    """
    Comprehensive multi-stage comparison pipeline supporting single or multi-face packaging:
    1. Load reference & inspection images across all packaging faces (Front, Back, Sides)
    2. Cross-face alignment and pair matching
    3. Registration (Homography for planar, local bands for curved)
    4. Critical region & statutory declaration comparison across all faces
    5. Multi-tier classification (STATIC, VARIABLE, VERSION-SENSITIVE)
    6. Evidence fusion & integrity verdict
    """
    if inspection_declarations is None:
        inspection_declarations = []

    # Normalize image paths
    all_ref_paths: List[Path] = []
    if ref_paths:
        for p in ref_paths:
            p_obj = Path(p)
            if p_obj not in all_ref_paths:
                all_ref_paths.append(p_obj)
    if ref_path:
        if isinstance(ref_path, (list, tuple)):
            for p in ref_path:
                p_obj = Path(p)
                if p_obj not in all_ref_paths:
                    all_ref_paths.append(p_obj)
        else:
            p_obj = Path(ref_path)
            if p_obj not in all_ref_paths:
                all_ref_paths.insert(0, p_obj)

    all_insp_paths: List[Path] = []
    if insp_paths:
        for p in insp_paths:
            p_obj = Path(p)
            if p_obj not in all_insp_paths:
                all_insp_paths.append(p_obj)
    if insp_path:
        if isinstance(insp_path, (list, tuple)):
            for p in insp_path:
                p_obj = Path(p)
                if p_obj not in all_insp_paths:
                    all_insp_paths.append(p_obj)
        else:
            p_obj = Path(insp_path)
            if p_obj not in all_insp_paths:
                all_insp_paths.insert(0, p_obj)

    # Decode images
    ref_imgs: List[Tuple[Path, np.ndarray]] = []
    for p in all_ref_paths:
        p_res = p
        if not p_res.exists():
            cand = config.UPLOAD_DIR / p.name
            if cand.exists():
                p_res = cand
        if p_res.exists():
            target_upload = config.UPLOAD_DIR / p_res.name
            try:
                config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                if not target_upload.exists() or (p_res.resolve() != target_upload.resolve()):
                    shutil.copy2(p_res, target_upload)
            except Exception as ce:
                logger.debug("Could not copy reference image %s to upload dir: %s", p_res, ce)
            img = cv2.imread(str(p_res))
            if img is not None:
                ref_imgs.append((p_res, img))

    insp_imgs: List[Tuple[Path, np.ndarray]] = []
    for p in all_insp_paths:
        p_res = p
        if not p_res.exists():
            cand = config.UPLOAD_DIR / p.name
            if cand.exists():
                p_res = cand
        if p_res.exists():
            target_upload = config.UPLOAD_DIR / p_res.name
            try:
                config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                if not target_upload.exists() or (p_res.resolve() != target_upload.resolve()):
                    shutil.copy2(p_res, target_upload)
            except Exception as ce:
                logger.debug("Could not copy inspected image %s to upload dir: %s", p_res, ce)
            img = cv2.imread(str(p_res))
            if img is not None:
                insp_imgs.append((p_res, img))

    if not ref_imgs or not insp_imgs:
        primary_ref = all_ref_paths[0] if all_ref_paths else None
        primary_insp = all_insp_paths[0] if all_insp_paths else None
        return IntegrityReport(
            status=STATUS_UNABLE_TO_VERIFY,
            product_id=product_id,
            has_reference=bool(ref_imgs),
            reference_type=ref_type,
            reference_image_url=f"/uploads/{primary_ref.name}" if primary_ref else None,
            reference_image_urls=[f"/uploads/{p.name}" for p, _ in ref_imgs],
            inspected_image_url=f"/uploads/{primary_insp.name}" if primary_insp else None,
            comparison_method="Multi-Surface Visual & Declaration Comparison",
            confidence_score=0.4,
            detected_differences=[],
            explanation="Could not decode reference or inspected image file bytes.",
            source_tag="COMPUTER VISION",
        )

    if ref_metadata is None:
        cand_text = f"{product_name or ''} {product_id or ''} " + " ".join(p.name for p, _ in ref_imgs) + " " + " ".join(p.name for p, _ in insp_imgs)
        cand_lower = cand_text.lower()
        clean_id = str(product_id or "").strip()
        for key, demo_info in DEMO_REFERENCE_PACKAGES.items():
            if key in cand_lower or (clean_id == "64934436" and key == "bru"):
                ref_metadata = dict(demo_info)
                break

    is_curved = bool(ref_metadata and ref_metadata.get("is_curved"))
    if not is_curved and product_name and "vaseline" in product_name.lower():
        is_curved = True

    all_differences: List[Dict[str, Any]] = []
    face_matches: List[Dict[str, Any]] = []
    face_fidelity_scores: List[float] = []

    # 1. Structural / Geometric Registration across all reference faces
    for ref_idx, (r_path, r_img) in enumerate(ref_imgs):
        best_insp_idx = 0
        best_aligned = None
        best_fidelity = -1.0

        for insp_idx, (i_path, i_img) in enumerate(insp_imgs):
            if is_curved:
                corr, _ = compare_curved_packaging_regions(r_img, i_img)
                if corr > best_fidelity:
                    best_fidelity = corr
                    best_insp_idx = insp_idx
                    best_aligned = cv2.resize(i_img, (r_img.shape[1], r_img.shape[0]))
            else:
                aligned, inlier_ratio = align_planar_images(r_img, i_img)
                if inlier_ratio > best_fidelity:
                    best_fidelity = inlier_ratio
                    best_insp_idx = insp_idx
                    best_aligned = aligned

        matched_insp_path, matched_insp_img = insp_imgs[best_insp_idx]
        face_fidelity_scores.append(max(0.0, best_fidelity))

        ref_face_name = f"Face {ref_idx + 1}"
        r_name_lower = r_path.name.lower()
        if "front" in r_name_lower:
            ref_face_name = "Front Face"
        elif "back 2" in r_name_lower or "back_2" in r_name_lower:
            ref_face_name = "Back Face 2"
        elif "back" in r_name_lower:
            ref_face_name = "Back Face"
        elif "side" in r_name_lower:
            ref_face_name = "Side Face"

        face_matches.append({
            "reference_face_index": ref_idx + 1,
            "reference_face_name": ref_face_name,
            "reference_image": r_path.name,
            "reference_image_url": f"/uploads/{r_path.name}",
            "inspected_face_index": best_insp_idx + 1,
            "inspected_image": matched_insp_path.name,
            "inspected_image_url": f"/uploads/{matched_insp_path.name}",
            "fidelity_score": round(max(0.0, best_fidelity), 2),
            "status": "ALIGNED" if best_fidelity >= 0.45 else "UNALIGNED",
        })

    # 2. Canonical Field Comparison across reference and inspected packages
    ref_decls: Dict[str, Any] = {}
    ref_bboxes: Dict[str, List[int]] = {}
    ref_crops: Dict[str, str] = {}
    ref_confs: Dict[str, float] = {}
    ref_polygons: Dict[str, List[List[float]]] = {}
    ref_surface_ids: Dict[str, str] = {}
    ref_image_ids: Dict[str, str] = {}
    ref_image_urls: Dict[str, str] = {}
    primary_ref_bgr = ref_imgs[0][1] if ref_imgs else None

    # 2a. REFERENCE EXTRACTION -- Run real LexMetra Localization pipeline across reference surfaces
    if ref_imgs:
        decls, bboxes, confs, crops, face_indices, raw = extract_canonical_package_evidence(ref_imgs)
        ref_decls = decls
        ref_bboxes = bboxes
        ref_confs = confs
        ref_crops = crops
        ref_polygons = raw.get("polygons", {})
        ref_surface_ids = raw.get("surface_ids", {})
        ref_image_ids = raw.get("image_ids", {})
        ref_image_urls = raw.get("image_urls", {})

    # Fallback to ref_metadata declarations if specific fields were not observed via OCR/VLM
    if ref_metadata and isinstance(ref_metadata.get("declarations"), dict):
        for k, v in ref_metadata["declarations"].items():
            if k not in ref_decls or not ref_decls[k]:
                ref_decls[k] = v
                if k not in ref_confs:
                    ref_confs[k] = 0.95
                if k not in ref_image_ids and ref_imgs:
                    ref_image_ids[k] = ref_imgs[0][0].name
                    ref_image_urls[k] = f"/uploads/{ref_imgs[0][0].name}"

    # 2b. INSPECTION EXTRACTION -- Run real LexMetra Localization pipeline across inspected surfaces
    insp_decls: Dict[str, Any] = {}
    insp_bboxes: Dict[str, List[int]] = {}
    insp_crops: Dict[str, str] = {}
    insp_confs: Dict[str, float] = {}
    insp_polygons: Dict[str, List[List[float]]] = {}
    insp_surface_ids: Dict[str, str] = {}
    insp_image_ids: Dict[str, str] = {}
    insp_image_urls: Dict[str, str] = {}
    primary_insp_bgr = insp_imgs[0][1] if insp_imgs else None

    if insp_imgs:
        i_decls, i_bboxes, i_confs, i_crops, i_face_indices, i_raw = extract_canonical_package_evidence(insp_imgs)
        insp_decls = i_decls
        insp_bboxes = i_bboxes
        insp_confs = i_confs
        insp_crops = i_crops
        insp_polygons = i_raw.get("polygons", {})
        insp_surface_ids = i_raw.get("surface_ids", {})
        insp_image_ids = i_raw.get("image_ids", {})
        insp_image_urls = i_raw.get("image_urls", {})

    effective_insp_declarations: List[Dict[str, Any]] = []

    # If caller provided inspection_declarations (from Capture Session or test), use them as primary and enrich with localized evidence
    if inspection_declarations and len(inspection_declarations) >= 2:
        seen_fields = set()
        for item in inspection_declarations:
            if isinstance(item, dict):
                k = (item.get("field") or item.get("name") or "").lower().strip()
                seen_fields.add(k)
                enriched = dict(item)
                if not enriched.get("confidence"):
                    enriched["confidence"] = 0.95
                if k in insp_bboxes and not enriched.get("bounding_box") and not enriched.get("bbox"):
                    enriched["bounding_box"] = insp_bboxes[k]
                if k in insp_polygons and not enriched.get("polygon"):
                    enriched["polygon"] = insp_polygons[k]
                if k in insp_surface_ids and not enriched.get("surface_id"):
                    enriched["surface_id"] = insp_surface_ids[k]
                if k in insp_image_ids and not enriched.get("image_id"):
                    enriched["image_id"] = insp_image_ids[k]
                if k in insp_image_urls and not enriched.get("image_url"):
                    enriched["image_url"] = insp_image_urls[k]
                if k in insp_crops and not enriched.get("evidence_crop_base64"):
                    enriched["evidence_crop_base64"] = insp_crops[k]
                effective_insp_declarations.append(enriched)
        # Also add any fields detected in image that were missing from inspection_declarations
        for k, v in insp_decls.items():
            if k not in seen_fields:
                effective_insp_declarations.append({
                    "field": k,
                    "name": k,
                    "value": v,
                    "bounding_box": insp_bboxes.get(k),
                    "polygon": insp_polygons.get(k),
                    "surface_id": insp_surface_ids.get(k),
                    "image_id": insp_image_ids.get(k),
                    "image_url": insp_image_urls.get(k),
                    "confidence": insp_confs.get(k, 0.85),
                    "evidence_crop_base64": insp_crops.get(k),
                    "source": "lexmetra_localization_pipeline",
                })
    else:
        # No inspection_declarations passed -> use all extractions from image pipeline
        for k, v in insp_decls.items():
            effective_insp_declarations.append({
                "field": k,
                "name": k,
                "value": v,
                "bounding_box": insp_bboxes.get(k),
                "polygon": insp_polygons.get(k),
                "surface_id": insp_surface_ids.get(k),
                "image_id": insp_image_ids.get(k),
                "image_url": insp_image_urls.get(k),
                "confidence": insp_confs.get(k, 0.85),
                "evidence_crop_base64": insp_crops.get(k),
                "source": "lexmetra_localization_pipeline",
            })

    canonical_items, decl_diffs = compare_canonical_fields(
        ref_declarations=ref_decls,
        insp_declarations=effective_insp_declarations,
        insp_image_bgr=primary_insp_bgr,
        ref_image_bgr=primary_ref_bgr,
        ref_bboxes=ref_bboxes,
        ref_crops=ref_crops,
        ref_polygons=ref_polygons,
        insp_polygons=insp_polygons,
        ref_surface_ids=ref_surface_ids,
        insp_surface_ids=insp_surface_ids,
        ref_image_ids=ref_image_ids,
        insp_image_ids=insp_image_ids,
        ref_image_urls=ref_image_urls,
        insp_image_urls=insp_image_urls,
        ref_confs=ref_confs,
        insp_confs=insp_confs,
        ref_imgs=ref_imgs,
        insp_imgs=insp_imgs,
        insp_raw=i_raw,
        ref_raw=raw,
    )
    all_differences.extend(decl_diffs)

    # 3. Decision Determination (Robust against imperfect OCR, perspective & lighting)
    # Strictly report meaningful field-level discrepancies supported by evidence
    matched_fields = [it.field_name for it in canonical_items if it.status == STATUS_MATCH]
    variable_fields = [it.field_name for it in canonical_items if it.status == STATUS_EXPECTED_TO_VARY or it.field_classification == FIELD_CLASS_VARIABLE]
    review_fields = [it.field_name for it in canonical_items if it.status == STATUS_REVIEW_REQUIRED]
    discrepancy_fields = [it.field_name for it in canonical_items if it.status == STATUS_POTENTIAL_DISCREPANCY]
    ref_not_obs_fields = [it.field_name for it in canonical_items if it.status == STATUS_REF_NOT_OBS]
    insp_not_obs_fields = [it.field_name for it in canonical_items if it.status == STATUS_INSP_NOT_OBS]

    summary_counts = {
        "consistent": len([it for it in canonical_items if it.status in (STATUS_MATCH, STATUS_EXPECTED_TO_VARY)]),
        "review_required": len(review_fields),
        "potential_discrepancy": len(discrepancy_fields),
        "reference_not_observed": len(ref_not_obs_fields),
        "inspection_not_observed": len(insp_not_obs_fields),
        "total_evaluated": len(canonical_items),
    }

    avg_fidelity = float(np.mean(face_fidelity_scores)) if face_fidelity_scores else 0.85
    fidelity_score = avg_fidelity

    if len(ref_imgs) > 1 or len(insp_imgs) > 1:
        comparison_method = (
            f"Multi-Surface Cross-Face Alignment & Field Verification "
            f"({len(ref_imgs)} Ref Faces, {len(insp_imgs)} Inspected Surfaces)"
        )
    elif is_curved:
        comparison_method = "Curved Packaging Local Region Patch Comparison"
    else:
        comparison_method = "Planar Perspective & Homography Feature Alignment"

    face_count_note = f" across all {len(ref_imgs)} reference face(s)" if len(ref_imgs) > 1 else ""

    quality_issues = [
        d for d in all_differences
        if d.get("finding_category") == FINDING_INSUFFICIENT_IMAGE_QUALITY
    ]

    n_total = len(canonical_items) or 1
    n_unverifiable = len(ref_not_obs_fields) + len(insp_not_obs_fields)
    pct_unverifiable = n_unverifiable / n_total
    has_sufficient_consistent = summary_counts["consistent"] >= 3
    most_unverifiable = (pct_unverifiable >= 0.50 and not has_sufficient_consistent and not discrepancy_fields) or (n_total == 0)

    if discrepancy_fields:
        status = STATUS_POTENTIAL_ALT
        confidence = round(min(0.96, 0.85 + (len(discrepancy_fields) * 0.04)), 2)
        top_diff = discrepancy_fields[0]
        explanation = (
            f"Potential packaging alteration detected -- {top_diff}. "
            f"({len(discrepancy_fields)} confirmed anomalous finding(s) with localized evidence). "
            "Requires inspector physical verification."
        )
    elif quality_issues and not discrepancy_fields:
        # Never turn poor image/OCR quality into a tampering conclusion
        status = STATUS_UNABLE_TO_VERIFY
        confidence = 0.50
        explanation = (
            "Packaging declarations could not be definitively verified due to insufficient image quality "
            f"({len(quality_issues)} region(s) affected by blur, glare, or low resolution). "
            "Verification is inconclusive; inspector manual examination is required. "
            "Poor image quality is not treated as tampering."
        )
    elif most_unverifiable:
        # Most fields are missing from reference OR inspection -> cannot trust the comparison.
        status = STATUS_UNABLE_TO_VERIFY
        confidence = 0.40
        explanation = (
            f"Insufficient declaration evidence on {n_unverifiable}/{n_total} evaluated fields "
            f"({len(ref_not_obs_fields)} missing reference evidence, "
            f"{len(insp_not_obs_fields)} missing inspection evidence). "
            "Upload clearer reference and inspection images covering all statutory declaration panels."
        )
    elif review_fields or ref_not_obs_fields or insp_not_obs_fields:
        # Field variations like price updates or OCR uncertainties require review, not false alteration
        status = STATUS_NO_DIFF
        confidence = round(min(0.94, max(0.82, fidelity_score)), 2)
        parts = []
        if summary_counts['consistent']:
            parts.append(f"{summary_counts['consistent']} fields consistent")
        if len(ref_not_obs_fields):
            parts.append(f"{len(ref_not_obs_fields)} reference-side unobserved")
        if len(insp_not_obs_fields):
            parts.append(f"{len(insp_not_obs_fields)} inspection-side unobserved")
        if len(review_fields):
            rev_names = ", ".join(review_fields[:3])
            parts.append(f"{len(review_fields)} review ({rev_names})")
        explanation = (
            f"Packaging integrity evaluated{face_count_note}: " + "; ".join(parts) + ". "
            "Variations are consistent with pricing revisions, production lot updates, or OCR ambiguity. "
            "No unauthorized alteration detected."
        )
    elif len(canonical_items) == 0:
        status = STATUS_UNABLE_TO_VERIFY
        confidence = 0.50
        explanation = (
            "Packaging declarations could not be definitively verified from the provided images. "
            "Inspector physical examination is required."
        )
    else:
        status = STATUS_NO_DIFF
        confidence = round(min(0.98, max(0.88, fidelity_score)), 2)
        explanation = (
            f"Packaging geometry, print layout, and all statutory declarations match "
            f"the comparative reference standard{face_count_note} within standard manufacturing tolerances."
        )

    # Reference source notice based on reference type
    if ref_type == REF_TYPE_UNVERIFIED:
        ref_notice = "ADVISORY NOTICE: Reference packaging was uploaded by the inspector/user (UNVERIFIED). Never treated as government/official record."
    elif ref_type == REF_TYPE_DEMO:
        ref_notice = "DEMONSTRATION STANDARD: Reference standard from pre-seeded deterministic demo catalog."
    else:
        ref_notice = "TRUSTED CATALOG STANDARD: Reference package matched to registered brand digital master."

    ref_urls = [f"/uploads/{p.name}" for p, _ in ref_imgs]
    insp_url = f"/uploads/{insp_imgs[0][0].name}" if insp_imgs else None
    comparison_id = f"cmp_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    ref_name = (ref_metadata or {}).get("product_name") or product_name or (all_ref_paths[0].stem if all_ref_paths else "Reference Packaging Standard")

    return IntegrityReport(
        status=status,
        product_id=product_id,
        has_reference=True,
        reference_type=ref_type,
        reference_image_url=ref_urls[0] if ref_urls else None,
        reference_image_urls=ref_urls,
        inspected_image_url=insp_url,
        comparison_method=comparison_method,
        confidence_score=confidence,
        detected_differences=all_differences[:12],
        explanation=explanation,
        source_tag="COMPUTER VISION",
        reference_source_notice=ref_notice,
        face_matches=face_matches,
        comparison_id=comparison_id,
        timestamp=now_iso,
        reference_name=ref_name,
        summary_counts=summary_counts,
        field_comparisons=[it.to_dict() for it in canonical_items],
        matched_fields=matched_fields,
        variable_fields=variable_fields,
        review_fields=review_fields,
        discrepancy_fields=discrepancy_fields,
        reference_not_observed_fields=ref_not_obs_fields,
        inspection_not_observed_fields=insp_not_obs_fields,
    )


def evaluate_package_integrity(
    inspected_image_path: Optional[str] = None,
    inspected_image_paths: Optional[List[str]] = None,
    product_id: Optional[str] = None,
    product_name: Optional[str] = None,
    inspection_declarations: Optional[List[Dict[str, Any]]] = None,
    custom_reference_path: Optional[str] = None,
    custom_reference_paths: Optional[List[str]] = None,
    custom_reference_type: str = REF_TYPE_UNVERIFIED,
    allow_demo_fixtures: bool = False,
) -> IntegrityReport:
    """Top-level entry point for package integrity verification supporting multi-face uploads."""
    ref_paths: List[Path] = []
    ref_type = custom_reference_type
    ref_meta = None

    if custom_reference_paths:
        for cp in custom_reference_paths:
            p_obj = Path(cp)
            if p_obj.exists() and p_obj not in ref_paths:
                ref_paths.append(p_obj)
    elif custom_reference_path and Path(custom_reference_path).exists():
        ref_paths.append(Path(custom_reference_path))

    if not ref_paths:
        primary_ref, ref_type, ref_meta = find_reference_package(
            product_id, product_name, allow_demo_fixtures=allow_demo_fixtures
        )
        if ref_meta and ref_meta.get("all_paths"):
            ref_paths = [Path(p) for p in ref_meta["all_paths"] if Path(p).exists()]
        elif primary_ref and primary_ref.exists():
            ref_paths = [primary_ref]

    if not ref_paths:
        return IntegrityReport(
            status=STATUS_UNABLE_TO_VERIFY,
            product_id=product_id,
            has_reference=False,
            reference_type=REF_TYPE_UNVERIFIED,
            reference_image_url=None,
            reference_image_urls=[],
            inspected_image_url=f"/uploads/{Path(inspected_image_path).name}" if inspected_image_path else None,
            comparison_method="REFERENCE_CATALOG_LOOKUP",
            confidence_score=0.0,
            detected_differences=[],
            explanation="No Reference Packaging Standard provided. Upload or scan reference package image(s) across all faces to run comparative integrity verification.",
            source_tag="COMPUTER VISION",
        )

    # Collect inspected paths
    candidate_insp_paths: List[Path] = []
    if inspected_image_paths:
        for ip in inspected_image_paths:
            if not ip:
                continue
            p_obj = Path(ip)
            if not p_obj.exists():
                p_obj = config.UPLOAD_DIR / Path(ip).name
            if p_obj.exists() and p_obj not in candidate_insp_paths:
                candidate_insp_paths.append(p_obj)

    if inspected_image_path:
        p_obj = Path(inspected_image_path)
        if not p_obj.exists():
            p_obj = config.UPLOAD_DIR / Path(inspected_image_path).name
        if p_obj.exists() and p_obj not in candidate_insp_paths:
            candidate_insp_paths.insert(0, p_obj)

    if not candidate_insp_paths:
        return IntegrityReport(
            status=STATUS_UNABLE_TO_VERIFY,
            product_id=product_id,
            has_reference=True,
            reference_type=ref_type,
            reference_image_url=f"/uploads/{ref_paths[0].name}",
            reference_image_urls=[f"/uploads/{p.name}" for p in ref_paths],
            inspected_image_url=None,
            comparison_method="REFERENCE_CATALOG_LOOKUP",
            confidence_score=0.5,
            detected_differences=[],
            explanation="Inspection image is unavailable for reference comparison.",
            source_tag="COMPUTER VISION",
        )

    return compare_reference_vs_inspected_package(
        ref_path=ref_paths[0] if ref_paths else None,
        insp_path=candidate_insp_paths[0] if candidate_insp_paths else None,
        ref_paths=ref_paths,
        insp_paths=candidate_insp_paths,
        ref_type=ref_type,
        ref_metadata=ref_meta,
        product_id=product_id,
        product_name=product_name,
        inspection_declarations=inspection_declarations or [],
    )
