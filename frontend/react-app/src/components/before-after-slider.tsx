import React, { useState, useRef, useCallback } from "react";
import { SlidersHorizontal } from "lucide-react";

interface BeforeAfterSliderProps {
  originalUrl: string;
  canonicalUrl: string;
  faceLabel: string;
  naturalWidth?: number;
  naturalHeight?: number;
  marginPercent?: number;
  onClose?: () => void;
}

export function BeforeAfterSlider({
  originalUrl,
  canonicalUrl,
  faceLabel,
  naturalWidth,
  naturalHeight,
  marginPercent = 6.0,
  onClose,
}: BeforeAfterSliderProps) {
  const [sliderPos, setSliderPos] = useState(50); // percentage 0..100
  const containerRef = useRef<HTMLDivElement | null>(null);
  const isDragging = useRef(false);

  const handleMove = useCallback((clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
    setSliderPos(pct);
  }, []);

  const handleMouseDown = () => {
    isDragging.current = true;
  };

  const handleMouseUp = () => {
    isDragging.current = false;
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging.current) return;
    handleMove(e.clientX);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (e.touches.length > 0) {
      handleMove(e.touches[0].clientX);
    }
  };

  return (
    <div className="flex flex-col rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-100 pb-3 mb-3">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-teal-600" />
          <h3 className="text-sm font-semibold text-neutral-900">
            {faceLabel} · Dual-Image Normalization Comparison
          </h3>
          <span className="rounded bg-teal-50 px-2 py-0.5 text-[10px] font-bold text-teal-700">
            +{marginPercent.toFixed(1)}% OUTWARD MARGIN
          </span>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-neutral-400 hover:text-neutral-700"
          >
            Close
          </button>
        )}
      </div>

      {/* Interactive Split Canvas */}
      <div
        ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onMouseMove={handleMouseMove}
        onTouchMove={handleTouchMove}
        className="relative aspect-[4/3] w-full cursor-ew-resize select-none overflow-hidden rounded-xl border border-neutral-200 bg-neutral-950"
      >
        {/* Underneath: Canonical Rectified Image */}
        <img
          src={canonicalUrl}
          alt="Canonical Preprocessed Scan"
          className="absolute inset-0 h-full w-full object-contain pointer-events-none"
        />

        {/* Clipped Over: Raw Camera Original Image */}
        <div
          style={{ clipPath: `inset(0 ${100 - sliderPos}% 0 0)` }}
          className="absolute inset-0 h-full w-full overflow-hidden"
        >
          <img
            src={originalUrl}
            alt="Original Camera Photograph"
            className="absolute inset-0 h-full w-full object-contain pointer-events-none"
          />
        </div>

        {/* Left Label (Raw) */}
        <div className="absolute top-3 left-3 rounded bg-neutral-900/80 px-2 py-1 text-[10px] font-bold tracking-wider text-neutral-200 uppercase backdrop-blur-sm pointer-events-none">
          Raw Camera Capture
        </div>

        {/* Right Label (Canonical) */}
        <div className="absolute top-3 right-3 rounded bg-teal-950/85 px-2 py-1 text-[10px] font-bold tracking-wider text-teal-300 uppercase backdrop-blur-sm pointer-events-none">
          Canonical Scan (+6% Safe Margin)
        </div>

        {/* Slider Divider Line */}
        <div
          style={{ left: `${sliderPos}%` }}
          className="absolute top-0 bottom-0 w-0.5 bg-white shadow-[0_0_10px_rgba(0,0,0,0.5)] pointer-events-none"
        >
          <div className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-teal-600 text-white shadow-md">
            <SlidersHorizontal className="h-3.5 w-3.5" />
          </div>
        </div>
      </div>

      {/* Explanatory Caption */}
      <div className="mt-3 flex items-center justify-between text-xs text-neutral-500">
        <span>Drag slider to compare raw camera angle vs. front-facing rectified canonical scan</span>
        {naturalWidth && naturalHeight && (
          <span className="font-mono text-[11px]">
            Dimensions: {naturalWidth}×{naturalHeight} px
          </span>
        )}
      </div>
    </div>
  );
}
