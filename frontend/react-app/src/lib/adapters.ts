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

// backend DeclarationEvidence.bbox is a bare 4-float list. Its docstring claims
// [x1, y1, x2, y2] but its only producer (rule_engine.py, ~line 2294) writes
// [ev.bbox.x, ev.bbox.y, ev.bbox.width, ev.bbox.height]. Trust the producer,
// not the comment — reading it as a corner pair would draw every evidence box
// at the wrong size, which would be worse than drawing none.
function bboxFromEvidence(
  bbox: number[] | null | undefined,
): { x: number; y: number; width: number; height: number } | undefined {
  if (!bbox || bbox.length < 4) return undefined;
  const [x, y, width, height] = bbox;
  if (![x, y, width, height].every((n) => typeof n === "number" && Number.isFinite(n))) return undefined;
  if (width <= 0 || height <= 0) return undefined;
  return { x, y, width, height };
}

function canonicalToDeclarations(canonicals: RawCanonicalDeclaration[]): Declaration[] {
  return canonicals.map((c) => {
    // Read the DECLARED Pydantic fields. `extracted_value`, `label_present`,
    // `canonical_field`, `statutory_rule`, `rule_description` and `provenance`
    // are @property accessors on the backend model and are absent from the JSON
    // — see the note on RawCanonicalDeclaration in api-client.ts.
    const value = c.value;
    const labelPresent = Boolean(c.label);
    const uiStatus = mapCanonicalStatus(c.status);

    const isUnobserved = uiStatus === "UNOBSERVED";
    const isNonCompliant = c.status === "NON_COMPLIANT";
    const isNotApplicable = c.status === "NOT_APPLICABLE";

    let displayVal: string;
    if (value && value.trim()) {
      displayVal = value;
      const norm = c.normalized_value;
      // normalized_value is Optional[Any] on the backend — it can arrive as a
      // number or bool, not just a string, so stringify before comparing.
      if (norm !== null && norm !== undefined && norm !== "") {
        const normStr = typeof norm === "string" ? norm : String(norm);
        if (normStr !== value) displayVal += ` (${normStr})`;
      }
    } else if (labelPresent) {
      displayVal = "Label detected, value missing";
    } else if (isUnobserved) {
      displayVal = "Not captured";
    } else if (isNonCompliant) {
      displayVal = "Absent";
    } else if (isNotApplicable) {
      displayVal = "Not applicable";
    } else {
      displayVal = "Not detected";
    }

    // Never show a confidence number for a row that was never judged on
    // evidence — a percentage next to "Not captured" reads as a measurement.
    let conf: number | null = null;
    if (!isUnobserved && !isNotApplicable && c.confidence != null) {
      conf = Math.round(c.confidence * 100);
    }

    let ocrConf: number | null = null;
    if (c.ocr_confidence != null) {
      ocrConf = Math.round(c.ocr_confidence * 100);
    }

    // `reason` is the rule engine's own sentence explaining the status. It is a
    // declared field and always present; the UI was reading the non-serialized
    // `rule_description` property instead, which is why no row had an
    // explanation. Append whichever validation dimensions actually failed —
    // backend ValidationDetails is four tri-state booleans, not an issues list.
    const issues: string[] = [];
    if (c.validation) {
      if (c.validation.readable === false) issues.push("Text was detected but could not be read reliably");
      if (c.validation.correct_format === false) issues.push("Value does not match the format the rule requires");
      if (c.validation.compliant === false) issues.push("Value does not satisfy the statutory requirement");
    }
    let reasonText = [c.reason || "", ...issues].filter(Boolean).join(" • ");
    if (!reasonText) {
      if (uiStatus === "MISSING") {
        reasonText = "Mandatory declaration was not detected in the provided image panels.";
      } else if (uiStatus === "REVIEW") {
        reasonText = "Declaration requires inspector review before compliance can be established.";
      } else if (uiStatus === "UNOBSERVED") {
        reasonText = "Evidence inconclusive; capture additional surface or inspect manually.";
      }
    }

    const bboxPx = bboxFromEvidence(c.evidence?.bbox);

    return {
      field: c.canonical_name,
      value: displayVal,
      status: uiStatus,
      confidence: conf,
      ocrConfidence: ocrConf,
      // statutory_rule was a property; rule_clause is the declared field it
      // returned (falling back to rule_id).
      ruleId: c.rule_clause || c.rule_id || undefined,
      ruleVersion: "2011 (amended)",
      reason: reasonText || undefined,
      reviewRequired: uiStatus === "REVIEW",
      canonicalField: c.field,
      normalizedValue:
        c.normalized_value === null || c.normalized_value === undefined
          ? null
          : String(c.normalized_value),
      provenance: c.evidence
        ? {
            imageId: c.evidence.image_id ?? null,
            surfaceId: null,
            surfaceType: c.evidence.page_or_view ?? null,
            rawText: c.raw_text ?? null,
          }
        : null,
      validationIssues: issues.length > 0 ? issues : undefined,
      evidenceBboxPx: bboxPx,
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
      reason: f.reason || (
        f.status === "FAIL"
          ? "Statutory requirement not satisfied or declaration not detected."
          : f.review_required
          ? "Declaration requires inspector verification."
          : undefined
      ),
      reviewRequired: f.review_required,
      missingEvidence: f.missing_evidence ?? undefined,
    });
  }
  return decls;
}

