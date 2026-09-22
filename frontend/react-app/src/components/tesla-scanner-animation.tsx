import { useEffect, useState, useRef } from "react";
import { Check, ShieldCheck, Sparkles, FileSearch, Layers, Cpu, Eye, Camera } from "lucide-react";
import { type Language } from "@/lib/i18n";

interface TeslaScannerAnimationProps {
  currentStage?: string;
  stageIndex?: number;
  productName?: string;
  lang?: Language;
}

const STAGES = [
  {
    id: "intake",
    icon: Camera,
    en: "Multi-Angle Image Capture & Alignment",
    hi: "मल्टी-एंगल इमेज कैप्चर व संरेखण",
    mr: "मल्टी-अँगल प्रतिमा कॅप्चर व संरेखन",
    subEn: "Ingesting package surface captures with high resolution clarity",
    subHi: "उच्च रिज़ॉल्यूशन स्पष्टता के साथ पैकेज सतहों का समकालिक अधिग्रहण",
    subMr: "उच्च रिझोल्यूशन स्पष्टतेसह पॅकेज प्रतिमा संपादन",
  },
  {
    id: "boundary",
    icon: Layers,
    en: "OpenCV Boundary Locking & Rectification",
    hi: "ओपनसीवी बाउंड्री लॉकिंग व सुधार",
    mr: "ओपनसीव्ही बाउंड्री लॉकिंग व दृष्टीकोन सुधारणा",
    subEn: "Perspective homography matrix rectification on all faces",
    subHi: "सभी सतहों पर होमोग्राफी मैट्रिक्स सुधार",
    subMr: "सर्व पृष्ठभागांवर होमोग्राफी मॅट्रिक्स सुधारणा",
  },
  {
    id: "ocr",
    icon: FileSearch,
    en: "Neural OCR & Text Localization",
    hi: "उच्च-घनता OCR व पाठ्य निष्कर्षण",
    mr: "उच्च-घनता OCR व मजकूर निष्कर्ष",
    subEn: "Extracting MRP, Net Weight, MFD, Expiry, FSSAI & Manufacturer",
    subHi: "MRP, शुद्ध वजन, निर्माण तिथि, समाप्ति, FSSAI व निर्माता का निष्कर्षण",
    subMr: "MRP, निव्वळ वजन, उत्पादन तारीख, एक्सपायरी, FSSAI व उत्पादक शोध",
  },
  {
    id: "rules",
    icon: Cpu,
    en: "Statutory Rule-Engine Verification",
    hi: "विधिक नियम इंजन सत्यापन (LMPC 2011)",
    mr: "वैधानिक नियम पडताळणी (LMPC 2011)",
    subEn: "Cross-checking Rule 6(1) declarations and Rule 6(11) Unit Sale Price",
    subHi: "नियम 6(1) घोषणाएं एवं नियम 6(11) इकाई विक्रय मूल्य की जांच",
    subMr: "नियम 6(1) अनिवार्य घोषणा व नियम 6(11) युनिट विक्री किंमत तपासणी",
  },
  {
    id: "vlm",
    icon: Eye,
    en: "VLM Visual Grounding & Audit Verification",
    hi: "VLM विजुअल ग्राउंडिंग व अंतिम ऑडिट",
    mr: "VLM व्हिज्युअल ग्राउंडिंग व पुरावा मॅपिंग",
    subEn: "Verifying bounding polygon evidence and tamper-proof compliance logging",
    subHi: "बाउंडिंग पॉलीगॉन साक्ष्य सत्यापन एवं डिजिटल ऑडिट लॉगिंग",
    subMr: "बाउंडिंग पॉलीगॉन पुरावा पडताळणी आणि डिजिटल नोंद",
  },
];

