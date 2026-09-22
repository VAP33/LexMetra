import { useEffect, useRef, useState } from "react";
import {
  Camera,
  ShieldCheck,
  CheckCircle2,
  FileText,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Check,
  Scale,
  Sparkles,
  Layers,
  Lock,
  Download,
  Globe,
  Search,
  Menu,
} from "lucide-react";
import { MobileMenuDrawer } from "./mobile-menu-drawer";

interface LandingPageProps {
  onStartScan: () => void;
  onOfficerLogin: () => void;
  onConsumerPortal?: () => void;
  onOpenPrivacy?: () => void;
  onOpenTerms?: () => void;
  onOpenRegulatory?: () => void;
  lang?: "en" | "hi" | "mr";
  onLanguageChange?: (l: "en" | "hi" | "mr") => void;
}

export function LandingPage({
  onStartScan,
  onOfficerLogin,
  onConsumerPortal,
  onOpenPrivacy,
  onOpenTerms,
  onOpenRegulatory,
  lang = "en",
  onLanguageChange,
}: LandingPageProps) {
  const [isLangOpen, setIsLangOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [showStickyCta, setShowStickyCta] = useState(false);
  const langMenuRef = useRef<HTMLDivElement>(null);
  const [activeStage, setActiveStage] = useState(0);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (langMenuRef.current && !langMenuRef.current.contains(event.target as Node)) {
        setIsLangOpen(false);
      }
    }
    if (isLangOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isLangOpen]);

  // Auto-cycle through the 4 perception pipeline stages smoothly
  useEffect(() => {
    const timer = setInterval(() => {
      setActiveStage((prev) => (prev + 1) % 4);
    }, 4200);
    return () => clearInterval(timer);
  }, []);

  const stages = [
    {
      title: "6-Face Synchronized Capture",
      sub: "Homography Surface Normalization & Perspective Rectification",
      badge: "Stage 01 · Computer Vision",
    },
    {
      title: "Fast OCR & Polygon Localization",
      sub: "Sub-Second Text Vectorization & Strict Bounding Box Isolation",
      badge: "Stage 02 · Perception Pipeline",
    },
    {
      title: "LMPC Deterministic Rule Engine",
      sub: "Rule 12 Unit Sale Price Math & Rule 6(1) Declarations Verification",
      badge: "Stage 03 · Statutory Engine",
    },
    {
      title: "Tamper-Proof Audit Docket Export",
      sub: "ReportLab Official PDF Certificate & Evidence Audit Trail",
      badge: "Stage 04 · Enforcement Action",
    },
  ];

  const t = {
    en: {
      directorate: "Legal Metrology Compliance · Statutory Packaged Commodities Authority",
      titleMain: "Automated Legal Metrology",
      titleHighlight: "Compliance & Enforcement",
      subtitle:
        "AI-powered multi-surface inspection under the Legal Metrology Act, 2009 & Packaged Commodities Rules, 2011. Instant mathematical unit-price validation, deterministic statutory compliance, and tamper-proof PDF audit dockets.",
      startScan: "Start Package Inspection",
      officerPortal: "Officer Command Center",
      citizenPortal: "Citizen Grievance & Search",
      cap1Title: "360° Multi-Panel Scan",
      cap1Desc: "Full-package unobserved evaluation preventing false absences across 6 surfaces.",
      cap2Title: "Rule 12 Unit Sale Price",
      cap2Desc: "Deterministic arithmetic cross-check of MRP vs Net Qty with 0% tolerance.",
      cap3Title: "Official Audit PDF",
      cap3Desc: "Tamper-proof dockets with localized bounding-box crops and court-admissible proof.",
      footerCopy: "© 2026 LexMetra · Automated Statutory Compliance Platform",
    },
    hi: {
      directorate: "विधिक मापविज्ञान प्रभाग · वैधानिक पैकेज्ड कमोडिटीज प्राधिकरण",
      titleMain: "स्वचालित विधिक मापविज्ञान",
      titleHighlight: "अनुपालन एवं प्रवर्तन",
      subtitle:
        "विधिक मापविज्ञान अधिनियम, 2009 एवं पैकेज्ड कमोडिटीज नियम, 2011 के अंतर्गत बहु-सतह एआई निरीक्षण। तत्काल इकाई मूल्य सत्यापन और आधिकारिक पीडीएफ डॉकेट।",
      startScan: "पैकेज निरीक्षण शुरू करें",
      officerPortal: "अधिकारी पोर्टल",
      citizenPortal: "नागरिक शिकायत पोर्टल",
      cap1Title: "360° बहु-सतह स्कैन",
      cap1Desc: "पैकेज की सभी 6 सतहों पर अनिवार्य घोषणाओं का समग्र सत्यापन।",
      cap2Title: "नियम 12 इकाई विक्रय मूल्य",
      cap2Desc: "एमआरपी और शुद्ध मात्रा का सटीक गणितीय सत्यापन।",
      cap3Title: "आधिकारिक पीडीएफ डॉकेट",
      cap3Desc: "साक्ष्य मानचित्र एवं विधिक रिपोर्ट के साथ निर्यात योग्य डॉकेट।",
      footerCopy: "© 2026 लेक्समेट्रा · स्वचालित वैधानिक अनुपालन प्रणाली",
    },
    mr: {
      directorate: "कायदेशीर मापनशास्त्र विभाग · वैधानिक पॅकेज्ड कमोडिटीज प्राधिकरण",
      titleMain: "स्वयंचलित कायदेशीर मापनशास्त्र",
      titleHighlight: "अनुपालन व अंमलबजावणी",
      subtitle:
        "कायदेशीर मापनशास्त्र कायदा, २००९ व पॅकेज्ड कमोडिटीज नियम, २०११ अंतर्गत एआय बहु-पृष्ठभाग तपासणी आणि अधिकृत पीडीएफ अहवाल.",
      startScan: "पॅकेज तपासणी सुरू करा",
      officerPortal: "अधिकारी पोर्टल",
      citizenPortal: "नागरिक पोर्टल",
      cap1Title: "360° बहु-पृष्ठभाग स्कॅन",
      cap1Desc: "संपूर्ण पॅकेजवरील 6 पृष्ठांवर अनिवार्य घोषणांची अचूक पडताळणी.",
      cap2Title: "नियम 12 युनिट विक्री किंमत",
      cap2Desc: "एमआरपी आणि निव्वळ प्रमाण यांचे तंतोतंत गणितीय परीक्षण.",
      cap3Title: "अधिकृत पीडीएफ डॉकेट",
      cap3Desc: "पुरावे नकाशे व पुराव्यासह न्यायालयीन मान्य अहवाल.",
      footerCopy: "© 2026 लेक्समेट्रा · स्वयंचलित वैधानिक अनुपालन प्रणाली",
    },
  }[lang] || {
    directorate: "Legal Metrology Division · Statutory Compliance Platform",
    titleMain: "Automated Legal Metrology",
    titleHighlight: "Compliance & Enforcement",
    subtitle: "AI-powered statutory package inspection platform.",
    startScan: "Start Package Inspection",
    officerPortal: "Officer Portal",
    citizenPortal: "Citizen Portal",
    cap1Title: "360° Multi-Panel Scan",
    cap1Desc: "Multi-angle surface analysis preventing false absence.",
    cap2Title: "Rule 12 Unit Sale Price",
    cap2Desc: "Deterministic arithmetic cross-check with 0% error tolerance.",
    cap3Title: "Official Audit PDF",
    cap3Desc: "Tamper-proof legal dockets with localized bounding-box crops.",
    footerCopy: "© 2026 LexMetra · Automated Statutory Compliance Platform",
  };

  // Scroll listener for sticky mobile CTA
  useEffect(() => {
    const handleScroll = () => {
      setShowStickyCta(window.scrollY > 240);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <div className="min-h-screen bg-white text-slate-900 flex flex-col justify-between selection:bg-saffron-500 selection:text-white overflow-x-hidden no-horizontal-scroll">
      {/* Mobile Slide-Out Drawer Navigation */}
      <MobileMenuDrawer
        isOpen={isMobileMenuOpen}
        onClose={() => setIsMobileMenuOpen(false)}
        currentView="landing"
        onNavigate={(view) => {
          if (view === "scan") onStartScan();
          else if (view === "login") onOfficerLogin();
          else if (view === "customer") onConsumerPortal?.();
          else if (view === "privacy") onOpenPrivacy?.();
          else if (view === "terms") onOpenTerms?.();
          else if (view === "regulatory") onOpenRegulatory?.();
          else if (view === "landing") window.scrollTo({ top: 0, behavior: "smooth" });
        }}
        lang={lang}
        onLanguageChange={onLanguageChange}
      />

      {/* 1. Header with Dark Blue Background and White Logo */}
      <header className="border-b border-brand-900/60 bg-gradient-to-r from-brand-950 via-brand-900 to-brand-800 text-white sticky top-0 z-40 shadow-md">
        <div className="h-1.5 w-full tricolor-stripe" />
        <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 min-h-[64px] sm:min-h-[76px] py-2 flex items-center justify-between gap-2 sm:gap-4">
          {/* White Logo on Dark Blue Background */}
          <div className="flex items-center gap-2 sm:gap-4 shrink-0">
            <button
              type="button"
              onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
              className="flex items-center gap-2 sm:gap-3 transition-opacity hover:opacity-90 active:scale-[0.98] touch-manipulation cursor-pointer text-left"
              aria-label="LexMetra Home"
            >
              <img
                src="/lexmetra-white-logo.png"
                alt="LexMetra National Statutory Compliance Logo"
                className="h-9 sm:h-12 w-auto object-contain drop-shadow-[0_2px_8px_rgba(255,255,255,0.2)]"
                draggable={false}
              />
              <div className="hidden sm:flex flex-col">
                <span className="text-base sm:text-lg font-black tracking-wider text-white font-mono leading-none">
                  LEXMETRA
                </span>
                <span className="text-[10px] sm:text-[11px] font-medium text-slate-300 leading-tight mt-0.5">
                  Legal Metrology Compliance &amp; Inspection Platform
                </span>
              </div>
            </button>
          </div>

          {/* Right Action Tools: Language Menu & Sign In & Mobile Menu Toggle */}
          <div className="flex items-center gap-1.5 sm:gap-3 shrink-0">
            {/* Multilingual Selector */}
            {onLanguageChange && (
              <div className="relative" ref={langMenuRef}>
                <button
                  type="button"
                  aria-label="Select Language"
                  onClick={() => setIsLangOpen((prev) => !prev)}
                  className="flex items-center gap-1.5 rounded-xl border border-white/20 bg-white/10 px-2.5 sm:px-3 py-1.5 text-xs font-bold text-white shadow-xs backdrop-blur-xs transition hover:bg-white/20 active:scale-95 touch-manipulation cursor-pointer"
                >
                  <Globe className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-saffron-300" />
                  <span className="text-xs uppercase tracking-wide">
                    {lang === "hi" ? "हिन्दी" : lang === "mr" ? "मराठी" : "EN"}
                  </span>
                  <ChevronDown
                    className={`h-3 w-3 text-brand-200 transition-transform ${isLangOpen ? "rotate-180" : ""}`}
                  />
                </button>

                {isLangOpen && (
                  <div className="absolute right-0 mt-2 w-44 rounded-2xl border border-slate-200 bg-white p-1.5 text-slate-800 shadow-2xl z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                    <div className="px-2.5 py-1.5 border-b border-slate-100 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      {lang === "hi" ? "भाषा चुनें" : lang === "mr" ? "भाषा निवडा" : "Select Language"}
                    </div>
                    <div className="py-1 space-y-0.5">
                      {[
                        { code: "en", label: "English", sub: "National Standard" },
                        { code: "hi", label: "हिन्दी", sub: "Hindi" },
                        { code: "mr", label: "मराठी", sub: "Marathi" },
                      ].map((opt) => {
                        const isActive = lang === opt.code;
                        return (
                          <button
                            key={opt.code}
                            type="button"
                            onClick={() => {
                              onLanguageChange(opt.code as "en" | "hi" | "mr");
                              setIsLangOpen(false);
                            }}
                            className={`flex w-full items-center justify-between rounded-xl px-2.5 py-2 text-xs transition touch-manipulation cursor-pointer ${
                              isActive
                                ? "bg-purple-50 text-purple-900 font-bold"
                                : "text-slate-700 hover:bg-slate-100 font-medium"
                            }`}
                          >
                            <div className="flex flex-col text-left">
                              <span>{opt.label}</span>
                              <span className="text-[10px] text-slate-400">{opt.sub}</span>
                            </div>
                            {isActive && <Check className="h-4 w-4 text-purple-700" />}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Officer Sign In Button */}
            <button
              type="button"
              id="officer-login-btn"
              aria-label="Officer Sign In"
              onClick={onOfficerLogin}
              className="inline-flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-purple-700 via-purple-800 to-indigo-800 hover:from-purple-800 hover:to-indigo-900 text-white shadow-md transition-all active:scale-95 touch-manipulation cursor-pointer"
            >
              <Lock className="h-3.5 w-3.5 text-white" />
              <span className="hidden sm:inline">{lang === "hi" ? "साइन इन" : lang === "mr" ? "साइन इन करा" : "Sign In"}</span>
              <span className="sm:hidden">Sign In</span>
            </button>

            {/* Mobile Hamburger Drawer Button */}
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen(true)}
              aria-label="Open mobile navigation menu"
              className="md:hidden flex h-9 w-9 items-center justify-center rounded-xl bg-white/10 text-white hover:bg-white/20 transition active:scale-95 touch-manipulation cursor-pointer"
            >
              <Menu className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>

      {/* 2. Main Hero Section on Crisp Pure White (Optimized Above-the-Fold for Mobile) */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 sm:py-10 lg:py-16 grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center flex-1 bg-white">
        {/* Left Column: Punchline & Value Proposition */}
        <div className="lg:col-span-7 space-y-4 sm:space-y-6">
          {/* Directorate Badge */}
          <div className="inline-flex items-center gap-2 px-3 sm:px-3.5 py-1 sm:py-1.5 rounded-full bg-brand-50 border border-brand-200 text-brand-900 text-[11px] sm:text-xs font-bold shadow-xs">
            <Sparkles className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-saffron-600 animate-pulse" />
            <span className="truncate max-w-[260px] sm:max-w-none">{t.directorate}</span>
          </div>

          {/* Heading */}
          <div className="space-y-2.5 sm:space-y-4">
            <h1 className="text-2xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-brand-950 leading-[1.15]">
              {t.titleMain} <br className="hidden sm:inline" />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-saffron-600 via-brand-700 to-govgreen">
                {t.titleHighlight}
              </span>
            </h1>
            <p className="text-xs sm:text-base lg:text-lg text-slate-700 leading-relaxed font-normal max-w-2xl">
              {t.subtitle}
            </p>
          </div>

          {/* Action CTAs (Mobile Stacked, Desktop Side-by-Side) */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4 pt-2">
            <button
              onClick={onStartScan}
              className="inline-flex items-center justify-center gap-3 px-6 sm:px-8 py-4 rounded-2xl bg-gradient-to-r from-saffron-500 via-saffron-600 to-orange-600 hover:from-saffron-600 hover:to-orange-700 text-white font-bold text-base shadow-lg shadow-saffron-500/25 transition-all hover:scale-[1.02] active:scale-[0.98] min-h-[52px] touch-manipulation cursor-pointer"
            >
              <Camera className="h-5 w-5 text-white" />
              <span>{t.startScan}</span>
              <ArrowRight className="h-5 w-5" />
            </button>

            <button
              onClick={onOfficerLogin}
              className="inline-flex items-center justify-center gap-2 px-5 sm:px-6 py-4 rounded-2xl bg-brand-900 hover:bg-brand-950 text-white font-bold text-sm border-2 border-brand-300 transition-all shadow-sm min-h-[52px] touch-manipulation cursor-pointer"
            >
              <Globe className="h-4 w-4 text-saffron-400" />
              <span>{t.officerPortal}</span>
              <ChevronRight className="h-4 w-4 text-brand-200" />
            </button>

            {onConsumerPortal && (
              <button
                onClick={onConsumerPortal}
                className="inline-flex items-center justify-center gap-2 px-4 py-4 rounded-2xl bg-white hover:bg-slate-50 text-slate-700 hover:text-slate-900 font-semibold text-xs border border-slate-300 transition-all shadow-xs min-h-[52px] touch-manipulation cursor-pointer"
              >
                <Search className="h-3.5 w-3.5 text-saffron-600" />
                <span>{t.citizenPortal}</span>
              </button>
            )}
          </div>
        </div>

        {/* Right Column: Live Interactive Simulation & Scanner Animation on White */}
        <div className="lg:col-span-5 relative w-full">
          <div className="relative rounded-3xl border-2 border-slate-200 bg-white p-5 sm:p-6 shadow-xl shadow-brand-900/10 overflow-hidden">
            <div className="h-1.5 w-full tricolor-stripe mb-4 rounded-full" />

            {/* Header Stage Indicator with Blue Logo on White */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
              <div className="flex items-center gap-3">
                <img
                  src="/lexmetra-blue-logo.png"
                  alt="LexMetra Blue Logo"
                  className="h-9 w-auto object-contain"
                  draggable={false}
                />
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-saffron-600 font-mono">
                    {stages[activeStage].badge}
                  </p>
                  <p className="text-xs sm:text-sm font-bold text-brand-950 mt-0.5">
                    {stages[activeStage].title}
                  </p>
                </div>
              </div>

              {/* Stage Indicators */}
              <div className="flex gap-1.5">
                {[0, 1, 2, 3].map((idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setActiveStage(idx)}
                    aria-label={`Switch to Stage ${idx + 1}`}
                    className={`h-2.5 rounded-full transition-all touch-manipulation cursor-pointer ${
                      activeStage === idx ? "w-6 bg-saffron-500 shadow-xs" : "w-2.5 bg-slate-200"
                    }`}
                  />
                ))}
              </div>
            </div>

            {/* Stage Title */}
            <p className="text-xs font-semibold text-slate-600 mb-3 min-h-[32px] line-clamp-2">
              {stages[activeStage].sub}
            </p>

            {/* Simulated Scanner Viewport on Pure White */}
            <div className="relative aspect-[4/3] rounded-2xl bg-slate-50 border-2 border-slate-100 overflow-hidden flex items-center justify-center p-4">
              {/* Grid Background */}
              <div className="absolute inset-0 bg-[linear-gradient(to_right,#e2e8f0_1px,transparent_1px),linear-gradient(to_bottom,#e2e8f0_1px,transparent_1px)] bg-[size:16px_16px]" />

              {/* Package Mock Representation */}
              <div className="relative w-44 sm:w-48 h-56 rounded-xl bg-white border-2 border-slate-200 shadow-lg flex flex-col justify-between p-3.5 z-10">
                {/* Brand & Top Header */}
                <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                  <span className="text-[10px] font-extrabold tracking-widest text-brand-900">
                    CHOCOLATE SYRUP
                  </span>
                  <span className="text-[8px] bg-brand-50 text-brand-800 border border-brand-200 px-1.5 py-0.5 rounded font-mono font-bold">
                    180 g
                  </span>
                </div>

                {/* Simulated Bounding Box 1: MRP */}
                <div
                  className={`p-1.5 rounded border-2 transition-all duration-300 ${
                    activeStage >= 1
                      ? "border-brand bg-brand-50/80 shadow-sm"
                      : "border-slate-200"
                  }`}
                >
                  <div className="flex items-center justify-between text-[9px]">
                    <span className="text-slate-800 font-mono font-bold">MRP: ₹99.00</span>
                    {activeStage >= 1 && (
                      <span className="text-brand-700 font-bold text-[8px]">99% CONF</span>
                    )}
                  </div>
                  <div className="text-[8px] text-govgreen font-mono font-semibold">
                    USP: ₹0.55/g (Rule 12 Valid)
                  </div>
                </div>

                {/* Simulated Bounding Box 2: FSSAI / Mfg Date */}
                <div
                  className={`p-1.5 rounded border-2 transition-all duration-300 ${
                    activeStage >= 1
                      ? "border-govgreen bg-emerald-50/80 shadow-sm"
                      : "border-slate-200"
                  }`}
                >
                  <div className="flex items-center justify-between text-[9px]">
                    <span className="text-slate-800 font-mono font-bold">FSSAI: 10012022000295</span>
                    {activeStage >= 1 && (
                      <span className="text-govgreen font-bold text-[8px]">PASS</span>
                    )}
                  </div>
                </div>

                {/* Simulated Bounding Box 3: Consumer Care */}
                <div
                  className={`p-1.5 rounded border-2 transition-all duration-300 ${
                    activeStage >= 2
                      ? "border-saffron-500 bg-saffron-50/80"
                      : "border-slate-200"
                  }`}
                >
                  <div className="text-[8px] text-slate-800 truncate font-mono font-semibold">
                    Care: 1800-425-4444
                  </div>
                </div>
              </div>

              {/* Laser Scanning Beam */}
              {activeStage === 0 || activeStage === 1 ? (
                <div className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-saffron-500 to-transparent shadow-[0_0_12px_#ea580c] animate-[scanLaser_2.4s_ease-in-out_infinite] z-20 pointer-events-none" />
              ) : null}

              {/* Interactive Floating Status Overlay */}
              {activeStage >= 2 && (
                <div className="absolute bottom-3 inset-x-3 bg-white/95 border-2 border-govgreen rounded-xl p-2.5 flex items-center justify-between z-30 shadow-lg backdrop-blur-md animate-in fade-in slide-in-from-bottom-2 duration-200">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-govgreen shrink-0" />
                    <div>
                      <p className="text-[11px] font-bold text-govgreen">100% LMPC COMPLIANT</p>
                      <p className="text-[9px] text-slate-600">All 13 Statutory Declarations Verified</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 bg-govgreen text-white px-2 py-1 rounded-lg text-[10px] font-bold shadow-xs">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    PASSED
                  </div>
                </div>
              )}
            </div>

            {/* Bottom PDF Export Simulation */}
            <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5 font-semibold text-brand-950">
                <FileText className="h-4 w-4 text-brand-800" />
                <span>Exportable PDF Audit Docket</span>
              </div>
              <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-saffron-600 hover:text-saffron-700 touch-manipulation cursor-pointer">
                <Download className="h-3.5 w-3.5" />
                ReportLab Engine Ready
              </span>
            </div>
          </div>
        </div>
      </main>

      {/* 3. Capabilities Grid on Pure White */}
      <section className="border-t border-slate-200 bg-slate-50/60 py-10 sm:py-14">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-8 sm:mb-10 space-y-2">
            <p className="text-xs font-bold uppercase tracking-widest text-saffron-600">
              Deterministic Statutory Architecture
            </p>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-brand-950">
              Engineered for Real-World Field Enforcement
            </h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
            <div className="p-5 sm:p-6 rounded-2xl bg-white border-2 border-slate-200/90 hover:border-brand-500 transition-all shadow-xs group">
              <div className="h-10 w-10 rounded-xl bg-brand-50 text-brand-800 flex items-center justify-center mb-4 group-hover:scale-110 transition">
                <Layers className="h-5 w-5" />
              </div>
              <h3 className="text-sm sm:text-base font-bold text-brand-950 mb-1.5">
                {t.cap1Title}
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                {t.cap1Desc}
              </p>
            </div>

            <div className="p-5 sm:p-6 rounded-2xl bg-white border-2 border-emerald-200/80 hover:border-govgreen transition-all shadow-xs group">
              <div className="h-10 w-10 rounded-xl bg-emerald-50 text-govgreen flex items-center justify-center mb-4 group-hover:scale-110 transition">
                <Scale className="h-5 w-5" />
              </div>
              <h3 className="text-sm sm:text-base font-bold text-govgreen mb-1.5">
                {t.cap2Title}
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                {t.cap2Desc}
              </p>
            </div>

            <div className="p-5 sm:p-6 rounded-2xl bg-white border-2 border-saffron-200/80 hover:border-saffron-500 transition-all shadow-xs group">
              <div className="h-10 w-10 rounded-xl bg-saffron-50 text-saffron-600 flex items-center justify-center mb-4 group-hover:scale-110 transition">
                <FileText className="h-5 w-5" />
              </div>
              <h3 className="text-sm sm:text-base font-bold text-saffron-700 mb-1.5">
                {t.cap3Title}
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                {t.cap3Desc}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 4. Footer on Crisp White */}
      <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-600 mb-16 sm:mb-0">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="font-medium">{t.footerCopy}</p>
          <div className="flex flex-wrap items-center justify-center gap-2.5 sm:gap-4 font-semibold text-brand-900 text-[11px] sm:text-xs">
            <button
              type="button"
              onClick={onOpenRegulatory}
              className="hover:text-saffron-600 hover:underline transition cursor-pointer"
            >
              LM Act 2009
            </button>
            <span className="text-saffron-500">•</span>
            <button
              type="button"
              onClick={onOpenRegulatory}
              className="hover:text-saffron-600 hover:underline transition cursor-pointer"
            >
              LMPC Rules 2011
            </button>
            <span className="text-govgreen">•</span>
            <button
              type="button"
              onClick={onOpenRegulatory}
              className="hover:text-saffron-600 hover:underline transition cursor-pointer"
            >
              Rule 12 Unit Pricing
            </button>
            <span className="text-slate-300">•</span>
            <button
              type="button"
              onClick={onOpenPrivacy}
              className="hover:text-saffron-600 hover:underline transition cursor-pointer"
            >
              Privacy Policy
            </button>
            <span className="text-slate-300">•</span>
            <button
              type="button"
              onClick={onOpenTerms}
              className="hover:text-saffron-600 hover:underline transition cursor-pointer"
            >
              Terms of Service
            </button>
          </div>
        </div>
      </footer>

      {/* Sticky Mobile CTA Bar (Slides in when user scrolls down on mobile) */}
      <div
        className={`sticky-mobile-cta flex items-center justify-between gap-3 md:hidden transition-transform duration-300 ${
          showStickyCta ? "translate-y-0 opacity-100" : "translate-y-full opacity-0 pointer-events-none"
        }`}
      >
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-xl bg-saffron-50 border border-saffron-200 flex items-center justify-center text-saffron-600 shrink-0">
            <Camera className="h-4 w-4" />
          </div>
          <div className="text-left">
            <p className="text-xs font-black text-brand-950">6-Face Inspection</p>
            <p className="text-[10px] text-slate-500 font-medium">Verify Rule 12 USP Math</p>
          </div>
        </div>

        <button
          type="button"
          onClick={onStartScan}
          className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-gradient-to-r from-saffron-500 via-saffron-600 to-orange-600 hover:from-saffron-600 hover:to-orange-700 text-white font-bold text-xs shadow-md shadow-saffron-500/25 active:scale-95 touch-manipulation cursor-pointer shrink-0"
        >
          <span>{t.startScan}</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
