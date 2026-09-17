import { useState, useEffect } from "react";
import {
  ShieldCheck,
  FileText,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  Lock,
  Layers,
  Download,
  Camera,
  ChevronRight,
  Scale,
  Users,
  Globe,
} from "lucide-react";

interface LandingPageProps {
  onStartScan: () => void;
  onOfficerLogin: () => void;
  onConsumerPortal: () => void;
}

export function LandingPage({
  onStartScan,
  onOfficerLogin,
  onConsumerPortal,
}: LandingPageProps) {
  const [activeStage, setActiveStage] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setActiveStage((prev) => (prev + 1) % 4);
    }, 2800);
    return () => clearInterval(timer);
  }, []);

  const stages = [
    { title: "Multi-Panel Image Ingestion", sub: "Parallel 6-Angle High-Resolution Capture", color: "text-saffron-600" },
    { title: "Computer Vision & OCR Vectorization", sub: "PaddleOCR + Homography Rectification", color: "text-brand-800" },
    { title: "LMPC Statutory Rule Engine", sub: "Legal Metrology Rules 2011 + Rule 12 Unit Pricing", color: "text-govgreen" },
    { title: "Verified PDF Inspection Report", sub: "Tamper-Proof Audit Docket Export", color: "text-saffron-600" },
  ];

  return (
    <div className="min-h-screen bg-white text-slate-900 flex flex-col justify-between selection:bg-saffron-500 selection:text-white">
      {/* Top Navigation Bar with Tricolor Ribbon & Crisp White Navbar */}
      <header className="border-b border-slate-200 bg-white text-slate-900 sticky top-0 z-50 shadow-xs">
        <div className="h-1.5 w-full tricolor-stripe" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
          {/* Left Corner Logo */}
          <div className="flex items-center gap-3.5">
            <div className="rounded-2xl bg-white p-1.5 shadow-sm border border-slate-200 ring-1 ring-slate-100">
              <img
                src="/dca-logo.png"
                alt="Department of Consumer Affairs, Govt of India"
                className="h-10 w-auto object-contain max-w-[140px] sm:max-w-[190px]"
              />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-black tracking-widest text-slate-900">LEXMETRA</span>
                <span className="bg-saffron-50 border border-saffron-200 text-saffron-700 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider">
                  STATUTORY AI
                </span>
                <span className="bg-emerald-50 border border-emerald-200 text-govgreen text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider hidden sm:inline">
                  DCA VERIFIED
                </span>
              </div>
              <p className="text-[11px] font-semibold text-slate-500 tracking-wider uppercase">
                Department of Consumer Affairs · Govt of India
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onConsumerPortal}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold text-slate-800 bg-white hover:bg-slate-50 border-2 border-slate-300 transition-all shadow-xs"
            >
              <Users className="h-4 w-4 text-govgreen" />
              Citizen Portal
            </button>
            <button
              onClick={onOfficerLogin}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-saffron-500 to-orange-600 hover:from-saffron-600 hover:to-orange-700 text-white border border-saffron-500 shadow-sm transition-all"
            >
              <Lock className="h-3.5 w-3.5 text-white" />
              Officer Sign In
            </button>
          </div>
        </div>
      </header>

      {/* Main Hero Section on Crisp Pure White */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16 grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center flex-1 bg-white">
        {/* Left Column: Punchline & Value Proposition */}
        <div className="lg:col-span-7 space-y-7">
          <div className="inline-flex items-center gap-2.5 px-3.5 py-1.5 rounded-full bg-purple-50 border border-purple-200 text-brand-900 text-xs font-bold shadow-xs">
            <Sparkles className="h-4 w-4 text-saffron-600 animate-pulse" />
            <span>Ministry of Consumer Affairs · Legal Metrology Division</span>
          </div>

          <div className="space-y-4">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-brand-950 leading-[1.14]">
              Instant Legal Metrology Compliance &{" "}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-saffron-600 via-brand-700 to-govgreen">
                Automated Inspection
              </span>
            </h1>
            <p className="text-base sm:text-lg text-slate-700 leading-relaxed max-w-2xl font-normal">
              Empowering enforcement officers and consumers with computer-vision verification under the{" "}
              <strong className="text-brand-900 font-bold">Legal Metrology Act 2009</strong> &{" "}
              <strong className="text-govgreen font-bold">LMPC Rules 2011</strong>. Multi-panel 6-face scanning, real-time bounding-box vectorization, and deterministic compliance verdicts.
            </p>
          </div>

          {/* Action CTAs */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 pt-2">
            <button
              onClick={onStartScan}
              className="inline-flex items-center justify-center gap-3 px-7 py-4 rounded-2xl bg-gradient-to-r from-saffron-500 via-saffron-600 to-orange-600 hover:from-saffron-600 hover:to-orange-700 text-white font-bold text-base shadow-lg shadow-saffron-500/25 transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <Camera className="h-5 w-5 text-white" />
              <span>Start Package Inspection</span>
              <ArrowRight className="h-5 w-5" />
            </button>
            <button
              onClick={onOfficerLogin}
              className="inline-flex items-center justify-center gap-2 px-6 py-4 rounded-2xl bg-brand-900 hover:bg-brand-950 text-white font-bold text-sm border-2 border-purple-300 transition-all shadow-sm"
            >
              <Globe className="h-4 w-4 text-saffron-400" />
              <span>Officer & Authority Portal</span>
              <ChevronRight className="h-4 w-4 text-purple-200" />
            </button>
          </div>

          {/* Capabilities Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-6 border-t border-purple-100">
            <div className="p-4 rounded-2xl bg-white border-2 border-purple-200/80 hover:border-brand-500 transition-colors shadow-xs">
              <div className="h-9 w-9 rounded-xl bg-purple-50 text-brand-800 flex items-center justify-center mb-3">
                <Layers className="h-5 w-5" />
              </div>
              <p className="text-xs font-bold text-brand-950 uppercase tracking-wider">6-Face 360° Scan</p>
              <p className="text-xs text-slate-600 mt-1">Multi-angle panel capture with homography perspective rectification.</p>
            </div>

            <div className="p-4 rounded-2xl bg-white border-2 border-emerald-200/80 hover:border-govgreen transition-colors shadow-xs">
              <div className="h-9 w-9 rounded-xl bg-emerald-50 text-govgreen flex items-center justify-center mb-3">
                <Scale className="h-5 w-5" />
              </div>
              <p className="text-xs font-bold text-govgreen uppercase tracking-wider">Rule 12 Unit Pricing</p>
              <p className="text-xs text-slate-600 mt-1">Mathematical MRP/USP cross-verification with 0% error tolerance.</p>
            </div>

            <div className="p-4 rounded-2xl bg-white border-2 border-saffron-200/80 hover:border-saffron-500 transition-colors shadow-xs">
              <div className="h-9 w-9 rounded-xl bg-saffron-50 text-saffron-600 flex items-center justify-center mb-3">
                <FileText className="h-5 w-5" />
              </div>
              <p className="text-xs font-bold text-saffron-700 uppercase tracking-wider">Official PDF Docket</p>
              <p className="text-xs text-slate-600 mt-1">Standardized statutory audit report export with evidence maps.</p>
            </div>
          </div>
        </div>

        {/* Right Column: Live Interactive Simulation & Scanner Animation on White */}
        <div className="lg:col-span-5 relative">
          <div className="relative rounded-3xl border-2 border-purple-200/90 bg-white p-6 shadow-xl shadow-purple-900/10 overflow-hidden">
            <div className="h-1.5 w-full tricolor-stripe mb-4 rounded-full" />
            
            {/* Header Stage Indicator */}
            <div className="flex items-center justify-between border-b border-purple-100 pb-3 mb-4">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-saffron-600">
                  REAL-TIME PERCEPTION PIPELINE
                </p>
                <p className="text-sm font-bold text-brand-950 mt-0.5">
                  Stage {activeStage + 1} of 4: {stages[activeStage].title}
                </p>
              </div>
              <div className="flex gap-1.5">
                {[0, 1, 2, 3].map((idx) => (
                  <button
                    key={idx}
                    onClick={() => setActiveStage(idx)}
                    className={`h-2.5 rounded-full transition-all ${
                      activeStage === idx ? "w-6 bg-saffron-500 shadow-xs" : "w-2.5 bg-purple-100"
                    }`}
                  />
                ))}
              </div>
            </div>

            {/* Stage Title */}
            <div className="mb-3">
              <p className="text-xs font-semibold text-slate-600">{stages[activeStage].sub}</p>
            </div>

            {/* Simulated Scanner Viewport on Pure White */}
            <div className="relative aspect-[4/3] rounded-2xl bg-slate-50 border-2 border-purple-100 overflow-hidden flex items-center justify-center p-4">
              {/* Grid Background */}
              <div className="absolute inset-0 bg-[linear-gradient(to_right,#e2e8f0_1px,transparent_1px),linear-gradient(to_bottom,#e2e8f0_1px,transparent_1px)] bg-[size:16px_16px]" />

              {/* Package Mock Representation */}
              <div className="relative w-44 h-56 rounded-xl bg-white border-2 border-purple-200 shadow-lg flex flex-col justify-between p-3.5 z-10">
                {/* Brand & Top Header */}
                <div className="flex items-center justify-between border-b border-purple-100 pb-2">
                  <span className="text-[10px] font-extrabold tracking-widest text-brand-900">PREMIUM COFFEE</span>
                  <span className="text-[8px] bg-purple-50 text-brand-800 border border-purple-200 px-1.5 py-0.5 rounded font-bold">150g</span>
                </div>

                {/* Simulated Bounding Box 1: MRP */}
                <div className={`p-1.5 rounded border-2 transition-all duration-300 ${activeStage >= 1 ? "border-brand-600 bg-purple-50/80 shadow-sm" : "border-slate-200"}`}>
                  <div className="flex items-center justify-between text-[9px]">
                    <span className="text-slate-800 font-mono font-bold">MRP: ₹420.00</span>
                    {activeStage >= 1 && <span className="text-brand-700 font-bold text-[8px]">99% CONF</span>}
                  </div>
                  <div className="text-[8px] text-govgreen font-mono font-semibold">USP: ₹2.80/g (Valid)</div>
                </div>

                {/* Simulated Bounding Box 2: Mfg Date & Batch */}
                <div className={`p-1.5 rounded border-2 transition-all duration-300 ${activeStage >= 1 ? "border-govgreen bg-emerald-50/80 shadow-sm" : "border-slate-200"}`}>
                  <div className="flex items-center justify-between text-[9px]">
                    <span className="text-slate-800 font-mono font-bold">MFG: 08/2026</span>
                    {activeStage >= 1 && <span className="text-govgreen font-bold text-[8px]">Rule 6(1)(d) PASS</span>}
                  </div>
                </div>

                {/* Simulated Bounding Box 3: Consumer Care */}
                <div className={`p-1.5 rounded border-2 transition-all duration-300 ${activeStage >= 2 ? "border-saffron-500 bg-saffron-50/80" : "border-slate-200"}`}>
                  <div className="text-[8px] text-slate-800 truncate font-mono font-semibold">Care: 1800-11-4000</div>
                </div>
              </div>

              {/* Laser Scanning Beam */}
              {activeStage === 0 || activeStage === 1 ? (
                <div className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-saffron-500 to-transparent shadow-[0_0_12px_#ea580c] animate-[scanLaser_2.4s_ease-in-out_infinite] z-20 pointer-events-none" />
              ) : null}

              {/* Interactive Floating Status Overlay */}
              {activeStage >= 2 && (
                <div className="absolute bottom-3 inset-x-3 bg-white/95 border-2 border-govgreen rounded-xl p-2.5 flex items-center justify-between z-30 shadow-lg backdrop-blur-md">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-govgreen" />
                    <div>
                      <p className="text-[11px] font-bold text-govgreen">LMPC COMPLIANT (100%)</p>
                      <p className="text-[9px] text-slate-600">All 6 Mandatory Declarations Verified</p>
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
            <div className="mt-4 pt-3 border-t border-purple-100 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <FileText className="h-4 w-4 text-brand-800" />
                <span className="text-xs text-brand-950 font-bold">Exportable PDF Audit Docket</span>
              </div>
              <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-saffron-600 hover:text-saffron-700 cursor-pointer">
                <Download className="h-3.5 w-3.5" />
                ReportLab Engine Ready
              </span>
            </div>
          </div>
        </div>
      </main>

      {/* Footer on Crisp White */}
      <footer className="border-t border-purple-200/80 bg-purple-50/40 py-6 text-center text-xs text-slate-600">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="font-medium">© 2026 LexMetra · Department of Consumer Affairs, Government of India</p>
          <div className="flex items-center gap-4 font-semibold text-brand-900">
            <span>LM Act 2009</span>
            <span className="text-saffron-500">•</span>
            <span>LMPC Rules 2011</span>
            <span className="text-govgreen">•</span>
            <span>Rule 12 Unit Pricing</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