export function TeslaScannerAnimation({
  currentStage: _currentStage,
  stageIndex = 0,
  productName = "Packaged Commodity",
  lang = "en",
}: TeslaScannerAnimationProps) {
  const [activeStage, setActiveStage] = useState(stageIndex);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (stageIndex !== undefined) {
      setActiveStage(stageIndex);
    }
  }, [stageIndex]);

  // Enhanced 3D Geometric Package Visualizer with dynamic phase transitions
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let time = 0;

    const render = () => {
      time += 0.024;
      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);

      const cx = width / 2;
      // Box is pulled lower for balanced spatial composition
      const cy = height / 2 + 32;

      // Smooth yaw & pitch rotation
      const angle = Math.sin(time * 0.8) * 0.16;
      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);

      // Package dimensions
      const boxW = 88;
      const boxD = 72;
      const boxH = 120;

      // Isometric projection matrix
      const project = (x: number, y: number, z: number) => {
        const rx = x * cosA - z * sinA;
        const rz = x * sinA + z * cosA;
        const isoX = cx + rx * 0.96 - rz * 0.84;
        const isoY = cy - y + (rx * 0.44 + rz * 0.48);
        return { x: isoX, y: isoY };
      };

      // Vertices
      const p1 = project(boxW / 2, 0, -boxD / 2);
      const p2 = project(boxW / 2, 0, boxD / 2);
      const p3 = project(-boxW / 2, 0, boxD / 2);

      const p4 = project(-boxW / 2, boxH, -boxD / 2);
      const p5 = project(boxW / 2, boxH, -boxD / 2);
      const p6 = project(boxW / 2, boxH, boxD / 2);
      const p7 = project(-boxW / 2, boxH, boxD / 2);

      // 1. Holographic Floor Grid Rings & Radial Waves
      ctx.save();
      const wavePhase = (time * 1.5) % 1;
      ctx.beginPath();
      ctx.ellipse(cx, cy + 64, 115 * (0.8 + wavePhase * 0.25), 36 * (0.8 + wavePhase * 0.25), 0, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(124, 58, 237, ${0.35 * (1 - wavePhase)})`;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      ctx.beginPath();
      ctx.ellipse(cx, cy + 64, 110, 36, 0, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(59, 130, 246, 0.2)";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);
      ctx.stroke();

      ctx.beginPath();
      ctx.ellipse(cx, cy + 64, 75, 24, 0, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(124, 58, 237, 0.25)";
      ctx.lineWidth = 1;
      ctx.setLineDash([]);
      ctx.stroke();
      ctx.restore();

      // 2. Soft Ambient Shadow
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(cx, cy + 64, 90, 28, 0, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(15, 23, 42, 0.09)";
      ctx.filter = "blur(12px)";
      ctx.fill();
      ctx.restore();

      // 3. Faces rendering
      // Front-Right Face
      ctx.beginPath();
      ctx.moveTo(p2.x, p2.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.lineTo(p5.x, p5.y);
      ctx.lineTo(p6.x, p6.y);
      ctx.closePath();
      const gradFR = ctx.createLinearGradient(p6.x, p6.y, p1.x, p1.y);
      gradFR.addColorStop(0, "rgba(241, 245, 249, 0.96)");
      gradFR.addColorStop(1, "rgba(226, 232, 240, 0.92)");
      ctx.fillStyle = gradFR;
      ctx.fill();

      // Front-Left Face (Main PDP)
      ctx.beginPath();
      ctx.moveTo(p3.x, p3.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.lineTo(p6.x, p6.y);
      ctx.lineTo(p7.x, p7.y);
      ctx.closePath();
      const gradFL = ctx.createLinearGradient(p7.x, p7.y, p2.x, p2.y);
      gradFL.addColorStop(0, "rgba(255, 255, 255, 0.99)");
      gradFL.addColorStop(1, "rgba(243, 244, 246, 0.96)");
      ctx.fillStyle = gradFL;
      ctx.fill();

      // Top Face
      ctx.beginPath();
      ctx.moveTo(p7.x, p7.y);
      ctx.lineTo(p6.x, p6.y);
      ctx.lineTo(p5.x, p5.y);
      ctx.lineTo(p4.x, p4.y);
      ctx.closePath();
      ctx.fillStyle = "rgba(255, 255, 255, 0.98)";
      ctx.fill();

      // 4. Edges
      ctx.lineWidth = 1.4;
      ctx.strokeStyle = "rgba(71, 85, 105, 0.45)";
      const edges = [
        [p3, p2], [p2, p1], [p2, p6],
        [p3, p7], [p1, p5], [p7, p6],
        [p6, p5], [p5, p4], [p4, p7],
      ];
      edges.forEach(([start, end]) => {
        ctx.beginPath();
        ctx.moveTo(start.x, start.y);
        ctx.lineTo(end.x, end.y);
        ctx.stroke();
      });

      // 5. PHASE-SPECIFIC VISUAL OVERLAYS:
      if (activeStage === 0) {
        // Phase 1: Camera Flash & Crosshairs
        const flashIntensity = Math.abs(Math.sin(time * 4));
        ctx.save();
        ctx.fillStyle = `rgba(255, 255, 255, ${flashIntensity * 0.25})`;
        ctx.fillRect(0, 0, width, height);

        // Reticle target at center
        const centerPt = project(0, boxH / 2, boxD / 2);
        ctx.strokeStyle = "#3B82F6";
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        ctx.arc(centerPt.x, centerPt.y, 24, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(centerPt.x - 30, centerPt.y);
        ctx.lineTo(centerPt.x + 30, centerPt.y);
        ctx.moveTo(centerPt.x, centerPt.y - 30);
        ctx.lineTo(centerPt.x, centerPt.y + 30);
        ctx.stroke();
        ctx.restore();
      } else if (activeStage === 1) {
        // Phase 2: OpenCV Homography Wireframe Mesh
        ctx.save();
        ctx.strokeStyle = "rgba(16, 185, 129, 0.6)";
        ctx.lineWidth = 1;
        for (let step = 1; step <= 3; step++) {
          const yLevel = (boxH / 4) * step;
          const left = project(-boxW / 2, yLevel, boxD / 2);
          const right = project(boxW / 2, yLevel, boxD / 2);
          ctx.beginPath();
          ctx.moveTo(left.x, left.y);
          ctx.lineTo(right.x, right.y);
          ctx.stroke();
        }
        // Coordinate points
        [p7, p6, p3, p2].forEach((pt) => {
          ctx.fillStyle = "#10B981";
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 3.5, 0, Math.PI * 2);
          ctx.fill();
        });
        ctx.restore();
      }

      // 6. Corner Target Brackets (AR Computer Vision effect)
      const bracketCorners = [p7, p6, p3, p2];
      bracketCorners.forEach((pt, i) => {
        ctx.save();
        ctx.strokeStyle = activeStage >= 3 ? "#10B981" : "#7C3AED";
        ctx.lineWidth = 2.5;
        const offset = (i % 2 === 0 ? -1 : 1) * 7;
        const vertOffset = (i < 2 ? -1 : 1) * 7;
        ctx.beginPath();
        ctx.moveTo(pt.x + offset, pt.y);
        ctx.lineTo(pt.x, pt.y);
        ctx.lineTo(pt.x, pt.y + vertOffset);
        ctx.stroke();
        ctx.restore();
      });

      // 7. Laser Scan Plane Sweeping (Synchronized with activeStage)
      // activeStage runs 0..4 over 3 seconds each.
      // Progress across 5 stages is 0.0 to 1.0; within each stage, we sweep smoothly.
      const basePhase = activeStage / 4.0;
      // Slight smooth oscillatory sweep confined around current stage height
      const sweepOffset = Math.sin(time * 1.5) * 0.08;
      const stageScanPhase = Math.max(0, Math.min(1, (1.0 - (basePhase * 0.8 + 0.1)) + sweepOffset));
      const scanY = boxH * stageScanPhase;

      const sp0 = project(-boxW * 0.68, scanY, -boxD * 0.68);
      const sp1 = project(boxW * 0.68, scanY, -boxD * 0.68);
      const sp2 = project(boxW * 0.68, scanY, boxD * 0.68);
      const sp3 = project(-boxW * 0.68, scanY, boxD * 0.68);

      ctx.beginPath();
      ctx.moveTo(sp0.x, sp0.y);
      ctx.lineTo(sp1.x, sp1.y);
      ctx.lineTo(sp2.x, sp2.y);
      ctx.lineTo(sp3.x, sp3.y);
      ctx.closePath();

      const scanGrad = ctx.createLinearGradient(sp3.x, sp3.y, sp1.x, sp1.y);
      scanGrad.addColorStop(0, "rgba(124, 58, 237, 0.05)");
      scanGrad.addColorStop(0.5, "rgba(147, 51, 234, 0.24)");
      scanGrad.addColorStop(1, "rgba(59, 130, 246, 0.05)");
      ctx.fillStyle = scanGrad;
      ctx.fill();

      // Glowing laser scan line across PDP
      const frontLeft = project(-boxW / 2, scanY, boxD / 2);
      const frontCenter = project(boxW / 2, scanY, boxD / 2);
      ctx.beginPath();
      ctx.moveTo(frontLeft.x, frontLeft.y);
      ctx.lineTo(frontCenter.x, frontCenter.y);
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = activeStage >= 3 ? "#10B981" : "#8B5CF6";
      ctx.shadowColor = activeStage >= 3 ? "#10B981" : "#8B5CF6";
      ctx.shadowBlur = 12;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // 8. Surface Detected Bounding Boxes on PDP
      // Bounding boxes unlock and persist as activeStage progresses:
      // Stage 1+: Top box unlocked
      // Stage 2+: Middle box unlocked
      // Stage 3+: Bottom box unlocked
      const regions = [
        { y: boxH * 0.72, w: boxW * 0.45, h: 14, color: "#10B981", minStage: 1 },
        { y: boxH * 0.48, w: boxW * 0.65, h: 16, color: "#3B82F6", minStage: 2 },
        { y: boxH * 0.24, w: boxW * 0.55, h: 14, color: "#F59E0B", minStage: 3 },
      ];

      regions.forEach((reg) => {
        if (activeStage >= reg.minStage) {
          const rP1 = project(-boxW / 2 + 8, reg.y, boxD / 2);
          const rP2 = project(-boxW / 2 + 8 + reg.w, reg.y, boxD / 2);
          const rP3 = project(-boxW / 2 + 8 + reg.w, reg.y - reg.h, boxD / 2);
          const rP4 = project(-boxW / 2 + 8, reg.y - reg.h, boxD / 2);

          ctx.beginPath();
          ctx.moveTo(rP1.x, rP1.y);
          ctx.lineTo(rP2.x, rP2.y);
          ctx.lineTo(rP3.x, rP3.y);
          ctx.lineTo(rP4.x, rP4.y);
          ctx.closePath();
          ctx.strokeStyle = reg.color;
          ctx.lineWidth = 1.3;
          ctx.fillStyle = reg.color === "#10B981" ? "rgba(16, 185, 129, 0.16)" : "rgba(59, 130, 246, 0.16)";
          ctx.fill();
          ctx.stroke();
        }
      });

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [activeStage]);

  const currentStageInfo = STAGES[Math.min(activeStage, STAGES.length - 1)];
  const progressPercent = Math.round(((activeStage + 1) / STAGES.length) * 100);

  return (
    <div className="flex min-h-[580px] w-full flex-col items-center justify-center bg-gradient-to-b from-slate-50 via-white to-purple-50/30 px-4 py-8 text-slate-900 selection:bg-purple-100">
      <div className="flex w-full max-w-xl flex-col items-center">
        {/* Phase Header Badge */}
        <div className="flex items-center gap-2 rounded-full border border-purple-200 bg-purple-50 px-4 py-1.5 shadow-xs">
          <ShieldCheck className="h-4 w-4 text-purple-700 animate-pulse" />
          <span className="text-xs font-extrabold tracking-wider text-purple-950 uppercase">
            {lang === "hi"
              ? "विधिक मापविज्ञान स्वचालित अनुपालन स्क्रीनिंग"
              : lang === "mr"
              ? "कायदेशीर मापनशास्त्र स्वयंचलित पडताळणी"
              : "Legal Metrology AI Statutory Vision Screening"}
          </span>
        </div>

        {/* 3D Holographic Package Visualizer (pulled lower as requested) */}
        <div className="relative mt-3 mb-2 flex h-68 w-84 items-center justify-center">
          <canvas
            ref={canvasRef}
            width={336}
            height={272}
            className="h-full w-full object-contain"
          />
        </div>

        {/* Product & Active Stage Status */}
        <div className="text-center space-y-1">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 text-white px-3.5 py-1 text-xs font-bold shadow-xs">
            <Sparkles className="h-3.5 w-3.5 text-amber-300 animate-spin" />
            <span>
              {lang === "hi"
                ? `चरण ${activeStage + 1} / 5: ${currentStageInfo.hi}`
                : lang === "mr"
                ? `टप्पा ${activeStage + 1} / 5: ${currentStageInfo.mr}`
                : `Stage ${activeStage + 1} of 5: ${currentStageInfo.en}`}
            </span>
          </div>
          <h2 className="text-xl sm:text-2xl font-black tracking-tight text-slate-900">
            {productName}
          </h2>
          <p className="text-xs font-medium text-slate-500 max-w-md mx-auto">
            {lang === "hi" ? currentStageInfo.subHi : lang === "mr" ? currentStageInfo.subMr : currentStageInfo.subEn}
          </p>
        </div>

        {/* Overall Progress Bar */}
        <div className="mt-4 w-full">
          <div className="flex items-center justify-between text-xs font-bold text-slate-600 mb-1.5">
            <span>{lang === "hi" ? "पाइपलाइन निष्पादन प्रगति" : lang === "mr" ? "पडताळणी प्रगती" : "Pipeline Execution Progress"}</span>
            <span className="text-purple-700 font-extrabold">{progressPercent}%</span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-gradient-to-r from-purple-700 via-indigo-600 to-emerald-500 transition-all duration-500 shadow-sm"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* 5-Stage Stepper Rail */}
        <div className="mt-6 w-full space-y-2">
          {STAGES.map((step, idx) => {
            const isCompleted = idx < activeStage;
            const isCurrent = idx === activeStage;
            const StepIcon = step.icon;

            const stepTitle = lang === "hi" ? step.hi : lang === "mr" ? step.mr : step.en;

            return (
              <div
                key={step.id}
                className={`flex items-center gap-3 rounded-2xl border px-4 py-3 transition-all duration-300 ${
                  isCurrent
                    ? "border-purple-600 bg-purple-900 text-white shadow-md scale-[1.01]"
                    : isCompleted
                    ? "border-emerald-200 bg-emerald-50/80 text-emerald-950"
                    : "border-slate-200 bg-white text-slate-400"
                }`}
              >
                {/* Stage Icon */}
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-colors ${
                    isCurrent
                      ? "bg-purple-700 text-amber-300 ring-2 ring-purple-400"
                      : isCompleted
                      ? "bg-emerald-600 text-white"
                      : "bg-slate-100 text-slate-400"
                  }`}
                >
                  {isCompleted ? (
                    <Check className="h-4 w-4 stroke-[3]" />
                  ) : (
                    <StepIcon className={`h-4 w-4 ${isCurrent ? "animate-pulse" : ""}`} />
                  )}
                </div>

                {/* Stage Label & Details */}
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-bold tracking-tight truncate">{stepTitle}</p>
                  <p
                    className={`text-[10px] truncate mt-0.5 ${
                      isCurrent ? "text-purple-200" : isCompleted ? "text-emerald-700 font-medium" : "text-slate-400"
                    }`}
                  >
                    {lang === "hi" ? step.subHi : lang === "mr" ? step.subMr : step.subEn}
                  </p>
                </div>

                {/* Status Badge */}
                {isCurrent && (
                  <span className="shrink-0 rounded-lg bg-amber-400 px-2 py-0.5 text-[10px] font-black text-slate-950 uppercase tracking-wide animate-pulse">
                    {lang === "hi" ? "सक्रिय" : lang === "mr" ? "सक्रिय" : "PROCESSING"}
                  </span>
                )}
                {isCompleted && (
                  <span className="shrink-0 rounded-lg bg-emerald-100 text-emerald-800 px-2 py-0.5 text-[10px] font-bold">
                    ✓ {lang === "hi" ? "पूर्ण" : lang === "mr" ? "पूर्ण" : "VERIFIED"}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer Guarantee */}
        <div className="mt-5 flex items-center gap-3 text-[11px] font-semibold text-slate-400">
          <span>{lang === "hi" ? "LMPC 2011 नियम 6 एवं 26 अनुपालन" : lang === "mr" ? "LMPC 2011 नियम 6 व 26 पडताळणी" : "LMPC Rules 2011 Statutory Verification"}</span>
          <span>•</span>
          <span>{lang === "hi" ? "100% डिजिटल साक्ष्य लॉग" : lang === "mr" ? "100% डिजिटल पुरावा नोंद" : "100% Digital Evidence Chain"}</span>
        </div>
      </div>
    </div>
  );
}
