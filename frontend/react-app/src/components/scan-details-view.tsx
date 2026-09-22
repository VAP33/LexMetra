import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Check,
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Info,
  LoaderCircle,
  PackageCheck,
  Sparkles,
} from "lucide-react";
import { type Language } from "@/lib/i18n";
import { type ScanDetails } from "@/lib/types";
import { extractPreview, resolveImageUrl, type ExtractPreviewResponse } from "@/lib/api-client";
import { dataUrlToBlob } from "@/lib/data-url";
import { type View, Button } from "./ui-primitives";
import { Header as AppHeader } from "./app-header";
import { SafeImage } from "./safe-image";

export const CATEGORY_OPTIONS = ["food", "beverage", "personal_care", "household", "other"];
export const UNIT_OPTIONS = ["g", "kg", "ml", "l", "number"];


export function ScanDetailsView({
  images,
  onSubmit,
  onBack,
  lang = "en",
  onLanguageChange,
}: {
  images: string[];
  onSubmit: (details: ScanDetails) => void;
  onBack: () => void;
  lang?: Language;
  onLanguageChange?: (l: Language) => void;
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
  const lastExtractedKeyRef = useRef<string>("");

  useEffect(() => {
    let cancelled = false;
    async function runPreview() {
      if (!images.length) {
        setExtracting(false);
        return;
      }
      // Deduplicate by face-set signature to prevent duplicate requests from React re-renders
      const requestKey = images.map((img, i) => `f${i}:${img.length}:${img.slice(0, 50)}`).join("|");
      if (lastExtractedKeyRef.current === requestKey && previewData) {
        setExtracting(false);
        return;
      }
      lastExtractedKeyRef.current = requestKey;

      try {
        setExtracting(true);
        setExtractError(null);
        const blobs = await Promise.all(
          images.map(async (img) => {
            if (img.startsWith("data:") || img.startsWith("blob:")) {
              return dataUrlToBlob(img);
            }
            const fullUrl = resolveImageUrl(img) || img;
            const fetched = await fetch(fullUrl);
            return await fetched.blob();
          })
        );
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
  const valid = true;

  const detectedDeclarationsList = useMemo(() => {
    if (!previewData?.field_extractions) return [];
    return Object.entries(previewData.field_extractions)
      .filter(([_, data]) => data && data.detected && data.value)
      .map(([field, data]) => ({
        field: field.replace(/_/g, " "),
        value: data.value,
        confidence: Math.round((data.confidence ?? 0) * 100),
        source: data.source_image,
      }));
  }, [previewData]);

  return (
    <>
      <AppHeader
        title={lang === "hi" ? "विवरण की पुष्टि करें" : lang === "mr" ? "तपशील पुष्टी करा" : "Confirm details"}
        lang={lang}
        onLanguageChange={onLanguageChange}
      />
      <main className="mx-auto max-w-2xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />Retake photos
        </button>

        <section className="flex gap-3 overflow-x-auto rounded-2xl border border-border/70 bg-card p-4 hide-scrollbar">
          {images.map((img, i) => (
            <div key={i} className="relative h-24 w-20 shrink-0 overflow-hidden rounded-xl border border-border">
              <SafeImage src={img} alt={`Face ${i + 1}`} className="h-full w-full object-cover" />
              <span className="absolute left-1 top-1 rounded bg-primary/90 px-1.5 py-0.5 text-[9px] font-bold text-primary-foreground">
                Face {i + 1}
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
                  {detectedDeclarationsList.map((item: any) => (
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
          <p className="mt-1 text-sm text-muted-foreground">Pre-filled from package perception. Adjust if needed or proceed directly.</p>

          <div className="mt-6 space-y-5">
            <div>
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-muted-foreground">Product Name</label>
                {previewData?.field_extractions?.common_name?.value ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <BadgeCheck className="h-3 w-3" /> Detected from label
                  </span>
                ) : null}
              </div>
              <div className="mt-1.5 flex h-11 w-full items-center rounded-xl border border-border/80 bg-muted/30 px-3 text-sm font-medium text-foreground">
                {previewData?.field_extractions?.common_name?.value || "Not detected"}
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-muted-foreground">Product ID / SKU</label>
                {previewData?.suggested_details?.product_id_source === "unidentified-placeholder" || previewData?.suggested_details?.needs_manual_entry || !previewData?.suggested_details?.product_id ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                    <AlertTriangle className="h-3 w-3" /> Not detected on label
                  </span>
                ) : previewData?.suggested_details?.product_id_source?.startsWith("barcode") ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <BadgeCheck className="h-3 w-3" /> Decoded Barcode ({previewData.suggested_details.barcode_info?.primary_symbology || "EAN-13"})
                  </span>
                ) : previewData?.suggested_details?.product_id ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <Sparkles className="h-3 w-3" /> Detected on label
                  </span>
                ) : null}
              </div>
              <input
                value={productId}
                onChange={(e) => setProductId(e.target.value)}
                placeholder="Not detected (optional/manual entry)"
                className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
              />
              {(!productId.trim() && (!previewData?.suggested_details?.product_id || previewData?.suggested_details?.needs_manual_entry)) && (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  No printed Product ID / Barcode was detected on the package label.
                </p>
              )}
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
                  {CATEGORY_OPTIONS.map((c: string) => (
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
                  {UNIT_OPTIONS.map((u: string) => (
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
                <span className="font-medium text-muted-foreground flex items-center gap-1.5">
                  <span className="text-sm">📐</span> Calculated Principal Display Panel (PDP) Area
                </span>
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
          Run compliance check<ArrowRight className="h-4 w-4" />
        </Button>
      </main>
    </>
  );
}


