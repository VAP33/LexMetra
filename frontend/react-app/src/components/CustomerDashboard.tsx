import { useState } from "react";
import {
  Camera,
  CheckCircle2,
  ChevronRight,
  Package,
  ScanLine,
  ShoppingBag,
  ArrowLeft,
} from "lucide-react";
import { type Inspection } from "@/lib/types";

interface CustomerDashboardProps {
  inspections?: Inspection[];
  onStartScan?: () => void;
  onOpenInspection?: (inspection: Inspection) => void;
  onReportIssue?: (inspection: Inspection) => void;
  onBack?: () => void;
}

export function CustomerDashboard({
  inspections = [],
  onStartScan = () => {},
  onOpenInspection = () => {},
  onReportIssue = () => {},
  onBack,
}: CustomerDashboardProps) {
  const [activeTab, setActiveTab] = useState<"MY_SCANS" | "MY_REPORTS">("MY_SCANS");

  const consumerScans = inspections.slice(0, 8);
  const flaggedProducts = inspections.filter((i) => i.status === "VIOLATION" || i.status === "UNCERTAIN");

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:pt-8">
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground mb-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Officer Dashboard
        </button>
      )}
      {/* Citizen Welcome Banner */}
      <div className="rounded-3xl border border-border/80 bg-linear-to-br from-card via-card to-brand/5 p-6 sm:p-8 shadow-sm space-y-4">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-brand/10 border border-brand/20 px-3 py-0.5 text-[10px] font-bold text-brand uppercase tracking-wider">
            Consumer Protection Portal
          </span>
          <span className="text-xs text-muted-foreground">Legal Metrology Packaged Commodities</span>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="max-w-lg">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
              Verify your purchases. Protect your rights.
            </h1>
            <p className="mt-1.5 text-xs sm:text-sm text-muted-foreground leading-relaxed">
              Instant AI verification of printed MRP, Net Weight, and mandatory government declarations. Report shortages or price tampering directly to enforcement officers.
            </p>
          </div>

          <button
            type="button"
            onClick={onStartScan}
            className="inline-flex h-12 items-center justify-center gap-2.5 rounded-2xl bg-brand px-6 text-sm font-bold text-brand-foreground shadow-lg shadow-brand/20 hover:bg-brand/90 transition active:scale-98 shrink-0"
          >
            <ScanLine className="h-5 w-5" />
            Scan Product Now
          </button>
        </div>
      </div>

      {/* Quick Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-border/60 pb-3">
        <button
          type="button"
          onClick={() => setActiveTab("MY_SCANS")}
          className={`rounded-xl px-4 py-2 text-xs font-semibold transition ${
            activeTab === "MY_SCANS"
              ? "bg-foreground text-background"
              : "bg-muted text-muted-foreground hover:text-foreground"
          }`}
        >
          Recent Product Checks ({consumerScans.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("MY_REPORTS")}
          className={`rounded-xl px-4 py-2 text-xs font-semibold transition ${
            activeTab === "MY_REPORTS"
              ? "bg-foreground text-background"
              : "bg-muted text-muted-foreground hover:text-foreground"
          }`}
        >
          Flagged / Reported Issues ({flaggedProducts.length})
        </button>
      </div>

      {/* Tab 1: Recent Scans */}
      {activeTab === "MY_SCANS" && (
        <div className="space-y-4">
          {consumerScans.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border/70 p-12 text-center text-muted-foreground">
              <ShoppingBag className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
              <p className="text-sm font-semibold">No product scans yet</p>
              <p className="text-xs text-muted-foreground mt-1">
                Scan grocery, cosmetics, or beverage packages to verify price and net weight.
              </p>
              <button
                type="button"
                onClick={onStartScan}
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2 text-xs font-bold text-brand-foreground"
              >
                <Camera className="h-4 w-4" /> Scan First Package
              </button>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {consumerScans.map((item) => {
                const isPass = item.status === "COMPLIANT" || item.status === "EXEMPT";
                return (
                  <div
                    key={item.id}
                    onClick={() => onOpenInspection(item)}
                    className="cursor-pointer rounded-2xl border border-border/70 bg-card p-4 transition-all hover:border-brand hover:shadow-md space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px] text-muted-foreground font-semibold">#{item.id}</span>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold ${
                          isPass
                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                            : "bg-destructive/10 text-destructive"
                        }`}
                      >
                        {item.status}
                      </span>
                    </div>

                    <div className="flex items-center gap-3">
                      <div className="h-12 w-12 shrink-0 overflow-hidden rounded-xl bg-muted border border-border/50">
                        {item.image ? (
                          <img src={item.image} alt={item.product} className="h-full w-full object-cover" />
                        ) : (
                          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
                            <Package className="h-6 w-6" />
                          </div>
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <h3 className="text-sm font-bold text-foreground truncate">{item.product}</h3>
                        <p className="text-xs text-muted-foreground truncate">{item.dateLabel} · {item.summary}</p>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-border/50 text-[11px]">
                      <span className="text-muted-foreground">{item.declarations?.length || 6} Declarations</span>
                      <span className="text-brand font-semibold inline-flex items-center gap-1">
                        View Details <ChevronRight className="h-3 w-3" />
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Flagged / Reported */}
      {activeTab === "MY_REPORTS" && (
        <div className="space-y-4">
          {flaggedProducts.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border/70 p-12 text-center text-muted-foreground">
              <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-500 mb-3" />
              <p className="text-sm font-semibold">No non-compliant packages detected</p>
              <p className="text-xs text-muted-foreground mt-1">All scanned packages satisfied legal declarations.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {flaggedProducts.map((item) => (
                <div
                  key={item.id}
                  className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-destructive/15 px-2 py-0.5 text-[10px] font-bold text-destructive">
                        Potential Non-Compliance
                      </span>
                      <span className="font-mono text-[10px] text-muted-foreground">#{item.id}</span>
                    </div>
                    <h3 className="text-sm font-bold text-foreground mt-1">{item.product}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">{item.summary}</p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => onOpenInspection(item)}
                      className="rounded-xl border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted"
                    >
                      Inspect
                    </button>
                    <button
                      type="button"
                      onClick={() => onReportIssue(item)}
                      className="rounded-xl bg-destructive text-destructive-foreground px-3.5 py-1.5 text-xs font-bold shadow-xs hover:bg-destructive/90"
                    >
                      Escalate Complaint
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
