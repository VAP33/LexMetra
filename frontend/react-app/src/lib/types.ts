// Types for the real backend contract (see backend/schema.py, backend/main.py).
// These extend the original demo-data.ts shapes rather than replacing them —
// existing UI components keep working; new fields are additive.

// --- Backend enums, exactly as schema.py defines them ---
export type FactStatus = "PASS" | "FAIL" | "UNCERTAIN" | "EXEMPT";
// Re-exported from the wire types so there is exactly one definition of the
// backend's enum. The previous local union here listed five members, two of
// which ("ABSENT", "UNOBSERVED") the backend never emits.
export type { RawCanonicalStatus as CanonicalStatus } from "./api-client";
import type { RawCanonicalStatus } from "./api-client";

// --- UI-facing enums (kept from the original app, EXEMPT & UNOBSERVED added) ---
export type InspectionStatus = "COMPLIANT" | "VIOLATION" | "UNCERTAIN" | "EXEMPT";
export type DeclarationStatus = "VERIFIED" | "MISSING" | "REVIEW" | "EXEMPT" | "UNOBSERVED";

export const statusCopy: Record<InspectionStatus, { label: string; short: string }> = {
  COMPLIANT: { label: "Compliant", short: "OK" },
  VIOLATION: { label: "Violation found", short: "Issue" },
  UNCERTAIN: { label: "Needs review", short: "Review" },
  EXEMPT: { label: "Exempt from these rules", short: "Exempt" },
};

export function mapFactStatus(status: FactStatus): DeclarationStatus {
  switch (status) {
    case "PASS": return "VERIFIED";
    case "FAIL": return "MISSING";
    case "EXEMPT": return "EXEMPT";
    case "UNCERTAIN":
    default: return "REVIEW";
  }
}

// Maps all EIGHT backend CanonicalStatus members onto the five UI states.
// Every member is listed explicitly and the `default` is unreachable-by-design
// (it exists only to satisfy the compiler for malformed payloads) — that is
// deliberate: the previous version routed four distinct backend statuses into
// `default: "REVIEW"`, so a confirmed statutory violation, a label whose value
// could not be read, and a panel that was never photographed all displayed as
// the same amber "Review" row. That is what made every inspection read as
// "1 verified / 8 need review" regardless of what the OCR actually found, and
// it kept blockedCount/missingCount permanently at zero, disabling the score
// breakdown entirely.
export function mapCanonicalStatus(status: RawCanonicalStatus): DeclarationStatus {
  switch (status) {
    // The declaration was found, read, and satisfies its rule.
    case "VERIFIED": return "VERIFIED";
    // Outside statutory scope for this category/origin — not a shortcoming.
    case "NOT_APPLICABLE": return "EXEMPT";
    // A real adverse finding: the rule engine concluded non-compliance, either
    // a bad value or an absence confirmed after full package coverage. This is
    // the only status that should ever render red.
    case "NON_COMPLIANT": return "MISSING";
    // Neither of these is a finding about the PACKAGE — they are statements
    // about the EVIDENCE. The surface was not captured, or coverage was too
    // thin to conclude anything. Routing them to UNOBSERVED is what lets
    // computeScores() count them as blocked rather than as failures.
    case "NOT_DETECTED_IN_PROVIDED_IMAGES": return "UNOBSERVED";
    case "INSUFFICIENT_EVIDENCE": return "UNOBSERVED";
    // Something was read but it is not conclusive: label without a value, a
    // value without a passing check, or an explicit reviewer referral.
    case "PARTIALLY_DETECTED": return "REVIEW";
    case "DETECTED": return "REVIEW";
    case "REVIEW_REQUIRED": return "REVIEW";
    default: return "REVIEW";
  }
}

export function mapOverallStatus(status: FactStatus): InspectionStatus {
  switch (status) {
    case "PASS": return "COMPLIANT";
    case "FAIL": return "VIOLATION";
    case "EXEMPT": return "EXEMPT";
    case "UNCERTAIN":
    default: return "UNCERTAIN";
  }
}

