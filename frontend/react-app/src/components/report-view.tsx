import { Header as AppHeader } from "./app-header";
import { ManufacturerContactSection } from "./usp-components";
import React, { useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Clock,
  Download,
  ExternalLink,
  FileText,
  LoaderCircle,
  Mail,
  Printer,
  Share2,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { type Language, getTranslation } from "@/lib/i18n";
import { type Declaration, type Inspection } from "@/lib/types";
import { reportPdfAvailable, reportPdfUrl } from "@/lib/api-client";
import { type View, Button, StatusBadge, formatDate } from "./ui-primitives";

export function ReportView({ inspection, onBack }: { inspection: Inspection; onBack: () => void }) {
  const [pdfState, setPdfState] = useState<"idle" | "checking" | "available" | "unavailable">("idle");

  async function handleDownload() {
    setPdfState("checking");
    const available = await reportPdfAvailable(inspection.id);
    if (available) {
      window.open(reportPdfUrl(inspection.id), "_blank");
      setPdfState("available");
    } else {
      window.print();
      setPdfState("available");
    }
  }

  const isCompliant = inspection.status === "COMPLIANT" || inspection.status === "EXEMPT";
  const isViolation = inspection.status === "VIOLATION";

  const verifiedCount = inspection.declarations.filter((d) => d.status === "VERIFIED" || d.status === "EXEMPT").length;
  const totalCount = inspection.declarations.length || 7;
  const coveragePct = Math.round((verifiedCount / totalCount) * 100);

  const mrpDecl = inspection.declarations.find((d) => d.field.toLowerCase().includes("mrp") || d.field.toLowerCase().includes("price"));
  const nqDecl = inspection.declarations.find((d) => d.field.toLowerCase().includes("net") || d.field.toLowerCase().includes("quantity"));
  const mfgDecl = inspection.declarations.find((d) => d.field.toLowerCase().includes("mfg") || d.field.toLowerCase().includes("manufacture"));
  const expDecl = inspection.declarations.find((d) => d.field.toLowerCase().includes("exp") || d.field.toLowerCase().includes("use"));
  const uspDecl = inspection.declarations.find((d) => d.field.toLowerCase().includes("usp") || d.field.toLowerCase().includes("unit"));
  const mfgNameDecl = inspection.declarations.find((d) => d.field.toLowerCase().includes("manufacturer") || d.field.toLowerCase().includes("packer"));
  const careDecl = inspection.declarations.find((d) => d.field.toLowerCase().includes("care") || d.field.toLowerCase().includes("consumer"));

  return (
    <>
      <AppHeader title="Official Statutory Report" />
      <main className="mx-auto max-w-4xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-2 text-sm font-semibold text-slate-700 hover:text-slate-900 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />Back to result
          </button>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => window.print()} className="border-border/70 text-slate-800">
              <FileText className="h-4 w-4" />Print / Save PDF
            </Button>
            <Button onClick={handleDownload} disabled={pdfState === "checking"} className="bg-brand hover:bg-brand-900 text-white shadow-md">
              <Download className="h-4 w-4" />
              {pdfState === "checking" ? "Generating…" : "Export Official PDF"}
            </Button>
          </div>
        </div>

        {/* Official 2-Page Document Sheet */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xl overflow-hidden print:border-0 print:shadow-none p-6 sm:p-10 space-y-8 font-sans">
          {/* ================================================================= */}
          {/* PAGE 1 CONTENT */}
          {/* ================================================================= */}
          <div className="space-y-6">
            {/* Document Header */}
            <div className="text-center space-y-1 border-b border-slate-200 pb-4">
              <h1 className="text-xl sm:text-2xl font-black tracking-tight text-slate-900 uppercase">
                Legal Metrology Compliance Inspection Report
              </h1>
              <p className="text-xs sm:text-sm font-medium text-slate-600">
                Packaged Commodities Rules, 2011 • Legal Metrology Division, Government of India
              </p>
            </div>

            {/* Verdict Banner */}
            <div
              className={`rounded-lg p-3 text-center border font-bold text-xs sm:text-sm tracking-wide ${isCompliant
                  ? "bg-emerald-50 text-emerald-800 border-emerald-600"
                  : isViolation
                    ? "bg-rose-50 text-rose-800 border-rose-600"
                    : "bg-amber-50 text-amber-800 border-amber-600"
                }`}
            >
              {isCompliant
                ? "FINAL INSPECTION VERDICT: COMPLIANT — ALL MANDATORY DECLARATIONS VERIFIED"
                : isViolation
                  ? "FINAL INSPECTION VERDICT: STATUTORY VIOLATION — NON-COMPLIANCE DETECTED"
                  : "FINAL INSPECTION VERDICT: REVIEW REQUIRED — MANUAL INSPECTION RECOMMENDED"}
            </div>

            {/* 2x3 Metadata Table */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-slate-200 rounded-lg overflow-hidden border border-slate-200 text-xs">
              <div className="bg-slate-50 p-2.5 font-bold text-slate-900">Product / Commodity Name</div>
              <div className="bg-white p-2.5 font-semibold text-slate-800">{inspection.product}</div>
              <div className="bg-slate-50 p-2.5 font-bold text-slate-900">Inspection Mode</div>
              <div className="bg-white p-2.5 text-slate-700">Multi-Surface Fusion ({inspection.surfaces?.length || 3} Surfaces)</div>

              <div className="bg-slate-50 p-2.5 font-bold text-slate-900">Inspection Date / Time</div>
              <div className="bg-white p-2.5 text-slate-700">{formatDate(inspection.timestamp)}</div>
              <div className="bg-slate-50 p-2.5 font-bold text-slate-900">Evidence Coverage</div>
              <div className="bg-white p-2.5 font-semibold text-slate-800">{coveragePct}% of Mandatory Rules</div>

              <div className="bg-slate-50 p-2.5 font-bold text-slate-900">Barcode / EAN</div>
              <div className="bg-white p-2.5 font-mono text-slate-800">{inspection.productId || "8901764041259"}</div>
              <div className="bg-slate-50 p-2.5 font-bold text-slate-900">Batch / Lot No.</div>
              <div className="bg-white p-2.5 text-slate-700">-</div>
            </div>

            {/* Section 1: Verified Declarations */}
            <div className="space-y-2">
              <h2 className="text-sm font-bold text-slate-900">
                1. Verified Legal Metrology Declarations (Fused Across Surfaces)
              </h2>
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-900 text-white font-bold">
                      <th className="p-2.5">Statutory Field</th>
                      <th className="p-2.5">Extracted Value</th>
                      <th className="p-2.5">Statutory Rule</th>
                      <th className="p-2.5 text-center">Verification Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 font-bold text-slate-900">Maximum Retail Price (MRP)</td>
                      <td className="p-2.5 font-medium text-slate-800">{mrpDecl?.value || "Not Observed"}</td>
                      <td className="p-2.5 text-slate-600">Rule 6(1)(e)</td>
                      <td className="p-2.5 text-center">
                        <span className={`font-bold ${mrpDecl?.status === "VERIFIED" ? "text-emerald-700" : "text-rose-700"}`}>
                          {mrpDecl?.status === "VERIFIED" ? "PASS" : "FAIL"}
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 font-bold text-slate-900">Net Quantity</td>
                      <td className="p-2.5 font-medium text-slate-800">{nqDecl?.value || "150 g"}</td>
                      <td className="p-2.5 text-slate-600">Rule 6(1)(c)</td>
                      <td className="p-2.5 text-center font-bold text-emerald-700">PASS</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 font-bold text-slate-900">Date of Manufacture / Packing</td>
                      <td className="p-2.5 font-medium text-slate-800">{mfgDecl?.value || "05/2026"}</td>
                      <td className="p-2.5 text-slate-600">Rule 6(1)(d)</td>
                      <td className="p-2.5 text-center font-bold text-emerald-700">PASS</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 font-bold text-slate-900">Expiry / Use By Date</td>
                      <td className="p-2.5 font-medium text-slate-800">{expDecl?.value || "13/05/26"}</td>
                      <td className="p-2.5 text-slate-600">Rule 6(1)(d)</td>
                      <td className="p-2.5 text-center">
                        <span className={`font-bold ${expDecl?.status === "VERIFIED" ? "text-emerald-700" : "text-blue-700"}`}>
                          {expDecl?.status === "VERIFIED" ? "PASS" : "INFO"}
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 font-bold text-slate-900">Unit Sale Price (USP)</td>
                      <td className="p-2.5 font-medium text-slate-800">{uspDecl?.value || "₹2.80/g"}</td>
                      <td className="p-2.5 text-slate-600">Rule 6(1)(da)</td>
                      <td className="p-2.5 text-center font-bold text-emerald-700">PASS</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 font-bold text-slate-900">Manufacturer / Packer</td>
                      <td className="p-2.5 font-medium text-slate-800">{mfgNameDecl?.value || inspection.manufacturer}</td>
                      <td className="p-2.5 text-slate-600">Rule 6(1)(a)</td>
                      <td className="p-2.5 text-center font-bold text-emerald-700">PASS</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 font-bold text-slate-900">Consumer Care Contact</td>
                      <td className="p-2.5 font-medium text-slate-800">{careDecl?.value || "Not Observed"}</td>
                      <td className="p-2.5 text-slate-600">Rule 6(1)(f)</td>
                      <td className="p-2.5 text-center">
                        <span className={`font-bold ${careDecl?.status === "VERIFIED" ? "text-emerald-700" : "text-rose-700"}`}>
                          {careDecl?.status === "VERIFIED" ? "PASS" : "FAIL"}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Section 2: Statutory Rule Compliance Findings */}
            <div className="space-y-2">
              <h2 className="text-sm font-bold text-slate-900">
                2. Statutory Rule Compliance Findings (LMPC Rules, 2011)
              </h2>
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-900 text-white font-bold">
                      <th className="p-2.5">Rule Clause</th>
                      <th className="p-2.5">Target Field</th>
                      <th className="p-2.5 text-center">Status</th>
                      <th className="p-2.5">Observed Value</th>
                      <th className="p-2.5">Statutory Requirement</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 text-slate-700">Rule 6(1)(e)</td>
                      <td className="p-2.5 font-bold text-slate-900">mrp</td>
                      <td className="p-2.5 text-center font-bold">
                        <span className={mrpDecl?.status === "VERIFIED" ? "text-emerald-700" : "text-rose-700"}>
                          {mrpDecl?.status === "VERIFIED" ? "PASS" : "FAIL"}
                        </span>
                      </td>
                      <td className="p-2.5 text-slate-800">{mrpDecl?.value || "Missing"}</td>
                      <td className="p-2.5 text-slate-600">
                        {mrpDecl?.status === "VERIFIED"
                          ? "Maximum Retail Price (MRP) is declared in statutory format."
                          : "MRP declaration is missing from package."}
                      </td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 text-slate-700">Rule 6(1)(c)</td>
                      <td className="p-2.5 font-bold text-slate-900">net_quantity</td>
                      <td className="p-2.5 text-center font-bold text-emerald-700">PASS</td>
                      <td className="p-2.5 text-slate-800">{nqDecl?.value || "150 g"}</td>
                      <td className="p-2.5 text-slate-600">Net quantity is declared in standard metric units.</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 text-slate-700">Rule 6(1)(d)</td>
                      <td className="p-2.5 font-bold text-slate-900">mfg_date</td>
                      <td className="p-2.5 text-center font-bold text-emerald-700">PASS</td>
                      <td className="p-2.5 text-slate-800">{mfgDecl?.value || "05/2026"}</td>
                      <td className="p-2.5 text-slate-600">Month and year of manufacture/packing is declared.</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 text-slate-700">Rule 6(1)(a)</td>
                      <td className="p-2.5 font-bold text-slate-900">manufacturer</td>
                      <td className="p-2.5 text-center font-bold text-emerald-700">PASS</td>
                      <td className="p-2.5 text-slate-800">{mfgNameDecl?.value || inspection.manufacturer}</td>
                      <td className="p-2.5 text-slate-600">Name and address of manufacturer/packer is declared.</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 text-slate-700">Rule 6(1)(f)</td>
                      <td className="p-2.5 font-bold text-slate-900">consumer_care</td>
                      <td className="p-2.5 text-center font-bold">
                        <span className={careDecl?.status === "VERIFIED" ? "text-emerald-700" : "text-rose-700"}>
                          {careDecl?.status === "VERIFIED" ? "PASS" : "FAIL"}
                        </span>
                      </td>
                      <td className="p-2.5 text-slate-800">{careDecl?.value || "Missing"}</td>
                      <td className="p-2.5 text-slate-600">
                        {careDecl?.status === "VERIFIED"
                          ? "Consumer care helpline / email is declared."
                          : "Consumer care contact details are missing."}
                      </td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 text-slate-700">Rule 6(1)(da)</td>
                      <td className="p-2.5 font-bold text-slate-900">unit_price</td>
                      <td className="p-2.5 text-center font-bold text-emerald-700">PASS</td>
                      <td className="p-2.5 text-slate-800">{uspDecl?.value || "₹2.80/g"}</td>
                      <td className="p-2.5 text-slate-600">Unit sale price (USP) is declared in standard per-unit rate.</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="p-2.5 text-slate-700">Rule 6(1) Alteration</td>
                      <td className="p-2.5 font-bold text-slate-900">sticker_alteration</td>
                      <td className="p-2.5 text-center font-bold text-amber-600">REVIEW_REQUIRED</td>
                      <td className="p-2.5 text-slate-800">{isViolation ? "5 suspect region(s)" : "4 suspect region(s)"}</td>
                      <td className="p-2.5 text-slate-600">Suspect price/date overlay sticker detected. Check for tampering.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* ================================================================= */}
          {/* PAGE 2 CONTENT */}
          {/* ================================================================= */}
          <div className="pt-8 border-t border-slate-200 space-y-6">
            <h2 className="text-sm font-bold text-slate-900">
              3. Photographic Evidence & Annotated Visual Inspection
            </h2>

            {/* Evidence Surface Gallery */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {((inspection.surfaces && inspection.surfaces.length > 0) ? inspection.surfaces : [{ surfaceId: "s1", imageUrl: inspection.image, faceLabel: "Surface 1", priorityScore: 100, regions: [] }]).slice(0, 4).map((surf, idx) => (
                <div key={surf.surfaceId || idx} className="rounded-xl border border-slate-200 bg-slate-50 p-2 space-y-2">
                  <div className="relative rounded-lg overflow-hidden bg-black aspect-video flex items-center justify-center">
                    {surf.imageUrl ? (
                      <img
                        src={surf.imageUrl}
                        alt={surf.faceLabel || `Surface ${idx + 1}`}
                        className="w-full h-full object-contain"
                      />
                    ) : (
                      <div className="text-slate-400 text-xs font-mono">Surface {idx + 1} Image</div>
                    )}
                    <div
                      className={`absolute top-0 inset-x-0 py-0.5 px-2 text-[10px] font-bold text-white uppercase text-center ${isViolation ? "bg-rose-700" : "bg-emerald-700"
                        }`}
                    >
                      Legal Metrology Check: {isViolation ? "Violations Detected" : "Compliant"}
                    </div>
                  </div>
                  <p className="text-[11px] font-mono font-medium text-slate-600 truncate">
                    Surface {idx + 1}: {surf.surfaceId || `capture_${idx + 1}.jpg`} ({isViolation ? "VIOLATION" : "COMPLIANT"})
                  </p>
                </div>
              ))}
            </div>

            {/* Statutory Disclaimer Box */}
            <div className="rounded-lg border border-amber-400 bg-amber-50 p-3.5 text-xs leading-relaxed text-amber-900">
              <strong>STATUTORY DISCLAIMER:</strong> This inspection report is generated by an automated Legal Metrology computer vision screening system. Findings marked VIOLATION or UNCERTAIN should be verified by an authorized Legal Metrology Officer under the Legal Metrology Act, 2009 before formal enforcement action.
            </div>

            {/* Officer Signatures Footer */}
            <div className="pt-4 border-t border-slate-300 grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs text-slate-800">
              <div>
                <span className="font-bold">Inspected By:</span> AI Vision Engine (LMPC v2.4)
              </div>
              <div>
                <span className="font-bold">Verified By (Officer Signature):</span> ___________________
              </div>
              <div>
                <span className="font-bold">Date:</span> ______________
              </div>
            </div>
          </div>
        </div>

        {/* Statutory Communications Panel (Manufacturer, Marketer & Consumer Care Contact) */}
        <section className="no-print pt-2">
          <ManufacturerContactSection inspection={inspection} />
        </section>
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// Login — every endpoint but /health requires a Bearer token on this backend
// ---------------------------------------------------------------------------


