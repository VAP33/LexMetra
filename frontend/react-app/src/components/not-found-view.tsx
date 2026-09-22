import React from "react";
import { FileQuestion, ArrowLeft, Camera, Sparkles, Users, Home } from "lucide-react";
import { type Language } from "@/lib/i18n";
import { type AppView } from "@/lib/nav-history";

interface NotFoundViewProps {
  onNavigate: (view: AppView) => void;
  lang?: Language;
}

export function NotFoundView({ onNavigate, lang = "en" }: NotFoundViewProps) {
  const t = {
    en: {
      code: "404",
      badge: "Statutory Resource Not Found",
      title: "Requested Docket or View Missing",
      desc: "The compliance docket, verification record, or statutory page you attempted to access does not exist or has been relocated to the permanent archive.",
      backHome: "Platform Overview",
      startScan: "Start Package Inspection",
      citizenPortal: "Citizen Portal (1915)",
    },
    hi: {
      code: "404",
      badge: "वैधानिक संसाधन नहीं मिला",
      title: "अनुरोधित डॉकेट या पृष्ठ उपलब्ध नहीं है",
      desc: "जो अनुपालन डॉकेट या वैधानिक पृष्ठ आप ढूंढ रहे हैं वह मौजूद नहीं है या अभिलेखागार में स्थानांतरित कर दिया गया है।",
      backHome: "मुख्य पृष्ठ",
      startScan: "पैकेज स्कैन करें",
      citizenPortal: "नागरिक पोर्टल",
    },
    mr: {
      code: "404",
      badge: "वैधानिक संसाधन सापडले नाही",
      title: "विनंती केलेले डॉकेट किंवा पृष्ठ अनुपलब्ध",
      desc: "आपण शोधत असलेले अनुपालन डॉकेट किंवा पृष्ठ अस्तित्वात नाही किंवा संग्रहित केले गेले आहे.",
      backHome: "मुख्य पृष्ठ",
      startScan: "पॅकेज स्कॅन करा",
      citizenPortal: "नागरिक पोर्टल",
    },
  }[lang] || {
    code: "404",
    badge: "Statutory Resource Not Found",
    title: "Requested Docket or View Missing",
    desc: "The compliance docket, verification record, or statutory page you attempted to access does not exist or has been relocated to the permanent archive.",
    backHome: "Platform Overview",
    startScan: "Start Package Inspection",
    citizenPortal: "Citizen Portal (1915)",
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-between selection:bg-saffron-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-brand-900/60 bg-gradient-to-r from-brand-950 via-brand-900 to-brand-800 text-white sticky top-0 z-30 shadow-md">
        <div className="h-1.5 w-full tricolor-stripe" />
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
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
          <button
            type="button"
            onClick={() => onNavigate("landing")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-xs font-semibold transition"
          >
            <Home className="h-3.5 w-3.5" />
            <span>Home</span>
          </button>
        </div>
      </header>

      {/* Main 404 Hero */}
      <main className="max-w-2xl mx-auto px-4 py-12 sm:py-16 text-center space-y-6 flex-1 flex flex-col items-center justify-center">
        {/* Error Badge */}
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-red-50 border border-red-200 text-red-700 text-xs font-bold shadow-xs">
          <FileQuestion className="h-4 w-4" />
          <span>{t.badge}</span>
        </div>

        {/* Big 404 Text */}
        <div className="relative">
          <span className="text-7xl sm:text-9xl font-black tracking-tight text-transparent bg-clip-text bg-gradient-to-b from-brand-950 to-brand-800 font-mono select-none">
            {t.code}
          </span>
          <div className="h-1.5 w-24 mx-auto tricolor-stripe rounded-full -mt-2 sm:-mt-4" />
        </div>

        {/* Title and Description */}
        <div className="space-y-2 max-w-lg">
          <h2 className="text-xl sm:text-2xl font-black text-brand-950">
            {t.title}
          </h2>
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t.desc}
          </p>
        </div>

        {/* Recovery Action Cards */}
        <div className="w-full pt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <button
            type="button"
            onClick={() => onNavigate("landing")}
            className="flex flex-col items-center gap-2 p-4 rounded-2xl border-2 border-slate-200 bg-white hover:border-brand-500 shadow-xs transition group touch-manipulation cursor-pointer"
          >
            <div className="h-10 w-10 rounded-xl bg-brand-50 text-brand-800 flex items-center justify-center group-hover:scale-110 transition">
              <Sparkles className="h-5 w-5" />
            </div>
            <span className="text-xs font-bold text-brand-950">{t.backHome}</span>
          </button>

          <button
            type="button"
            onClick={() => onNavigate("scan")}
            className="flex flex-col items-center gap-2 p-4 rounded-2xl border-2 border-saffron-200 bg-white hover:border-saffron-500 shadow-xs transition group touch-manipulation cursor-pointer"
          >
            <div className="h-10 w-10 rounded-xl bg-saffron-50 text-saffron-600 flex items-center justify-center group-hover:scale-110 transition">
              <Camera className="h-5 w-5" />
            </div>
            <span className="text-xs font-bold text-saffron-700">{t.startScan}</span>
          </button>

          <button
            type="button"
            onClick={() => onNavigate("customer")}
            className="flex flex-col items-center gap-2 p-4 rounded-2xl border-2 border-emerald-200 bg-white hover:border-govgreen shadow-xs transition group touch-manipulation cursor-pointer"
          >
            <div className="h-10 w-10 rounded-xl bg-emerald-50 text-govgreen flex items-center justify-center group-hover:scale-110 transition">
              <Users className="h-5 w-5" />
            </div>
            <span className="text-xs font-bold text-govgreen">{t.citizenPortal}</span>
          </button>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 py-4 text-center text-xs text-slate-500">
        Legal Metrology Statutory Compliance Platform · 404 Handler
      </footer>
    </div>
  );
}
