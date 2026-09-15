# CDD Package — EVID-01 (Evidence System / Viewer)

(Verbatim from `CDD/Wave 1/3 EVID-01.md`, copied here for persistent context.)

**Agent ID:** EVID-01
**Role:** Make the evidence chain (image → bbox → OCR → confidence → rule → decision) that the vision's USP1 describes actually visible to a human, not just present in backend data structures.

**Purpose:** Build the Evidence Viewer as a new backend endpoint + React component, surfacing data that mostly already exists but currently isn't exposed anywhere.

**You must:**
1. Audit what evidence data is already captured but not surfaced: `region_detection.py` produces bboxes with confidence and signal provenance; `ocr_extraction.py` attaches raw OCR text next to extracted fields (the README says the dashboard already does this — verify it, don't assume); `rule_engine.py` produces per-rule findings with reasons. Map exactly which pieces exist vs. which need new plumbing before building UI for data that isn't there yet.
2. Add a new backend endpoint, e.g. `GET /inspections/{id}/evidence`, that returns the full chain for one inspection: original image reference, detected regions with bboxes, OCR text per region with confidence and source engine, the rule/finding each field fed into, and the final verdict — one response, not scattered across today's separate endpoints.
3. Build the corresponding React component in `frontend/react-app/src/components/` (following the FE-01 decision to standardize on React) — image with overlaid bounding boxes, click-to-inspect per region, confidence shown honestly (not hidden when low).
4. Respect the vision's core invariants explicitly in the UI, not just the backend: "NOT_OBSERVED != MISSING", "LOW OCR CONFIDENCE != NON-COMPLIANCE" — the viewer must not visually imply certainty the data doesn't have. If a rule's `verification_status` is `needs_official_verification` (true for every current rule per the README), surface that too, don't silently drop it.
5. Coordinate directly with OCR-01 on the exact confidence/provenance JSON shape — you're both Wave 1, run in parallel, but your endpoint's contract depends on their output format.

**You must NOT:**
- Change what data OCR/CV/rule engine produce — you're a consumer/aggregator, not a producer, of evidence data. If something's missing, request it from the owning agent (OCR-01, CV-01, RULE-01) rather than reaching into their modules yourself.
- Build this as a fork of the existing `dashboard.html` — build it in the React app per the FE-01 decision.

## CONTEXT.md

- No dedicated evidence-viewer endpoint exists today — this is genuinely new. The raw ingredients exist scattered across `region_detection.py`, `ocr_extraction.py`, and `rule_engine.py`.
- `region_detection.py`'s module docstring is unusually explicit about what its outputs do and don't mean (worth reading in full — it's essentially a spec for the honesty this viewer needs to preserve): text-detected regions aren't mandatory-declaration regions, sticker-detected regions aren't violations, package boundaries aren't the legally-defined Principal Display Panel, and an empty detection result is evidence about the detector, not the package.
- React app currently has 2 component files (`InspectionApp.tsx` plus a `lib/` with `api-client.ts`, `adapters.ts`, `types.ts`) — small enough that adding a new evidence view is a real addition, not a refactor.

## CONTRACTS.md

**Contract you consume:** OCR-01's confidence/provenance output; CV-01's region/bbox output (when it lands — until then, use `region_detection.py`'s current classical-CV output, it already has the right shape even if the detector itself is a later CV-01 upgrade target).
**Contract you produce:** `GET /inspections/{id}/evidence` response schema — document it clearly, since FE-02 (Consumer frontend, later) may eventually want a simplified version of the same data.
