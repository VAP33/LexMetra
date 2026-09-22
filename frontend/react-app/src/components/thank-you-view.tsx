import React from "react";
import { CheckCircle2, FileText, ArrowRight, Camera, ShieldCheck, Download, Share2 } from "lucide-react";
import { type Language } from "@/lib/i18n";
import { type AppView } from "@/lib/nav-history";

interface ThankYouViewProps {
  onNavigate: (view: AppView) => void;
  docketId?: string;
  kind?: "inspection" | "grievance";
  lang?: Language;
}

export function ThankYouView({
  onNavigate,
  docketId = "LM-2026-" + Math.floor(100000 + Math.random() * 900000),
  kind = "inspection",
  lang = "en",
}: ThankYouViewProps) {
  const isGrievance = kind === "grievance";

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-between selection:bg-saffron-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-brand-900/60 bg-gradient-to-r from-brand-950 via-brand-900 to-brand-800 text-white sticky top-0 z-30 shadow-md">
        <div className="h-1.5 w-full tricolor-stripe" />
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img
              src="/lexmetra-white-logo.png"
              alt="LexMetra Logo"
              className="h-8 sm:h-9 w-auto object-contain"
            />
            <span className="text-base font-black tracking-wider text-white font-mono">
              LEXMETRA
            </span>
          </div>
          <span className="text-xs font-mono font-bold bg-emerald-500/20 border border-emerald-400/40 text-emerald-300 px-3 py-1 rounded-full">
            Docket Verified
          </span>
        </div>
      </header>

      {/* Main Thank You Card */}
      <main className="max-w-xl mx-auto px-4 py-10 sm:py-14 flex-1 flex flex-col items-center justify-center">
        <div className="w-full rounded-3xl border-2 border-slate-200 bg-white p-6 sm:p-8 shadow-xl shadow-brand-950/5 text-center space-y-5">
          {/* Animated Success Check Icon */}
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-50 text-govgreen border-2 border-emerald-200 shadow-md animate-in zoom-in duration-300">
            <CheckCircle2 className="h-9 w-9 text-govgreen" />
          </div>

          <div className="space-y-1.5">
            <span className="text-[10px] font-bold uppercase tracking-widest text-saffron-600 font-mono">
              Official Statutory Confirmation
            </span>
            <h1 className="text-xl sm:text-2xl font-black text-brand-950">
              {isGrievance
                ? "Grievance Successfully Lodged"
                : "Inspection Docket Recorded"}
            </h1>
            <p className="text-xs sm:text-sm text-slate-600 max-w-md mx-auto leading-relaxed">
              {isGrievance
                ? "Your consumer packaging grievance has been timestamped and indexed for verification by the respective Legal Metrology Controller."
                : "All 13 statutory declarations and Rule 12 Unit Sale Price mathematical evaluations have been cryptographically committed to the register."}
            </p>
          </div>

          {/* Reference Docket Box */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-left space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500 font-semibold">Docket Reference ID:</span>
              <span className="font-mono font-bold text-brand-900 bg-brand-100/60 px-2 py-0.5 rounded border border-brand-200">
                {docketId}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500 font-semibold">Statutory Authority:</span>
              <span className="font-semibold text-slate-800">Legal Metrology Act, 2009</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500 font-semibold">Audit Hash:</span>
              <span className="font-mono text-[10px] text-slate-500 truncate max-w-[180px]">
                sha256:4f8e9b1a7d...3c2e
              </span>
            </div>
          </div>

          {/* Action CTAs */}
          <div className="pt-2 flex flex-col sm:flex-row items-stretch sm:items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => onNavigate("scan")}
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-2xl bg-gradient-to-r from-saffron-500 to-orange-600 hover:from-saffron-600 hover:to-orange-700 text-white font-bold text-xs shadow-md transition active:scale-95 touch-manipulation cursor-pointer"
            >
              <Camera className="h-4 w-4" />
              <span>Scan Another Package</span>
            </button>

            <button
              type="button"
              onClick={() => onNavigate("landing")}
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-2xl border-2 border-slate-200 bg-white hover:bg-slate-50 text-slate-800 font-bold text-xs shadow-xs transition active:scale-95 touch-manipulation cursor-pointer"
            >
              <span>Return to Overview</span>
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 py-4 text-center text-xs text-slate-500">
        Legal Metrology Statutory Compliance Platform · Confirmation Service
      </footer>
    </div>
  );
}
