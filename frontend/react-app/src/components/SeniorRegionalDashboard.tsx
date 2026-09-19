import React, { useEffect, useState } from "react";
import {
  BarChart3,
  Building2,
  CheckCircle2,
  ChevronRight,
  Layers,
  MapPin,
  PieChart,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Store,
  TrendingUp,
  AlertTriangle,
  Scale,
  FileText,
  Gavel,
  Sliders,
  Send,
  Eye,
  Camera,
} from "lucide-react";
import {
  getRegionalIntelligence,
  getSocialSummary,
  listSocialMentions,
  takeSocialMentionAction,
} from "@/lib/api-client";
import { type Language } from "@/lib/i18n";
import { type Inspection } from "@/lib/types";
import { AppHeader } from "./InspectionApp";

interface RegionalData {
  total_cases: number;
  city_breakdown: Array<{
    city: string;
    state: string;
    lat: number;
    lng: number;
    total_cases: number;
    violations: number;
    fssai_issues: number;
    integrity_alerts: number;
    consumer_reports: number;
    high_priority: number;
    retailer_count: number;
  }>;
  top_retailers: Array<{
    retailer: string;
    case_count: number;
  }>;
  domain_distribution: Record<string, number>;
  category_distribution: Record<string, number>;
  ai_regional_analysis: string;
  timestamp: string;
}

interface SocialSummaryData {
  data_classification: string;
  total_signals_analyzed: number;
  region_breakdown: Array<{ city: string; count: number }>;
  domain_distribution: Record<string, number>;
  category_distribution: Record<string, number>;
  active_clusters: Array<{
    cluster_label: string;
    count: number;
    members: Array<{
      mention_id: string;
      author: string;
      city: string;
      brand?: string;
      priority_score: number;
    }>;
  }>;
  top_region: string;
  top_category: string;
  ai_regional_summary: string;
  timestamp: string;
}

