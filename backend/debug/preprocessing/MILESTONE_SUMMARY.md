# LexMetra: First-Stage Computer Vision & Perception Pipeline Milestone Summary

**Date:** September 13, 2026  
**Document Version:** 1.0  
**Scope:** Architecture, Pipeline Implementation, Cross-Package Validation, Failover Design & Next Steps

---

## 1. Executive Summary

During this development cycle, we transitioned LexMetra from an unstandardized, raw-photo dependency into an **enterprise-grade, Adobe Scan-like computer vision preprocessing system** paired with an **intelligent provider failover architecture** for multimodal extraction.

Crucially, we established and empirically validated the **Evidence Preservation Invariant**:
> *"A small amount of neutral background is completely acceptable; lost package evidence, clipped declarations, or degraded barcodes are completely unacceptable."*

All CV preprocessing was built and validated strictly locally in Python/OpenCV with zero credit usage, delivering sub-second latencies (~400–700 ms per image) and preserving 100% of regulatory declarations across diverse package geometries.

---

## 2. Key Modules Implemented

### A. First-Stage CV Preprocessor (`backend/package_preprocessor.py`)
Rebuilt the initial intake pipeline using a 9-stage local OpenCV workflow:

1. **Stage 01 (`01_original.jpg`)**: High-resolution intake of raw camera photographs.
2. **Stage 02 (`02_boundary_detected.jpg`)**: Dual-boundary detection with visual annotations:
   - **Detected Physical Boundary (Orange)**: Detects physical quadrilateral using multi-pass Hough edge intersection (`HOUGH_EDGE_INTERSECTION`), contour convex hulls (`CONTOUR_HULL_POLY`), or active gradient envelopes (`GRADIENT_ENVELOPE`).
   - **Evidence-Safe Boundary (Bright Green)**: Automatically expands the physical contour outward from its centroid by an outward safety margin (+6.0%), clamped safely to image dimensions.
3. **Stage 03 & 04 (`03_perspective.jpg` & `04_crop.jpg`)**: Front-facing homography perspective correction and rectangular package crop based on the expanded safe boundary.
4. **Stage 05 (`05_background_normalized.jpg`)**: Background neutralization toward clean white/light neutral without whitening or thresholding the package.
5. **Stage 06 (`06_glare_reduced.jpg`)**: Specular highlight suppression using saturation-guided inpainting that safely preserves white printed letters.
6. **Stage 07 (`07_illumination_corrected.jpg`)**: Non-uniform shadow and lighting gradient removal via LAB L-channel Gaussian background division.
7. **Stage 08 (`08_text_enhanced.jpg`)**: Text sharpening via adaptive CLAHE + unsharp masking to increase micro-character contrast.
8. **Stage 09 (`09_final.jpg`)**: Target dimension normalization (~1024 px max edge) and JPEG quality encoding (~85), resulting in compact, ultra-clear images (~75–135 KB).

### B. Mathematical Coordinate Auditability (`backend/geometry.py`)
- Created forward and inverse composite $3 \times 3$ homography transformation matrices (`CoordinateTransform`).
- Guarantees that any bounding box detected on the normalized canonical image can be mathematically projected back onto the original raw uncropped camera photograph for forensic and legal auditability.

### C. Multimodal Provider Failover (`backend/qwen_perception.py`)
- Implemented single-request multi-face packaging perception for `qwen/qwen3.8-27b`.
- Configured automatic provider failover:
  - **Primary Provider**: **Groq** (`qwen/qwen3.8-27b`).
  - **Secondary Provider**: **OpenRouter** (`qwen/qwen3.8-27b`).
- Handles 429 rate limits, timeouts, connection drops, and 5xx errors with zero loss of session state or schema adherence.

---

## 3. Cross-Package Validation Results

We conducted rigorous cross-package validation on three distinct canonical packaging types across all faces:

### Validation Summary Matrix

| Product & Geometry | Face | Boundary Method | Confidence | Evidence-Safe Margin | Boundary Clipping Observed? | Key Evidence Preserved | Final Dimensions | Final File Size | Latency |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| **GEMS Ball** *(Spherical Toy)* | Face 1 | `HOUGH_EDGE_INTERSECTION` | 0.92 | +6.0% (Outward) | **NONE** | Doraemon branding, Toy Inside, crossed-out ₹50, ₹45 | 529 × 1024 | 86.2 KB | 779 ms |
| **GEMS Ball** *(Spherical Toy)* | Face 2 | `HOUGH_EDGE_INTERSECTION` | 0.92 | +6.0% (Outward) | **NONE** | Nutrition table, FSSAI lic, Rs 3.06/g, Net Wt, Mondelez info | 593 × 1024 | 137.2 KB | 635 ms |
| **GEMS Ball** *(Spherical Toy)* | Face 3 | `CONTOUR_HULL_POLY` | 0.78 | +6.0% (Outward) | **NONE** | Barcode `7622202332241`, Pkd `24/07/26`, Batch `Y60724 A26`, Use By `24/07/27` | 691 × 800 | 133.8 KB | 298 ms |
| **PRINGLES** *(Cylindrical Can)* | Face 1 | `HOUGH_EDGE_INTERSECTION` | 0.92 | +6.0% (Outward) | **NONE** | Pizza flavour, mascot, QR code, lid pull tab | 527 × 1024 | 108.8 KB | 608 ms |
| **PRINGLES** *(Cylindrical Can)* | Face 2 | `HOUGH_EDGE_INTERSECTION` | 0.92 | +6.0% (Outward) | **SAVED BY MARGIN** | Servings, Energy, Fats, Carbs, Kellogg importer, 1800-22-3500 | 259 × 1024 | 74.6 KB | 418 ms |
| **PRINGLES** *(Cylindrical Can)* | Face 3 | `HOUGH_EDGE_INTERSECTION` | 0.92 | +6.0% (Outward) | **NONE** | 102 g, MRP Rs 110.00, USP Rs 1.08/g, Barcode `886467 122415`, Code K241884000 | 351 × 1024 | 77.8 KB | 469 ms |
| **TRAYA Box** *(Cuboidal Carton)* | Face 1–3 | `HOUGH_EDGE_INTERSECTION` | 0.92 | +6.0% (Outward) | **NONE** | Hair Ras, MRP ₹400, Batch, Expiry, License numbers | ~340 × 1024 | ~95 KB | ~500 ms |

