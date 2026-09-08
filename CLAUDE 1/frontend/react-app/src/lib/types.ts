// Types for the real backend contract (see backend/schema.py, backend/main.py).
// These extend the original demo-data.ts shapes rather than replacing them —
// existing UI components keep working; new fields are additive.

// --- Backend enums, exactly as schema.py defines them ---
export type FactStatus = "PASS" | "FAIL" | "UNCERTAIN" | "EXEMPT";

// --- UI-facing enums (kept from the original app, EXEMPT added) ---
export type InspectionStatus = "COMPLIANT" | "VIOLATION" | "UNCERTAIN" | "EXEMPT";
export type DeclarationStatus = "VERIFIED" | "MISSING" | "REVIEW" | "EXEMPT";

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
  confidence: number; // 0-100, UI-scale
  ruleId?: string;
  ruleVersion?: string;
  reason?: string;
  reviewRequired?: boolean;
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
  score: number; // 0-100, computed from real facts — see adapters.ts
  summary: string;
  declarations: Declaration[];
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
