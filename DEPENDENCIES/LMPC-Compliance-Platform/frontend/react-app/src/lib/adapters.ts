// Converts raw backend shapes (RawScanResponse / RawInspectionRow) into the
// UI's Inspection type. This is the ONE place that reconciles backend field
// names/enums with what the components expect — if the backend contract
// changes, this file is what needs updating, not every component.
import type {
  RawCanonicalDeclaration,
  RawInspectionRow,
  RawScanResponse,
} from "./api-client";
import {
  mapCanonicalStatus,
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

function canonicalToDeclarations(canonicals: RawCanonicalDeclaration[]): Declaration[] {
  return canonicals.map((c) => {
    const isUnobserved = c.status === "UNOBSERVED";
    const isAbsent = c.status === "ABSENT";
    const isNotApplicable = c.status === "NOT_APPLICABLE";

    let displayVal: string;
    if (c.extracted_value && c.extracted_value.trim()) {
      displayVal = c.extracted_value;
      if (c.normalized_value && c.normalized_value !== c.extracted_value) {
        displayVal += ` (${c.normalized_value})`;
      }
    } else if (c.label_present) {
      displayVal = "Label detected, value missing";
    } else if (isUnobserved) {
      displayVal = "Not captured";
    } else if (isAbsent) {
      displayVal = "Absent";
    } else if (isNotApplicable) {
      displayVal = "Not applicable";
    } else {
      displayVal = "Not detected";
    }

    // Never display 0% confidence for unobserved or absent declarations
    let conf: number | null = null;
    if (!isUnobserved && !isAbsent && !isNotApplicable && c.confidence != null) {
      conf = Math.round(c.confidence * 100);
    }

    let ocrConf: number | null = null;
    if (c.ocr_confidence != null) {
      ocrConf = Math.round(c.ocr_confidence * 100);
    }

    let reasonText = c.rule_description || "";
    if (c.validation?.issues && c.validation.issues.length > 0) {
      reasonText += (reasonText ? " • " : "") + c.validation.issues.join("; ");
    }

    return {
      field: c.canonical_name,
      value: displayVal,
      status: mapCanonicalStatus(c.status),
      confidence: conf,
      ocrConfidence: ocrConf,
      ruleId: c.statutory_rule || undefined,
      ruleVersion: "2011 (amended)",
      reason: reasonText || undefined,
      reviewRequired: c.validation?.requires_inspector_review || c.status === "REVIEW_REQUIRED",
      canonicalField: c.canonical_field,
      normalizedValue: c.normalized_value,
      provenance: c.provenance ? {
        imageId: c.provenance.image_id,
        surfaceId: c.provenance.surface_id,
        surfaceType: c.provenance.surface_type,
        rawText: c.provenance.raw_text,
      } : null,
      validationIssues: c.validation?.issues,
    };
  });
}

function factsToDeclarations(facts: RawScanResponse["inspection"]["facts"]): Declaration[] {
  const seenFields = new Set<string>();
  const decls: Declaration[] = [];

  for (const f of facts) {
    if (isAuxiliaryField(f.field)) continue;
    if (seenFields.has(f.field)) continue;
    seenFields.add(f.field);

    const isMissing = f.status === "FAIL";
    const conf = (isMissing || f.confidence == null) ? null : Math.round(f.confidence * 100);

    decls.push({
      field: humanizeField(f.field),
      value: f.extracted_value || "Not detected",
      status: mapFactStatus(f.status),
      confidence: conf,
      ruleId: f.rule_id ?? undefined,
      ruleVersion: f.rule_version ?? undefined,
      reason: f.reason,
      reviewRequired: f.review_required,
    });
  }
  return decls;
}

function humanizeField(field: string): string {
  return field
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function computeScore(declarations: Declaration[]): number {
  const applicable = declarations.filter((d) => d.status !== "EXEMPT");
  if (applicable.length === 0) return 100;
  const satisfied = applicable.filter((d) => d.status === "VERIFIED").length;
  return Math.round((satisfied / applicable.length) * 100);
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

function evidenceFromDeclarationsOrFacts(
  declarations?: RawCanonicalDeclaration[],
  facts?: RawScanResponse["inspection"]["facts"],
): EvidenceRegion[] {
  if (declarations && declarations.length > 0) {
    const regions: EvidenceRegion[] = [];
    for (const d of declarations) {
      const bbox = d.provenance?.bbox;
      if (bbox && d.extracted_value) {
        regions.push({
          label: d.canonical_name,
          value: d.extracted_value,
          confidence: Math.round((d.ocr_confidence ?? d.confidence ?? 0.8) * 100),
          bboxPx: bbox,
        });
      }
    }
    if (regions.length > 0) return regions;
  }
  return facts ? evidenceFromFacts(facts) : [];
}

/** Build an Inspection from a fresh /scan response. */
export function fromScanResponse(
  raw: RawScanResponse,
  details: { productId: string; productLabel?: string; manufacturerLabel?: string },
  imageDataUrl?: string,
): Inspection {
  const declarations = (raw.inspection.declarations && raw.inspection.declarations.length > 0)
    ? canonicalToDeclarations(raw.inspection.declarations)
    : factsToDeclarations(raw.inspection.facts);

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
    declarationSummary: raw.inspection.declaration_summary ? {
      applicable: raw.inspection.declaration_summary.applicable,
      detected: raw.inspection.declaration_summary.detected,
      verified: raw.inspection.declaration_summary.verified,
      reviewRequired: raw.inspection.declaration_summary.review_required,
      nonCompliant: raw.inspection.declaration_summary.non_compliant,
    } : undefined,
    evidence: evidenceFromDeclarationsOrFacts(raw.inspection.declarations, raw.inspection.facts),
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

/** Build an Inspection from a stored /inspections or /inspections/{id} row. */
export function fromInspectionRow(row: RawInspectionRow): Inspection {
  const facts = row.facts || [];
  const declarations = (row.declarations && row.declarations.length > 0)
    ? canonicalToDeclarations(row.declarations)
    : factsToDeclarations(facts);

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
    declarationSummary: row.declaration_summary ? {
      applicable: row.declaration_summary.applicable,
      detected: row.declaration_summary.detected,
      verified: row.declaration_summary.verified,
      reviewRequired: row.declaration_summary.review_required,
      nonCompliant: row.declaration_summary.non_compliant,
    } : undefined,
    evidence: evidenceFromDeclarationsOrFacts(row.declarations, facts),
    image: undefined,
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

/** Build an Inspection from POST /sessions/{id}/finalize's response. */
export function fromFinalizedInspection(
  inspection: RawScanResponse["inspection"],
  details: { productId: string; productLabel?: string; manufacturerLabel?: string },
  primaryImageDataUrl?: string,
): Inspection {
  const declarations = (inspection.declarations && inspection.declarations.length > 0)
    ? canonicalToDeclarations(inspection.declarations)
    : factsToDeclarations(inspection.facts);

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
    declarationSummary: inspection.declaration_summary ? {
      applicable: inspection.declaration_summary.applicable,
      detected: inspection.declaration_summary.detected,
      verified: inspection.declaration_summary.verified,
      reviewRequired: inspection.declaration_summary.review_required,
      nonCompliant: inspection.declaration_summary.non_compliant,
    } : undefined,
    evidence: evidenceFromDeclarationsOrFacts(inspection.declarations, inspection.facts),
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
