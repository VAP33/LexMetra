// ---------------------------------------------------------------------------
// LexMetra - Statutory Legal Metrology Compliance Platform
// Root Application Orchestrator & Native Browser History Controller
// ---------------------------------------------------------------------------

import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";

import {
  type Inspection,
  type ScanDetails,
} from "@/lib/types";
import {
  ApiError,
  clearSession,
  getInspectionDetail,
  getStoredToken,
  getStoredUser,
  listInspections,
  markReviewed,
  type AuthedUser,
  resolveImageUrl,
  scanPackagesMulti,
} from "@/lib/api-client";
import { fromInspectionRow, fromScanResponse } from "@/lib/adapters";
import { dataUrlToBlob } from "@/lib/data-url";
import { type Language } from "@/lib/i18n";
import {
  type AppView as View,
  pushNavRoute,
  replaceNavRoute,
  setupNavListener,
  parseRouteHash,
} from "@/lib/nav-history";

// Modular Views
import { Header as AppHeader } from "./app-header";
import { DesktopRail, BottomNav } from "./app-navigation";
import { HomeView } from "./home-view";
import { ListView } from "./history-view";
import { ReviewQueueView } from "./review-queue-view";
import { ScanView } from "./scan-capture-view";
import { ScanDetailsView } from "./scan-details-view";
import {
  PreprocessingRunner,
  ProcessingRunner,
  ProcessingErrorView,
} from "./scan-processing-views";
import { ResultView } from "./result-view";
import { EvidenceView } from "./evidence-view";
import { ReportView } from "./report-view";
import { LoginView, ProfileView } from "./auth-views";
import { LandingPage } from "./landing-page";
import { RegulatoryIntelligenceDashboard } from "./regulatory-intelligence-dashboard";
import { CustomerDashboard } from "./customer-dashboard";
import { SeniorRegionalDashboard } from "./senior-regional-dashboard";
import { AuthorityDashboardView, MultilingualAssistantWidget } from "./usp-components";

