import { Header as AppHeader } from "./app-header";
import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  Building2,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  Mail,
  Phone,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { type Inspection } from "@/lib/types";
import {
  getPackageIntegrity,
  getDepartmentalCrossVerification,
  downloadOrOpenInspectionReportPdf,
  getMasterRules,
  type IntegrityReportData,
  type DepartmentalRegulatoryDossierData,
  type MasterRuleItem,
} from "@/lib/api-client";
import { Button, formatDate } from "./ui-primitives";
import { exportElementAsPdf } from "@/lib/pdf-generator";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function fieldLabel(field: string): string {
  return field
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusColor(status: string): string {
  const s = (status || "").toUpperCase();
  if (s === "VERIFIED" || s === "PASS") return "text-emerald-700 font-bold";
  if (s === "NON_COMPLIANT" || s === "FAIL" || s === "MISSING") return "text-rose-700 font-bold";
  if (s === "REVIEW" || s === "REVIEW_REQUIRED" || s === "UNCERTAIN") return "text-amber-600 font-bold";
  if (s === "NOT_APPLICABLE" || s === "EXEMPT") return "text-slate-400 font-semibold";
  return "text-slate-600";
}

function statusLabel(status: string): string {
  const s = (status || "").toUpperCase();
  if (s === "VERIFIED") return "PASS ✓";
  if (s === "NON_COMPLIANT" || s === "MISSING") return "FAIL ✗";
  if (s === "REVIEW" || s === "REVIEW_REQUIRED") return "REVIEW ⚠";
  if (s === "NOT_APPLICABLE") return "N/A";
  if (s === "EXEMPT") return "EXEMPT";
  return status;
}

function integrityStatusLabel(status: string): string {
  const s = (status || "").toUpperCase();
  if (s.includes("NO_SIGNIFICANT") || s.includes("NO SIGNIFICANT")) return "NO SIGNIFICANT DIFFERENCE";
  if (s.includes("POTENTIAL")) return "POTENTIAL ALTERATION DETECTED";
  return "UNABLE TO VERIFY";
}

function deptStatusColor(status: string): string {
  const s = (status || "").toUpperCase();
  if (s === "LIVE" || s === "DEMO") return "text-emerald-700 font-bold";
  if (s === "UNAVAILABLE") return "text-rose-700 font-bold";
  if (s === "MANUAL") return "text-amber-600 font-bold";
  return "text-slate-400";
}

function deptStatusLabel(status: string): string {
  const s = (status || "").toUpperCase();
  if (s === "LIVE") return "VERIFIED (Live Portal)";
  if (s === "DEMO") return "VERIFIED (Demo/Registry)";
  if (s === "NOT_APPLICABLE") return "Not Applicable";
  if (s === "MANUAL") return "Manual Review Required";
  if (s === "UNAVAILABLE") return "Portal Unavailable";
  return status;
}

function fieldCompStatusColor(status: string): string {
  const s = (status || "").toUpperCase();
  if (s.includes("MATCH") || s.includes("EXPECTED")) return "text-emerald-700 font-bold";
  if (s.includes("DISCREPANCY")) return "text-rose-700 font-bold";
  if (s.includes("REVIEW")) return "text-amber-600 font-bold";
  return "text-slate-500";
}

function fieldCompStatusLabel(status: string): string {
  const s = (status || "").toUpperCase();
  if (s === "MATCH") return "MATCH ✓";
  if (s.includes("EXPECTED TO VARY")) return "OK (Variable)";
  if (s.includes("POTENTIAL DISCREPANCY") || s.includes("POTENTIAL_DISCREPANCY")) return "DISCREPANCY ✗";
  if (s.includes("REVIEW")) return "REVIEW ⚠";
  if (s.includes("NOT_OBSERVED")) return "Not Observed";
  return status;
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function SectionTitle({ n, title }: { n: number; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-3 mt-6 first:mt-0">
      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-900 text-white text-xs font-bold flex items-center justify-center">
        {n}
      </span>
      <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">{title}</h2>
    </div>
  );
}

function TableHeader({ cols }: { cols: string[] }) {
  return (
    <thead>
      <tr className="bg-slate-800 text-white text-left">
        {cols.map((c) => (
          <th key={c} className="px-3 py-2 text-xs font-bold whitespace-nowrap">
            {c}
          </th>
        ))}
      </tr>
    </thead>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export function ReportView({ inspection, onBack }: { inspection: Inspection; onBack: () => void }) {
  const [pdfState, setPdfState] = useState<"idle" | "generating" | "done">("idle");
  const [pdfProgress, setPdfProgress] = useState<{ stage: string; pct: number } | null>(null);
  const [integrityData, setIntegrityData] = useState<IntegrityReportData | null>(inspection.packageIntegrity || null);
  const [dossier, setDossier] = useState<DepartmentalRegulatoryDossierData | null>(null);
  const [masterRules, setMasterRules] = useState<MasterRuleItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function loadData() {
      setLoading(true);
      try {
        const [integrity, dept, rules] = await Promise.allSettled([
          getPackageIntegrity(inspection.id),
          getDepartmentalCrossVerification(inspection.id),
          getMasterRules({ category: inspection.category, saleType: inspection.saleType }),
        ]);
        if (cancelled) return;
        if (integrity.status === "fulfilled") setIntegrityData(integrity.value);
        if (dept.status === "fulfilled") setDossier(dept.value);
        if (rules.status === "fulfilled") setMasterRules(rules.value);
      } catch {
        // tolerates partial failures silently
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadData();
    return () => { cancelled = true; };
  }, [inspection.id, inspection.category, inspection.saleType]);

  async function handleExportPdf() {
    if (pdfState === "generating") return;
    setPdfState("generating");
    setPdfProgress({ stage: "Generating official statutory dossier…", pct: 30 });
    try {
      setPdfProgress({ stage: "Opening certified 3-page PDF dossier…", pct: 75 });
      await downloadOrOpenInspectionReportPdf(inspection.id);
      setPdfProgress({ stage: "Ready!", pct: 100 });
    } catch (err) {
      console.warn("Direct PDF retrieval failed, falling back to document export:", err);
      try {
        await exportElementAsPdf(
          "lexmetra-report-shell",
          `LexMetra_Report_${inspection.id.slice(0, 8)}.pdf`,
          (p) => setPdfProgress(p)
        );
      } catch (fallbackErr) {
        window.print();
      }
    } finally {
      setPdfState("done");
      setTimeout(() => setPdfProgress(null), 1200);
    }
  }

  const isCompliant = inspection.status === "COMPLIANT" || inspection.status === "EXEMPT";
  const isViolation = inspection.status === "VIOLATION";

  const allDecls = inspection.declarations || [];
  const verifiedCount = allDecls.filter((d) => d.status === "VERIFIED").length;
  const failCount = allDecls.filter((d) => d.status === "NON_COMPLIANT" || d.status === "MISSING").length;
  const reviewCount = allDecls.filter((d) => d.status === "REVIEW" || (d.status as string) === "REVIEW_REQUIRED").length;

  const mfgDecl = allDecls.find((d) => d.field.toLowerCase().includes("manufacturer") || d.field.toLowerCase().includes("packer"));
  const careDecl = allDecls.find((d) => d.field.toLowerCase().includes("consumer_care") || d.field.toLowerCase().includes("consumer care"));
  const fssaiDecl = allDecls.find((d) => d.field.toLowerCase().includes("fssai") || d.field.toLowerCase().includes("license"));
  const barcodeDecl = allDecls.find((d) => d.field.toLowerCase().includes("barcode") || d.field.toLowerCase().includes("gtin"));
  const addrDecl = allDecls.find((d) => d.field.toLowerCase().includes("address"));

  const consumerCareText = careDecl?.value || "";
  const emailMatch = consumerCareText.match(/[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}/g);
  const phoneMatch = consumerCareText.match(/(\+?[\d][\d\s\-()]{6,})/g);

  const surfaces = (inspection.surfaces && inspection.surfaces.length > 0)
    ? inspection.surfaces.slice(0, 4)
    : inspection.image
      ? [{ surfaceId: "s1", imageUrl: inspection.image, faceLabel: "Surface 1", priorityScore: 100, regions: [] as any[], surfaceType: "Front" }]
      : [];

  const intFields = integrityData?.field_comparisons || [];
  const deptDepts = dossier?.departments || [];

  return (
    <>
      {/* ── Print CSS injected inline ── */}
      <style>{`
        @media print {
          body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
          .print-hidden { display: none !important; }
          .print-page-break { page-break-before: always; break-before: page; }
          .print-avoid-break { page-break-inside: avoid; break-inside: avoid; }
          @page { margin: 14mm 11mm; size: A4; }
          .report-shell { box-shadow: none !important; border: none !important; border-radius: 0 !important; }
        }
        @media screen {
          .print-page-break { border-top: 2px dashed #cbd5e1; padding-top: 2rem; margin-top: 2rem; }
        }
      `}</style>

      <AppHeader title="Official Statutory Inspection Report" />
      <main className="mx-auto max-w-5xl px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8">

        {/* Action bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6 print-hidden">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-2 text-sm font-semibold text-slate-700 hover:text-slate-900 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" /> Back to result
          </button>
          <div className="flex items-center gap-2">
            {loading && (
              <span className="flex items-center gap-1 text-xs text-slate-500">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading report data…
              </span>
            )}
            <Button variant="secondary" onClick={() => window.print()} className="border-border/70 text-slate-800">
              <FileText className="h-4 w-4" /> Print
            </Button>
            <Button
              onClick={handleExportPdf}
              disabled={pdfState === "generating" || loading}
              className="bg-brand hover:bg-brand/90 text-white shadow-md min-w-[180px] justify-center"
            >
              {pdfState === "generating" ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> {pdfProgress?.stage || "Generating…"}</>
              ) : (
                <><Download className="h-4 w-4" /> Export Official PDF</>
              )}
            </Button>
          </div>
        </div>

        {/* PDF progress overlay */}
        {pdfState === "generating" && pdfProgress && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 print-hidden">
            <div className="bg-white rounded-2xl shadow-2xl p-8 flex flex-col items-center gap-4 w-80">
              <Loader2 className="h-10 w-10 animate-spin text-brand" />
              <div className="text-center">
                <div className="font-bold text-slate-900 mb-1">Generating Official PDF</div>
                <div className="text-sm text-slate-500">{pdfProgress.stage}</div>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2">
                <div
                  className="bg-brand h-2 rounded-full transition-all duration-300"
                  style={{ width: `${pdfProgress.pct}%` }}
                />
              </div>
              <div className="text-xs text-slate-400">{pdfProgress.pct}% complete</div>
            </div>
          </div>
        )}

        {/* ══ Report document shell ══ */}
        <div id="lexmetra-report-shell" className="report-shell bg-white rounded-2xl border border-slate-200 shadow-xl overflow-hidden font-sans">

          {/* ═══════════════════════════════════════════════════════════════ */}
          {/* PAGE 1 — Header · Verdict · Metadata · All Declarations        */}
          {/* ═══════════════════════════════════════════════════════════════ */}
          <div className="p-6 sm:p-10 space-y-5">

            {/* Document header */}
            <div className="text-center border-b-2 border-slate-900 pb-4 space-y-1">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest">
                Government of India &bull; Ministry of Consumer Affairs, Food &amp; Public Distribution
              </p>
              <h1 className="text-xl sm:text-2xl font-black tracking-tight text-slate-900 uppercase leading-tight">
                Legal Metrology Compliance Inspection Report
              </h1>
              <p className="text-xs text-slate-600 font-medium">
                Legal Metrology (Packaged Commodities) Rules, 2011 &bull; LexMetra AI Vision Platform v2.4
              </p>
            </div>

            {/* Verdict banner */}
            <div className={`print-avoid-break rounded-xl p-4 text-center border-2 font-black text-sm tracking-widest ${
              isCompliant ? "bg-emerald-50 text-emerald-800 border-emerald-600"
              : isViolation ? "bg-rose-50 text-rose-800 border-rose-600"
              : "bg-amber-50 text-amber-800 border-amber-600"
            }`}>
              {isCompliant
                ? "✓  FINAL VERDICT: COMPLIANT — ALL MANDATORY DECLARATIONS VERIFIED"
                : isViolation
                  ? "✗  FINAL VERDICT: STATUTORY VIOLATION — NON-COMPLIANCE DETECTED"
                  : "⚠  FINAL VERDICT: REVIEW REQUIRED — MANUAL INSPECTION RECOMMENDED"}
            </div>

            {/* Metadata grid */}
            <div className="print-avoid-break grid grid-cols-2 sm:grid-cols-4 gap-px bg-slate-200 rounded-xl overflow-hidden border border-slate-200 text-xs">
              {[
                ["Product / Commodity Name", inspection.product],
                ["Inspection ID", inspection.id],
                ["Category", inspection.category || "Packaged Commodity"],
                ["Sale Type", inspection.saleType || "Retail"],
                ["Inspection Date / Time", formatDate(inspection.timestamp)],
                ["Evidence Coverage", `${inspection.verifiedScore ?? Math.round((verifiedCount / Math.max(allDecls.length, 1)) * 100)}%`],
                ["Barcode / GTIN", barcodeDecl?.value || inspection.productId || "Not Detected"],
                ["FSSAI License No.", fssaiDecl?.value || "Not Detected"],
              ].map(([label, value]) => (
                <React.Fragment key={label as string}>
                  <div className="bg-slate-50 p-2.5 font-bold text-slate-800">{label}</div>
                  <div className="bg-white p-2.5 text-slate-700 break-all">{value}</div>
                </React.Fragment>
              ))}
            </div>

            {/* Score summary */}
            <div className="print-avoid-break grid grid-cols-3 gap-3 text-center">
              {[
                { Icon: CheckCircle2, count: verifiedCount, label: "Verified", bg: "bg-emerald-50 border-emerald-200", fg: "text-emerald-700" },
                { Icon: XCircle, count: failCount, label: "Non-Compliant", bg: "bg-rose-50 border-rose-200", fg: "text-rose-700" },
                { Icon: AlertTriangle, count: reviewCount, label: "Review Required", bg: "bg-amber-50 border-amber-200", fg: "text-amber-600" },
              ].map(({ Icon, count, label, bg, fg }) => (
                <div key={label} className={`rounded-xl border p-3 ${bg}`}>
                  <Icon className={`h-5 w-5 mx-auto mb-1 ${fg}`} />
                  <div className={`text-2xl font-black ${fg}`}>{count}</div>
                  <div className="text-xs font-semibold text-slate-600">{label}</div>
                </div>
              ))}
            </div>

            {/* Section 1: All Declarations */}
            <div className="print-avoid-break">
              <SectionTitle n={1} title="Extracted Legal Metrology Declarations (Fused Across All Package Surfaces)" />
              <div className="rounded-xl border border-slate-200 overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <TableHeader cols={["Statutory Field", "Extracted Value", "Conf.", "Rule Ref.", "Status", "Notes / Reason"]} />
                  <tbody className="divide-y divide-slate-100">
                    {allDecls.length > 0 ? allDecls.map((d, i) => (
                      <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                        <td className="px-3 py-2 font-semibold text-slate-800 whitespace-nowrap">{fieldLabel(d.field)}</td>
                        <td className="px-3 py-2 text-slate-700 max-w-[200px] break-words">{d.value || <span className="text-slate-400 italic">Not observed</span>}</td>
                        <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{d.confidence != null ? `${d.confidence}%` : "—"}</td>
                        <td className="px-3 py-2 text-slate-500 whitespace-nowrap font-mono">{d.ruleId || "—"}</td>
                        <td className={`px-3 py-2 whitespace-nowrap ${statusColor(d.status)}`}>{statusLabel(d.status)}</td>
                        <td className="px-3 py-2 text-slate-500 text-[10px] max-w-[160px] break-words">
                          {d.reason || (d.missingEvidence?.length ? `Blocked on: ${d.missingEvidence.join(", ")}` : "")}
                        </td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan={6} className="px-3 py-4 text-center text-slate-400 italic text-xs">No declarations extracted</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Section 1B: LMPC Master Statutory Rule & Exemption Register */}
            <div className="print-avoid-break">
              <SectionTitle n="1B" title="LMPC-2011 Master Statutory Rule & Exemption Register (G.S.R. 202(E))" />
              <p className="text-xs text-slate-500 mb-2">
                Statutory codification under the Legal Metrology (Packaged Commodities) Rules, 2011 and Legal Metrology Act, 2009.
                Contextual exemptions evaluated dynamically for this package category, sale type, and container specification.
              </p>
              <div className="rounded-xl border border-slate-200 overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <TableHeader cols={["Statutory Citation", "Chapter / Rule Title", "Category Scope", "Applicability / Exemption", "Contextual Analysis & Conditions", "Penal Section"]} />
                  <tbody className="divide-y divide-slate-100">
                    {masterRules.length > 0 ? masterRules.map((r, i) => (
                      <tr key={r.id || i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                        <td className="px-3 py-2 font-mono font-bold text-slate-800 whitespace-nowrap">{r.citation}</td>
                        <td className="px-3 py-2 text-slate-800 font-semibold max-w-[170px] break-words">
                          <div>{r.title}</div>
                          <div className="text-[10px] text-slate-500 font-normal">{r.chapter}</div>
                        </td>
                        <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{r.category_scope}</td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            r.evaluation_status === "APPLICABLE"
                              ? "bg-blue-100 text-blue-800"
                              : r.evaluation_status === "EXEMPT" || r.evaluation_status === "ACTIVE_EXEMPTION"
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-slate-100 text-slate-600"
                          }`}>
                            {r.evaluation_status || (r.is_mandatory ? "MANDATORY" : "CONDITIONAL")}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-slate-600 text-[10px] max-w-[240px] break-words">
                          <div className="font-medium text-slate-700">{r.context_note || r.summary}</div>
                          {r.exemptions?.length > 0 && (
                            <div className="text-slate-500 mt-0.5 italic">
                              Exemptions: {r.exemptions.join("; ")}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 font-mono text-[10px] text-rose-700 whitespace-nowrap">
                          <div>{r.penal_section}</div>
                          <div className="text-[9px] text-slate-500 font-sans max-w-[130px] break-words">{r.penalty_description}</div>
                        </td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan={6} className="px-3 py-4 text-center text-slate-400 italic text-xs">Loading statutory master rules…</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Section 2: Rule-by-rule compliance */}
            <div className="print-avoid-break">
              <SectionTitle n={2} title="Statutory Rule-by-Rule Compliance Findings (LMPC Rules, 2011)" />
              <div className="rounded-xl border border-slate-200 overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <TableHeader cols={["Rule Clause", "Requirement", "Observed Value", "Status", "Statutory Requirement"]} />
                  <tbody className="divide-y divide-slate-100">
                    {[
                      { rule: "Rule 6(1)(a)", req: "Manufacturer / Packer Name & Address", decl: mfgDecl, req_text: "Full name and complete address of manufacturer/packer/importer." },
                      { rule: "Rule 6(1)(b)", req: "Common / Generic Name of Commodity", decl: allDecls.find(d => d.field.toLowerCase().includes("product") || d.field.toLowerCase().includes("name")), req_text: "Common or generic name of commodity must be declared." },
                      { rule: "Rule 6(1)(c)", req: "Net Quantity (weight/volume/number)", decl: allDecls.find(d => d.field.toLowerCase().includes("net") || d.field.toLowerCase().includes("quantity")), req_text: "Net quantity in standard metric units." },
                      { rule: "Rule 6(1)(d)", req: "Month and Year of Manufacture / Packing", decl: allDecls.find(d => d.field.toLowerCase().includes("mfg") || d.field.toLowerCase().includes("manufacture")), req_text: "MM/YYYY or Month-Year format." },
                      { rule: "Rule 6(1)(e)", req: "Maximum Retail Price (MRP) incl. all taxes", decl: allDecls.find(d => d.field.toLowerCase().includes("mrp") || d.field.toLowerCase().includes("price")), req_text: "MRP as 'M.R.P. ₹ XX.XX (Inclusive of all taxes)'." },
                      { rule: "Rule 6(1)(da)", req: "Unit Sale Price (USP)", decl: allDecls.find(d => d.field.toLowerCase().includes("usp") || d.field.toLowerCase().includes("unit_sale")), req_text: "Price per standard unit (per gram, per ml, etc.)." },
                      { rule: "Rule 6(1)(f)", req: "Consumer Care Contact", decl: careDecl, req_text: "Telephone number or email of consumer care." },
                      { rule: "Rule 6(1)(g)", req: "Country of Origin (Imported Goods)", decl: allDecls.find(d => d.field.toLowerCase().includes("country") || d.field.toLowerCase().includes("origin")), req_text: "Country of origin required for imported goods." },
                    ].map(({ rule, req, decl, req_text }, i) => (
                      <tr key={rule} className={i % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                        <td className="px-3 py-2 font-mono text-slate-700 whitespace-nowrap">{rule}</td>
                        <td className="px-3 py-2 font-semibold text-slate-800">{req}</td>
                        <td className="px-3 py-2 text-slate-700 max-w-[150px] break-words">{decl?.value || <span className="italic text-slate-400">Not Observed</span>}</td>
                        <td className={`px-3 py-2 whitespace-nowrap ${statusColor(decl?.status || "MISSING")}`}>
                          {decl ? statusLabel(decl.status) : "NOT OBSERVED ✗"}
                        </td>
                        <td className="px-3 py-2 text-slate-500 text-[10px] max-w-[160px] break-words">{req_text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* ═══════════════════════════════════════════════════════════════ */}
          {/* PAGE 2 — Package Integrity · Cross-Departmental Verification   */}
          {/* ═══════════════════════════════════════════════════════════════ */}
          <div className="print-page-break p-6 sm:p-10 space-y-5">

            {/* Section 3: Package Integrity */}
            <div className="print-avoid-break">
              <SectionTitle n={3} title="Package Integrity Cross-Verification (Reference vs. Inspected)" />
              {integrityData ? (
                <div className="space-y-3">
                  <div className={`rounded-xl border-2 p-3 text-center text-sm font-black tracking-widest ${
                    integrityData.status?.toUpperCase().includes("NO_SIGNIFICANT") || integrityData.status?.toUpperCase().includes("NO SIGNIFICANT")
                      ? "bg-emerald-50 border-emerald-500 text-emerald-800"
                      : integrityData.status?.toUpperCase().includes("POTENTIAL")
                        ? "bg-rose-50 border-rose-500 text-rose-800"
                        : "bg-amber-50 border-amber-500 text-amber-800"
                  }`}>
                    {integrityStatusLabel(integrityData.status)} &nbsp;&bull;&nbsp; Confidence: {Math.round((integrityData.confidence_score || 0) * 100)}%
                  </div>

                  {integrityData.summary_counts && (
                    <div className="grid grid-cols-4 gap-2 text-center text-xs">
                      {[
                        { label: "Matched", count: integrityData.summary_counts.consistent, color: "text-emerald-700" },
                        { label: "Review", count: integrityData.summary_counts.review_required, color: "text-amber-600" },
                        { label: "Discrepancy", count: integrityData.summary_counts.potential_discrepancy, color: "text-rose-700" },
                        { label: "Total Evaluated", count: integrityData.summary_counts.total_evaluated ?? 0, color: "text-slate-700" },
                      ].map(({ label, count, color }) => (
                        <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                          <div className={`text-xl font-black ${color}`}>{count ?? 0}</div>
                          <div className="text-slate-500 font-semibold">{label}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {((integrityData.matched_fields?.length ?? 0) > 0 || (integrityData.discrepancy_fields?.length ?? 0) > 0) && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                      {(integrityData.matched_fields?.length ?? 0) > 0 && (
                        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                          <p className="font-bold text-emerald-800 mb-1">&#10003; Verified Matching Fields</p>
                          {integrityData.matched_fields!.map((f) => <div key={f} className="text-emerald-700">• {f}</div>)}
                        </div>
                      )}
                      {(integrityData.discrepancy_fields?.length ?? 0) > 0 && (
                        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3">
                          <p className="font-bold text-rose-800 mb-1">&#10007; Discrepancy Detected</p>
                          {integrityData.discrepancy_fields!.map((f) => <div key={f} className="text-rose-700">• {f}</div>)}
                        </div>
                      )}
                    </div>
                  )}

                  {intFields.length > 0 && (
                    <div className="rounded-xl border border-slate-200 overflow-x-auto">
                      <table className="w-full text-left text-xs border-collapse">
                        <TableHeader cols={["Field", "Reference Value", "Inspected Value", "Classification", "Status", "Reason"]} />
                        <tbody className="divide-y divide-slate-100">
                          {intFields.map((f, i) => (
                            <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                              <td className="px-3 py-2 font-semibold text-slate-800 whitespace-nowrap">{f.field_name}</td>
                              <td className="px-3 py-2 text-slate-600 max-w-[120px] break-words">{f.reference_value || "—"}</td>
                              <td className="px-3 py-2 text-slate-700 max-w-[120px] break-words">{f.inspection_value || "—"}</td>
                              <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{f.field_classification || "—"}</td>
                              <td className={`px-3 py-2 whitespace-nowrap ${fieldCompStatusColor(f.status)}`}>{fieldCompStatusLabel(f.status)}</td>
                              <td className="px-3 py-2 text-slate-500 text-[10px] max-w-[140px] break-words">{f.reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {integrityData.explanation && (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 leading-relaxed">
                      <strong className="text-slate-800">AI Explanation: </strong>{integrityData.explanation}
                    </div>
                  )}
                </div>
              ) : loading ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center text-xs text-slate-400">
                  <Loader2 className="h-4 w-4 animate-spin mx-auto mb-2" />Loading package integrity data…
                </div>
              ) : (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center text-xs text-slate-400 italic">
                  Package integrity comparison not yet performed for this inspection.
                </div>
              )}
            </div>

            {/* Section 4: Cross-Departmental Regulatory Verification */}
            <div className="print-avoid-break">
              <SectionTitle n={4} title="Cross-Departmental Regulatory Verification (FSSAI / BIS / CDSCO / LMPC)" />
              {dossier ? (
                <div className="space-y-3">
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div><span className="font-bold text-slate-700">Category: </span><span className="text-slate-600">{dossier.commodity.category_label}</span></div>
                    <div><span className="font-bold text-slate-700">Subtype: </span><span className="text-slate-600">{dossier.commodity.commodity_subtype}</span></div>
                    <div><span className="font-bold text-slate-700">Is Food: </span><span className="text-slate-600">{dossier.commodity.is_food ? "Yes" : "No"}</span></div>
                    <div><span className="font-bold text-slate-700">Primary Regulator: </span><span className="text-slate-600">{dossier.primary_regulator}</span></div>
                  </div>

                  <div className="rounded-xl border border-slate-200 overflow-x-auto">
                    <table className="w-full text-left text-xs border-collapse">
                      <TableHeader cols={["Department", "Governing Act", "Ministry", "Identifier (Extracted)", "GTIN", "Verification Status", "Licensee / Remarks"]} />
                      <tbody className="divide-y divide-slate-100">
                        {deptDepts.map((dept, i) => (
                          <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                            <td className="px-3 py-2">
                              <div className="font-bold text-slate-800">{dept.department_code}</div>
                              <div className="text-slate-500 text-[10px]">{dept.department_name}</div>
                            </td>
                            <td className="px-3 py-2 text-slate-600 max-w-[110px] text-[10px] break-words">{dept.governing_act}</td>
                            <td className="px-3 py-2 text-slate-500 max-w-[90px] text-[10px] break-words">{dept.ministry}</td>
                            <td className="px-3 py-2 font-mono text-slate-700">{dept.extracted_identifier || "—"}</td>
                            <td className="px-3 py-2 font-mono text-slate-600">{dept.product_gtin || "—"}</td>
                            <td className={`px-3 py-2 whitespace-nowrap ${deptStatusColor(dept.verification_status)}`}>
                              {deptStatusLabel(dept.verification_status)}
                            </td>
                            <td className="px-3 py-2 text-slate-600 text-[10px] max-w-[150px] break-words">
                              {dept.licensee_name && <div><strong>Licensee:</strong> {dept.licensee_name}</div>}
                              {dept.licensee_premises && <div><strong>Premises:</strong> {dept.licensee_premises}</div>}
                              {dept.jurisdiction && <div><strong>Jurisdiction:</strong> {dept.jurisdiction}</div>}
                              {!dept.is_applicable && <div className="text-slate-400 italic">{dept.applicability_reason}</div>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {dossier.summary && (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 leading-relaxed">
                      <strong className="text-slate-800">Regulatory Summary: </strong>{dossier.summary}
                    </div>
                  )}
                </div>
              ) : loading ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center text-xs text-slate-400">
                  <Loader2 className="h-4 w-4 animate-spin mx-auto mb-2" />Loading departmental verification data…
                </div>
              ) : (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center text-xs text-slate-400 italic">
                  Departmental verification data not available for this inspection.
                </div>
              )}
            </div>
          </div>

          {/* ═══════════════════════════════════════════════════════════════ */}
          {/* PAGE 3 — Evidence Images · Contacts · Disclaimer · Sign-off    */}
          {/* ═══════════════════════════════════════════════════════════════ */}
          <div className="print-page-break p-6 sm:p-10 space-y-5">

            {/* Section 5: Evidence surface images */}
            <div>
              <SectionTitle n={5} title="Photographic Evidence — Annotated Visual Inspection Surfaces" />
              {surfaces.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {surfaces.map((surf, idx) => (
                    <div key={(surf as any).surfaceId || idx} className="print-avoid-break rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
                      {/* Surface label */}
                      <div className={`px-3 py-1 text-[10px] font-bold text-white uppercase text-center ${isViolation ? "bg-rose-700" : "bg-emerald-700"}`}>
                        Surface {idx + 1}: {(surf as any).faceLabel || (surf as any).surfaceType || `Face ${idx + 1}`} — {isViolation ? "Violations Detected" : "Compliant"}
                      </div>
                      {/* Image: correct aspect ratio, no distortion */}
                      <div className="flex items-center justify-center bg-slate-900 w-full" style={{ minHeight: "160px", maxHeight: "300px" }}>
                        {(surf as any).imageUrl ? (
                          <img
                            src={(surf as any).imageUrl}
                            alt={(surf as any).faceLabel || `Surface ${idx + 1}`}
                            style={{
                              display: "block",
                              maxWidth: "100%",
                              maxHeight: "300px",
                              width: "auto",
                              height: "auto",
                              objectFit: "contain",
                              margin: "0 auto",
                            }}
                          />
                        ) : (
                          <div className="text-slate-500 text-xs py-12">No image available for Surface {idx + 1}</div>
                        )}
                      </div>
                      <div className="px-3 py-2 text-[10px] font-mono text-slate-500">
                        {(surf as any).surfaceId || `surface_${idx + 1}.jpg`} — {isViolation ? "NON-COMPLIANT" : "COMPLIANT"}
                        {(surf as any).regions?.length > 0 && <span className="ml-2">({(surf as any).regions.length} localized region(s))</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center text-xs text-slate-400 italic">
                  No surface images available in this inspection.
                </div>
              )}

              {/* Sub-section 5B: Specific Rule Localized Bounding Box Cutouts */}
              <div className="mt-5 space-y-3">
                <div className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                  <BadgeCheck className="h-3.5 w-3.5 text-emerald-600" />
                  Specific Rule Localized Bounding Box Cutouts (Aspect Ratio Preserved)
                </div>
                <p className="text-[11px] text-slate-500">
                  Micro-crops isolated directly around statutory inscriptions with localized coordinate bounds.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {allDecls.filter((d: any) => d.evidenceCropBase64 || d.evidenceCrop || d.boundingBox || d.bbox).slice(0, 6).map((d: any, idx) => {
                    const cropB64 = d.evidenceCropBase64 || d.evidenceCrop;
                    const bbox = d.boundingBox || d.bbox;
                    const bboxStr = Array.isArray(bbox) ? `[${bbox.map((v: number) => Math.round(v)).join(", ")}]` : null;

                    return (
                      <div key={idx} className="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-800 truncate">{fieldLabel(d.field)}</span>
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            d.status === "VERIFIED" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
                          }`}>
                            {d.status}
                          </span>
                        </div>

                        {/* Aspect ratio preserved crop preview */}
                        <div className="flex items-center justify-center bg-slate-900 rounded-lg p-2 overflow-hidden" style={{ minHeight: "90px", maxHeight: "140px" }}>
                          {cropB64 ? (
                            <img
                              src={cropB64.startsWith("data:") ? cropB64 : `data:image/jpeg;base64,${cropB64}`}
                              alt={d.field}
                              style={{
                                display: "block",
                                maxWidth: "100%",
                                maxHeight: "120px",
                                width: "auto",
                                height: "auto",
                                objectFit: "contain",
                                margin: "0 auto",
                              }}
                            />
                          ) : (
                            <div className="text-slate-400 text-[10px] text-center p-2">
                              Bounding Box Coordinate: {bboxStr || "Mapped"}
                            </div>
                          )}
                        </div>

                        <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
                          <span className="truncate max-w-[120px]">Val: {d.value || "—"}</span>
                          {bboxStr && <span>BBox: {bboxStr}</span>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Sub-section 5C: Side-by-Side Reference vs. Inspected Evidence Comparison */}
              {intFields.length > 0 && (
                <div className="mt-5 space-y-3">
                  <div className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5 text-blue-600" />
                    Side-by-Side Reference Standard vs. Inspected Package Comparison
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Direct visual corroboration between approved catalog reference standard and scanned retail specimen.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {intFields.filter((f) => f.reference_crop || f.inspection_crop).slice(0, 4).map((f, fIdx) => (
                      <div key={fIdx} className="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2 text-xs">
                        <div className="font-bold text-slate-800 flex items-center justify-between">
                          <span>{fieldLabel(f.field_name)}</span>
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            f.comparison_status === "CONSISTENT" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
                          }`}>
                            {f.comparison_status || "EVALUATED"}
                          </span>
                        </div>

                        <div className="grid grid-cols-2 gap-2 text-center">
                          {/* Reference Standard */}
                          <div className="space-y-1">
                            <span className="text-[10px] font-semibold text-slate-600">Reference Standard</span>
                            <div className="flex items-center justify-center bg-slate-900 rounded p-1.5" style={{ minHeight: "75px", maxHeight: "110px" }}>
                              {f.reference_crop ? (
                                <img
                                  src={f.reference_crop.startsWith("data:") ? f.reference_crop : `data:image/jpeg;base64,${f.reference_crop}`}
                                  alt="Reference"
                                  style={{ maxWidth: "100%", maxHeight: "100px", width: "auto", height: "auto", objectFit: "contain" }}
                                />
                              ) : (
                                <span className="text-slate-400 text-[9px]">Text Standard</span>
                              )}
                            </div>
                            <div className="text-[10px] font-mono text-slate-700 truncate">{f.reference_value || "—"}</div>
                          </div>

                          {/* Inspected Specimen */}
                          <div className="space-y-1">
                            <span className="text-[10px] font-semibold text-slate-600">Inspected Specimen</span>
                            <div className="flex items-center justify-center bg-slate-900 rounded p-1.5" style={{ minHeight: "75px", maxHeight: "110px" }}>
                              {f.inspection_crop ? (
                                <img
                                  src={f.inspection_crop.startsWith("data:") ? f.inspection_crop : `data:image/jpeg;base64,${f.inspection_crop}`}
                                  alt="Inspected"
                                  style={{ maxWidth: "100%", maxHeight: "100px", width: "auto", height: "auto", objectFit: "contain" }}
                                />
                              ) : (
                                <span className="text-slate-400 text-[9px]">Captured Inscription</span>
                              )}
                            </div>
                            <div className="text-[10px] font-mono text-slate-700 truncate">{f.inspection_value || "—"}</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Section 6: Consumer & Manufacturer contact */}
            <div className="print-avoid-break">
              <SectionTitle n={6} title="Statutory Communications — Manufacturer &amp; Consumer Care Contact" />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Manufacturer */}
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-2 text-xs">
                  <div className="flex items-center gap-2 mb-1">
                    <Building2 className="h-4 w-4 text-slate-600" />
                    <span className="font-bold text-slate-800 text-sm">Manufacturer / Packer</span>
                  </div>
                  <div className="text-slate-700 font-semibold leading-relaxed">{mfgDecl?.value || inspection.manufacturer || "Not Declared"}</div>
                  {addrDecl?.value && (
                    <div className="text-slate-500 leading-relaxed">{addrDecl.value}</div>
                  )}
                  {fssaiDecl?.value && (
                    <div className="flex items-center gap-1 mt-2 text-emerald-700 font-semibold">
                      <BadgeCheck className="h-3 w-3" />FSSAI License: {fssaiDecl.value}
                    </div>
                  )}
                </div>

                {/* Consumer Care */}
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-2 text-xs">
                  <div className="flex items-center gap-2 mb-1">
                    <ShieldCheck className="h-4 w-4 text-slate-600" />
                    <span className="font-bold text-slate-800 text-sm">Consumer Care Details</span>
                  </div>
                  {consumerCareText
                    ? <div className="text-slate-700 leading-relaxed">{consumerCareText}</div>
                    : <div className="text-slate-400 italic">Consumer care contact not declared</div>}
                  {emailMatch && emailMatch.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {emailMatch.map((e) => (
                        <span key={e} className="flex items-center gap-1 text-blue-700 font-semibold">
                          <Mail className="h-3 w-3" />{e}
                        </span>
                      ))}
                    </div>
                  )}
                  {phoneMatch && phoneMatch.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {phoneMatch.slice(0, 3).map((p, i) => (
                        <span key={i} className="flex items-center gap-1 text-slate-700">
                          <Phone className="h-3 w-3" />{p.trim()}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="mt-2 pt-2 border-t border-slate-200">
                    <div className="text-slate-500 font-semibold">National Consumer Helpline</div>
                    <div className="text-slate-600">Toll-free: 1915 &bull; consumer.affairs@nic.in</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Statutory Disclaimer */}
            <div className="print-avoid-break rounded-xl border-2 border-amber-400 bg-amber-50 p-4 text-xs leading-relaxed text-amber-900">
              <strong>STATUTORY DISCLAIMER:</strong> This report is generated by LexMetra, an automated Legal Metrology computer vision AI screening system.
              Findings marked VIOLATION, REVIEW_REQUIRED, or UNCERTAIN must be verified by an authorized Legal Metrology Officer under the Legal Metrology Act, 2009, before formal enforcement action.
              This report does not constitute a final enforcement order. Reference cross-verification is advisory and independent of statutory determinations under the Legal Metrology Act, 2009.
            </div>

            {/* Officer Sign-off */}
            <div className="print-avoid-break pt-4 border-t-2 border-slate-300 grid grid-cols-1 sm:grid-cols-3 gap-6 text-xs text-slate-800">
              <div className="space-y-5">
                <div><span className="font-bold block mb-1">Screened By:</span>LexMetra AI Vision Platform v2.4</div>
                <div><span className="font-bold block mb-1">Inspection ID:</span><span className="font-mono break-all">{inspection.id}</span></div>
              </div>
              <div className="space-y-5">
                <div>
                  <span className="font-bold block mb-1">Verified By (Officer Signature):</span>
                  <div className="mt-6 border-b border-slate-400 w-48">&nbsp;</div>
                </div>
                <div>
                  <span className="font-bold block mb-1">Officer Name &amp; Designation:</span>
                  <div className="mt-6 border-b border-slate-400 w-48">&nbsp;</div>
                </div>
              </div>
              <div className="space-y-5">
                <div>
                  <span className="font-bold block mb-1">Date of Physical Verification:</span>
                  <div className="mt-6 border-b border-slate-400 w-32">&nbsp;</div>
                </div>
                <div>
                  <span className="font-bold block mb-1">Official Stamp / Seal:</span>
                  <div className="mt-2 h-16 w-16 rounded-full border-2 border-dashed border-slate-300">&nbsp;</div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="text-center text-[10px] text-slate-400 border-t border-slate-200 pt-3">
              Generated by LexMetra — Legal Metrology Compliance AI Platform &bull; Government of India, Ministry of Consumer Affairs &bull; {formatDate(new Date().toISOString())}
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
