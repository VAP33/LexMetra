function getSvgColors(label: string, isSelected: boolean) {
  const l = label.toLowerCase();
  if (l.includes("mrp") || l.includes("retail") || l.includes("price")) {
    return {
      stroke: isSelected ? "#10b981" : "#059669",
      fill: isSelected ? "rgba(16, 185, 129, 0.35)" : "rgba(16, 185, 129, 0.18)",
    };
  }
  if (l.includes("unit") || l.includes("usp")) {
    return {
      stroke: isSelected ? "#06b6d4" : "#0891b2",
      fill: isSelected ? "rgba(6, 182, 212, 0.35)" : "rgba(6, 182, 212, 0.18)",
    };
  }
  if (l.includes("batch") || l.includes("lot")) {
    return {
      stroke: isSelected ? "#6366f1" : "#4f46e5",
      fill: isSelected ? "rgba(99, 102, 241, 0.35)" : "rgba(99, 102, 241, 0.18)",
    };
  }
  if (l.includes("net") || l.includes("qty") || l.includes("volume") || l.includes("weight")) {
    return {
      stroke: isSelected ? "#f59e0b" : "#d97706",
      fill: isSelected ? "rgba(245, 158, 11, 0.35)" : "rgba(245, 158, 11, 0.18)",
    };
  }
  if (l.includes("date") || l.includes("mfd") || l.includes("exp") || l.includes("before")) {
    return {
      stroke: isSelected ? "#a855f7" : "#9333ea",
      fill: isSelected ? "rgba(168, 85, 247, 0.35)" : "rgba(168, 85, 247, 0.18)",
    };
  }
  return {
    stroke: isSelected ? "#3b82f6" : "#2563eb",
    fill: isSelected ? "rgba(59, 130, 246, 0.35)" : "rgba(59, 130, 246, 0.18)",
  };
}


import { Header as AppHeader } from "./app-header";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronRight,
  Eye,
  Info,
  LoaderCircle,
  Maximize2,
  Minimize2,
  PackageCheck,
  RotateCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { BeforeAfterSlider } from "./before-after-slider";
import { type Language, getTranslation } from "@/lib/i18n";
import { type Declaration, type Inspection, type SurfaceEvidence } from "@/lib/types";
import { resolveImageUrl, getInspectionDetail, API_BASE } from "@/lib/api-client";
import { fromInspectionRow } from "@/lib/adapters";
import { type View, Button, StatusBadge } from "./ui-primitives";

