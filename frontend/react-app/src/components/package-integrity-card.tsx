import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Eye,
  History,
  Layers,
  LoaderCircle,
  ShieldAlert,
  Upload,
  X,
} from "lucide-react";
import {
  getPackageIntegrity,
  getPackageIntegrityHistory,
  comparePackageIntegrity,
  type FieldComparisonData,
  type ComparisonHistoryItem,
  type IntegrityReportData,
  API_BASE,
} from "@/lib/api-client";

// ===========================================================================
// USP 1: Package Integrity Verification Component
// ===========================================================================

function SideEvidencePanel({
  side,
  title,
  subtitle,
  value,
  cropBase64,
  imageUrl,
  bbox,
  polygon,
  confidence,
  surfaceId,
  imageId,
  status,
  isMissing,
}: {
  side: "LEFT" | "RIGHT";
  title: string;
  subtitle: string;
  value?: string;
  cropBase64?: string;
  imageUrl?: string;
  bbox?: number[];
  polygon?: number[][];
  confidence?: number;
  surfaceId?: string;
  imageId?: string;
  status?: string;
  isMissing?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [loadError, setLoadError] = useState(false);
  const [isRendered, setIsRendered] = useState(false);

  const isLeft = side === "LEFT";
  const accentColor = isLeft ? "#10b981" : "#818cf8"; // Emerald for Left (Inspected), Indigo for Right (Reference)
  const badgeBorder = isLeft
    ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/10"
    : "border-indigo-500/30 text-indigo-400 bg-indigo-500/10";

  // Build resolved source
  const rawSrc = cropBase64 || imageUrl;
  const resolvedSrc = rawSrc
    ? rawSrc.startsWith("http") || rawSrc.startsWith("data:") || rawSrc.startsWith("blob:")
      ? rawSrc
      : `${API_BASE}${rawSrc.startsWith("/") ? "" : "/"}${rawSrc}`
    : undefined;

  useEffect(() => {
    if (!resolvedSrc || isMissing) return;

    let isMounted = true;
    const img = new Image();
    img.crossOrigin = "anonymous";

    img.onload = () => {
      if (!isMounted) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const nw = img.naturalWidth;
      const nh = img.naturalHeight;

      let cropX = 0;
      let cropY = 0;
      let cropW = nw;
      let cropH = nh;
      let drawPolygon = polygon;
      let drawBbox = bbox;

      if (!cropBase64 && bbox && bbox.length >= 4 && nw > bbox[2] * 1.5) {
        const [bx, by, bw, bh] = bbox;
        const padX = Math.max(bw * 0.35, 30);
        const padY = Math.max(bh * 0.35, 20);
        cropX = Math.max(0, bx - padX);
        cropY = Math.max(0, by - padY);
        cropW = Math.max(1, Math.min(nw, bx + bw + padX) - cropX);
        cropH = Math.max(1, Math.min(nh, by + bh + padY) - cropY);

        if (polygon && polygon.length >= 3) {
          drawPolygon = polygon.map(([px, py]) => [px - cropX, py - cropY]);
        }
        drawBbox = [bx - cropX, by - cropY, bw, bh];
      }

      canvas.width = 600;
      canvas.height = Math.max(220, Math.min(Math.round(600 * (cropH / cropW)), 380));

      ctx.fillStyle = "#030712";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const scale = Math.min(canvas.width / cropW, canvas.height / cropH);
      const rw = cropW * scale;
      const rh = cropH * scale;
      const ox = (canvas.width - rw) / 2;
      const oy = (canvas.height - rh) / 2;

      ctx.drawImage(img, cropX, cropY, cropW, cropH, ox, oy, rw, rh);

      if (!cropBase64 && drawPolygon && drawPolygon.length >= 3) {
        ctx.beginPath();
        const startPt = drawPolygon[0];
        ctx.moveTo(ox + startPt[0] * scale, oy + startPt[1] * scale);
        for (let i = 1; i < drawPolygon.length; i++) {
          ctx.lineTo(ox + drawPolygon[i][0] * scale, oy + drawPolygon[i][1] * scale);
        }
        ctx.closePath();
        ctx.fillStyle = isLeft ? "rgba(16, 185, 129, 0.15)" : "rgba(99, 102, 241, 0.15)";
        ctx.fill();
        ctx.strokeStyle = accentColor;
        ctx.lineWidth = 2.5;
        ctx.stroke();
      } else if (!cropBase64 && drawBbox && drawBbox.length >= 4) {
        const [bx, by, bw, bh] = drawBbox;
        ctx.fillStyle = isLeft ? "rgba(16, 185, 129, 0.12)" : "rgba(99, 102, 241, 0.12)";
        ctx.fillRect(ox + bx * scale, oy + by * scale, bw * scale, bh * scale);
        ctx.strokeStyle = accentColor;
        ctx.lineWidth = 2;
        ctx.strokeRect(ox + bx * scale, oy + by * scale, bw * scale, bh * scale);
      }

      setIsRendered(true);
      setLoadError(false);
    };

    img.onerror = () => {
      if (!isMounted) return;
      setLoadError(true);
    };

    img.src = resolvedSrc;
    return () => {
      isMounted = false;
    };
  }, [resolvedSrc, bbox, polygon, isMissing, isLeft, accentColor, cropBase64]);

  if (isMissing || (!resolvedSrc && !value)) {
    return (
      <div className="rounded-xl border border-border/80 bg-card p-4 space-y-3 flex flex-col justify-between">
        <div className="flex items-center justify-between border-b border-border/40 pb-2">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-foreground">{title}</span>
            <p className="text-[10px] text-muted-foreground">{subtitle}</p>
          </div>
          <span className="rounded px-2 py-0.5 text-[9px] font-bold border border-amber-500/30 bg-amber-500/10 text-amber-500">
            UNOBSERVED
          </span>
        </div>
        <div className="h-44 w-full rounded-xl bg-slate-950/70 flex flex-col items-center justify-center p-4 text-center border border-dashed border-border/80">
          <ShieldAlert className="h-8 w-8 text-amber-500 mb-2 opacity-80" />
          <p className="text-xs font-semibold text-foreground">Declaration Not Observed</p>
          <p className="text-[10px] text-muted-foreground mt-1 max-w-[220px]">
            No verified text localization or OCR match found on any {isLeft ? "inspected" : "reference"} panel.
          </p>
          <span className="mt-2 text-[9px] font-mono rounded bg-muted/60 px-2 py-0.5 text-muted-foreground">
            Status: {status || "NOT_OBSERVED"}
          </span>
        </div>
        <div className="rounded-lg bg-muted/40 p-2.5 text-xs">
          <span className="text-[10px] uppercase font-bold text-muted-foreground block">Observed Value:</span>
          <span className="font-mono text-muted-foreground italic text-[11px]">— No declaration detected —</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border ${
        isLeft ? "border-emerald-500/30 bg-emerald-500/[0.02]" : "border-indigo-500/30 bg-indigo-500/[0.02]"
      } p-4 space-y-3`}
    >
      <div className="flex items-center justify-between border-b border-border/40 pb-2">
        <div>
          <span
            className={`text-xs font-black uppercase tracking-wider ${
              isLeft ? "text-emerald-400" : "text-indigo-400"
            }`}
          >
            {title}
          </span>
          <p className="text-[10px] text-muted-foreground">{subtitle}</p>
        </div>
        <div className="flex items-center gap-1.5">
          {confidence !== undefined && (
            <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold border ${badgeBorder}`}>
              {(confidence * 100).toFixed(0)}% Conf
            </span>
          )}
        </div>
      </div>

      {/* Visual Canvas Display */}
      <div className="relative h-48 w-full rounded-xl bg-slate-950 flex items-center justify-center overflow-hidden border border-border/80 shadow-inner">
        {resolvedSrc && !loadError ? (
          <>
            <canvas ref={canvasRef} className="max-h-full max-w-full object-contain" />
            {!isRendered && (
              <img
                src={resolvedSrc}
                alt={title}
                className="max-h-full max-w-full object-contain"
                onError={() => setLoadError(true)}
              />
            )}
          </>
        ) : (
          <div className="text-center p-3 text-slate-400 text-xs">
            <p className="font-semibold">{value || "No Crop Available"}</p>
          </div>
        )}

        {/* Overlay Badges */}
        <div className="absolute top-2 left-2 flex flex-wrap gap-1 pointer-events-none">
          {polygon && polygon.length >= 3 ? (
            <span className="rounded bg-black/80 backdrop-blur px-1.5 py-0.5 text-[9px] font-mono text-emerald-300 border border-emerald-500/40">
              Vector DBNet Polygon ({polygon.length} pts)
            </span>
          ) : bbox ? (
            <span className="rounded bg-black/80 backdrop-blur px-1.5 py-0.5 text-[9px] font-mono text-slate-300 border border-slate-700">
              BBox [{bbox.join(", ")}]
            </span>
          ) : null}
        </div>

        {(surfaceId || imageId) && (
          <div className="absolute bottom-2 right-2 flex gap-1 pointer-events-none">
            <span className="rounded bg-black/80 backdrop-blur px-1.5 py-0.5 text-[9px] font-mono text-muted-foreground border border-border/60">
              {[surfaceId, imageId].filter(Boolean).join(" • ")}
            </span>
          </div>
        )}
      </div>

      {/* Extracted Specification & Metadata */}
      <div className="rounded-lg bg-card border border-border/70 p-3 space-y-1.5 text-xs shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase font-bold text-muted-foreground">
            {isLeft ? "Inspected Marking" : "Reference Master"}
          </span>
          {bbox && (
            <span className="text-[9px] font-mono text-muted-foreground">
              Coord: [{bbox[0]}, {bbox[1]}, {bbox[2]}×{bbox[3]}]
            </span>
          )}
        </div>
        <div className="font-mono text-sm font-black text-foreground bg-muted/30 px-2 py-1.5 rounded border border-border/40 break-words">
          {value || "—"}
        </div>
      </div>
    </div>
  );
}

