# DECISIONS — FE-01

## 2026-09-16 — D-01: Treat dashboard.html source as the parity target, not the README
- Context: FE-01 item 1 says verify dashboard features before treating the README description as a target. README claims "raw OCR text shown next to every field".
- Options considered:
  1. Implement a raw-OCR column because the README says so.
  2. Match what `dashboard.html` actually renders (`extracted_value` + reason). **(chosen, with an honesty add)**
- Decision: Parity is the three tabs and their real endpoints. Additionally show `raw_text` next to the extracted value *when the backend already sends it and it differs* — that is the README's intent using data that already exists, not a new Inspector feature.
- Why: The package itself says don't assume the README is still accurate. Building a second OCR dump the dashboard never had would be expansion, not parity.
- Reversible? Yes — hide the OCR line in `DeclarationRow` if ARCH-01 wants strict visual cloning.

## 2026-09-16 — D-02: Keep the session-based scan path (superset of POST /scan)
- Context: dashboard.html POSTs a single file to `/scan`. The React app already opened a capture session, uploaded each photo as a surface, and finalized once.
- Options considered:
  1. Rip sessions out and call `/scan` only, to clone the dashboard.
  2. Keep sessions; a single gallery photo is FRONT + finalize, which covers the dashboard's one-photo Scan. **(chosen)**
- Decision: Do not replace `api-client.ts`'s session helpers. `/scan` remains in the client for anyone who needs the richer scan envelope (`nearest_matches`, `sticker_suspects`).
- Why: Package says extend the existing integration layer, don't replace it, and don't delete working capability. A one-photo session is the dashboard Scan tab.
- Reversible? Yes — `scanPackage()` is still in `api-client.ts`.

## 2026-09-16 — D-03: `capture.html` stays separate
- Context: FE-01 CONTEXT.md says confirm with ARCH-01 whether calibrated capture folds into React. ARCH-01 D-02 froze `dashboard.html` only; it never mentioned `capture.html`.
- Options considered:
  1. Fold overlay-guide + ID-1 reference card into the React Scan view now.
  2. Leave `capture.html` as its own tool until ARCH-01 says otherwise. **(chosen)**
- Decision: Out of FE-01 scope. Different job (millimetre calibration at capture time vs. inspection review).
- Why: Package: "don't assume it's in scope without checking." Folding it in would be a new Inspector feature.
- Reversible? Yes — a later FE task can mount a CalibratedCapture view next to `ScanView`.

## 2026-09-16 — D-04: Split InspectionApp by screen, keep view-state navigation
- Context: Item 5 requires room for EVID-01 / CON-01 / FE-02, "not as a single monolithic component if avoidable." The file was 1,882 lines. No react-router in `package.json`.
- Options considered:
  1. Add react-router now.
  2. Extract screens into folders; keep the existing view-state navigator in `lib/views.ts`. **(chosen)**
- Decision: Screens are independent modules. `EvidenceView` is the EVID-01 seam. CON-01/FE-02 can wrap these views in real routes later without rewriting them.
- Why: Adding a router is a dependency the current app never had. The package forbids expansion-for-its-own-sake.
- Reversible? Yes — wrapping exported views in a router is mechanical.

## 2026-09-16 — D-05: Review queue uses the backend `needs_review=true` filter
- Context: dashboard.html calls GET `/inspections?needs_review=true`. React previously filtered the history list client-side as `reviewRequired && !reviewed`. Backend SQL includes any inspection with a fact `review_required=TRUE`, including already-reviewed rows.
- Options considered:
  1. Keep the client-side "unreviewed only" filter (arguably nicer UX).
  2. Match the dashboard/API contract. **(chosen)**
- Decision: `ReviewQueueView` is fed from `listInspections({ needsReview: true })`. Reviewed rows still appear, with a "Reviewed" marker, same as the dashboard's ✓ column.
- Why: Parity first. Changing queue semantics is a product decision, not FE-01's.
- Reversible? Yes — add `reviewed=false` client-side if ARCH-01 wants a stricter queue.
