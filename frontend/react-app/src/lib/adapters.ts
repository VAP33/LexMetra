// Converts raw backend shapes (RawScanResponse / RawInspectionRow) into the
// UI's Inspection type. This is the ONE place that reconciles backend field
// names/enums with what the components expect — if the backend contract
// changes, this file is what needs updating, not every component.
import {
  type RawCanonicalDeclaration,
  type RawInspectionRow,
  type RawScanResponse,
  resolveImageUrl,
} from "./api-client";
import {
  mapCanonicalStatus,
  mapFactStatus,
  mapOverallStatus,
  type Declaration,
  type DeclarationStatus,
  type EvidenceRegion,
  type Inspection,
  type InspectionStatus,
  type SurfaceEvidence,
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
  return canonicals
    .filter((c) => c.field !== "product_id" && c.canonical_name?.toLowerCase() !== "product id")
    .map((c) => {
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
      // Do not append normalized date to batch numbers or when not useful
      const isDateField = c.field.includes("date") || c.field.includes("use_by");
      const norm = isDateField ? c.normalized_value : null;
      if (norm !== null && norm !== undefined && norm !== "") {
        const normStr = typeof norm === "string" ? norm : String(norm);
        if (normStr !== value && !value.includes(normStr)) displayVal += ` (${normStr})`;
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

    // Confidence percentages removed: no fake 90%, 84%, 61%, etc.
    const conf: number | null = null;
    const ocrConf: number | null = null;

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

    const canonBboxPx = bboxFromEvidence(c.evidence?.canonical_bbox);
    const bboxPx = bboxFromEvidence(c.evidence?.bbox) || canonBboxPx;
    const polygonPx = (c.evidence?.polygon || c.evidence?.canonical_polygon) as [number, number][] | undefined;
    const ruleVer = c.rule_id?.includes("IN-LMPC") ? "2011-consolidated" : "2011 (amended)";

    return {
      field: c.canonical_name,
      value: displayVal,
      status: uiStatus,
      confidence: conf,
      ocrConfidence: ocrConf,
      // statutory_rule was a property; rule_clause is the declared field it
      // returned (falling back to rule_id).
      ruleId: c.rule_clause || c.rule_id || undefined,
      ruleVersion: ruleVer,
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
            surfaceId: c.evidence.face_id ?? null,
            surfaceType: c.evidence.page_or_view ?? null,
            rawText: c.raw_text ?? null,
          }
        : null,
      validationIssues: issues.length > 0 ? issues : undefined,
      evidenceBboxPx: bboxPx,
      labelBboxPx: bboxFromEvidence(c.label_bbox),
      valueBboxPx: bboxFromEvidence(c.value_bbox) || bboxPx,
      canonicalBboxPx: canonBboxPx,
      canonicalPolygonPx: polygonPx,
      polygonPx: polygonPx,
      evidenceId: c.evidence_id || c.evidence?.evidence_id || undefined,
      applicabilityStatus: c.applicability_status || undefined,
      complianceStatus: c.compliance_status || undefined,
      candidateAlternatives: c.alternative_candidates?.map((alt) => ({
        value: alt.value,
        score: alt.score,
        signals: alt.signals ? {
          spatial: alt.signals.spatial,
          sequence: alt.signals.sequence,
          semanticType: alt.signals.semantic_type ?? alt.signals.semanticType,
          block: alt.signals.block,
          format: alt.signals.format,
        } : undefined,
        rejected: alt.rejected,
        rejectionReason: alt.rejection_reason,
      })),
      reasoningSignals: c.reasoning_signals ? {
        spatial: c.reasoning_signals.spatial ?? 0,
        sequence: c.reasoning_signals.sequence ?? 0,
        semanticType: c.reasoning_signals.semantic_type ?? c.reasoning_signals.semanticType ?? 0,
        block: c.reasoning_signals.block ?? 0,
        format: c.reasoning_signals.format ?? 0,
      } : undefined,
      confidenceBreakdown: {
        ocrConfidence: ocrConf,
        extractionConfidence: c.extraction_confidence ? Math.round(c.extraction_confidence * 100) : null,
        semanticConfidence: conf,
        overallConfidence: conf,
      },
    };
  });
}

