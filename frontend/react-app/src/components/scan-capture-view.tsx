import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Camera,
  CameraOff,
  Check,
  Flashlight,
  ImageIcon,
  LoaderCircle,
  RefreshCcw,
  ScanLine,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import { type Language, getTranslation } from "@/lib/i18n";
import { checkCaptureReadiness } from "@/lib/api-client";
import { type View, Button } from "./ui-primitives";

export function ScanView({
  onCaptured,
  onBack,
  lang = "en",
}: {
  onCaptured: (images: string[]) => void;
  onBack: () => void;
  lang?: Language;
}) {
  const t = getTranslation(lang);
  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState(false);
  const [captured, setCaptured] = useState<string[]>([]);
  const [guidance, setGuidance] = useState<string>("Position package inside viewfinder");
  const [isReady, setIsReady] = useState(false);

  // Dynamic quad corners state [TL, TR, BR, BL] in normalized 0..1 coordinates
  const targetCornersRef = useRef<Array<[number, number]>>([
    [0.15, 0.15],
    [0.85, 0.15],
    [0.85, 0.85],
    [0.15, 0.85],
  ]);
  const currentCornersRef = useRef<Array<[number, number]>>([
    [0.15, 0.15],
    [0.85, 0.15],
    [0.85, 0.85],
    [0.15, 0.85],
  ]);

  useEffect(() => () => { streamRef.current?.getTracks().forEach((track) => track.stop()); }, []);

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) { setCameraError(true); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setCameraActive(true);
    } catch { setCameraError(true); }
  }

  // Real-time assistive capture loop
  useEffect(() => {
    if (!cameraActive) return;
    let animId: number;
    let lastCheck = 0;
    const offscreen = document.createElement("canvas");
    offscreen.width = 240;
    offscreen.height = 300;
    const offCtx = offscreen.getContext("2d", { willReadFrequently: true });

    async function evaluateFrame() {
      const video = videoRef.current;
      const overlay = overlayCanvasRef.current;
      if (!video || !overlay || video.readyState < 2) {
        animId = requestAnimationFrame(evaluateFrame);
        return;
      }

      // Match canvas dimensions to display size
      const rect = overlay.getBoundingClientRect();
      if (overlay.width !== rect.width || overlay.height !== rect.height) {
        overlay.width = rect.width;
        overlay.height = rect.height;
      }

      const now = performance.now();
      // Periodically sample frame for quality & boundary checks (~180ms)
      if (now - lastCheck > 180 && offCtx) {
        lastCheck = now;
        offCtx.drawImage(video, 0, 0, offscreen.width, offscreen.height);
        const imgData = offCtx.getImageData(0, 0, offscreen.width, offscreen.height);
        const data = imgData.data;

        // 1. Luminance & Glare check
        let totalLuma = 0;
        let glareCount = 0;
        let darkCount = 0;
        const totalPixels = offscreen.width * offscreen.height;

        for (let i = 0; i < data.length; i += 4) {
          const luma = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
          totalLuma += luma;
          if (luma > 245) glareCount++;
          if (luma < 30) darkCount++;
        }
        const avgLuma = totalLuma / totalPixels;
        const glareRatio = glareCount / totalPixels;

        // 2. High-frequency edge energy (blur estimate)
        let edgeEnergy = 0;
        const w = offscreen.width;
        const step = 2;
        for (let y = 1; y < offscreen.height - 1; y += step) {
          for (let x = 1; x < w - 1; x += step) {
            const idx = (y * w + x) * 4;
            const diffX = Math.abs(data[idx] - data[idx + 4]);
            const diffY = Math.abs(data[idx] - data[idx + w * 4]);
            edgeEnergy += diffX + diffY;
          }
        }
        const sharpness = edgeEnergy / (totalPixels / (step * step));

        // 3. Package bounding proposal
        // Call backend lightweight detector with base64 snippet if available, or use adaptive boundary
        let ready = false;
        let msg = "Center package";

        if (sharpness < 18) {
          msg = "Hold steady";
          ready = false;
        } else if (glareRatio > 0.12) {
          msg = "Tilt package / Reduce glare";
          ready = false;
        } else if (avgLuma < 40) {
          msg = "More light needed";
          ready = false;
        } else {
          // Send scaled snippet to /capture/readiness for exact package corners if possible
          try {
            const snippet = offscreen.toDataURL("image/jpeg", 0.6);
            const readiness = await checkCaptureReadiness(snippet);
            if (readiness.detected && readiness.corners.length === 4) {
              const sw = offscreen.width;
              const sh = offscreen.height;
              targetCornersRef.current = readiness.corners.map(
                ([x, y]) => [Math.max(0.05, Math.min(0.95, x / sw)), Math.max(0.05, Math.min(0.95, y / sh))] as [number, number]
              );
              msg = readiness.guidance;
              ready = readiness.is_ready;
            } else {
              // Synthetic perspective framing standard
              targetCornersRef.current = [
                [0.18, 0.16],
                [0.82, 0.16],
                [0.84, 0.84],
                [0.16, 0.84],
              ];
              msg = sharpness > 28 ? "Ready for capture" : "Hold steady";
              ready = sharpness > 28;
            }
          } catch {
            targetCornersRef.current = [
              [0.18, 0.16],
              [0.82, 0.16],
              [0.84, 0.84],
              [0.16, 0.84],
            ];
            ready = sharpness > 25 && glareRatio < 0.10;
            msg = ready ? "Ready for capture" : "Hold steady";
          }
        }

        setIsReady(ready);
        setGuidance(msg);
      }

      // Smooth corners using exponential moving average for jitter-free rendering
      const curr = currentCornersRef.current;
      const target = targetCornersRef.current;
      const alpha = 0.35;
      for (let i = 0; i < 4; i++) {
        curr[i][0] = curr[i][0] * (1 - alpha) + target[i][0] * alpha;
        curr[i][1] = curr[i][1] * (1 - alpha) + target[i][1] * alpha;
      }

      // Draw dynamic perspective quadrilateral grid on overlay canvas
      const ctx = overlay.getContext("2d");
      if (ctx) {
        ctx.clearRect(0, 0, overlay.width, overlay.height);

        const ow = overlay.width;
        const oh = overlay.height;
        const p0 = [curr[0][0] * ow, curr[0][1] * oh];
        const p1 = [curr[1][0] * ow, curr[1][1] * oh];
        const p2 = [curr[2][0] * ow, curr[2][1] * oh];
        const p3 = [curr[3][0] * ow, curr[3][1] * oh];

        // Bilinear interpolation point helper
        function lerpPoint(u: number, v: number): [number, number] {
          const x = (1 - u) * (1 - v) * p0[0] + u * (1 - v) * p1[0] + u * v * p2[0] + (1 - u) * v * p3[0];
          const y = (1 - u) * (1 - v) * p0[1] + u * (1 - v) * p1[1] + u * v * p2[1] + (1 - u) * v * p3[1];
          return [x, y];
        }

        // Color selection: White normally, Green when ready
        const strokeColor = isReady ? "rgba(34, 197, 94, 0.95)" : "rgba(255, 255, 255, 0.85)";
        const meshColor = isReady ? "rgba(34, 197, 94, 0.35)" : "rgba(255, 255, 255, 0.25)";
        const glowColor = isReady ? "rgba(34, 197, 94, 0.6)" : "rgba(0, 0, 0, 0.4)";

        // 1. Draw interior 3x3 perspective mesh
        ctx.save();
        ctx.strokeStyle = meshColor;
        ctx.lineWidth = 1.2;
        ctx.setLineDash([4, 4]);

        for (const t of [0.333, 0.666]) {
          // Vertical mesh line
          const topPt = lerpPoint(t, 0);
          const botPt = lerpPoint(t, 1);
          ctx.beginPath();
          ctx.moveTo(topPt[0], topPt[1]);
          ctx.lineTo(botPt[0], botPt[1]);
          ctx.stroke();

          // Horizontal mesh line
          const leftPt = lerpPoint(0, t);
          const rightPt = lerpPoint(1, t);
          ctx.beginPath();
          ctx.moveTo(leftPt[0], leftPt[1]);
          ctx.lineTo(rightPt[0], rightPt[1]);
          ctx.stroke();
        }
        ctx.restore();

        // 2. Draw outer package boundary quadrilateral
        ctx.save();
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = isReady ? 3.0 : 2.0;
        ctx.shadowColor = glowColor;
        ctx.shadowBlur = isReady ? 12 : 4;

        ctx.beginPath();
        ctx.moveTo(p0[0], p0[1]);
        ctx.lineTo(p1[0], p1[1]);
        ctx.lineTo(p2[0], p2[1]);
        ctx.lineTo(p3[0], p3[1]);
        ctx.closePath();
        ctx.stroke();

        // 3. Draw 4 dynamic corner target anchors
        const cornerPoints = [p0, p1, p2, p3];
        cornerPoints.forEach(([cx, cy]) => {
          ctx.fillStyle = strokeColor;
          ctx.beginPath();
          ctx.arc(cx, cy, isReady ? 5.5 : 4.5, 0, Math.PI * 2);
          ctx.fill();

          ctx.strokeStyle = "rgba(0, 0, 0, 0.6)";
          ctx.lineWidth = 1;
          ctx.stroke();
        });

        ctx.restore();
      }

      animId = requestAnimationFrame(evaluateFrame);
    }

    animId = requestAnimationFrame(evaluateFrame);
    return () => cancelAnimationFrame(animId);
  }, [cameraActive, isReady]);

  function addImage(dataUrl: string) {
    setCaptured((current) => {
      if (current.length >= 6) return current;
      return [...current, dataUrl];
    });
  }

  // Preserve the original full-resolution image when captured!
  function capture() {
    if (!cameraActive || !videoRef.current || captured.length >= 6) return;
    const video = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 960;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      // Draw pristine raw video frame directly (preserves original image!)
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      addImage(canvas.toDataURL("image/jpeg", 0.92));
    }
  }

  function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    const remaining = 6 - captured.length;
    const toProcess = files.slice(0, remaining);
    toProcess.forEach((file) => {
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === "string") {
          setCaptured((prev) => {
            if (prev.length >= 6) return prev;
            return [...prev, reader.result as string];
          });
        }
      };
      reader.readAsDataURL(file);
    });
    event.target.value = "";
  }

  function removeAt(index: number) {
    setCaptured((current) => current.filter((_, i) => i !== index));
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 pb-8 pt-5 sm:px-6">
        {/* Top Header Bar */}
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={onBack}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 shadow-xs transition"
            aria-label="Back"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="text-center">
            <p className="text-[10px] font-extrabold uppercase tracking-[.2em] text-brand-700">
              Smart Assistive Capture
            </p>
            <h1 className="mt-0.5 text-lg font-bold text-slate-900">
              {t.scanProduct} ({captured.length}/6 {t.facesOf6})
            </h1>
          </div>
          <button
            type="button"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 shadow-xs transition"
            aria-label="Flash"
          >
            <Flashlight className="h-5 w-5" />
          </button>
        </div>

        {/* Camera Viewfinder Enclosure */}
        <div className="flex flex-1 flex-col justify-center py-4">
          <div className="relative mx-auto aspect-[4/5] w-full max-w-md overflow-hidden rounded-3xl border-2 border-slate-200 bg-slate-950 shadow-2xl">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className={`h-full w-full object-cover ${cameraActive ? "block" : "hidden"}`}
            />

            {/* Smart Adobe-Scan-Like Assistive Grid Overlay Canvas */}
            {cameraActive && (
              <canvas
                ref={overlayCanvasRef}
                className="absolute inset-0 pointer-events-none w-full h-full z-10"
              />
            )}

            {/* Floating Guidance Pill Badge */}
            {cameraActive && (
              <div className="absolute top-4 inset-x-0 flex justify-center z-20 pointer-events-none px-4">
                <div
                  className={`inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-bold shadow-lg backdrop-blur-md transition-all duration-200 ${
                    isReady
                      ? "bg-emerald-600/90 text-white ring-2 ring-emerald-400/50"
                      : "bg-slate-900/85 text-slate-200 border border-slate-700"
                  }`}
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      isReady ? "bg-emerald-300 animate-ping" : "bg-amber-400"
                    }`}
                  />
                  <span>{guidance}</span>
                </div>
              </div>
            )}

            {/* Inactive State Prompt */}
            {!cameraActive && (
              <div className="absolute inset-x-8 bottom-8 rounded-2xl border border-slate-700/80 bg-slate-900/90 p-5 text-center text-white backdrop-blur shadow-2xl">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-950 border border-brand-500/40 text-brand-300 mb-2">
                  <Camera className="h-6 w-6" />
                </div>
                <p className="text-sm font-bold text-white">{t.cameraPreview}</p>
                <p className="mt-1 text-xs leading-5 text-slate-300">
                  {t.positionPackageInside}
                </p>
                <Button
                  variant="primary"
                  className="mt-4 bg-brand hover:bg-brand-800 text-white font-bold px-5 shadow-lg ring-2 ring-brand-400/30"
                  onClick={startCamera}
                >
                  <Camera className="h-4 w-4 mr-1.5" />
                  {t.enableCamera}
                </Button>
              </div>
            )}
          </div>

          {/* Guidance Notes */}
          <p className="mx-auto mt-4 max-w-sm text-center text-xs sm:text-sm font-medium text-slate-600 leading-relaxed">
            {t.captureGuidance}
          </p>
          {captured.length >= 6 && (
            <div className="mx-auto mt-2 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-300 px-3.5 py-1 text-xs font-bold text-emerald-800">
              <Check className="h-3.5 w-3.5 text-emerald-600" />
              <span>{t.max6FacesReached}</span>
            </div>
          )}
          {cameraError && (
            <div className="mx-auto mt-3 flex items-center gap-2 rounded-xl bg-amber-50 border border-amber-200 px-4 py-2.5 text-xs font-semibold text-amber-900 shadow-xs">
              <CameraOff className="h-4 w-4 text-amber-600 shrink-0" />
              <span>{t.cameraUnavailable}</span>
            </div>
          )}

          {/* Captured Photos Gallery Strip */}
          {captured.length > 0 && (
            <div className="mx-auto mt-5 flex max-w-md gap-3 overflow-x-auto p-1 hide-scrollbar">
              {captured.map((img, index) => (
                <div
                  key={index}
                  className="relative h-20 w-16 shrink-0 overflow-hidden rounded-xl border-2 border-brand-300 bg-white shadow-sm ring-1 ring-brand-200/50"
                >
                  <img src={img} alt={`Face ${index + 1}`} className="h-full w-full object-cover" />
                  <span className="absolute left-1 top-1 rounded bg-brand px-1 py-0.5 text-[8px] font-extrabold text-white shadow-xs">
                    F{index + 1}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeAt(index)}
                    aria-label="Remove photo"
                    className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-600 text-white shadow hover:bg-red-700 transition"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Bottom Shutter & Action Bar */}
        <div className="flex items-end justify-between gap-4 pt-2">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={captured.length >= 6}
            className="flex w-24 flex-col items-center gap-1.5 text-xs font-bold text-slate-700 hover:text-brand-900 disabled:opacity-40 transition-colors"
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white border border-slate-200 text-brand shadow-sm hover:bg-brand-50 transition">
              <ImageIcon className="h-5 w-5" />
            </span>
            {t.gallery}
          </button>
          <button
            type="button"
            onClick={capture}
            aria-label="Capture inspection image"
            disabled={!cameraActive || captured.length >= 6}
            className="flex h-20 w-20 items-center justify-center rounded-full border-4 border-brand-100 bg-brand text-white shadow-xl hover:bg-brand-800 active:scale-95 disabled:opacity-40 transition-all"
          >
            <div className="flex h-14 w-14 items-center justify-center rounded-full border-2 border-white/60 bg-white/10">
              <Camera className="h-6 w-6" />
            </div>
          </button>
          <button
            type="button"
            onClick={() => captured.length && onCaptured(captured)}
            disabled={!captured.length}
            className={`flex w-24 flex-col items-center gap-1.5 text-xs font-bold ${captured.length ? "text-brand hover:text-brand-900" : "text-slate-400"
              } disabled:opacity-40 transition-colors`}
          >
            <span
              className={`flex h-12 w-12 items-center justify-center rounded-full transition-all ${captured.length
                  ? "bg-brand text-white hover:bg-brand-800 shadow-md ring-2 ring-brand-300"
                  : "bg-white border border-slate-200 text-slate-400 shadow-xs"
                }`}
            >
              <ArrowRight className="h-5 w-5" />
            </span>
            <span>
              {t.continue}
              {captured.length ? ` (${captured.length})` : ""}
            </span>
          </button>
        </div>
        <input ref={inputRef} type="file" accept="image/*" multiple onChange={handleFile} className="hidden" />
      </div>
    </div>
  );
}

const CATEGORY_OPTIONS = ["food", "beverage", "personal_care", "household", "other"];
const UNIT_OPTIONS = ["g", "kg", "ml", "l", "number"];