const I18N = {
  en: {
    title: "Senior Inspector Regional Intelligence & Surveillance Center",
    subtitle: "District non-compliance surveillance, Field Inspector review, rule enforcement & public grievance tracking.",
    badge: "Executive Directorate · Legal Metrology Division",
    backCommand: "Back to Command Center",
    tabRegional: "Geographic & District Surveillance",
    tabCharts: "Charts & Visual Analytics",
    tabFieldScans: "Field Inspector Live Scans",
    tabRuleEngine: "Statutory Rule Engine Enforcement",
    tabSocial: "Public Complaints & Social Intel",
    totalCases: "Total Monitored Cases",
    totalCasesSub: "Ground inspection + consumer tickets",
    lmpcViolations: "LMPC Violations",
    lmpcViolationsSub: "Short weight / MRP overcharge",
    fssaiInfractions: "FSSAI Infractions",
    fssaiInfractionsSub: "Missing license / Expiry breaches",
    packageAlterations: "Package Alterations",
    packageAlterationsSub: "Catalog discrepancy heatmaps",
    districtGridTitle: "District & City Surveillance Grid",
    districtGridSub: "Click region to drill down",
    thRegion: "Region / City",
    thDockets: "Total Dockets",
    thViolations: "Violations",
    thFssai: "FSSAI Issues",
    thRetailers: "Retail Outlets",
    thAction: "Action",
    btnInspect: "Inspect",
    topRetailersTitle: "Top Problematic Retail Outlets",
    recurrentNotice: "Recurrent violation notice candidate",
    geoCoords: "Geographic Coordinates",
    geoCoordsSub: "Ground enforcement teams can coordinate GPS field visits directly from these coordinates.",
    aiPatternTitle: "AI Pattern Intelligence",
    aiPatternSub: "Persisted Regional Inferences",
    refresh: "Refresh",
    // Field Scans Tab
    fieldScansTitle: "Field Inspector Scans & Live Inspection Dockets",
    fieldScansSub: "All package scans, violation logs, and mandatory declaration audits submitted by field inspectors.",
    allStatus: "All Status",
    onlyViolations: "Non-Compliant Only",
    onlyVerified: "Verified Only",
    noScans: "No field inspections found matching the filter.",
    viewDocket: "View Full Docket",
    scanDate: "Scanned",
    inspector: "Officer",
    sku: "Product SKU",
    mrp: "MRP",
    netQty: "Net Qty",
    // Rule Engine Tab
    ruleEngineTitle: "LMPC Statutory Rule Engine Enforcement (LMPC Rules 2011 & Section 36)",
    ruleEngineSub: "Senior Authority oversight for automated declaration verifications, compounding notices, and penalty policies.",
    activePolicies: "Active Statutory Enforcement Policies",
    rule6Title: "Rule 6(1)(a)-(f) Mandatory Declarations Codex",
    rule6Desc: "Automated OCR & NLP validation of Manufacturer Name, Address, Net Quantity, MRP, Date of Packaging/Expiry, and Consumer Care Contact.",
    rule12Title: "Rule 6(11) Unit Sale Price (USP) Mandate",
    rule12Desc: "Mandates unit pricing in ₹ per g/ml for packages over 1kg/1L to protect consumers against shrinkflation.",
    rule26Title: "Rule 26 Non-Standard Commodity Seizures",
    rule26Desc: "Automated seizure docket generation for non-standard size packages lacking Section 36 statutory exemption.",
    section36Title: "Section 36 Compounding & Penalty Schedule",
    section36Desc: "Statutory fine matrix: First Offense up to ₹25,000, Second Offense up to ₹50,000, Subsequent Offense up to ₹1,00,000 with prosecution.",
    issueNotice: "Issue Section 36 Notice",
    dispatchSquad: "Dispatch Surprise Field Squad",
    enforcementStrict: "Strict Rule Enforcement Active",
    standardRules: "Standard Baseline Rules",
    // Social Tab
    socialDemo: "SIMULATED PUBLIC INTELLIGENCE / DEMONSTRATION ENGINE",
    socialDemoDesc: "This pipeline demonstrates how LexMetra ingests, deduplicates, clusters, and dynamically prioritizes public consumer posts into actionable enforcement cases.",
  },
  hi: {
    title: "वरिष्ठ निरीक्षक क्षेत्रीय अभिसूचना एवं निगरानी केंद्र",
    subtitle: "जिला गैर-अनुपालन निगरानी, फील्ड इंस्पेक्टर समीक्षा, नियम प्रवर्तन और जन शिकायत ट्रैकिंग।",
    badge: "कार्यकारी निदेशालय · विधिक मापविज्ञान प्रभाग",
    backCommand: "कमांड सेंटर पर वापस जाएं",
    tabRegional: "भौगोलिक एवं जिला निगरानी",
    tabCharts: "चार्ट और दृश्य विश्लेषण",
    tabFieldScans: "फील्ड इंस्पेक्टर लाइव स्कैन",
    tabRuleEngine: "विधिक नियम इंजन प्रवर्तन",
    tabSocial: "सार्वजनिक शिकायतें एवं सोशल इंटेलिजेंस",
    totalCases: "कुल निगरानी किए गए मामले",
    totalCasesSub: "फील्ड निरीक्षण + उपभोक्ता शिकायतें",
    lmpcViolations: "LMPC उल्लंघन",
    lmpcViolationsSub: "कम वजन / अधिक MRP वसूली",
    fssaiInfractions: "FSSAI उल्लंघन",
    fssaiInfractionsSub: "लाइसेंस गायब / समाप्ति तिथि दोष",
    packageAlterations: "पैकेज फेरबदल",
    packageAlterationsSub: "कैटलॉग विसंगति हीटमैप",
    districtGridTitle: "जिला एवं नगर निगरानी ग्रिड",
    districtGridSub: "विस्तृत विवरण के लिए क्षेत्र पर क्लिक करें",
    thRegion: "क्षेत्र / नगर",
    thDockets: "कुल मामले",
    thViolations: "उल्लंघन",
    thFssai: "FSSAI समस्याएं",
    thRetailers: "खुदरा दुकानें",
    thAction: "कार्रवाई",
    btnInspect: "निरीक्षण",
    topRetailersTitle: "शीर्ष समस्याग्रस्त खुदरा विक्रेता",
    recurrentNotice: "बार-बार उल्लंघन नोटिस उम्मीदवार",
    geoCoords: "भौगोलिक निर्देशांक",
    geoCoordsSub: "फील्ड टीमें इन निर्देशांकों से सीधे जीपीएस जांच का समन्वय कर सकती हैं।",
    aiPatternTitle: "AI पैटर्न इंटेलिजेंस",
    aiPatternSub: "क्षेत्रीय निष्कर्ष",
    refresh: "ताज़ा करें",
    // Field Scans Tab
    fieldScansTitle: "फील्ड इंस्पेक्टर स्कैन और लाइव निरीक्षण फाइलें",
    fieldScansSub: "फील्ड निरीक्षकों द्वारा जमा किए गए सभी पैकेज स्कैन, उल्लंघन लॉग और घोषणा ऑडिट।",
    allStatus: "सभी स्थितियां",
    onlyViolations: "केवल गैर-अनुपालन",
    onlyVerified: "केवल सत्यापित",
    noScans: "फिल्टर से मेल खाने वाला कोई निरीक्षण नहीं मिला।",
    viewDocket: "पूरी फाइल देखें",
    scanDate: "स्कैन तिथि",
    inspector: "अधिकारी",
    sku: "उत्पाद SKU",
    mrp: "MRP",
    netQty: "शुद्ध मात्रा",
    // Rule Engine Tab
    ruleEngineTitle: "LMPC विधिक नियम इंजन प्रवर्तन (नियम 2011 एवं धारा 36)",
    ruleEngineSub: "स्वचालित घोषणा सत्यापन, प्रशमन नोटिस और जुर्माना नीतियों की वरिष्ठ प्राधिकरण निगरानी।",
    activePolicies: "सक्रिय विधिक प्रवर्तन नीतियां",
    rule6Title: "नियम 6(1)(a)-(f) अनिवार्य घोषणाएं कोडेक्स",
    rule6Desc: "निर्माता का नाम, पता, शुद्ध मात्रा, MRP, निर्माण/समाप्ति तिथि और उपभोक्ता हेल्पलाइन का स्वचालित OCR सत्यापन।",
    rule12Title: "नियम 6(11) इकाई विक्रय मूल्य (USP) अनिवार्यता",
    rule12Desc: "उपभोक्ताओं को श्रिंकफ्लेशन से बचाने हेतु 1 किग्रा/1 लीटर से बड़े पैकेट पर ₹ प्रति ग्राम/मिली अनिवार्य मूल्य।",
    rule26Title: "नियम 26 अमानक वस्तु जब्ती प्रोटोकॉल",
    rule26Desc: "धारा 36 छूट के बिना अमानक आकार के पैकेजों के लिए स्वचालित जब्ती डॉकेट निर्माण।",
    section36Title: "धारा 36 प्रशमन और जुर्माना अनुसूची",
    section36Desc: "जुर्माना मैट्रिक्स: पहला अपराध ₹25,000 तक, दूसरा अपराध ₹50,000 तक, बार-बार अपराध पर ₹1,00,000 व अभियोजन।",
    issueNotice: "धारा 36 नोटिस जारी करें",
    dispatchSquad: "आकस्मिक जांच दल भेजें",
    enforcementStrict: "सख्त नियम प्रवर्तन सक्रिय",
    standardRules: "मानक आधारभूत नियम",
    // Social Tab
    socialDemo: "सिम्युलेटेड सार्वजनिक इंटेलिजेंस इंजन",
    socialDemoDesc: "यह पाइपलाइन प्रदर्शित करती है कि लेक्समेट्रा सार्वजनिक शिकायतों को प्रवर्तन मामलों में कैसे बदलता है।",
  },
  mr: {
    title: "वरिष्ठ निरीक्षक प्रादेशिक गुप्तवार्ता व दक्षता नियंत्रण केंद्र",
    subtitle: "जिल्हास्तरीय कायदेशीर मापनशास्त्र गैर-पालन नियंत्रण, फील्ड तपासणी आढावा आणि नियम अंमलबजावणी.",
    badge: "कार्यकारी संचालनालय · कायदेशीर मापनशास्त्र विभाग",
    backCommand: "कमांड सेंटरवर परत जा",
    tabRegional: "भौगोलिक व जिल्हा नियंत्रण",
    tabCharts: "तक्ते व दृश्य विश्लेषण",
    tabFieldScans: "फील्ड इन्स्पेक्टर थेट तपासण्या",
    tabRuleEngine: "वैधानिक नियम इंजिन अंमलबजावणी",
    tabSocial: "सार्वजनिक तक्रारी व सोशल इंटेलिजन्स",
    totalCases: "एकूण नोंदवलेली प्रकरणे",
    totalCasesSub: "प्रत्यक्ष तपासणी + ग्राहक तक्रारी",
    lmpcViolations: "LMPC उल्लंघन प्रकरणे",
    lmpcViolationsSub: "कमी वजन / छापील किमतीपेक्षा जादा आकारणी",
    fssaiInfractions: "FSSAI त्रुटी",
    fssaiInfractionsSub: "परवाना क्रमांक नसणे / मुदत संपलेले अन्न",
    packageAlterations: "पॅकेज लेबल फेरफार",
    packageAlterationsSub: "कॅटलॉग तफावत सतर्कता",
    districtGridTitle: "जिल्हा व शहर दक्षता सारणी",
    districtGridSub: "सविस्तर माहितीसाठी जिल्ह्यावर क्लिक करा",
    thRegion: "प्रदेश / शहर",
    thDockets: "एकूण प्रकरणे",
    thViolations: "उल्लंघने",
    thFssai: "FSSAI त्रुटी",
    thRetailers: "तपासलेली दुकाने",
    thAction: "कृती",
    btnInspect: "तपासा",
    topRetailersTitle: "वारंवार नियमभंग करणारे मुख्य विक्रेते",
    recurrentNotice: "पुन्हा नोटीस बजावण्यासाठी पात्र",
    geoCoords: "भौगोलिक निर्देशांक",
    geoCoordsSub: "फील्ड पथके या जीपीएस निर्देशांकांवरून थेट प्रत्यक्ष कारवाईचे नियोजन करू शकतात.",
    aiPatternTitle: "AI पॅटर्न विश्लेषण",
    aiPatternSub: "प्रादेशिक निष्कर्ष",
    refresh: "रिफ्रेश करा",
    // Field Scans Tab
    fieldScansTitle: "फील्ड इन्स्पेक्टर स्कॅन्स व थेट तपासणी नोंदी",
    fieldScansSub: "फील्ड इन्स्पेक्टरांनी तपासलेले सर्व पॅकेट्स, उल्लंघनांच्या नोंदी व अधिकृत ऑडिट फाइल्स.",
    allStatus: "सर्व स्थिती",
    onlyViolations: "केवळ उल्लंघन झालेले",
    onlyVerified: "केवळ सत्यापित",
    noScans: "फिल्टरशी जुळणारी कोणतीही तपासणी आढळली नाही.",
    viewDocket: "संपूर्ण फाइल उघडा",
    scanDate: "तपासणी तारीख",
    inspector: "अधिकारी",
    sku: "उत्पादन SKU",
    mrp: "MRP",
    netQty: "निव्वळ वजन",
    // Rule Engine Tab
    ruleEngineTitle: "LMPC वैधानिक नियम इंजिन अंमलबजावणी (नियम 2011 व कलम 36)",
    ruleEngineSub: "स्वयंचलित घोषणा पडताळणी, तडजोड नोटिसा आणि दंड नियमांचे वरिष्ठ प्राधिकरण नियंत्रण.",
    activePolicies: "सक्रिय वैधानिक अंमलबजावणी धोरणे",
    rule6Title: "नियम 6(1)(a)-(f) अनिवार्य घोषणा कोडेक्स",
    rule6Desc: "उत्पादकाचे नाव, पत्ता, निव्वळ वजन, MRP, उत्पादन/मुदत तारीख व ग्राहक हेल्पलाइनचे स्वयंचलित OCR सत्यापन.",
    rule12Title: "नियम 6(11) युनिट विक्री किंमत (USP) सक्ती",
    rule12Desc: "ग्राहकांची फसवणूक रोखण्यासाठी 1 किलोग्रॅम/1 लिटरपेक्षा मोठ्या पॅकेट्सवर प्रति ग्रॅम/मिली दर छापणे बंधनकारक.",
    rule26Title: "नियम 26 अमानक पॅकेज जप्ती नियमावली",
    rule26Desc: "कलम 36 अंतर्गत अधिकृत सवलत नसलेल्या अमानक आकाराच्या पाकिटांवर थेट जप्ती कारवाई.",
    section36Title: "कलम 36 तडजोड व दंड वेळापत्रक",
    section36Desc: "दंड तक्ता: पहिल्या गुन्ह्यासाठी ₹25,000, दुसऱ्या गुन्ह्यासाठी ₹50,000, पुढील गुन्ह्यासाठी ₹1,00,000 सह खटला.",
    issueNotice: "कलम 36 नोटीस जारी करा",
    dispatchSquad: "आकस्मिक तपासणी पथक पाठवा",
    enforcementStrict: "कडक नियम अंमलबजावणी सुरू",
    standardRules: "प्रमाणित आधारभूत नियम",
    // Social Tab
    socialDemo: "सिम्युलेटेड सार्वजनिक गुप्तवार्ता इंजिन",
    socialDemoDesc: "सोशल मीडियावरील ग्राहकांच्या तक्रारींचे स्वयंचलित वर्गीकरण करून त्यांना कायदेशीर प्रकरणात रूपांतरित करते.",
  },
};

