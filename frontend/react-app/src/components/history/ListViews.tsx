import { Filter, Search } from "lucide-react";
import { useMemo, useState } from "react";

import type { Inspection, InspectionStatus } from "@/lib/types";
import type { View } from "@/lib/views";
import { AppHeader } from "@/components/layout";
import { EmptyState, ErrorBanner, InspectionRow, statusLabel } from "@/components/ui";

function FilterBar({ search, setSearch, filter, setFilter }: { search: string; setSearch: (value: string) => void; filter: "ALL" | InspectionStatus; setFilter: (value: "ALL" | InspectionStatus) => void }) {
  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search products or inspection IDs" className="h-11 w-full rounded-xl border border-border bg-card pl-10 pr-4 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/15" />
      </div>
      <div className="flex items-center gap-2 overflow-x-auto pb-1 hide-scrollbar">
        <Filter className="h-4 w-4 shrink-0 text-muted-foreground" />
        {(["ALL", "COMPLIANT", "VIOLATION", "UNCERTAIN", "EXEMPT"] as const).map((item) => (
          <button type="button" key={item} onClick={() => setFilter(item)} className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${filter === item ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"}`}>
            {item === "ALL" ? "All" : statusLabel(item)}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ListView({
  kind,
  inspections,
  loading,
  error,
  onRetry,
  onOpen,
  onNavigate,
}: {
  kind: "history" | "register";
  inspections: Inspection[];
  loading: boolean;
  error?: string;
  onRetry: () => void;
  onOpen: (inspection: Inspection) => void;
  onNavigate: (view: View) => void;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"ALL" | InspectionStatus>("ALL");
  const filtered = useMemo(
    () =>
      inspections.filter(
        (item) =>
          (kind === "history" || item.saved) &&
          (filter === "ALL" || item.status === filter) &&
          `${item.product} ${item.id} ${item.manufacturer}`.toLowerCase().includes(search.toLowerCase()),
      ),
    [filter, inspections, kind, search],
  );
  const title = kind === "history" ? "Inspection history" : "Compliance register";
  const subtitle = kind === "history" ? "Every package inspection, in one place." : "Products you have explicitly verified or reviewed.";
  return (
    <>
      <AppHeader title={title} online={!error} />
      <main className="mx-auto max-w-6xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="text-sm font-semibold text-brand">{kind === "history" ? "Audit trail" : "Statutory records"}</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-[-.05em]">{title}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>
          </div>
          <div className="rounded-xl bg-muted px-4 py-3 text-sm"><span className="text-muted-foreground">Showing </span><strong>{filtered.length}</strong><span className="text-muted-foreground"> records</span></div>
        </div>
        {error && <ErrorBanner message={error} onRetry={onRetry} />}
        <FilterBar search={search} setSearch={setSearch} filter={filter} setFilter={setFilter} />
        {loading ? (
          <div className="space-y-3 rounded-2xl border border-border/70 bg-card p-4">{[0, 1, 2, 3].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-muted" />)}</div>
        ) : filtered.length ? (
          <div className="rounded-2xl border border-border/70 bg-card px-4">{filtered.map((inspection) => <InspectionRow key={inspection.id} inspection={inspection} onOpen={onOpen} />)}</div>
        ) : (
          <EmptyState
            title={search || filter !== "ALL" ? "No matching records" : kind === "history" ? "No inspections yet" : "Your register is empty"}
            description={search || filter !== "ALL" ? "Try a different search or filter." : kind === "history" ? "Scan your first product to start building your inspection history." : "Products you verify and save will appear here."}
            onAction={() => onNavigate("scan")}
          />
        )}
      </main>
    </>
  );
}

/** Review queue is loaded from GET /inspections?needs_review=true — the same
 * filter dashboard.html uses — not a client-side guess on the history list. */
export function ReviewQueueView({
  inspections,
  loading,
  error,
  onRetry,
  onOpen,
  onNavigate,
}: {
  inspections: Inspection[];
  loading: boolean;
  error?: string;
  onRetry: () => void;
  onOpen: (inspection: Inspection) => void;
  onNavigate: (view: View) => void;
}) {
  return (
    <>
      <AppHeader title="Review queue" online={!error} />
      <main className="mx-auto max-w-6xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <div>
          <p className="text-sm font-semibold text-brand">Human-in-the-loop</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-[-.05em]">Review queue</h2>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Inspections with at least one fact flagged <code className="text-xs">review_required=true</code>,
            loaded from the backend. A reviewer can open a row and mark it reviewed with a note.
          </p>
        </div>
        {error && <ErrorBanner message={error} onRetry={onRetry} />}
        {loading ? (
          <div className="space-y-3 rounded-2xl border border-border/70 bg-card p-4">{[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-muted" />)}</div>
        ) : inspections.length ? (
          <div className="rounded-2xl border border-border/70 bg-card px-4">{inspections.map((inspection) => <InspectionRow key={inspection.id} inspection={inspection} onOpen={onOpen} />)}</div>
        ) : (
          <EmptyState title="Queue is clear" description="Nothing is waiting on human review right now." onAction={() => onNavigate("scan")} actionLabel="Start a scan" />
        )}
      </main>
    </>
  );
}
