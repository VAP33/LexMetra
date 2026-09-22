import React from "react";
import { PackageSearch, Camera, ArrowLeft, Sparkles, CheckCircle, Shield } from "lucide-react";
import { type Language } from "@/lib/i18n";
import { type AppView } from "@/lib/nav-history";

interface EmptyStateViewProps {
  onStartScan: () => void;
  onBack: () => void;
  lang?: Language;
}

export function EmptyStateView({ onStartScan, onBack, lang = "en" }: EmptyStateViewProps) {
  const t = {
    en: {
      badge: "Compliance Register Status",
      title: "No Inspection Records in Register",
      desc: "There are currently no active statutory package inspections in this workbench view. Start a 6-face package capture to populate the compliance register and trigger automated Rule 12 USP verification.",
      step1: "Align front principal display panel in camera target box",
      step2: "Rotate commodity through all 6 faces for complete 360° unobserved coverage",
      step3: "Deterministic engine cross-checks MRP vs Net Quantity with zero tolerance",
      startScan: "Start Package Inspection",
      returnHome: "Return to Dashboard",
    },
    hi: {
      badge: "अनुपालन रजिस्टर स्थिति",
      title: "रजिस्टर में कोई निरीक्षण रिकॉर्ड नहीं",
      desc: "वर्तमान में इस दृश्य में कोई सक्रिय निरीक्षण रिकॉर्ड नहीं है। अनुपालन रजिस्टर भरने और नियम 12 सत्यापन शुरू करने के लिए पैकेज स्कैन करें।",
      step1: "कैमरा बॉक्स में उत्पाद का मुख्य पैनल संरेखित करें",
      step2: "360° कवरेज के लिए उत्पाद की सभी 6 सतहों को घुमाएं",
      step3: "इंजन शून्य त्रुटि सहनशीलता के साथ एमआरपी और मात्रा का मिलान करता है",
      startScan: "पैकेज निरीक्षण शुरू करें",
      returnHome: "डैशबोर्ड पर लौटें",
    },
    mr: {
      badge: "अनुपालन नोंदवही स्थिती",
      title: "नोंदवहीत तपासणी नोंदी नाहीत",
      desc: "सध्या या दृश्यात कोणतीही सक्रिय तपासणी नोंद नाही. नोंदवही भरण्यासाठी आणि नियम 12 पडताळणी सुरू करण्यासाठी पॅकेज स्कॅन करा.",
      step1: "कॅमेरा बॉक्समध्ये उत्पादनाचा मुख्य पृष्ठभाग जुळवा",
      step2: "360° कव्हरेजसाठी उत्पादनाचे सर्व 6 पृष्ठभाग फिरवा",
      step3: "इंजिन शून्य त्रुटी सहनशीलतेसह एमआरपी आणि प्रमाणाची पडताळणी करते",
      startScan: "पॅकेज तपासणी सुरू करा",
      returnHome: "डॅशबोर्डवर परत जा",
    },
  }[lang] || {
    badge: "Compliance Register Status",
    title: "No Inspection Records in Register",
    desc: "There are currently no active statutory package inspections in this workbench view. Start a 6-face package capture to populate the compliance register and trigger automated Rule 12 USP verification.",
    step1: "Align front principal display panel in camera target box",
    step2: "Rotate commodity through all 6 faces for complete 360° unobserved coverage",
    step3: "Deterministic engine cross-checks MRP vs Net Quantity with zero tolerance",
    startScan: "Start Package Inspection",
    returnHome: "Return to Dashboard",
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-between selection:bg-saffron-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-brand-900/60 bg-gradient-to-r from-brand-950 via-brand-900 to-brand-800 text-white sticky top-0 z-30 shadow-md">
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
            <span className="text-base font-black tracking-wider text-white font-mono">
              LEXMETRA REGISTER
            </span>
          </div>
          <span className="text-xs font-mono font-bold bg-white/10 border border-white/20 px-3 py-1 rounded-full text-slate-300">
            0 Records
          </span>
        </div>
      </header>

      {/* Main Empty State Content */}
      <main className="max-w-2xl mx-auto px-4 py-10 sm:py-14 flex-1 flex flex-col items-center justify-center">
        <div className="w-full rounded-3xl border-2 border-dashed border-slate-300 bg-white p-6 sm:p-10 text-center space-y-6 shadow-sm">
          {/* Animated Empty Icon */}
          <div className="mx-auto flex h-16 w-16 sm:h-20 sm:w-20 items-center justify-center rounded-3xl bg-brand-50 text-brand-700 border-2 border-brand-200 shadow-sm">
            <PackageSearch className="h-8 w-8 sm:h-10 sm:w-10 text-brand-800" />
          </div>

          {/* Heading */}
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-100 text-slate-700 text-xs font-bold">
              <Shield className="h-3.5 w-3.5 text-saffron-600" />
              <span>{t.badge}</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-black text-brand-950">
              {t.title}
            </h1>
            <p className="text-xs sm:text-sm text-slate-600 max-w-lg mx-auto leading-relaxed">
              {t.desc}
            </p>
          </div>

          {/* 3 Step Guidance Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-left pt-2">
            <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 text-xs space-y-1">
              <span className="font-mono font-bold text-saffron-600 text-[11px]">01 · Align</span>
              <p className="text-slate-700 font-medium leading-relaxed">{t.step1}</p>
            </div>
            <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 text-xs space-y-1">
              <span className="font-mono font-bold text-govgreen text-[11px]">02 · 6-Face Scan</span>
              <p className="text-slate-700 font-medium leading-relaxed">{t.step2}</p>
            </div>
            <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 text-xs space-y-1">
              <span className="font-mono font-bold text-brand-700 text-[11px]">03 · Rule 12 USP</span>
              <p className="text-slate-700 font-medium leading-relaxed">{t.step3}</p>
            </div>
          </div>

          {/* Action Button */}
          <div className="pt-2 flex flex-col sm:flex-row items-stretch sm:items-center justify-center gap-3">
            <button
              type="button"
              onClick={onStartScan}
              className="inline-flex items-center justify-center gap-2 px-6 py-3.5 rounded-2xl bg-gradient-to-r from-saffron-500 via-saffron-600 to-orange-600 hover:from-saffron-600 hover:to-orange-700 text-white font-bold text-xs shadow-md shadow-saffron-500/20 transition active:scale-95 touch-manipulation cursor-pointer"
            >
              <Camera className="h-4 w-4 text-white" />
              <span>{t.startScan}</span>
            </button>
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center justify-center gap-2 px-5 py-3.5 rounded-2xl border-2 border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-bold text-xs transition active:scale-95 touch-manipulation cursor-pointer"
            >
              <span>{t.returnHome}</span>
            </button>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 py-4 text-center text-xs text-slate-500">
        Legal Metrology Statutory Compliance Platform · Register Management
      </footer>
    </div>
  );
}