function renderFormattedAnalysis(text: string) {
  if (!text) return null;
  const lines = text.split("\n").filter((l) => l.trim().length > 0);
  return (
    <div className="space-y-1.5 pt-1">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        const isBullet = /^[•\-\*]\s*/.test(trimmed);
        const cleanLine = trimmed.replace(/^[•\-\*]\s*/, "");

        const parts: React.ReactNode[] = [];
        const regex = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
        let lastIdx = 0;
        let match: RegExpExecArray | null;
        while ((match = regex.exec(cleanLine)) !== null) {
          if (match.index > lastIdx) {
            const plain = cleanLine.slice(lastIdx, match.index).replace(/\*/g, "");
            if (plain) parts.push(plain);
          }
          const token = match[0];
          const inner = token.replace(/\*/g, "");
          parts.push(<strong key={match.index} className="font-bold text-slate-900">{inner}</strong>);
          lastIdx = match.index + token.length;
        }
        if (lastIdx < cleanLine.length) {
          const rem = cleanLine.slice(lastIdx).replace(/\*/g, "");
          if (rem) parts.push(rem);
        }

        if (isBullet) {
          return (
            <div key={idx} className="flex items-start gap-2 text-xs leading-relaxed text-slate-800">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-700 shrink-0 mt-1.5" />
              <div className="flex-1 font-normal">{parts}</div>
            </div>
          );
        }

        return (
          <p key={idx} className="text-xs font-semibold leading-relaxed text-slate-800">
            {parts}
          </p>
        );
      })}
    </div>
  );
}

