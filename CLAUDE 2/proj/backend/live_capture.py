"""
Live capture intelligence - the "is this frame good enough to capture
evidence" loop, deliberately separate from the CAPTURED-mode full pipeline
in vision_pipeline.py.

Reuses the SAME underlying components as vision_pipeline.py (image_quality,
package_boundary) rather than re-implementing quality/framing logic, per
the "one shared vision core, not three independent implementations"
instruction. The difference is only in WHAT is run and WHEN:

    LIVE mode      : quality + package boundary + framing guidance.
                     No OCR by default (optional cheap sampling, see below).
                     Meant to be called frequently (e.g. once per N frames).
    CAPTURED mode  : vision_pipeline.run_vision_pipeline() - full OCR,
                     multi-engine fusion, barcode, orientation handling.
                     Meant to be called once, when the inspector taps capture.

HONEST LIMITATION: there is no real camera or mobile client in this
environment to drive this function at actual frame rate. This module is
implemented and unit-tested as a pure function of a single image; its
real-world FPS/latency on a phone camera is UNVERIFIED - there is nothing
to measure it against here. The design (cheap, OCR-optional, single-frame,
no shared mutable state) is intended to make that verification straight-
forward later, not a substitute for having done it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import numpy as np

import image_quality as image_quality_module
import package_boundary as package_boundary_module
from schema import EvidenceStatus


class LiveReadiness(str, Enum):
    NOT_READY = "NOT_READY"
    ALMOST_READY = "ALMOST_READY"
    READY = "READY"


@dataclass
class CaptureGuidance:
    state: LiveReadiness
    message: str
    target_region: Optional[str] = None
    severity: str = "medium"  # "low" | "medium" | "high"
    actions: List[str] = field(default_factory=list)


@dataclass
class DetectedRegion:
    name: str
    bbox: tuple
    confidence: float


@dataclass
class CaptureAnalysis:
    """
    The single contract a frontend/mobile client consumes for live feedback.
    Deliberately does NOT contain OCR text, extracted fields, or anything
    resembling a legal result - see safety rule "Live READY != legal
    compliance". Only readiness-relevant signals live here.
    """
    readiness: LiveReadiness
    guidance: List[CaptureGuidance]
    package_detected: bool
    package_frame_fill_ratio: Optional[float]
    global_quality_status: str
    detected_regions: List[DetectedRegion] = field(default_factory=list)
    sampled_ocr_hint: Optional[str] = None  # only set if sample_ocr=True was requested


def analyze_live_frame(img_bgr: np.ndarray, sample_ocr: bool = False) -> CaptureAnalysis:
    """
    Single-frame, OCR-free (by default) readiness analysis. Cheap enough to
    call frequently - no OCR, no barcode decode, no multi-engine fusion.

    sample_ocr=True runs ONE lightweight Tesseract pass on a downscaled copy
    purely to produce a coarse "is there readable text at all yet" hint for
    guidance copy (e.g. distinguishing "no text visible yet" from "text
    visible but blurry"). It never returns extracted fields or a legal
    signal, and is off by default because it is markedly more expensive than
    the rest of this function.
    """
    quality = image_quality_module.assess_image_quality(img_bgr)
    boundary = package_boundary_module.estimate_package_boundary(img_bgr)
    framing_msg = package_boundary_module.framing_guidance(boundary, img_bgr.shape)

    guidance: List[CaptureGuidance] = []

    if boundary is None:
        guidance.append(CaptureGuidance(
            state=LiveReadiness.NOT_READY,
            message="No package detected. Center the package and hold steady.",
            severity="high",
            actions=["center_package", "hold_steady"],
        ))
    elif framing_msg is not None:
        guidance.append(CaptureGuidance(
            state=LiveReadiness.ALMOST_READY,
            message=framing_msg,
            severity="medium",
            actions=["reframe"],
        ))

    if quality.status == EvidenceStatus.INVALID:
        guidance.append(CaptureGuidance(
            state=LiveReadiness.NOT_READY,
            message="Image quality too poor to use. " + " ".join(quality.notes),
            severity="high",
            actions=["improve_lighting", "hold_steady", "refocus"],
        ))
    elif quality.status == EvidenceStatus.LOW_QUALITY:
        for note in quality.notes:
            guidance.append(CaptureGuidance(
                state=LiveReadiness.ALMOST_READY,
                message=note,
                severity="medium",
                actions=["hold_steady", "improve_lighting", "reduce_glare"],
            ))

    sampled_hint = None
    if sample_ocr:
        try:
            import cv2
            small = cv2.resize(img_bgr, (0, 0), fx=0.5, fy=0.5)
            from PIL import Image
            from ocr_extraction import run_ocr
            pil_small = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
            lines = run_ocr(pil_small)
            sampled_hint = (
                "Readable text detected." if any(l.confidence > 0.4 for l in lines)
                else "No clearly readable text yet."
            )
        except Exception:
            sampled_hint = None

    if not guidance:
        readiness = LiveReadiness.READY
        guidance.append(CaptureGuidance(
            state=LiveReadiness.READY,
            message="Ready to capture.",
            severity="low",
            actions=["capture"],
        ))
    elif any(g.state == LiveReadiness.NOT_READY for g in guidance):
        readiness = LiveReadiness.NOT_READY
    else:
        readiness = LiveReadiness.ALMOST_READY

    # Priority order: most severe first, so a client rendering "the one
    # message to show" can just take guidance[0].
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    guidance.sort(key=lambda g: severity_rank.get(g.severity, 1))

    return CaptureAnalysis(
        readiness=readiness,
        guidance=guidance,
        package_detected=boundary is not None,
        package_frame_fill_ratio=boundary.frame_fill_ratio if boundary else None,
        global_quality_status=quality.status.value,
        detected_regions=(
            [DetectedRegion(name="package", bbox=boundary.bbox, confidence=boundary.confidence)]
            if boundary else []
        ),
        sampled_ocr_hint=sampled_hint,
    )
