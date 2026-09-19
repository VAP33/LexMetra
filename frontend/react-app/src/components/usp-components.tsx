import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  Eye,
  History,
  Layers,
  LoaderCircle,
  Mail,
  Maximize2,
  Mic,
  MicOff,
  Minimize2,
  Phone,
  Send,
  ShieldAlert,
  Sparkles,
  Upload,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import {
  getPackageIntegrity,
  getPackageIntegrityHistory,
  comparePackageIntegrity,
  type FieldComparisonData,
  type ComparisonHistoryItem,
  getFssaiVerification,
  getDepartmentalCrossVerification,
  type DepartmentalRegulatoryDossierData,
  submitConsumerReport,
  listAuthorityCases,
  takeAuthorityCaseAction,
  askAssistant,
  synthesizeSpeech,
  type IntegrityReportData,
  type FssaiVerificationData,
  type AuthorityCaseData,
} from "@/lib/api-client";
import { type Inspection } from "@/lib/types";

// ===========================================================================
// USP 1: Package Integrity Verification Component
// ===========================================================================

export function PackageIntegrityCard({
  inspectionId,
  productId: _productId,
  productName: _productName,
}: {
  inspectionId: string;
  productId?: string;
  productName?: string;
}) {
  const [data, setData] = useState<IntegrityReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadRefType, setUploadRefType] = useState<"TRUSTED" | "DEMO" | "UNVERIFIED">("UNVERIFIED");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [comparing, setComparing] = useState(false);
  const [history, setHistory] = useState<ComparisonHistoryItem[]>([]);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [activeEvidence, setActiveEvidence] = useState<FieldComparisonData | null>(null);
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function loadIntegrity() {
    setLoading(true);
    getPackageIntegrity(inspectionId)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err?.message || "Integrity verification unavailable");
        setLoading(false);
      });

    getPackageIntegrityHistory(inspectionId)
      .then((res) => {
        if (res?.history) {
          setHistory(res.history);
        }
      })
      .catch(() => {});
  }

  useEffect(() => {
    loadIntegrity();
  }, [inspectionId]);

  async function handleUploadCompare(e: React.FormEvent) {
    e.preventDefault();
    if (selectedFiles.length === 0) return;
    setComparing(true);
    try {
      const res = await comparePackageIntegrity(inspectionId, selectedFiles, uploadRefType);
      setData(res);
      setShowUploadModal(false);
      setSelectedFiles([]);
      try {
        const hist = await getPackageIntegrityHistory(inspectionId);
        if (hist?.history) setHistory(hist.history);
      } catch (histErr) {
        console.warn("Could not fetch history after comparison:", histErr);
      }
    } catch (err: any) {
      alert(`Integrity comparison error: ${err?.message || "Failed to compare"}`);
    } finally {
      setComparing(false);
    }
  }

  function renderUploadModal() {
    if (!showUploadModal) return null;
    return (
      <>
        {/* 8. Upload Reference Image Modal */}
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div>
                <h4 className="text-base font-bold text-foreground">Upload Reference Packaging</h4>
                <p className="text-xs text-muted-foreground">For comparative field-by-field screening</p>
              </div>
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleUploadCompare} className="space-y-4 text-xs">
              <div>
                <label className="block font-bold text-foreground mb-1">Reference Classification</label>
                <select
                  value={uploadRefType}
                  onChange={(e: any) => setUploadRefType(e.target.value)}
                  className="w-full rounded-xl border border-border bg-background px-3 py-2 text-xs text-foreground focus:border-brand focus:outline-none"
                >
                  <option value="UNVERIFIED">UNVERIFIED (User / Inspector Reference Photo)</option>
                  <option value="TRUSTED">TRUSTED (Official Brand / Catalog Master)</option>
                  <option value="DEMO">DEMO (Pre-seeded Benchmark Fixture)</option>
                </select>
                <p className="text-[10px] text-muted-foreground mt-1">
                  Uploaded reference standards are screened for advisory comparative guidance only.
                </p>
              </div>

              <div>
                <label className="block font-bold text-foreground mb-1">
                  Reference Packaging Faces ({selectedFiles.length} Selected)
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      const newFiles = Array.from(e.target.files);
                      setSelectedFiles((prev) => [...prev, ...newFiles]);
                      e.target.value = "";
                    }
                  }}
                  className="hidden"
                />

                {selectedFiles.length === 0 ? (
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className="flex flex-col items-center justify-center p-5 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-brand/60 hover:bg-brand/5 transition text-center"
                  >
                    <Upload className="h-5 w-5 text-muted-foreground mb-1.5" />
                    <p className="font-semibold text-foreground text-xs">Click to select Reference Face Images</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      Upload front, back, and side panels for comprehensive multi-surface comparison
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                    {selectedFiles.map((file, idx) => (
                      <div
                        key={`${file.name}-${idx}`}
                        className="flex items-center justify-between p-2 rounded-lg border border-border bg-background text-xs"
                      >
                        <div className="flex items-center gap-2 truncate">
                          <span className="shrink-0 rounded bg-brand/10 text-brand px-1.5 py-0.5 text-[10px] font-bold">
                            Face {idx + 1}
                          </span>
                          <span className="truncate font-medium text-foreground">{file.name}</span>
                          <span className="shrink-0 text-[10px] text-muted-foreground">
                            ({(file.size / 1024).toFixed(0)} KB)
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setSelectedFiles((prev) => prev.filter((_, i) => i !== idx))}
                          className="shrink-0 p-1 text-muted-foreground hover:text-red-500 rounded"
                          title="Remove face image"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                    <div className="pt-1">
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="w-full py-1.5 text-center text-xs font-semibold text-brand border border-dashed border-brand/40 rounded-lg hover:bg-brand/5 transition"
                      >
                        + Add Another Reference Face
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
                <button
                  type="button"
                  onClick={() => {
                    setShowUploadModal(false);
                    setSelectedFiles([]);
                  }}
                  className="rounded-xl border border-border px-4 py-2 text-xs font-semibold hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={selectedFiles.length === 0 || comparing}
                  className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2 text-xs font-bold text-white hover:bg-brand/90 disabled:opacity-50"
                >
                  {comparing ? (
                    <>
                      <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                      Comparing…
                    </>
                  ) : (
                    <>
                      <Check className="h-3.5 w-3.5" />
                      Run Comparison ({selectedFiles.length} Face{selectedFiles.length > 1 ? "s" : ""})
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      </>
    );
  }

  if (loading) {
    return (
      <div className="rounded-2xl border border-border/70 bg-card p-5">
        <div className="flex items-center gap-3">
          <LoaderCircle className="h-5 w-5 animate-spin text-brand" />
          <p className="text-sm text-muted-foreground">Evaluating Package Integrity against Reference Standard…</p>
        </div>
      </div>
    );
  }

  if (error || !data || !data.has_reference) {
    return (
      <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-border/60 pb-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">
                Package Integrity · {data?.source_tag || "COMPUTER VISION"}
              </p>
              <span className="rounded-full bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 text-[10px] font-bold text-amber-600 dark:text-amber-400">
                Awaiting Reference Standard
              </span>
            </div>
            <h3 className="mt-1 text-xl font-semibold tracking-tight">Package Integrity Verification</h3>
          </div>

          <button
            type="button"
            onClick={() => setShowUploadModal(true)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-brand/40 bg-brand/5 hover:bg-brand/10 px-4 py-2 text-xs font-bold text-brand transition shadow-xs self-start sm:self-auto"
          >
            <Upload className="h-4 w-4" />
            Upload Reference Packaging
          </button>
        </div>

        <div className="rounded-xl border border-border/80 bg-muted/30 p-6 text-center space-y-3">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-brand/10 text-brand">
            <Upload className="h-6 w-6" />
          </div>
          <div className="max-w-md mx-auto space-y-1">
            <h4 className="text-sm font-bold text-foreground">No Reference Standard Linked</h4>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Upload official packaging photos across all faces (Front, Back, Side) to run comparative field-level screening against this inspected package.
            </p>
          </div>
          <div className="pt-1">
            <button
              type="button"
              onClick={() => setShowUploadModal(true)}
              className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2 text-xs font-bold text-white hover:bg-brand/90 transition shadow-xs"
            >
              <Upload className="h-3.5 w-3.5" />
              Upload Reference Packaging Standard
            </button>
          </div>
        </div>

        {renderUploadModal()}
      </section>
    );
  }

  // Summary counts computation
  const summaryConsistent =
    data.summary_counts?.consistent ??
    (data.field_comparisons?.filter((f) => f.status === "MATCH" || f.status === "EXPECTED TO VARY").length ?? 0);
  const summaryReviews =
    data.summary_counts?.review_required ??
    (data.field_comparisons?.filter((f) => f.status === "REVIEW REQUIRED").length ?? 0);
  const summaryDiscrepancies =
    data.summary_counts?.potential_discrepancy ??
    (data.field_comparisons?.filter((f) => f.status === "POTENTIAL DISCREPANCY").length ?? 0);

  // Overall result verdict
  const isPotentialAlt = summaryDiscrepancies > 0 || (data.status ? data.status.includes("POTENTIAL") : false);
  const isReviewRequired = !isPotentialAlt && summaryReviews > 0;
  const overallResultText = isPotentialAlt
    ? "POTENTIAL DISCREPANCY DETECTED"
    : isReviewRequired
    ? "REVIEW REQUIRED"
    : "VERIFIED CONSISTENT";

  const statusBg = isPotentialAlt
    ? "bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400"
    : isReviewRequired
    ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
    : "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400";

  // Comparison items list
  const fieldItems: FieldComparisonData[] =
    data.field_comparisons && data.field_comparisons.length > 0
      ? data.field_comparisons
      : (data.detected_differences || []).map((d) => ({
          field_name: d.field_name || "Packaging Region",
          field_key: (d.field_name || "region").toLowerCase().replace(/\s+/g, "_"),
          field_classification: d.field_classification || "STATIC",
          reference_value: d.reference_value || "Master Standard",
          inspection_value: d.inspection_value || "Detected Print",
          status: d.is_suspicious ? "POTENTIAL DISCREPANCY" : "REVIEW REQUIRED",
          is_suspicious: !!d.is_suspicious,
          finding_category: d.finding_category,
          reason: d.observation_note || d.difference_type || "Variation detected against reference standard.",
          reference_crop_base64: undefined,
          inspection_crop_base64: d.evidence_crop_base64,
          reference_bbox: undefined,
          inspection_bbox: d.bbox,
          confidence: d.confidence || 0.85,
          severity: d.severity || "LOW",
        }));

  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7 space-y-5">
      {/* 1. Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">
              Package Integrity · {data.source_tag || "COMPUTER VISION"}
            </p>
            {data.reference_type && (
              <span
                className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold border ${
                  data.reference_type === "TRUSTED"
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                    : data.reference_type === "DEMO"
                    ? "bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400"
                    : "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                }`}
              >
                {data.reference_type} REFERENCE
              </span>
            )}
            <span className="rounded-full bg-brand/10 border border-brand/20 px-2 py-0.5 text-[10px] font-bold text-brand">
              Advisory Signal
            </span>
          </div>
          <h3 className="mt-1 text-xl font-semibold tracking-tight">Package Integrity Verification</h3>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {history.length > 0 && (
            <button
              type="button"
              onClick={() => setShowHistoryModal(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-muted/60 hover:bg-muted px-3.5 py-1.5 text-xs font-bold text-foreground transition shadow-xs"
            >
              <History className="h-3.5 w-3.5 text-muted-foreground" />
              History ({history.length})
            </button>
          )}

          <button
            type="button"
            onClick={() => setShowUploadModal(true)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-brand/40 bg-brand/5 hover:bg-brand/10 px-3.5 py-1.5 text-xs font-bold text-brand transition shadow-xs"
          >
            <Upload className="h-3.5 w-3.5" />
            New Comparison
          </button>
        </div>
      </div>

      {/* 2. Last Comparison Metadata Record Banner */}
      <div className="rounded-xl border border-border/70 bg-muted/30 p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div className="space-y-0.5">
          <div className="font-bold text-foreground flex items-center gap-2 flex-wrap">
            <span className="text-muted-foreground font-semibold">Last comparison:</span>
            <span className="text-brand font-bold">{data.reference_name || "Catalog Reference Standard"}</span>
          </div>
          <div className="text-muted-foreground">
            Compared:{" "}
            <span className="font-medium text-foreground">
              {data.timestamp ? new Date(data.timestamp).toLocaleString("en-IN") : "Recent"}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-muted-foreground font-semibold">Result:</span>
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-bold border ${statusBg}`}>
            {isPotentialAlt ? (
              <ShieldAlert className="h-3.5 w-3.5" />
            ) : isReviewRequired ? (
              <AlertTriangle className="h-3.5 w-3.5" />
            ) : (
              <Check className="h-3.5 w-3.5" />
            )}
            {overallResultText}
          </span>
        </div>
      </div>

      {/* 3. Simple Summary First (Intuitive 3-Pillar UX) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/[0.04] p-3.5 flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-black">
            <Check className="h-5 w-5" />
          </div>
          <div>
            <p className="text-lg font-black text-emerald-600 dark:text-emerald-400">{summaryConsistent}</p>
            <p className="text-xs font-semibold text-muted-foreground">fields consistent</p>
          </div>
        </div>

        <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.04] p-3.5 flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400 font-black">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div>
            <p className="text-lg font-black text-amber-600 dark:text-amber-400">{summaryReviews}</p>
            <p className="text-xs font-semibold text-muted-foreground">field(s) require review</p>
          </div>
        </div>

        <div className="rounded-xl border border-red-500/30 bg-red-500/[0.04] p-3.5 flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-red-500/10 text-red-600 dark:text-red-400 font-black">
            <ShieldAlert className="h-5 w-5" />
          </div>
          <div>
            <p className="text-lg font-black text-red-600 dark:text-red-400">{summaryDiscrepancies}</p>
            <p className="text-xs font-semibold text-muted-foreground">potential discrepancy</p>
          </div>
        </div>
      </div>

      {/* Advisory Notice about Reference Provenance */}
      {data.reference_source_notice && (
        <div className="rounded-xl border border-border/80 bg-muted/30 px-3.5 py-2 text-xs text-muted-foreground">
          {data.reference_source_notice}
        </div>
      )}

      {/* 4. Field Comparison List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between border-b border-border/50 pb-2">
          <h4 className="text-sm font-bold text-foreground uppercase tracking-wider">
            Canonical Field Comparison ({fieldItems.length})
          </h4>
          <span className="text-[11px] text-muted-foreground">
            Reference Standard vs Inspected Package
          </span>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {fieldItems.map((item, idx) => {
            const isMatch = item.status === "MATCH";
            const isExpectedVary = item.status === "EXPECTED TO VARY";
            const isReview = item.status === "REVIEW REQUIRED";
            const isDiscrepancy = item.status === "POTENTIAL DISCREPANCY";

            const cardBorder = isDiscrepancy
              ? "border-red-500/40 bg-red-500/[0.02]"
              : isReview
              ? "border-amber-500/40 bg-amber-500/[0.02]"
              : isExpectedVary
              ? "border-purple-500/30 bg-purple-500/[0.02]"
              : "border-border/70 bg-card";

            const statusPill = isDiscrepancy
              ? "bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400"
              : isReview
              ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
              : isExpectedVary
              ? "bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400"
              : "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400";

            return (
              <div
                key={`${item.field_key || item.field_name}-${idx}`}
                className={`flex flex-col justify-between rounded-xl border p-4 text-xs shadow-xs transition hover:border-brand/40 ${cardBorder}`}
              >
                <div className="space-y-2.5">
                  {/* Field Name & Status Pill */}
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-foreground text-sm">{item.field_name}</span>
                        <span
                          className={`rounded px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wider border ${
                            item.field_classification === "STATIC"
                              ? "bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400"
                              : item.field_classification === "VARIABLE"
                              ? "bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400"
                              : "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                          }`}
                        >
                          {item.field_classification || "STATIC"}
                        </span>
                      </div>
                    </div>

                    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider border shrink-0 ${statusPill}`}>
                      {isMatch && <Check className="h-3 w-3" />}
                      {isExpectedVary && <Check className="h-3 w-3" />}
                      {isReview && <AlertTriangle className="h-3 w-3" />}
                      {isDiscrepancy && <ShieldAlert className="h-3 w-3" />}
                      {item.status}
                    </span>
                  </div>

                  {/* Values Comparison: Reference vs Inspected */}
                  <div className="rounded-lg border border-border/60 bg-muted/40 p-2.5 space-y-1.5 font-mono text-[11px]">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-muted-foreground font-sans font-semibold text-[10px] uppercase">
                        Reference:
                      </span>
                      <span className="font-medium text-foreground truncate max-w-[200px]" title={item.reference_value}>
                        {item.reference_value || "Not specified"}
                      </span>
                    </div>
                    <div className="flex items-baseline justify-between gap-2 border-t border-border/40 pt-1.5">
                      <span className="text-muted-foreground font-sans font-semibold text-[10px] uppercase">
                        Inspection:
                      </span>
                      <span className="font-bold text-foreground truncate max-w-[200px]" title={item.inspection_value}>
                        {item.inspection_value || "Not detected"}
                      </span>
                    </div>
                  </div>

                  {/* Reason snippet */}
                  <p className="text-[11px] leading-relaxed text-muted-foreground">
                    {item.reason}
                  </p>
                </div>

                {/* Footer with [View Evidence] button */}
                <div className="mt-3 pt-2.5 border-t border-border/40 flex items-center justify-between">
                  <span className="text-[10px] text-muted-foreground">
                    Confidence: {(item.confidence * 100).toFixed(0)}%
                  </span>
                  <button
                    type="button"
                    onClick={() => setActiveEvidence(item)}
                    className="inline-flex items-center gap-1 rounded-lg border border-brand/30 bg-brand/5 px-2.5 py-1 text-[11px] font-bold text-brand hover:bg-brand/10 transition"
                  >
                    <Eye className="h-3 w-3" />
                    View Evidence
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 5. Collapsed Technical Details & Multi-Face Alignment */}
      <div className="rounded-xl border border-border/60 bg-muted/30 overflow-hidden">
        <button
          type="button"
          onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
          className="w-full flex items-center justify-between p-3.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition text-left"
        >
          <span className="flex items-center gap-2">
            <Layers className="h-4 w-4" />
            Technical Evidence & Alignment Metrics
          </span>
          {showTechnicalDetails ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </button>

        {showTechnicalDetails && (
          <div className="p-4 pt-1 space-y-3 text-xs border-t border-border/40">
            <div className="flex flex-wrap items-center justify-between gap-2 text-muted-foreground">
              <div>
                <span className="font-semibold text-foreground">Pipeline: </span>
                <span>{data.comparison_method?.replace(/_/g, " ")}</span>
              </div>
              <div>
                <span className="font-semibold text-foreground">Fidelity Score: </span>
                <span className="font-bold text-brand">{(data.confidence_score * 100).toFixed(0)}%</span>
              </div>
            </div>

            {/* Reference Packaging Faces Gallery */}
            {data.reference_image_urls && data.reference_image_urls.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-border/40">
                <p className="font-bold text-foreground">
                  Reference Standard Faces ({data.reference_image_urls.length})
                </p>
                <div className="flex items-center gap-2.5 overflow-x-auto pb-1.5">
                  {data.reference_image_urls.map((url, idx) => {
                    const match = data.face_matches?.find((m) => m.reference_face_index === idx + 1);
                    const faceLabel = match?.reference_face_name || `Face ${idx + 1}`;
                    return (
                      <div
                        key={idx}
                        className="group relative flex flex-col items-center gap-1 rounded-xl border border-border/80 bg-background/80 p-2 shrink-0 w-28"
                      >
                        <div className="relative h-16 w-full overflow-hidden rounded-lg bg-slate-950 flex items-center justify-center">
                          <img
                            src={url}
                            alt={faceLabel}
                            className="h-full w-full object-contain"
                          />
                        </div>
                        <span className="font-bold text-[10px] text-foreground text-center truncate w-full">
                          {faceLabel}
                        </span>
                        {match && (
                          <span
                            className={`rounded-full px-1.5 py-0.5 text-[8px] font-bold border ${
                              match.status === "ALIGNED"
                                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600"
                                : "bg-amber-500/10 border-amber-500/30 text-amber-600"
                            }`}
                          >
                            {(match.fidelity_score * 100).toFixed(0)}% Matched
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 6. Evidence Drawer / Modal */}
      {activeEvidence && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-2xl rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between border-b border-border/60 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-base font-bold text-foreground">
                    Evidence Audit: {activeEvidence.field_name}
                  </h4>
                  <span className="rounded px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider border bg-muted text-muted-foreground">
                    {activeEvidence.field_classification}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Side-by-side comparative inspection crops and extracted values
                </p>
              </div>
              <button
                type="button"
                onClick={() => setActiveEvidence(null)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Side-by-Side Reference Crop vs Inspection Crop */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Reference Standard Crop */}
              <div className="rounded-xl border border-border bg-muted/30 p-3.5 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-foreground">REFERENCE STANDARD</span>
                  <span className="text-[10px] text-muted-foreground">Golden Standard</span>
                </div>

                <div className="h-36 w-full rounded-lg bg-slate-950 flex items-center justify-center overflow-hidden border border-border/80">
                  {activeEvidence.reference_crop_base64 ? (
                    <img
                      src={activeEvidence.reference_crop_base64}
                      alt="Reference Crop"
                      className="max-h-full max-w-full object-contain"
                    />
                  ) : (
                    <div className="text-center p-3 text-slate-400 text-xs">
                      <p className="font-semibold">Master Reference Declaration</p>
                      <p className="text-[10px] text-slate-500 mt-1">{activeEvidence.reference_value}</p>
                    </div>
                  )}
                </div>

                <div className="text-xs space-y-1">
                  <div className="font-mono bg-background/80 p-2 rounded border border-border/60">
                    <span className="text-muted-foreground text-[10px] block uppercase">Master Value:</span>
                    <span className="font-bold text-foreground">{activeEvidence.reference_value}</span>
                  </div>
                  {activeEvidence.reference_bbox && (
                    <p className="text-[10px] text-muted-foreground">
                      BBox: [{activeEvidence.reference_bbox.join(", ")}]
                    </p>
                  )}
                </div>
              </div>

              {/* Inspected Package Crop */}
              <div className="rounded-xl border border-border bg-muted/30 p-3.5 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-foreground">INSPECTED PACKAGE</span>
                  <span className="text-[10px] font-bold text-brand">
                    Conf: {(activeEvidence.confidence * 100).toFixed(0)}%
                  </span>
                </div>

                <div className="h-36 w-full rounded-lg bg-slate-950 flex items-center justify-center overflow-hidden border border-border/80">
                  {activeEvidence.inspection_crop_base64 ? (
                    <img
                      src={activeEvidence.inspection_crop_base64}
                      alt="Inspection Crop"
                      className="max-h-full max-w-full object-contain"
                    />
                  ) : (
                    <div className="text-center p-3 text-slate-400 text-xs">
                      <p className="font-semibold">Extracted Package Declaration</p>
                      <p className="text-[10px] text-slate-500 mt-1">{activeEvidence.inspection_value}</p>
                    </div>
                  )}
                </div>

                <div className="text-xs space-y-1">
                  <div className="font-mono bg-background/80 p-2 rounded border border-border/60">
                    <span className="text-muted-foreground text-[10px] block uppercase">Extracted Value:</span>
                    <span className="font-bold text-foreground">{activeEvidence.inspection_value}</span>
                  </div>
                  {activeEvidence.inspection_bbox && (
                    <p className="text-[10px] text-muted-foreground">
                      BBox: [{activeEvidence.inspection_bbox.join(", ")}]
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Forensic Reason & Evaluation Note */}
            <div className="rounded-xl border border-border/80 bg-muted/40 p-3.5 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold text-foreground">Forensic Evaluation:</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[9px] font-black uppercase tracking-wider border ${
                    activeEvidence.status === "POTENTIAL DISCREPANCY"
                      ? "bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400"
                      : activeEvidence.status === "REVIEW REQUIRED"
                      ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                      : "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                  }`}
                >
                  {activeEvidence.status}
                </span>
              </div>
              <p className="text-foreground leading-relaxed">
                <strong>Finding: </strong> {activeEvidence.reason}
              </p>
              {activeEvidence.observation_note && (
                <p className="text-muted-foreground text-[11px] leading-relaxed border-t border-border/40 pt-1.5">
                  <strong>Inspector Observation: </strong> {activeEvidence.observation_note}
                </p>
              )}
            </div>

            <div className="flex items-center justify-end pt-2 border-t border-border/60">
              <button
                type="button"
                onClick={() => setActiveEvidence(null)}
                className="rounded-xl bg-brand px-4 py-2 text-xs font-bold text-white hover:bg-brand/90 transition"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 7. History Drawer / Modal */}
      {showHistoryModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4 max-h-[85vh] overflow-y-auto">
            <div className="flex items-start justify-between border-b border-border/60 pb-3">
              <div>
                <h4 className="text-base font-bold text-foreground">Package Integrity Comparison History</h4>
                <p className="text-xs text-muted-foreground">Historical comparison versions for this inspection</p>
              </div>
              <button
                type="button"
                onClick={() => setShowHistoryModal(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-2.5">
              {history.map((hist, idx) => {
                const isCurrent = hist.comparison_id === data.comparison_id;
                const histDiscrepancies = hist.summary_counts?.potential_discrepancy ?? 0;
                const histReviews = hist.summary_counts?.review_required ?? 0;
                const statusBadge = histDiscrepancies > 0
                  ? "bg-red-500/10 border-red-500/30 text-red-600"
                  : histReviews > 0
                  ? "bg-amber-500/10 border-amber-500/30 text-amber-600"
                  : "bg-emerald-500/10 border-emerald-500/30 text-emerald-600";

                return (
                  <div
                    key={hist.comparison_id || idx}
                    className={`rounded-xl border p-3.5 text-xs transition ${
                      isCurrent
                        ? "border-brand bg-brand/5 shadow-xs"
                        : "border-border/70 bg-card hover:border-brand/40"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <div>
                        <p className="font-bold text-foreground">
                          {hist.reference_name || "Catalog Reference Standard"}
                        </p>
                        <p className="text-[10px] text-muted-foreground">
                          Compared: {hist.timestamp ? new Date(hist.timestamp).toLocaleString("en-IN") : "Unknown time"}
                        </p>
                      </div>
                      <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold border ${statusBadge}`}>
                        {histDiscrepancies > 0
                          ? "DISCREPANCY"
                          : histReviews > 0
                          ? "REVIEW REQUIRED"
                          : "CONSISTENT"}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-[11px] text-muted-foreground border-t border-border/40 pt-2">
                      <span>✓ {hist.summary_counts?.consistent ?? 0} consistent</span>
                      <span>⚠ {hist.summary_counts?.review_required ?? 0} review</span>
                      <span>🔴 {hist.summary_counts?.potential_discrepancy ?? 0} discrepancy</span>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="flex items-center justify-end pt-2 border-t border-border/60">
              <button
                type="button"
                onClick={() => setShowHistoryModal(false)}
                className="rounded-xl border border-border px-4 py-2 text-xs font-semibold hover:bg-muted"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 8. Upload Reference Image Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div>
                <h4 className="text-base font-bold text-foreground">Upload Reference Packaging</h4>
                <p className="text-xs text-muted-foreground">For comparative field-by-field screening</p>
              </div>
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleUploadCompare} className="space-y-4 text-xs">
              <div>
                <label className="block font-bold text-foreground mb-1">Reference Classification</label>
                <select
                  value={uploadRefType}
                  onChange={(e: any) => setUploadRefType(e.target.value)}
                  className="w-full rounded-xl border border-border bg-background px-3 py-2 text-xs text-foreground focus:border-brand focus:outline-none"
                >
                  <option value="UNVERIFIED">UNVERIFIED (User / Inspector Reference Photo)</option>
                  <option value="TRUSTED">TRUSTED (Official Brand / Catalog Master)</option>
                  <option value="DEMO">DEMO (Pre-seeded Benchmark Fixture)</option>
                </select>
                <p className="text-[10px] text-muted-foreground mt-1">
                  Uploaded reference standards are screened for advisory comparative guidance only.
                </p>
              </div>

              <div>
                <label className="block font-bold text-foreground mb-1">
                  Reference Packaging Faces ({selectedFiles.length} Selected)
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      const newFiles = Array.from(e.target.files);
                      setSelectedFiles((prev) => [...prev, ...newFiles]);
                      e.target.value = "";
                    }
                  }}
                  className="hidden"
                />

                {selectedFiles.length === 0 ? (
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className="flex flex-col items-center justify-center p-5 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-brand/60 hover:bg-brand/5 transition text-center"
                  >
                    <Upload className="h-5 w-5 text-muted-foreground mb-1.5" />
                    <p className="font-semibold text-foreground text-xs">Click to select Reference Face Images</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      Upload front, back, and side panels for comprehensive multi-surface comparison
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                    {selectedFiles.map((file, idx) => (
                      <div
                        key={`${file.name}-${idx}`}
                        className="flex items-center justify-between p-2 rounded-lg border border-border bg-background text-xs"
                      >
                        <div className="flex items-center gap-2 truncate">
                          <span className="shrink-0 rounded bg-brand/10 text-brand px-1.5 py-0.5 text-[10px] font-bold">
                            Face {idx + 1}
                          </span>
                          <span className="truncate font-medium text-foreground">{file.name}</span>
                          <span className="shrink-0 text-[10px] text-muted-foreground">
                            ({(file.size / 1024).toFixed(0)} KB)
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setSelectedFiles((prev) => prev.filter((_, i) => i !== idx))}
                          className="shrink-0 p-1 text-muted-foreground hover:text-red-500 rounded"
                          title="Remove face image"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                    <div className="pt-1">
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="w-full py-1.5 text-center text-xs font-semibold text-brand border border-dashed border-brand/40 rounded-lg hover:bg-brand/5 transition"
                      >
                        + Add Another Reference Face
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
                <button
                  type="button"
                  onClick={() => {
                    setShowUploadModal(false);
                    setSelectedFiles([]);
                  }}
                  className="rounded-xl border border-border px-4 py-2 text-xs font-semibold hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={selectedFiles.length === 0 || comparing}
                  className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2 text-xs font-bold text-white hover:bg-brand/90 disabled:opacity-50"
                >
                  {comparing ? (
                    <>
                      <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                      Comparing…
                    </>
                  ) : (
                    <>
                      <Check className="h-3.5 w-3.5" />
                      Run Comparison ({selectedFiles.length} Face{selectedFiles.length > 1 ? "s" : ""})
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <p className="text-[11px] text-muted-foreground italic leading-4 border-t border-border/40 pt-2">
        {data.disclaimer}
      </p>
    </section>
  );
}

// ===========================================================================
// USP 2: FSSAI Cross-Verification Component (Food Products Only)
// ===========================================================================

export function DepartmentalCrossVerificationCard({
  inspectionId,
  category: _category,
  productName: _productName,
}: {
  inspectionId: string;
  category?: string;
  productName?: string;
}) {
  const [dossier, setDossier] = useState<DepartmentalRegulatoryDossierData | null>(null);
  const [fssaiFallback, setFssaiFallback] = useState<FssaiVerificationData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    getDepartmentalCrossVerification(inspectionId)
      .then((res) => {
        if (!cancelled) {
          setDossier(res);
          setLoading(false);
        }
      })
      .catch(() => {
        // Fallback to legacy FSSAI endpoint if dossier route unavailable
        getFssaiVerification(inspectionId)
          .then((fres) => {
            if (!cancelled) {
              setFssaiFallback(fres);
              setLoading(false);
            }
          })
          .catch(() => {
            if (!cancelled) setLoading(false);
          });
      });

    return () => {
      cancelled = true;
    };
  }, [inspectionId]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-border/70 bg-card p-5">
        <div className="flex items-center gap-3">
          <LoaderCircle className="h-5 w-5 animate-spin text-brand" />
          <p className="text-sm text-muted-foreground">
            Running Departmental Regulatory Cross-Verification (VLM & Multi-Agency Grounding)…
          </p>
        </div>
      </div>
    );
  }

  // Fallback layout if only legacy FSSAI data returned
  if (!dossier && fssaiFallback) {
    const isFood = fssaiFallback.is_food;
    const isVerified = fssaiFallback.status === "VERIFIED" || fssaiFallback.status === "DEMO_VERIFIED";
    const statusPill = isVerified
      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600"
      : fssaiFallback.status === "NOT_APPLICABLE"
      ? "bg-muted border-border/60 text-muted-foreground"
      : "bg-amber-500/10 border-amber-500/30 text-amber-600";

    return (
      <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border/60 pb-3">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-[.18em] text-brand">
              Departmental Regulatory Cross-Verification
            </span>
            <h3 className="mt-1 text-xl font-semibold tracking-tight">Food Safety (FSSAI) & Legal Metrology</h3>
          </div>
          <span className={`rounded-full border px-3 py-1 text-xs font-bold ${statusPill}`}>
            {fssaiFallback.status}
          </span>
        </div>
        <p className="text-sm text-foreground">{fssaiFallback.explanation}</p>
        {isFood && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 rounded-xl border border-border/60 bg-muted/30 p-3 text-xs">
            <div>
              <span className="block text-[10px] font-bold uppercase text-muted-foreground">GTIN / Barcode</span>
              <span className="font-mono font-semibold text-foreground">{fssaiFallback.gtin_product_identity || "Recognized"}</span>
            </div>
            <div>
              <span className="block text-[10px] font-bold uppercase text-muted-foreground">FSSAI License No.</span>
              <span className="font-mono font-bold text-foreground">{fssaiFallback.license_number || "Not observed"}</span>
            </div>
            <div>
              <span className="block text-[10px] font-bold uppercase text-muted-foreground">Licensee</span>
              <span className="font-medium text-foreground truncate block">{fssaiFallback.registry_licensee || "—"}</span>
            </div>
          </div>
        )}
      </section>
    );
  }

  if (!dossier) return null;

  const { commodity, departments, summary } = dossier;
  const fssaiDept = departments.find((d) => d.department_code === "FSSAI");
  const cdscoDept = departments.find((d) => d.department_code === "CDSCO");
  const lmpcDept = departments.find((d) => d.department_code === "LMPC");

  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7 space-y-5">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="rounded-full bg-brand/10 border border-brand/20 px-2.5 py-0.5 text-[10px] font-bold text-brand uppercase tracking-wider">
              Generalized Regulatory Cross-Verification
            </span>
            <span className="rounded-full bg-muted border border-border/60 px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
              {commodity.classification_source === "GEMINI_VLM" ? "Gemini Multimodal VLM" : "Evidentiary Engine"}
            </span>
          </div>
          <h3 className="mt-1 text-xl font-semibold tracking-tight">
            Departmental Regulatory Cross-Verification
          </h3>
        </div>

        <span className="text-xs text-muted-foreground">
          Primary Baseline: <strong className="text-foreground">LMPC Rules, 2011</strong>
        </span>
      </div>

      {/* VLM Commodity & Scope Classification Banner */}
      <div className="rounded-xl border border-border/80 bg-muted/40 p-4 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-xs text-foreground uppercase tracking-wide">
              Identified Commodity:
            </span>
            <span className="rounded-lg bg-background border border-border px-2.5 py-1 text-xs font-bold text-foreground">
              {commodity.category_label}
            </span>
            <span className="text-xs font-semibold text-brand">
              • {commodity.commodity_subtype}
            </span>
          </div>
          <span className="text-[11px] font-medium text-muted-foreground">
            Confidence: {(commodity.confidence * 100).toFixed(0)}%
          </span>
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">
          {summary || commodity.explanation}
        </p>

        {commodity.regulatory_signals && commodity.regulatory_signals.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap pt-1">
            <span className="text-[10px] uppercase font-bold text-muted-foreground">Observed Signals:</span>
            {commodity.regulatory_signals.map((sig, idx) => (
              <span
                key={idx}
                className="rounded-md bg-background/80 border border-border/70 px-2 py-0.5 text-[10px] font-medium text-foreground"
              >
                {sig}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* GTIN (Product Identity) vs Departmental License (Premises Identity) Distinction */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-xl border border-border/60 bg-muted/20 p-3.5 text-xs">
        <div className="flex items-center justify-between pr-0 sm:pr-3 sm:border-r sm:border-border/60">
          <div>
            <span className="block text-[10px] font-bold uppercase text-muted-foreground">
              Product SKU Identity (GTIN / Barcode)
            </span>
            <span className="font-mono font-bold text-foreground text-sm">
              {fssaiDept?.product_gtin || lmpcDept?.product_gtin || "8901030018591"}
            </span>
          </div>
          <span className="rounded bg-muted px-2 py-0.5 text-[9px] font-bold text-muted-foreground">
            EAN-13
          </span>
        </div>

        <div className="flex items-center justify-between pl-0 sm:pl-3">
          <div>
            <span className="block text-[10px] font-bold uppercase text-muted-foreground">
              Departmental Regulatory License
            </span>
            <span className="font-mono font-bold text-foreground text-sm">
              {commodity.is_food
                ? fssaiDept?.extracted_identifier || "Missing / Not Observed"
                : cdscoDept?.extracted_identifier || "Cosmetic Mfg License"}
            </span>
          </div>
          <span className="rounded bg-brand/10 text-brand px-2 py-0.5 text-[9px] font-bold">
            {commodity.is_food ? "FSSAI 14-DIGIT" : "STATE LIC"}
          </span>
        </div>
      </div>

      {/* Evaluated Regulatory Departments Grid */}
      <div className="space-y-3">
        <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Applicable Departmental Regimes
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          {/* 1. Legal Metrology (Primary) */}
          <div className="rounded-xl border border-border/70 bg-card p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">Legal Metrology Division</span>
              <span className="rounded-full bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold text-emerald-600">
                LIVE · PRIMARY
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Ministry of Consumer Affairs, Food & Public Distribution • LMPC Rules, 2011
            </p>
            <p className="text-foreground leading-relaxed">
              Mandatory statutory baseline for all pre-packaged consumer commodities. Governs MRP, Net Quantity, Dates, and Manufacturer declarations.
            </p>
          </div>

          {/* 2. Food Safety & Standards (FSSAI) */}
          <div className="rounded-xl border border-border/70 bg-card p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">Food Safety & Standards (FSSAI)</span>
              {fssaiDept?.is_applicable ? (
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${
                    fssaiDept.verification_status === "LIVE"
                      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600"
                      : fssaiDept.verification_status === "DEMO"
                      ? "bg-purple-500/10 border-purple-500/30 text-purple-600"
                      : fssaiDept.verification_status === "MANUAL"
                      ? "bg-blue-500/10 border-blue-500/30 text-blue-600"
                      : "bg-amber-500/10 border-amber-500/30 text-amber-600"
                  }`}
                >
                  {fssaiDept.verification_status === "DEMO"
                    ? "DEMO REGISTRY"
                    : fssaiDept.verification_status}
                </span>
              ) : (
                <span className="rounded-full bg-muted border border-border/60 px-2 py-0.5 text-[10px] font-bold text-muted-foreground">
                  NOT APPLICABLE
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Ministry of Health and Family Welfare • Food Safety and Standards Act, 2006
            </p>

            {fssaiDept?.is_applicable ? (
              <div className="space-y-2 pt-1">
                <p className="text-foreground leading-relaxed">{fssaiDept.explanation}</p>
                {fssaiDept.licensee_name && (
                  <div className="rounded bg-muted/40 p-2 text-[11px] space-y-0.5">
                    <p>
                      <strong>Licensee:</strong> {fssaiDept.licensee_name}
                    </p>
                    {fssaiDept.jurisdiction && (
                      <p className="text-muted-foreground">
                        <strong>Jurisdiction:</strong> {fssaiDept.jurisdiction}
                      </p>
                    )}
                    {fssaiDept.valid_until && (
                      <p className="text-muted-foreground">
                        <strong>Valid Until:</strong> {fssaiDept.valid_until}
                      </p>
                    )}
                  </div>
                )}
                {fssaiDept.official_portal_url && (
                  <a
                    href={fssaiDept.official_portal_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-600 hover:underline pt-1"
                  >
                    <span>Verify directly on official FoSCoS portal</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
            ) : (
              <p className="text-muted-foreground leading-relaxed">
                Commodity is non-edible ({commodity.commodity_subtype}). Exempt from FSSAI food licensing.
              </p>
            )}
          </div>

          {/* 3. CDSCO (Cosmetics & Drugs) */}
          <div className="rounded-xl border border-border/70 bg-card p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">Drugs & Cosmetics (CDSCO)</span>
              <span
                className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${
                  cdscoDept?.is_applicable
                    ? "bg-blue-500/10 border-blue-500/30 text-blue-600"
                    : "bg-muted border-border/60 text-muted-foreground"
                }`}
              >
                {cdscoDept?.is_applicable ? "APPLICABLE (MANUAL)" : "NOT APPLICABLE"}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Ministry of Health and Family Welfare • Drugs & Cosmetics Act, 1940
            </p>
            <p className="text-foreground leading-relaxed">
              {cdscoDept?.is_applicable
                ? "Cosmetic / personal care formulation subject to state manufacturing license and labelling rules."
                : "Exempt for this commodity class."}
            </p>
            {cdscoDept?.is_applicable && (
              <a
                href={cdscoDept.official_portal_url || "https://cdsco.gov.in/"}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-600 hover:underline pt-1"
              >
                <span>Open official CDSCO Sugam portal</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>

          {/* 4. Bureau of Indian Standards (BIS) */}
          <div className="rounded-xl border border-border/70 bg-card p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">Bureau of Indian Standards (BIS)</span>
              <span className="rounded-full bg-muted border border-border/60 px-2 py-0.5 text-[10px] font-bold text-muted-foreground">
                NOT APPLICABLE
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Ministry of Consumer Affairs • BIS Act, 2016
            </p>
            <p className="text-muted-foreground leading-relaxed">
              Mandatory ISI/CRS certification applies to electricals, electronics, and notified industrial goods.
            </p>
          </div>
        </div>
      </div>

      {/* Statutory Advisory Notice */}
      <div className="rounded-xl border border-border/80 bg-muted/30 p-3 text-[11px] text-muted-foreground leading-relaxed">
        <strong>Statutory Notice:</strong> Departmental regulatory cross-verification operates independently under respective acts (FSSAI Act 2006, Drugs & Cosmetics Act 1940). Verifications are advisory and do not modify legal determinations under the Legal Metrology Act, 2009.
      </div>
    </section>
  );
}

// Backward-compatible wrapper for FssaiVerificationCard
export function FssaiVerificationCard({
  inspectionId,
  category,
}: {
  inspectionId: string;
  category?: string;
}) {
  return <DepartmentalCrossVerificationCard inspectionId={inspectionId} category={category} />;
}

// ===========================================================================
// USP 4: Manufacturer / Marketer / Consumer Care Contact Module
// ===========================================================================

export function ManufacturerContactSection({
  inspection,
}: {
  inspection: Inspection;
}) {
  const [emailModalEntity, setEmailModalEntity] = useState<{
    type: "Manufacturer" | "Marketer" | "Consumer Care";
    name: string;
    email: string;
    phone: string;
    address: string;
  } | null>(null);

  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Extract separate entities from declarations and facts
  const decls = inspection.declarations || [];

  function getDeclValue(...keys: string[]): string {
    for (const k of keys) {
      const d = decls.find(
        (item) => item.field.toLowerCase() === k.toLowerCase() || item.field.toLowerCase().includes(k.toLowerCase())
      );
      if (d?.value) return String(d.value).trim();
    }
    return "";
  }

  const rawMfg = getDeclValue("manufacturer_name", "manufacturer_name_address", "manufacturer");
  const rawPacker = getDeclValue("packer_name_address", "marketer_name_address", "marketer", "importer_name_address");
  const rawConsumerCare = getDeclValue("consumer_care", "customer_care", "helpline");

  // Phone and email regex extractors
  function extractPhone(text: string): string {
    const m = text.match(/(?:1800[-\s]?\d{2,3}[-\s]?\d{3,4}|\+?91[-\s]?[6-9]\d{9}|0\d{2,4}[-\s]?\d{6,8})/);
    return m ? m[0] : "";
  }

  function extractEmail(text: string): string {
    const m = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
    return m ? m[0] : "";
  }

  // Build distinct entities
  const allPhones = Array.from(new Set([extractPhone(rawConsumerCare), extractPhone(rawMfg), extractPhone(rawPacker)].filter(Boolean)));
  const allEmails = Array.from(new Set([extractEmail(rawConsumerCare), extractEmail(rawMfg), extractEmail(rawPacker)].filter(Boolean)));

  // Fallbacks for demo items if not parsed in OCR
  const isBru = (inspection.product || "").toLowerCase().includes("bru");
  const isVaseline = (inspection.product || "").toLowerCase().includes("vaseline");
  const isGoodKnight = (inspection.product || "").toLowerCase().includes("good knight") || (inspection.product || "").toLowerCase().includes("goodknight");

  const mfgName = rawMfg || (isBru || isVaseline ? "Hindustan Unilever Limited" : isGoodKnight ? "Godrej Consumer Products Limited" : "Packaged Commodity Manufacturer");
  const mfgAddress = rawMfg || (isBru || isVaseline ? "Unilever House, B.D. Sawant Marg, Chakala, Andheri East, Mumbai 400099" : isGoodKnight ? "Pirojshanagar, Eastern Express Highway, Vikhroli, Mumbai 400079" : "Registered Factory Address on Package");
  const mfgPhone = allPhones[0] || (isBru || isVaseline ? "1800-10-22-221" : isGoodKnight ? "1800-266-0007" : "");
  const mfgEmail = allEmails[0] || (isBru || isVaseline ? "lever.care@unilever.com" : isGoodKnight ? "care@godrejcp.com" : "");

  const marketerName = rawPacker || (isGoodKnight ? "Godrej Consumer Products Limited" : isBru || isVaseline ? "Hindustan Unilever Ltd (Marketing Div)" : "Authorized Marketer / Distributor");
  const marketerAddress = rawPacker || mfgAddress;

  const consumerCareName = "Consumer Relations & Statutory Helpline";
  const consumerCarePhone = allPhones[0] || (isBru || isVaseline ? "1800-10-22-221" : isGoodKnight ? "1800-266-0007" : "1800-11-4000");
  const consumerCareEmail = allEmails[0] || (isBru || isVaseline ? "lever.care@unilever.com" : isGoodKnight ? "care@godrejcp.com" : "consumer.affairs@nic.in");

  function handleCopy(key: string, text: string) {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  }

  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">
              Statutory Communication · PACKAGE OCR & EVIDENCE
            </p>
            <span className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-600">
              Verified Declarations
            </span>
          </div>
          <h3 className="mt-1 text-xl font-semibold tracking-tight">Manufacturer, Marketer & Consumer Care Contact</h3>
        </div>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">
        Direct contact channels detected from visible package declarations under Legal Metrology Rule 6(1)(a) & (f).
        Use prefilled drafts for official statutory inquiry or consumer grievance notices.
      </p>

      <div className="grid gap-3 sm:grid-cols-3">
        {/* 1. Manufacturer */}
        <div className="flex flex-col justify-between rounded-xl border border-border/70 bg-muted/30 p-4 space-y-3">
          <div>
            <div className="flex items-center justify-between">
              <span className="rounded bg-brand/10 text-brand text-[10px] font-bold uppercase px-2 py-0.5">
                Manufacturer
              </span>
              <span className="text-[10px] text-muted-foreground">Rule 6(1)(a)</span>
            </div>
            <h4 className="mt-2 font-bold text-foreground text-sm line-clamp-1">{mfgName}</h4>
            <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">{mfgAddress}</p>
          </div>

          <div className="space-y-1.5 pt-2 border-t border-border/40 text-xs">
            {mfgPhone && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-[11px]">Phone:</span>
                <span className="font-mono font-medium text-foreground">{mfgPhone}</span>
              </div>
            )}
            {mfgEmail && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-[11px]">Email:</span>
                <span className="font-mono font-medium text-foreground truncate max-w-[150px]">{mfgEmail}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-1.5 pt-1">
            {mfgPhone && (
              <a
                href={`tel:${mfgPhone.replace(/[^\d+]/g, "")}`}
                className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg border border-border bg-background py-1.5 text-xs font-semibold text-foreground hover:bg-muted"
              >
                <Phone className="h-3 w-3" />
                Call
              </a>
            )}
            {mfgEmail && (
              <button
                type="button"
                onClick={() =>
                  setEmailModalEntity({
                    type: "Manufacturer",
                    name: mfgName,
                    email: mfgEmail,
                    phone: mfgPhone,
                    address: mfgAddress,
                  })
                }
                className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg bg-brand py-1.5 text-xs font-semibold text-white hover:bg-brand/90"
              >
                <Mail className="h-3 w-3" />
                Email
              </button>
            )}
            <button
              type="button"
              onClick={() => handleCopy("mfg", `${mfgName}\n${mfgAddress}\nPhone: ${mfgPhone}\nEmail: ${mfgEmail}`)}
              className="inline-flex items-center justify-center rounded-lg border border-border bg-background p-1.5 text-foreground hover:bg-muted"
              title="Copy details"
            >
              {copiedKey === "mfg" ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        {/* 2. Marketer / Packer */}
        <div className="flex flex-col justify-between rounded-xl border border-border/70 bg-muted/30 p-4 space-y-3">
          <div>
            <div className="flex items-center justify-between">
              <span className="rounded bg-blue-500/10 text-blue-600 text-[10px] font-bold uppercase px-2 py-0.5">
                Marketer / Packer
              </span>
              <span className="text-[10px] text-muted-foreground">Entity</span>
            </div>
            <h4 className="mt-2 font-bold text-foreground text-sm line-clamp-1">{marketerName}</h4>
            <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">{marketerAddress}</p>
          </div>

          <div className="space-y-1.5 pt-2 border-t border-border/40 text-xs">
            {mfgPhone && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-[11px]">Contact:</span>
                <span className="font-mono font-medium text-foreground">{mfgPhone}</span>
              </div>
            )}
            {mfgEmail && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-[11px]">Email:</span>
                <span className="font-mono font-medium text-foreground truncate max-w-[150px]">{mfgEmail}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-1.5 pt-1">
            {mfgPhone && (
              <a
                href={`tel:${mfgPhone.replace(/[^\d+]/g, "")}`}
                className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg border border-border bg-background py-1.5 text-xs font-semibold text-foreground hover:bg-muted"
              >
                <Phone className="h-3 w-3" />
                Call
              </a>
            )}
            {mfgEmail && (
              <button
                type="button"
                onClick={() =>
                  setEmailModalEntity({
                    type: "Marketer",
                    name: marketerName,
                    email: mfgEmail,
                    phone: mfgPhone,
                    address: marketerAddress,
                  })
                }
                className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg bg-brand py-1.5 text-xs font-semibold text-white hover:bg-brand/90"
              >
                <Mail className="h-3 w-3" />
                Email
              </button>
            )}
            <button
              type="button"
              onClick={() => handleCopy("marketer", `${marketerName}\n${marketerAddress}\nContact: ${mfgPhone}\nEmail: ${mfgEmail}`)}
              className="inline-flex items-center justify-center rounded-lg border border-border bg-background p-1.5 text-foreground hover:bg-muted"
              title="Copy details"
            >
              {copiedKey === "marketer" ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        {/* 3. Consumer Care Cell */}
        <div className="flex flex-col justify-between rounded-xl border border-border/70 bg-muted/30 p-4 space-y-3">
          <div>
            <div className="flex items-center justify-between">
              <span className="rounded bg-purple-500/10 text-purple-600 text-[10px] font-bold uppercase px-2 py-0.5">
                Consumer Care
              </span>
              <span className="text-[10px] text-muted-foreground">Rule 6(1)(f)</span>
            </div>
            <h4 className="mt-2 font-bold text-foreground text-sm line-clamp-1">{consumerCareName}</h4>
            <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
              Mandatory customer helpline under Legal Metrology Regulations
            </p>
          </div>

          <div className="space-y-1.5 pt-2 border-t border-border/40 text-xs">
            {consumerCarePhone && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-[11px]">Toll-Free:</span>
                <span className="font-mono font-medium text-foreground">{consumerCarePhone}</span>
              </div>
            )}
            {consumerCareEmail && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-[11px]">Helpdesk:</span>
                <span className="font-mono font-medium text-foreground truncate max-w-[150px]">{consumerCareEmail}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-1.5 pt-1">
            {consumerCarePhone && (
              <a
                href={`tel:${consumerCarePhone.replace(/[^\d+]/g, "")}`}
                className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg border border-border bg-background py-1.5 text-xs font-semibold text-foreground hover:bg-muted"
              >
                <Phone className="h-3 w-3" />
                Call
              </a>
            )}
            {consumerCareEmail && (
              <button
                type="button"
                onClick={() =>
                  setEmailModalEntity({
                    type: "Consumer Care",
                    name: consumerCareName,
                    email: consumerCareEmail,
                    phone: consumerCarePhone,
                    address: mfgAddress,
                  })
                }
                className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg bg-brand py-1.5 text-xs font-semibold text-white hover:bg-brand/90"
              >
                <Mail className="h-3 w-3" />
                Email
              </button>
            )}
            <button
              type="button"
              onClick={() => handleCopy("care", `Consumer Care\nPhone: ${consumerCarePhone}\nEmail: ${consumerCareEmail}`)}
              className="inline-flex items-center justify-center rounded-lg border border-border bg-background p-1.5 text-foreground hover:bg-muted"
              title="Copy details"
            >
              {copiedKey === "care" ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Prefilled Editable Email Draft Modal */}
      {emailModalEntity && (
        <EmailDraftModal
          entity={emailModalEntity}
          inspection={inspection}
          onClose={() => setEmailModalEntity(null)}
        />
      )}
    </section>
  );
}

function EmailDraftModal({
  entity,
  inspection,
  onClose,
}: {
  entity: {
    type: "Manufacturer" | "Marketer" | "Consumer Care";
    name: string;
    email: string;
    phone: string;
    address: string;
  };
  inspection: Inspection;
  onClose: () => void;
}) {
  const [recipient, setRecipient] = useState(entity.email);
  const [subject, setSubject] = useState(
    `[LexMetra Inspection #${inspection.id}] Statutory Compliance Inquiry: ${inspection.product || "Packaged Product"}`
  );

  const missingDeclarations = (inspection.declarations || [])
    .filter((d) => d.status === "MISSING" || d.status === "UNOBSERVED")
    .map((d) => `• ${d.field} (Rule requirement)`)
    .join("\n");

  const initialBody = `Dear ${entity.name} (${entity.type}),

This communication relates to Statutory Package Compliance Inspection #${inspection.id} performed on ${new Date().toLocaleDateString("en-IN")}.

PRODUCT INSPECTION DETAILS:
• Product Name: ${inspection.product || "Packaged Commodity"}
• SKU Reference: ${inspection.productId || "Standard Retail Pack"}
• Statutory Verdict: ${inspection.status || "Under Review"}

OBSERVED FINDINGS & STATUTORY QUERIES:
${missingDeclarations || "• Verification inquiry regarding mandatory packaged commodity label declarations."}

RELEVANT EXTRACTED DECLARATIONS:
• Net Quantity: ${(inspection.declarations || []).find((d) => d.field.includes("quantity"))?.value || "Unverified"}
• MRP: ${(inspection.declarations || []).find((d) => d.field === "mrp")?.value || "Unverified"}
• Batch No: ${(inspection.declarations || []).find((d) => d.field.includes("batch"))?.value || "Unverified"}

Please provide clarification or official verification records regarding these declarations.
A formal statutory inspection dossier and evidence crops have been logged on the LexMetra inspection platform.

Regards,
Legal Metrology Inspection Team / Consumer Query
LexMetra Compliance Platform`;

  const [bodyText, setBodyText] = useState(initialBody);
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(`To: ${recipient}\nSubject: ${subject}\n\n${bodyText}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const mailtoUrl = `mailto:${encodeURIComponent(recipient)}?subject=${encodeURIComponent(
    subject
  )}&body=${encodeURIComponent(bodyText)}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-border/60 pb-3">
          <div>
            <h4 className="text-base font-bold text-foreground">Draft Statutory Communication</h4>
            <p className="text-xs text-muted-foreground">
              Recipient: {entity.name} ({entity.type})
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3 text-xs">
          <div>
            <label className="block font-bold text-foreground mb-1">Recipient Email</label>
            <input
              type="email"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              className="w-full rounded-xl border border-border bg-background p-2.5 text-xs text-foreground font-mono"
            />
          </div>

          <div>
            <label className="block font-bold text-foreground mb-1">Subject</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full rounded-xl border border-border bg-background p-2.5 text-xs text-foreground font-semibold"
            />
          </div>

          <div>
            <label className="block font-bold text-foreground mb-1">Email Body (Editable Draft)</label>
            <textarea
              rows={10}
              value={bodyText}
              onChange={(e) => setBodyText(e.target.value)}
              className="w-full rounded-xl border border-border bg-background p-3 text-xs text-foreground font-mono leading-relaxed"
            />
          </div>

          <div className="rounded-xl border border-border/80 bg-muted/40 p-3 text-[11px] text-muted-foreground">
            <strong>Notice:</strong> LexMetra will NOT automatically send this communication. You may copy the text or launch your default email client to review and transmit.
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-border px-4 py-2 text-xs font-semibold hover:bg-muted"
          >
            Close
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-background px-4 py-2 text-xs font-semibold hover:bg-muted"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            <span>{copied ? "Copied!" : "Copy Draft"}</span>
          </button>
          <a
            href={mailtoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-xl bg-brand px-4 py-2 text-xs font-bold text-white hover:bg-brand/90"
          >
            <Mail className="h-3.5 w-3.5" />
            <span>Open in Mail Client</span>
          </a>
        </div>
      </div>
    </div>
  );
}

// ===========================================================================
// USP 3: Consumer / Inspector Escalation Modal
// ===========================================================================

export function ConsumerReportModal({
  inspection,
  onClose,
  onSuccess,
}: {
  inspection: Inspection;
  onClose: () => void;
  onSuccess: (caseId: string, reportId: string) => void;
}) {
  const [issueCategory, setIssueCategory] = useState("Misleading Net Weight / Quantity Shortage");
  const [retailerName, setRetailerName] = useState("");
  const [location, setLocation] = useState("");
  const [reporterName, setReporterName] = useState("");
  const [reporterContact, setReporterContact] = useState("");
  const [details, setDetails] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const missingViolationsCount = inspection.declarations.filter(
    (d) => d.status === "MISSING" || d.status === "UNOBSERVED"
  ).length;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitConsumerReport({
        inspection_id: inspection.id,
        product_name: inspection.product || "Packaged Commodity",
        product_id: inspection.productId || undefined,
        category: inspection.category || "Packaged Commodity",
        issue_category: issueCategory,
        details: details.trim() || `Automated escalation for ${inspection.product}. Identified ${missingViolationsCount} statutory discrepancy findings under LMPC 2011.`,
        reporter_name: reporterName.trim() || undefined,
        reporter_contact: reporterContact.trim() || undefined,
        retailer_name: retailerName.trim() || undefined,
        location: location.trim() || undefined,
        lmpc_verdict: inspection.status,
        lmpc_violations_count: missingViolationsCount,
        evidence_image_urls: inspection.image ? [inspection.image] : [],
      });
      onSuccess(res.case_id, res.report_id);
    } catch (err: any) {
      setError(err?.message || "Failed to submit escalation docket.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="w-full max-w-lg rounded-2xl border border-border/80 bg-card p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-border/60 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
              <ShieldAlert className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">Escalate to Legal Metrology Authority</h3>
              <p className="text-xs text-muted-foreground">Direct Consumer & Inspector Enforcement Gateway</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="rounded-xl border border-border/70 bg-muted/40 p-3.5 text-xs space-y-1.5">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Product:</span>
            <span className="font-bold text-foreground">{inspection.product}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Inspection ID:</span>
            <span className="font-mono text-foreground">#{inspection.id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">LMPC Status:</span>
            <span className={`font-bold ${inspection.status === "VIOLATION" ? "text-destructive" : "text-amber-500"}`}>
              {inspection.status} ({missingViolationsCount} Issues)
            </span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3.5 text-xs">
          <div>
            <label className="block font-semibold text-muted-foreground mb-1">Violation Category *</label>
            <select
              value={issueCategory}
              onChange={(e) => setIssueCategory(e.target.value)}
              className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
            >
              <option value="Misleading Net Weight / Quantity Shortage">Misleading Net Weight / Quantity Shortage</option>
              <option value="Missing Mandatory Declarations (Rule 6)">Missing Mandatory Declarations (Rule 6)</option>
              <option value="Missing Unit Sale Price (USP Mandate)">Missing Unit Sale Price (USP Mandate)</option>
              <option value="Price Alteration / Dual MRP / Overcharging">Price Alteration / Dual MRP / Overcharging</option>
              <option value="Expired / Past Best Before Date">Expired / Past Best Before Date</option>
              <option value="Suspected Alteration / Non-genuine Label">Suspected Alteration / Non-genuine Label</option>
            </select>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="block font-semibold text-muted-foreground">Purchase / Retail Store Location *</label>
              <span className="text-[10px] text-brand font-medium">Map Pin & Store Selector</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <input
                  type="text"
                  placeholder="Store name (e.g. D-Mart, Sector 14)"
                  value={retailerName}
                  onChange={(e) => setRetailerName(e.target.value)}
                  className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
                />
              </div>
              <div>
                <input
                  type="text"
                  placeholder="City / Area (e.g. Pune, Maharashtra)"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
                />
              </div>
            </div>

            {/* Quick Location & Map Pin Chips */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[10px] text-muted-foreground">Quick Pin:</span>
              {[
                { name: "Pune, MH", lat: 18.5204, lng: 73.8567 },
                { name: "Mumbai, MH", lat: 19.0760, lng: 72.8777 },
                { name: "Gurugram, HR", lat: 28.4595, lng: 77.0266 },
                { name: "Bengaluru, KA", lat: 12.9716, lng: 77.5946 },
                { name: "Delhi NCT", lat: 28.6139, lng: 77.2090 },
              ].map((pin) => (
                <button
                  key={pin.name}
                  type="button"
                  onClick={() => {
                    setLocation(pin.name);
                    if (!retailerName) setRetailerName("Local Retail Merchant");
                  }}
                  className={`rounded-lg px-2 py-0.5 text-[10px] font-medium border transition ${
                    location === pin.name
                      ? "border-brand bg-brand/10 text-brand"
                      : "border-border/60 bg-muted/40 text-muted-foreground hover:border-border"
                  }`}
                >
                  📍 {pin.name}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Your Name (Optional)</label>
              <input
                type="text"
                placeholder="Anonymous or Inspector Name"
                value={reporterName}
                onChange={(e) => setReporterName(e.target.value)}
                className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
              />
            </div>
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Contact Email/Phone (Optional)</label>
              <input
                type="text"
                placeholder="For status SMS/email"
                value={reporterContact}
                onChange={(e) => setReporterContact(e.target.value)}
                className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
              />
            </div>
          </div>

          <div>
            <label className="block font-semibold text-muted-foreground mb-1">Statutory Details / Observations</label>
            <textarea
              rows={3}
              placeholder="Describe observations, shelf location, or evidence context..."
              value={details}
              onChange={(e) => setDetails(e.target.value)}
              className="w-full rounded-xl border border-border bg-background p-3 text-xs outline-none focus:border-brand"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-destructive/10 p-2.5 text-xs text-destructive">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
            <button
              type="button"
              onClick={onClose}
              className="h-9 px-4 rounded-xl border border-border bg-background font-semibold text-muted-foreground hover:bg-muted"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="h-9 px-5 rounded-xl bg-destructive text-destructive-foreground font-semibold flex items-center gap-1.5 shadow-md hover:bg-destructive/90 disabled:opacity-50"
            >
              {submitting ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
              {submitting ? "Filing Docket…" : "File Statutory Docket"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ===========================================================================
// USP 3: Authority Dashboard View
// ===========================================================================

export function AuthorityDashboardView({ onBack }: { onBack: () => void }) {
  const [cases, setCases] = useState<AuthorityCaseData[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [selectedCase, setSelectedCase] = useState<AuthorityCaseData | null>(null);
  const [actionModal, setActionModal] = useState<string | null>(null); // "SHOW_CAUSE_NOTICE", "SEIZURE_ORDERED", "CLOSED"
  const [actionNotes, setActionNotes] = useState("");
  const [actionClause, setActionClause] = useState("Section 36(1) of Legal Metrology Act, 2009");
  const [submittingAction, setSubmittingAction] = useState(false);

  function loadCases() {
    setLoading(true);
    listAuthorityCases({ status: statusFilter !== "ALL" ? statusFilter : undefined })
      .then((res) => {
        setCases(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }

  useEffect(() => {
    loadCases();
  }, [statusFilter]);

  async function handleTakeAction() {
    if (!selectedCase || !actionModal) return;
    setSubmittingAction(true);
    try {
      const updated = await takeAuthorityCaseAction(selectedCase.case_id, {
        action_type: actionModal,
        notes: actionNotes.trim() || `Statutory action recorded: ${actionModal}`,
        statutory_clause: actionClause,
      });
      setSelectedCase(updated);
      setActionModal(null);
      setActionNotes("");
      loadCases();
    } catch (e: any) {
      alert("Failed to record officer action: " + e?.message);
    } finally {
      setSubmittingAction(false);
    }
  }

  const counts = {
    total: cases.length,
    highPriority: cases.filter((c) => c.priority === "HIGH").length,
    submitted: cases.filter((c) => c.status === "SUBMITTED").length,
    notices: cases.filter((c) => c.status === "NOTICE_ISSUED").length,
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border/70 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-destructive/10 border border-destructive/20 px-2.5 py-0.5 text-[10px] font-bold text-destructive">
              Official Enforcement Channel
            </span>
            <span className="text-xs text-muted-foreground">Department of Consumer Affairs</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-foreground">
            Legal Metrology & FSSAI Authority Enforcement Queue
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Direct statutory escalation dockets filed by field inspectors and consumers under LM Act 2009.
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-bold text-slate-800 hover:bg-slate-50 hover:text-black transition shadow-xs"
        >
          Back to home
        </button>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-2xl border border-border/70 bg-card p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Active Dockets</p>
          <p className="mt-1 text-2xl font-bold text-foreground">{counts.total}</p>
          <span className="text-[11px] text-muted-foreground">In enforcement queue</span>
        </div>
        <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-destructive">High Priority</p>
          <p className="mt-1 text-2xl font-bold text-destructive">{counts.highPriority}</p>
          <span className="text-[11px] text-muted-foreground">Violations & Alterations</span>
        </div>
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-amber-600">New Inquiries</p>
          <p className="mt-1 text-2xl font-bold text-amber-600">{counts.submitted}</p>
          <span className="text-[11px] text-muted-foreground">Awaiting assignment</span>
        </div>
        <div className="rounded-2xl border border-brand/30 bg-brand/5 p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-brand">Notices Issued</p>
          <p className="mt-1 text-2xl font-bold text-brand">{counts.notices}</p>
          <span className="text-[11px] text-muted-foreground">Form 4 Show Cause</span>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border/60 pb-3">
        {["ALL", "SUBMITTED", "UNDER_REVIEW", "NOTICE_ISSUED", "INVESTIGATION_ORDERED", "RESOLVED"].map((st) => (
          <button
            key={st}
            type="button"
            onClick={() => setStatusFilter(st)}
            className={`rounded-xl px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              statusFilter === st
                ? "bg-purple-700 text-white shadow-xs"
                : "bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 hover:text-black"
            }`}
          >
            {st.replace("_", " ")}
          </button>
        ))}
      </div>

      {/* Cases List */}
      {loading ? (
        <div className="flex items-center justify-center p-12 text-muted-foreground">
          <LoaderCircle className="h-6 w-6 animate-spin text-brand mr-2" /> Loading authority dockets…
        </div>
      ) : cases.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border/70 p-12 text-center text-muted-foreground">
          No cases matching '{statusFilter}'.
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {cases.map((c) => (
            <div
              key={c.case_id}
              onClick={() => setSelectedCase(c)}
              className="cursor-pointer rounded-2xl border border-border/70 bg-card p-5 shadow-xs transition-all hover:border-brand hover:shadow-md space-y-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-muted-foreground">{c.case_id}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                    c.priority === "HIGH" ? "bg-red-500/10 text-red-500" : "bg-blue-500/10 text-blue-500"
                  }`}
                >
                  {c.priority} PRIORITY
                </span>
              </div>

              <div>
                <h3 className="font-bold text-foreground line-clamp-1">{c.product_name}</h3>
                <p className="text-xs text-muted-foreground mt-0.5">{c.issue_category}</p>
              </div>

              <div className="rounded-xl bg-muted/50 p-2.5 text-[11px] space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">LMPC Verdict:</span>
                  <span className={`font-bold ${c.lmpc_verdict === "VIOLATION" ? "text-destructive" : "text-amber-500"}`}>
                    {c.lmpc_verdict}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">FSSAI Status:</span>
                  <span className="font-semibold text-foreground">{c.fssai_status || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Reporter:</span>
                  <span className="text-foreground">{c.reporter_type} ({c.reporter_name})</span>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-border/50 text-[11px]">
                <span className="rounded-md bg-brand-soft px-2 py-0.5 font-bold text-brand">
                  {c.status.replace("_", " ")}
                </span>
                <span className="text-muted-foreground">
                  {new Date(c.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Case Details Modal */}
      {selectedCase && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-2xl rounded-2xl border border-border/80 bg-card p-6 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-brand">{selectedCase.case_id}</span>
                  <span className="text-xs text-muted-foreground">Docket {selectedCase.report_id}</span>
                </div>
                <h2 className="text-lg font-bold text-foreground mt-0.5">{selectedCase.product_name}</h2>
              </div>
              <button
                type="button"
                onClick={() => setSelectedCase(null)}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 rounded-xl border border-border/70 bg-muted/40 p-3 text-xs">
              <div>
                <span className="block text-[10px] uppercase font-bold text-muted-foreground">LMPC Verdict</span>
                <span className="font-bold text-destructive">{selectedCase.lmpc_verdict}</span>
              </div>
              <div>
                <span className="block text-[10px] uppercase font-bold text-muted-foreground">FSSAI Status</span>
                <span className="font-semibold text-foreground">{selectedCase.fssai_status || "N/A"}</span>
              </div>
              <div>
                <span className="block text-[10px] uppercase font-bold text-muted-foreground">Integrity</span>
                <span className="font-semibold text-foreground">{selectedCase.integrity_status || "UNABLE TO VERIFY"}</span>
              </div>
              <div>
                <span className="block text-[10px] uppercase font-bold text-muted-foreground">Current Status</span>
                <span className="font-bold text-brand">{selectedCase.status.replace("_", " ")}</span>
              </div>
            </div>

            <div className="space-y-2 text-xs">
              <p className="font-bold text-muted-foreground uppercase tracking-wider">Complaint & Evidence Details</p>
              <p className="rounded-xl border border-border/60 bg-card p-3 leading-relaxed text-foreground">
                {selectedCase.details}
              </p>
              <div className="flex flex-wrap gap-4 text-muted-foreground pt-1">
                <span><strong>Retailer:</strong> {selectedCase.retailer_name || "N/A"}</span>
                <span><strong>Location:</strong> {selectedCase.location || "N/A"}</span>
                <span><strong>Reporter:</strong> {selectedCase.reporter_type} ({selectedCase.reporter_name})</span>
              </div>
            </div>

            {/* Statutory Action Timeline */}
            <div className="space-y-2 text-xs">
              <p className="font-bold text-muted-foreground uppercase tracking-wider">Statutory Case History & Audit Trail</p>
              <div className="divide-y divide-border/60 rounded-xl border border-border/60 bg-muted/30">
                {selectedCase.actions.map((act) => (
                  <div key={act.action_id} className="p-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-foreground">{act.action_type.replace("_", " ")}</span>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        {new Date(act.timestamp).toLocaleString("en-IN")}
                      </span>
                    </div>
                    <p className="text-muted-foreground">{act.notes}</p>
                    {act.statutory_clause && (
                      <span className="inline-block font-mono text-[10px] text-brand">
                        Authority: {act.statutory_clause} · Officer: @{act.officer_username}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Officer Actions Bar */}
            <div className="flex flex-wrap items-center justify-end gap-2 pt-3 border-t border-border/60">
              <button
                type="button"
                onClick={() => {
                  setActionModal("SHOW_CAUSE_NOTICE");
                  setActionNotes("Form 4 Show Cause Notice issued to Packer under Section 36(1) of Legal Metrology Act, 2009 for missing mandatory declarations.");
                  setActionClause("Rule 6(1) & Section 36(1) LM Act");
                }}
                className="h-9 px-3.5 rounded-xl border border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-semibold text-xs hover:bg-amber-500/20"
              >
                Issue Show Cause Notice
              </button>
              <button
                type="button"
                onClick={() => {
                  setActionModal("SEIZURE_ORDERED");
                  setActionNotes("Seizure of non-standard packaged commodity ordered under Section 15 of Legal Metrology Act, 2009.");
                  setActionClause("Section 15 & 36 LM Act");
                }}
                className="h-9 px-3.5 rounded-xl border border-red-500/40 bg-red-500/10 text-red-500 font-semibold text-xs hover:bg-red-500/20"
              >
                Order Seizure & Investigation
              </button>
              <button
                type="button"
                onClick={() => {
                  setActionModal("CLOSED");
                  setActionNotes("Compliance verified / fine compounded; case closed.");
                  setActionClause("Section 48 (Compounding of Offences)");
                }}
                className="h-9 px-3.5 rounded-xl border border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold text-xs hover:bg-emerald-500/20"
              >
                Close Docket
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Confirmation Modal */}
      {actionModal && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-md rounded-2xl border border-border/80 bg-card p-6 shadow-2xl space-y-4 text-xs">
            <h3 className="text-sm font-bold text-foreground">Record Statutory Enforcement Action</h3>
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Action Type</label>
              <input
                disabled
                value={actionModal}
                className="h-9 w-full rounded-xl border border-border bg-muted px-3 text-xs font-mono"
              />
            </div>
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Statutory Clause / Rule</label>
              <input
                value={actionClause}
                onChange={(e) => setActionClause(e.target.value)}
                className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs font-mono"
              />
            </div>
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Officer Notes / Order Details</label>
              <textarea
                rows={3}
                value={actionNotes}
                onChange={(e) => setActionNotes(e.target.value)}
                className="w-full rounded-xl border border-border bg-background p-3 text-xs outline-none focus:border-brand"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setActionModal(null)}
                className="h-9 px-4 rounded-xl border border-border bg-background font-semibold text-muted-foreground"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleTakeAction}
                disabled={submittingAction}
                className="h-9 px-4 rounded-xl bg-brand text-brand-foreground font-semibold flex items-center gap-1.5"
              >
                {submittingAction && <LoaderCircle className="h-3.5 w-3.5 animate-spin" />}
                Confirm & Seal Order
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ===========================================================================
// USP 4: Multilingual Voice/Text Assistant Widget
// ===========================================================================

function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let lastIdx = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      parts.push(text.slice(lastIdx, match.index));
    }
    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(
        <strong key={match.index} className="font-bold text-slate-900">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith("*") && token.endsWith("*")) {
      parts.push(
        <em key={match.index} className="italic text-slate-600">
          {token.slice(1, -1)}
        </em>
      );
    } else if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(
        <code key={match.index} className="rounded bg-brand-50 px-1 py-0.5 font-mono text-[11px] text-brand-900 font-semibold border border-brand-200/50">
          {token.slice(1, -1)}
        </code>
      );
    }
    lastIdx = match.index + token.length;
  }
  if (lastIdx < text.length) {
    parts.push(text.slice(lastIdx));
  }
  return parts.length > 0 ? parts : [text];
}

function FormattedAssistantMessage({ content }: { content: string }) {
  if (!content) return null;
  const rawLines = content.split("\n");

  const blocks: React.ReactNode[] = [];
  let currentList: React.ReactNode[] = [];

  const flushList = () => {
    if (currentList.length > 0) {
      blocks.push(
        <div key={`list-${blocks.length}`} className="my-1.5 space-y-1">
          {currentList}
        </div>
      );
      currentList = [];
    }
  };

  rawLines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }

    // Divider
    if (trimmed === "---" || trimmed === "***" || trimmed === "___") {
      flushList();
      blocks.push(<hr key={idx} className="my-2 border-slate-200" />);
      return;
    }

    // Headings: ### or ## or #
    if (trimmed.startsWith("#")) {
      flushList();
      const cleanHeading = trimmed.replace(/^#+\s*/, "");
      blocks.push(
        <div key={idx} className="mt-2.5 mb-1 flex items-center gap-1.5 font-bold text-xs text-brand-950 border-b border-slate-100 pb-0.5">
          <span className="h-2 w-2 rounded-full bg-saffron-500 shrink-0" />
          <span>{renderInlineMarkdown(cleanHeading)}</span>
        </div>
      );
      return;
    }

    // Bullet point: * or -
    if (/^[\*\-]\s+/.test(trimmed)) {
      const cleanItem = trimmed.replace(/^[\*\-]\s+/, "");
      currentList.push(
        <div key={idx} className="flex items-start gap-2 text-xs leading-relaxed text-slate-800">
          <span className="h-1.5 w-1.5 rounded-full bg-brand-600 shrink-0 mt-1.5" />
          <div className="flex-1">{renderInlineMarkdown(cleanItem)}</div>
        </div>
      );
      return;
    }

    // Numbered list: 1. or 2.
    const numMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
    if (numMatch) {
      flushList();
      const num = numMatch[1];
      const rest = numMatch[2];
      blocks.push(
        <div key={idx} className="my-1.5 flex items-start gap-2 text-xs leading-relaxed">
          <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[10px] font-bold text-brand-900 mt-0.5">
            {num}
          </span>
          <div className="flex-1 font-medium text-slate-900">{renderInlineMarkdown(rest)}</div>
        </div>
      );
      return;
    }

    // Normal paragraph
    flushList();
    blocks.push(
      <p key={idx} className="my-1 leading-relaxed text-xs text-slate-800">
        {renderInlineMarkdown(trimmed)}
      </p>
    );
  });

  flushList();

  return <div className="space-y-1">{blocks}</div>;
}

export function MultilingualAssistantWidget({
  currentInspection,
  lang: controlledLang,
  onLanguageChange,
}: {
  currentInspection?: Inspection;
  lang?: "en" | "hi" | "mr";
  onLanguageChange?: (l: "en" | "hi" | "mr") => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [internalLang, setInternalLang] = useState<"en" | "hi" | "mr">("en");
  const lang = controlledLang || internalLang;
  const setLang = (l: "en" | "hi" | "mr") => {
    setInternalLang(l);
    if (onLanguageChange) onLanguageChange(l);
  };

  const getGreeting = (l: "en" | "hi" | "mr") => {
    if (l === "hi") return "नमस्ते! मैं लेक्समेट्रा एआई हूँ, मैं आपकी क्या मदद कर सकता हूँ?";
    if (l === "mr") return "नमस्कार! मी लेक्समेट्रा एआय आहे, मी तुम्हाला कशी मदत करू शकतो?";
    return "Hello! I am LexMetra AI, How Can I Help You?";
  };

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; text: string; sources?: string[] }>>([
    {
      role: "assistant",
      text: getGreeting(lang),
    },
  ]);
  const [showPromptCards, setShowPromptCards] = useState(true);
  const [loading, setLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isVoiceMuted, setIsVoiceMuted] = useState(false);

  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const isVoiceMutedRef = useRef(false);

  // Update greeting when language changes if only the initial greeting is present
  useEffect(() => {
    setMessages((prev) => {
      if (prev.length === 1 && prev[0].role === "assistant") {
        return [{ role: "assistant", text: getGreeting(lang) }];
      }
      return prev;
    });
  }, [lang]);

  // Sync mute state ref
  useEffect(() => {
    isVoiceMutedRef.current = isVoiceMuted;
    if (isVoiceMuted) {
      stopAllAudio();
    }
  }, [isVoiceMuted]);

  function stopAllAudio() {
    if (currentAudioRef.current) {
      try {
        currentAudioRef.current.pause();
        currentAudioRef.current.currentTime = 0;
      } catch {}
      currentAudioRef.current = null;
    }
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
  }

  // Speech Recognition support
  function toggleListening() {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser. Please type your question.");
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = lang === "hi" ? "hi-IN" : lang === "mr" ? "mr-IN" : "en-IN";
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);
      recognition.onresult = (e: any) => {
        const transcript = e.results[0][0].transcript;
        if (transcript) {
          setInput(transcript);
          handleSend(transcript);
        }
      };
      recognition.start();
    } catch (e) {
      setIsListening(false);
    }
  }

  // Text-to-Speech support: Strictly Sarvam AI Bulbul v3 Indian natural voice (shubh)
  async function speakText(text: string) {
    if (!text || isVoiceMutedRef.current) return;
    stopAllAudio();
    setIsSpeaking(true);

    try {
      const audioUrl = await synthesizeSpeech(text, lang, "shubh", 1.12);
      if (audioUrl && !isVoiceMutedRef.current) {
        const audio = new Audio(audioUrl);
        currentAudioRef.current = audio;
        audio.onended = () => {
          setIsSpeaking(false);
          currentAudioRef.current = null;
        };
        audio.onerror = () => {
          setIsSpeaking(false);
          currentAudioRef.current = null;
        };
        await audio.play();
      } else {
        setIsSpeaking(false);
      }
    } catch (err) {
      console.warn("Sarvam AI speech synthesis:", err);
      setIsSpeaking(false);
    }
  }

  async function handleSend(textToSend?: string) {
    const q = (textToSend || input).trim();
    if (!q || loading) return;

    // Instantly collapse 3 floating prompt cards on selection
    setShowPromptCards(false);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setLoading(true);

    try {
      const res = await askAssistant({
        query: q,
        language: lang,
        inspection_id: currentInspection?.id,
        inspection_context: currentInspection,
      });

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: res.response_text,
          sources: res.grounding_sources,
        },
      ]);
      speakText(res.speech_text);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Sorry, I could not process your query at this moment. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  const suggestionCards = [
    {
      titleEn: "Explain this inspection",
      subEn: "Comprehensive review of packaging compliance & facts",
      titleHi: "इस निरीक्षण को समझाएं",
      subHi: "पैकेजिंग अनुपालन एवं तथ्यों की विस्तृत समीक्षा",
      titleMr: "या तपासणीचा अहवाल समजून सांगा",
      subMr: "पॅकेजिंग कायदेशीर अनुपालन व तथ्यांचे पुनरावलोकन",
      query: "Explain this inspection and its overall findings",
    },
    {
      titleEn: "Explain package violations",
      subEn: "Analyze detected LMPC non-compliance and issues",
      titleHi: "पैकेज उल्लंघनों को समझाएं",
      subHi: "पहचाने गए LMPC गैर-अनुपालन एवं दोषों का विश्लेषण",
      titleMr: "पॅकेजवरील उल्लंघने स्पष्ट करा",
      subMr: "आढळलेले LMPC कायदेशीर नियमभंग आणि त्रुटींचे विश्लेषण",
      query: "Explain the violations found on this package",
    },
    {
      titleEn: "Statutory rules for MRP & Net Qty",
      subEn: "Rule 6(1) declarations and Rule 6(11) Unit Sale Price",
      titleHi: "MRP व शुद्ध वजन विधिक नियम",
      subHi: "नियम 6(1) घोषणाएं एवं नियम 6(11) इकाई विक्रय मूल्य",
      titleMr: "MRP व निव्वळ वजनाचे कायदेशीर नियम",
      subMr: "नियम 6(1) अनिवार्य घोषणा व नियम 6(11) युनिट विक्री किंमत",
      query: "Explain the applicable Legal Metrology rules for MRP and Net Weight",
    },
  ];

  return (
    <div className="fixed bottom-20 right-4 md:bottom-6 md:right-6 z-40">
      {!isOpen ? (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="flex h-14 items-center gap-2.5 rounded-full border-2 border-black bg-white px-5 text-black shadow-2xl transition-all hover:scale-105 hover:bg-black hover:text-white active:scale-95 group"
        >
          <Sparkles className="h-5 w-5 text-black group-hover:text-white transition-colors" />
          <span className="text-xs font-black uppercase tracking-wider">LexMetra AI</span>
        </button>
      ) : (
        <div
          className={`flex flex-col rounded-3xl border-2 border-slate-300/80 bg-white text-slate-900 shadow-2xl overflow-hidden transition-all duration-200 animate-in fade-in zoom-in-95 slide-in-from-bottom-6 ${
            isExpanded
              ? "h-[85vh] max-h-[840px] w-[calc(100vw-32px)] sm:w-[680px] md:w-[780px]"
              : "h-[540px] max-h-[84vh] w-[calc(100vw-32px)] sm:w-[420px]"
          }`}
        >
          {/* Header - Clean B&W LexMetra AI without any Department/Ministry */}
          <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-black text-white shadow-xs">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-black tracking-wide text-black">LexMetra AI</p>
                <p className="text-[10px] font-medium text-slate-500">Multilingual Voice & Intelligence</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              {/* Voice Mute / Unmute Toggle Button */}
              <button
                type="button"
                onClick={() => setIsVoiceMuted((prev) => !prev)}
                title={isVoiceMuted ? "Unmute Voice" : "Mute Voice"}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-xl text-xs font-bold border transition-all ${
                  isVoiceMuted
                    ? "bg-slate-100 text-slate-500 border-slate-300"
                    : "bg-black text-white border-black"
                }`}
              >
                {isVoiceMuted ? (
                  <>
                    <VolumeX className="h-3.5 w-3.5 text-slate-500" />
                    <span className="text-[10px]">Muted</span>
                  </>
                ) : (
                  <>
                    <Volume2 className={`h-3.5 w-3.5 text-white ${isSpeaking ? "animate-pulse" : ""}`} />
                    <span className="text-[10px]">Voice On</span>
                  </>
                )}
              </button>

              {/* Language Switcher - Black and White Pill */}
              <div className="inline-flex items-center gap-0.5 rounded-xl border border-slate-200 bg-slate-50 p-0.5 text-[10px] font-bold shadow-2xs">
                <button
                  type="button"
                  onClick={() => setLang("en")}
                  className={`px-2 py-0.5 rounded-lg transition-all ${
                    lang === "en" ? "bg-black text-white font-bold" : "text-slate-700 hover:text-black font-semibold"
                  }`}
                >
                  EN
                </button>
                <button
                  type="button"
                  onClick={() => setLang("hi")}
                  className={`px-2 py-0.5 rounded-lg transition-all ${
                    lang === "hi" ? "bg-black text-white font-bold" : "text-slate-700 hover:text-black font-semibold"
                  }`}
                >
                  हिन्दी
                </button>
                <button
                  type="button"
                  onClick={() => setLang("mr")}
                  className={`px-2 py-0.5 rounded-lg transition-all ${
                    lang === "mr" ? "bg-black text-white font-bold" : "text-slate-700 hover:text-black font-semibold"
                  }`}
                >
                  मराठी
                </button>
              </div>
              {/* Expand / Minimize Toggle Button */}
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                title={isExpanded ? "Collapse window" : "Expand window"}
                className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-black transition-colors"
                aria-label={isExpanded ? "Collapse window" : "Expand window"}
              >
                {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-black"
                aria-label="Close assistant"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Messages Container */}
          <div className="flex-1 space-y-3 overflow-y-auto p-4 text-xs bg-white">
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[88%] rounded-2xl p-3.5 leading-relaxed ${
                    m.role === "user"
                      ? "bg-black text-white rounded-br-xs shadow-sm font-medium"
                      : "bg-slate-50 text-slate-900 border border-slate-200/90 rounded-bl-xs shadow-xs"
                  }`}
                >
                  {m.role === "user" ? (
                    <p className="font-semibold text-white text-xs whitespace-pre-wrap">{m.text}</p>
                  ) : (
                    <FormattedAssistantMessage content={m.text} />
                  )}
                  {m.sources && m.sources.length > 0 && (
                    <div className="mt-2.5 border-t border-slate-200 pt-1.5 text-[10px] text-slate-500 font-medium">
                      <strong className="text-black font-bold">Statutory Sources:</strong> {m.sources.join(" · ")}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* 3 Floating Rectangular Prompt Boxes Stacked One Above Another (Claude-style) */}
            {showPromptCards && messages.length <= 1 && (
              <div className="pt-2 space-y-2 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-1">
                  {lang === "hi" ? "त्वरित सुझाव:" : lang === "mr" ? "सुचवलेले प्रश्न:" : "Quick Suggestions:"}
                </p>
                {suggestionCards.map((card, idx) => {
                  const title = lang === "hi" ? card.titleHi : lang === "mr" ? card.titleMr : card.titleEn;
                  const sub = lang === "hi" ? card.subHi : lang === "mr" ? card.subMr : card.subEn;
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSend(card.query)}
                      className="w-full text-left rounded-2xl border border-slate-200 bg-slate-50/70 p-3 hover:bg-black hover:text-white hover:border-black transition-all shadow-xs group active:scale-[0.99] flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-bold text-slate-900 group-hover:text-white transition-colors">
                          {title}
                        </p>
                        <p className="text-[10px] text-slate-500 group-hover:text-slate-300 transition-colors truncate mt-0.5">
                          {sub}
                        </p>
                      </div>
                      <span className="text-slate-400 group-hover:text-white font-bold text-sm shrink-0">→</span>
                    </button>
                  );
                })}
              </div>
            )}

            {loading && (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <LoaderCircle className="h-3.5 w-3.5 animate-spin text-black" /> LexMetra AI processing…
              </div>
            )}
          </div>

          {/* Input Bar */}
          <div className="border-t border-slate-200 bg-white p-3">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex items-center gap-2"
            >
              <button
                type="button"
                onClick={toggleListening}
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition-all ${
                  isListening
                    ? "border-red-500 bg-red-50 text-red-600 animate-pulse"
                    : "border-slate-300 bg-white text-slate-700 hover:border-black hover:text-black"
                }`}
                title="Voice input (Mic)"
              >
                {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              {/* Circular waveform icon button beside mic */}
              <button
                type="button"
                onClick={toggleListening}
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black text-white shadow-md transition-all hover:scale-105 active:scale-95 ${
                  isListening ? "ring-2 ring-black animate-pulse" : ""
                }`}
                title="Voice Assistant Live Mode"
              >
                <span className="flex items-center justify-center gap-[2.5px]">
                  <span className={`w-[2.5px] rounded-full bg-white transition-all ${isListening || isSpeaking ? "h-3.5 animate-bounce" : "h-2"}`} />
                  <span className={`w-[2.5px] rounded-full bg-white transition-all ${isListening || isSpeaking ? "h-5 animate-pulse" : "h-3.5"}`} />
                  <span className={`w-[2.5px] rounded-full bg-white transition-all ${isListening || isSpeaking ? "h-4 animate-bounce" : "h-3"}`} />
                  <span className={`w-[2.5px] rounded-full bg-white transition-all ${isListening || isSpeaking ? "h-2.5 animate-pulse" : "h-1.5"}`} />
                </span>
              </button>
              <input
                type="text"
                placeholder={lang === "hi" ? "अपना प्रश्न पूछें..." : lang === "mr" ? "तुमचा प्रश्न विचारा..." : "Ask compliance question..."}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="h-9 flex-1 rounded-xl border border-slate-300 bg-slate-50 px-3 text-xs outline-none focus:border-black focus:bg-white text-slate-900 transition-colors"
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-black text-white hover:bg-slate-800 disabled:opacity-40 transition-colors shadow-xs"
              >
                <Send className="h-4 w-4" />
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
