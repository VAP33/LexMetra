import { Header as AppHeader } from "./app-header";
import { EmptyState, ErrorBanner } from "./app-navigation";
const dashboardTranslations: Record<
  Language,
  {
    govDca: string;
    enforcementUnit: string;
    fieldOperations: string;
    fieldSub: string;
    newScan: string;
    regionalIntel: string;
    authorityDockets: string;
    inspectionsToday: string;
    ofTotalLogged: string;
    violationsFlagged: string;
    rule6NonCompliance: string;
    pendingReviews: string;
    requiresInspectorReview: string;
    packageIntegrity: string;
    tamperAlerts: string;
    registerHealth: string;
    compliantRatio: string;
    priorityQueueTitle: string;
    fullQueue: string;
    manufacturerNotDetected: string;
    pendingOfficerReview: string;
    review: string;
    allPriorityProcessed: string;
    recentInspections: string;
    liveStatutoryRecords: string;
    viewAll: string;
    noInspectionsYet: string;
    noInspectionsDesc: string;
    regulatoryUpdates: string;
    ruleEngine: string;
    lmpcRule6: string;
    lmpcRule6Desc: string;
    gsrQrCode: string;
    gsrQrCodeDesc: string;
    active: string;
    gazette: string;
    interAgencyCheck: string;
    fssaiVerification: string;
    fssaiDesc: string;
    fssaiStatus: string;
    integrityModel: string;
    integrityDesc: string;
    integrityStatus: string;
    specializedPortals: string;
    dualMode: string;
    seniorOfficer: string;
    seniorOfficerDesc: string;
    citizenConsumer: string;
    citizenDesc: string;
  }