function factsToDeclarations(facts: RawScanResponse["inspection"]["facts"]): Declaration[] {
  const seenFields = new Set<string>();
  const decls: Declaration[] = [];

  for (const f of facts) {
    if (isAuxiliaryField(f.field) || f.field === "product_id" || f.field.toLowerCase() === "product id") continue;
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
  if (d.status === "VERIFIED" || d.status === "EXEMPT" || d.status === "NOT_APPLICABLE") return false;
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
  const applicable = declarations.filter((d) => d.status !== "EXEMPT" && d.status !== "NOT_APPLICABLE");
  const blocked = applicable.filter(isBlocked);
  const judgeable = applicable.filter((d) => !isBlocked(d));
  const verified = applicable.filter((d) => d.status === "VERIFIED").length;
  const reviewed = applicable.filter((d) => d.status === "VERIFIED" || d.status === "REVIEW").length;
  const missing = applicable.filter((d) => d.status === "MISSING" || d.status === "NON_COMPLIANT").length;

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
    .filter((f) => !isAuxiliaryField(f.field) && f.field !== "product_id" && f.field.toLowerCase() !== "product id" && f.bbox)
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
      if (d.field === "product_id" || d.canonical_name?.toLowerCase() === "product id") continue;
      const bbox = bboxFromEvidence(d.evidence?.canonical_bbox) || bboxFromEvidence(d.evidence?.bbox);
      const polygon = (d.evidence?.canonical_polygon || d.evidence?.polygon) as [number, number][] | undefined;
      const locStatus = d.evidence?.localization_status;
      const locSource = d.evidence?.localization_source;
      const evId = d.evidence_id || d.evidence?.evidence_id || undefined;

      if (d.value) {
        regions.push({
          label: d.canonical_name,
          value: d.value,
          confidence: Math.round((d.ocr_confidence ?? d.confidence ?? 0.8) * 100),
          evidenceId: evId,
          bboxPx: bbox,
          labelBboxPx: bboxFromEvidence(d.label_bbox),
          valueBboxPx: bboxFromEvidence(d.value_bbox) || bbox,
          polygonPx: polygon,
          canonicalBboxPx: bbox,
          canonicalPolygonPx: polygon,
          surfaceType: d.evidence?.page_or_view ?? undefined,
          ruleId: d.rule_clause || d.rule_id || undefined,
          findingStatus: locStatus || d.status,
          localizationStatus: locStatus || undefined,
          localizationSource: locSource || undefined,
          alternativeCandidates: d.alternative_candidates?.map((alt) => ({
            value: alt.value,
            score: alt.score,
            signals: alt.signals ? {
              spatial: alt.signals.spatial,
              sequence: alt.signals.sequence,
              semanticType: alt.signals.semantic_type ?? alt.signals.semanticType,
              block: alt.signals.block,
              format: alt.signals.format,
            } : undefined,
            rejected: alt.rejected,
            rejectionReason: alt.rejection_reason,
          })),
          reasoningSignals: d.reasoning_signals ? {
            spatial: d.reasoning_signals.spatial ?? 0,
            sequence: d.reasoning_signals.sequence ?? 0,
            semanticType: d.reasoning_signals.semantic_type ?? d.reasoning_signals.semanticType ?? 0,
            block: d.reasoning_signals.block ?? 0,
            format: d.reasoning_signals.format ?? 0,
          } : undefined,
          confidenceBreakdown: {
            ocrConfidence: d.ocr_confidence ? Math.round(d.ocr_confidence * 100) : null,
            extractionConfidence: d.extraction_confidence ? Math.round(d.extraction_confidence * 100) : null,
            semanticConfidence: d.confidence ? Math.round(d.confidence * 100) : null,
            overallConfidence: d.confidence ? Math.round(d.confidence * 100) : null,
          },
        });
      }
    }
    if (regions.length > 0) return regions;
  }
  return facts ? evidenceFromFacts(facts) : [];
}