export function InspectionApp() {
  const [user, setUser] = useState<AuthedUser | null>(() => (getStoredToken() ? getStoredUser() : null));

  // Initialize view from URL hash or stored credentials
  const [view, setView] = useState<View>(() => {
    const hashRoute = parseRouteHash();
    if (hashRoute) return hashRoute.view;
    const token = getStoredToken();
    if (!token) return "landing";
    const u = getStoredUser();
    if (u?.role === "customer" || u?.role === "consumer") return "customer";
    if (u?.role === "authority") return "authority";
    if (u?.role === "admin" || u?.role === "senior_inspector") return "seniorRegional";
    return "home";
  });

  const [lang, setLang] = useState<Language>(() => {
    const saved = localStorage.getItem("lexmetra_lang");
    if (saved === "en" || saved === "hi" || saved === "mr") return saved as Language;
    return "en";
  });

  const [inspections, setInspections] = useState<Inspection[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | undefined>(undefined);
  const [selected, setSelected] = useState<Inspection | undefined>(undefined);
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const [canonicalImages, setCanonicalImages] = useState<string[]>([]);
  const [preprocessingError, setPreprocessingError] = useState<string | undefined>(undefined);
  const [processingError, setProcessingError] = useState<string | undefined>(undefined);
  const [toast, setToast] = useState<string | undefined>(undefined);

  function handleSetLang(newLang: Language) {
    setLang(newLang);
    localStorage.setItem("lexmetra_lang", newLang);
  }

  function handleAuthExpiry(err: unknown): boolean {
    if (err instanceof ApiError && err.status === 401) {
      clearSession();
      setUser(null);
      return true;
    }
    return false;
  }

  async function refreshInspections() {
    setListLoading(true);
    setListError(undefined);
    try {
      const rows = await listInspections({ limit: 100 });
      setInspections(rows.map(fromInspectionRow));
    } catch (err) {
      if (handleAuthExpiry(err)) return;
      setListError(err instanceof ApiError ? err.message : "Could not load inspections.");
    } finally {
      setListLoading(false);
    }
  }

  // Sync with browser back/forward buttons (popstate events)
  useEffect(() => {
    const unsubscribe = setupNavListener((route) => {
      setView(route.view);
      if (route.id) {
        // Find existing or fetch detail
        setInspections((current) => {
          const found = current.find((item) => item.id === route.id);
          if (found) {
            setSelected(found);
          } else {
            getInspectionDetail(route.id!)
              .then((row) => setSelected(fromInspectionRow(row)))
              .catch(console.error);
          }
          return current;
        });
      } else if (!["result", "detail", "evidence", "report"].includes(route.view)) {
        setSelected(undefined);
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    return unsubscribe;
  }, []);

  // Restore initial inspection detail if hash provided an ID
  useEffect(() => {
    const hashRoute = parseRouteHash();
    if (hashRoute?.id) {
      getInspectionDetail(hashRoute.id)
        .then((row) => setSelected(fromInspectionRow(row)))
        .catch(console.error);
    }
  }, []);

  useEffect(() => {
    if (user) {
      refreshInspections();
    } else {
      setListLoading(false);
      setListError(undefined);
    }
  }, [user]);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(undefined), 2600);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  function go(nextView: View, targetInspectionId?: string, replace = false) {
    let targetView = nextView;
    // Strict RBAC Route Isolation: Allow scanning and product review for consumers while keeping workbench isolated
    if (user?.role === "customer" || user?.role === "consumer") {
      const allowedViews: View[] = [
        "customer",
        "landing",
        "profile",
        "login",
        "scan",
        "preprocessing",
        "scanDetails",
        "processing",
        "result",
        "detail",
        "evidence",
        "report",
        "history",
        "register",
      ];
      if (!allowedViews.includes(targetView)) {
        targetView = "customer";
      }
    }

    const inspectionId = targetInspectionId || (["result", "detail", "evidence", "report"].includes(targetView) ? selected?.id : undefined);

    if (replace) {
      replaceNavRoute(targetView, inspectionId);
    } else {
      pushNavRoute(targetView, inspectionId);
    }

    setView(targetView);
    if (!["result", "detail", "evidence", "report"].includes(targetView)) setSelected(undefined);
    if (targetView === "scan") {
      setPendingImages([]);
      setCanonicalImages([]);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function handleOpen(inspection: Inspection) {
    setSelected(inspection);
    go("detail", inspection.id);
    getInspectionDetail(inspection.id)
      .then((row) => setSelected(fromInspectionRow(row)))
      .catch((err) => { handleAuthExpiry(err); });
  }

  function onCaptured(images: string[]) {
    setPendingImages(images);
    setCanonicalImages(images);
    setPreprocessingError(undefined);
    submitDetails({
      productId: "",
      saleType: "retail",
      productCategory: "food_general",
      isExportOnly: false,
      retailBundleCount: 1,
      isImported: false,
    }, images);
  }

  function handlePreprocessingDone(canonUrls: string[]) {
    const urls = canonUrls.length > 0 ? canonUrls : pendingImages;
    setCanonicalImages(urls);
    submitDetails({
      productId: "",
      saleType: "retail",
      productCategory: "food_general",
      isExportOnly: false,
      retailBundleCount: 1,
      isImported: false,
    }, urls);
  }

  function handlePreprocessingError(message: string) {
    setPreprocessingError(message);
  }

  const pendingRunRef = useRef<() => Promise<Inspection>>(() => Promise.reject(new Error("no scan queued")));

  async function runScanSession(details: ScanDetails, overrideImages?: string[]): Promise<Inspection> {
    const targetImages = (overrideImages && overrideImages.length > 0)
      ? overrideImages
      : (canonicalImages.length > 0 ? canonicalImages : pendingImages);
    try {
      const blobs: Blob[] = [];
      for (let i = 0; i < targetImages.length; i++) {
        const imgRef = targetImages[i];
        let blob: Blob;
        if (imgRef.startsWith("data:") || imgRef.startsWith("blob:")) {
          blob = dataUrlToBlob(imgRef);
        } else {
          const fullUrl = resolveImageUrl(imgRef) || imgRef;
          const fetched = await fetch(fullUrl);
          blob = await fetched.blob();
        }
        blobs.push(blob);
      }

      // Execute high-speed multimodal scan endpoint (/scan)
      const rawScanRes = await scanPackagesMulti(blobs, details);
      return fromScanResponse(rawScanRes, { productId: details.productId }, targetImages[0] || pendingImages[0]);
    } catch (err) {
      console.error("[Inspection Flow Error] /scan request failed:", err);
      throw err;
    }
  }

  function submitDetails(details: ScanDetails, overrideImages?: string[]) {
    setProcessingError(undefined);
    pendingRunRef.current = () => runScanSession(details, overrideImages);
    go("processing", undefined, true);
  }

  function handleProcessingDone(inspection: Inspection) {
    setSelected(inspection);
    setInspections((current) => [inspection, ...current]);
    go("result", inspection.id, true);
  }

  function handleProcessingError(message: string) {
    setProcessingError(message);
  }

  function handleInspectionUpdated(updated: Inspection) {
    setSelected(updated);
    setInspections((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    setToast("Declaration updated & rules re-evaluated");
  }

  async function saveAndRegister() {
    if (!selected) return;
    try {
      await markReviewed(selected.id, "Saved to compliance register by inspector.");
      const saved = { ...selected, saved: true, reviewed: true };
      setSelected(saved);
      setInspections((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      setToast("Added to Compliance Register");
    } catch (err) {
      if (handleAuthExpiry(err)) return;
      setToast(err instanceof ApiError ? err.message : "Could not save — check your connection.");
    }
  }

  function handleLogout() {
    clearSession();
    setUser(null);
    setInspections([]);
    go("login");
  }

  function handleBackNav() {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      go(user ? "home" : "landing");
    }
  }

  if (view === "login" && !user) {
    return (
      <LoginView
        onLoggedIn={(u, target) => {
          setUser(u);
          go(target || (u.role === "admin" ? "seniorRegional" : "home"));
        }}
        onConsumerPortal={() => go("customer")}
      />
    );
  }

  if (view === "landing" && !user) {
    return (
      <LandingPage
        onStartScan={() => go("scan")}
        onOfficerLogin={() => go("login")}
        onConsumerPortal={() => go("customer")}
        lang={lang}
        onLanguageChange={handleSetLang}
      />
    );
  }

  const content =
    view === "landing" ? (
      <LandingPage
        onStartScan={() => go("scan")}
        onOfficerLogin={() => go("login")}
        onConsumerPortal={() => go("customer")}
        lang={lang}
        onLanguageChange={handleSetLang}
      />
    ) : view === "home" ? (
      <HomeView inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onLogout={handleLogout} onNavigate={go} onOpen={handleOpen} lang={lang} onSetLang={handleSetLang} />
    ) : view === "history" ? (
      <ListView
        kind="history"
        inspections={inspections}
        loading={listLoading}
        error={listError}
        onRetry={refreshInspections}
        onOpen={handleOpen}
        onNavigate={go}
        lang={lang}
        onLanguageChange={handleSetLang}
        user={user}
        onLogout={handleLogout}
      />
    ) : view === "register" ? (
      <ListView
        kind="register"
        inspections={inspections}
        loading={listLoading}
        error={listError}
        onRetry={refreshInspections}
        onOpen={handleOpen}
        onNavigate={go}
        lang={lang}
        onLanguageChange={handleSetLang}
        user={user}
        onLogout={handleLogout}
      />
    ) : view === "reviewQueue" ? (
      <ReviewQueueView
        inspections={inspections}
        loading={listLoading}
        error={listError}
        onRetry={refreshInspections}
        onOpen={handleOpen}
        onNavigate={go}
        lang={lang}
        onLanguageChange={handleSetLang}
        user={user}
        onLogout={handleLogout}
      />
    ) : view === "profile" ? (
      <ProfileView user={user} onLogout={handleLogout} onNavigate={go} lang={lang} onSetLang={handleSetLang} />
    ) : view === "scan" ? (
      <ScanView onCaptured={onCaptured} onBack={handleBackNav} lang={lang} />
    ) : view === "preprocessing" ? (
      preprocessingError ? (
        <ProcessingErrorView message={preprocessingError} onRetry={() => onCaptured(pendingImages)} onCancel={handleBackNav} />
      ) : (
        <PreprocessingRunner images={pendingImages} onDone={handlePreprocessingDone} onError={handlePreprocessingError} />
      )
    ) : view === "scanDetails" ? (
      <ScanDetailsView images={canonicalImages.length > 0 ? canonicalImages : pendingImages} onSubmit={submitDetails} onBack={handleBackNav} />
    ) : view === "processing" ? (
      processingError ? (
        <ProcessingErrorView message={processingError} onRetry={() => setProcessingError(undefined)} onCancel={handleBackNav} />
      ) : (
        <ProcessingRunner onRun={() => pendingRunRef.current()} onDone={handleProcessingDone} onError={handleProcessingError} />
      )
    ) : selected && (view === "result" || view === "detail") ? (
      <ResultView
        inspection={selected}
        onSave={saveAndRegister}
        onOpenEvidence={() => go("evidence", selected.id)}
        onOpenReport={() => go("report", selected.id)}
        onNew={() => go("scan")}
        onInspectionUpdated={handleInspectionUpdated}
      />
    ) : selected && view === "evidence" ? (
      <EvidenceView inspection={selected} onBack={handleBackNav} />
    ) : selected && view === "report" ? (
      <ReportView inspection={selected} onBack={handleBackNav} />
    ) : view === "regulatory" ? (
      <div className="space-y-4">
        <AppHeader
          title={lang === "hi" ? "विधिक नियम एवं राजपत्र आसूचना" : lang === "mr" ? "वैधानिक नियम व राजपत्र गुप्तचर" : "Regulatory Rules & Intelligence"}
          online={!listError}
          lang={lang}
          onLanguageChange={handleSetLang}
          user={user}
          onLogout={handleLogout}
          onNavigate={go}
        />
        <RegulatoryIntelligenceDashboard onBack={handleBackNav} />
      </div>
    ) : view === "authority" ? (
      <div className="space-y-4">
        <AppHeader
          title={lang === "hi" ? "विधिक मापविज्ञान प्राधिकारी डॉकेट" : lang === "mr" ? "कायदेशीर मापनशास्त्र प्राधिकरण डॉकेट" : "Authority Action Dockets & Enforcement"}
          online={!listError}
          lang={lang}
          onLanguageChange={handleSetLang}
          user={user}
          onLogout={handleLogout}
          onNavigate={go}
        />
        <AuthorityDashboardView onBack={handleBackNav} />
      </div>
    ) : view === "customer" ? (
      <CustomerDashboard
        onBack={() => go("landing")}
        onOpenInspection={handleOpen}
        onStartScan={() => go("scan")}
        onOfficerLogin={() => go("login")}
        inspections={inspections}
        lang={lang}
        onLanguageChange={handleSetLang}
        user={user}
        onLogout={handleLogout}
        onNavigate={go}
      />
    ) : view === "seniorRegional" ? (
      <SeniorRegionalDashboard
        onBack={handleBackNav}
        onOpenInspection={(id: string) => {
          const item = inspections.find((x) => x.id === id);
          if (item) handleOpen(item);
        }}
        inspections={inspections}
        lang={lang}
        onLanguageChange={handleSetLang}
        user={user}
        onLogout={handleLogout}
        onNavigate={go}
      />
    ) : (
      <HomeView inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onLogout={handleLogout} onNavigate={go} onOpen={handleOpen} lang={lang} onSetLang={handleSetLang} user={user} />
    );

  const isLanding = view === "landing";

  return (
    <div className="min-h-screen bg-background text-foreground">
      {!isLanding && <DesktopRail view={view} onNavigate={go} lang={lang} role={user?.role || (user == null ? "customer" : undefined)} />}
      {!isLanding ? <div className="md:pl-64">{content}</div> : content}
      {!isLanding && <BottomNav view={view} onNavigate={go} lang={lang} role={user?.role || (user == null ? "customer" : undefined)} />}
      <MultilingualAssistantWidget currentInspection={selected || inspections[0]} lang={lang} onLanguageChange={handleSetLang} />
      {toast && (
        <div className="fixed bottom-24 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-xl md:bottom-8">
          <Check className="h-4 w-4 text-success" />{toast}
        </div>
      )}
    </div>
  );
}


export { Header as AppHeader } from "./app-header";
export { LexMetraLogo } from "./ui-primitives";