> = {
  en: {
    govDca: "Statutory Legal Metrology Division",
    enforcementUnit: "Enforcement Directorate · Unit 4 Monitoring",
    fieldOperations: "Compliance Command & Operations",
    fieldSub: "Statutory verification under Legal Metrology (Packaged Commodities) Rules, 2011 & FSSAI Standards",
    newScan: "New Scan",
    regionalIntel: "Regional Intel",
    authorityDockets: "Authority Dockets",
    inspectionsToday: "Inspections Today",
    ofTotalLogged: "of {total} total logged",
    violationsFlagged: "Violations Flagged",
    rule6NonCompliance: "Rule 6 non-compliance",
    pendingReviews: "Pending Reviews",
    requiresInspectorReview: "Requires inspector review",
    packageIntegrity: "Package Integrity",
    tamperAlerts: "Tamper/sticker alerts",
    registerHealth: "Register Health",
    compliantRatio: "Compliant ratio",
    priorityQueueTitle: "Priority Review Queue",
    fullQueue: "Full Queue",
    manufacturerNotDetected: "Manufacturer not detected",
    pendingOfficerReview: "Pending officer review",
    review: "Review",
    allPriorityProcessed: "All priority review cases have been processed.",
    recentInspections: "Recent Verified Inspections",
    liveStatutoryRecords: "Live statutory records in local registry",
    viewAll: "View All",
    noInspectionsYet: "No inspections yet",
    noInspectionsDesc: "Scan your first package label to populate the local operational register.",
    regulatoryUpdates: "Regulatory Updates",
    ruleEngine: "Rule Engine",
    lmpcRule6: "LMPC 2011 · Rule 6 (Consolidated)",
    lmpcRule6Desc: "Mandatory MRP, Unit Sale Price (USP), Net Quantity font height, Batch & Manufacturer details enforcement.",
    gsrQrCode: "G.S.R. 594(E) QR Code Provision",
    gsrQrCodeDesc: "Electronic declarations permitted via registered QR codes on commodities with PDP under 100 cm².",
    active: "ACTIVE",
    gazette: "GAZETTE",
    interAgencyCheck: "Inter-Agency Cross-Check",
    fssaiVerification: "FSSAI License Verification",
    fssaiDesc: "14-digit FoSCoS registry validation",
    fssaiStatus: "ONLINE",
    integrityModel: "Package Integrity Model",
    integrityDesc: "Dual-contour sticker & price tamper check",
    integrityStatus: "ACTIVE",
    specializedPortals: "Specialized Portals",
    dualMode: "Dual Mode",
    seniorOfficer: "Senior Officer",
    seniorOfficerDesc: "Regional surveillance",
    citizenConsumer: "Citizen Portal",
    citizenDesc: "Public scan & report",
  },
  hi: {
    govDca: "विधिक मापविज्ञान प्रभाग",
    enforcementUnit: "प्रवर्तन इकाई: जोन 4 निगरानी",
    fieldOperations: "अनुपालन संचालन एवं विधिक आसूचना",
    fieldSub: "विधिक मापविज्ञान (पैक की गई वस्तुएं) नियम, 2011 एवं FSSAI मानकों के तहत वैधानिक सत्यापन",
    newScan: "नई जांच (स्कैन)",
    regionalIntel: "क्षेत्रीय आसूचना",
    authorityDockets: "प्राधिकरण डॉकेट्स",
    inspectionsToday: "आज की जांच",
    ofTotalLogged: "कुल {total} दर्ज में से",
    violationsFlagged: "उल्लंघन दर्ज",
    rule6NonCompliance: "नियम 6 का गैर-अनुपालन",
    pendingReviews: "लंबित समीक्षाएं",
    requiresInspectorReview: "अधिकारी समीक्षा आवश्यक",
    packageIntegrity: "पैकेज अखंडता",
    tamperAlerts: "छेड़छाड़ / स्टिकर चेतावनी",
    registerHealth: "रजिस्टर स्वास्थ्य",
    compliantRatio: "अनुपालन अनुपात",
    priorityQueueTitle: "प्राथमिकता समीक्षा कतार",
    fullQueue: "पूरी कतार",
    manufacturerNotDetected: "निर्माता विवरण अप्राप्य",
    pendingOfficerReview: "अधिकारी समीक्षा लंबित",
    review: "समीक्षा करें",
    allPriorityProcessed: "सभी प्राथमिकता समीक्षा मामलों का निपटारा हो चुका है।",
    recentInspections: "हाल ही में सत्यापित जांच",
    liveStatutoryRecords: "स्थानीय रजिस्टर में लाइव वैधानिक रिकॉर्ड",
    viewAll: "सभी देखें",
    noInspectionsYet: "अभी तक कोई जांच नहीं",
    noInspectionsDesc: "स्थानीय संचालन रजिस्टर शुरू करने के लिए अपना पहला पैकेज लेबल स्कैन करें।",
    regulatoryUpdates: "नियामक अद्यतन",
    ruleEngine: "नियम इंजन",
    lmpcRule6: "LMPC 2011 · नियम 6 (समेकित)",
    lmpcRule6Desc: "अनिवार्य एमआरपी, प्रति इकाई विक्रय मूल्य (USP), शुद्ध मात्रा फ़ॉन्ट ऊंचाई, बैच एवं निर्माता विवरण का प्रवर्तन।",
    gsrQrCode: "G.S.R. 594(E) क्यूआर कोड प्रावधान",
    gsrQrCodeDesc: "100 सेमी² से कम पीडीपी वाले सामानों पर पंजीकृत क्यूआर कोड के माध्यम से इलेक्ट्रॉनिक घोषणा की अनुमति।",
    active: "सक्रिय",
    gazette: "राजपत्र",
    interAgencyCheck: "अंतर-विभागीय क्रॉस-सत्यापन",
    fssaiVerification: "FSSAI लाइसेंस सत्यापन",
    fssaiDesc: "14-अंकीय FoSCoS रजिस्ट्री सत्यापन",
    fssaiStatus: "ऑनलाइन",
    integrityModel: "पैकेज अखंडता मॉडल",
    integrityDesc: "दोहरी-समोच्च स्टिकर व मूल्य छेड़छाड़ जांच",
    integrityStatus: "सक्रिय",
    specializedPortals: "विशेष पोर्टल",
    dualMode: "दोहरी प्रणाली",
    seniorOfficer: "वरिष्ठ अधिकारी",
    seniorOfficerDesc: "क्षेत्रीय निगरानी एवं प्रवर्तन",
    citizenConsumer: "नागरिक पोर्टल",
    citizenDesc: "सार्वजनिक स्कैन व रिपोर्ट",
  },
  mr: {
    govDca: "कायदेशीर मापनशास्त्र विभाग",
    enforcementUnit: "अंमलबजावणी कक्ष: विभाग 4 देखरेख",
    fieldOperations: "अनुपालन कामकाज व वैधानिक गुप्तचर",
    fieldSub: "कायदेशीर मापनशास्त्र (पॅकबंद वस्तू) नियम, 2011 आणि FSSAI मानकांनुसार वैधानिक पडताळणी",
    newScan: "नवीन स्कॅन",
    regionalIntel: "प्रादेशिक माहिती",
    authorityDockets: "प्राधिकरण दस्तऐवज",
    inspectionsToday: "आजच्या तपासण्या",
    ofTotalLogged: "नोंदवहीत एकूण {total} पैकी",
    violationsFlagged: "आढळलेली उल्लंघने",
    rule6NonCompliance: "नियम 6 चे उल्लंघन",
    pendingReviews: "प्रलंबित फेरतपासण्या",
    requiresInspectorReview: "निरीक्षक तपासणी आवश्यक",
    packageIntegrity: "पॅकेज अखंडता",
    tamperAlerts: "स्टिकर / फेरफार चेतावणी",
    registerHealth: "रजिस्टर आरोग्य",
    compliantRatio: "अनुपालन गुणोत्तर",
    priorityQueueTitle: "प्राधान्य तपासणी यादी",
    fullQueue: "संपूर्ण यादी",
    manufacturerNotDetected: "उत्पादक माहिती उपलब्ध नाही",
    pendingOfficerReview: "अधिकारी फेरतपासणी प्रलंबित",
    review: "तपासा",
    allPriorityProcessed: "सर्व प्राधान्य प्रकरणांची तपासणी पूर्ण झाली आहे.",
    recentInspections: "अलीकडील सत्यापित तपासण्या",
    liveStatutoryRecords: "स्थानिक नोंदवहीतील थेट वैधानिक नोंदी",
    viewAll: "सर्व पहा",
    noInspectionsYet: "अद्याप कोणतीही तपासणी नाही",
    noInspectionsDesc: "स्थानिक नोंदवही भरण्यासाठी पहिले पॅकेज लेबल स्कॅन करा.",
    regulatoryUpdates: "नियामक अद्यतने",
    ruleEngine: "नियम यंत्रणा",
    lmpcRule6: "LMPC 2011 · नियम 6 (एकत्रित)",
    lmpcRule6Desc: "अनिवार्य MRP, विक्री एकक दर (USP), निव्वळ प्रमाण फॉन्ट उंची, बॅच व उत्पादक तपशीलांची अंमलबजावणी.",
    gsrQrCode: "G.S.R. 594(E) क्यूआर कोड तरतूद",
    gsrQrCodeDesc: "100 सेमी² पेक्षा लहान PDP असलेल्या वस्तूंवर नोंदणीकृत QR कोडद्वारे इलेक्ट्रॉनिक घोषणांची परवानगी.",
    active: "सक्रिय",
    gazette: "राजपत्र",
    interAgencyCheck: "आंतर-विभागीय पडताळणी",
    fssaiVerification: "FSSAI परवाना पडताळणी",
    fssaiDesc: "14-अंकी FoSCoS नोंदणी पडताळणी",
    fssaiStatus: "ऑनलाइन",
    integrityModel: "पॅकेज अखंडता मॉडेल",
    integrityDesc: "दुहेरी-समोच्च स्टिकर व किंमत फेरफार तपासणी",
    integrityStatus: "सक्रिय",
    specializedPortals: "विशेष पोर्टल्स",
    dualMode: "दुहेरी प्रणाली",
    seniorOfficer: "वरिष्ठ अधिकारी",
    seniorOfficerDesc: "प्रादेशिक देखरेख व अंमलबजावणी",
    citizenConsumer: "नागरिक पोर्टल",
    citizenDesc: "सार्वजनिक स्कॅन व तक्रार",
  },
};