// A declaration row shown in the "Extracted information" table. Only real
// legal fields belong here — auxiliary AI signals (sticker suspicion, etc.)
// are surfaced separately (see AiSignal below), never mixed into this list,
// so the compliance table only ever shows things a rule actually governs.
export interface Declaration {
  field: string;
  value: string;
  status: DeclarationStatus;
  confidence: number | null; // 0-100 UI-scale, null for unobserved/absent
  ocrConfidence?: number | null; // Raw OCR engine confidence (0-100)
  ruleId?: string;
  ruleVersion?: string;
  reason?: string;
  reviewRequired?: boolean;
  // Inputs the rule engine needed but never got. When non-empty, this
  // declaration was NOT judged and could never have passed -- it is blocked on
  // a missing input, not failing on the evidence. Presenting these two cases
  // identically is what made every inspection read as ~1/10.
  missingEvidence?: string[];
  canonicalField?: string;
  normalizedValue?: string | null;
  provenance?: {
    imageId?: string | null;
    surfaceId?: string | null;
    surfaceType?: string | null;
    rawText?: string | null;
  } | null;
  validationIssues?: string[];
  // Pixel bbox of the evidence for THIS declaration on the source image, in the
  // original image's coordinate space. Carried per-declaration so a row can be
  // traced back to the exact region it came from.
  evidenceBboxPx?: { x: number; y: number; width: number; height: number };
}

// One localized evidence region on the original image. bbox is kept in RAW
// PIXEL coordinates (matching backend/schema.py's BBox) — converting to a
// percentage for absolute-positioned overlays requires the image's natural
// pixel dimensions, which the UI only knows once the <img> has loaded. See
// useImageNaturalSize() in EvidenceView — never bake a percentage in here,
// it would silently be wrong for any image not exactly the size assumed.
export interface EvidenceRegion {
  label: string;
  value: string;
  confidence: number;
  bboxPx?: { x: number; y: number; width: number; height: number };
}

export interface SimilarMatch {
  productId: string;
  imageId: string;
  score: number; // 0-1
}

export interface StickerSuspicion {
  bboxPx: [number, number, number, number];
  confidence: number;
  reason: string;
}

export interface DeclarationSummary {
  applicable: number;
  detected: number;
  verified: number;
  reviewRequired: number;
  nonCompliant: number;
}

export interface Inspection {
  id: string;
  product: string;
  manufacturer: string;
  category: string;
  saleType: string;
  timestamp: string;
  dateLabel: string;
  status: InspectionStatus;
  exemptReason?: string;
  score: number; // 0-100, computed from real facts (kept as verifiedScore for compatibility)
  verifiedScore: number; // 0-100, proportion of applicable fields with VERIFIED status
  reviewedScore: number; // 0-100, proportion of applicable fields with VERIFIED or REVIEW status
  // Counts behind the percentages. Present so the UI can say "2 verified,
  // 4 need a second photo, 1 blocked on a missing input" instead of "11%",
  // which reads as a failing product when it often means an unread frame.
  scoreBreakdown?: {
    verifiedCount: number;
    reviewCount: number;
    blockedCount: number;
    missingCount: number;
    applicableCount: number;
    judgeableCount: number;
    verifiedOfJudgeableScore: number;
  };
  productIdSource?: string;
  pdpAreaCm2?: number;
  barcodeInfo?: {
    status?: string;
    symbol_count?: number;
    primary_gtin?: string | null;
    primary_symbology?: string | null;
    primary_method?: string | null;
  } | null;
  summary: string;
  declarations: Declaration[];
  declarationSummary?: DeclarationSummary;
  evidence: EvidenceRegion[];
  image?: string;
  imageNaturalWidth?: number;
  imageNaturalHeight?: number;
  saved: boolean;
  reviewed: boolean;
  reviewRequired: boolean;
  reviewerNote?: string;
  disclaimer: string;
  similarMatches: SimilarMatch[];
  stickerSuspicions: StickerSuspicion[];
  priceOrLabelChangeFlag?: string | null;
}

// What the pre-scan details sheet collects before calling /scan. These are
// required by the real backend contract (net quantity, sale type, category)
// that the original mock flow never needed to collect.
export interface ScanDetails {
  productId: string;
  saleType: "retail" | "wholesale" | "industrial" | "institutional";
  productCategory: string;
  netQuantityValue: number;
  netQuantityUnit: string;
  mrp?: number;
  pdpAreaCm2?: number;
  isExportOnly?: boolean;
  retailBundleCount?: number;
  isImported?: boolean;
}