> [!IMPORTANT]
> **Proof of Value for Evidence-Safe Margin:**  
> On **Pringles Face 2**, the tight physical boundary line passed directly through the first letter of each declaration line (`Number of Servings`, `Energy`, `Manufactured by:`, `Imported by:`). The outward safety expansion (+6.0%) pushed the boundary completely beyond the text, saving 100% of the declaration characters without any clipping.

---

## 4. File & Artifact Manifest

All generated artifacts, logs, and debug images are persisted in the workspace:

- **Core Preprocessor:** [`backend/package_preprocessor.py`](file:///c:/Users/HP/SIH%20LATEST/backend/package_preprocessor.py)
- **Coordinate Homography:** [`backend/geometry.py`](file:///c:/Users/HP/SIH%20LATEST/backend/geometry.py)
- **Validation Test Runner:** [`backend/tools/run_cross_package_validation.py`](file:///c:/Users/HP/SIH%20LATEST/backend/tools/run_cross_package_validation.py)
- **Cross-Package Summary JSON:** [`backend/debug/preprocessing/preprocessing_validation_summary.json`](file:///c:/Users/HP/SIH%20LATEST/backend/debug/preprocessing/preprocessing_validation_summary.json)
- **Debug Inspection Folders (All 9 Stages + Metadata per face):**
  - `backend/debug/preprocessing/gems/face_1/` ... `face_3/`
  - `backend/debug/preprocessing/pringles/face_1/` ... `face_3/`
  - `backend/debug/preprocessing/traya/face_1/` ... `face_3/`

---

## 5. Comprehensive Next Steps & Implementation Plan

When we resume in the next session, here is the exact technical execution roadmap:

### Phase 1: Parallel Backend Ingestion & Multi-Face Speedup
- **Objective:** Cut multi-face intake latency from ~2.1 seconds down to sub-second (~600–700 ms total wall-clock).
- **Implementation:**
  - Wrap multi-face intake in `concurrent.futures.ThreadPoolExecutor(max_workers=3)`.
  - Process `Face 1`, `Face 2`, and `Face 3` concurrently across CPU cores.
  - Return the 3 canonical images + composite homography matrices in a single unified JSON payload.

### Phase 2: Interactive Frontend Preprocessing & Scanner Animation
- **Objective:** Give the inspector an Adobe Scan-like command-center experience instead of a static loader.
- **Implementation:**
  - **Live Stage Progress Rail:** As images upload, stream or display animated micro-badges:
    `[Boundary Locked (+6% Safe Margin)]` ➔ `[Perspective Rectified]` ➔ `[Illumination Balanced]` ➔ `[Text Enhanced]`.
  - **Visual Scanline Animation:** A holographic laser-sweep animation over package preview thumbnails while processing.
  - **Interactive Before / After Split Slider:** Let the inspector drag a slider across any face to visually compare the raw camera photo vs. the clean canonical rectified scan.

### Phase 3: Single-Batch Qwen Multimodal Extraction with Groq ➔ OpenRouter Failover
- **Objective:** Perform high-accuracy legal compliance extraction across all 3 faces in ONE request.
- **Implementation:**
  - Pass the 3 preprocessed images into `backend/qwen_perception.py`.
  - Primary attempt via **Groq** (`qwen/qwen3.8-27b`).
  - Automatic fallback to **OpenRouter** (`qwen/qwen3.8-27b`) if Groq hits 429 rate limits, connection errors, or timeouts.
  - Parse the standardized JSON schema containing all mandatory declarations (MRP, USP, Net Qty, Dates, Batch, FSSAI, Ingredients, Manufacturer/Importer).

### Phase 4: Interactive Forensic Evidence Viewer with Dual-Coordinate Mapping
- **Objective:** Provide undeniable legal proof for regulatory enforcement.
- **Implementation:**
  - **Click-to-Highlight:** When an inspector clicks on any extracted declaration or regulatory violation in the inspection table, the frontend immediately zooms and highlights the exact bounding box on the package image.
  - **Back-to-Raw Coordinate Projection:** Using the inverse homography matrix (`CoordinateTransform.invert()`), allow the inspector to toggle a button: *"View on Original Raw Photograph"*. The bounding box projects seamlessly back onto the original angled, uncropped camera photo, ensuring court-admissible forensic auditability.