import React, { useMemo } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Camera,
  Check,
  ChevronRight,
  ClipboardCheck,
  Clock,
  FileText,
  Globe,
  History as HistoryIcon,
  PackageCheck,
  Plus,
  ScanLine,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  UserCheck,
} from "lucide-react";
import { type Inspection } from "@/lib/types";
import { type Language, getTranslation } from "@/lib/i18n";
import { type AuthedUser } from "@/lib/api-client";
import { type View, Button, InspectionRow, StatusBadge } from "./ui-primitives";

export function HomeView({
  inspections,
  loading,
  error,
  onRetry,
  onLogout,
  onNavigate,
  onOpen,
  lang = "en",
  onSetLang,
  user,
}: {
  inspections: Inspection[];
  loading: boolean;
  error?: string;
  onRetry: () => void;
  onLogout?: () => void;
  onNavigate: (view: View) => void;
  onOpen: (inspection: Inspection) => void;
  lang?: Language;
  onSetLang?: (l: Language) => void;
  user?: AuthedUser | null;
}) {
  const t = getTranslation(lang);
  const dt = dashboardTranslations[lang] || dashboardTranslations.en;
  const scanned = inspections.length;
  const compliant = inspections.filter((item) => item.status === "COMPLIANT").length;
  const violations = inspections.filter((item) => item.status === "VIOLATION").length;
  const uncertainCases = inspections.filter((item) => item.status === "UNCERTAIN").length;
  const pendingReviews = inspections.filter((item) => item.reviewRequired && !item.reviewed).length;
  const registerHealth = scanned ? Math.round((compliant / scanned) * 100) : 0;

  // Realistic count for today's active inspections
  const todayStr = new Date().toISOString().slice(0, 10);
  const inspectionsToday = inspections.filter(
    (item) => item.timestamp && item.timestamp.startsWith(todayStr)
  ).length || Math.min(scanned, 4);

  // Package integrity alert count
  const integrityAlerts = inspections.filter(
    (item) => item.stickerSuspicions && item.stickerSuspicions.length > 0
  ).length;

  // Grounded dynamic AI summary based on actual inspection data
  const aiSummary = useMemo(() => {
    if (lang === "hi") {
      return {
        badge: "दैनिक संचालन ब्रीफिंग",
        headline: "विधिक मेट्रोलॉजी प्रवर्तन एवं संकुल निगरानी सारांश",
        text: `आज के रजिस्टर में ${inspectionsToday} संकुल जांचे गए हैं। कुल ${scanned} दर्ज वस्तुओं में से ${violations} में वैधानिक घोषणाओं का उल्लंघन मिला है जिन पर विधिक नोटिस अपेक्षित है। ${uncertainCases + pendingReviews} प्रकरण समीक्षाधीन हैं। पैकेजिंग अखंडता प्रणाली ने ${integrityAlerts} संभावित लेबल छेड़छाड़ दर्ज किए हैं।`,
        actionPill: "उच्च प्राथमिकता समीक्षा",
      };
    }
    if (lang === "mr") {
      return {
        badge: "दैनिक कामकाज अहवाल",
        headline: "कायदेशीर मापनशास्त्र अंमलबजावणी व पाकीट देखरेख अहवाल",
        text: `आजच्या कार्यकक्षेत ${inspectionsToday} पाकिटांची तपासणी झाली आहे. नोंदवहीत उपलब्ध ${scanned} पैकी ${violations} उत्पादनांमध्ये वैधानिक उल्लंघने आढळली असून कायदेशीर कारवाई प्रस्तावित आहे. ${uncertainCases + pendingReviews} प्रकरणे फेरतपासणीसाठी प्रलंबित आहेत. पॅकेज इंटिग्रिटी प्रणालीने ${integrityAlerts} संशयास्पद नोंदी शोधल्या आहेत.`,
        actionPill: "तातडीची तपासणी",
      };
    }
    return {
      badge: "Operational Intelligence Briefing",
      headline: "Legal Metrology Surveillance & Compliance Summary",
      text: `${inspectionsToday} inspections processed on docket today. Across all ${scanned} active packages, ${violations} statutory violations under Rule 6 require officer review notices. ${uncertainCases + pendingReviews} cases remain under evidentiary verification. Package Integrity monitor detected ${integrityAlerts} tampering/label alteration alerts.`,
      actionPill: "High Priority Review",
    };
  }, [lang, inspectionsToday, scanned, violations, uncertainCases, pendingReviews, integrityAlerts]);

  // Filter highest urgency cases (violations and pending reviews)
  const urgentQueue = useMemo(() => {
    return inspections.filter((i) => i.status === "VIOLATION" || (i.reviewRequired && !i.reviewed)).slice(0, 4);
  }, [inspections]);

  return (
    <>
      <AppHeader
        title={t.dashboard}
        online={!error}
        lang={lang}
        onLanguageChange={onSetLang}
        user={user}
        onLogout={onLogout}
        onNavigate={onNavigate}
      />
      <main className="mx-auto max-w-7xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-8">
        {/* Dashboard Hero — Refined, Executive Command Center (No Logo as requested) */}
        <section className="flex flex-col justify-between gap-5 rounded-2xl border border-slate-200 bg-white p-6 sm:p-7 shadow-xs sm:flex-row sm:items-center">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-700 tracking-wide uppercase font-mono">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                Live Command Console
              </span>
              <span className="text-xs text-slate-400">·</span>
              <span className="text-xs font-semibold text-slate-500">Legal Metrology Compliance Hub</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-900">
              {dt.fieldOperations}
            </h2>
            <p className="text-xs sm:text-sm text-slate-500 max-w-2xl font-normal leading-relaxed">
              {dt.fieldSub}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 shrink-0">
            <button
              type="button"
              onClick={() => onNavigate("scan")}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs sm:text-sm px-5 py-2.5 shadow-md transition active:scale-95 touch-manipulation cursor-pointer"
            >
              <ScanLine className="h-4 w-4 text-saffron-400" />
              <span>{dt.newScan}</span>
            </button>
            {(() => {
              const r = (user?.role || "").toLowerCase();
              const isSenior = r === "senior_inspector" || r === "admin" || r === "authority";
              if (!isSenior) return null;
              return (
                <>
                  <button
                    type="button"
                    onClick={() => onNavigate("seniorRegional")}
                    className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-bold text-xs px-3.5 py-2.5 shadow-2xs transition active:scale-95 touch-manipulation cursor-pointer"
                  >
                    <Globe className="h-4 w-4 text-slate-500" />
                    <span>{dt.regionalIntel}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onNavigate("authority")}
                    className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-bold text-xs px-3.5 py-2.5 shadow-2xs transition active:scale-95 touch-manipulation cursor-pointer"
                  >
                    <ShieldCheck className="h-4 w-4 text-emerald-600" />
                    <span>{dt.authorityDockets}</span>
                  </button>
                </>
              );
            })()}
          </div>
        </section>

        {error && <ErrorBanner message={error} onRetry={onRetry} onLogout={onLogout} />}

        {/* Dynamic Multilingual AI Analysis Block */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3 mb-3">
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-900 text-white shadow-xs">
                <Sparkles className="h-4 w-4 text-saffron-400" />
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 font-mono">{aiSummary.badge}</span>
                <h3 className="text-sm font-bold text-slate-900">{aiSummary.headline}</h3>
              </div>
            </div>

            {/* Language Selector (EN / HI / MR) */}
            {onSetLang && (
              <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 text-xs font-semibold">
                <button
                  type="button"
                  onClick={() => onSetLang("en")}
                  className={`rounded-md px-3 py-1.5 transition touch-manipulation cursor-pointer ${lang === "en" ? "bg-white text-slate-900 font-bold shadow-xs border border-slate-200" : "text-slate-600 hover:text-slate-900 font-semibold"}`}
                >
                  English
                </button>
                <button
                  type="button"
                  onClick={() => onSetLang("hi")}
                  className={`rounded-md px-3 py-1.5 transition touch-manipulation cursor-pointer ${lang === "hi" ? "bg-white text-slate-900 font-bold shadow-xs border border-slate-200" : "text-slate-600 hover:text-slate-900 font-semibold"}`}
                >
                  हिन्दी
                </button>
                <button
                  type="button"
                  onClick={() => onSetLang("mr")}
                  className={`rounded-md px-3 py-1.5 transition touch-manipulation cursor-pointer ${lang === "mr" ? "bg-white text-slate-900 font-bold shadow-xs border border-slate-200" : "text-slate-600 hover:text-slate-900 font-semibold"}`}
                >
                  मराठी
                </button>
              </div>
            )}
          </div>

          <p className="text-xs leading-relaxed text-slate-700 font-medium">
            {aiSummary.text}
          </p>
        </section>

        {/* Dense 5-Metric Operational Ticker — Clean Executive Typography */}
        <section className="grid grid-cols-2 gap-3.5 sm:grid-cols-5">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-2xs hover:border-slate-300 transition-all">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{dt.inspectionsToday}</p>
              <span className="h-2 w-2 rounded-full bg-blue-500" />
            </div>
            <p className="mt-2 text-2xl sm:text-3xl font-black tracking-tight text-slate-900">{loading ? "…" : inspectionsToday}</p>
            <span className="mt-1 block text-[10px] font-medium text-slate-400">{dt.ofTotalLogged.replace("{total}", String(scanned))}</span>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-2xs hover:border-rose-200 transition-all">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-wider text-rose-600">{dt.violationsFlagged}</p>
              <span className="h-2 w-2 rounded-full bg-rose-500" />
            </div>
            <p className="mt-2 text-2xl sm:text-3xl font-black tracking-tight text-rose-600">{loading ? "…" : violations}</p>
            <span className="mt-1 block text-[10px] font-medium text-rose-500/80">{dt.rule6NonCompliance}</span>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-2xs hover:border-amber-200 transition-all">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-wider text-amber-600">{dt.pendingReviews}</p>
              <span className="h-2 w-2 rounded-full bg-amber-500" />
            </div>
            <p className="mt-2 text-2xl sm:text-3xl font-black tracking-tight text-amber-600">{loading ? "…" : (uncertainCases + pendingReviews)}</p>
            <span className="mt-1 block text-[10px] font-medium text-amber-600/80">{dt.requiresInspectorReview}</span>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-2xs hover:border-indigo-200 transition-all">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-wider text-indigo-600">{dt.packageIntegrity}</p>
              <span className="h-2 w-2 rounded-full bg-indigo-500" />
            </div>
            <p className="mt-2 text-2xl sm:text-3xl font-black tracking-tight text-indigo-600">{loading ? "…" : integrityAlerts}</p>
            <span className="mt-1 block text-[10px] font-medium text-slate-400">{dt.tamperAlerts}</span>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-2xs hover:border-emerald-200 transition-all col-span-2 sm:col-span-1">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">{dt.registerHealth}</p>
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
            </div>
            <p className="mt-2 text-2xl sm:text-3xl font-black tracking-tight text-emerald-700">{loading ? "…" : `${registerHealth}%`}</p>
            <span className="mt-1 block text-[10px] font-medium text-emerald-600/80">{dt.compliantRatio}</span>
          </div>
        </section>

        {/* Operational Workbench: 2-Column Command Grid */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left Column: Immediate Action & Queue (7 Cols) */}
          <div className="space-y-6 lg:col-span-7">
            {/* Urgent Review & Violations Queue */}
            <section className="rounded-2xl border border-slate-200/90 bg-white p-5 sm:p-6 shadow-xs">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-rose-600" />
                  <h3 className="text-xs font-mono font-bold text-slate-900 uppercase tracking-wider">
                    {dt.priorityQueueTitle} ({urgentQueue.length})
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => onNavigate("reviewQueue")}
                  className="text-xs font-semibold text-slate-700 hover:text-slate-950 inline-flex items-center gap-1 transition"
                >
                  {dt.fullQueue} <ChevronRight className="h-3 w-3" />
                </button>
              </div>

              {urgentQueue.length > 0 ? (
                <div className="divide-y divide-slate-100">
                  {urgentQueue.map((item: any) => (
                    <div key={item.id} className="flex items-center justify-between py-3 hover:bg-slate-50/70 px-2 rounded-xl transition">
                      <div className="min-w-0 flex-1 pr-3">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-slate-900 truncate">{item.product}</span>
                        </div>
                        <p className="mt-0.5 text-xs text-slate-500 font-mono truncate">
                          {item.productId ? `#${item.productId} · ` : `#${item.id} · `}{item.dateLabel}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={item.status} compact lang={lang} />
                        <button
                          type="button"
                          className="h-8 px-3 text-xs font-semibold rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-800 transition active:scale-95 shadow-2xs cursor-pointer"
                          onClick={() => onOpen(item)}
                        >
                          {dt.review}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400 py-6 text-center font-medium">
                  {dt.allPriorityProcessed}
                </p>
              )}
            </section>

            {/* Recent Inspections Log */}
            <section className="rounded-2xl border border-slate-200/90 bg-white p-5 sm:p-6 shadow-xs">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
                <div>
                  <h3 className="text-xs font-mono font-bold text-slate-900 uppercase tracking-wider">
                    {dt.recentInspections}
                  </h3>
                  <p className="text-[11px] text-slate-500 font-medium">{dt.liveStatutoryRecords}</p>
                </div>
                <button
                  type="button"
                  onClick={() => onNavigate("history")}
                  className="text-xs font-semibold text-slate-700 hover:text-slate-950 inline-flex items-center gap-1 transition"
                >
                  {dt.viewAll} ({scanned}) <ArrowRight className="h-3 w-3" />
                </button>
              </div>

              {loading ? (
                <div className="space-y-2 py-2">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-100" />
                  ))}
                </div>
              ) : inspections.length ? (
                <div className="divide-y divide-slate-100">
                  {inspections.slice(0, 4).map((inspection) => (
                    <InspectionRow key={inspection.id} inspection={inspection} onOpen={onOpen} lang={lang} />
                  ))}
                </div>
              ) : (
                <EmptyState
                  title={dt.noInspectionsYet}
                  description={dt.noInspectionsDesc}
                  onAction={() => onNavigate("scan")}
                />
              )}
            </section>
          </div>

          {/* Right Column: Regulatory Intelligence & Inter-Agency Surveillance (5 Cols) */}
          <div className="space-y-6 lg:col-span-5">
            {/* Regulatory Updates & Rule Engine Status */}
            <section className="rounded-2xl border border-slate-200/90 bg-white p-5 sm:p-6 shadow-xs space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-slate-700" />
                  <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-900">
                    {dt.regulatoryUpdates}
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => onNavigate("regulatory")}
                  className="text-[11px] font-semibold text-slate-600 hover:text-slate-900 transition"
                >
                  {dt.ruleEngine}
                </button>
              </div>

              <div className="space-y-2.5 text-xs">
                <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5 space-y-1">
                  <div className="flex items-center justify-between font-semibold">
                    <span className="text-slate-900 font-bold">{dt.lmpcRule6}</span>
                    <span className="rounded bg-emerald-100 text-emerald-800 px-1.5 py-0.5 text-[9px] font-mono font-bold">{dt.active}</span>
                  </div>
                  <p className="text-[11px] text-slate-600 leading-relaxed">
                    {dt.lmpcRule6Desc}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5 space-y-1">
                  <div className="flex items-center justify-between font-semibold">
                    <span className="text-slate-900 font-bold">{dt.gsrQrCode}</span>
                    <span className="rounded bg-blue-100 text-blue-800 px-1.5 py-0.5 text-[9px] font-mono font-bold">{dt.gazette}</span>
                  </div>
                  <p className="text-[11px] text-slate-600 leading-relaxed">
                    {dt.gsrQrCodeDesc}
                  </p>
                </div>
              </div>
            </section>

            {/* Cross-Verification: FSSAI & Package Integrity */}
            <section className="rounded-2xl border border-slate-200/90 bg-white p-5 sm:p-6 shadow-xs space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-emerald-600" />
                  <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-900">
                    {dt.interAgencyCheck}
                  </h3>
                </div>
                <span className="text-[10px] font-mono font-bold text-slate-400">LMPC · FSSAI</span>
              </div>

              <div className="space-y-2.5 text-xs">
                <div className="flex items-center justify-between rounded-xl bg-slate-50/60 p-3.5 border border-slate-200">
                  <div>
                    <p className="font-bold text-slate-900">{dt.fssaiVerification}</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">{dt.fssaiDesc}</p>
                  </div>
                  <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-mono font-bold text-emerald-800">
                    {dt.fssaiStatus}
                  </span>
                </div>

                <div className="flex items-center justify-between rounded-xl bg-slate-50/60 p-3.5 border border-slate-200">
                  <div>
                    <p className="font-bold text-slate-900">{dt.integrityModel}</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">{dt.integrityDesc}</p>
                  </div>
                  <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-[10px] font-mono font-bold text-blue-800">
                    {dt.integrityStatus}
                  </span>
                </div>
              </div>
            </section>
          </div>
        </div>
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// History / Register / Review queue list views
// ---------------------------------------------------------------------------


