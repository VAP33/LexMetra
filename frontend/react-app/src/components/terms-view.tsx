import React from "react";
import { Scale, ArrowLeft, FileCheck, AlertTriangle, Shield, CheckCircle } from "lucide-react";
import { type Language } from "@/lib/i18n";

interface TermsViewProps {
  onBack: () => void;
  lang?: Language;
}

export function TermsView({ onBack, lang = "en" }: TermsViewProps) {
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
                <Scale className="h-5 w-5 text-saffron-400" />
                {lang === "hi"
                  ? "सेवा की शर्तें एवं वैधानिक उपयोग"
                  : lang === "mr"
                  ? "सेवा अटी आणि वैधानिक वापर"
                  : "Terms of Service & Statutory Usage"}
              </h1>
              <p className="text-[10px] sm:text-xs text-slate-300">
                Legal Metrology Act, 2009 · Packaged Commodities Rules, 2011
              </p>
            </div>
          </div>
          <span className="hidden sm:inline text-xs font-mono font-bold bg-white/10 border border-white/20 px-2.5 py-1 rounded-full text-govgreen">
            Official Regulatory Terms
          </span>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-10 space-y-6 sm:space-y-8">
        <div className="rounded-2xl border-2 border-emerald-200 bg-white p-5 sm:p-6 shadow-sm flex items-start gap-4">
          <div className="h-10 w-10 rounded-xl bg-emerald-50 text-govgreen flex items-center justify-center shrink-0 border border-emerald-200">
            <FileCheck className="h-5 w-5" />
          </div>
          <div className="space-y-1">
            <h2 className="text-sm sm:text-base font-bold text-brand-950">
              Statutory Platform Agreement
            </h2>
            <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
              By accessing, browsing, or executing inspections on the LexMetra compliance platform, you acknowledge and agree to comply with these terms, the Legal Metrology Act, 2009, and the Legal Metrology (Packaged Commodities) Rules, 2011. This platform serves authorized Legal Metrology officers and consumer citizens for statutory packaging verification.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Section 1: Authorized Inspector Usage */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-brand-950 font-bold text-sm">
              <Shield className="h-4 w-4 text-brand-700" />
              <h3>1. Enforcement Officer Protocols</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Authorized inspectors and officers accessing the Command Center warrant that all inspection captures are taken in the ordinary course of statutory duties under Sections 15 &amp; 18 of the Legal Metrology Act. Officers remain responsible for visually verifying AI OCR extractions prior to submitting formal seizure notices or compounding orders.
            </p>
          </div>

          {/* Section 2: Deterministic Rule Engine Status */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-brand-950 font-bold text-sm">
              <CheckCircle className="h-4 w-4 text-govgreen" />
              <h3>2. Deterministic Rule Engine Status</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Rule 12 Unit Sale Price calculations (MRP divided by declared Net Quantity) are deterministic arithmetic checks with zero error tolerance. While the OCR text extraction relies on high-speed computer vision, all arithmetic violations are accompanied by verbatim bounding-box crops to provide indisputable court evidence.
            </p>
          </div>

          {/* Section 3: Consumer Grievance Submissions */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-brand-950 font-bold text-sm">
              <Scale className="h-4 w-4 text-saffron-600" />
              <h3>3. Citizen Grievance Submissions</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Consumers utilizing the Citizen Verification portal agree to submit honest packaging photographs taken at retail or online points of purchase. Submitting fabricated or defamatory complaints is strictly prohibited and subject to legal action under applicable laws.
            </p>
          </div>

          {/* Section 4: Limitation of Liability */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-brand-950 font-bold text-sm">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <h3>4. Advisory Decision-Support Disclaimer</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              LexMetra functions as an accelerated computational assistant for regulatory enforcement. Final legal compounding notices, show-cause orders, and formal court prosecutions must be signed and confirmed by the competent Legal Metrology Authority of the respective State / Union Territory.
            </p>
          </div>
        </div>

        {/* Governing Law */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 space-y-3">
          <h3 className="text-sm font-bold text-brand-950">
            5. Jurisdiction &amp; Governing Law
          </h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            These terms and any disputes arising out of the use of the platform shall be governed by and construed in accordance with the laws of the Republic of India, with exclusive jurisdiction resting in the competent courts of New Delhi.
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
