import { useState } from "react";
import {
  Camera,
  CheckCircle2,
  ChevronRight,
  Package,
  ShoppingBag,
  ArrowLeft,
  AlertTriangle,
  PhoneCall,
  Sparkles,
  Calculator,
  Lock,
  FileCheck2,
  ExternalLink,
  X,
  Send,
} from "lucide-react";
import { type Inspection } from "@/lib/types";
import { type Language } from "@/lib/i18n";
import { LexMetraLogo } from "./InspectionApp";

interface CustomerDashboardProps {
  inspections?: Inspection[];
  onStartScan?: () => void;
  onOpenInspection?: (inspection: Inspection) => void;
  onOfficerLogin?: () => void;
  onBack?: () => void;
  lang?: Language;
  onLanguageChange?: (l: Language) => void;
}

export function CustomerDashboard({
  inspections = [],
  onStartScan = () => {},
  onOpenInspection = () => {},
  onOfficerLogin = () => {},
  onBack,
  lang = "en",
  onLanguageChange,
}: CustomerDashboardProps) {
  const [activeTab, setActiveTab] = useState<"MY_SCANS" | "CHECK_PRICE" | "CONSUMER_RIGHTS">("MY_SCANS");
  const [grievanceModalItem, setGrievanceModalItem] = useState<Inspection | null>(null);
  const [grievanceSubmitted, setGrievanceSubmitted] = useState(false);
  const [retailerName, setRetailerName] = useState("");
  const [priceCharged, setPriceCharged] = useState("");
  const [complaintText, setComplaintText] = useState("");

  // Price Calculator state
  const [calcMrp, setCalcMrp] = useState<string>("150");
  const [calcQty, setCalcQty] = useState<string>("200");
  const [calcUnit, setCalcUnit] = useState<string>("g");

  const calcRate =
    parseFloat(calcMrp) > 0 && parseFloat(calcQty) > 0
      ? (parseFloat(calcMrp) / parseFloat(calcQty)).toFixed(2)
      : "0.00";

  const consumerScans = inspections.slice(0, 10);

  function handleFileGrievance(e: React.FormEvent) {
    e.preventDefault();
    setGrievanceSubmitted(true);
    setTimeout(() => {
      setGrievanceSubmitted(false);
      setGrievanceModalItem(null);
      setRetailerName("");
      setPriceCharged("");
      setComplaintText("");
    }, 2500);
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {/* Official Consumer Suvidha Header */}
      <header className="sticky top-0 z-30 border-b border-purple-900/40 bg-gradient-to-r from-brand-950 via-brand-900 to-purple-950 text-white shadow-md">
        <div className="h-1.5 w-full tricolor-stripe" />
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3.5">
            {onBack && (
              <button
                type="button"
                onClick={onBack}
                aria-label="Back to Home"
                className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10 text-white hover:bg-white/20 transition"
              >
                <ArrowLeft className="h-5 w-5" />
              </button>
            )}
            <div className="flex items-center justify-center rounded-2xl bg-white p-1 sm:p-1.5 shadow-sm ring-1 ring-purple-300/30">
              <LexMetraLogo className="h-7 sm:h-9 w-auto max-w-[130px] sm:max-w-[180px]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-black tracking-widest text-white">CONSUMER SUVIDHA</span>
                <span className="rounded-full bg-saffron-500/30 border border-saffron-400/50 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider text-saffron-300">
                  Jago Grahak Jago
                </span>
              </div>
              <p className="text-[10px] font-semibold text-purple-200 tracking-wider uppercase">
                Citizen Package Verification & Consumer Rights Portal · Dept. of Consumer Affairs
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Language Switcher */}
            {onLanguageChange && (
              <div className="inline-flex rounded-lg border border-purple-400/30 bg-purple-950/60 p-0.5 text-xs font-semibold shadow-inner">
                <button
                  type="button"
                  onClick={() => onLanguageChange("en")}
                  className={`rounded-md px-2.5 py-1 transition text-xs ${
                    lang === "en" ? "bg-purple-600 text-white font-bold shadow-xs" : "text-purple-200 hover:text-white"
                  }`}
                >
                  English
                </button>
                <button
                  type="button"
                  onClick={() => onLanguageChange("hi")}
                  className={`rounded-md px-2.5 py-1 transition text-xs ${
                    lang === "hi" ? "bg-purple-600 text-white font-bold shadow-xs" : "text-purple-200 hover:text-white"
                  }`}
                >
                  हिन्दी
                </button>
                <button
                  type="button"
                  onClick={() => onLanguageChange("mr")}
                  className={`rounded-md px-2.5 py-1 transition text-xs ${
                    lang === "mr" ? "bg-purple-600 text-white font-bold shadow-xs" : "text-purple-200 hover:text-white"
                  }`}
                >
                  मराठी
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={onOfficerLogin}
              className="hidden sm:inline-flex items-center gap-1.5 rounded-xl bg-white/10 px-3.5 py-2 text-xs font-bold text-white border border-white/20 hover:bg-white/20 transition shadow-xs"
            >
              <Lock className="h-3.5 w-3.5 text-saffron-300" />
              Officer Sign In
            </button>
          </div>
        </div>
      </header>

      {/* Main Citizen Workbench */}
      <main className="mx-auto max-w-6xl space-y-7 px-4 pb-28 pt-7 sm:px-6 md:pb-12 lg:px-8">
        {/* Hero Banner: Direct Scan Action */}
        <section className="relative overflow-hidden rounded-3xl border-2 border-purple-200 bg-gradient-to-br from-white via-purple-50/40 to-amber-50/30 p-6 sm:p-9 shadow-md">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
            <div className="max-w-2xl space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full bg-purple-100 border border-purple-300 px-3 py-1 text-xs font-bold text-purple-900">
                <Sparkles className="h-3.5 w-3.5 text-saffron-600" />
                <span>Zero-Cost Official Package Protection for Every Citizen</span>
              </div>
              <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-slate-900">
                Verify MRP, Expiry & Net Weight Before You Pay.
              </h1>
              <p className="text-xs sm:text-sm text-slate-600 leading-relaxed font-medium">
                Snap a photo of any grocery, packaged food, medicine, or beverage package. Our Legal Metrology screening checks if you are being overcharged, whether the expiry date is valid, and lets you file a 1-click complaint to the National Consumer Helpline (1915).
              </p>

              {/* 4 Consumer Protection Check Chips */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
                <div className="rounded-xl border border-slate-200 bg-white p-2.5 text-center shadow-xs">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Fair Price</span>
                  <p className="text-xs font-extrabold text-purple-900 mt-0.5">MRP Verification</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-2.5 text-center shadow-xs">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Freshness</span>
                  <p className="text-xs font-extrabold text-emerald-800 mt-0.5">Expiry / Best Before</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-2.5 text-center shadow-xs">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Exact Quantity</span>
                  <p className="text-xs font-extrabold text-blue-900 mt-0.5">Declared Net Weight</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-2.5 text-center shadow-xs">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Food Safety</span>
                  <p className="text-xs font-extrabold text-orange-900 mt-0.5">14-Digit FSSAI Lic</p>
                </div>
              </div>
            </div>

            {/* Big Primary Scan Button */}
            <div className="flex flex-col sm:flex-row lg:flex-col items-center gap-3 shrink-0">
              <button
                type="button"
                onClick={onStartScan}
                className="w-full sm:w-auto inline-flex h-14 items-center justify-center gap-3 rounded-2xl bg-gradient-to-r from-purple-800 via-purple-700 to-indigo-800 px-8 text-base font-black text-white shadow-xl shadow-purple-700/25 hover:from-purple-900 hover:to-indigo-900 active:scale-95 transition-all"
              >
                <Camera className="h-6 w-6 text-saffron-300" />
                <span>Scan Package Photo</span>
              </button>
              <span className="text-[11px] font-bold text-slate-500 text-center">
                Supports up to 6 angles (Front PDP, Back & Sides)
              </span>
            </div>
          </div>
        </section>

        {/* Consumer Portal Navigation Tabs */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
          <div className="inline-flex rounded-xl bg-slate-200/80 p-1 text-xs font-bold">
            <button
              type="button"
              onClick={() => setActiveTab("MY_SCANS")}
              className={`rounded-lg px-4 py-2 transition ${
                activeTab === "MY_SCANS"
                  ? "bg-white text-purple-950 shadow-sm font-extrabold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              My Scanned Products ({consumerScans.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("CHECK_PRICE")}
              className={`rounded-lg px-4 py-2 transition ${
                activeTab === "CHECK_PRICE"
                  ? "bg-white text-purple-950 shadow-sm font-extrabold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Unit Price Calculator
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("CONSUMER_RIGHTS")}
              className={`rounded-lg px-4 py-2 transition ${
                activeTab === "CONSUMER_RIGHTS"
                  ? "bg-white text-purple-950 shadow-sm font-extrabold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Jago Grahak Jago & Helpline 1915
            </button>
          </div>

          <div className="inline-flex items-center gap-2 text-xs font-semibold text-slate-600">
            <PhoneCall className="h-4 w-4 text-govgreen" />
            <span>National Consumer Toll-Free: </span>
            <span className="font-extrabold text-slate-900 text-sm">1915</span>
          </div>
        </div>

        {/* Tab 1: Scanned Products */}
        {activeTab === "MY_SCANS" && (
          <div className="space-y-4">
            {consumerScans.length === 0 ? (
              <div className="rounded-3xl border-2 border-dashed border-slate-300 bg-white p-12 text-center shadow-xs">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-purple-50 text-purple-700 mb-4">
                  <ShoppingBag className="h-7 w-7" />
                </div>
                <h3 className="text-base font-bold text-slate-900">No scanned packages in your history</h3>
                <p className="mx-auto mt-1 max-w-md text-xs sm:text-sm text-slate-500 font-medium">
                  Scan any packaged commodity from your grocery shopping, local bakery, or online delivery to verify statutory compliance.
                </p>
                <button
                  type="button"
                  onClick={onStartScan}
                  className="mt-5 inline-flex items-center gap-2 rounded-xl bg-purple-700 px-5 py-2.5 text-xs font-bold text-white shadow-md hover:bg-purple-800 transition"
                >
                  <Camera className="h-4 w-4" /> Start Your First Scan
                </button>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {consumerScans.map((item) => {
                  const isViolation = item.status === "VIOLATION";
                  return (
                    <div
                      key={item.id}
                      className="rounded-2xl border border-slate-200 bg-white p-4 transition-all hover:border-purple-300 hover:shadow-md flex flex-col justify-between gap-3.5"
                    >
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-mono text-[10px] text-slate-400 font-semibold">#{item.id}</span>
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${
                              !isViolation
                                ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                                : "bg-red-50 text-red-800 border border-red-200"
                            }`}
                          >
                            {!isViolation ? "✓ Genuine & Fair Price" : "⚠ Non-Compliant / Violation"}
                          </span>
                        </div>

                        <div className="flex items-start gap-3">
                          <div className="h-16 w-14 shrink-0 overflow-hidden rounded-xl bg-slate-100 border border-slate-200">
                            {item.image ? (
                              <img src={item.image} alt={item.product} className="h-full w-full object-cover" />
                            ) : (
                              <div className="flex h-full w-full items-center justify-center text-slate-400">
                                <Package className="h-6 w-6" />
                              </div>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <h3 className="text-sm font-bold text-slate-900 truncate">{item.product}</h3>
                            <p className="text-xs text-slate-500 font-medium truncate mt-0.5">
                              {item.manufacturer || "Manufacturer on Label"}
                            </p>
                            <p className="text-[11px] text-slate-600 mt-1 line-clamp-2">
                              {item.summary}
                            </p>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center justify-between pt-3 border-t border-slate-100">
                        <button
                          type="button"
                          onClick={() => onOpenInspection(item)}
                          className="text-xs font-bold text-purple-700 hover:text-purple-900 inline-flex items-center gap-1"
                        >
                          View Full Details <ChevronRight className="h-3.5 w-3.5" />
                        </button>
                        {isViolation && (
                          <button
                            type="button"
                            onClick={() => setGrievanceModalItem(item)}
                            className="rounded-lg bg-red-600 hover:bg-red-700 px-3 py-1.5 text-[11px] font-bold text-white shadow-xs transition"
                          >
                            File Grievance
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Unit Price Calculator */}
        {activeTab === "CHECK_PRICE" && (
          <section className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm space-y-6">
            <div>
              <div className="inline-flex items-center gap-2 text-xs font-bold text-purple-700 uppercase tracking-wider">
                <Calculator className="h-4 w-4" />
                <span>Unit Sale Price (USP) Rule 6(11) Verification</span>
              </div>
              <h2 className="mt-1 text-xl font-bold text-slate-900">
                Are you getting fair value? Calculate exact price per gram or milliliter.
              </h2>
              <p className="mt-1 text-xs sm:text-sm text-slate-600 font-medium">
                Under Legal Metrology Rules, manufacturers must declare the Unit Sale Price (₹ per g / per ml) so consumers can easily compare pack sizes.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="text-xs font-bold text-slate-700 block">Total MRP (₹)</label>
                <div className="relative mt-1">
                  <span className="absolute left-3 top-2.5 text-slate-400 font-bold">₹</span>
                  <input
                    type="number"
                    value={calcMrp}
                    onChange={(e) => setCalcMrp(e.target.value)}
                    className="h-11 w-full rounded-xl border border-slate-300 bg-slate-50 pl-7 pr-3 text-sm font-bold text-slate-900 outline-none focus:border-purple-600 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-bold text-slate-700 block">Net Quantity Value</label>
                <input
                  type="number"
                  value={calcQty}
                  onChange={(e) => setCalcQty(e.target.value)}
                  className="mt-1 h-11 w-full rounded-xl border border-slate-300 bg-slate-50 px-3 text-sm font-bold text-slate-900 outline-none focus:border-purple-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="text-xs font-bold text-slate-700 block">Unit of Measure</label>
                <select
                  value={calcUnit}
                  onChange={(e) => setCalcUnit(e.target.value)}
                  className="mt-1 h-11 w-full rounded-xl border border-slate-300 bg-slate-50 px-3 text-sm font-bold text-slate-900 outline-none focus:border-purple-600 focus:bg-white"
                >
                  <option value="g">Grams (g)</option>
                  <option value="kg">Kilograms (kg)</option>
                  <option value="ml">Milliliters (ml)</option>
                  <option value="l">Liters (L)</option>
                  <option value="number">Per Unit / Piece (N)</option>
                </select>
              </div>
            </div>

            <div className="rounded-2xl bg-purple-50 border border-purple-200 p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-purple-900">Calculated Unit Sale Price</p>
                <p className="text-2xl sm:text-3xl font-black text-purple-950 mt-0.5">
                  ₹{calcRate} <span className="text-sm font-bold text-purple-800">per {calcUnit}</span>
                </p>
              </div>
              <p className="text-xs text-slate-600 max-w-sm">
                Check this rate against competitor brands or smaller/larger packs to ensure you are not paying an inflated markup.
              </p>
            </div>
          </section>
        )}

        {/* Tab 3: Jago Grahak Jago & National Consumer Helpline */}
        {activeTab === "CONSUMER_RIGHTS" && (
          <section className="space-y-6">
            {/* National Helpline Hotline Banner */}
            <div className="rounded-3xl border border-emerald-300 bg-emerald-50/80 p-6 sm:p-8 shadow-xs">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="space-y-1">
                  <span className="rounded-full bg-emerald-200 text-emerald-900 px-3 py-0.5 text-[10px] font-extrabold uppercase tracking-wider">
                    Government of India Official Grievance Channel
                  </span>
                  <h3 className="text-xl font-bold text-emerald-950">National Consumer Helpline (NCH 1915)</h3>
                  <p className="text-xs text-emerald-800 font-medium">
                    Facing overcharging above MRP, short weight, altered expiry date, or defective goods? Reach consumer grievance officers directly.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2.5">
                  <a
                    href="tel:1915"
                    className="inline-flex items-center gap-2 rounded-xl bg-govgreen px-4 py-2.5 text-xs font-extrabold text-white shadow hover:bg-emerald-800 transition"
                  >
                    <PhoneCall className="h-4 w-4" /> Call 1915 Toll-Free
                  </a>
                  <a
                    href="https://consumerhelpline.gov.in"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-xl bg-white border border-emerald-400 px-4 py-2.5 text-xs font-bold text-emerald-900 hover:bg-emerald-50 transition"
                  >
                    <ExternalLink className="h-4 w-4" /> consumerhelpline.gov.in
                  </a>
                </div>
              </div>
            </div>

            {/* 3 Core Consumer Rights under LMPC 2011 */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-2">
                <div className="h-9 w-9 rounded-xl bg-purple-100 text-purple-800 flex items-center justify-center font-bold">
                  §1
                </div>
                <h4 className="text-sm font-bold text-slate-900">Right Against Overcharging (MRP)</h4>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  Selling above the declared Maximum Retail Price (MRP) printed on the package is a cognizable offence under Section 36(1) of the Legal Metrology Act, 2009.
                </p>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-2">
                <div className="h-9 w-9 rounded-xl bg-purple-100 text-purple-800 flex items-center justify-center font-bold">
                  §2
                </div>
                <h4 className="text-sm font-bold text-slate-900">Prohibition of Dual MRP</h4>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  It is illegal for a manufacturer to print different MRPs for identical products for different locations (e.g. airport/cinema vs general retail stores).
                </p>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-2">
                <div className="h-9 w-9 rounded-xl bg-purple-100 text-purple-800 flex items-center justify-center font-bold">
                  §3
                </div>
                <h4 className="text-sm font-bold text-slate-900">Mandatory Customer Care Details</h4>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  Every packaged commodity must visibly declare the name, full address, email, and telephone number of the consumer grievance officer on the label.
                </p>
              </div>
            </div>
          </section>
        )}
      </main>

      {/* Consumer Grievance Modal */}
      {grievanceModalItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl border border-slate-200 animate-in fade-in zoom-in duration-150">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-red-100 text-red-700">
                  <AlertTriangle className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">File Consumer Grievance (NCH 1915)</h3>
                  <p className="text-[10px] text-slate-500">Auto-filled statutory evidence for enforcement notice</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setGrievanceModalItem(null)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {grievanceSubmitted ? (
              <div className="py-8 text-center space-y-2">
                <CheckCircle2 className="h-12 w-12 text-govgreen mx-auto" />
                <h4 className="text-base font-bold text-slate-900">Grievance Docket Generated!</h4>
                <p className="text-xs text-slate-600">
                  Docket reference #NCH-{Math.floor(100000 + Math.random() * 900000)} has been submitted with image evidence to the Department of Consumer Affairs surveillance cell.
                </p>
              </div>
            ) : (
              <form onSubmit={handleFileGrievance} className="mt-4 space-y-3.5 text-xs font-semibold">
                <div>
                  <label className="text-slate-700 block mb-1">Product Being Reported</label>
                  <input
                    readOnly
                    value={grievanceModalItem.product}
                    className="h-9 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-slate-800 font-bold"
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-slate-700 block mb-1">Store / Retailer Name</label>
                    <input
                      required
                      placeholder="e.g. City Supermarket / QuickCommerce"
                      value={retailerName}
                      onChange={(e) => setRetailerName(e.target.value)}
                      className="h-9 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-purple-600"
                    />
                  </div>
                  <div>
                    <label className="text-slate-700 block mb-1">Price Charged to You (₹)</label>
                    <input
                      type="number"
                      placeholder="e.g. 500"
                      value={priceCharged}
                      onChange={(e) => setPriceCharged(e.target.value)}
                      className="h-9 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-purple-600"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-slate-700 block mb-1">Description of Violation</label>
                  <textarea
                    rows={3}
                    placeholder="e.g. Store charged ₹50 extra above MRP / Expiry date label was pasted over with a sticker."
                    value={complaintText}
                    onChange={(e) => setComplaintText(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 p-2.5 outline-none focus:border-purple-600 text-xs font-normal"
                  />
                </div>

                <div className="rounded-xl bg-purple-50 border border-purple-200 p-3 text-[11px] text-purple-900 flex items-center gap-2">
                  <FileCheck2 className="h-4 w-4 shrink-0 text-purple-700" />
                  <span>The package scan photo & detected label evidence will be automatically attached.</span>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setGrievanceModalItem(null)}
                    className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="inline-flex items-center gap-1.5 rounded-xl bg-red-600 hover:bg-red-700 px-5 py-2 text-xs font-bold text-white shadow transition"
                  >
                    <Send className="h-3.5 w-3.5" /> Submit to DCA & 1915
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
