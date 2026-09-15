/**
 * Evidence viewer — FE-01 surface for EVID-01.
 *
 * EVID-01 owns the full image → bbox → OCR → rule chain
 * (`GET /inspections/{id}/evidence`). This component currently overlays
 * whatever bbox/value the scan/session payload already carries. Extend this
 * file (and `lib/api-client.ts`) rather than forking `dashboard.html`.
 */
import { ArrowLeft, Info } from "lucide-react";
import { useState } from "react";

import { AppHeader } from "@/components/layout";
import { ProductThumb } from "@/components/ui";
import type { Inspection } from "@/lib/types";

export function EvidenceView({ inspection, onBack }: { inspection: Inspection; onBack: () => void }) {
  const [selected, setSelected] = useState(inspection.evidence[0]);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(
    inspection.imageNaturalWidth && inspection.imageNaturalHeight
      ? { w: inspection.imageNaturalWidth, h: inspection.imageNaturalHeight }
      : null,
  );

  function toPercentBox(bboxPx?: { x: number; y: number; width: number; height: number }) {
    if (!bboxPx || !naturalSize) return null;
    return {
      left: (bboxPx.x / naturalSize.w) * 100,
      top: (bboxPx.y / naturalSize.h) * 100,
      width: (bboxPx.width / naturalSize.w) * 100,
      height: (bboxPx.height / naturalSize.h) * 100,
    };
  }

  const regionsWithBox = inspection.evidence.filter((r) => r.bboxPx);
  const canOverlay = Boolean(inspection.image && naturalSize && regionsWithBox.length);

  return (
    <>
      <AppHeader title="Evidence viewer" />
      <main className="mx-auto max-w-5xl space-y-5 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Back to result</button>
        <div className="grid gap-5 lg:grid-cols-[1.25fr_.75fr]">
          <section className="rounded-2xl border border-border/70 bg-card p-4 sm:p-6">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Original capture</p>
                <h2 className="mt-2 text-xl font-semibold tracking-[-.035em]">Detected regions</h2>
              </div>
              <span className="rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand">{regionsWithBox.length} markers</span>
            </div>
            <div className="relative aspect-[4/3] overflow-hidden rounded-xl bg-muted">
              {inspection.image ? (
                <img
                  src={inspection.image}
                  alt="Uploaded package evidence"
                  className="h-full w-full object-cover"
                  onLoad={(e) => {
                    const img = e.currentTarget;
                    if (!naturalSize) setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
                  }}
                />
              ) : (
                <div className="flex h-full items-center justify-center"><ProductThumb inspection={inspection} large /></div>
              )}
              {canOverlay && regionsWithBox.map((region) => {
                const box = toPercentBox(region.bboxPx);
                if (!box) return null;
                return (
                  <button
                    type="button"
                    key={region.label}
                    onClick={() => setSelected(region)}
                    style={{ top: `${box.top}%`, left: `${box.left}%`, width: `${box.width}%`, height: `${box.height}%` }}
                    className={`absolute rounded-md border-2 text-left transition ${selected?.label === region.label ? "border-brand bg-brand/20" : "border-brand/70 bg-brand/10 hover:bg-brand/20"}`}
                  >
                    <span className="absolute -top-6 left-0 whitespace-nowrap rounded bg-brand px-1.5 py-1 text-[9px] font-bold text-white">{region.label} · {region.confidence}%</span>
                  </button>
                );
              })}
            </div>
            {!canOverlay && inspection.image && (
              <p className="mt-3 text-xs text-muted-foreground">Region markers aren't available for this inspection — showing the original capture only.</p>
            )}
          </section>
          <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-6">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Evidence detail</p>
            {selected ? (
              <>
                <h2 className="mt-3 text-2xl font-semibold tracking-[-.04em]">{selected.label}</h2>
                <p className="mt-2 text-sm text-muted-foreground">Detected from package image</p>
                <div className="mt-7 rounded-xl bg-muted p-4">
                  <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Detected text</p>
                  <p className="mt-2 text-lg font-semibold">{selected.value || "—"}</p>
                </div>
                <div className="mt-4 flex items-center justify-between border-b border-border pb-4">
                  <span className="text-sm text-muted-foreground">Confidence</span>
                  <span className="text-sm font-bold text-success">{selected.confidence}%</span>
                </div>
                <p className="mt-5 text-xs leading-5 text-muted-foreground">This region is linked to the extracted declaration in the inspection record.</p>
              </>
            ) : (
              <div className="mt-10 rounded-xl bg-warning-soft p-5 text-center">
                <Info className="mx-auto h-6 w-6 text-warning" />
                <p className="mt-3 text-sm font-semibold">Evidence unavailable</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">No reliable region was detected for this inspection.</p>
              </div>
            )}
          </section>
        </div>
        {(inspection.status === "UNCERTAIN" || (inspection.reviewRequired && !inspection.reviewed)) && (
          <div className="flex items-center gap-3 rounded-xl border border-warning/25 bg-warning-soft p-4 text-sm">
            <Info className="h-5 w-5 shrink-0 text-warning" />
            <p><strong>Human review recommended.</strong> The image does not provide sufficient evidence for a final compliance decision.</p>
          </div>
        )}
      </main>
    </>
  );
}
