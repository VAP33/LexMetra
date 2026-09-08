// Converts raw backend shapes (RawScanResponse / RawInspectionRow) into the
// UI's Inspection type. This is the ONE place that reconciles backend field
// names/enums with what the components expect — if the backend contract
// changes, this file is what needs updating, not every component.
import type { RawInspectionRow, RawScanResponse } from "./api-client";
import {
  mapFactStatus,
  mapOverallStatus,
  type Declaration,
  type EvidenceRegion,
  type Inspection,
} from "./types";

function formatDateLabel(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(
    new Date(iso),
  );
}

// Auxiliary CV/AI signal fields are prefixed with "__" by the rule engine
// (see backend/rule_engine.py) specifically so they never get mistaken for
// a real legal declaration. Filter them out of the declarations table; they
// surface instead as stickerSuspicions/similarMatches.
function isAuxiliaryField(field: string): boolean {
  return field.startsWith("__") || field === "mrp_numeral_height" || field === "declaration_placement";
}

function factsToDeclarations(facts: RawScanResponse["inspection"]["facts"]): Declaration[] {
  return facts
    .filter((f) => !isAuxiliaryField(f.field))
    .map((f) => ({
      field: humanizeField(f.field),
      value: f.extracted_value || "Not detected",
      status: mapFactStatus(f.status),
      confidence: Math.round((f.confidence ?? 0) * 100),
      ruleId: f.rule_id ?? undefined,
      ruleVersion: f.rule_version ?? undefined,
      reason: f.reason,
      reviewRequired: f.review_required,
    }));
}

