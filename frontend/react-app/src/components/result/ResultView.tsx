import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronRight,
  CircleHelp,
  FileText,
  Info,
  Link2,
  LoaderCircle,
  ScanLine,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import { AppHeader } from "@/components/layout";
import { Button, DisclaimerBanner, StatusBadge, statusStyles } from "@/components/ui";
import type { Declaration, DeclarationStatus, Inspection } from "@/lib/types";

function DeclarationRow({ declaration }: { declaration: Declaration }) {
  const statusMap: Record<DeclarationStatus, { label: string; className: string; icon: LucideIcon }> = {
    VERIFIED: { label: "Verified", className: "text-success", icon: Check },
    MISSING: { label: "Missing", className: "text-destructive", icon: XCircle },
    REVIEW: { label: "Review", className: "text-warning", icon: Info },
    EXEMPT: { label: "Exempt", className: "text-brand", icon: ShieldCheck },
    UNOBSERVED: { label: "Not captured", className: "text-muted-foreground", icon: CircleHelp },
  };
  const [expanded, setExpanded] = useState(false);
  const item = statusMap[declaration.status] || statusMap.REVIEW;
  const Icon = item.icon;
  const rawText = declaration.provenance?.rawText?.trim();
  const showRawOcr = Boolean(rawText && rawText !== declaration.value);

  return (
    <div className={`border-b border-border/70 py-4 last:border-0 ${declaration.reviewRequired ? "bg-warning-soft/40 -mx-2 rounded-lg px-2" : ""}`}>
      <button type="button" onClick={() => setExpanded((v) => !v)} className="grid w-full grid-cols-[1fr_auto] items-center gap-4 text-left sm:grid-cols-[1.1fr_1fr_auto]">
        <div>
          <p className="text-sm font-semibold">{declaration.field}</p>
          <p className="mt-1 truncate text-xs text-muted-foreground sm:hidden">{declaration.value}</p>
        </div>
        <div className="hidden min-w-0 sm:block">
          <p className="truncate text-sm text-muted-foreground">{declaration.value}</p>
          {showRawOcr && (
            <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground/80" title={rawText}>
              OCR: {rawText}
            </p>
          )}
        </div>
        <div className={`flex items-center gap-1.5 text-xs font-semibold ${item.className}`}>
          <Icon className="h-4 w-4" />{item.label}
          {declaration.confidence != null && declaration.status !== "UNOBSERVED" && declaration.status !== "MISSING" && declaration.status !== "EXEMPT" && (
            <span className="hidden text-[10px] text-muted-foreground sm:inline">
              {declaration.confidence}%
              {declaration.ocrConfidence != null && declaration.ocrConfidence !== declaration.confidence && (
                <span className="text-[9px] text-muted-foreground/70" title="OCR confidence"> (OCR {declaration.ocrConfidence}%)</span>
              )}
            </span>
          )}
          <ChevronRight className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`} />
        </div>
      </button>
      {expanded && (
        <div className="mt-3 rounded-lg bg-muted p-3 text-xs leading-5 text-muted-foreground">
          <p>{declaration.reason || "No further detail available for this field."}</p>
          {showRawOcr && (
            <p className="mt-2 font-mono text-[11px] text-foreground">
              Raw OCR: {rawText}
            </p>
          )}
          {declaration.validationIssues && declaration.validationIssues.length > 0 && (
            <div className="mt-2 space-y-1">
              {declaration.validationIssues.map((issue, idx) => (
                <p key={idx} className="font-medium text-warning">• {issue}</p>
              ))}
            </div>
          )}
          {declaration.provenance?.surfaceType && (
            <p className="mt-1.5 text-[11px] text-muted-foreground">Captured panel: <span className="font-semibold text-foreground">{declaration.provenance.surfaceType}</span></p>
          )}
          {declaration.ruleId && (
            <p className="mt-2 inline-flex items-center gap-1.5 font-semibold text-foreground"><Link2 className="h-3 w-3" />{declaration.ruleId}{declaration.ruleVersion ? ` · ${declaration.ruleVersion}` : ""}</p>
          )}
          {declaration.reviewRequired && <p className="mt-2 font-semibold text-warning">Flagged for human review.</p>}
        </div>
      )}
    </div>
  );
}

function AiSignalsSection({ inspection }: { inspection: Inspection }) {
  const hasSignals = inspection.stickerSuspicions.length > 0 || inspection.similarMatches.length > 0 || inspection.priceOrLabelChangeFlag;
  if (!hasSignals) return null;
  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">AI signals</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-.035em]">Additional evidence</h3>
        </div>
        <ShieldAlert className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        These are heuristic signals for a human reviewer — they never decide compliance by themselves.
      </p>
      <div className="mt-4 space-y-3">
        {inspection.priceOrLabelChangeFlag && (
          <div className="flex items-start gap-3 rounded-xl bg-warning-soft p-4">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <p className="text-sm leading-5">{inspection.priceOrLabelChangeFlag}</p>
          </div>
        )}
        {inspection.stickerSuspicions.map((s, i) => (
          <div key={i} className="flex items-start gap-3 rounded-xl bg-warning-soft p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <div>
              <p className="text-sm font-semibold">Possible sticker or alteration</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{s.reason} (heuristic confidence {(s.confidence * 100).toFixed(0)}%)</p>
            </div>
          </div>
        ))}
        {inspection.similarMatches.map((m, i) => (
          <div key={i} className="flex items-center justify-between rounded-xl bg-muted p-4 text-xs">
            <span className="font-semibold">{m.productId}</span>
            <span className="text-muted-foreground">similarity: {(m.score * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function ReviewPanel({
  inspection,
  submitting,
  error,
  onMarkReviewed,
}: {
  inspection: Inspection;
  submitting: boolean;
  error?: string;
  onMarkReviewed: (note: string) => void;
}) {
  const [note, setNote] = useState(inspection.reviewerNote || "");

  if (inspection.reviewed) {
    return (
      <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
        <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Human review</p>
        <h3 className="mt-2 text-xl font-semibold tracking-[-.035em]">Reviewed</h3>
        <p className="mt-3 text-sm text-muted-foreground">Note: {inspection.reviewerNote || "(none)"}</p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
      <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Human review</p>
      <h3 className="mt-2 text-xl font-semibold tracking-[-.035em]">Mark reviewed</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Same action as the dashboard Review Queue — POST /inspections/{"{id}"}/review. Requires reviewer or admin role.
      </p>
      <label className="mt-4 block text-xs font-semibold text-muted-foreground">Reviewer note</label>
      <input
        id="reviewNote"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="e.g. verified against physical package, MRP confirmed 470"
        className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
      />
      {error && (
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-danger-soft px-3 py-2 text-xs text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" />{error}
        </div>
      )}
      <Button className="mt-4" onClick={() => onMarkReviewed(note)} disabled={submitting}>
        {submitting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
        {submitting ? "Saving…" : "Mark reviewed"}
      </Button>
    </section>
  );
}

export function ResultView({
  inspection,
  reviewSubmitting,
  reviewError,
  onMarkReviewed,
  onOpenEvidence,
  onOpenReport,
  onNew,
}: {
  inspection: Inspection;
  reviewSubmitting?: boolean;
  reviewError?: string;
  onMarkReviewed: (note: string) => void;
  onOpenEvidence: () => void;
  onOpenReport: () => void;
  onNew: () => void;
}) {
  const style = statusStyles[inspection.status];
  const verified = inspection.declarations.filter((item) => item.status === "VERIFIED" || item.status === "EXEMPT").length;
  const total = inspection.declarations.length;
  const headline =
    inspection.status === "COMPLIANT" ? "Compliant" :
    inspection.status === "VIOLATION" ? "Compliance issue found" :
    inspection.status === "EXEMPT" ? "Exempt from these rules" : "Needs review";
  const body =
    inspection.status === "COMPLIANT" ? "Required declarations were detected and validated against the applicable rules." :
    inspection.status === "VIOLATION" ? "Some required information was not detected or needs an officer review." :
    inspection.status === "EXEMPT" ? (inspection.exemptReason || "This package falls outside the scope of these rules.") :
    "Some information could not be reliably verified from the image.";

  return (
    <>
      <AppHeader title="Inspection result" />
      <main className="mx-auto max-w-5xl space-y-5 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <button type="button" onClick={onNew} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />New inspection</button>

        <section className={`overflow-hidden rounded-2xl border ${style.border} ${style.bg}`}>
          <div className="flex flex-col gap-6 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-7">
            <div>
              <StatusBadge status={inspection.status} />
              <h2 className="mt-4 text-3xl font-semibold tracking-[-.05em]">{headline}</h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">{body}</p>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <div className="flex h-24 w-24 flex-col items-center justify-center rounded-full bg-card shadow-sm border border-border/60">
                <span className={`text-2xl font-semibold ${style.text}`}>
                  {inspection.scoreBreakdown
                    ? `${inspection.scoreBreakdown.verifiedCount}/${inspection.scoreBreakdown.applicableCount}`
                    : `${inspection.verifiedScore ?? inspection.score}%`}
                </span>
                <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Verified</span>
              </div>
              <div className="flex h-20 w-20 flex-col items-center justify-center rounded-full bg-card/60 border border-border/40">
                <span className="text-xl font-semibold text-foreground">
                  {inspection.scoreBreakdown
                    ? `${inspection.scoreBreakdown.judgeableCount}/${inspection.scoreBreakdown.applicableCount}`
                    : `${inspection.reviewedScore ?? inspection.score}%`}
                </span>
                <span className="text-[8px] font-bold uppercase tracking-widest text-muted-foreground">Assessed</span>
              </div>
            </div>
          </div>
          {inspection.scoreBreakdown && inspection.scoreBreakdown.applicableCount > 0 && (
            <div className="border-t border-current/10 px-5 py-3 sm:px-7">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
                <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                  {inspection.scoreBreakdown.verifiedCount} verified
                </span>
                {inspection.scoreBreakdown.reviewCount > 0 && (
                  <span className="font-semibold text-amber-600 dark:text-amber-400">
                    {inspection.scoreBreakdown.reviewCount} need a closer look
                  </span>
                )}
                {inspection.scoreBreakdown.missingCount > 0 && (
                  <span className="font-semibold text-red-600 dark:text-red-400">
                    {inspection.scoreBreakdown.missingCount} absent
                  </span>
                )}
                {inspection.scoreBreakdown.blockedCount > 0 && (
                  <span className="font-semibold text-muted-foreground">
                    {inspection.scoreBreakdown.blockedCount} not assessable from this photo
                  </span>
                )}
                <span className="text-muted-foreground">
                  of {inspection.scoreBreakdown.applicableCount} applicable
                </span>
              </div>
              {inspection.scoreBreakdown.blockedCount > 0 &&
                inspection.scoreBreakdown.blockedCount >= inspection.scoreBreakdown.judgeableCount && (
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">
                    Most declarations were not visible in the captured frame, so they were
                    not assessed — this is not a finding against the product. Capture the
                    remaining panels to complete the inspection.
                  </p>
                )}
            </div>
          )}
          <div className="grid grid-cols-2 gap-4 border-t border-current/10 bg-card/50 p-5 sm:grid-cols-4">
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Product</p><p className="mt-1 text-sm font-semibold">{inspection.product}</p></div>
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Inspection</p><p className="mt-1 text-sm font-semibold">#{inspection.id}</p></div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Checked</p>
              <p className="mt-1 text-sm font-semibold">
                {inspection.declarationSummary ? `${inspection.declarationSummary.verified} / ${inspection.declarationSummary.applicable}` : `${verified} / ${total}`}
                {inspection.pdpAreaCm2 ? ` · ${inspection.pdpAreaCm2} cm² PDP` : ""}
              </p>
            </div>
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Time</p><p className="mt-1 text-sm font-semibold">{inspection.dateLabel}</p></div>
          </div>
        </section>

        <DisclaimerBanner text={inspection.disclaimer} />

        <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
          <div className="flex items-end justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Declarations</p>
              <h3 className="mt-2 text-xl font-semibold tracking-[-.035em]">Extracted information</h3>
              <p className="mt-1 text-xs text-muted-foreground">Extracted value is shown on each row; raw OCR text appears next to it when it differs.</p>
            </div>
            <div className="text-right">
              <span className="text-sm font-semibold text-muted-foreground">
                {inspection.declarationSummary ? `${inspection.declarationSummary.verified} / ${inspection.declarationSummary.applicable} verified` : `${verified}/${total} verified`}
              </span>
              {inspection.declarationSummary && inspection.declarationSummary.reviewRequired > 0 && (
                <p className="text-xs font-medium text-warning">{inspection.declarationSummary.reviewRequired} need review</p>
              )}
            </div>
          </div>
          <div className="mt-4">{inspection.declarations.map((declaration) => <DeclarationRow key={declaration.field} declaration={declaration} />)}</div>
        </section>

        {inspection.status !== "COMPLIANT" && inspection.status !== "EXEMPT" && (
          <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Rules checked</p>
                <h3 className="mt-2 text-xl font-semibold tracking-[-.035em]">Issues found</h3>
              </div>
              <SlidersHorizontal className="h-5 w-5 text-muted-foreground" />
            </div>
            <div className="mt-4 space-y-3">
              {inspection.declarations.filter((item) => item.status !== "VERIFIED" && item.status !== "EXEMPT").map((item) => (
                <div key={item.field} className="flex items-start gap-3 rounded-xl bg-muted p-4">
                  <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${item.status === "MISSING" ? "bg-danger-soft text-destructive" : "bg-warning-soft text-warning"}`}>
                    {item.status === "MISSING" ? <XCircle className="h-4 w-4" /> : <Info className="h-4 w-4" />}
                  </div>
                  <div>
                    <p className="text-sm font-semibold">{item.field}</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.reason || (item.status === "MISSING" ? "Required declaration was not detected in the captured label." : "Evidence is ambiguous and requires human review.")}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <AiSignalsSection inspection={inspection} />

        <ReviewPanel
          inspection={inspection}
          submitting={Boolean(reviewSubmitting)}
          error={reviewError}
          onMarkReviewed={onMarkReviewed}
        />

        <div className="grid gap-3 sm:grid-cols-2">
          <Button onClick={onOpenEvidence} variant="secondary"><ScanLine className="h-4 w-4" />View evidence</Button>
          <Button onClick={onOpenReport} variant="secondary"><FileText className="h-4 w-4" />Report preview</Button>
        </div>
      </main>
    </>
  );
}