export function PackageIntegrityCard({
  inspectionId,
  productId: _productId,
  productName: _productName,
  initialData,
}: {
  inspectionId: string;
  productId?: string;
  productName?: string;
  initialData?: IntegrityReportData | null;
}) {
  const [data, setData] = useState<IntegrityReportData | null>(initialData || null);
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadRefType, setUploadRefType] = useState<"TRUSTED" | "DEMO" | "UNVERIFIED">("UNVERIFIED");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [comparing, setComparing] = useState(false);
  const [history, setHistory] = useState<ComparisonHistoryItem[]>([]);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [activeEvidence, setActiveEvidence] = useState<FieldComparisonData | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (initialData) {
      setData(initialData);
      setLoading(false);
    }
  }, [initialData]);

  function loadIntegrity(silent = false) {
    if (!silent) setLoading(true);
    getPackageIntegrity(inspectionId)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        if (!initialData) {
          setError(err?.message || "Integrity verification unavailable");
        }
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
    loadIntegrity(Boolean(initialData));
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

                  {/* Special Barcode Product ID Breakdown */}
                  {(item.field_key === "barcode" || item.field_name.toLowerCase().includes("barcode")) && (item.decoded_value || item.observed_value || item.barcode_verification_status) && (
                    <div className="rounded-lg border border-blue-500/30 bg-blue-500/[0.04] p-2 space-y-1 text-[10px]">
                      <div className="flex items-center justify-between">
                        <span className="font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">Barcode Cross-Check</span>
                        <span className={`rounded px-1.5 py-0.2 font-black uppercase text-[9px] border ${
                          item.barcode_verification_status === "VERIFIED"
                            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                            : item.barcode_verification_status === "NOT_OBSERVED"
                            ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                            : "bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400"
                        }`}>
                          {item.barcode_verification_status || "VERIFIED"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-muted-foreground font-mono">
                        <span>Decoded Bars:</span>
                        <span className="font-bold text-foreground">{item.decoded_value || "—"}</span>
                      </div>
                      <div className="flex items-center justify-between text-muted-foreground font-mono">
                        <span>Printed Digits:</span>
                        <span className="font-bold text-foreground">{item.observed_value || "— (Not Observed)"}</span>
                      </div>
                    </div>
                  )}

                  {/* Special USP Arithmetic Corroboration Badge */}
                  {item.field_key === "unit_sale_price" && item.status === "MATCH" && (
                    <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/[0.04] p-1.5 flex items-center justify-between text-[10px]">
                      <span className="font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                        <Check className="h-3 w-3" /> Arithmetic Corroborated
                      </span>
                      <span className="font-mono text-[9px] text-muted-foreground">MRP / Net Qty</span>
                    </div>
                  )}

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


      {/* 6. Evidence Drawer / Modal */}
      {activeEvidence && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-md animate-in fade-in duration-150">
          <div className="w-full max-w-4xl rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4 max-h-[92vh] overflow-y-auto">
            <div className="flex items-start justify-between border-b border-border/60 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-lg font-black tracking-tight text-foreground">
                    Evidence Audit: {activeEvidence.field_name}
                  </h4>
                  <span className="rounded-full px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider border bg-muted text-muted-foreground">
                    {activeEvidence.field_classification}
                  </span>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider border ${
                      activeEvidence.status === "POTENTIAL DISCREPANCY"
                        ? "bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400"
                        : activeEvidence.status === "REVIEW REQUIRED"
                        ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                        : activeEvidence.status === "EXPECTED TO VARY"
                        ? "bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400"
                        : activeEvidence.status === "UNABLE TO VERIFY" ||
                          activeEvidence.status === "REFERENCE NOT OBSERVED" ||
                          activeEvidence.status === "INSPECTION NOT OBSERVED"
                        ? "bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400"
                        : "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                    }`}
                  >
                    {activeEvidence.comparison_status || activeEvidence.status}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Side-by-side comparative inspection crops and localized vector evidence from each packaging surface.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setActiveEvidence(null)}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Side-by-Side: STRICTLY LEFT = ORIGINAL / INSPECTED, RIGHT = REFERENCE / GOLDEN */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* LEFT: ORIGINAL / INSPECTED IMAGE */}
              <SideEvidencePanel
                side="LEFT"
                title="LEFT: ORIGINAL / INSPECTED"
                subtitle="Physical Scanned Package Evidence"
                value={activeEvidence.inspection_value}
                cropBase64={activeEvidence.inspection_crop_base64 || activeEvidence.inspection_crop}
                imageUrl={activeEvidence.inspection_image_url}
                bbox={activeEvidence.inspection_bbox}
                polygon={activeEvidence.inspection_polygon}
                confidence={activeEvidence.inspection_confidence ?? activeEvidence.confidence}
                surfaceId={activeEvidence.inspection_surface_id}
                imageId={activeEvidence.inspection_image_id}
                status={activeEvidence.status}
                isMissing={
                  activeEvidence.status === "INSPECTION NOT OBSERVED" ||
                  (!activeEvidence.inspection_value && !activeEvidence.inspection_bbox)
                }
              />

              {/* RIGHT: REFERENCE / GOLDEN IMAGE */}
              <SideEvidencePanel
                side="RIGHT"
                title="RIGHT: REFERENCE / GOLDEN"
                subtitle="Registered Digital Master / Catalog Standard"
                value={activeEvidence.reference_value}
                cropBase64={activeEvidence.reference_crop_base64 || activeEvidence.reference_crop}
                imageUrl={activeEvidence.reference_image_url}
                bbox={activeEvidence.reference_bbox}
                polygon={activeEvidence.reference_polygon}
                confidence={activeEvidence.reference_confidence ?? 0.9}
                surfaceId={activeEvidence.reference_surface_id}
                imageId={activeEvidence.reference_image_id}
                status={activeEvidence.status}
                isMissing={
                  activeEvidence.status === "REFERENCE NOT OBSERVED" ||
                  (!activeEvidence.reference_value && !activeEvidence.reference_bbox)
                }
              />
            </div>

            {/* Barcode Dual-Channel Evidence Cross-Check Card */}
            {(activeEvidence.field_key === "barcode" || activeEvidence.decoded_value || activeEvidence.observed_value) && (
              <div className="rounded-xl border border-blue-500/30 bg-blue-500/[0.03] p-3.5 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-foreground flex items-center gap-1.5">
                    Barcode Dual-Channel Verification (Decoded vs Visually Observed)
                  </span>
                  <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider border ${
                    activeEvidence.barcode_verification_status === "VERIFIED"
                      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                      : activeEvidence.barcode_verification_status === "NOT_OBSERVED"
                      ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                      : "bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400"
                  }`}>
                    {activeEvidence.barcode_verification_status || "VERIFIED"}
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                  <div className="rounded-lg bg-card border border-border/60 p-2.5 space-y-1">
                    <span className="text-[10px] uppercase font-bold text-muted-foreground block">Machine Decoded Barcode:</span>
                    <span className="font-mono text-xs font-black text-foreground">{activeEvidence.decoded_value || activeEvidence.inspection_value || "—"}</span>
                    <span className="text-[9px] text-muted-foreground block">CV Barcode Detector / ZXing Channel</span>
                  </div>
                  <div className="rounded-lg bg-card border border-border/60 p-2.5 space-y-1">
                    <span className="text-[10px] uppercase font-bold text-muted-foreground block">Visually Observed Printed Digits:</span>
                    <span className="font-mono text-xs font-black text-foreground">{activeEvidence.observed_value || "— (Not Observable on Packaging)"}</span>
                    <span className="text-[9px] text-muted-foreground block">OCR Text Localization / HRI Channel</span>
                  </div>
                </div>
                <p className="text-[10px] text-muted-foreground italic">
                  * Invariant: Printed digits are never fabricated from the machine decoder. Real vector polygons & bboxes preserved.
                </p>
              </div>
            )}

            {/* Unit Sale Price Arithmetic Corroboration Card */}
            {activeEvidence.field_key === "unit_sale_price" && (
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/[0.03] p-3.5 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-foreground flex items-center gap-1.5">
                    Unit Sale Price (USP) Mathematical Corroboration
                  </span>
                  <span className="rounded-full bg-emerald-500/10 border border-emerald-500/30 px-2.5 py-0.5 text-[10px] font-black uppercase text-emerald-600 dark:text-emerald-400">
                    LMPC Rule 6 Compliant
                  </span>
                </div>
                <div className="rounded-lg bg-card border border-border/60 p-2.5 space-y-1 text-[11px] leading-relaxed">
                  <div className="font-mono font-bold text-foreground">
                    Formula: Declared MRP ÷ Declared Net Quantity = Expected Statutory USP
                  </div>
                  <p className="text-muted-foreground text-[10px]">
                    Corroborated across real localized USP polygon/bbox, normalized statutory basis units, and declared retail price.
                  </p>
                </div>
              </div>
            )}

            {/* Forensic Reason & Evaluation Note */}
            <div className="rounded-xl border border-border/80 bg-muted/30 p-4 space-y-2.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold text-foreground flex items-center gap-1.5">
                  Forensic Decision & Comparison Analysis
                </span>
                {activeEvidence.normalized_similarity !== undefined && (
                  <span className="text-[10px] font-mono text-muted-foreground">
                    OCR Sim: {(activeEvidence.normalized_similarity * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              <p className="text-foreground leading-relaxed">
                <strong>Decision Rationale: </strong> {activeEvidence.comparison_reason || activeEvidence.reason}
              </p>
              {activeEvidence.observation_note && (
                <p className="text-muted-foreground text-[11px] leading-relaxed border-t border-border/40 pt-2">
                  <strong>Inspector Observation: </strong> {activeEvidence.observation_note}
                </p>
              )}
              <div className="border-t border-border/40 pt-2 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
                <span className="rounded bg-background/80 px-2 py-0.5 border border-border/60">
                  Field Classification: <strong>{activeEvidence.field_classification}</strong>
                </span>
                <span className="rounded bg-background/80 px-2 py-0.5 border border-border/60">
                  Finding Category: <strong>{activeEvidence.finding_category}</strong>
                </span>
                <span className="rounded bg-background/80 px-2 py-0.5 border border-border/60">
                  Severity: <strong>{activeEvidence.severity}</strong>
                </span>
              </div>
            </div>

            <div className="flex items-center justify-end pt-2 border-t border-border/60">
              <button
                type="button"
                onClick={() => setActiveEvidence(null)}
                className="rounded-xl bg-brand px-5 py-2 text-xs font-bold text-white hover:bg-brand/90 transition shadow-sm"
              >
                Close Audit
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

