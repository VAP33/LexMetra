export type Language = "en" | "hi" | "mr";

export interface Translations {
  // Navigation & General
  portalTitle: string;
  portalSubtitle: string;
  dashboard: string;
  history: string;
  register: string;
  reviewQueue: string;
  profile: string;
  scan: string;
  startScan: string;
  officerLogin: string;
  consumerPortal: string;
  authorityDashboard: string;
  regionalIntelligence: string;
  logout: string;
  back: string;
  retry: string;
  cancel: string;
  continue: string;
  save: string;
  download: string;

  // Metrics & Headers
  inspectionsToday: string;
  violationsFlagged: string;
  pendingReviews: string;
  verifiedClean: string;
  highRiskProducts: string;
  ofTotalLogged: string;
  rule6NonCompliance: string;
  requireHumanSignOff: string;
  statutoryConforming: string;
  actionRequired: string;
  recentInspections: string;
  allLogs: string;
  noInspectionsFound: string;
  readyToScreen: string;

  // Camera & Scan
  multiAngleCapture: string;
  scanProduct: string;
  facesOf6: string;
  cameraPreview: string;
  positionPackageInside: string;
  enableCamera: string;
  gallery: string;
  captureGuidance: string;
  max6FacesReached: string;
  cameraUnavailable: string;

  // Scan Details
  productIdentity: string;
  productId: string;
  saleType: string;
  category: string;
  netQuantity: string;
  unit: string;
  mrpOptional: string;
  pdpArea: string;
  runComplianceCheck: string;
  autoDetected: string;

  // Results & Declarations
  inspectionResult: string;
  compliant: string;
  violation: string;
  reviewRequired: string;
  exempt: string;
  verified: string;
  missing: string;
  statutoryField: string;
  extractedValue: string;
  statutoryRule: string;
  verificationStatus: string;
  findings: string;
  evidence: string;
  viewEvidence: string;
  reportPreview: string;
  exportPdf: string;
  saveInspection: string;
  escalateToAuthority: string;
  aiAssistant: string;
}