function humanizeField(field: string): string {
  return field
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// A declaration is BLOCKED when the rule engine named an input it never
// received (missingEvidence) -- most commonly `calibrated_pdp_area_cm2`, which
// Rule 7(2) font-height needs to pick a threshold. A blocked check was never
// judged and is structurally incapable of passing, so counting it against the
// verified score makes a correct, cautious inspection look like a failing one.
// It is reported as its own number instead of being hidden inside "review".
export function isBlocked(d: Declaration): boolean {
  if (d.status === "VERIFIED" || d.status === "EXEMPT") return false;
  // Fact path: the rule engine named an input it never received.
  if ((d.missingEvidence?.length ?? 0) > 0) return true;
  // Canonical path: UNOBSERVED means the surface was never captured, so the
  // check was never attempted. Same category -- not judged, not failing.
  return d.status === "UNOBSERVED";
}

export function computeScores(declarations: Declaration[]): {
  verifiedScore: number;
  reviewedScore: number;
  verifiedCount: number;
  reviewCount: number;
  blockedCount: number;
  missingCount: number;
  applicableCount: number;
  judgeableCount: number;
  verifiedOfJudgeableScore: number;
} {
  const applicable = declarations.filter((d) => d.status !== "EXEMPT");
  const blocked = applicable.filter(isBlocked);
  const judgeable = applicable.filter((d) => !isBlocked(d));
  const verified = applicable.filter((d) => d.status === "VERIFIED").length;
  const reviewed = applicable.filter((d) => d.status === "VERIFIED" || d.status === "REVIEW").length;
  const missing = applicable.filter((d) => d.status === "MISSING").length;

  if (applicable.length === 0) {
    return {
      verifiedScore: 100, reviewedScore: 100, verifiedCount: 0, reviewCount: 0,
      blockedCount: 0, missingCount: 0, applicableCount: 0, judgeableCount: 0,
      verifiedOfJudgeableScore: 100,
    };
  }

  return {
    verifiedScore: Math.round((verified / applicable.length) * 100),
    reviewedScore: Math.round((reviewed / applicable.length) * 100),
    verifiedCount: verified,
    reviewCount: applicable.filter((d) => d.status === "REVIEW" && !isBlocked(d)).length,
    blockedCount: blocked.length,
    missingCount: missing,
    applicableCount: applicable.length,
    judgeableCount: judgeable.length,
    // Verified as a proportion of what could actually be judged. This is the
    // honest headline: it excludes checks that were never possible, instead of
    // silently scoring them zero.
    verifiedOfJudgeableScore: judgeable.length > 0
      ? Math.round((verified / judgeable.length) * 100)
      : 100,
  };
}

export function computeScore(declarations: Declaration[]): number {
  return computeScores(declarations).verifiedScore;
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
      // Was `d.provenance?.bbox` and `d.extracted_value` — both non-serialized
      // @property names, so this loop found nothing on any payload and the
      // evidence overlay silently fell back to the fact path every time.
      const bbox = bboxFromEvidence(d.evidence?.bbox);
      if (bbox && d.value) {
        regions.push({
          label: d.canonical_name,
          value: d.value,
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
  const { verifiedScore, reviewedScore, ...scoreCounts } = computeScores(declarations);

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
    score: verifiedScore,
    verifiedScore,
    reviewedScore,
    scoreBreakdown: scoreCounts,
    pdpAreaCm2: raw.resolved_inputs?.pdp_area_cm2 ?? undefined,
    barcodeInfo: raw.barcode_info,
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
  const { verifiedScore, reviewedScore, ...scoreCounts } = computeScores(declarations);

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
    score: verifiedScore,
    verifiedScore,
    reviewedScore,
    scoreBreakdown: scoreCounts,
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
  const { verifiedScore, reviewedScore, ...scoreCounts } = computeScores(declarations);

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
    score: verifiedScore,
    verifiedScore,
    reviewedScore,
    scoreBreakdown: scoreCounts,
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
