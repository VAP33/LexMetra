import { useEffect, useState, useRef } from "react";
import { Check, ShieldCheck } from "lucide-react";

interface TeslaScannerAnimationProps {
  currentStage?: string;
  stageIndex?: number;
  productName?: string;
}

const STAGES = [
  { id: "intake", label: "Package Intake & Face Normalization" },
  { id: "boundary", label: "Boundary Locked (+6.0% Safe Margin)" },
  { id: "perspective", label: "Perspective Rectified (3×3 Homography)" },
  { id: "enhancement", label: "Illumination Balanced & Text Preserved" },
  { id: "perception", label: "Multimodal Perception Ready" },
];

export function TeslaScannerAnimation({
  currentStage: _currentStage,
  stageIndex = 0,
  productName = "Packaged Commodity",
}: TeslaScannerAnimationProps) {
  const [activeStage, setActiveStage] = useState(stageIndex);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (stageIndex !== undefined) {
      setActiveStage(stageIndex);
    }
  }, [stageIndex]);

  // Tesla-style minimalist 3D geometric package visualization on HTML5 Canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let time = 0;

    const render = () => {
      time += 0.02;
      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);

      const cx = width / 2;
      const cy = height / 2 + 10;

      // Subtle slow yaw oscillation (Tesla vehicle visualizer style)
      const angle = Math.sin(time * 0.7) * 0.15;
      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);

      // Package dimensions
      const boxW = 85;
      const boxD = 70;
      const boxH = 130;

      // Isometric projection matrix helper
      const project = (x: number, y: number, z: number) => {
        // Rotate around Y axis
        const rx = x * cosA - z * sinA;
        const rz = x * sinA + z * cosA;
        // Isometric incline
        const isoX = cx + rx * 0.95 - rz * 0.85;
        const isoY = cy - y + (rx * 0.45 + rz * 0.5);
        return { x: isoX, y: isoY };
      };

      // Visible vertices of the package
      const p1 = project(boxW / 2, 0, -boxD / 2);  // Bottom-Back-Right
      const p2 = project(boxW / 2, 0, boxD / 2);   // Bottom-Front-Right
      const p3 = project(-boxW / 2, 0, boxD / 2);  // Bottom-Front-Left

      const p4 = project(-boxW / 2, boxH, -boxD / 2); // Top-Back-Left
      const p5 = project(boxW / 2, boxH, -boxD / 2);  // Top-Back-Right
      const p6 = project(boxW / 2, boxH, boxD / 2);   // Top-Front-Right
      const p7 = project(-boxW / 2, boxH, boxD / 2);  // Top-Front-Left

      // 1. Soft ground shadow
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(cx, cy + 70, 95, 30, 0, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(15, 23, 42, 0.05)";
      ctx.filter = "blur(10px)";
      ctx.fill();
      ctx.restore();

      // 2. Render solid surfaces with soft minimal shading
      // Front-Right Face (p2, p1, p5, p6)
      ctx.beginPath();
      ctx.moveTo(p2.x, p2.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.lineTo(p5.x, p5.y);
      ctx.lineTo(p6.x, p6.y);
      ctx.closePath();
      const gradFR = ctx.createLinearGradient(p6.x, p6.y, p1.x, p1.y);
      gradFR.addColorStop(0, "rgba(241, 245, 249, 0.92)");
      gradFR.addColorStop(1, "rgba(226, 232, 240, 0.88)");
      ctx.fillStyle = gradFR;
      ctx.fill();

      // Front-Left Face (p3, p2, p6, p7)
      ctx.beginPath();
      ctx.moveTo(p3.x, p3.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.lineTo(p6.x, p6.y);
      ctx.lineTo(p7.x, p7.y);
      ctx.closePath();
      const gradFL = ctx.createLinearGradient(p7.x, p7.y, p2.x, p2.y);
      gradFL.addColorStop(0, "rgba(248, 250, 252, 0.98)");
      gradFL.addColorStop(1, "rgba(238, 242, 246, 0.94)");
      ctx.fillStyle = gradFL;
      ctx.fill();

      // Top Face (p7, p6, p5, p4)
      ctx.beginPath();
      ctx.moveTo(p7.x, p7.y);
      ctx.lineTo(p6.x, p6.y);
      ctx.lineTo(p5.x, p5.y);
      ctx.lineTo(p4.x, p4.y);
      ctx.closePath();
      ctx.fillStyle = "rgba(255, 255, 255, 0.98)";
      ctx.fill();

      // 3. Subtle thin wireframe edges (Tesla visualizer aesthetic: clean 1px lines)
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = "rgba(100, 116, 139, 0.35)";
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

      // 4. Subtle structural declaration lines (clean gray indicators on front face)
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(148, 163, 184, 0.4)";
      for (let hFrac = 0.25; hFrac <= 0.75; hFrac += 0.15) {
        const lineY = boxH * hFrac;
        const lineP1 = project(-boxW / 2 + 10, lineY, boxD / 2);
        const lineP2 = project(boxW / 2 - 10, lineY, boxD / 2);
        ctx.beginPath();
        ctx.moveTo(lineP1.x, lineP1.y);
        ctx.lineTo(lineP2.x, lineP2.y);
        ctx.stroke();
      }

      // 5. Thin scanning plane sweeping vertically across the package
      // Sine wave sweep between 0 and boxH
      const scanPhase = (Math.sin(time * 2.2) + 1) / 2; // 0..1
      const scanY = boxH * scanPhase;

      const sp0 = project(-boxW * 0.65, scanY, -boxD * 0.65);
      const sp1 = project(boxW * 0.65, scanY, -boxD * 0.65);
      const sp2 = project(boxW * 0.65, scanY, boxD * 0.65);
      const sp3 = project(-boxW * 0.65, scanY, boxD * 0.65);

      // Scanning plane volume / line
      ctx.beginPath();
      ctx.moveTo(sp0.x, sp0.y);
      ctx.lineTo(sp1.x, sp1.y);
      ctx.lineTo(sp2.x, sp2.y);
      ctx.lineTo(sp3.x, sp3.y);
      ctx.closePath();

      // Restrained LexMetra Teal accent
      const scanGrad = ctx.createLinearGradient(sp3.x, sp3.y, sp1.x, sp1.y);
      scanGrad.addColorStop(0, "rgba(13, 148, 136, 0.03)");
      scanGrad.addColorStop(0.5, "rgba(13, 148, 136, 0.12)");
      scanGrad.addColorStop(1, "rgba(13, 148, 136, 0.03)");
      ctx.fillStyle = scanGrad;
      ctx.fill();

      // Thin scanning outline
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = "rgba(13, 148, 136, 0.65)";
      ctx.stroke();

      // Scanning intersection line across the front face
      const frontLeft = project(-boxW / 2, scanY, boxD / 2);
      const frontCenter = project(boxW / 2, scanY, boxD / 2);
      ctx.beginPath();
      ctx.moveTo(frontLeft.x, frontLeft.y);
      ctx.lineTo(frontCenter.x, frontCenter.y);
      ctx.lineWidth = 1.8;
      ctx.strokeStyle = "rgba(13, 148, 136, 0.9)";
      ctx.stroke();

      // 6. Surface anchor nodes / evidence points (subtle pulsing dots)
      const nodeCount = 4;
      for (let i = 0; i < nodeCount; i++) {
        const nodeY = boxH * (0.2 + i * 0.22);
        const distFromScan = Math.abs(nodeY - scanY);
        const intensity = Math.max(0, 1 - distFromScan / 30);

        if (intensity > 0.05) {
          const np = project(-boxW / 2 + 15 + i * 16, nodeY, boxD / 2);
          ctx.beginPath();
          ctx.arc(np.x, np.y, 2.5, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(13, 148, 136, ${0.4 + intensity * 0.6})`;
          ctx.fill();

          // Subtle ring around node
          ctx.beginPath();
          ctx.arc(np.x, np.y, 5 + intensity * 3, 0, Math.PI * 2);
          ctx.lineWidth = 0.8;
          ctx.strokeStyle = `rgba(13, 148, 136, ${intensity * 0.5})`;
          ctx.stroke();
        }
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="flex min-h-[560px] w-full flex-col items-center justify-center bg-white px-4 py-8 text-neutral-900 selection:bg-neutral-200">
      <div className="flex w-full max-w-lg flex-col items-center">
        {/* Header Branding */}
        <div className="flex items-center gap-2 rounded-full border border-neutral-200 bg-neutral-50 px-3.5 py-1 shadow-sm">
          <ShieldCheck className="h-4 w-4 text-teal-700" />
          <span className="text-[11px] font-semibold tracking-wider text-neutral-600 uppercase">
            LexMetra Technical Intake
          </span>
        </div>

        {/* Minimalist Tesla-style 3D Visualizer Canvas */}
        <div className="relative my-4 flex h-60 w-72 items-center justify-center">
          <canvas
            ref={canvasRef}
            width={288}
            height={240}
            className="h-full w-full object-contain"
          />
        </div>

        {/* Product Identity */}
        <div className="text-center">
          <h2 className="text-xl font-medium tracking-tight text-neutral-900">
            {productName}
          </h2>
          <p className="mt-1 text-xs text-neutral-500">
            Parallel 3-Face CV Ingestion & Evidence Normalization
          </p>
        </div>

        {/* Truthful Stage Rail (Driven strictly by actual state) */}
        <div className="mt-7 w-full space-y-2">
          {STAGES.map((step, idx) => {
            const isCompleted = idx < activeStage;
            const isCurrent = idx === activeStage;

            return (
              <div
                key={step.id}
                className={`flex items-center gap-3 rounded-lg border px-3.5 py-2.5 transition-all duration-300 ${
                  isCurrent
                    ? "border-neutral-900 bg-neutral-900 text-white shadow-sm"
                    : isCompleted
                    ? "border-neutral-200 bg-neutral-50/80 text-neutral-700"
                    : "border-neutral-100 bg-white text-neutral-400"
                }`}
              >
                {/* Stage Indicator */}
                <div className="flex h-5 w-5 shrink-0 items-center justify-center">
                  {isCompleted ? (
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-teal-600 text-white">
                      <Check className="h-2.5 w-2.5 stroke-[2.5]" />
                    </span>
                  ) : isCurrent ? (
                    <span className="relative flex h-2.5 w-2.5">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-75" />
                      <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-teal-400" />
                    </span>
                  ) : (
                    <span className="h-1.5 w-1.5 rounded-full bg-neutral-300" />
                  )}
                </div>

                {/* Stage Label */}
                <span className="text-xs font-medium tracking-normal">
                  {step.label}
                </span>

                {/* Status Tag */}
                {isCurrent && (
                  <span className="ml-auto rounded bg-neutral-800 px-2 py-0.5 text-[10px] font-medium tracking-wide text-teal-300 uppercase">
                    ACTIVE
                  </span>
                )}
                {isCompleted && (
                  <span className="ml-auto text-[10px] font-medium text-neutral-500">
                    LOCKED
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Minimal Footer Metadata */}
        <div className="mt-6 flex items-center gap-4 text-[11px] text-neutral-400">
          <span>Evidence-Safe +6% Boundary</span>
          <span>•</span>
          <span>Zero Evidence Loss Guarantee</span>
        </div>
      </div>
    </div>
  );
}
