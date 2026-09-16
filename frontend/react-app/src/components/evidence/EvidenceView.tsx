/**
 * Evidence viewer — EVID-01. Loads GET /inspections/{id}/evidence when the
 * inspection was persisted; falls back to scan-payload overlays otherwise.
 *
 * Honesty rules shown in the UI:
 * - not observed ≠ missing
 * - low OCR confidence ≠ non-compliance
 * - verification_status is surfaced, never dropped
 */
import { ArrowLeft, Info } from "lucide-react";
import { useEffect, useState } from "react";

import { AppHeader } from "@/components/layout";
import { ProductThumb } from "@/components/ui";
import { getInspectionEvidence, type EvidenceChainPayload } from "@/lib/api-client";
import type { Inspection } from "@/lib/types";

function confidenceClass(confidence: number | null | undefined): string {
  if (confidence == null) return "text-muted-foreground";
  if (confidence < 0.45) return "text-warning";
  if (confidence < 0.7) return "text-foreground";
  return "text-foreground";
}

export function EvidenceView({ inspection, onBack }: { inspection: Inspection; onBack: () => void }) {
  const [chain, setChain] = useState<EvidenceChainPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedField, setSelectedField] = useState<string | null>(inspection.evidence[0]?.label ?? null);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(
    inspection.imageNaturalWidth && inspection.imageNaturalHeight
      ? { w: inspection.imageNaturalWidth, h: inspection.imageNaturalHeight }
      : null,
  );

  useEffect(() => {
    let cancelled = false;
    getInspectionEvidence(inspection.id)
      .then((payload) => {
        if (cancelled) return;
        setChain(payload);
        if (payload.regions[0]) setSelectedField(payload.regions[0].field);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "Evidence endpoint unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, [inspection.id]);

  const imageSrc = chain?.image_url || inspection.image;

  const regions = chain
    ? chain.regions.map((r) => ({
        label: r.field,
        value: r.extracted_value || r.raw_text || "",
        confidence: r.confidence != null ? Math.round(r.confidence * 100) : null,
        bboxPx: r.bbox ?? undefined,
        status: r.status,
        reason: r.reason,
        sourceEngine: r.source_engine,
        reviewRequired: r.review_required,
      }))
    : inspection.evidence.map((r) => ({
        label: r.label,
        value: r.value,
        confidence: r.confidence,
        bboxPx: r.bboxPx,
        status: undefined as string | undefined,
        reason: "",
        sourceEngine: undefined as string | undefined,
        reviewRequired: false,
      }));

  const selected = regions.find((r) => r.label === selectedField) || regions[0];

  function toPercentBox(bboxPx?: { x: number; y: number; width: number; height: number }) {
    if (!bboxPx || !naturalSize) return null;
    return {
      left: (bboxPx.x / naturalSize.w) * 100,
      top: (bboxPx.y / naturalSize.h) * 100,
      width: (bboxPx.width / naturalSize.w) * 100,
      height: (bboxPx.height / naturalSize.h) * 100,
    };
  }

  const regionsWithBox = regions.filter((r) => r.bboxPx);
  const canOverlay = Boolean(imageSrc && naturalSize && regionsWithBox.length);

  return (
    <>
      <AppHeader title="Evidence viewer" />
      <main className="mx-auto max-w-5xl space-y-5 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
          Back to result
        </button>
        {chain?.honesty && (
          <div className="space-y-2 rounded-xl border border-border/70 bg-muted/50 p-4 text-xs leading-5 text-muted-foreground">
            <p><strong className="text-foreground">Not observed is not missing.</strong> {chain.honesty.not_observed_is_not_missing}</p>
            <p><strong className="text-foreground">Low confidence is not a violation.</strong> {chain.honesty.low_confidence_is_not_noncompliance}</p>
            <p>{chain.honesty.verification_status_note}</p>
          </div>
        )}
        {loadError && <p className="text-xs text-muted-foreground">Using scan payload overlays ({loadError}).</p>}
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
              {imageSrc ? (
                <img
                  src={imageSrc}
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
                    onClick={() => setSelectedField(region.label)}
                    style={{ top: `${box.top}%`, left: `${box.left}%`, width: `${box.width}%`, height: `${box.height}%` }}
                    className={`absolute rounded-md border-2 text-left transition ${selected?.label === region.label ? "border-brand bg-brand/20" : "border-brand/70 bg-brand/10 hover:bg-brand/20"}`}
                  >
                    <span className="absolute -top-6 left-0 whitespace-nowrap rounded bg-brand px-1.5 py-1 text-[9px] font-bold text-white">{region.label}</span>
                  </button>
                );
              })}
            </div>
          </section>
          <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-6">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Evidence detail</p>
            {selected ? (
              <>
                <h2 className="mt-3 text-2xl font-semibold tracking-[-.04em]">{selected.label}</h2>
                <p className="mt-2 text-sm text-muted-foreground">{selected.status === "UNCERTAIN" ? "Not a finding that the declaration is absent." : "Detected from package image"}</p>
                <div className="mt-7 rounded-xl bg-muted p-4">
                  <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Detected text</p>
                  <p className="mt-2 text-lg font-semibold">{selected.value || "— not observed in provided images —"}</p>
                </div>
                <div className="mt-4 flex items-center justify-between border-b border-border pb-4">
                  <span className="text-sm text-muted-foreground">Confidence (readability, not legality)</span>
                  <span className={`text-sm font-bold ${confidenceClass(selected.confidence == null ? null : selected.confidence / 100)}`}>
                    {selected.confidence == null ? "n/a" : `${selected.confidence}%`}
                  </span>
                </div>
                {selected.sourceEngine && <p className="mt-3 text-xs text-muted-foreground">Engine: {selected.sourceEngine}</p>}
                {selected.reason && <p className="mt-3 text-xs leading-5 text-muted-foreground">{selected.reason}</p>}
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
        {chain?.findings?.length ? (
          <section className="rounded-2xl border border-border/70 bg-card p-5">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Rule findings</p>
            <ul className="mt-3 space-y-3">
              {chain.findings.map((finding) => (
                <li key={finding.rule_id} className="rounded-lg bg-muted p-3 text-sm">
                  <p className="font-semibold">{finding.rule_id} · {finding.status}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{finding.reason}</p>
                  {finding.verification_status && (
                    <p className="mt-1 text-[11px] uppercase tracking-wide text-warning">verification: {finding.verification_status}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {(inspection.status === "UNCERTAIN" || (inspection.reviewRequired && !inspection.reviewed)) && (
          <div className="flex items-center gap-3 rounded-xl border border-warning/25 bg-warning-soft p-4 text-sm">
            <Info className="h-5 w-5 shrink-0 text-warning" />
            <p><strong>Human review recommended.</strong> The image does not provide sufficient evidence for a final compliance decision.</p>
          </div>
        )}
        <p className="text-xs text-muted-foreground">{chain?.disclaimer || inspection.disclaimer}</p>
      </main>
    </>
  );
}