function humanizeField(field: string): string {
  return field
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function computeScore(declarations: Declaration[]): number {
  if (declarations.length === 0) return 0;
  const satisfied = declarations.filter((d) => d.status === "VERIFIED" || d.status === "EXEMPT").length;
  return Math.round((satisfied / declarations.length) * 100);
}

function evidenceFromFacts(facts: RawScanResponse["inspection"]["facts"]): EvidenceRegion[] {
  return facts
    .filter((f) => !isAuxiliaryField(f.field) && f.bbox)
    .map((f) => ({
      label: humanizeField(f.field),
      value: f.extracted_value || "",
      confidence: Math.round((f.confidence ?? 0) * 100),
      bboxPx: f.bbox ?? undefined,
    }));
}

/** Build an Inspection from a fresh /scan response. imageDataUrl is the
 * locally-captured photo (kept client-side for the evidence viewer — the
 * backend stores only the filename, not the bytes, in this MVP). */
export function fromScanResponse(
  raw: RawScanResponse,
  details: { productId: string; productLabel?: string; manufacturerLabel?: string },
  imageDataUrl?: string,
): Inspection {
  const declarations = factsToDeclarations(raw.inspection.facts);
  return {
    id: raw.inspection.inspection_id,
    product: details.productLabel || details.productId,
    manufacturer: details.manufacturerLabel || "—",
    category: raw.inspection.product_category,
    saleType: raw.inspection.sale_type,
    timestamp: new Date().toISOString(),
    dateLabel: formatDateLabel(new Date().toISOString()),
    status: mapOverallStatus(raw.inspection.overall_status),
    exemptReason: raw.inspection.exempt_reason ?? undefined,
    score: computeScore(declarations),
    summary:
      raw.inspection.overall_status === "PASS"
        ? "All checked declarations verified"
        : raw.inspection.overall_status === "EXEMPT"
          ? raw.inspection.exempt_reason || "Outside rule scope"
          : `${declarations.filter((d) => d.status !== "VERIFIED").length} item(s) need attention`,
    declarations,
    evidence: evidenceFromFacts(raw.inspection.facts),
    image: imageDataUrl,
    saved: false,
    reviewed: false,
    reviewRequired: Boolean(raw.inspection.review_required),
    reviewerNote: undefined,
    disclaimer: raw.inspection.disclaimer,
    similarMatches: (raw.nearest_matches || []).map((m) => ({
      productId: m.product_id,
      imageId: m.image_id,
      score: m.score,
    })),
    stickerSuspicions: (raw.sticker_suspects || []).map((s) => ({
      bboxPx: s.bbox,
      confidence: s.confidence,
      reason: s.reason,
    })),
    priceOrLabelChangeFlag: raw.price_or_label_change_flag,
  };
}

/** Build an Inspection from a stored /inspections or /inspections/{id} row.
 * These come back without sticker/similarity signals (that data isn't
 * persisted in the MVP schema) — those arrays are empty, not fabricated. */
export function fromInspectionRow(row: RawInspectionRow): Inspection {
  const facts = row.facts || [];
  const declarations = factsToDeclarations(facts);
  return {
    id: row.inspection_id,
    product: row.product_id || row.inspection_id,
    manufacturer: "—",
    category: row.product_category,
    saleType: row.sale_type,
    timestamp: row.created_at,
    dateLabel: formatDateLabel(row.created_at),
    status: mapOverallStatus(row.overall_status),
    exemptReason: row.exempt_reason ?? undefined,
    score: computeScore(declarations),
    summary:
      row.overall_status === "PASS"
        ? "All checked declarations verified"
        : row.overall_status === "EXEMPT"
          ? row.exempt_reason || "Outside rule scope"
          : `${declarations.filter((d) => d.status !== "VERIFIED").length} item(s) need attention`,
    declarations,
    evidence: evidenceFromFacts(facts),
    image: undefined, // original bytes aren't persisted server-side in this MVP
    saved: row.reviewed,
    reviewed: row.reviewed,
    reviewRequired: Boolean(row.review_required),
    reviewerNote: row.reviewer_note ?? undefined,
    disclaimer:
      "This is an automated screening / pre-inspection aid, not a legal determination. " +
      "Findings must be reviewed by an authorized Legal Metrology officer before any action.",
    similarMatches: [],
    stickerSuspicions: [],
    priceOrLabelChangeFlag: null,
  };
}

/** Build an Inspection from POST /sessions/{id}/finalize's response — a bare
 * ProductInspection (same shape as raw.inspection from /scan, unwrapped).
 * No sticker/similarity signals at this call site in the current backend —
 * those only run inside /scan's single-image path, not session finalize —
 * so those arrays are honestly empty here, not a fetch that was skipped. */
export function fromFinalizedInspection(
  inspection: RawScanResponse["inspection"],
  details: { productId: string; productLabel?: string; manufacturerLabel?: string },
  primaryImageDataUrl?: string,
): Inspection {
  const declarations = factsToDeclarations(inspection.facts);
  return {
    id: inspection.inspection_id,
    product: details.productLabel || details.productId,
    manufacturer: details.manufacturerLabel || "—",
    category: inspection.product_category,
    saleType: inspection.sale_type,
    timestamp: new Date().toISOString(),
    dateLabel: formatDateLabel(new Date().toISOString()),
    status: mapOverallStatus(inspection.overall_status),
    exemptReason: inspection.exempt_reason ?? undefined,
    score: computeScore(declarations),
    summary:
      inspection.overall_status === "PASS"
        ? "All checked declarations verified across every captured surface"
        : inspection.overall_status === "EXEMPT"
          ? inspection.exempt_reason || "Outside rule scope"
          : `${declarations.filter((d) => d.status !== "VERIFIED").length} item(s) need attention`,
    declarations,
    evidence: evidenceFromFacts(inspection.facts),
    image: primaryImageDataUrl,
    saved: false,
    reviewed: false,
    reviewRequired: Boolean(inspection.review_required),
    reviewerNote: undefined,
    disclaimer: inspection.disclaimer,
    similarMatches: [],
    stickerSuspicions: [],
    priceOrLabelChangeFlag: null,
  };
}
