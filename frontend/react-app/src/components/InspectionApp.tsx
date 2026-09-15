import { Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { LoginView } from "@/components/auth/LoginView";
import { ProfileView } from "@/components/auth/ProfileView";
import { EvidenceView } from "@/components/evidence/EvidenceView";
import { ListView, ReviewQueueView } from "@/components/history/ListViews";
import { HomeView } from "@/components/home/HomeView";
import { BottomNav, DesktopRail } from "@/components/layout";
import { ReportView } from "@/components/report/ReportView";
import { ResultView } from "@/components/result/ResultView";
import { ProcessingErrorView, ProcessingRunner, ScanDetailsView, ScanView } from "@/components/scan/ScanFlow";
import { fromFinalizedInspection, fromInspectionRow } from "@/lib/adapters";
import {
  ApiError,
  addSessionCapture,
  clearSession,
  createSession,
  finalizeSession,
  getInspectionDetail,
  getStoredToken,
  getStoredUser,
  listInspections,
  markReviewed,
  type AuthedUser,
  type SurfaceType,
} from "@/lib/api-client";
import { dataUrlToBlob } from "@/lib/data-url";
import type { Inspection, ScanDetails } from "@/lib/types";
import { isFocusedFlow, type View } from "@/lib/views";

export function InspectionApp() {
  const [user, setUser] = useState<AuthedUser | null>(() => (getStoredToken() ? getStoredUser() : null));
  const [view, setView] = useState<View>("home");
  const [inspections, setInspections] = useState<Inspection[]>([]);
  const [reviewQueue, setReviewQueue] = useState<Inspection[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | undefined>(undefined);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState<string | undefined>(undefined);
  const [selected, setSelected] = useState<Inspection | undefined>(undefined);
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const [processingError, setProcessingError] = useState<string | undefined>(undefined);
  const [markReviewSubmitting, setMarkReviewSubmitting] = useState(false);
  const [markReviewError, setMarkReviewError] = useState<string | undefined>(undefined);
  const [toast, setToast] = useState<string | undefined>(undefined);

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

  async function refreshReviewQueue() {
    setReviewLoading(true);
    setReviewError(undefined);
    try {
      const rows = await listInspections({ limit: 100, needsReview: true });
      setReviewQueue(rows.map(fromInspectionRow));
    } catch (err) {
      if (handleAuthExpiry(err)) return;
      setReviewError(err instanceof ApiError ? err.message : "Could not load the review queue.");
    } finally {
      setReviewLoading(false);
    }
  }

  useEffect(() => { if (user) refreshInspections(); }, [user]);

  useEffect(() => {
    if (user && view === "reviewQueue") void refreshReviewQueue();
  }, [user, view]);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(undefined), 2600);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  function go(nextView: View) {
    setView(nextView);
    if (!["result", "detail", "evidence", "report"].includes(nextView)) setSelected(undefined);
    if (nextView === "scan") setPendingImages([]);
    setMarkReviewError(undefined);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function handleOpen(inspection: Inspection) {
    setSelected(inspection);
    setView("detail");
    setMarkReviewError(undefined);
    getInspectionDetail(inspection.id)
      .then((row) => setSelected(fromInspectionRow(row)))
      .catch((err) => { handleAuthExpiry(err); });
  }

  function onCaptured(images: string[]) { setPendingImages(images); setView("scanDetails"); }

  const pendingRunRef = useRef<() => Promise<Inspection>>(() => Promise.reject(new Error("no scan queued")));

  async function runScanSession(details: ScanDetails): Promise<Inspection> {
    const session = await createSession({
      productId: details.productId,
      saleType: details.saleType,
      productCategory: details.productCategory,
      netQuantityValue: details.netQuantityValue,
      netQuantityUnit: details.netQuantityUnit,
      mrp: details.mrp,
      pdpAreaCm2: details.pdpAreaCm2,
      isExportOnly: details.isExportOnly,
      retailBundleCount: details.retailBundleCount,
      isImported: details.isImported,
    });

    const surfaceForIndex = (i: number): SurfaceType => (i === 0 ? "FRONT" : i === 1 ? "BACK" : "SIDE");
    for (let i = 0; i < pendingImages.length; i++) {
      const blob = dataUrlToBlob(pendingImages[i]);
      await addSessionCapture(session.session_id, blob, surfaceForIndex(i));
    }

    const inspection = await finalizeSession(session.session_id);
    const adapted = fromFinalizedInspection(inspection, { productId: details.productId }, pendingImages[0]);
    return { ...adapted, mrp: details.mrp ?? adapted.mrp ?? null };
  }

  function submitDetails(details: ScanDetails) {
    setProcessingError(undefined);
    setView("processing");
    pendingRunRef.current = () => runScanSession(details);
  }

  function handleProcessingDone(inspection: Inspection) {
    setSelected(inspection);
    setInspections((current) => [inspection, ...current]);
    setView("result");
  }

  function handleProcessingError(message: string) {
    setProcessingError(message);
  }

  async function handleMarkReviewed(note: string) {
    if (!selected) return;
    setMarkReviewSubmitting(true);
    setMarkReviewError(undefined);
    try {
      const res = await markReviewed(selected.id, note);
      const saved: Inspection = {
        ...selected,
        saved: true,
        reviewed: true,
        reviewerNote: res.review_note ?? note,
      };
      setSelected(saved);
      setInspections((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      setReviewQueue((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      setToast("Marked reviewed");
    } catch (err) {
      if (handleAuthExpiry(err)) return;
      setMarkReviewError(err instanceof ApiError ? err.message : "Could not mark reviewed — check your role and connection.");
    } finally {
      setMarkReviewSubmitting(false);
    }
  }

  function handleLogout() {
    clearSession();
    setUser(null);
    setInspections([]);
    setReviewQueue([]);
    setView("home");
  }

  if (!user) {
    return <LoginView onLoggedIn={setUser} />;
  }

  const content =
    view === "home" ? (
      <HomeView inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onLogout={handleLogout} onNavigate={go} onOpen={handleOpen} />
    ) : view === "history" ? (
      <ListView kind="history" inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onOpen={handleOpen} onNavigate={go} />
    ) : view === "register" ? (
      <ListView kind="register" inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onOpen={handleOpen} onNavigate={go} />
    ) : view === "reviewQueue" ? (
      <ReviewQueueView inspections={reviewQueue} loading={reviewLoading} error={reviewError} onRetry={refreshReviewQueue} onOpen={handleOpen} onNavigate={go} />
    ) : view === "profile" ? (
      <ProfileView user={user} onLogout={handleLogout} />
    ) : view === "scan" ? (
      <ScanView onCaptured={onCaptured} onBack={() => go("home")} />
    ) : view === "scanDetails" ? (
      <ScanDetailsView images={pendingImages} onSubmit={submitDetails} onBack={() => go("scan")} />
    ) : view === "processing" ? (
      processingError ? (
        <ProcessingErrorView message={processingError} onRetry={() => setProcessingError(undefined)} onCancel={() => go("home")} />
      ) : (
        <ProcessingRunner onRun={() => pendingRunRef.current()} onDone={handleProcessingDone} onError={handleProcessingError} />
      )
    ) : selected && (view === "result" || view === "detail") ? (
      <ResultView
        inspection={selected}
        reviewSubmitting={markReviewSubmitting}
        reviewError={markReviewError}
        onMarkReviewed={(note) => void handleMarkReviewed(note)}
        onOpenEvidence={() => go("evidence")}
        onOpenReport={() => go("report")}
        onNew={() => go("scan")}
      />
    ) : selected && view === "evidence" ? (
      <EvidenceView inspection={selected} onBack={() => go("result")} />
    ) : selected && view === "report" ? (
      <ReportView inspection={selected} onBack={() => go("result")} />
    ) : (
      <HomeView inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onNavigate={go} onOpen={handleOpen} />
    );

  const inFocusedFlow = isFocusedFlow(view);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {!inFocusedFlow && <DesktopRail view={view} onNavigate={go} />}
      {!inFocusedFlow && <div className="md:pl-64">{content}</div>}
      {inFocusedFlow && content}
      {!inFocusedFlow && <BottomNav view={view} onNavigate={go} />}
      {toast && (
        <div className="fixed bottom-24 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-xl md:bottom-8">
          <Check className="h-4 w-4 text-success" />{toast}
        </div>
      )}
    </div>
  );
}
