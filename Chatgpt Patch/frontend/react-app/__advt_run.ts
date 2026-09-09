import { fromScanResponse } from "./src/lib/adapters";

// Payload shaped exactly like backend/schema.py CanonicalDeclaration serializes:
// declared fields only, real 8-member status enum.
const decl = (o: any) => ({ label: null, value: null, normalized_value: null, raw_text: null,
  confidence: 0.0, ocr_confidence: null, evidence: null,
  validation: { present: false, readable: null, correct_format: null, compliant: null },
  reason: "", rule_id: "LMPC-2011-R6-DECLARATIONS", rule_clause: null, ...o });

const declarations: any[] = [
  decl({ field: "manufacturer_name_address", canonical_name: "Manufacturer / Packer / Importer Name & Address",
    value: "HINDUSTAN UNILEVER LTD., HARIDWAR 249403", confidence: 0.81, status: "VERIFIED",
    rule_clause: "Rule 6(1)(a)", reason: "'Manufacturer' verified compliant.",
    evidence: { image_id: "img1", page_or_view: "back", bbox: [387, 205, 736, 348], source: "ocr" },
    validation: { present: true, readable: true, correct_format: true, compliant: true } }),
  decl({ field: "common_name", canonical_name: "Common / Generic Name of Commodity",
    value: "BODY LOTION", confidence: 0.74, status: "VERIFIED", rule_clause: "Rule 6(1)(b)",
    reason: "'Common name' verified compliant." }),
  decl({ field: "net_quantity", canonical_name: "Net Quantity", value: "200 ml",
    normalized_value: 200, confidence: 0.62, status: "REVIEW_REQUIRED", rule_clause: "Rule 6(1)(e)",
    reason: "Net quantity read from a rotated side panel; confirm against the package.",
    validation: { present: true, readable: true, correct_format: null, compliant: null } }),
  decl({ field: "mfg_date", canonical_name: "Manufacturing / Packing Date",
    label: "MFD.", confidence: 0.2, status: "PARTIALLY_DETECTED", rule_clause: "Rule 6(1)(d)",
    reason: "Declaration label detected, but value was not reliably detected." }),
  decl({ field: "best_before_use_by", canonical_name: "Best Before / Use By / Expiry Date",
    status: "NOT_APPLICABLE", confidence: 1.0,
    reason: "Declaration is outside statutory scope for this product category and origin." }),
  decl({ field: "mrp", canonical_name: "Maximum Retail Price (MRP)", status: "NOT_DETECTED_IN_PROVIDED_IMAGES",
    confidence: 0.0, rule_clause: "Rule 6(1)(da)",
    reason: "Declaration not observed in the provided view(s). Package evidence is insufficient to conclude absence." }),
  decl({ field: "consumer_care", canonical_name: "Consumer Care Details",
    value: "LEVER.CARE@UNILEVER.COM", confidence: 0.55, status: "NON_COMPLIANT",
    rule_clause: "Rule 6(1)(f)", reason: "Consumer care telephone number is absent.",
    validation: { present: true, readable: true, correct_format: false, compliant: false } }),
  decl({ field: "unit_sale_price", canonical_name: "Unit Sale Price", status: "INSUFFICIENT_EVIDENCE",
    confidence: 0.0, reason: "Coverage too thin to conclude." }),
  decl({ field: "country_of_origin", canonical_name: "Country of Origin (Imported)",
    status: "NOT_APPLICABLE", confidence: 1.0, reason: "Not an imported package." }),
];

const raw: any = {
  inspection: { inspection_id: "INS-1", product_category: "personal_care", sale_type: "retail",
    overall_status: "UNCERTAIN", disclaimer: "d", review_required: true, facts: [], declarations },
};

const insp = fromScanResponse(raw, { productId: "P1", productLabel: "Vaseline 200ml" });
console.log("headline:", `${insp.scoreBreakdown!.verifiedCount}/${insp.scoreBreakdown!.applicableCount} verified`);
console.log("breakdown:", JSON.stringify(insp.scoreBreakdown));
console.log("evidence regions:", JSON.stringify(insp.evidence));
console.log("");
for (const d of insp.declarations) {
  console.log(`${d.status.padEnd(11)} | ${String(d.confidence ?? "-").padStart(4)} | ${d.field.slice(0,42).padEnd(42)} | ${d.value.slice(0,44).padEnd(44)} | ${(d.reason||"(no reason)").slice(0,60)}`);
}
