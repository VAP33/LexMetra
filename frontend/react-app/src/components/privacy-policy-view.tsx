import React from "react";
import { ShieldCheck, ArrowLeft, Lock, FileText, CheckCircle2, Scale, Database, Eye } from "lucide-react";
import { type Language } from "@/lib/i18n";

interface PrivacyPolicyViewProps {
  onBack: () => void;
  lang?: Language;
}

export function PrivacyPolicyView({ onBack, lang = "en" }: PrivacyPolicyViewProps) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-16">
      {/* Header Bar */}
      <header className="sticky top-0 z-30 border-b border-brand-900/60 bg-gradient-to-r from-brand-950 via-brand-900 to-brand-800 text-white shadow-md">
        <div className="h-1.5 w-full tricolor-stripe" />
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="rounded-xl p-2 bg-white/10 hover:bg-white/20 text-white transition active:scale-95 touch-manipulation cursor-pointer"
              aria-label="Go back"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-base sm:text-lg font-black tracking-tight text-white flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-govgreen" />
                {lang === "hi"
                  ? "गोपनीयता नीति एवं डेटा संरक्षण"
                  : lang === "mr"
                  ? "गोपनीयता धोरण आणि डेटा संरक्षण"
                  : "Privacy Policy & Statutory Data Protection"}
              </h1>
              <p className="text-[10px] sm:text-xs text-slate-300">
                Digital Personal Data Protection Act, 2023 · Legal Metrology Act, 2009
              </p>
            </div>
          </div>
          <span className="hidden sm:inline text-xs font-mono font-bold bg-white/10 border border-white/20 px-2.5 py-1 rounded-full text-saffron-300">
            DPDPA 2023 Compliant
          </span>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-10 space-y-6 sm:space-y-8">
        {/* Banner Notice */}
        <div className="rounded-2xl border-2 border-brand-200 bg-white p-5 sm:p-6 shadow-sm flex items-start gap-4">
          <div className="h-10 w-10 rounded-xl bg-brand-50 text-brand-900 flex items-center justify-center shrink-0 border border-brand-200">
            <Lock className="h-5 w-5" />
          </div>
          <div className="space-y-1">
            <h2 className="text-sm sm:text-base font-bold text-brand-950">
              Statutory Purpose &amp; Regulatory Mandate
            </h2>
            <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
              LexMetra is an automated compliance verification platform engineered strictly for enforcement of the Legal Metrology Act, 2009 and the Legal Metrology (Packaged Commodities) Rules, 2011. All photographic imagery, OCR vectors, and calculation logs are processed solely to verify statutory declarations (MRP, USP, Net Quantity, Manufacturer details, Best Before dates) on pre-packaged goods.
            </p>
          </div>
        </div>

        {/* Policy Sections */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* 1. Data Collection */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-brand-950 font-bold text-sm">
              <Eye className="h-4 w-4 text-saffron-600" />
              <h3>1. Data We Collect &amp; Process</h3>
            </div>
            <ul className="text-xs text-slate-600 space-y-2 leading-relaxed list-disc list-inside">
              <li><strong>Commodity Packaging Images:</strong> Visual surfaces of packaged consumer goods captured by field inspectors or consumers.</li>
              <li><strong>Optical Character Recognition (OCR) Vectors:</strong> Extracted bounding boxes of text, numerical weights, prices, dates, and FSSAI license codes.</li>
              <li><strong>Statutory Arithmetic:</strong> Derived unit sale price calculations under Rule 12.</li>
              <li><strong>Grievance Information:</strong> Store names, retailer location descriptions, and contact info optionally provided by citizens filing statutory grievance alerts.</li>
            </ul>
          </div>

          {/* 2. Facial & Biometric Exclusion */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-brand-950 font-bold text-sm">
              <CheckCircle2 className="h-4 w-4 text-govgreen" />
              <h3>2. Zero Biometric &amp; Facial Data Policy</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              LexMetra’s computer vision pipeline is strictly tuned for rectangular package geometry. If any human face or bystander is accidentally present in the camera frame, our homography preprocessor crops and isolates solely the commodity panel surface, preventing biometric storage in compliance with Section 4 of the DPDPA 2023.
            </p>
          </div>

          {/* 3. Security & Cryptographic Integrity */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-brand-950 font-bold text-sm">
              <Database className="h-4 w-4 text-brand-700" />
              <h3>3. Storage &amp; Cryptographic Audit Trails</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Every verified inspection docket is generated with an immutable SHA-256 digital fingerprint. All database records are stored with role-based access control (RBAC), and transmitted via TLS 1.3 encryption. Evidence documents are retained strictly for the statutory limitation period stipulated under Section 49 of the Legal Metrology Act.
            </p>
          </div>

          {/* 4. Consumer Grievance & NCH 1915 */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-brand-950 font-bold text-sm">
              <Scale className="h-4 w-4 text-purple-700" />
              <h3>4. Inter-Agency Consumer Grievance Sharing</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              When a citizen lodges a formal grievance regarding MRP overwriting or absence of unit pricing, reports may be securely routed to the Department of Consumer Affairs National Consumer Helpline (NCH 1915) or state Controller of Legal Metrology for field inspection.
            </p>
          </div>
        </div>

        {/* Officer & Data Principal Rights */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 space-y-3">
          <h3 className="text-sm font-bold text-brand-950">
            5. Rights of Data Principals (Under DPDPA 2023)
          </h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            Registered officers and citizen complainants maintain the right to review, rectify, or request deletion of personal profile data. Inquiries regarding statutory data protection can be directed to the LexMetra Legal Metrology Compliance Data Officer at <code>compliance@lexmetra.gov.in</code>.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-brand-900 hover:bg-brand-950 text-white text-xs font-bold shadow-sm transition active:scale-95 touch-manipulation cursor-pointer"
            >
              <ArrowLeft className="h-4 w-4" />
              <span>Return to Platform</span>
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