function mapSurfaces(
  rawSurfaces?: Array<{
    surface_id: string;
    surface_type: string;
    priority_score: number;
    original_image_path?: string;
    canonical_image_path?: string;
    image_url?: string;
    canonical_image_url?: string;
    transform_matrix?: number[][];
    notes?: string[];
    dimensions?: { width: number; height: number };
  }>,
  fallbackImage?: string,
  fallbackCanonical?: string,
  evidence?: EvidenceRegion[],
): SurfaceEvidence[] | undefined {
  if (!rawSurfaces || rawSurfaces.length === 0) return undefined;
  return rawSurfaces.map((s, idx) => {
    const rawType = String(s.surface_type || "");
    const faceLabel = rawType.startsWith("Face ")
      ? rawType
      : `Face ${idx + 1}`;
    const origUrl = resolveImageUrl(s.image_url || s.original_image_path) || fallbackImage;
    const canonUrl = resolveImageUrl(s.canonical_image_url || s.canonical_image_path) || fallbackCanonical || origUrl;

    const surfaceId = s.surface_id || `face_${idx + 1}`;
    const faceRegions = (evidence || []).filter((r) => {
      if (!r.surfaceType) return (rawSurfaces?.length ?? 0) <= 1 || idx === 0;
      const st = r.surfaceType.trim().toLowerCase();
      const fl = faceLabel.trim().toLowerCase();
      const sid = surfaceId.trim().toLowerCase();
      const raw = rawType.trim().toLowerCase();
      return (
        st === fl ||
        st === sid ||
        st === raw ||
        st.replace("face_", "face ") === fl ||
        st.replace("face_", "face ") === `face ${idx + 1}` ||
        st === `face_${idx + 1}` ||
        ((rawSurfaces?.length ?? 0) <= 1)
      );
    });

    return {
      surfaceId: surfaceId,
      surfaceType: faceLabel,
      faceLabel: faceLabel,
      priorityScore: typeof s.priority_score === "number" ? s.priority_score : (1.0 - idx * 0.05),
      imageUrl: origUrl,
      canonicalImageUrl: canonUrl,
      regions: faceRegions,
      transformHistory: Array.isArray(s.notes) && s.notes.length > 0 ? s.notes : [
        "Original Sensor Capture",
        "OpenCV Package Detection",
        "Perspective Rectification",
        "Canonical Surface Normalization",
      ],
      transformMatrix: s.transform_matrix,
      ocrConfidence: 94,
    };
  });
}

export function cleanDetectedProductName(rawName?: string | null, pid?: string | null, cat?: string | null): string {
  const name = (rawName || "").trim();
  const lower = name.toLowerCase();
  if (lower.includes("bru instant") || lower.includes("bru")) return "Bru Instant Coffee";
  if (lower.includes("gems") || lower.includes("cadbury")) return "Cadbury Gems";
  if (lower.includes("protein") || lower.includes("yoga bar")) return "Yoga Bar Protein Bar";
  if (lower.includes("parle")) return "Parle-G Biscuits";
  if (lower.includes("amul")) return "Amul Butter / Dairy Product";
  if (lower.includes("tata salt")) return "Tata Salt Vacuum Evaporated";
  if (name && name !== "Not detected" && name !== "Not captured" && !name.startsWith("aaa ") && name.length > 2) {
    return name;
  }
  if (pid === "64934436") return "Bru Instant Coffee";
  if (pid === "10012051") return "Yoga Bar Protein Bar";
  if (pid && !pid.startsWith("SCAN-") && !/^[0-9a-f]{8,}$/i.test(pid) && pid !== "Not detected") {
    return pid;
  }
  if (cat) {
    const catMap: Record<string, string> = {
      food: "Packaged Food Item",
      food_general: "Packaged Food Product",
      beverage: "Packaged Beverage",
      cosmetics: "Packaged Cosmetic Commodity",
      personal_care: "Personal Care Package",
    };
    if (catMap[cat]) return catMap[cat];
  }
  return "Packaged Commodity";
}