export const translations: Record<Language, Translations> = {
  en: {
    portalTitle: "LEXMETRA",
    portalSubtitle: "Legal Metrology Compliance Portal • Govt. of India",
    dashboard: "Dashboard",
    history: "History",
    register: "Compliance Register",
    reviewQueue: "Review Queue",
    profile: "Profile",
    scan: "New Scan",
    startScan: "Start Inspection Scan",
    officerLogin: "Inspector Login",
    consumerPortal: "Consumer Grievance Portal",
    authorityDashboard: "Authority Enforcement",
    regionalIntelligence: "Regional Analytics",
    logout: "Sign out",
    back: "Back",
    retry: "Retry",
    cancel: "Cancel",
    continue: "Continue",
    save: "Save",
    download: "Download",

    inspectionsToday: "Inspections Today",
    violationsFlagged: "Violations Flagged",
    pendingReviews: "Pending Reviews",
    verifiedClean: "Verified Compliant",
    highRiskProducts: "High Risk Goods",
    ofTotalLogged: "of total logged",
    rule6NonCompliance: "Rule 6 violations",
    requireHumanSignOff: "Require inspector verification",
    statutoryConforming: "100% compliant",
    actionRequired: "Enforcement required",
    recentInspections: "Recent Statutory Inspections",
    allLogs: "View complete audit register",
    noInspectionsFound: "No inspections recorded yet",
    readyToScreen: "Ready to inspect package labels under LMPC Rules 2011",

    multiAngleCapture: "Multi-Angle Capture",
    scanProduct: "Scan Package",
    facesOf6: "faces",
    cameraPreview: "Camera Preview",
    positionPackageInside: "Position package label face inside the frame.",
    enableCamera: "Enable Camera",
    gallery: "Upload Photos",
    captureGuidance: "Capture up to 6 package faces (Front PDP, Back, Sides, Top/Bottom) for 360° compliance verification.",
    max6FacesReached: "Maximum 6 package surfaces captured. Ready to proceed.",
    cameraUnavailable: "Camera unavailable — upload photos from device gallery.",

    productIdentity: "Package & Product Details",
    productId: "Product / Barcode ID",
    saleType: "Sale Type",
    category: "Commodity Category",
    netQuantity: "Declared Net Quantity",
    unit: "Unit of Measure",
    mrpOptional: "Maximum Retail Price (MRP ₹)",
    pdpArea: "Principal Display Panel (PDP) Area",
    runComplianceCheck: "Run LMPC Compliance Check",
    autoDetected: "Auto-detected by CV",

    inspectionResult: "Statutory Inspection Verdict",
    compliant: "COMPLIANT",
    violation: "STATUTORY VIOLATION",
    reviewRequired: "REVIEW REQUIRED",
    exempt: "EXEMPT",
    verified: "Verified",
    missing: "Missing / Non-Compliant",
    statutoryField: "Statutory Field",
    extractedValue: "Extracted Value",
    statutoryRule: "Statutory Rule",
    verificationStatus: "Verification Status",
    findings: "Statutory Rule Compliance Findings",
    evidence: "Visual Photographic Evidence",
    viewEvidence: "View Evidence & BBoxes",
    reportPreview: "Inspection Report",
    exportPdf: "Export Official PDF",
    saveInspection: "Save Inspection",
    escalateToAuthority: "Escalate to Authority",
    aiAssistant: "AI Statutory Assistant",
  },
  hi: {
    portalTitle: "लेक्समेट्रा (LEXMETRA)",
    portalSubtitle: "विधिक मापविज्ञान अनुपालन पोर्टल • विधिक मापविज्ञान प्रभाग, भारत सरकार",
    dashboard: "डैशबोर्ड",
    history: "निरीक्षण इतिहास",
    register: "अनुपालन रजिस्टर",
    reviewQueue: "समीक्षा कतार",
    profile: "प्रोफ़ाइल",
    scan: "नया स्कैन",
    startScan: "निरीक्षण स्कैन शुरू करें",
    officerLogin: "अधिकारी लॉगिन",
    consumerPortal: "उपभोक्ता शिकायत पोर्टल",
    authorityDashboard: "प्रवर्तन प्राधिकरण",
    regionalIntelligence: "क्षेत्रीय विश्लेषण",
    logout: "लॉग आउट",
    back: "वापस",
    retry: "पुनः प्रयास",
    cancel: "रद्द करें",
    continue: "आगे बढ़ें",
    save: "सुरक्षित करें",
    download: "डाउनलोड",

    inspectionsToday: "आज के कुल निरीक्षण",
    violationsFlagged: "चिह्नित उल्लंघन",
    pendingReviews: "लंबित समीक्षाएं",
    verifiedClean: "सत्यापित अनुपालन",
    highRiskProducts: "उच्च जोखिम उत्पाद",
    ofTotalLogged: "कुल दर्ज रिकॉर्ड",
    rule6NonCompliance: "नियम 6 का उल्लंघन",
    requireHumanSignOff: "अधिकारी सत्यापन आवश्यक",
    statutoryConforming: "100% वैधानिक अनुपालन",
    actionRequired: "कार्रवाई आवश्यक",
    recentInspections: "हाल के वैधानिक निरीक्षण",
    allLogs: "संपूर्ण ऑडिट रजिस्टर देखें",
    noInspectionsFound: "अभी तक कोई निरीक्षण दर्ज नहीं है",
    readyToScreen: "विधिक मापविज्ञान नियम 2011 के तहत पैकेज लेबल जांच के लिए तैयार",

    multiAngleCapture: "मल्टी-एंगल पैकेज कैप्चर",
    scanProduct: "पैकेज स्कैन करें",
    facesOf6: "सतह",
    cameraPreview: "कैमरा पूर्वावलोकन",
    positionPackageInside: "पैकेज लेबल को फ्रेम के अंदर रखें।",
    enableCamera: "कैमरा चालू करें",
    gallery: "गैलरी से फोटो चुनें",
    captureGuidance: "360° विधिक अनुपालन जांच हेतु पैकेज की 6 सतहों (मुख्य फ्रंट, बैक, साइड, टॉप/बॉटम) की तस्वीरें लें।",
    max6FacesReached: "अधिकतम 6 सतहें कैप्चर हो चुकी हैं। आगे बढ़ने के लिए तैयार।",
    cameraUnavailable: "कैमरा उपलब्ध नहीं है — गैलरी से तस्वीरें अपलोड करें।",

    productIdentity: "पैकेज एवं उत्पाद विवरण",
    productId: "उत्पाद / बारकोड आईडी",
    saleType: "बिक्री प्रकार",
    category: "वस्तु श्रेणी",
    netQuantity: "घोषित शुद्ध मात्रा",
    unit: "माप की इकाई",
    mrpOptional: "अधिकतम खुदरा मूल्य (MRP ₹)",
    pdpArea: "मुख्य प्रदर्शन पैनल (PDP) क्षेत्रफल",
    runComplianceCheck: "विधिक मापविज्ञान अनुपालन जांचें",
    autoDetected: "स्वचालित रूप से पहचाना गया",

    inspectionResult: "वैधानिक निरीक्षण परिणाम",
    compliant: "पूर्ण अनुपालित (COMPLIANT)",
    violation: "वैधानिक उल्लंघन (VIOLATION)",
    reviewRequired: "समीक्षा आवश्यक (REVIEW)",
    exempt: "छूट प्राप्त (EXEMPT)",
    verified: "सत्यापित",
    missing: "अनुपस्थित / गैर-अनुपालित",
    statutoryField: "वैधानिक घोषणा क्षेत्र",
    extractedValue: "प्राप्त मान",
    statutoryRule: "विधिक नियम",
    verificationStatus: "सत्यापन स्थिति",
    findings: "वैधानिक नियम अनुपालन निष्कर्ष (LMPC 2011)",
    evidence: "प्रमाणिक फोटोग्राफिक साक्ष्य",
    viewEvidence: "साक्ष्य एवं बाउंडिंग बॉक्स देखें",
    reportPreview: "निरीक्षण रिपोर्ट",
    exportPdf: "आधिकारिक PDF डाउनलोड करें",
    saveInspection: "निरीक्षण सहेजें",
    escalateToAuthority: "प्राधिकरण को शिकायत भेजें",
    aiAssistant: "एआई विधिक सहायक",
  },
  mr: {
    portalTitle: "लेक्समेट्रा (LEXMETRA)",
    portalSubtitle: "वैधानिक मापनशास्त्र अनुपालन पोर्टल • कायदेशीर मापनशास्त्र विभाग, भारत सरकार",
    dashboard: "डॅशबोर्ड",
    history: "तपासणी इतिहास",
    register: "अनुपालन नोंदवही",
    reviewQueue: "पुनरावलोकन रांग",
    profile: "प्रोफाइल",
    scan: "नवीन स्कॅन",
    startScan: "तपासणी स्कॅन सुरू करा",
    officerLogin: "अधिकारी लॉगिन",
    consumerPortal: "ग्राहक तक्रार निवारण पोर्टल",
    authorityDashboard: "अंमलबजावणी प्राधिकरण",
    regionalIntelligence: "प्रादेशिक विश्लेषण",
    logout: "बाहेर पडा",
    back: "मागे",
    retry: "पुन्हा प्रयत्न करा",
    cancel: "रद्द करा",
    continue: "पुढे जा",
    save: "जतन करा",
    download: "डाउनलोड",

    inspectionsToday: "आजच्या एकूण तपासण्या",
    violationsFlagged: "नोंदवलेले कायदेशीर उल्लंघन",
    pendingReviews: "प्रलंबित पुनरावलोकन",
    verifiedClean: "सत्यापित अनुपालन",
    highRiskProducts: "संशयास्पद उत्पादने",
    ofTotalLogged: "एकूण नोंदी",
    rule6NonCompliance: "नियम ६ चे उल्लंघन",
    requireHumanSignOff: "अधिकारी पडताळणी आवश्यक",
    statutoryConforming: "१००% कायदेशीर अनुपालन",
    actionRequired: "कारवाई आवश्यक",
    recentInspections: "अलीकडील वैधानिक तपासण्या",
    allLogs: "संपूर्ण ऑडिट रजिस्टर पहा",
    noInspectionsFound: "अद्याप कोणतीही तपासणी नोंदवलेली नाही",
    readyToScreen: "वैधानिक मापनशास्त्र नियम २०११ नुसार लेबल तपासणीसाठी सज्ज",

    multiAngleCapture: "मल्टी-अँगल पॅकेज कॅप्चर",
    scanProduct: "पॅकेज स्कॅन करा",
    facesOf6: "पृष्ठभाग",
    cameraPreview: "कॅमेरा पूर्वावलोकन",
    positionPackageInside: "पॅकेजचे लेबल फ्रेमच्या आत ठेवा.",
    enableCamera: "कॅमेरा सुरू करा",
    gallery: "गॅलरीतून फोटो निवडा",
    captureGuidance: "३६०° कायदेशीर तपासणीसाठी पॅकेजच्या ६ बाजूंचे (मुख्य फ्रंट, बॅक, बाजू, टॉप/तळ) फोटो घ्या.",
    max6FacesReached: "कमाल ६ बाजूंचे फोटो घेतले आहेत. पुढे जाण्यासाठी तयार.",
    cameraUnavailable: "कॅमेरा उपलब्ध नाही — गॅलरीतून फोटो अपलोड करा.",

    productIdentity: "पॅकेज व उत्पादन तपशील",
    productId: "उत्पादन / बारकोड आयडी",
    saleType: "विक्री प्रकार",
    category: "वस्तू श्रेणी",
    netQuantity: "घोषित निव्वळ वजन / प्रमाण",
    unit: "मोजमाप एकक",
    mrpOptional: "कमाल किरकोळ किंमत (MRP ₹)",
    pdpArea: "मुख्य प्रदर्शन पॅनेल (PDP) क्षेत्रफळ",
    runComplianceCheck: "वैधानिक अनुपालन तपासा",
    autoDetected: "स्वयंचलितपणे ओळखले",

    inspectionResult: "वैधानिक तपासणी निकाल",
    compliant: "पूर्ण अनुपालन (COMPLIANT)",
    violation: "कायदेशीर उल्लंघन (VIOLATION)",
    reviewRequired: "पुनरावलोकन आवश्यक (REVIEW)",
    exempt: "सूट मिळालेली (EXEMPT)",
    verified: "सत्यापित",
    missing: "अनुपस्थित / गैर-अनुपालन",
    statutoryField: "वैधानिक घोषणा बाब",
    extractedValue: "मिळालेले मूल्य",
    statutoryRule: "कायदेशीर नियम",
    verificationStatus: "पडताळणी स्थिती",
    findings: "वैधानिक नियम अनुपालन निष्कर्ष (LMPC 2011)",
    evidence: "छायाचित्र पुरावे",
    viewEvidence: "पुरावे व बाउंडिंग बॉक्स पहा",
    reportPreview: "तपासणी अहवाल",
    exportPdf: "अधिकृत PDF डाउनलोड करा",
    saveInspection: "तपासणी जतन करा",
    escalateToAuthority: "प्राधिकरणाकडे तक्रार नोंदवा",
    aiAssistant: "एआय कायदेशीर सहाय्यक",
  },
};

export function getTranslation(lang: Language): Translations {
  return translations[lang] || translations.en;
}
