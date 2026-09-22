// ---------------------------------------------------------------------------
// LexMetra - Dynamic Page Metadata & SEO Controller
// Dynamically updates document.title and meta tags for every route view
// ---------------------------------------------------------------------------

import { type AppView } from "./nav-history";
import { type Language } from "./i18n";

export interface PageMeta {
  title: string;
  description: string;
}

export const VIEW_METADATA: Record<
  AppView | "notFound" | "privacy" | "terms" | "thankYou" | "emptyState",
  Record<Language, PageMeta>
> = {
  landing: {
    en: {
      title: "LEXMETRA — Statutory Legal Metrology & Compliance Platform",
      description: "AI-powered statutory package inspection platform under the Legal Metrology Act, 2009. Automated Rule 12 Unit Sale Price cross-checking and official PDF audit dockets.",
    },
    hi: {
      title: "लेक्समेट्रा — वैधानिक विधिक मापविज्ञान अनुपालन मंच",
      description: "विधिक मापविज्ञान अधिनियम, 2009 के तहत स्वचालित बहु-सतह एआई निरीक्षण। तत्काल इकाई मूल्य सत्यापन और आधिकारिक पीडीएफ डॉकेट।",
    },
    mr: {
      title: "लेक्समेट्रा — कायदेशीर मापनशास्त्र अनुपालन आणि तपासणी",
      description: "कायदेशीर मापनशास्त्र कायदा, २००९ अंतर्गत एआय बहु-पृष्ठभाग तपासणी आणि अधिकृत पीडीएफ अहवाल.",
    },
  },
  home: {
    en: {
      title: "Inspector Operations Command Center | LexMetra",
      description: "Live statutory inspection feed, rapid package scanner launcher, and enforcement workflow dashboard.",
    },
    hi: {
      title: "निरीक्षक कमान केंद्र | लेक्समेट्रा",
      description: "सक्रिय वैधानिक निरीक्षण फ़ीड, पैकेज स्कैनर और प्रवर्तन कार्यप्रवाह डैशबोर्ड।",
    },
    mr: {
      title: "तपासणी अधिकारी नियंत्रण केंद्र | लेक्समेट्रा",
      description: "थेट वैधानिक तपासणी फीड, पॅकेज स्कॅनर आणि अंमलबजावणी डॅशबोर्ड.",
    },
  },
  scan: {
    en: {
      title: "Multi-Panel Camera Scanner | LexMetra Inspection",
      description: "Synchronized 6-face package capture with homography perspective normalization and real-time bounding box localization.",
    },
    hi: {
      title: "बहु-सतह कैमरा स्कैनर | लेक्समेट्रा निरीक्षण",
      description: "पैकेज की सभी सतहों का सटीक कंप्यूटर विज़न स्कैन और वास्तविक समय ओसीआर पहचान।",
    },
    mr: {
      title: "बहु-पृष्ठभाग कॅमेरा स्कॅनर | लेक्समेट्रा तपासणी",
      description: "पॅकेजच्या सर्व पृष्ठांचे संगणक दृष्टी स्कॅन आणि तात्काळ ओसीआर ओळख.",
    },
  },
  preprocessing: {
    en: {
      title: "Homography Normalization & Image Pipeline | LexMetra",
      description: "Perspective rectification, sharpness scoring, and shadow suppression for statutory OCR readiness.",
    },
    hi: {
      title: "छवि सामान्यीकरण एवं प्रसंस्करण | लेक्समेट्रा",
      description: "वैधानिक ओसीआर के लिए छवि सुधार एवं गुणवत्ता विश्लेषण।",
    },
    mr: {
      title: "प्रतिमा सामान्यीकरण व प्रक्रिया | लेक्समेट्रा",
      description: "वैधानिक ओसीआरसाठी प्रतिमा सुधारणा आणि गुणवत्ता विश्लेषण.",
    },
  },
  scanDetails: {
    en: {
      title: "Package Classification & Details | LexMetra",
      description: "Confirm product category, sale type (retail, wholesale, e-commerce), and bundle configurations.",
    },
    hi: {
      title: "पैकेज वर्गीकरण एवं विवरण | लेक्समेट्रा",
      description: "उत्पाद श्रेणी, विक्रय प्रकार और पैकेजिंग विनिर्देशों की पुष्टि करें।",
    },
    mr: {
      title: "पॅकेज वर्गीकरण आणि तपशील | लेक्समेट्रा",
      description: "उत्पादन श्रेणी, विक्री प्रकार आणि पॅकेजिंग तपशीलांची पुष्टी करा.",
    },
  },
  processing: {
    en: {
      title: "Perception & Rule Engine Running | LexMetra",
      description: "Extracting declarations, evaluating 13 mandatory statutory rules, and computing Rule 12 USP arithmetics.",
    },
    hi: {
      title: "नियम मूल्यांकन एवं प्रसंस्करण प्रगति पर | लेक्समेट्रा",
      description: "घोषणाओं का निष्कर्षण, 13 अनिवार्य नियमों का मूल्यांकन और इकाई मूल्य गणना।",
    },
    mr: {
      title: "नियम मूल्यांकन व प्रक्रिया सुरू | लेक्समेट्रा",
      description: "घोषणांचे विश्लेषण, 13 अनिवार्य नियमांचे मूल्यांकन आणि युनिट किंमत गणना.",
    },
  },
  result: {
    en: {
      title: "Statutory Compliance Inspection Findings | LexMetra",
      description: "Comprehensive violation summary, Rule 12 USP verification, and evidence bounding boxes.",
    },
    hi: {
      title: "वैधानिक अनुपालन निरीक्षण परिणाम | लेक्समेट्रा",
      description: "उल्लंघन सारांश, नियम 12 इकाई मूल्य सत्यापन और साक्ष्य क्रॉप।",
    },
    mr: {
      title: "वैधानिक अनुपालन तपासणी निष्कर्ष | लेक्समेट्रा",
      description: "उल्लंघन सारांश, नियम 12 युनिट किंमत पडताळणी आणि पुरावे क्रॉप.",
    },
  },
  detail: {
    en: {
      title: "Inspection Record Dossier | LexMetra",
      description: "Detailed compliance declaration checklist, evidence surfaces, and regulatory verification status.",
    },
    hi: {
      title: "निरीक्षण अभिलेख फ़ाइल | लेक्समेट्रा",
      description: "विस्तृत अनुपालन घोषणा चेकलिस्ट और वैधानिक सत्यापन स्थिति।",
    },
    mr: {
      title: "तपासणी नोंद दस्तऐवज | लेक्समेट्रा",
      description: "तपशीलवार अनुपालन घोषणा चेकलिस्ट आणि वैधानिक पडताळणी स्थिती.",
    },
  },
  evidence: {
    en: {
      title: "Forensic Evidence Map & Bounding Boxes | LexMetra",
      description: "Interactive multi-surface evidence overlay with synchronized polygon crops and confidence scores.",
    },
    hi: {
      title: "न्यायालयीन साक्ष्य मानचित्र | लेक्समेट्रा",
      description: "इंटरैक्टिव बहु-सतह साक्ष्य मानचित्र और सत्यापन स्कोर।",
    },
    mr: {
      title: "फॉरेन्सिक पुरावा नकाशा | लेक्समेट्रा",
      description: "परस्परसंवादी बहु-पृष्ठभाग पुरावा नकाशा आणि पडताळणी गुण.",
    },
  },
  report: {
    en: {
      title: "Official Enforcement Docket & PDF Export | LexMetra",
      description: "Court-admissible inspection report certificate with cryptographic SHA-256 hash and officer stamp.",
    },
    hi: {
      title: "आधिकारिक प्रवर्तन डॉकेट एवं पीडीएफ निर्यात | लेक्समेट्रा",
      description: "क्रिप्टोग्राफिक हैश और अधिकारी मुहर के साथ न्यायालयीन मान्य निरीक्षण रिपोर्ट।",
    },
    mr: {
      title: "अधिकृत अंमलबजावणी डॉकेट व पीडीएफ | लेक्समेट्रा",
      description: "क्रिप्टोग्राफिक हॅश आणि अधिकारी शिक्क्यानिशी न्यायालयीन मान्य तपासणी अहवाल.",
    },
  },
  history: {
    en: {
      title: "Statutory Inspection History | LexMetra",
      description: "Chronological log of scanned packaged commodities, compliance flags, and violation records.",
    },
    hi: {
      title: "निरीक्षण इतिहास | लेक्समेट्रा",
      description: "स्कैन की गई पैकेज्ड वस्तुओं, अनुपालन स्थिति और उल्लंघन रिकॉर्ड का कालानुक्रमिक विवरण।",
    },
    mr: {
      title: "तपासणी इतिहास | लेक्समेट्रा",
      description: "स्कॅन केलेल्या पॅकेज केलेल्या वस्तू, अनुपालन स्थिती आणि उल्लंघन नोंदींचा कालक्रमानुसार अहवाल.",
    },
  },
  register: {
    en: {
      title: "Official Legal Metrology Register | LexMetra",
      description: "Permanent statutory register of reviewed and verified packaged commodity inspections.",
    },
    hi: {
      title: "आधिकारिक विधिक मापविज्ञान रजिस्टर | लेक्समेट्रा",
      description: "समीक्षित और सत्यापित पैकेज्ड कमोडिटी निरीक्षणों का स्थायी वैधानिक रजिस्टर।",
    },
    mr: {
      title: "अधिकृत कायदेशीर मापनशास्त्र नोंदवही | लेक्समेट्रा",
      description: "पुनरावलोकन केलेल्या आणि सत्यापित पॅकेज्ड कमोडिटी तपासणीची कायमस्वरूपी वैधानिक नोंदवही.",
    },
  },
  reviewQueue: {
    en: {
      title: "Actionable Review & Enforcement Queue | LexMetra",
      description: "Priority queue of commodities with missing declarations, negative tolerances, or anomalous unit sale prices.",
    },
    hi: {
      title: "समीक्षा एवं प्रवर्तन कतार | लेक्समेट्रा",
      description: "लापता घोषणाओं या मूल्य विसंगतियों वाली वस्तुओं की प्राथमिकता समीक्षा कतार।",
    },
    mr: {
      title: "पुनरावलोकन व अंमलबजावणी रांग | लेक्समेट्रा",
      description: "गहाळ घोषणा किंवा किंमत तफावत असलेल्या वस्तूंची प्राधान्य पुनरावलोकन रांग.",
    },
  },
  regulatory: {
    en: {
      title: "Regulatory Intelligence & Gazette Rules | LexMetra",
      description: "Up-to-date gazette notifications, Legal Metrology amendments, and exemption directories.",
    },
    hi: {
      title: "विधिक नियम एवं राजपत्र आसूचना | लेक्समेट्रा",
      description: "अद्यतन राजपत्र अधिसूचनाएं, विधिक मापविज्ञान संशोधन और छूट निर्देशिका।",
    },
    mr: {
      title: "वैधानिक नियम व राजपत्र गुप्तचर | लेक्समेट्रा",
      description: "अद्ययावत राजपत्र अधिसूचना, कायदेशीर मापनशास्त्र दुरुस्त्या आणि सूट निर्देशिका.",
    },
  },
  authority: {
    en: {
      title: "Enforcement Action Dockets & Legal Notices | LexMetra",
      description: "Automated issuance of Section 18 / Rule 6 statutory notices and compounding proceedings.",
    },
    hi: {
      title: "प्राधिकारी डॉकेट एवं विधिक नोटिस | लेक्समेट्रा",
      description: "धारा 18 एवं नियम 6 के अंतर्गत वैधानिक नोटिस और कंपाउंडिंग कार्यवाही।",
    },
    mr: {
      title: "प्राधिकरण डॉकेट आणि कायदेशीर नोटिसा | लेक्समेट्रा",
      description: "कलम 18 आणि नियम 6 अंतर्गत वैधानिक नोटिसा आणि तडजोड कार्यवाही.",
    },
  },
  customer: {
    en: {
      title: "Citizen Consumer Verification & Grievance Portal | LexMetra",
      description: "Verify retail package compliance, check MRP/USP fairness, and lodge statutory grievances with National Consumer Helpline 1915 integration.",
    },
    hi: {
      title: "नागरिक उपभोक्ता सत्यापन एवं शिकायत पोर्टल | लेक्समेट्रा",
      description: "खुदरा पैकेज अनुपालन की जांच करें, एमआरपी निष्पक्षता देखें और राष्ट्रीय उपभोक्ता हेल्पलाइन 1915 पर शिकायत दर्ज करें।",
    },
    mr: {
      title: "नागरिक ग्राहक पडताळणी आणि तक्रार पोर्टल | लेक्समेट्रा",
      description: "किरकोळ पॅकेज अनुपालनाची पडताळणी करा, एमआरपी तपासा आणि राष्ट्रीय ग्राहक हेल्पलाइन 1915 वर तक्रार नोंदवा.",
    },
  },
  seniorRegional: {
    en: {
      title: "Senior Directorate Intelligence & Regional Analytics | LexMetra",
      description: "Inter-district compliance heatmaps, systematic brand non-compliance detection, and regional enforcement dashboards.",
    },
    hi: {
      title: "वरिष्ठ निदेशालय आसूचना एवं क्षेत्रीय विश्लेषण | लेक्समेट्रा",
      description: "अंतर-जिला अनुपालन हीटमैप, ब्रांड उल्लंघन पहचान और क्षेत्रीय प्रवर्तन डैशबोर्ड।",
    },
    mr: {
      title: "वरिष्ठ संचालनालय गुप्तचर आणि प्रादेशिक विश्लेषण | लेक्समेट्रा",
      description: "आंतर-जिल्हा अनुपालन नकाशे, ब्रँड उल्लंघन ओळख आणि प्रादेशिक अंमलबजावणी डॅशबोर्ड.",
    },
  },
  login: {
    en: {
      title: "Authorized Officer Authentication | LexMetra",
      description: "Secure role-based authentication for Legal Metrology Officers, Inspectors, and Controllers.",
    },
    hi: {
      title: "अधिकृत अधिकारी लॉगिन | लेक्समेट्रा",
      description: "विधिक मापविज्ञान अधिकारियों एवं निरीक्षकों के लिए सुरक्षित प्रमाणीकरण।",
    },
    mr: {
      title: "अधिकृत अधिकारी लॉगिन | लेक्समेट्रा",
      description: "कायदेशीर मापनशास्त्र अधिकारी आणि निरीक्षकांसाठी सुरक्षित प्रमाणीकरण.",
    },
  },
  profile: {
    en: {
      title: "Officer Profile & Calibration Settings | LexMetra",
      description: "Inspector credentials, jurisdiction assignment, camera calibration tokens, and accessibility preferences.",
    },
    hi: {
      title: "अधिकारी प्रोफ़ाइल एवं सेटिंग्स | लेक्समेट्रा",
      description: "निरीक्षक साख, अधिकार क्षेत्र और कैमरा अंशांकन प्राथमिकताएं।",
    },
    mr: {
      title: "अधिकारी प्रोफाइल आणि सेटिंग्ज | लेक्समेट्रा",
      description: "निरीक्षक प्रमाणपत्रे, अधिकारक्षेत्र आणि कॅमेरा कॅलिब्रेशन प्राधान्ये.",
    },
  },
  privacy: {
    en: {
      title: "Privacy Policy & Data Protection | LexMetra",
      description: "Data handling, statutory image retention, and privacy safeguards under the Digital Personal Data Protection Act, 2023.",
    },
    hi: {
      title: "गोपनीयता नीति एवं डेटा सुरक्षा | लेक्समेट्रा",
      description: "डिजिटल व्यक्तिगत डेटा संरक्षण अधिनियम, 2023 के अंतर्गत डेटा प्रबंधन और सुरक्षा उपाय।",
    },
    mr: {
      title: "गोपनीयता धोरण आणि डेटा संरक्षण | लेक्समेट्रा",
      description: "डिजिटल वैयक्तिक डेटा संरक्षण कायदा, २०२३ अंतर्गत डेटा हाताळणी आणि गोपनीयता उपाय.",
    },
  },
  terms: {
    en: {
      title: "Terms of Service & Statutory Usage | LexMetra",
      description: "Official usage policies, inspection evidence disclaimers, and statutory authority protocols under Legal Metrology Act, 2009.",
    },
    hi: {
      title: "सेवा की शर्तें एवं वैधानिक उपयोग | लेक्समेट्रा",
      description: "विधिक मापविज्ञान अधिनियम, 2009 के तहत आधिकारिक उपयोग नीतियां और प्रवर्तन प्रोटोकॉल।",
    },
    mr: {
      title: "सेवा अटी आणि वैधानिक वापर | लेक्समेट्रा",
      description: "कायदेशीर मापनशास्त्र कायदा, २००९ अंतर्गत अधिकृत वापर धोरणे आणि अंमलबजावणी प्रोटोकॉल.",
    },
  },
  notFound: {
    en: {
      title: "Page Not Found (404) | LexMetra",
      description: "The requested compliance resource or docket could not be located in the register.",
    },
    hi: {
      title: "पृष्ठ नहीं मिला (404) | लेक्समेट्रा",
      description: "अनुरोधित वैधानिक संसाधन या डॉकेट रजिस्टर में नहीं मिला।",
    },
    mr: {
      title: "पृष्ठ आढळले नाही (404) | लेक्समेट्रा",
      description: "विनंती केलेले वैधानिक संसाधन किंवा डॉकेट नोंदवहीत सापडले नाही.",
    },
  },
  thankYou: {
    en: {
      title: "Inspection Submitted & Registered | LexMetra",
      description: "Confirmation of inspection docket recording and statutory register indexing.",
    },
    hi: {
      title: "निरीक्षण सफलतापूर्वक दर्ज | लेक्समेट्रा",
      description: "निरीक्षण डॉकेट के सफल पंजीकरण और अनुपालन सूची में जोड़ने की पुष्टि।",
    },
    mr: {
      title: "तपासणी यशस्वीरित्या नोंदवली गेली | लेक्समेट्रा",
      description: "तपासणी डॉकेटची यशस्वी नोंद आणि अनुपालन सूचीमध्ये समाविष्ट केल्याची पुष्टी.",
    },
  },
  emptyState: {
    en: {
      title: "No Inspections Found | LexMetra",
      description: "Start a new statutory package inspection to populate the compliance register.",
    },
    hi: {
      title: "कोई निरीक्षण नहीं मिला | लेक्समेट्रा",
      description: "अनुपालन रजिस्टर में प्रविष्टि जोड़ने के लिए नया पैकेज निरीक्षण शुरू करें।",
    },
    mr: {
      title: "कोणतीही तपासणी आढळली नाही | लेक्समेट्रा",
      description: "अनुपालन नोंदवहीत प्रविष्टी जोडण्यासाठी नवीन पॅकेज तपासणी सुरू करा.",
    },
  },
};

export function updatePageMetadata(
  viewKey: AppView | "notFound" | "privacy" | "terms" | "thankYou" | "emptyState",
  lang: Language = "en"
): void {
  const metaGroup = VIEW_METADATA[viewKey] || VIEW_METADATA.landing;
  const current = metaGroup[lang] || metaGroup.en;

  // Update document title
  document.title = current.title;

  // Update meta name="description"
  let descTag = document.querySelector('meta[name="description"]');
  if (!descTag) {
    descTag = document.createElement("meta");
    descTag.setAttribute("name", "description");
    document.head.appendChild(descTag);
  }
  descTag.setAttribute("content", current.description);

  // Update og:title and og:description
  const ogTitle = document.querySelector('meta[property="og:title"]');
  if (ogTitle) ogTitle.setAttribute("content", current.title);

  const ogDesc = document.querySelector('meta[property="og:description"]');
  if (ogDesc) ogDesc.setAttribute("content", current.description);

  // Update twitter:title and twitter:description
  const twTitle = document.querySelector('meta[name="twitter:title"]');
  if (twTitle) twTitle.setAttribute("content", current.title);

  const twDesc = document.querySelector('meta[name="twitter:description"]');
  if (twDesc) twDesc.setAttribute("content", current.description);
}
