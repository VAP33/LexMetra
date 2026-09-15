import { ArrowRight, BadgeCheck, ScanLine } from "lucide-react";

import type { Inspection } from "@/lib/types";
import type { View } from "@/lib/views";
import { AppHeader } from "@/components/layout";
import { Button, EmptyState, ErrorBanner, InspectionRow, Metric } from "@/components/ui";

export function HomeView({
  inspections,
  loading,
  error,
  onRetry,
  onLogout,
  onNavigate,
  onOpen,
}: {
  inspections: Inspection[];
  loading: boolean;
  error?: string;
  onRetry: () => void;
  onLogout?: () => void;
  onNavigate: (view: View) => void;
  onOpen: (inspection: Inspection) => void;
}) {
  const scanned = inspections.length;
  const compliant = inspections.filter((item) => item.status === "COMPLIANT").length;
  const violations = inspections.filter((item) => item.status === "VIOLATION").length;
  const review = inspections.filter((item) => item.status === "UNCERTAIN" || (item.reviewRequired && !item.reviewed)).length;
  const registerHealth = scanned ? Math.round((compliant / scanned) * 100) : 0;

  return (
    <>
      <AppHeader title="Inspection dashboard" online={!error} />
      <main className="mx-auto max-w-6xl space-y-8 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div>
            <p className="text-sm font-semibold text-brand">Field Unit · Legal Metrology</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-[-.05em] text-foreground sm:text-4xl">Inspection dashboard</h2>
            <p className="mt-2 text-sm text-muted-foreground">Ready for your next inspection?</p>
          </div>
          <Button onClick={() => onNavigate("scan")}><ScanLine className="h-4 w-4" />Start inspection<ArrowRight className="h-4 w-4" /></Button>
        </section>

        {error && <ErrorBanner message={error} onRetry={onRetry} onLogout={onLogout} />}

        <section className="grid grid-cols-2 gap-3 rounded-2xl border border-border/70 bg-card p-4 sm:grid-cols-4 sm:p-5">
          <Metric label="Scanned" value={scanned} loading={loading} />
          <Metric label="Compliant" value={compliant} accent="COMPLIANT" loading={loading} />
          <Metric label="Violations" value={violations} accent="VIOLATION" loading={loading} />
          <Metric label="Review" value={review} accent="UNCERTAIN" loading={loading} />
        </section>

        <section className="grid gap-5 lg:grid-cols-[1.2fr_.8fr]">
          <button type="button" onClick={() => onNavigate("scan")} className="group relative overflow-hidden rounded-2xl bg-primary p-6 text-left text-primary-foreground transition-transform hover:-translate-y-0.5 sm:p-8">
            <div className="absolute right-6 top-6 flex h-12 w-12 items-center justify-center rounded-full border border-primary-foreground/20 bg-primary-foreground/10"><ScanLine className="h-6 w-6" /></div>
            <p className="text-xs font-bold uppercase tracking-[.16em] text-primary-foreground/60">Next action</p>
            <h3 className="mt-12 max-w-sm text-2xl font-semibold tracking-[-.04em]">Scan a product label with confidence.</h3>
            <p className="mt-3 max-w-sm text-sm leading-6 text-primary-foreground/70">Capture declarations, validate the package, and keep an evidence-backed record.</p>
            <span className="mt-7 inline-flex items-center gap-2 text-sm font-semibold">Open scanner <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></span>
          </button>
          <div className="rounded-2xl border border-border/70 bg-card p-6 sm:p-8">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Register health</p>
                {loading ? <div className="mt-3 h-9 w-16 animate-pulse rounded-md bg-muted" /> : <p className="mt-3 text-3xl font-semibold tracking-[-.05em]">{registerHealth}%</p>}
              </div>
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-success-soft text-success"><BadgeCheck className="h-6 w-6" /></div>
            </div>
            <div className="mt-7 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-success transition-all" style={{ width: `${registerHealth}%` }} /></div>
            <p className="mt-3 text-sm text-muted-foreground">{scanned ? "Based on all inspections run so far." : "Run your first scan to populate this."}</p>
          </div>
        </section>

        <section>
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Latest activity</p>
              <h3 className="mt-1 text-xl font-semibold tracking-[-.035em]">Recent inspections</h3>
            </div>
            <button type="button" onClick={() => onNavigate("history")} className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:text-brand/80">View all <ArrowRight className="h-4 w-4" /></button>
          </div>
          {loading ? (
            <div className="space-y-3 rounded-2xl border border-border/70 bg-card p-4">
              {[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-muted" />)}
            </div>
          ) : inspections.length ? (
            <div className="rounded-2xl border border-border/70 bg-card px-4">{inspections.slice(0, 4).map((inspection) => <InspectionRow key={inspection.id} inspection={inspection} onOpen={onOpen} />)}</div>
          ) : (
            <EmptyState title="No inspections yet" description="Scan your first product to start building your inspection history." onAction={() => onNavigate("scan")} />
          )}
        </section>
      </main>
    </>
  );
}