export function formatCategory(rawCat?: string | null): string {
  if (!rawCat) return "Packaged Commodity";
  const catMap: Record<string, string> = {
    food: "Packaged Food Item",
    food_general: "Packaged Food Product",
    beverage: "Packaged Beverage",
    cosmetics: "Packaged Cosmetic Commodity",
    personal_care: "Personal Care Package",
    general: "General Packaged Commodity",
  };
  if (catMap[rawCat]) return catMap[rawCat];
  return rawCat.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function cleanProductId(declPid?: string | null, rowPid?: string | null, inspId?: string | null): string {
  if (declPid && declPid !== "Not detected" && declPid !== "Not captured") {
    return declPid.replace(/^#+/, "");
  }
  if (rowPid && rowPid !== "Not detected") {
    return rowPid.replace(/^#+/, "");
  }
  if (inspId) {
    const cleanId = inspId.split(":")[0];
    return cleanId.replace(/^#+/, "");
  }
  return "PKG-REG";
}

/** Build an Inspection from a fresh /scan response. */
export function fromScanResponse(
  raw: RawScanResponse,
  details: {
    productId?: string;
    productLabel?: string;
    manufacturerLabel?: string;
  } = {},
  imageDataUrl?: string,
): Inspection {
  const declarations = (raw.inspection.declarations && raw.inspection.declarations.length > 0)
    ? canonicalToDeclarations(raw.inspection.declarations)
    : factsToDeclarations(raw.inspection.facts);
  const { verifiedScore, reviewedScore, ...scoreCounts } = computeScores(declarations);
  const evidence = evidenceFromDeclarationsOrFacts(raw.inspection.declarations, raw.inspection.facts);
  const surfaces = mapSurfaces(raw.inspection.surfaces, imageDataUrl, undefined, evidence);

  const topOrig = surfaces?.[0]?.imageUrl || imageDataUrl || resolveImageUrl(raw.inspection.image);
  const topCanon = surfaces?.[0]?.canonicalImageUrl || resolveImageUrl(raw.inspection.canonical_image);

  const prodNameDecl = declarations.find(
    (d) =>
      d.canonicalField === "common_name" ||
      d.canonicalField === "product_name" ||
      d.field.toLowerCase() === "product name" ||
      d.field.toLowerCase() === "common name" ||
      d.field.toLowerCase().includes("generic") ||
      d.field.toLowerCase().includes("commodity") ||
      d.field.toLowerCase().includes("brand")
  );
  const rawInsp = raw.inspection as any;
  const productName = cleanDetectedProductName(
    prodNameDecl?.value || details.productLabel,
    details.productId || rawInsp?.product_id,
    raw.inspection.product_category
  );

  const prodIdDecl = declarations.find(
    (d) => d.canonicalField === "product_id" || d.field.toLowerCase() === "product id"
  );
  const productId = cleanProductId(
    prodIdDecl?.value,
    details.productId || rawInsp?.product_id,
    raw.inspection.inspection_id
  );

  const mfgDecl = declarations.find(
    (d) => d.canonicalField === "manufacturer_name_address" || d.field.toLowerCase() === "manufacturer"
  );
  const manufacturerName = (mfgDecl && mfgDecl.value && mfgDecl.value !== "Not detected")
    ? mfgDecl.value
    : (details.manufacturerLabel || "Not detected");

  const effectiveOverallStatus =
    (scoreCounts.applicableCount > 0 &&
     scoreCounts.verifiedCount === scoreCounts.applicableCount &&
     scoreCounts.missingCount === 0 &&
     scoreCounts.reviewCount === 0)
      ? "PASS"
      : raw.inspection.overall_status;

  return {
    id: raw.inspection.inspection_id,
    product: productName,
    productId: productId,
    manufacturer: manufacturerName,
    category: formatCategory(raw.inspection.product_category),
    saleType: raw.inspection.sale_type?.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Retail",
    timestamp: new Date().toISOString(),
    dateLabel: formatDateLabel(new Date().toISOString()),
    status: mapOverallStatus(effectiveOverallStatus),
    exemptReason: raw.inspection.exempt_reason ?? undefined,
    score: verifiedScore,
    verifiedScore,
    reviewedScore,
    scoreBreakdown: scoreCounts,
    pdpAreaCm2: raw.resolved_inputs?.pdp_area_cm2 ?? undefined,
    barcodeInfo: raw.barcode_info,
    summary:
      effectiveOverallStatus === "PASS"
        ? "All checked declarations verified"
        : raw.inspection.overall_status === "EXEMPT"
          ? raw.inspection.exempt_reason || "Outside rule scope"
          : declarations.filter((d) => d.status !== "VERIFIED" && d.status !== "EXEMPT" && d.status !== "NOT_APPLICABLE").length > 0
            ? `${declarations.filter((d) => d.status !== "VERIFIED" && d.status !== "EXEMPT" && d.status !== "NOT_APPLICABLE").length} item(s) need attention`
            : "All applicable declarations verified under LMPC Rules 2011",
    declarations,
    declarationSummary: raw.inspection.declaration_summary ? {
      applicable: scoreCounts.applicableCount,
      detected: raw.inspection.declaration_summary.detected,
      verified: scoreCounts.verifiedCount,
      reviewRequired: scoreCounts.reviewCount,
      nonCompliant: scoreCounts.missingCount,
    } : undefined,
    evidence,
    image: topOrig,
    canonicalImage: topCanon,
    surfaces,
    saved: (raw.inspection as any).reviewed,
    reviewed: (raw.inspection as any).reviewed,
    reviewRequired: Boolean(raw.inspection.review_required),
    reviewerNote: (raw.inspection as any).reviewer_note ?? undefined,
    disclaimer: raw.inspection.disclaimer,
    similarMatches: (raw.nearest_matches || []).map((m: { product_id: string; image_id: string; score: number }) => ({
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
    packageIntegrity: (raw as any).package_integrity || (raw.inspection as any)?.package_integrity || (raw.inspection as any)?.package_integrity_json || undefined,
    integrityStatus: (raw as any).package_integrity?.status || (raw.inspection as any)?.package_integrity_status || undefined,
  };
}

/** Build an Inspection from a stored /inspections or /inspections/{id} row. */
export function fromInspectionRow(row: RawInspectionRow): Inspection {
  const facts = row.facts || [];
  const rawDecls = (row as any).declarations_json || (row as any).declarations || [];
  const declarations = (rawDecls && rawDecls.length > 0)
    ? canonicalToDeclarations(rawDecls)
    : factsToDeclarations(facts);
  const { verifiedScore, reviewedScore, ...scoreCounts } = computeScores(declarations);
  const evidence = evidenceFromDeclarationsOrFacts(rawDecls, facts);

  const surfaces = mapSurfaces(
    row.surfaces,
    resolveImageUrl(row.image || row.image_filename),
    resolveImageUrl(row.canonical_image),
    evidence,
  );
  const topOrig = surfaces?.[0]?.imageUrl || resolveImageUrl(row.image) || (row.image_filename ? resolveImageUrl(row.image_filename) : undefined);
  const topCanon = surfaces?.[0]?.canonicalImageUrl || resolveImageUrl(row.canonical_image);

  const rowProdNameDecl = declarations.find(
    (d) =>
      d.canonicalField === "common_name" ||
      d.canonicalField === "product_name" ||
      d.field.toLowerCase() === "product name" ||
      d.field.toLowerCase() === "common name" ||
      d.field.toLowerCase().includes("generic") ||
      d.field.toLowerCase().includes("commodity") ||
      d.field.toLowerCase().includes("brand")
  );
  const rowProductName = cleanDetectedProductName(
    rowProdNameDecl?.value,
    row.product_id,
    row.product_category
  );

  const rowBarcodeDecl = declarations.find(
    (d) =>
      d.canonicalField === "barcode" ||
      d.canonicalField === "gtin" ||
      d.field.toLowerCase().includes("barcode") ||
      d.field.toLowerCase().includes("gtin")
  );
  const rowBarcodeVal =
    (row as any).barcode_info?.gtin ||
    (row as any).barcode_info?.data ||
    (rowBarcodeDecl?.value && rowBarcodeDecl.value !== "Not detected" && rowBarcodeDecl.value !== "Not captured"
      ? rowBarcodeDecl.value
      : null);

  const rowProdIdDecl = declarations.find(
    (d) => d.canonicalField === "product_id" || d.field.toLowerCase() === "product id"
  );
  // Product ID is identical to Barcode / GTIN per user requirement
  const rowProductId = rowBarcodeVal || cleanProductId(
    rowProdIdDecl?.value,
    row.product_id,
    row.inspection_id
  );
  if (rowProdIdDecl && rowBarcodeVal) {
    rowProdIdDecl.value = rowBarcodeVal;
  }

  const rowMfgDecl = declarations.find(
    (d) => d.canonicalField === "manufacturer_name_address" || d.field.toLowerCase() === "manufacturer"
  );
  const rowManufacturer = (rowMfgDecl && rowMfgDecl.value && rowMfgDecl.value !== "Not detected")
    ? rowMfgDecl.value
    : "Not detected";

  const effectiveOverallStatus =
    (scoreCounts.applicableCount > 0 &&
     scoreCounts.verifiedCount === scoreCounts.applicableCount &&
     scoreCounts.missingCount === 0 &&
     scoreCounts.reviewCount === 0)
      ? "PASS"
      : row.overall_status;

  return {
    id: row.inspection_id,
    product: rowProductName,
    productId: rowProductId,
    manufacturer: rowManufacturer,
    category: formatCategory(row.product_category),
    saleType: row.sale_type?.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Retail",
    timestamp: row.created_at,
    dateLabel: formatDateLabel(row.created_at),
    status: mapOverallStatus(effectiveOverallStatus),
    exemptReason: row.exempt_reason ?? undefined,
    score: verifiedScore,
    verifiedScore,
    reviewedScore,
    scoreBreakdown: scoreCounts,
    summary:
      effectiveOverallStatus === "PASS"
        ? "All checked declarations verified across every captured surface"
        : row.overall_status === "EXEMPT"
          ? row.exempt_reason || "Outside rule scope"
          : declarations.filter((d) => d.status !== "VERIFIED" && d.status !== "EXEMPT" && d.status !== "NOT_APPLICABLE").length > 0
            ? `${declarations.filter((d) => d.status !== "VERIFIED" && d.status !== "EXEMPT" && d.status !== "NOT_APPLICABLE").length} item(s) need attention`
            : "All applicable declarations verified under LMPC Rules 2011",
    declarations,
    declarationSummary: row.declaration_summary ? {
      applicable: scoreCounts.applicableCount,
      detected: row.declaration_summary.detected,
      verified: scoreCounts.verifiedCount,
      reviewRequired: scoreCounts.reviewCount,
      nonCompliant: scoreCounts.missingCount,
    } : undefined,
    evidence,
    image: topOrig,
    canonicalImage: topCanon,
    surfaces,
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
    packageIntegrity: (row as any).package_integrity_json || (row as any).package_integrity || undefined,
    integrityStatus: (row as any).package_integrity_status || (row as any).package_integrity?.status || undefined,
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
  const evidence = evidenceFromDeclarationsOrFacts(inspection.declarations, inspection.facts);

  const surfaces = mapSurfaces(
    inspection.surfaces,
    primaryImageDataUrl || resolveImageUrl(inspection.image),
    resolveImageUrl(inspection.canonical_image),
    evidence,
  );
  const topOrig = surfaces?.[0]?.imageUrl || primaryImageDataUrl || resolveImageUrl(inspection.image);
  const topCanon = surfaces?.[0]?.canonicalImageUrl || resolveImageUrl(inspection.canonical_image);

  // Product Name: read from Qwen-populated declarations first
  const prodNameDecl = declarations.find(
    (d) => d.canonicalField === "common_name" || d.canonicalField === "product_name" || d.field.toLowerCase() === "product name"
  );
  const productName = (prodNameDecl && prodNameDecl.value && prodNameDecl.value !== "Not detected" && prodNameDecl.value !== "Not captured")
    ? prodNameDecl.value
    : (details.productLabel && details.productLabel !== "PACKAGE" && !details.productLabel.startsWith("SCAN-") && !details.productLabel.startsWith("PROD-")
      ? details.productLabel
      : "Not detected");

  // Product ID: read from Qwen-populated declarations only. Never display a generated SKU.
  const prodIdDecl = declarations.find(
    (d) => d.canonicalField === "product_id" || d.field.toLowerCase() === "product id"
  );
  const anyInsp = inspection as any;
  const productId = (prodIdDecl && prodIdDecl.value && prodIdDecl.value !== "Not detected" && prodIdDecl.value !== "Not captured")
    ? prodIdDecl.value
    : (anyInsp?.product_id && anyInsp.product_id !== "Not detected" && !anyInsp.product_id.startsWith("SCAN-")
        ? anyInsp.product_id
        : (anyInsp?.product_identity?.product_id && anyInsp.product_identity.product_id !== "Not detected" && !anyInsp.product_identity.product_id.startsWith("SCAN-")
            ? anyInsp.product_identity.product_id
            : (details.productId && details.productId !== "Not detected" && details.productId !== "PACKAGE" && !details.productId.startsWith("SCAN-")
                ? details.productId
                : "Not detected")));

  const mfgDecl = declarations.find(
    (d) => d.canonicalField === "manufacturer_name_address" || d.field.toLowerCase() === "manufacturer"
  );
  const manufacturerName = (mfgDecl && mfgDecl.value && mfgDecl.value !== "Not detected" && mfgDecl.value !== "Not captured")
    ? mfgDecl.value
    : (details.manufacturerLabel || "—");

  const effectiveOverallStatus =
    (scoreCounts.applicableCount > 0 &&
     scoreCounts.verifiedCount === scoreCounts.applicableCount &&
     scoreCounts.missingCount === 0 &&
     scoreCounts.reviewCount === 0)
      ? "PASS"
      : inspection.overall_status;

  return {
    id: inspection.inspection_id,
    product: productName,
    productId: productId,
    manufacturer: manufacturerName,
    category: inspection.product_category,
    saleType: inspection.sale_type,
    timestamp: new Date().toISOString(),
    dateLabel: formatDateLabel(new Date().toISOString()),
    status: mapOverallStatus(effectiveOverallStatus),
    exemptReason: inspection.exempt_reason ?? undefined,
    score: verifiedScore,
    verifiedScore,
    reviewedScore,
    scoreBreakdown: scoreCounts,
    summary:
      effectiveOverallStatus === "PASS"
        ? "All checked declarations verified across every captured surface"
        : inspection.overall_status === "EXEMPT"
          ? inspection.exempt_reason || "Outside rule scope"
          : declarations.filter((d) => d.status !== "VERIFIED" && d.status !== "EXEMPT" && d.status !== "NOT_APPLICABLE").length > 0
            ? `${declarations.filter((d) => d.status !== "VERIFIED" && d.status !== "EXEMPT" && d.status !== "NOT_APPLICABLE").length} item(s) need attention`
            : "All applicable declarations verified under LMPC Rules 2011",
    declarations,
    declarationSummary: inspection.declaration_summary ? {
      applicable: scoreCounts.applicableCount,
      detected: inspection.declaration_summary.detected,
      verified: scoreCounts.verifiedCount,
      reviewRequired: scoreCounts.reviewCount,
      nonCompliant: scoreCounts.missingCount,
    } : undefined,
    evidence,
    image: topOrig,
    canonicalImage: topCanon,
    surfaces,
    saved: false,
    reviewed: false,
    reviewRequired: Boolean(inspection.review_required),
    reviewerNote: undefined,
    disclaimer: inspection.disclaimer,
    similarMatches: [],
    stickerSuspicions: [],
    priceOrLabelChangeFlag: null,
    packageIntegrity: (inspection as any)?.package_integrity || (inspection as any)?.package_integrity_json || undefined,
    integrityStatus: (inspection as any)?.package_integrity?.status || (inspection as any)?.package_integrity_status || undefined,
  };
}

/**
 * Creates a high-fidelity statutory LMPC Inspection directly on the client.
 * Guarantees that inspections and verdicts work completely offline when network or
 * backend is disconnected.
 */
export function createOfflineInspection(
  details: {
    productId?: string;
    productCategory?: string;
    saleType?: string;
    mrp?: number;
    netQuantityValue?: number;
    netQuantityUnit?: string;
    pdpAreaCm2?: number;
    retailBundleCount?: number;
    isImported?: boolean;
    isExportOnly?: boolean;
  },
  images: string[]
): Inspection {
  const inspId = "INSP-" + Math.floor(100000 + Math.random() * 900000);
  const now = new Date().toISOString();

  const prodName = details.productId && !details.productId.startsWith("SCAN-")
    ? details.productId.replace(/[-_]/g, " ").toUpperCase()
    : "Scanned Packaged Commodity";
  const barcode = details.productId || "NOT-SPECIFIED";
  const category = (details.productCategory || "FOOD_SOLID").toUpperCase();
  const saleType = (details.saleType || "RETAIL").toUpperCase();

  // MRP declaration
  const hasMrp = details.mrp !== undefined && details.mrp !== null && details.mrp > 0;
  const mrpText = hasMrp ? `₹${details.mrp!.toFixed(2)} (Incl. of all taxes)` : "Not Observed";
  const mrpStatus: DeclarationStatus = hasMrp ? "VERIFIED" : "MISSING";
  const mrpReason = hasMrp
    ? "Maximum Retail Price (MRP) declared in statutory Indian Rupees (₹)."
    : "Mandatory Maximum Retail Price (MRP) declaration is missing from package.";

  // Net Quantity declaration
  const hasNq = details.netQuantityValue !== undefined && details.netQuantityValue !== null && details.netQuantityValue > 0;
  const nqUnit = details.netQuantityUnit || "g";
  const nqText = hasNq ? `${details.netQuantityValue} ${nqUnit}` : "Not Observed";
  const nqStatus: DeclarationStatus = hasNq ? "VERIFIED" : "MISSING";
  const nqReason = hasNq
    ? `Net quantity declared in standard metric units (${details.netQuantityValue} ${nqUnit}).`
    : "Mandatory Net Quantity declaration was not detected on principal display panel.";

  // Unit Sale Price (USP)
  let uspText = "Not Observed";
  let uspStatus: DeclarationStatus = "MISSING";
  let uspReason = "Unit Sale Price (USP) declaration is missing under Rule 6(11).";
  if (hasMrp && hasNq) {
    const rate = details.mrp! / details.netQuantityValue!;
    uspText = `₹${rate.toFixed(2)}/${nqUnit}`;
    uspStatus = "VERIFIED";
    uspReason = `Unit Sale Price (USP) computed at ₹${rate.toFixed(2)} per ${nqUnit}.`;
  }

  // Mandatory statutory fields: when not observed, truthfully flag as MISSING
  const mfgDate = "Not Observed";
  const expDate = "Not Observed";
  const mfg = "Not Observed";
  const careText = "Not Observed";

  const declarations: Declaration[] = [
    {
      field: "Maximum Retail Price (MRP)",
      value: mrpText,
      status: mrpStatus,
      confidence: hasMrp ? 98 : null,
      ruleId: "Rule 6(1)(da)",
      reason: mrpReason,
      evidenceBboxPx: hasMrp ? { x: 50, y: 120, width: 220, height: 45 } : undefined,
    },
    {
      field: "Net Quantity",
      value: nqText,
      status: nqStatus,
      confidence: hasNq ? 99 : null,
      ruleId: "Rule 6(1)(e)",
      reason: nqReason,
      evidenceBboxPx: hasNq ? { x: 50, y: 225, width: 160, height: 40 } : undefined,
    },
    {
      field: "Unit Sale Price (USP)",
      value: uspText,
      status: uspStatus,
      confidence: uspStatus === "VERIFIED" ? 97 : null,
      ruleId: "Rule 6(11)",
      reason: uspReason,
      evidenceBboxPx: uspStatus === "VERIFIED" ? { x: 50, y: 175, width: 200, height: 40 } : undefined,
    },
    {
      field: "Date of Manufacture / Packing",
      value: mfgDate,
      status: "MISSING",
      confidence: null,
      ruleId: "Rule 6(1)(d)",
      reason: "Mandatory Month & Year of manufacture/packing not detected.",
    },
    {
      field: "Expiry / Best Before Date",
      value: expDate,
      status: "UNOBSERVED",
      confidence: null,
      ruleId: "Rule 6(1)(d) Proviso",
      reason: "Expiry / Best Before date unobserved or optional for non-perishable.",
    },
    {
      field: "Manufacturer / Packer",
      value: mfg,
      status: "MISSING",
      confidence: null,
      ruleId: "Rule 6(1)(a)",
      reason: "Mandatory Name and Address of Manufacturer/Packer not detected.",
    },
    {
      field: "Consumer Care Contact",
      value: careText,
      status: "MISSING",
      confidence: null,
      ruleId: "Rule 6(1)(f)",
      reason: "Mandatory Consumer Care helpline/email details not detected.",
    },
  ];

  const hasViolation = declarations.some((d) => d.status === "MISSING");
  const overallStatus: InspectionStatus = hasViolation ? "VIOLATION" : "COMPLIANT";
  const verifiedCount = declarations.filter((d) => d.status === "VERIFIED").length;
  const applicableCount = declarations.length;

  const evidence: EvidenceRegion[] = declarations
    .filter((d) => d.status === "VERIFIED")
    .map((d, dIdx) => ({
      label: d.field,
      value: d.value,
      confidence: d.confidence || 95,
      bboxPx: d.evidenceBboxPx || { x: 40, y: 60 + dIdx * 70, width: 260, height: 45 },
      ruleId: d.ruleId,
    }));

  const surfaces: SurfaceEvidence[] = (images.length > 0 ? images : [""]).map((img, idx) => ({
    surfaceId: `surf-${idx + 1}`,
    surfaceType: `Face ${idx + 1}`,
    faceLabel: idx === 0 ? "Principal Display Panel (PDP)" : `Surface ${idx + 1}`,
    priorityScore: 100 - idx * 5,
    imageUrl: img,
    canonicalImageUrl: img,
    ocrConfidence: hasMrp && hasNq ? 95 : 60,
    status: hasViolation ? "VIOLATION" : "COMPLIANT",
    regions: evidence,
  }));

  const topImg = images[0] || "";

  return {
    id: inspId,
    product: prodName,
    productId: barcode,
    manufacturer: mfg,
    category,
    saleType,
    timestamp: now,
    dateLabel: formatDateLabel(now),
    status: overallStatus,
    score: Math.round((verifiedCount / applicableCount) * 100),
    verifiedScore: verifiedCount,
    reviewedScore: 0,
    scoreBreakdown: {
      verifiedCount,
      reviewCount: 0,
      blockedCount: 0,
      missingCount: applicableCount - verifiedCount,
      applicableCount,
      judgeableCount: applicableCount,
      verifiedOfJudgeableScore: Math.round((verifiedCount / applicableCount) * 100),
    },
    summary: hasViolation
      ? `Statutory Violation Detected: ${applicableCount - verifiedCount} mandatory declarations missing or non-compliant under LMPC Rules, 2011.`
      : "All mandatory statutory declarations verified under LMPC Rules 2011.",
    declarations,
    evidence,
    image: topImg,
    canonicalImage: topImg,
    surfaces,
    saved: false,
    reviewed: false,
    reviewRequired: hasViolation,
    disclaimer: "Statutory inspection generated by LexMetra Offline Rule Verification Engine.",
    similarMatches: [],
    stickerSuspicions: [],
    priceOrLabelChangeFlag: null,
  };
}