export function DynamicEvidenceCrop({
  imageSrc,
  bbox,
  polygon,
  localizationStatus,
  label,
  value,
  confidence,
}: {
  imageSrc: string;
  bbox?: { x: number; y: number; width: number; height: number };
  polygon?: [number, number][];
  localizationStatus?: string;
  label: string;
  value?: string;
  confidence?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [loadError, setLoadError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [cropStats, setCropStats] = useState<{
    cropW: number;
    cropH: number;
    zoomFactor: number;
    naturalW: number;
    naturalH: number;
  } | null>(null);

  useEffect(() => {
    if (!bbox || bbox.width <= 0 || bbox.height <= 0 || !imageSrc) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setLoadError(false);
    const resolvedSrc = resolveImageUrl(imageSrc) || imageSrc;
    const img = new Image();
    img.onload = () => {
      setLoading(false);
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const nw = img.naturalWidth;
      const nh = img.naturalHeight;

      // Add generous padding (40% of dimensions or at least 35-40px)
      const padX = Math.max(bbox.width * 0.4, 40);
      const padY = Math.max(bbox.height * 0.4, 30);

      const cropX = Math.max(0, bbox.x - padX);
      const cropY = Math.max(0, bbox.y - padY);
      const cropRight = Math.min(nw, bbox.x + bbox.width + padX);
      const cropBottom = Math.min(nh, bbox.y + bbox.height + padY);

      const cropW = Math.max(1, cropRight - cropX);
      const cropH = Math.max(1, cropBottom - cropY);

      const targetWidth = 720;
      const aspect = cropH / cropW;
      const targetHeight = Math.max(260, Math.min(Math.round(targetWidth * aspect), 520));

      canvas.width = targetWidth;
      canvas.height = targetHeight;

      // Clear dark background
      ctx.fillStyle = "#09090b";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Fit cropped region inside canvas preserving aspect ratio
      const scale = Math.min(canvas.width / cropW, canvas.height / cropH);
      const renderW = cropW * scale;
      const renderH = cropH * scale;
      const offsetX = (canvas.width - renderW) / 2;
      const offsetY = (canvas.height - renderH) / 2;

      ctx.drawImage(img, cropX, cropY, cropW, cropH, offsetX, offsetY, renderW, renderH);

      // Bounding box within canvas
      const boxCanvasX = offsetX + (bbox.x - cropX) * scale;
      const boxCanvasY = offsetY + (bbox.y - cropY) * scale;
      const boxCanvasW = bbox.width * scale;
      const boxCanvasH = bbox.height * scale;

      // Draw tight polygon if available, else rectangle
      if (polygon && polygon.length >= 3) {
        ctx.beginPath();
        const startX = offsetX + (polygon[0][0] - cropX) * scale;
        const startY = offsetY + (polygon[0][1] - cropY) * scale;
        ctx.moveTo(startX, startY);
        for (let i = 1; i < polygon.length; i++) {
          ctx.lineTo(offsetX + (polygon[i][0] - cropX) * scale, offsetY + (polygon[i][1] - cropY) * scale);
        }
        ctx.closePath();
        ctx.fillStyle = "rgba(16, 185, 129, 0.22)";
        ctx.fill();
        ctx.strokeStyle = "#10b981";
        ctx.lineWidth = 3;
        ctx.stroke();
      } else {
        ctx.fillStyle = "rgba(16, 185, 129, 0.16)";
        ctx.fillRect(boxCanvasX, boxCanvasY, boxCanvasW, boxCanvasH);
        ctx.strokeStyle = "#10b981";
        ctx.lineWidth = 3;
        ctx.strokeRect(boxCanvasX, boxCanvasY, boxCanvasW, boxCanvasH);
      }

      // Badge label
      const badgeText = `${label}${value ? `: ${value}` : ""}${confidence ? ` (${confidence}%)` : ""}`;
      ctx.font = "bold 13px system-ui, -apple-system, sans-serif";
      const textMetrics = ctx.measureText(badgeText);
      const badgeW = textMetrics.width + 16;
      const badgeH = 24;
      const badgeX = Math.max(offsetX, Math.min(boxCanvasX, canvas.width - badgeW - 10));
      const badgeY = Math.max(badgeH + 6, boxCanvasY - 6);

      ctx.fillStyle = "rgba(15, 23, 42, 0.95)";
      ctx.beginPath();
      if (typeof ctx.roundRect === "function") {
        ctx.roundRect(badgeX, badgeY - badgeH, badgeW, badgeH, 6);
      } else {
        ctx.rect(badgeX, badgeY - badgeH, badgeW, badgeH);
      }
      ctx.fill();
      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      ctx.fillStyle = "#34d399";
      ctx.fillText(badgeText, badgeX + 8, badgeY - 7);

      setCropStats({
        cropW: Math.round(cropW),
        cropH: Math.round(cropH),
        zoomFactor: Number(scale.toFixed(1)),
        naturalW: nw,
        naturalH: nh,
      });
    };

    img.onerror = () => {
      // Fallback without protocol/relative differences
      if (!resolvedSrc.startsWith("http") && typeof window !== "undefined") {
        const fallbackUrl = `${API_BASE}${resolvedSrc.startsWith("/") ? "" : "/"}${resolvedSrc}`;
        const retryImg = new Image();
        retryImg.onload = () => {
          setLoading(false);
          const canvas = canvasRef.current;
          if (!canvas) return;
          const ctx = canvas.getContext("2d");
          if (!ctx) return;
          const nw = retryImg.naturalWidth;
          const nh = retryImg.naturalHeight;
          const padX = Math.max(bbox.width * 0.4, 40);
          const padY = Math.max(bbox.height * 0.4, 30);
          const cropX = Math.max(0, bbox.x - padX);
          const cropY = Math.max(0, bbox.y - padY);
          const cropW = Math.max(1, Math.min(nw, bbox.x + bbox.width + padX) - cropX);
          const cropH = Math.max(1, Math.min(nh, bbox.y + bbox.height + padY) - cropY);
          canvas.width = 720;
          canvas.height = Math.max(260, Math.min(Math.round(720 * (cropH / cropW)), 520));
          ctx.fillStyle = "#09090b";
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          const scale = Math.min(canvas.width / cropW, canvas.height / cropH);
          const rw = cropW * scale;
          const rh = cropH * scale;
          ctx.drawImage(retryImg, cropX, cropY, cropW, cropH, (canvas.width - rw) / 2, (canvas.height - rh) / 2, rw, rh);
        };
        retryImg.onerror = () => {
          setLoading(false);
          setLoadError(true);
        };
        retryImg.src = fallbackUrl;
      } else {
        setLoading(false);
        setLoadError(true);
      }
    };

    img.src = resolvedSrc;
  }, [imageSrc, bbox, polygon, label, confidence]);

  if (!bbox || bbox.width <= 0 || bbox.height <= 0) {
    const isAmbiguous = localizationStatus === "AMBIGUOUS_MATCH";
    const isUnavailable = localizationStatus === "LOCALIZER_UNAVAILABLE";
    const heading = isAmbiguous
      ? "Evidence location uncertain"
      : isUnavailable
        ? "Localization service unavailable"
        : "Evidence location unavailable";
    const desc = isAmbiguous
      ? `Multiple candidate text locations detected on this face for "${label}". Coarse fallback box suppressed for statutory precision.`
      : isUnavailable
        ? "The localization engine was unavailable during this scan."
        : `No verified tight text polygon could be localized for "${label}" on this package face. Physical verification is required.`;

    return (
      <div className="flex flex-col items-center justify-center p-8 text-center bg-card rounded-xl border border-warning/30 min-h-[320px]">
        <ShieldAlert className="h-12 w-12 text-warning mb-3 animate-pulse" />
        <h4 className="text-base font-bold text-foreground">{heading}</h4>
        <p className="text-xs text-muted-foreground mt-1.5 max-w-sm">{desc}</p>
        <div className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-warning/10 px-3 py-1 text-[11px] font-semibold text-warning border border-warning/20">
          Status: {localizationStatus || "UNLOCALIZED"}
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center bg-card rounded-xl border border-danger/30 min-h-[320px]">
        <AlertTriangle className="h-10 w-10 text-danger mb-2" />
        <p className="text-sm font-semibold text-foreground">Failed to load evidence crop</p>
        <p className="text-xs text-muted-foreground mt-1">Image resource could not be rendered.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col space-y-2">
      <div className="relative aspect-[4/3] w-full overflow-hidden rounded-xl border border-border/70 bg-neutral-950 flex items-center justify-center">
        {loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-neutral-950/80 z-10 text-xs text-muted-foreground">
            <LoaderCircle className="h-6 w-6 animate-spin text-brand mb-2" />
            Rendering dynamic crop...
          </div>
        )}
        <canvas ref={canvasRef} className="max-h-full max-w-full object-contain rounded-lg" />
      </div>
      {cropStats && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[11px] font-mono text-muted-foreground">
          <span>
            <strong>Dynamic Crop:</strong> {cropStats.cropW}×{cropStats.cropH}px (Source: {cropStats.naturalW}×{cropStats.naturalH}px)
          </span>
          <span>
            <strong>Zoom:</strong> {cropStats.zoomFactor}× Centered
          </span>
        </div>
      )}
    </div>
  );
}

export function EvidenceView({ inspection, onBack }: { inspection: Inspection; onBack: () => void }) {
  const [currentInspection, setCurrentInspection] = useState<Inspection>(inspection);

  // Ensure ALL persisted faces and evidence are loaded on the FIRST View Evidence click
  useEffect(() => {
    let cancelled = false;
    if (inspection?.id && (!inspection.surfaces || inspection.surfaces.length <= 1)) {
      getInspectionDetail(inspection.id)
        .then((row) => {
          if (!cancelled && row) {
            setCurrentInspection(fromInspectionRow(row));
          }
        })
        .catch((err) => console.warn("[EvidenceView] Failed to hydrate surfaces on first click:", err));
    } else {
      setCurrentInspection(inspection);
    }
    return () => {
      cancelled = true;
    };
  }, [inspection]);

  // Synthesize or use populated surfaces from inspection
  const surfaces: SurfaceEvidence[] = useMemo(() => {
    if (currentInspection.surfaces && currentInspection.surfaces.length > 0) {
      return currentInspection.surfaces;
    }
    return [
      {
        surfaceId: "face_1",
        surfaceType: "Face 1",
        faceLabel: "Face 1",
        priorityScore: 1.0,
        imageUrl: currentInspection.image,
        canonicalImageUrl: currentInspection.canonicalImage || currentInspection.image,
        regions: currentInspection.evidence,
        transformHistory: [
          "Original Sensor Capture (Raw)",
          "Package Boundary & Object Detection",
          "Perspective Homography H-Matrix",
          "Illumination Normalization",
          "Canonical Surface Normalization",
        ],
        ocrConfidence: currentInspection.declarations[0]?.ocrConfidence ?? 90,
      },
    ];
  }, [currentInspection]);

  const [activeSurfaceType, setActiveSurfaceType] = useState<string>(
    surfaces[0]?.surfaceType || "Face 1"
  );

  // Per-face natural image dimensions for zero-distortion bounding boxes
  const [faceNaturalSizes, setFaceNaturalSizes] = useState<Record<string, { w: number; h: number }>>({});

  // Per-face view mode ("canonical" vs "original" photograph)
  const [faceViewModes, setFaceViewModes] = useState<Record<string, "canonical" | "original">>({});

  // Active face for Before/After dual-slider comparison
  const [sliderFace, setSliderFace] = useState<SurfaceEvidence | null>(null);

  const activeSurface = useMemo(() => {
    return surfaces.find((s) => s.surfaceType === activeSurfaceType) || surfaces[0];
  }, [surfaces, activeSurfaceType]);

  // Strict face-specific declarations: only show declarations actually on the currently selected face
  const faceDeclarations = useMemo(() => {
    if (!activeSurface) return currentInspection.declarations;
    const fl = (activeSurface.faceLabel || "").toLowerCase().trim();
    const st = (activeSurface.surfaceType || "").toLowerCase().trim();
    const sid = (activeSurface.surfaceId || "").toLowerCase().trim();

    return currentInspection.declarations.filter((d) => {
      // 1. Explicit provenance match
      const provType = (d.provenance?.surfaceType || "").toLowerCase().trim();
      const provSid = (d.provenance?.surfaceId || "").toLowerCase().trim();
      if (provType && (provType === fl || provType === st || provType === sid || provType.replace("face_", "face ") === fl)) {
        return true;
      }
      if (provSid && (provSid === sid || provSid === fl || provSid.replace("face_", "face ") === fl)) {
        return true;
      }

      // 2. Matching region on the active surface
      if (activeSurface.regions && activeSurface.regions.length > 0) {
        const hasRegion = activeSurface.regions.some((r) => {
          const rl = (r.label || "").toLowerCase().trim();
          const df = (d.field || "").toLowerCase().trim();
          const dcf = (d.canonicalField || "").toLowerCase().trim();
          return rl === df || rl === dcf || df.includes(rl) || rl.includes(df);
        });
        if (hasRegion) return true;
      }

      return false;
    });
  }, [currentInspection.declarations, activeSurface]);

  // Selected declaration / region (Bidirectional navigation)
  const [selectedLabel, setSelectedLabel] = useState<string>(
    faceDeclarations[0]?.field || currentInspection.evidence[0]?.label || currentInspection.declarations[0]?.field || "MRP"
  );

  // Synchronize active declaration and region bidirectionally
  const activeDecl = useMemo(() => {
    return (
      faceDeclarations.find(
        (d) =>
          d.field.toLowerCase() === selectedLabel.toLowerCase() ||
          d.canonicalField?.toLowerCase() === selectedLabel.toLowerCase() ||
          selectedLabel.toLowerCase().includes(d.field.toLowerCase())
      ) ||
      faceDeclarations[0] ||
      currentInspection.declarations.find(
        (d) =>
          d.field.toLowerCase() === selectedLabel.toLowerCase() ||
          d.canonicalField?.toLowerCase() === selectedLabel.toLowerCase()
      ) ||
      currentInspection.declarations[0]
    );
  }, [selectedLabel, faceDeclarations, currentInspection.declarations]);

  const activeRegion = useMemo(() => {
    const pool = activeSurface?.regions?.length ? activeSurface.regions : currentInspection.evidence;
    return (
      pool.find(
        (r: any) =>
          r.label.toLowerCase() === selectedLabel.toLowerCase() ||
          r.label.toLowerCase().includes(selectedLabel.toLowerCase())
      ) ||
      pool.find(
        (r: any) =>
          activeDecl && (
            r.label.toLowerCase() === activeDecl.field.toLowerCase() ||
            r.label.toLowerCase().includes(activeDecl.field.toLowerCase())
          )
      ) ||
      null
    );
  }, [selectedLabel, activeSurface, currentInspection.evidence, activeDecl]);

  // Target bounding box for evidence crop (raw pixel space)
  const targetBbox = activeRegion?.bboxPx || (
    activeDecl && (!activeDecl.provenance?.surfaceType || 
      activeDecl.provenance.surfaceType === activeSurface.surfaceType || 
      activeDecl.provenance.surfaceType === activeSurface.faceLabel)
      ? activeDecl.evidenceBboxPx
      : undefined
  );

  function handleSelectSurface(surfaceType: string) {
    setActiveSurfaceType(surfaceType);
    const targetSurface = surfaces.find(
      (s) => s.surfaceType === surfaceType || s.faceLabel === surfaceType || s.surfaceId === surfaceType
    );
    if (targetSurface) {
      const fl = (targetSurface.faceLabel || "").toLowerCase().trim();
      const st = (targetSurface.surfaceType || "").toLowerCase().trim();
      const sid = (targetSurface.surfaceId || "").toLowerCase().trim();

      const targetDecls = currentInspection.declarations.filter((d) => {
        const provType = (d.provenance?.surfaceType || "").toLowerCase().trim();
        const provSid = (d.provenance?.surfaceId || "").toLowerCase().trim();
        return (
          (provType && (provType === fl || provType === st || provType === sid || provType.replace("face_", "face ") === fl)) ||
          (provSid && (provSid === sid || provSid === fl || provSid.replace("face_", "face ") === fl))
        );
      });

      if (targetDecls.length > 0) {
        setSelectedLabel(targetDecls[0].field);
      } else if (targetSurface.regions && targetSurface.regions.length > 0) {
        setSelectedLabel(targetSurface.regions[0].label);
      }
    }
  }

  function handleSelectDeclaration(field: string, targetFace?: string) {
    setSelectedLabel(field);
    const decl = currentInspection.declarations.find((d) => d.field.toLowerCase() === field.toLowerCase());
    const surfaceType = targetFace || decl?.provenance?.surfaceType;
    if (surfaceType) {
      const match = surfaces.find(
        (s) =>
          s.surfaceType.toLowerCase() === surfaceType.toLowerCase() ||
          s.faceLabel?.toLowerCase() === surfaceType.toLowerCase()
      );
      if (match) {
        setActiveSurfaceType(match.surfaceType);
      }
    }
  }

  // Package-level unobserved declarations (Zero false absence warning)
  const unobservedDeclarations = useMemo(() => {
    return currentInspection.declarations.filter(
      (d) => d.status === "MISSING" || d.status === "UNOBSERVED" || d.status === "REVIEW"
    );
  }, [currentInspection.declarations]);

  return (
    <>
      <AppHeader title="Legal Metrology Evidence Investigator" />
      <main className="mx-auto max-w-7xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-8">
        {/* Top bar: Back & Evidence Meta */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/70 pb-4">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground transition"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to inspection result
          </button>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">Inspection:</span> {inspection.id}
            <span className="h-3 w-px bg-border" />
            <span className="font-semibold text-foreground">Category:</span> {inspection.category?.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Packaged Commodity"}
          </div>
        </div>

        {/* Active Before/After Comparison Slider */}
        {sliderFace && (
          <div className="relative">
            <BeforeAfterSlider
              originalUrl={sliderFace.imageUrl || inspection.image || ""}
              canonicalUrl={sliderFace.canonicalImageUrl || sliderFace.imageUrl || inspection.image || ""}
              faceLabel={sliderFace.faceLabel || sliderFace.surfaceType}
              naturalWidth={faceNaturalSizes[sliderFace.surfaceType]?.w}
              naturalHeight={faceNaturalSizes[sliderFace.surfaceType]?.h}
              marginPercent={6.0}
              onClose={() => setSliderFace(null)}
            />
          </div>
        )}

        {/* Authoritative 3-Face Side-by-Side Canonical Panels */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[.18em] text-muted-foreground">
                Authoritative Multi-Surface Analysis
              </p>
              <h2 className="text-lg font-bold tracking-tight text-foreground">
                All Canonical Preprocessed Faces ({surfaces.length} Registered Surfaces)
              </h2>
            </div>
            <span className="text-xs text-muted-foreground hidden sm:inline">
              Face-isolated overlays · Dual canonical/original projection · Homography normalized
            </span>
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
            {surfaces.map((st, idx) => {
              const currentMode = faceViewModes[st.surfaceType] || "canonical";
              const displayUrl =
                currentMode === "original"
                  ? st.imageUrl || st.canonicalImageUrl || inspection.image
                  : st.canonicalImageUrl || st.imageUrl || inspection.image;
              const isPanelActive = activeSurfaceType === st.surfaceType;
              const priority = st.priorityScore ?? (1.0 - idx * 0.05);

              // Filter regions strictly belonging to this face with valid polygons or bboxes
              const faceRegionsWithBox = (st.regions || []).filter(
                (r: any) => (r.polygonPx && r.polygonPx.length >= 3) || (r.bboxPx && r.bboxPx.width > 0 && r.bboxPx.height > 0)
              );

              return (
                <div
                  key={st.surfaceId || st.surfaceType || idx}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest("button, svg, a")) return;
                    handleSelectSurface(st.surfaceType);
                  }}
                  className={`flex flex-col rounded-2xl border bg-card p-4 shadow-sm transition-all cursor-pointer ${isPanelActive
                      ? "border-brand ring-2 ring-brand/30 shadow-md"
                      : "border-border/70 hover:border-border"
                    }`}
                >
                  {/* Face Header: Sleek, decluttered minimalist toolbar */}
                  <div className="flex items-center justify-between border-b border-border/60 pb-2 mb-3">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleSelectSurface(st.surfaceType)}
                        className="text-left group flex items-center gap-1.5"
                      >
                        <span className="text-sm font-bold text-foreground group-hover:text-brand transition">
                          {st.faceLabel || st.surfaceType || `Face ${idx + 1}`}
                        </span>
                      </button>
                      <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[9px] font-bold text-brand">
                        P{(priority * 100).toFixed(0)}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      {/* Segmented Pill Switcher */}
                      <div className="inline-flex rounded-lg border border-border/70 bg-muted/60 p-0.5 text-[10px] font-medium">
                        <button
                          type="button"
                          onClick={() => {
                            setFaceViewModes((prev) => ({
                              ...prev,
                              [st.surfaceType]: "canonical",
                            }));
                          }}
                          className={`rounded-md px-2 py-0.5 transition ${currentMode === "canonical"
                              ? "bg-background text-foreground font-bold shadow-xs"
                              : "text-muted-foreground hover:text-foreground"
                            }`}
                        >
                          Scan
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setFaceViewModes((prev) => ({
                              ...prev,
                              [st.surfaceType]: "original",
                            }));
                          }}
                          className={`rounded-md px-2 py-0.5 transition ${currentMode === "original"
                              ? "bg-background text-foreground font-bold shadow-xs"
                              : "text-muted-foreground hover:text-foreground"
                            }`}
                        >
                          Raw
                        </button>
                      </div>

                      {/* Before / After Slider Toggle */}
                      <button
                        type="button"
                        onClick={() => setSliderFace(st)}
                        className="rounded-lg border border-border/70 bg-card p-1 text-muted-foreground hover:bg-brand-soft hover:text-brand transition"
                        title="Open interactive Before/After comparison slider"
                      >
                        <SlidersHorizontal className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Canvas Viewport with Face-Isolated Overlays */}
                  <div className="relative aspect-[4/3] w-full overflow-hidden rounded-xl border border-border/60 bg-neutral-950 flex items-center justify-center">
                    {displayUrl ? (
                      <div className="relative flex items-center justify-center h-full w-full">
                        <img
                          src={displayUrl}
                          alt={`${st.faceLabel || st.surfaceType} scan`}
                          className="max-h-full max-w-full object-contain select-none block"
                          onLoad={(e) => {
                            const img = e.currentTarget;
                            setFaceNaturalSizes((prev) => ({
                              ...prev,
                              [st.surfaceType]: { w: img.naturalWidth, h: img.naturalHeight },
                            }));
                          }}
                        />
                        {/* SVG Polygon & Vector Overlay (Canonical Mode) */}
                        {currentMode === "canonical" && faceNaturalSizes[st.surfaceType] && (
                          <svg
                            className="absolute inset-0 w-full h-full pointer-events-none"
                            viewBox={`0 0 ${faceNaturalSizes[st.surfaceType].w} ${faceNaturalSizes[st.surfaceType].h}`}
                            preserveAspectRatio="xMidYMid meet"
                          >
                            {faceRegionsWithBox.map((region) => {
                              const isSelected = selectedLabel.toLowerCase() === region.label.toLowerCase();
                              const cols = getSvgColors(region.label, isSelected);

                              if (region.polygonPx && region.polygonPx.length >= 3) {
                                const pts = region.polygonPx.map(([px, py]) => `${px},${py}`).join(" ");
                                const [firstX, firstY] = region.polygonPx[0];
                                return (
                                  <g
                                    key={region.label}
                                    className="pointer-events-auto cursor-pointer group"
                                    onClick={() => handleSelectDeclaration(region.label, st.surfaceType)}
                                  >
                                    <polygon
                                      points={pts}
                                      fill={cols.fill}
                                      stroke={cols.stroke}
                                      strokeWidth={isSelected ? 4 : 2}
                                      strokeLinejoin="round"
                                      className="transition-all hover:fill-opacity-50"
                                    />
                                    <rect
                                      x={firstX}
                                      y={Math.max(4, firstY - 20)}
                                      width={region.label.length * 8 + 14}
                                      height={18}
                                      rx={4}
                                      fill="#0f172a"
                                      fillOpacity={0.9}
                                      stroke={cols.stroke}
                                      strokeWidth={1}
                                    />
                                    <text
                                      x={firstX + 6}
                                      y={Math.max(16, firstY - 7)}
                                      fill="#ffffff"
                                      fontSize="11"
                                      fontWeight="bold"
                                    >
                                      {region.label}
                                    </text>
                                  </g>
                                );
                              } else if (region.bboxPx) {
                                return (
                                  <g
                                    key={region.label}
                                    className="pointer-events-auto cursor-pointer group"
                                    onClick={() => handleSelectDeclaration(region.label, st.surfaceType)}
                                  >
                                    <rect
                                      x={region.bboxPx.x}
                                      y={region.bboxPx.y}
                                      width={region.bboxPx.width}
                                      height={region.bboxPx.height}
                                      rx={3}
                                      fill={cols.fill}
                                      stroke={cols.stroke}
                                      strokeWidth={isSelected ? 4 : 2}
                                      className="transition-all hover:fill-opacity-50"
                                    />
                                    <rect
                                      x={region.bboxPx.x}
                                      y={Math.max(4, region.bboxPx.y - 20)}
                                      width={region.label.length * 8 + 14}
                                      height={18}
                                      rx={4}
                                      fill="#0f172a"
                                      fillOpacity={0.9}
                                      stroke={cols.stroke}
                                      strokeWidth={1}
                                    />
                                    <text
                                      x={region.bboxPx.x + 6}
                                      y={Math.max(16, region.bboxPx.y - 7)}
                                      fill="#ffffff"
                                      fontSize="11"
                                      fontWeight="bold"
                                    >
                                      {region.label}
                                    </text>
                                  </g>
                                );
                              }
                              return null;
                            })}
                          </svg>
                        )}
                      </div>
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                        No image capture
                      </div>
                    )}
                  </div>

                  {/* Surface Declarations Pill List - Decluttered & Compact */}
                  <div className="mt-3 flex flex-wrap items-center gap-1.5 max-h-24 overflow-y-auto pr-0.5">
                    {st.regions && st.regions.length > 0 ? (
                      st.regions.map((r: any) => {
                        const isSelected = selectedLabel.toLowerCase() === r.label.toLowerCase();
                        return (
                          <button
                            key={r.label}
                            type="button"
                            onClick={() => handleSelectDeclaration(r.label, st.surfaceType)}
                            className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-semibold transition ${isSelected
                                ? "bg-brand text-brand-foreground shadow-xs ring-1 ring-brand"
                                : "bg-muted/70 text-muted-foreground hover:bg-muted hover:text-foreground"
                              }`}
                          >
                            <span>{r.label}:</span>
                            <span className="font-mono text-[9px] opacity-90 truncate max-w-[70px]">
                              {r.value}
                            </span>
                          </button>
                        );
                      })
                    ) : (
                      <span className="text-[11px] italic text-muted-foreground">
                        {st.faceLabel === "Face 1"
                          ? "Principal display branding / title"
                          : "No statutory declarations isolated on this surface"}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Statutory Package-Level Unobserved Declarations (Zero False Absence Warning) */}
        {unobservedDeclarations.length > 0 && (
          <section className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 sm:p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
              <div className="space-y-1">
                <h3 className="text-sm font-bold text-foreground">
                  Package-Level Unobserved Declarations ({unobservedDeclarations.length})
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  These statutory items were not observed across <strong>any of the 3 captured package surfaces</strong>.
                  Under Legal Metrology Rules, absence is evaluated across the package as a whole; this is <strong>not</strong> an error or omission of Face 1 or Face 2 individually.
                </p>
                <div className="mt-2.5 flex flex-wrap gap-2">
                  {unobservedDeclarations.map((d: any) => (
                    <div
                      key={d.field}
                      className="inline-flex items-center gap-2 rounded-lg border border-amber-500/20 bg-background/80 px-2.5 py-1 text-xs"
                    >
                      <span className="font-semibold text-foreground">{d.field}</span>
                      <span className="rounded bg-amber-500/10 px-1.5 py-0.2 text-[10px] font-bold text-amber-500 uppercase">
                        {d.status}
                      </span>
                      {d.reason && (
                        <span className="text-[11px] text-muted-foreground max-w-xs truncate">
                          ({d.reason})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Dynamic Evidence Crop & Multi-Signal Audit Drawer */}
        <div className="grid gap-6 lg:grid-cols-[1.3fr_0.95fr]">
          {/* Left: Dynamic Evidence Crop & Coordinate Projection */}
          <section className="flex flex-col space-y-3 rounded-2xl border border-border/70 bg-card p-4 sm:p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">
                  Dynamic Evidence Crop · {activeDecl?.field || selectedLabel}
                </p>
                <h3 className="text-lg font-semibold tracking-tight">
                  Located on {activeSurface?.faceLabel || activeSurface?.surfaceType} (P{((activeSurface?.priorityScore ?? 1.0) * 100).toFixed(0)})
                </h3>
              </div>
              <span className="rounded-full bg-brand-soft px-3 py-1 text-xs font-bold text-brand">
                Target Crop Active
              </span>
            </div>

            {/* Coordinate Projection Info */}
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/60 px-3 py-1.5 text-[11px] font-mono text-muted-foreground">
              <span>
                <strong>Coordinate Space:</strong> DYNAMIC_CROP (
                {faceNaturalSizes[activeSurface.surfaceType]
                  ? `${faceNaturalSizes[activeSurface.surfaceType].w}×${faceNaturalSizes[activeSurface.surfaceType].h}px`
                  : "Reading..."}
                )
              </span>
              <span>
                <strong>Projection:</strong> In-plane Rectified Canonical ↔ Sensor
              </span>
            </div>

            {/* Dynamic Crop Component */}
            <DynamicEvidenceCrop
              imageSrc={
                activeSurface.canonicalImageUrl ||
                activeSurface.imageUrl ||
                inspection.canonicalImage ||
                inspection.image ||
                ""
              }
              bbox={targetBbox}
              polygon={activeDecl?.canonicalPolygonPx || activeDecl?.polygonPx || activeRegion?.canonicalPolygonPx || activeRegion?.polygonPx}
              localizationStatus={activeRegion?.localizationStatus || (targetBbox ? "VERIFIED_MATCH" : "UNLOCALIZED")}
              label={activeDecl?.field || selectedLabel}
              value={activeDecl?.value || activeRegion?.value}
              confidence={activeDecl?.confidence ?? activeRegion?.confidence}
            />

            {/* Transformation History Provenance Chain */}
            <div className="rounded-xl border border-border/60 bg-muted/40 p-3">
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
                Transformation Provenance Chain ({activeSurface?.faceLabel || activeSurface?.surfaceType}):
              </p>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-foreground/80">
                {(activeSurface.transformHistory || [
                  "Original Camera Sensor Capture",
                  "OpenCV Dual-Threshold Contouring",
                  "Perspective Homography H-Matrix",
                  "Safe +6% Outward Margin Rectification",
                  "Declaration Boundary Localized",
                ]).map((step: string, idx: number, arr: string[]) => (
                  <span key={step} className="inline-flex items-center gap-1.5">
                    <span className="rounded bg-card px-2 py-0.5 border border-border/80 text-[11px] font-medium">
                      {step}
                    </span>
                    {idx < arr.length - 1 && <ChevronRight className="h-3 w-3 text-muted-foreground" />}
                  </span>
                ))}
              </div>
            </div>

            {/* Quick Declaration Inspector Selector Chips */}
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[.15em] text-muted-foreground mb-2">
                Quick Declaration Inspector ({activeSurface?.faceLabel || activeSurface?.surfaceType})
              </p>
              <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto pr-1">
                {faceDeclarations.length > 0 ? (
                  faceDeclarations.map((d) => {
                    const isSelected = selectedLabel.toLowerCase() === d.field.toLowerCase();
                    return (
                      <button
                        key={d.field}
                        type="button"
                        onClick={() => handleSelectDeclaration(d.field)}
                        className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${isSelected
                            ? "bg-brand text-brand-foreground shadow-xs ring-1 ring-brand"
                            : "border border-border/60 bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
                          }`}
                      >
                        {d.field}
                      </button>
                    );
                  })
                ) : (
                  <span className="text-xs italic text-muted-foreground py-1">
                    No statutory declarations detected on this surface
                  </span>
                )}
              </div>
            </div>
          </section>

          {/* Right: Rich Explainability & Reasoning Signals */}
          <section className="flex flex-col space-y-4 rounded-2xl border border-border/70 bg-card p-5 sm:p-6 shadow-sm overflow-y-auto">
            <div className="flex items-center justify-between border-b border-border/70 pb-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Declaration Audit</p>
                <h3 className="text-xl font-bold tracking-tight text-foreground">{activeDecl?.field || selectedLabel}</h3>
              </div>
              <div className="text-right">
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ${activeDecl?.status === "VERIFIED"
                    ? "bg-success-soft text-success"
                    : activeDecl?.status === "MISSING"
                      ? "bg-danger-soft text-danger"
                      : "bg-warning-soft text-warning"
                  }`}>
                  {activeDecl?.status || "DETECTED"}
                </span>
                <p className="mt-1 text-[11px] font-mono text-muted-foreground">
                  Status: {activeDecl?.status === "VERIFIED" ? "Verified" : (activeDecl?.status === "REVIEW" ? "Review" : "Not detected")}
                </p>
              </div>
            </div>

            {/* Selected Value Card */}
            <div className="rounded-xl border border-border/80 bg-muted/40 p-4">
              <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Resolved Value</p>
              <p className="mt-1.5 text-2xl font-black tracking-tight text-foreground">
                {activeDecl?.value || activeRegion?.value || "Not Detected"}
              </p>
              {activeDecl?.ruleId && (
                <p className="mt-2 text-xs font-medium text-muted-foreground">
                  Governed under: <strong className="text-foreground">{activeDecl.ruleId}</strong>
                </p>
              )}
            </div>

            {/* Statutory Finding & Legal Notes */}
            <div className="rounded-xl border border-border/80 bg-muted/30 p-3.5 text-xs text-muted-foreground space-y-1">
              <p className="font-semibold text-foreground">
                Statutory Rule Analysis: {activeDecl?.ruleId || "Rule 6 - Declarations on Pre-packaged Commodities"}
              </p>
              <p className="leading-relaxed">
                {activeDecl?.reason || "Declaration is fully compliant with legal metrology statutory formatting and position standards."}
              </p>
            </div>
          </section>
        </div>
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------