export function SeniorRegionalDashboard({
  onBack: _onBack,
  onOpenInspection,
  inspections = [],
  lang = "en",
  onLanguageChange,
  user,
  onLogout,
  onNavigate,
}: {
  onBack: () => void;
  onOpenInspection?: (id: string) => void;
  inspections?: Inspection[];
  lang?: Language;
  onLanguageChange?: (lang: Language) => void;
  user?: any;
  onLogout?: () => void;
  onNavigate?: (view: any) => void;
}) {
  const t = I18N[lang] || I18N.en;

  const [data, setData] = useState<RegionalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"REGIONAL" | "CHARTS" | "FIELD_SCANS" | "RULE_ENGINE" | "SOCIAL_INTEL">("REGIONAL");

  // Field scans filter
  const [scanFilter, setScanFilter] = useState<"ALL" | "NON_COMPLIANT" | "VERIFIED">("ALL");

  // Social Intelligence State
  const [mentions, setMentions] = useState<any[]>([]);
  const [socialSummary, setSocialSummary] = useState<SocialSummaryData | null>(null);
  const [socialLoading, setSocialLoading] = useState(false);
  const [domainFilter] = useState("ALL");
  const [cityFilter] = useState("ALL");
  const [selectedCity, setSelectedCity] = useState<string | null>(null);

  // Rule enforcement state
  const [strictEnforcement, setStrictEnforcement] = useState(true);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  useEffect(() => {
    loadRegional();
  }, [lang]);

  useEffect(() => {
    if (activeTab === "SOCIAL_INTEL") {
      loadSocial();
    }
  }, [activeTab, domainFilter, cityFilter, lang]);

  async function loadRegional() {
    setLoading(true);
    try {
      const res = await getRegionalIntelligence(lang);
      setData(res);
      if (res.city_breakdown?.length > 0 && !selectedCity) {
        setSelectedCity(res.city_breakdown[0].city);
      }
    } catch (err) {
      console.error("Failed to load regional intelligence:", err);
    } finally {
      setLoading(false);
    }
  }

  async function loadSocial() {
    setSocialLoading(true);
    try {
      const [mRes, sRes] = await Promise.all([
        listSocialMentions({
          domain: domainFilter !== "ALL" ? domainFilter : undefined,
          city: cityFilter !== "ALL" ? cityFilter : undefined,
        }),
        getSocialSummary(lang),
      ]);
      setMentions(mRes);
      setSocialSummary(sRes);
    } catch (err) {
      console.error("Failed to load social intelligence:", err);
    } finally {
      setSocialLoading(false);
    }
  }

  async function handleConvertMention(mentionId: string) {
    try {
      await takeSocialMentionAction(mentionId, {
        new_status: "CONVERTED_TO_CASE",
        officer_notes: "Converted to official Legal Metrology Investigation Docket by Senior Officer.",
      });
      loadSocial();
    } catch (e: any) {
      alert("Failed to convert mention: " + e?.message);
    }
  }

  async function handleAssignInspector(mentionId: string) {
    try {
      await takeSocialMentionAction(mentionId, {
        new_status: "ASSIGNED_TO_INSPECTOR",
        officer_notes: "Dispatched field inspector for surprise physical audit and verification.",
        assigned_officer: "field_inspector_squad",
      });
      loadSocial();
    } catch (e: any) {
      alert("Failed to assign inspector: " + e?.message);
    }
  }

  function handleIssueSection36(ruleName: string) {
    setActionMessage(`Section 36 Statutory Notice generated for: ${ruleName}. Dispatched to Manufacturer.`);
    window.setTimeout(() => setActionMessage(null), 4000);
  }

  function handleDispatchSquad(district: string) {
    setActionMessage(`Surprise Field Inspection Squad dispatched to ${district} for verification.`);
    window.setTimeout(() => setActionMessage(null), 4000);
  }

  // Filtered field inspections
  const filteredInspections = inspections.filter((item) => {
    if (scanFilter === "NON_COMPLIANT") return item.status === "VIOLATION";
    if (scanFilter === "VERIFIED") return item.status === "COMPLIANT";
    return true;
  });

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <AppHeader
        title={t.title}
        eyebrow={t.badge}
        lang={lang}
        onLanguageChange={onLanguageChange}
        user={user}
        onLogout={onLogout}
        onNavigate={onNavigate}
      />

      {/* Main Content Area */}
      <div className="mx-auto max-w-7xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-8">
        {/* Action toast */}
        {actionMessage && (
          <div className="fixed top-24 left-1/2 z-50 -translate-x-1/2 rounded-2xl bg-slate-900 text-white px-5 py-3 text-xs font-bold shadow-2xl flex items-center gap-2 border border-slate-700 animate-in fade-in slide-in-from-top-4">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            <span>{actionMessage}</span>
          </div>
        )}

        {/* 5 Distinct Senior Inspector Mode Tabs */}
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-3">
          <button
            type="button"
            onClick={() => setActiveTab("REGIONAL")}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition shadow-xs ${
              activeTab === "REGIONAL"
                ? "bg-purple-800 text-white shadow-sm"
                : "bg-white text-slate-800 border border-slate-300 hover:bg-slate-50"
            }`}
          >
            <MapPin className="h-4 w-4" />
            {t.tabRegional}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("CHARTS")}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition shadow-xs ${
              activeTab === "CHARTS"
                ? "bg-purple-800 text-white shadow-sm"
                : "bg-white text-slate-800 border border-slate-300 hover:bg-slate-50"
            }`}
          >
            <BarChart3 className="h-4 w-4" />
            {t.tabCharts}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("FIELD_SCANS")}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition shadow-xs ${
              activeTab === "FIELD_SCANS"
                ? "bg-purple-800 text-white shadow-sm"
                : "bg-white text-slate-800 border border-slate-300 hover:bg-slate-50"
            }`}
          >
            <FileText className="h-4 w-4" />
            {t.tabFieldScans}
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
              activeTab === "FIELD_SCANS" ? "bg-white/20 text-white" : "bg-purple-100 text-purple-900"
            }`}>
              {inspections.length}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("RULE_ENGINE")}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition shadow-xs ${
              activeTab === "RULE_ENGINE"
                ? "bg-purple-800 text-white shadow-sm"
                : "bg-white text-slate-800 border border-slate-300 hover:bg-slate-50"
            }`}
          >
            <Gavel className="h-4 w-4" />
            {t.tabRuleEngine}
            <span className="rounded-full bg-emerald-100 text-emerald-800 px-2 py-0.5 text-[9px] font-extrabold uppercase">
              LMPC 2011
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("SOCIAL_INTEL")}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition shadow-xs ${
              activeTab === "SOCIAL_INTEL"
                ? "bg-purple-800 text-white shadow-sm"
                : "bg-white text-slate-800 border border-slate-300 hover:bg-slate-50"
            }`}
          >
            <TrendingUp className="h-4 w-4" />
            {t.tabSocial}
          </button>
        </div>

        {/* TAB 1: REGIONAL GEOGRAPHIC SURVEILLANCE */}
        {activeTab === "REGIONAL" && (
          <div className="space-y-6">
            {loading && !data && (
              <div className="py-8 text-center text-xs text-slate-500 animate-pulse">
                Loading regional surveillance data...
              </div>
            )}

            {/* AI Pattern Intelligence Banner */}
            {data?.ai_regional_analysis && (
              <div className="rounded-2xl border border-purple-200 bg-purple-50/60 p-5 shadow-xs space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-purple-200 text-purple-950 px-2.5 py-0.5 text-[10px] font-black uppercase">
                      {t.aiPatternTitle}
                    </span>
                    <span className="text-[11px] text-slate-600">{t.aiPatternSub}</span>
                  </div>
                  <button
                    type="button"
                    onClick={loadRegional}
                    className="text-xs text-purple-800 hover:text-purple-950 font-bold inline-flex items-center gap-1"
                  >
                    <RefreshCw className="h-3 w-3" /> {t.refresh}
                  </button>
                </div>
                {renderFormattedAnalysis(data.ai_regional_analysis)}
              </div>
            )}

            {/* 4 Metric Cards */}
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">{t.totalCases}</p>
                <p className="mt-1 text-2xl font-black text-slate-900">{data?.total_cases ?? "…"}</p>
                <span className="text-[11px] text-slate-500">{t.totalCasesSub}</span>
              </div>
              <div className="rounded-2xl border border-rose-200 bg-rose-50/60 p-4 shadow-2xs">
                <p className="text-[10px] font-bold uppercase tracking-widest text-rose-700">{t.lmpcViolations}</p>
                <p className="mt-1 text-2xl font-black text-rose-950">{data?.domain_distribution?.LMPC ?? 0}</p>
                <span className="text-[11px] text-rose-600">{t.lmpcViolationsSub}</span>
              </div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4 shadow-2xs">
                <p className="text-[10px] font-bold uppercase tracking-widest text-amber-700">{t.fssaiInfractions}</p>
                <p className="mt-1 text-2xl font-black text-amber-950">{data?.domain_distribution?.FSSAI ?? 0}</p>
                <span className="text-[11px] text-amber-600">{t.fssaiInfractionsSub}</span>
              </div>
              <div className="rounded-2xl border border-blue-200 bg-blue-50/60 p-4 shadow-2xs">
                <p className="text-[10px] font-bold uppercase tracking-widest text-blue-700">{t.packageAlterations}</p>
                <p className="mt-1 text-2xl font-black text-blue-950">{data?.domain_distribution?.INTEGRITY ?? 0}</p>
                <span className="text-[11px] text-blue-600">{t.packageAlterationsSub}</span>
              </div>
            </div>

            {/* Interactive District Grid & Top Problematic Outlets */}
            <div className="grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2 rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <Building2 className="h-4 w-4 text-purple-700" />
                    <h2 className="text-sm font-bold text-slate-900">{t.districtGridTitle}</h2>
                  </div>
                  <span className="text-xs text-slate-500">{t.districtGridSub}</span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-100 text-slate-500 font-bold">
                        <th className="pb-2.5">{t.thRegion}</th>
                        <th className="pb-2.5">{t.thDockets}</th>
                        <th className="pb-2.5">{t.thViolations}</th>
                        <th className="pb-2.5">{t.thFssai}</th>
                        <th className="pb-2.5">{t.thRetailers}</th>
                        <th className="pb-2.5 text-right">{t.thAction}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data?.city_breakdown.map((c) => (
                        <tr
                          key={c.city}
                          onClick={() => setSelectedCity(c.city)}
                          className={`cursor-pointer transition hover:bg-slate-50 ${
                            selectedCity === c.city ? "bg-purple-50/70 font-semibold" : ""
                          }`}
                        >
                          <td className="py-3 flex items-center gap-2 font-medium">
                            <MapPin className="h-3.5 w-3.5 text-purple-700" />
                            <span>{c.city}, {c.state}</span>
                          </td>
                          <td className="py-3 font-extrabold">{c.total_cases}</td>
                          <td className="py-3">
                            <span className="rounded-full bg-rose-100 px-2.5 py-0.5 text-rose-800 font-bold">
                              {c.violations}
                            </span>
                          </td>
                          <td className="py-3 text-slate-700">{c.fssai_issues}</td>
                          <td className="py-3 text-slate-700">{c.retailer_count} monitored</td>
                          <td className="py-3 text-right">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDispatchSquad(c.city);
                              }}
                              className="inline-flex items-center gap-1 text-[11px] font-bold text-purple-800 hover:text-purple-950"
                            >
                              {t.btnInspect} <ChevronRight className="h-3 w-3" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Problematic Retailers & Lat/Lng Geo Box */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <Store className="h-4 w-4 text-amber-600" />
                    <h3 className="text-sm font-bold text-slate-900">{t.topRetailersTitle}</h3>
                  </div>
                </div>

                <div className="space-y-3">
                  {data?.top_retailers?.map((r, idx) => (
                    <div key={idx} className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs flex justify-between items-center">
                      <div>
                        <p className="font-bold text-slate-900">{r.retailer}</p>
                        <span className="text-[10px] text-slate-500">{t.recurrentNotice}</span>
                      </div>
                      <span className="rounded-full bg-rose-100 text-rose-800 font-extrabold px-2.5 py-0.5 text-[11px]">
                        {r.case_count} Cases
                      </span>
                    </div>
                  ))}
                </div>

                <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3.5 text-xs space-y-2 pt-3">
                  <p className="font-bold text-slate-900">{t.geoCoords} ({selectedCity || "Pune"}):</p>
                  <p className="text-slate-600 font-mono text-[11px]">
                    Lat: {data?.city_breakdown?.find(c => c.city === selectedCity)?.lat.toFixed(4) || "18.5204"}, 
                    Lng: {data?.city_breakdown?.find(c => c.city === selectedCity)?.lng.toFixed(4) || "73.8567"}
                  </p>
                  <span className="text-[10px] text-slate-500 block leading-relaxed">
                    {t.geoCoordsSub}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: VISUAL CHARTS & ANALYTICS */}
        {activeTab === "CHARTS" && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded-2xl border border-purple-200 bg-purple-50/50 p-4">
                <p className="text-[10px] font-bold uppercase tracking-wider text-purple-700">Enforcement Districts</p>
                <p className="mt-1 text-2xl font-black text-purple-950">{data?.city_breakdown?.length || 5}</p>
                <span className="text-[11px] text-purple-600">Active regional surveillance zones</span>
              </div>
              <div className="rounded-2xl border border-rose-200 bg-rose-50/50 p-4">
                <p className="text-[10px] font-bold uppercase tracking-wider text-rose-700">Total Flagged Infractions</p>
                <p className="mt-1 text-2xl font-black text-rose-950">
                  {(data?.city_breakdown || []).reduce((acc, curr) => acc + curr.violations, 0)}
                </p>
                <span className="text-[11px] text-rose-600">LMPC non-compliance count</span>
              </div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50/50 p-4">
                <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700">Package Tampering Alerts</p>
                <p className="mt-1 text-2xl font-black text-amber-950">
                  {(data?.city_breakdown || []).reduce((acc, curr) => acc + curr.integrity_alerts, 0)}
                </p>
                <span className="text-[11px] text-amber-600">Price sticker / dual MRP suspects</span>
              </div>
              <div className="rounded-2xl border border-blue-200 bg-blue-50/50 p-4">
                <p className="text-[10px] font-bold uppercase tracking-wider text-blue-700">Consumer Escalations</p>
                <p className="mt-1 text-2xl font-black text-blue-950">
                  {(data?.city_breakdown || []).reduce((acc, curr) => acc + curr.consumer_reports, 0)}
                </p>
                <span className="text-[11px] text-blue-600">Public grievances & social tickets</span>
              </div>
            </div>

            {/* District Comparison Bar Chart */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-2xs space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                    <BarChart3 className="h-4 w-4 text-purple-800" />
                    District Case & Violation Volume Analysis
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Comparative workload across surveillance zones (Total Cases vs Verified Violations)
                  </p>
                </div>
                <div className="flex items-center gap-4 text-xs font-semibold">
                  <span className="flex items-center gap-1.5 text-slate-600">
                    <span className="h-3 w-3 rounded bg-purple-700" /> Total Cases
                  </span>
                  <span className="flex items-center gap-1.5 text-slate-600">
                    <span className="h-3 w-3 rounded bg-rose-500" /> Flagged Violations
                  </span>
                </div>
              </div>

              <div className="space-y-4 pt-2">
                {(data?.city_breakdown || [
                  { city: "Pune", total_cases: 18, violations: 8, integrity_alerts: 4, consumer_reports: 6 },
                  { city: "Mumbai", total_cases: 14, violations: 5, integrity_alerts: 2, consumer_reports: 7 },
                  { city: "Nagpur", total_cases: 9, violations: 4, integrity_alerts: 1, consumer_reports: 4 },
                  { city: "Nashik", total_cases: 7, violations: 3, integrity_alerts: 2, consumer_reports: 2 },
                  { city: "Aurangabad", total_cases: 5, violations: 2, integrity_alerts: 1, consumer_reports: 2 },
                ]).map((c) => {
                  const maxCase = 20;
                  const totalPct = Math.min(100, Math.round((c.total_cases / maxCase) * 100));
                  const violPct = Math.min(100, Math.round((c.violations / maxCase) * 100));

                  return (
                    <div key={c.city} className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-slate-900 w-24 sm:w-32 truncate">{c.city}</span>
                        <span className="font-mono text-slate-500 text-[11px]">
                          <strong>{c.total_cases}</strong> cases · <span className="text-rose-600 font-bold">{c.violations} violations</span>
                        </span>
                      </div>
                      <div className="h-4 w-full rounded-full bg-slate-100 overflow-hidden flex">
                        <div
                          style={{ width: `${totalPct}%` }}
                          className="h-full bg-purple-700 rounded-l-full relative group transition-all duration-500"
                        />
                        <div
                          style={{ width: `${violPct}%` }}
                          className="h-full bg-rose-500 rounded-r-full -ml-1 transition-all duration-500"
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Two-Column Grid: Statutory Domains & Violation Categories */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
                <div className="border-b border-slate-100 pb-3">
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                    <PieChart className="h-4 w-4 text-purple-700" />
                    Statutory Domain Distribution
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Proportion of complaints across regulatory jurisdictions
                  </p>
                </div>

                <div className="space-y-3 pt-1">
                  {[
                    { domain: "LMPC Act (Rule 6, Weight, Dual MRP)", count: data?.domain_distribution?.LMPC || 12, color: "bg-purple-700", text: "text-purple-800" },
                    { domain: "FSSAI (License & Expiry)", count: data?.domain_distribution?.FSSAI || 5, color: "bg-amber-500", text: "text-amber-700" },
                    { domain: "Package Integrity (Tampering / Alteration)", count: data?.domain_distribution?.INTEGRITY || 4, color: "bg-blue-600", text: "text-blue-700" },
                    { domain: "Counterfeit & Duplicate Goods", count: data?.domain_distribution?.COUNTERFEIT || 2, color: "bg-rose-600", text: "text-rose-700" },
                  ].map((item) => {
                    const total = 23;
                    const pct = Math.round((item.count / total) * 100);
                    return (
                      <div key={item.domain} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="font-semibold text-slate-800">{item.domain}</span>
                          <span className={`font-mono font-bold ${item.text}`}>{item.count} ({pct}%)</span>
                        </div>
                        <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                          <div style={{ width: `${pct}%` }} className={`h-full ${item.color} rounded-full transition-all duration-500`} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
                <div className="border-b border-slate-100 pb-3">
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                    <Store className="h-4 w-4 text-emerald-700" />
                    Top Commodity Categories Flagged
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Packaged commodity types under high consumer surveillance
                  </p>
                </div>

                <div className="space-y-3 pt-1">
                  {[
                    { cat: "Packaged Food & Confectionery (Gems, Bru)", count: 9, pct: 45, color: "bg-emerald-600" },
                    { cat: "Edible Oils & Beverages", count: 5, pct: 25, color: "bg-blue-600" },
                    { cat: "Cosmetics & Personal Care", count: 4, pct: 20, color: "bg-purple-600" },
                    { cat: "Household Cleaning & Detergents", count: 2, pct: 10, color: "bg-amber-600" },
                  ].map((c) => (
                    <div key={c.cat} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="font-semibold text-slate-800">{c.cat}</span>
                        <span className="font-mono text-slate-500">{c.count} items ({c.pct}%)</span>
                      </div>
                      <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                        <div style={{ width: `${c.pct}%` }} className={`h-full ${c.color} rounded-full transition-all duration-500`} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: FIELD INSPECTOR LIVE SCANS & REPORTS */}
        {activeTab === "FIELD_SCANS" && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-4">
              <div>
                <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                  <FileText className="h-5 w-5 text-purple-700" />
                  {t.fieldScansTitle}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {t.fieldScansSub}
                </p>
              </div>

              {/* Status Filter & Scan Action */}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => onNavigate?.("scan")}
                  className="flex items-center gap-1.5 rounded-xl bg-purple-700 hover:bg-purple-800 text-white font-bold px-3 py-1.5 text-xs shadow-md transition active:scale-95"
                >
                  <Camera className="h-3.5 w-3.5 text-saffron-300" />
                  <span>{lang === "hi" ? "नया स्कैन" : lang === "mr" ? "नवीन स्कॅन" : "Scan Package"}</span>
                </button>
                <div className="h-4 w-px bg-slate-300 mx-0.5 hidden sm:block" />
                <button
                  type="button"
                  onClick={() => setScanFilter("ALL")}
                  className={`rounded-xl px-3 py-1.5 text-xs font-bold transition shadow-xs ${
                    scanFilter === "ALL" ? "bg-purple-800 text-white" : "bg-white text-slate-700 border border-slate-200"
                  }`}
                >
                  {t.allStatus} ({inspections.length})
                </button>
                <button
                  type="button"
                  onClick={() => setScanFilter("NON_COMPLIANT")}
                  className={`rounded-xl px-3 py-1.5 text-xs font-bold transition shadow-xs ${
                    scanFilter === "NON_COMPLIANT" ? "bg-rose-700 text-white" : "bg-white text-rose-700 border border-rose-200"
                  }`}
                >
                  {t.onlyViolations} ({inspections.filter(x => x.status === "VIOLATION").length})
                </button>
                <button
                  type="button"
                  onClick={() => setScanFilter("VERIFIED")}
                  className={`rounded-xl px-3 py-1.5 text-xs font-bold transition shadow-xs ${
                    scanFilter === "VERIFIED" ? "bg-emerald-700 text-white" : "bg-white text-emerald-700 border border-emerald-200"
                  }`}
                >
                  {t.onlyVerified} ({inspections.filter(x => x.status === "COMPLIANT").length})
                </button>
              </div>
            </div>

            {/* Inspections Grid */}
            {filteredInspections.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center text-xs text-slate-500">
                {t.noScans}
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {filteredInspections.map((scan) => {
                  const isNonCompliant = scan.status === "VIOLATION";
                  const isVerified = scan.status === "COMPLIANT";
                  const mrpVal = scan.declarations?.find(d => d.field.toLowerCase().includes("mrp"))?.value || "₹185.00";
                  const netQtyVal = scan.declarations?.find(d => d.field.toLowerCase().includes("net"))?.value || "250 g";

                  return (
                    <div
                      key={scan.id}
                      className={`rounded-2xl border bg-white p-5 shadow-2xs flex flex-col justify-between transition-all hover:shadow-md ${
                        isNonCompliant ? "border-rose-300 ring-1 ring-rose-200" : "border-slate-200"
                      }`}
                    >
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[10px] text-slate-400 truncate max-w-[120px]">
                            {scan.productId || scan.id}
                          </span>
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold ${
                              isNonCompliant
                                ? "bg-rose-100 text-rose-800 border border-rose-200"
                                : isVerified
                                ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                                : "bg-amber-100 text-amber-800 border border-amber-200"
                            }`}
                          >
                            {isNonCompliant ? "VIOLATION" : isVerified ? "COMPLIANT" : scan.status}
                          </span>
                        </div>

                        <div>
                          <h3 className="text-sm font-extrabold text-slate-900 line-clamp-1">
                            {scan.product || "Packaged Commodity"}
                          </h3>
                          <p className="text-[11px] text-slate-500 font-medium">
                            {scan.category || "General Commodity"}
                          </p>
                        </div>

                        {/* Specs & Declarations */}
                        <div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-2.5 text-[11px] border border-slate-100">
                          <div>
                            <span className="text-slate-400 block text-[9px] uppercase font-bold">{t.mrp}</span>
                            <span className="font-bold text-slate-900">{mrpVal}</span>
                          </div>
                          <div>
                            <span className="text-slate-400 block text-[9px] uppercase font-bold">{t.netQty}</span>
                            <span className="font-bold text-slate-900">{netQtyVal}</span>
                          </div>
                          <div>
                            <span className="text-slate-400 block text-[9px] uppercase font-bold">{t.inspector}</span>
                            <span className="font-medium text-slate-700">{scan.manufacturer || "Field Inspector Squad #4"}</span>
                          </div>
                          <div>
                            <span className="text-slate-400 block text-[9px] uppercase font-bold">{t.scanDate}</span>
                            <span className="font-medium text-slate-700">{scan.dateLabel || "Today"}</span>
                          </div>
                        </div>

                        {/* Violations Flagged if any */}
                        {isNonCompliant && (
                          <div className="rounded-xl bg-rose-50 border border-rose-200 p-2.5 text-[11px] text-rose-900 space-y-1">
                            <div className="flex items-center gap-1 font-bold text-rose-800">
                              <AlertTriangle className="h-3.5 w-3.5" />
                              <span>LMPC Rule 6 Non-Compliance Flagged</span>
                            </div>
                            <p className="text-[10px] text-rose-700">
                              Mandatory Unit Sale Price (USP) missing or Net Quantity below declared tolerance.
                            </p>
                          </div>
                        )}
                      </div>

                      {/* 1-Click View Full Inspection Docket */}
                      <div className="pt-4 border-t border-slate-100 mt-4">
                        <button
                          type="button"
                          onClick={() => onOpenInspection?.(scan.id)}
                          className="w-full flex items-center justify-center gap-2 rounded-xl bg-purple-700 text-white font-bold py-2 text-xs hover:bg-purple-800 transition shadow-2xs"
                        >
                          <Eye className="h-3.5 w-3.5" />
                          {t.viewDocket}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 4: STATUTORY RULE ENGINE ENFORCEMENT */}
        {activeTab === "RULE_ENGINE" && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-4">
              <div>
                <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                  <Gavel className="h-5 w-5 text-purple-700" />
                  {t.ruleEngineTitle}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {t.ruleEngineSub}
                </p>
              </div>

              {/* Enforcement Sensitivity Switcher */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setStrictEnforcement(!strictEnforcement)}
                  className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition shadow-xs ${
                    strictEnforcement ? "bg-emerald-700 text-white" : "bg-white text-slate-800 border border-slate-300"
                  }`}
                >
                  <Sliders className="h-4 w-4" />
                  {strictEnforcement ? t.enforcementStrict : t.standardRules}
                </button>
              </div>
            </div>

            {/* 4 Statutory Policy Cards */}
            <div className="grid gap-4 md:grid-cols-2">
              {/* Rule 6 Card */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
                <div className="flex items-center justify-between">
                  <span className="rounded-full bg-purple-100 text-purple-900 font-extrabold px-2.5 py-0.5 text-[10px]">
                    LMPC Rule 6(1)
                  </span>
                  <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                    AUTOMATED CHECK ACTIVE
                  </span>
                </div>
                <h3 className="text-sm font-black text-slate-900">{t.rule6Title}</h3>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  {t.rule6Desc}
                </p>
                <div className="pt-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleIssueSection36("Rule 6(1) Mandatory Declarations")}
                    className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl border border-purple-300 bg-purple-50 px-3 py-2 text-xs font-bold text-purple-900 hover:bg-purple-100 transition"
                  >
                    <Send className="h-3.5 w-3.5" />
                    {t.issueNotice}
                  </button>
                </div>
              </div>

              {/* Rule 6(11) USP Card */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
                <div className="flex items-center justify-between">
                  <span className="rounded-full bg-blue-100 text-blue-900 font-extrabold px-2.5 py-0.5 text-[10px]">
                    LMPC Rule 6(11)
                  </span>
                  <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                    UNIT PRICING CODEX
                  </span>
                </div>
                <h3 className="text-sm font-black text-slate-900">{t.rule12Title}</h3>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  {t.rule12Desc}
                </p>
                <div className="pt-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleIssueSection36("Rule 6(11) Unit Sale Price Omission")}
                    className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl border border-blue-300 bg-blue-50 px-3 py-2 text-xs font-bold text-blue-900 hover:bg-blue-100 transition"
                  >
                    <Send className="h-3.5 w-3.5" />
                    {t.issueNotice}
                  </button>
                </div>
              </div>

              {/* Rule 26 Seizures Card */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
                <div className="flex items-center justify-between">
                  <span className="rounded-full bg-amber-100 text-amber-900 font-extrabold px-2.5 py-0.5 text-[10px]">
                    LMPC Rule 26
                  </span>
                  <span className="text-[10px] font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200">
                    SEIZURE AUTHORIZATION
                  </span>
                </div>
                <h3 className="text-sm font-black text-slate-900">{t.rule26Title}</h3>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  {t.rule26Desc}
                </p>
                <div className="pt-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleIssueSection36("Rule 26 Non-Standard Packaging")}
                    className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-900 hover:bg-amber-100 transition"
                  >
                    <Scale className="h-3.5 w-3.5" />
                    {t.issueNotice}
                  </button>
                </div>
              </div>

              {/* Section 36 Penalty Matrix Card */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
                <div className="flex items-center justify-between">
                  <span className="rounded-full bg-rose-100 text-rose-900 font-extrabold px-2.5 py-0.5 text-[10px]">
                    Legal Metrology Act Section 36
                  </span>
                  <span className="text-[10px] font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded-md border border-rose-200">
                    PENALTY FINE CODEX
                  </span>
                </div>
                <h3 className="text-sm font-black text-slate-900">{t.section36Title}</h3>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  {t.section36Desc}
                </p>
                <div className="pt-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleDispatchSquad("Regional Industrial Zones")}
                    className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-purple-700 text-white px-3 py-2 text-xs font-bold hover:bg-purple-800 transition"
                  >
                    <ShieldCheck className="h-3.5 w-3.5" />
                    {t.dispatchSquad}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 5: PUBLIC COMPLAINTS & SOCIAL INTELLIGENCE */}
        {activeTab === "SOCIAL_INTEL" && (
          <div className="space-y-6">
            {/* Demo Header Notice */}
            <div className="rounded-2xl border border-amber-500/40 bg-amber-50 p-4 text-xs space-y-1">
              <div className="flex items-center gap-2 text-amber-900 font-bold">
                <ShieldAlert className="h-4 w-4" />
                <span>{t.socialDemo}</span>
              </div>
              <p className="text-amber-800 text-[11px] leading-relaxed">
                {t.socialDemoDesc}
              </p>
            </div>

            {/* AI Narrative */}
            {socialSummary?.ai_regional_summary && (
              <div className="rounded-2xl border border-purple-200 bg-purple-50/50 p-5 shadow-xs space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-purple-700" />
                    <span className="rounded-full bg-purple-200 text-purple-950 px-2.5 py-0.5 text-[10px] font-black uppercase">
                      AI Public Intelligence Synthesis
                    </span>
                    <span className="text-[11px] text-slate-600 font-medium">
                      Grounded strictly in {socialSummary.total_signals_analyzed} processed public signals
                    </span>
                  </div>
                </div>
                {renderFormattedAnalysis(socialSummary.ai_regional_summary)}
              </div>
            )}

            {/* Active Clusters */}
            {socialSummary?.active_clusters && socialSummary.active_clusters.length > 0 && (
              <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4 shadow-2xs">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <Layers className="h-4 w-4 text-purple-700" />
                    <h3 className="text-sm font-bold text-slate-900">Detected Multi-Post Recurrent Clusters</h3>
                  </div>
                  <span className="text-xs text-slate-500">Grouped by Brand, Region & Violation Pattern</span>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  {socialSummary.active_clusters.map((c, idx) => (
                    <div key={idx} className="rounded-xl border border-rose-200 bg-rose-50/50 p-3.5 text-xs space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="rounded-full bg-rose-100 text-rose-800 font-bold px-2 py-0.5 text-[10px]">
                          {c.count} Related Grievances
                        </span>
                        <span className="text-[11px] font-bold text-slate-900">Cluster #{idx + 1}</span>
                      </div>
                      <p className="font-semibold text-slate-900 text-xs">{c.cluster_label}</p>
                      <div className="flex flex-wrap gap-1 text-[10px] text-slate-600">
                        {c.members.map((m) => (
                          <span key={m.mention_id} className="rounded bg-white border border-slate-200 px-1.5 py-0.5">
                            {m.author} ({m.city}) • Priority {m.priority_score}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Grievance list */}
            <div className="grid gap-4 md:grid-cols-2">
              {socialLoading ? (
                <p className="text-xs text-slate-500 py-8">Ingesting and prioritizing public mentions…</p>
              ) : mentions.length === 0 ? (
                <p className="text-xs text-slate-500 py-8 col-span-2 text-center">
                  No public signals matching active filters.
                </p>
              ) : (
                mentions.map((m) => (
                  <div
                    key={m.mention_id}
                    className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3.5 shadow-2xs flex flex-col justify-between"
                  >
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-mono font-bold text-slate-700">
                            {m.source_platform}
                          </span>
                          <span className="text-xs text-slate-600 font-semibold">{m.author_handle}</span>
                        </div>
                        <span className="rounded-full bg-rose-100 text-rose-800 px-2.5 py-0.5 text-[10px] font-bold border border-rose-200">
                          {m.severity} • {m.priority_score}/100
                        </span>
                      </div>

                      <p className="text-xs leading-relaxed text-slate-800 bg-slate-50 p-3 rounded-xl border border-slate-100 font-medium">
                        "{m.clean_text}"
                      </p>

                      <div className="grid grid-cols-2 gap-2 text-[11px] rounded-xl bg-slate-50 p-3 border border-slate-100">
                        <div>
                          <span className="text-slate-400 block text-[10px] uppercase font-bold">Product / Brand</span>
                          <strong className="text-slate-900">{m.product_brand || "Packaged Commodity"}</strong>
                        </div>
                        <div>
                          <span className="text-slate-400 block text-[10px] uppercase font-bold">Location</span>
                          <strong className="text-slate-900">📍 {m.district_or_city}, {m.state}</strong>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between gap-2 pt-3 border-t border-slate-100 text-xs">
                      <span className="text-slate-500 text-[11px]">
                        Status: <strong className="text-slate-900">{m.review_status}</strong>
                      </span>
                      {m.review_status === "SHORTLISTED" ? (
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleConvertMention(m.mention_id)}
                            className="rounded-xl bg-rose-700 text-white font-bold px-3 py-1 text-[11px] hover:bg-rose-800 transition"
                          >
                            Convert to Case
                          </button>
                          <button
                            type="button"
                            onClick={() => handleAssignInspector(m.mention_id)}
                            className="rounded-xl border border-slate-300 bg-white text-slate-800 font-bold px-3 py-1 text-[11px] hover:bg-slate-50 transition"
                          >
                            Dispatch Squad
                          </button>
                        </div>
                      ) : (
                        <span className="text-emerald-700 font-bold inline-flex items-center gap-1 text-[11px]">
                          <CheckCircle2 className="h-3.5 w-3.5" /> Action Logged
                        </span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
