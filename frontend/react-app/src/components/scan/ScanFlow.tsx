import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Camera,
  CameraOff,
  Check,
  ChevronDown,
  Flashlight,
  Image as ImageIcon,
  Info,
  LoaderCircle,
  RefreshCcw,
  Sparkles,
  WifiOff,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { AppHeader } from "@/components/layout";
import { Button } from "@/components/ui";
import { ApiError, extractPreview, type ExtractPreviewResponse } from "@/lib/api-client";
import { dataUrlToBlob } from "@/lib/data-url";
import type { Inspection, ScanDetails } from "@/lib/types";

export function ScanView({ onCaptured, onBack }: { onCaptured: (images: string[]) => void; onBack: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState(false);
  const [captured, setCaptured] = useState<string[]>([]);

  useEffect(() => () => { streamRef.current?.getTracks().forEach((track) => track.stop()); }, []);

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) { setCameraError(true); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setCameraActive(true);
    } catch { setCameraError(true); }
  }

  function addImage(dataUrl: string) {
    setCaptured((current) => [...current, dataUrl]);
  }

  function capture() {
    if (!cameraActive || !videoRef.current) return;
    const video = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 800;
    canvas.height = video.videoHeight || 1000;
    canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
    addImage(canvas.toDataURL("image/jpeg", 0.85));
  }

  function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { if (typeof reader.result === "string") addImage(reader.result); };
    reader.readAsDataURL(file);
    event.target.value = "";
  }

  function removeAt(index: number) {
    setCaptured((current) => current.filter((_, i) => i !== index));
  }

  return (
    <div className="min-h-screen bg-primary text-primary-foreground">
      <div className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 pb-8 pt-5 sm:px-6">
        <div className="flex items-center justify-between">
          <button type="button" onClick={onBack} className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-foreground/10 hover:bg-primary-foreground/15" aria-label="Back"><ArrowLeft className="h-5 w-5" /></button>
          <div className="text-center">
            <p className="text-[10px] font-bold uppercase tracking-[.2em] text-primary-foreground/60">Live capture</p>
            <h1 className="mt-1 text-lg font-semibold">Scan product</h1>
          </div>
          <button type="button" className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-foreground/10 hover:bg-primary-foreground/15" aria-label="Flash"><Flashlight className="h-5 w-5" /></button>
        </div>

        <div className="flex flex-1 flex-col justify-center py-8">
          <div className="relative mx-auto aspect-[4/5] w-full max-w-md overflow-hidden rounded-3xl border border-primary-foreground/20 bg-primary-foreground/5">
            <video ref={videoRef} autoPlay playsInline muted className={`h-full w-full object-cover ${cameraActive ? "block" : "hidden"}`} />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="relative h-[76%] w-[76%] rounded-2xl border border-primary-foreground/30">
                <span className="absolute -left-px -top-px h-10 w-10 rounded-tl-xl border-l-2 border-t-2 border-brand" />
                <span className="absolute -right-px -top-px h-10 w-10 rounded-tr-xl border-r-2 border-t-2 border-brand" />
                <span className="absolute -bottom-px -left-px h-10 w-10 rounded-bl-xl border-b-2 border-l-2 border-brand" />
                <span className="absolute -bottom-px -right-px h-10 w-10 rounded-br-xl border-b-2 border-l-2 border-brand" />
                {cameraActive && <div className="scan-line absolute inset-x-4 top-1/2 h-px bg-brand shadow-[0_0_18px] shadow-brand" />}
              </div>
            </div>
            {!cameraActive && (
              <div className="absolute inset-x-8 bottom-8 rounded-2xl border border-primary-foreground/15 bg-primary-foreground/10 p-4 text-center backdrop-blur">
                <Camera className="mx-auto h-7 w-7 text-primary-foreground/70" />
                <p className="mt-2 text-sm font-semibold">Camera preview</p>
                <p className="mt-1 text-xs leading-5 text-primary-foreground/60">Position the package label inside the frame, or pick a photo from the gallery — the dashboard Scan tab is a file upload of the same pipeline.</p>
                <Button variant="secondary" className="mt-4 bg-primary-foreground text-primary" onClick={startCamera}><Camera className="h-4 w-4" />Enable camera</Button>
              </div>
            )}
          </div>

          <p className="mx-auto mt-5 max-w-sm text-center text-sm text-primary-foreground/65">
            Capture the front (product name) and back (declarations) separately for the most accurate result. Every
            photo you capture is analyzed together as one inspection.
          </p>
          {cameraError && <div className="mx-auto mt-3 flex items-center gap-2 rounded-lg bg-warning/20 px-3 py-2 text-xs text-warning"><CameraOff className="h-4 w-4" />Camera unavailable — use gallery instead.</div>}

          {captured.length > 0 && (
            <div className="mx-auto mt-6 flex max-w-md gap-3 overflow-x-auto hide-scrollbar">
              {captured.map((img, index) => (
                <div key={index} className="relative h-20 w-16 shrink-0 overflow-hidden rounded-lg border border-primary-foreground/20">
                  <img src={img} alt={`Capture ${index + 1}`} className="h-full w-full object-cover" />
                  <span className="absolute left-1 top-1 rounded bg-primary-foreground/80 px-1 text-[9px] font-bold text-primary">{index === 0 ? "Primary" : index + 1}</span>
                  <button type="button" onClick={() => removeAt(index)} aria-label="Remove photo" className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-black/50"><X className="h-2.5 w-2.5" /></button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-end justify-between gap-5">
          <button type="button" onClick={() => inputRef.current?.click()} className="flex w-24 flex-col items-center gap-2 text-xs font-semibold text-primary-foreground/70">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-foreground/10"><ImageIcon className="h-5 w-5" /></span>Gallery
          </button>
          <button type="button" onClick={capture} aria-label="Capture inspection image" disabled={!cameraActive} className="flex h-20 w-20 items-center justify-center rounded-full border-[6px] border-primary-foreground/20 bg-primary-foreground text-primary transition-transform active:scale-95 disabled:opacity-40">
            <div className="flex h-14 w-14 items-center justify-center rounded-full border-2 border-primary"><Camera className="h-6 w-6" /></div>
          </button>
          <button
            type="button"
            onClick={() => captured.length && onCaptured(captured)}
            disabled={!captured.length}
            className="flex w-24 flex-col items-center gap-2 text-xs font-semibold text-primary-foreground/70 disabled:opacity-40"
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-foreground/10"><ArrowRight className="h-5 w-5" /></span>
            Continue{captured.length ? ` (${captured.length})` : ""}
          </button>
        </div>
        <input ref={inputRef} type="file" accept="image/*" onChange={handleFile} className="hidden" />
      </div>
    </div>
  );
}

const CATEGORY_OPTIONS = ["food", "beverage", "personal_care", "household", "other"];
const UNIT_OPTIONS = ["g", "kg", "ml", "l", "number"];

export function ScanDetailsView({
  images,
  onSubmit,
  onBack,
}: {
  images: string[];
  onSubmit: (details: ScanDetails) => void;
  onBack: () => void;
}) {
  const [productId, setProductId] = useState("");
  const [saleType, setSaleType] = useState<ScanDetails["saleType"]>("retail");
  const [category, setCategory] = useState(CATEGORY_OPTIONS[0]);
  const [qtyValue, setQtyValue] = useState("");
  const [qtyUnit, setQtyUnit] = useState(UNIT_OPTIONS[0]);
  const [mrp, setMrp] = useState("");

  const [extracting, setExtracting] = useState(true);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<ExtractPreviewResponse | null>(null);
  const [showDetectedDeclarations, setShowDetectedDeclarations] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function runPreview() {
      if (!images.length) {
        setExtracting(false);
        return;
      }
      try {
        setExtracting(true);
        setExtractError(null);
        const blobs = images.map(dataUrlToBlob);
        const res = await extractPreview(blobs);
        if (cancelled) return;
        setPreviewData(res);

        if (res.suggested_details.product_id) {
          setProductId(res.suggested_details.product_id);
        }
        if (res.suggested_details.sale_type) {
          setSaleType(res.suggested_details.sale_type);
        }
        if (res.suggested_details.category && CATEGORY_OPTIONS.includes(res.suggested_details.category)) {
          setCategory(res.suggested_details.category);
        }
        if (res.suggested_details.net_quantity_value != null) {
          setQtyValue(String(res.suggested_details.net_quantity_value));
        }
        if (res.suggested_details.net_quantity_unit && UNIT_OPTIONS.includes(res.suggested_details.net_quantity_unit.toLowerCase())) {
          setQtyUnit(res.suggested_details.net_quantity_unit.toLowerCase());
        }
        if (res.suggested_details.mrp != null) {
          setMrp(String(res.suggested_details.mrp));
        }
      } catch (err) {
        if (cancelled) return;
        setExtractError(err instanceof Error ? err.message : "OCR preview unavailable");
      } finally {
        if (!cancelled) setExtracting(false);
      }
    }
    runPreview();
    return () => {
      cancelled = true;
    };
  }, [images]);

  const effectiveProductId = productId.trim() || previewData?.suggested_details?.product_id || "";
  const effectiveQty = Number(qtyValue) > 0 ? Number(qtyValue) : (previewData?.suggested_details?.net_quantity_value ?? undefined);
  const effectiveQtyUnit = qtyUnit || previewData?.suggested_details?.net_quantity_unit || undefined;
  const valid = effectiveProductId.length > 0;

  const detectedDeclarationsList = useMemo(() => {
    if (!previewData?.field_extractions) return [];
    return Object.entries(previewData.field_extractions)
      .filter(([, data]) => data && data.detected && data.value)
      .map(([field, data]) => ({
        field: field.replace(/_/g, " "),
        value: data.value,
        confidence: Math.round((data.confidence ?? 0) * 100),
        source: data.source_image,
      }));
  }, [previewData]);

  return (
    <>
      <AppHeader title="Confirm details" />
      <main className="mx-auto max-w-2xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />Retake photos
        </button>

        <section className="flex gap-3 overflow-x-auto rounded-2xl border border-border/70 bg-card p-4 hide-scrollbar">
          {images.map((img, i) => (
            <div key={i} className="relative h-24 w-20 shrink-0 overflow-hidden rounded-xl border border-border">
              <img src={img} alt={`Capture ${i + 1}`} className="h-full w-full object-cover" />
              <span className="absolute left-1 top-1 rounded bg-primary/90 px-1.5 py-0.5 text-[9px] font-bold text-primary-foreground">
                {i === 0 ? "Primary" : `#${i + 1}`}
              </span>
            </div>
          ))}
        </section>

        {extracting ? (
          <div className="flex items-center gap-3 rounded-2xl border border-brand/25 bg-brand/5 p-4 text-xs text-brand">
            <LoaderCircle className="h-5 w-5 animate-spin shrink-0 text-brand" />
            <div>
              <p className="font-semibold text-sm">Reading mandatory declarations from label...</p>
              <p className="text-muted-foreground mt-0.5">Auto-extracting SKU, net quantity, MRP, and product category</p>
            </div>
          </div>
        ) : previewData ? (
          <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-4 text-xs text-emerald-800 dark:text-emerald-300">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Sparkles className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <div>
                  <p className="font-semibold text-sm">Details auto-filled from package photo</p>
                  <p className="text-muted-foreground mt-0.5">
                    {previewData.total_lines} text lines analyzed • Review and confirm below
                  </p>
                </div>
              </div>
              {detectedDeclarationsList.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowDetectedDeclarations((v) => !v)}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
                >
                  {showDetectedDeclarations ? "Hide declarations" : `${detectedDeclarationsList.length} detected`}
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showDetectedDeclarations ? "rotate-180" : ""}`} />
                </button>
              )}
            </div>

            {showDetectedDeclarations && (
              <div className="mt-4 pt-3 border-t border-emerald-500/15 space-y-2">
                <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Detected Declarations</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {detectedDeclarationsList.map((item) => (
                    <div key={item.field} className="rounded-xl border border-border/70 bg-card p-2.5 text-foreground">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground capitalize truncate">{item.field}</span>
                        <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">{item.confidence}%</span>
                      </div>
                      <p className="text-xs font-medium mt-1 truncate" title={item.value ?? ""}>{item.value}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : extractError ? (
          <div className="flex items-center gap-2.5 rounded-2xl border border-border/70 bg-muted/40 p-3.5 text-xs text-muted-foreground">
            <Info className="h-4 w-4 shrink-0" />
            <span>AI OCR preview unavailable ({extractError}). Please confirm details manually.</span>
          </div>
        ) : null}

        <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
          <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Before we run the checks</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-.035em]">Confirm details</h2>
          <p className="mt-1 text-sm text-muted-foreground">Same fields as the dashboard Scan tab: product ID, sale type, category, net quantity, MRP.</p>

          <div className="mt-6 space-y-5">
            <div>
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-muted-foreground">Product ID / SKU</label>
                {previewData?.suggested_details?.product_id_source === "unidentified-placeholder" || previewData?.suggested_details?.needs_manual_entry ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                    <AlertTriangle className="h-3 w-3" /> Placeholder SKU (no barcode detected)
                  </span>
                ) : previewData?.suggested_details?.product_id_source?.startsWith("barcode") ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <BadgeCheck className="h-3 w-3" /> Decoded Barcode ({previewData.suggested_details.barcode_info?.primary_symbology || "EAN-13"})
                  </span>
                ) : previewData?.suggested_details?.product_id ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <Sparkles className="h-3 w-3" /> Auto-suggested
                  </span>
                ) : null}
              </div>
              <input
                value={productId}
                onChange={(e) => setProductId(e.target.value)}
                placeholder="e.g. TRAYA-VITAMIN-30CAP"
                className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Sale type</label>
                <select
                  value={saleType}
                  onChange={(e) => setSaleType(e.target.value as ScanDetails["saleType"])}
                  className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                >
                  <option value="retail">Retail</option>
                  <option value="wholesale">Wholesale</option>
                  <option value="industrial">Industrial</option>
                  <option value="institutional">Institutional</option>
                </select>
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-muted-foreground">Category</label>
                  {previewData?.suggested_details?.category && (
                    <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400">Inferred</span>
                  )}
                </div>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                >
                  {CATEGORY_OPTIONS.map((c) => (
                    <option key={c} value={c}>
                      {c.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-[1fr_auto] gap-3">
              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-muted-foreground">Net quantity</label>
                  {previewData?.suggested_details?.net_quantity_value != null ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                      <Sparkles className="h-3 w-3" /> Auto-detected
                    </span>
                  ) : (
                    <span className="text-[11px] text-amber-600 dark:text-amber-400">Not reliably observed yet</span>
                  )}
                </div>
                <input
                  value={qtyValue}
                  onChange={(e) => setQtyValue(e.target.value)}
                  type="number"
                  placeholder="30"
                  className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Unit</label>
                <select
                  value={qtyUnit}
                  onChange={(e) => setQtyUnit(e.target.value)}
                  className="mt-1.5 h-11 rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                >
                  {UNIT_OPTIONS.map((u) => (
                    <option key={u} value={u}>
                      {u}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-muted-foreground">MRP (₹) — optional</label>
                {previewData?.suggested_details?.mrp != null && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <Sparkles className="h-3 w-3" /> Auto-detected
                  </span>
                )}
              </div>
              <input
                value={mrp}
                onChange={(e) => setMrp(e.target.value)}
                type="number"
                placeholder="470"
                className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
              />
            </div>

            {previewData?.suggested_details?.pdp_area_cm2 != null && (
              <div className="flex items-center justify-between rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3.5 py-2.5 text-xs">
                <span className="font-medium text-muted-foreground">Principal Display Panel (PDP) Area</span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                  {previewData.suggested_details.pdp_area_cm2} cm²
                </span>
              </div>
            )}
          </div>
        </section>

        <Button
          className="w-full"
          disabled={!valid}
          onClick={() =>
            onSubmit({
              productId: effectiveProductId,
              saleType,
              productCategory: category,
              ...(effectiveQty !== undefined ? { netQuantityValue: effectiveQty } : {}),
              ...(effectiveQtyUnit ? { netQuantityUnit: effectiveQtyUnit } : {}),
              mrp: mrp ? Number(mrp) : (previewData?.suggested_details?.mrp ?? undefined),
              pdpAreaCm2: previewData?.suggested_details?.pdp_area_cm2 ?? undefined,
            })
          }
        >
          Run inspection<ArrowRight className="h-4 w-4" />
        </Button>
      </main>
    </>
  );
}

export function ProcessingRunner({
  onRun,
  onDone,
  onError,
}: {
  onRun: () => Promise<Inspection>;
  onDone: (inspection: Inspection) => void;
  onError: (message: string) => void;
}) {
  const steps = ["Image received", "Detecting package label", "Extracting declarations", "Checking Legal Metrology rules", "Preparing compliance report"];
  const [active, setActive] = useState(0);
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    const interval = window.setInterval(() => {
      setActive((value) => Math.min(value + 1, steps.length - 1));
    }, 650);

    const minDisplay = new Promise((resolve) => window.setTimeout(resolve, 1400));

    Promise.all([onRun(), minDisplay])
      .then(([inspection]) => {
        window.clearInterval(interval);
        setActive(steps.length);
        window.setTimeout(() => onDone(inspection), 350);
      })
      .catch((err: unknown) => {
        window.clearInterval(interval);
        const message = err instanceof ApiError ? err.message : "Something went wrong while analyzing this package.";
        onError(message);
      });

    return () => window.clearInterval(interval);
    // Intentionally once-per-mount: the parent queues the run via a ref so
    // identity changes of onRun must not re-fire the pipeline.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-brand-soft text-brand"><LoaderCircle className="breathe h-9 w-9" /></div>
        <p className="mt-8 text-xs font-bold uppercase tracking-[.2em] text-brand">Inspection pipeline</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-.05em]">Analyzing package</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">Extracting evidence and checking each declaration against the Legal Metrology rule set.</p>
        <div className="mt-10 space-y-3 text-left">
          {steps.map((step, index) => (
            <div key={step} className={`flex items-center gap-3 rounded-xl border px-4 py-3 transition-all ${index < active ? "border-success/20 bg-success-soft" : index === active ? "border-brand/30 bg-brand-soft" : "border-border bg-card"}`}>
              {index < active ? (
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-success text-white"><Check className="h-3.5 w-3.5" /></span>
              ) : index === active ? (
                <LoaderCircle className="h-6 w-6 animate-spin text-brand" />
              ) : (
                <span className="h-6 w-6 rounded-full border border-border" />
              )}
              <span className={`text-sm font-semibold ${index <= active ? "text-foreground" : "text-muted-foreground"}`}>{step}</span>
              {index === active && <span className="ml-auto text-[10px] font-bold uppercase tracking-widest text-brand">Working</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ProcessingErrorView({ message, onRetry, onCancel }: { message: string; onRetry: () => void; onCancel: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-danger-soft text-destructive"><WifiOff className="h-9 w-9" /></div>
        <h1 className="mt-8 text-2xl font-semibold tracking-[-.04em]">Couldn't complete the check</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{message}</p>
        <div className="mt-8 flex justify-center gap-3">
          <Button variant="secondary" onClick={onCancel}>Cancel</Button>
          <Button onClick={onRetry}><RefreshCcw className="h-4 w-4" />Try again</Button>
        </div>
      </div>
    </div>
  );
}
