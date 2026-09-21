import { getTranslation } from "@/lib/i18n";
import { CircleHelp, Info, PackageCheck, RefreshCcw, ScanLine } from "lucide-react";
import React from "react";
import {
  AlertTriangle,
  Camera,
  ClipboardCheck,
  FileText,
  Globe,
  History as HistoryIcon,
  LayoutDashboard,
  LogOut,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import { type Language } from "@/lib/i18n";
import { type View, Button } from "./ui-primitives";

export function getNavItems(lang: Language, role?: string): Array<{ label: string; view: View; icon: LucideIcon }> {
  let allItems: Array<{ label: string; view: View; icon: LucideIcon }> = [];
  if (lang === "hi") {
    allItems = [
      { label: "अवलोकन", view: "landing", icon: Sparkles },
      { label: "डैशबोर्ड", view: "home", icon: LayoutDashboard },
      { label: "पैकेज स्कैन करें", view: "scan", icon: Camera },
      { label: "निरीक्षण सूची", view: "history", icon: HistoryIcon },
      { label: "वैधानिक रजिस्टर", view: "register", icon: ClipboardCheck },
      { label: "समीक्षा कतार", view: "reviewQueue", icon: ShieldAlert },
      { label: "क्षेत्रीय आसूचना", view: "seniorRegional", icon: Globe },
      { label: "विधिक नियम", view: "regulatory", icon: FileText },
      { label: "प्राधिकारी डॉकेट", view: "authority", icon: ShieldCheck },
      { label: "उपभोक्ता पोर्टल", view: "customer", icon: Users },
      { label: "प्रोफ़ाइल", view: "profile", icon: UserRound },
    ];
  } else if (lang === "mr") {
    allItems = [
      { label: "आढावा", view: "landing", icon: Sparkles },
      { label: "डॅशबोर्ड", view: "home", icon: LayoutDashboard },
      { label: "पॅकेज स्कॅन करा", view: "scan", icon: Camera },
      { label: "तपासणी सूची", view: "history", icon: HistoryIcon },
      { label: "वैधानिक नोंदवही", view: "register", icon: ClipboardCheck },
      { label: "पुनरावलोकन रांग", view: "reviewQueue", icon: ShieldAlert },
      { label: "प्रादेशिक गुप्तचर", view: "seniorRegional", icon: Globe },
      { label: "वैधानिक नियम", view: "regulatory", icon: FileText },
      { label: "प्राधिकरण डॉकेट", view: "authority", icon: ShieldCheck },
      { label: "नागरिक पोर्टल", view: "customer", icon: Users },
      { label: "प्रोफाइल", view: "profile", icon: UserRound },
    ];
  } else {
    allItems = [
      { label: "Overview", view: "landing", icon: Sparkles },
      { label: "Dashboard", view: "home", icon: LayoutDashboard },
      { label: "Scan Package", view: "scan", icon: Camera },
      { label: "Inspections", view: "history", icon: HistoryIcon },
      { label: "Register", view: "register", icon: ClipboardCheck },
      { label: "Review Queue", view: "reviewQueue", icon: ShieldAlert },
      { label: "Senior Intel", view: "seniorRegional", icon: Globe },
      { label: "Regulatory Rules", view: "regulatory", icon: FileText },
      { label: "Authority Dockets", view: "authority", icon: ShieldCheck },
      { label: "Citizen Portal", view: "customer", icon: Users },
      { label: "Profile", view: "profile", icon: UserRound },
    ];
  }

  const r = (role || "").toLowerCase();
  if (r === "customer" || r === "consumer") {
    return allItems.filter((i) => i.view === "customer" || i.view === "scan" || i.view === "profile");
  }
  if (r === "authority") {
    return allItems.filter(
      (i) =>
        i.view === "seniorRegional" ||
        i.view === "scan" ||
        i.view === "authority" ||
        i.view === "register" ||
        i.view === "regulatory" ||
        i.view === "profile"
    );
  }
  if (r === "admin") {
    return allItems.filter(
      (i) =>
        i.view === "seniorRegional" ||
        i.view === "scan" ||
        i.view === "authority" ||
        i.view === "register" ||
        i.view === "regulatory" ||
        i.view === "profile"
    );
  }
  if (r === "senior_inspector") {
    return allItems.filter(
      (i) =>
        i.view === "home" ||
        i.view === "scan" ||
        i.view === "history" ||
        i.view === "register" ||
        i.view === "reviewQueue" ||
        i.view === "seniorRegional" ||
        i.view === "authority" ||
        i.view === "regulatory" ||
        i.view === "profile"
    );
  }
  if (r === "inspector" || r === "reviewer") {
    return allItems.filter(
      (i) =>
        i.view === "home" ||
        i.view === "scan" ||
        i.view === "history" ||
        i.view === "register" ||
        i.view === "reviewQueue" ||
        i.view === "profile"
    );
  }
  return allItems.filter((i) => i.view !== "landing");
}



export function DesktopRail({ view, onNavigate, lang = "en", role }: { view: View; onNavigate: (view: View) => void; lang?: Language; role?: string }) {
  const currentNavItems = getNavItems(lang, role);
  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-slate-200 bg-white px-4 py-5 md:flex shadow-sm">
      <div className="h-1.5 w-full tricolor-stripe mb-4 rounded-full" />

      {/* LexMetra Sidebar Logo */}
      <button
        type="button"
        onClick={() => onNavigate("landing")}
        className="mb-6 w-full transition-opacity hover:opacity-80 active:scale-[0.98] flex items-center justify-center"
      >
        <img
          src="/lexmetra-blue-logo.png"
          alt="LexMetra"
          className="h-10 w-auto object-contain"
          draggable={false}
        />
      </button>

      <nav className="space-y-1">
        {currentNavItems.map((item) => {
          const Icon = item.icon;
          const active = view === item.view;
          return (
            <button
              key={item.view}
              type="button"
              onClick={() => onNavigate(item.view)}
              className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-sm font-semibold transition-all ${active
                  ? "bg-gradient-to-r from-brand-900 via-brand-800 to-brand-700 text-white shadow-md shadow-brand/25 font-bold"
                  : "text-slate-600 hover:bg-brand-50/70 hover:text-brand-900"
                }`}
            >
              <span className="flex items-center gap-3">
                <Icon className={`h-[18px] w-[18px] ${active ? "text-saffron-300" : "text-slate-400"}`} />
                {item.label}
              </span>
              {active && <span className="h-2 w-2 rounded-full bg-saffron-400 shadow-xs" />}
            </button>
          );
        })}
      </nav>

      <div className="mt-auto rounded-2xl bg-gradient-to-b from-slate-50 to-brand-50/30 border border-slate-200 p-4 text-xs">
        <div className="flex items-center gap-2 font-bold text-brand-950">
          <ShieldCheck className="h-4 w-4 text-govgreen" />
          <span>Statutory Authority Unit</span>
        </div>
        <p className="mt-1.5 leading-relaxed text-slate-600 text-[11px]">
          Legal Metrology (Packaged Commodities) Rules, 2011 · Statutory Standards
        </p>
        <div className="mt-2.5 flex items-center gap-1.5 text-[10px] font-bold text-saffron-700">
          <span className="h-1.5 w-1.5 rounded-full bg-govgreen" />
        </div>
      </div>
    </aside>
  );
}

export function BottomNav({ view, onNavigate, lang = "en", role }: { view: View; onNavigate: (view: View) => void; lang?: Language; role?: string }) {
  const t = getTranslation(lang);
  const isConsumer = role === "customer";
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-border/70 bg-card/95 px-3 pt-2 backdrop-blur md:hidden">
      <div className="mx-auto grid max-w-lg grid-cols-5 items-end">
        <NavButton label={isConsumer ? "Citizen Portal" : t.dashboard} icon={LayoutDashboard} active={isConsumer ? view === "customer" : view === "home"} onClick={() => onNavigate(isConsumer ? "customer" : "home")} />
        <NavButton label={t.history} icon={HistoryIcon} active={view === "history"} onClick={() => onNavigate("history")} />
        <div className="relative -top-5 flex justify-center">
          <button type="button" aria-label="Start a scan" onClick={() => onNavigate("scan")} className="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-xl shadow-primary/20 transition-transform active:scale-95">
            <ScanLine className="h-7 w-7" />
          </button>
        </div>
        {isConsumer ? (
          <NavButton label="Help & 1915" icon={CircleHelp} active={view === "customer"} onClick={() => onNavigate("customer")} />
        ) : (
          <NavButton label={t.reviewQueue} icon={ShieldAlert} active={view === "reviewQueue"} onClick={() => onNavigate("reviewQueue")} />
        )}
        <NavButton label={t.profile} icon={UserRound} active={view === "profile"} onClick={() => onNavigate("profile")} />
      </div>
    </nav>
  );
}

export function NavButton({ label, icon: Icon, active, onClick }: { label: string; icon: LucideIcon; active: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={`flex min-h-14 flex-col items-center justify-center gap-1 text-[10px] font-semibold ${active ? "text-brand" : "text-muted-foreground"}`}>
      <Icon className="h-[18px] w-[18px]" /><span>{label}</span>
    </button>
  );
}

export function EmptyState({ title, description, onAction, actionLabel = "Scan Product" }: { title: string; description: string; onAction: () => void; actionLabel?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-card px-6 py-12 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground"><PackageCheck className="h-6 w-6" /></div>
      <h3 className="mt-4 text-base font-semibold">{title}</h3>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{description}</p>
      <Button className="mt-6" onClick={onAction}><ScanLine className="h-4 w-4" />{actionLabel}</Button>
    </div>
  );
}

export function ErrorBanner({ message, onRetry, onLogout }: { message: string; onRetry?: () => void; onLogout?: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-destructive/25 bg-danger-soft p-4 text-sm">
      <AlertTriangle className="h-5 w-5 shrink-0 text-destructive" />
      <p className="flex-1 text-destructive">{message}</p>
      {onRetry && <Button variant="secondary" onClick={onRetry}><RefreshCcw className="h-4 w-4" />Retry</Button>}
      {onLogout && <Button variant="secondary" onClick={onLogout}><LogOut className="h-4 w-4" />Sign in</Button>}
    </div>
  );
}

export function DisclaimerBanner({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/70 bg-muted/60 p-4 text-xs leading-5 text-muted-foreground">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <p>{text}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Multilingual Localization Dictionary (EN / HI / MR)
// ---------------------------------------------------------------------------

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
    enforcementUnit: "Enforcement Unit: Zone 4 Surveillance",
    fieldOperations: "Compliance Operations & Intelligence",
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


