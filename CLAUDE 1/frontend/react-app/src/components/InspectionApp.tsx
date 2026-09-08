import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Bell,
  Camera,
  CameraOff,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  Download,
  FileCheck2,
  FileText,
  Filter,
  Flashlight,
  History as HistoryIcon,
  Image as ImageIcon,
  Info,
  LayoutDashboard,
  Link2,
  LoaderCircle,
  LogOut,
  Menu,
  PackageCheck,
  RefreshCcw,
  Search,
  ScanLine,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  UserRound,
  WifiOff,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  statusCopy,
  type Declaration,
  type DeclarationStatus,
  type Inspection,
  type InspectionStatus,
  type ScanDetails,
} from "@/lib/types";
import {
  ApiError,
  addSessionCapture,
  checkHealth,
  clearSession,
  createSession,
  finalizeSession,
  getInspectionDetail,
  getStoredToken,
  getStoredUser,
  listInspections,
  login,
  markReviewed,
  reportPdfAvailable,
  reportPdfUrl,
  type AuthedUser,
  type SurfaceType,
} from "@/lib/api-client";
import { fromFinalizedInspection, fromInspectionRow } from "@/lib/adapters";
import { dataUrlToBlob } from "@/lib/data-url";

type View =
  | "home"
  | "history"
  | "register"
  | "reviewQueue"
  | "profile"
  | "scan"
  | "scanDetails"
  | "processing"
  | "result"
  | "detail"
  | "evidence"
  | "report";

const navItems: Array<{ label: string; view: View; icon: LucideIcon }> = [
  { label: "Home", view: "home", icon: LayoutDashboard },
  { label: "History", view: "history", icon: HistoryIcon },
  { label: "Register", view: "register", icon: ClipboardCheck },
  { label: "Review", view: "reviewQueue", icon: ShieldAlert },
  { label: "Profile", view: "profile", icon: UserRound },
];

const statusStyles: Record<
  InspectionStatus,
  { dot: string; text: string; bg: string; border: string; icon: LucideIcon }
> = {
  COMPLIANT: { dot: "bg-success", text: "text-success", bg: "bg-success-soft", border: "border-success/20", icon: Check },
  VIOLATION: { dot: "bg-destructive", text: "text-destructive", bg: "bg-danger-soft", border: "border-destructive/20", icon: XCircle },
  UNCERTAIN: { dot: "bg-warning", text: "text-warning", bg: "bg-warning-soft", border: "border-warning/20", icon: Info },
  EXEMPT: { dot: "bg-brand", text: "text-brand", bg: "bg-brand-soft", border: "border-brand/20", icon: ShieldCheck },
};

function statusLabel(status: InspectionStatus) {
  return statusCopy[status].label;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
}

function Button({
  children,
  className = "",
  variant = "primary",
  onClick,
  type = "button",
  disabled = false,
}: {
  children: React.ReactNode;
  className?: string;
  variant?: "primary" | "secondary" | "quiet" | "danger";
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
}) {
  const variants = {
    primary: "bg-primary text-primary-foreground hover:bg-primary/90",
    secondary: "bg-card text-foreground ring-1 ring-inset ring-border hover:bg-muted",
    quiet: "text-muted-foreground hover:bg-muted hover:text-foreground",
    danger: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
  };
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition-all active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

function ProductThumb({ inspection, large = false }: { inspection: Inspection; large?: boolean }) {
  const initials = inspection.product.split(" ").map((word) => word[0]).slice(0, 2).join("");
  const tone =
    inspection.status === "VIOLATION" ? "bg-danger-soft" : inspection.status === "UNCERTAIN" ? "bg-warning-soft" : "bg-brand-soft";
  return (
    <div className={`relative flex shrink-0 items-center justify-center overflow-hidden rounded-xl ${large ? "h-28 w-24" : "h-12 w-12"} ${tone}`}>
      {inspection.image ? (
        <img src={inspection.image} alt={`${inspection.product} package`} className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-[72%] w-[66%] flex-col items-center justify-center rounded-md bg-card text-[10px] font-bold text-foreground shadow-sm">
          <PackageCheck className="mb-1 h-4 w-4 text-brand" />
          <span>{initials}</span>
        </div>
      )}
      <span className="absolute bottom-1 right-1 h-2 w-2 rounded-full bg-brand ring-2 ring-card" />
    </div>
  );
}

function StatusBadge({ status, compact = false }: { status: InspectionStatus; compact?: boolean }) {
  const style = statusStyles[status];
  const Icon = style.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-[.08em] ${style.bg} ${style.text} ${style.border}`}>
      <Icon className="h-3.5 w-3.5" />
      {compact ? statusCopy[status].short : statusLabel(status)}
    </span>
  );
}

function Metric({ label, value, accent, loading = false }: { label: string; value: number; accent?: InspectionStatus; loading?: boolean }) {
  const accentClass = accent ? statusStyles[accent].text : "text-foreground";
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-bold uppercase tracking-[.14em] text-muted-foreground">{label}</p>
      {loading ? (
        <div className="mt-2 h-7 w-10 animate-pulse rounded-md bg-muted" />
      ) : (
        <p className={`mt-1 text-2xl font-semibold tracking-[-.04em] ${accentClass}`}>{value}</p>
      )}
    </div>
  );
}

function InspectionRow({ inspection, onOpen }: { inspection: Inspection; onOpen: (inspection: Inspection) => void }) {
  return (
    <button type="button" onClick={() => onOpen(inspection)} className="group flex w-full items-center gap-3 border-b border-border/70 py-4 text-left last:border-0 hover:bg-muted/40">
      <ProductThumb inspection={inspection} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-foreground">{inspection.product}</p>
        <p className="mt-1 truncate text-xs text-muted-foreground">{inspection.dateLabel} · {inspection.summary}</p>
      </div>
      <div className="flex flex-col items-end gap-1">
        <StatusBadge status={inspection.status} compact />
        {inspection.reviewRequired && !inspection.reviewed && <span className="text-[10px] font-bold text-warning">Needs review</span>}
        <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </div>
    </button>
  );
}

function AppHeader({
  title,
  eyebrow = "The Inspectors",
  onMenu,
  online,
}: {
  title: string;
  eyebrow?: string;
  onMenu?: () => void;
  online?: boolean;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-border/70 bg-background/95 backdrop-blur md:border-b-0">
      <div className="mx-auto flex h-[72px] max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <button type="button" aria-label="Open navigation" onClick={onMenu} className="rounded-lg p-2 text-muted-foreground hover:bg-muted md:hidden">
            <Menu className="h-5 w-5" />
          </button>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[.18em] text-muted-foreground">{eyebrow}</p>
            <h1 className="mt-0.5 text-lg font-semibold tracking-[-.03em] text-foreground">{title}</h1>
          </div>
        </div>
        <div className="hidden items-center gap-3 md:flex">
          {online === false ? (
            <span className="inline-flex items-center gap-2 rounded-full bg-danger-soft px-3 py-1.5 text-xs font-semibold text-destructive">
              <WifiOff className="h-3.5 w-3.5" />Offline
            </span>
          ) : (
            <span className="inline-flex items-center gap-2 rounded-full bg-success-soft px-3 py-1.5 text-xs font-semibold text-success">
              <span className="h-1.5 w-1.5 rounded-full bg-success" />Live
            </span>
          )}
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground"><UserRound className="h-4 w-4" /></div>
        </div>
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground md:hidden"><UserRound className="h-4 w-4" /></div>
      </div>
    </header>
  );
}

function DesktopRail({ view, onNavigate }: { view: View; onNavigate: (view: View) => void }) {
  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-border/70 bg-card px-4 py-6 md:flex">
      <div className="mb-10 flex items-center gap-3 px-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground"><ScanLine className="h-5 w-5" /></div>
        <div>
          <p className="text-sm font-bold tracking-[-.03em]">THE INSPECTORS</p>
          <p className="text-[10px] font-bold uppercase tracking-[.12em] text-muted-foreground">SIH 2026 · PS 26034</p>
        </div>
      </div>
      <nav className="space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = view === item.view;
          return (
            <button key={item.view} type="button" onClick={() => onNavigate(item.view)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold transition-colors ${active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"}`}>
              <Icon className="h-[18px] w-[18px]" />{item.label}
            </button>
          );
        })}
      </nav>
      <div className="mt-auto rounded-2xl bg-muted p-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground"><ShieldCheck className="h-4 w-4 text-brand" />Live compliance engine</div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">Real OCR extraction and deterministic rule evaluation are active.</p>
      </div>
    </aside>
  );
}

function BottomNav({ view, onNavigate }: { view: View; onNavigate: (view: View) => void }) {
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-border/70 bg-card/95 px-3 pt-2 backdrop-blur md:hidden">
      <div className="mx-auto grid max-w-lg grid-cols-5 items-end">
        <NavButton label="Home" icon={LayoutDashboard} active={view === "home"} onClick={() => onNavigate("home")} />
        <NavButton label="History" icon={HistoryIcon} active={view === "history"} onClick={() => onNavigate("history")} />
        <div className="relative -top-5 flex justify-center">
          <button type="button" aria-label="Start a scan" onClick={() => onNavigate("scan")} className="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-xl shadow-primary/20 transition-transform active:scale-95">
            <ScanLine className="h-7 w-7" />
          </button>
        </div>
        <NavButton label="Review" icon={ShieldAlert} active={view === "reviewQueue"} onClick={() => onNavigate("reviewQueue")} />
        <NavButton label="Profile" icon={UserRound} active={view === "profile"} onClick={() => onNavigate("profile")} />
      </div>
    </nav>
  );
}

function NavButton({ label, icon: Icon, active, onClick }: { label: string; icon: LucideIcon; active: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={`flex min-h-14 flex-col items-center justify-center gap-1 text-[10px] font-semibold ${active ? "text-brand" : "text-muted-foreground"}`}>
      <Icon className="h-[18px] w-[18px]" /><span>{label}</span>
    </button>
  );
}

function EmptyState({ title, description, onAction, actionLabel = "Scan Product" }: { title: string; description: string; onAction: () => void; actionLabel?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-card px-6 py-12 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground"><PackageCheck className="h-6 w-6" /></div>
      <h3 className="mt-4 text-base font-semibold">{title}</h3>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{description}</p>
      <Button className="mt-6" onClick={onAction}><ScanLine className="h-4 w-4" />{actionLabel}</Button>
    </div>
  );
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-destructive/25 bg-danger-soft p-4 text-sm">
      <AlertTriangle className="h-5 w-5 shrink-0 text-destructive" />
      <p className="flex-1 text-destructive">{message}</p>
      {onRetry && <Button variant="secondary" onClick={onRetry}><RefreshCcw className="h-4 w-4" />Retry</Button>}
    </div>
  );
}

function DisclaimerBanner({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/70 bg-muted/60 p-4 text-xs leading-5 text-muted-foreground">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <p>{text}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Home
// ---------------------------------------------------------------------------

function HomeView({
  inspections,
  loading,
  error,
  onRetry,
  onNavigate,
  onOpen,
}: {
  inspections: Inspection[];
  loading: boolean;
  error?: string;
  onRetry: () => void;
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

        {error && <ErrorBanner message={error} onRetry={onRetry} />}

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

// ---------------------------------------------------------------------------
// History / Register / Review queue list views
// ---------------------------------------------------------------------------

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

function ListView({
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

function ReviewQueueView({
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
  const pending = inspections.filter((item) => item.reviewRequired && !item.reviewed);
  return (
    <>
      <AppHeader title="Review queue" online={!error} />
      <main className="mx-auto max-w-6xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <div>
          <p className="text-sm font-semibold text-brand">Human-in-the-loop</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-[-.05em]">Review queue</h2>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Low-confidence extractions, sticker/alteration suspicions, and other AI signals that need a person to look
            before anything is finalized. Nothing here has been auto-decided.
          </p>
        </div>
        {error && <ErrorBanner message={error} onRetry={onRetry} />}
        {loading ? (
          <div className="space-y-3 rounded-2xl border border-border/70 bg-card p-4">{[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-muted" />)}</div>
        ) : pending.length ? (
          <div className="rounded-2xl border border-border/70 bg-card px-4">{pending.map((inspection) => <InspectionRow key={inspection.id} inspection={inspection} onOpen={onOpen} />)}</div>
        ) : (
          <EmptyState title="Queue is clear" description="Nothing is waiting on human review right now." onAction={() => onNavigate("scan")} actionLabel="Start a scan" />
        )}
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// Scan flow: capture (multi-photo) -> details -> processing -> result
// ---------------------------------------------------------------------------

function ScanView({ onCaptured, onBack }: { onCaptured: (images: string[]) => void; onBack: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState(false);
  const [captured, setCaptured] = useState<string[]>([]);

  useEffect(() => () => { streamRef.current?.getTracks().forEach((track) => track.stop()); }, []);

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) { setCameraError(true); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setCameraActive(true);
    } catch { setCameraError(true); }
  }

  function addImage(dataUrl: string) {
    setCaptured((current) => [...current, dataUrl]);
  }

  function capture() {
    if (!cameraActive || !videoRef.current) return;
    const video = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 800;
    canvas.height = video.videoHeight || 1000;
    canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
    addImage(canvas.toDataURL("image/jpeg", 0.85));
  }

  function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { if (typeof reader.result === "string") addImage(reader.result); };
    reader.readAsDataURL(file);
    event.target.value = "";
  }

  function removeAt(index: number) {
    setCaptured((current) => current.filter((_, i) => i !== index));
  }

  return (
    <div className="min-h-screen bg-primary text-primary-foreground">
      <div className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 pb-8 pt-5 sm:px-6">
        <div className="flex items-center justify-between">
          <button type="button" onClick={onBack} className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-foreground/10 hover:bg-primary-foreground/15" aria-label="Back"><ArrowLeft className="h-5 w-5" /></button>
          <div className="text-center">
            <p className="text-[10px] font-bold uppercase tracking-[.2em] text-primary-foreground/60">Live capture</p>
            <h1 className="mt-1 text-lg font-semibold">Scan product</h1>
          </div>
          <button type="button" className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-foreground/10 hover:bg-primary-foreground/15" aria-label="Flash"><Flashlight className="h-5 w-5" /></button>
        </div>

        <div className="flex flex-1 flex-col justify-center py-8">
          <div className="relative mx-auto aspect-[4/5] w-full max-w-md overflow-hidden rounded-3xl border border-primary-foreground/20 bg-primary-foreground/5">
            <video ref={videoRef} autoPlay playsInline muted className={`h-full w-full object-cover ${cameraActive ? "block" : "hidden"}`} />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="relative h-[76%] w-[76%] rounded-2xl border border-primary-foreground/30">
                <span className="absolute -left-px -top-px h-10 w-10 rounded-tl-xl border-l-2 border-t-2 border-brand" />
                <span className="absolute -right-px -top-px h-10 w-10 rounded-tr-xl border-r-2 border-t-2 border-brand" />
                <span className="absolute -bottom-px -left-px h-10 w-10 rounded-bl-xl border-b-2 border-l-2 border-brand" />
                <span className="absolute -bottom-px -right-px h-10 w-10 rounded-br-xl border-b-2 border-r-2 border-brand" />
                {cameraActive && <div className="scan-line absolute inset-x-4 top-1/2 h-px bg-brand shadow-[0_0_18px] shadow-brand" />}
              </div>
            </div>
            {!cameraActive && (
              <div className="absolute inset-x-8 bottom-8 rounded-2xl border border-primary-foreground/15 bg-primary-foreground/10 p-4 text-center backdrop-blur">
                <Camera className="mx-auto h-7 w-7 text-primary-foreground/70" />
                <p className="mt-2 text-sm font-semibold">Camera preview</p>
                <p className="mt-1 text-xs leading-5 text-primary-foreground/60">Position the package label inside the frame.</p>
                <Button variant="secondary" className="mt-4 bg-primary-foreground text-primary" onClick={startCamera}><Camera className="h-4 w-4" />Enable camera</Button>
              </div>
            )}
          </div>

          <p className="mx-auto mt-5 max-w-sm text-center text-sm text-primary-foreground/65">
            Capture the front (product name) and back (declarations) separately for the most accurate result. Every
            photo you capture is analyzed together as one inspection.
          </p>
          {cameraError && <div className="mx-auto mt-3 flex items-center gap-2 rounded-lg bg-warning/20 px-3 py-2 text-xs text-warning"><CameraOff className="h-4 w-4" />Camera unavailable — use gallery instead.</div>}

          {captured.length > 0 && (
            <div className="mx-auto mt-6 flex max-w-md gap-3 overflow-x-auto hide-scrollbar">
              {captured.map((img, index) => (
                <div key={index} className="relative h-20 w-16 shrink-0 overflow-hidden rounded-lg border border-primary-foreground/20">
                  <img src={img} alt={`Capture ${index + 1}`} className="h-full w-full object-cover" />
                  <span className="absolute left-1 top-1 rounded bg-primary-foreground/80 px-1 text-[9px] font-bold text-primary">{index === 0 ? "Primary" : index + 1}</span>
                  <button type="button" onClick={() => removeAt(index)} aria-label="Remove photo" className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-black/50"><X className="h-2.5 w-2.5" /></button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-end justify-between gap-5">
          <button type="button" onClick={() => inputRef.current?.click()} className="flex w-24 flex-col items-center gap-2 text-xs font-semibold text-primary-foreground/70">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-foreground/10"><ImageIcon className="h-5 w-5" /></span>Gallery
          </button>
          <button type="button" onClick={capture} aria-label="Capture inspection image" disabled={!cameraActive} className="flex h-20 w-20 items-center justify-center rounded-full border-[6px] border-primary-foreground/20 bg-primary-foreground text-primary transition-transform active:scale-95 disabled:opacity-40">
            <div className="flex h-14 w-14 items-center justify-center rounded-full border-2 border-primary"><Camera className="h-6 w-6" /></div>
          </button>
          <button
            type="button"
            onClick={() => captured.length && onCaptured(captured)}
            disabled={!captured.length}
            className="flex w-24 flex-col items-center gap-2 text-xs font-semibold text-primary-foreground/70 disabled:opacity-40"
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-foreground/10"><ArrowRight className="h-5 w-5" /></span>
            Continue{captured.length ? ` (${captured.length})` : ""}
          </button>
        </div>
        <input ref={inputRef} type="file" accept="image/*" onChange={handleFile} className="hidden" />
      </div>
    </div>
  );
}

const CATEGORY_OPTIONS = ["food", "beverage", "personal_care", "household", "other"];
const UNIT_OPTIONS = ["g", "kg", "ml", "l", "number"];

function ScanDetailsView({
  images,
  onSubmit,
  onBack,
}: {
  images: string[];
  onSubmit: (details: ScanDetails) => void;
  onBack: () => void;
}) {
  const [productId, setProductId] = useState("");
  const [saleType, setSaleType] = useState<ScanDetails["saleType"]>("retail");
  const [category, setCategory] = useState(CATEGORY_OPTIONS[0]);
  const [qtyValue, setQtyValue] = useState("");
  const [qtyUnit, setQtyUnit] = useState(UNIT_OPTIONS[0]);
  const [mrp, setMrp] = useState("");
  const valid = productId.trim().length > 0 && Number(qtyValue) > 0;

  return (
    <>
      <AppHeader title="Confirm details" />
      <main className="mx-auto max-w-2xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Retake photos</button>

        <section className="flex gap-3 overflow-x-auto rounded-2xl border border-border/70 bg-card p-4 hide-scrollbar">
          {images.map((img, i) => (
            <div key={i} className="relative h-24 w-20 shrink-0 overflow-hidden rounded-xl border border-border">
              <img src={img} alt={`Capture ${i + 1}`} className="h-full w-full object-cover" />
              <span className="absolute left-1 top-1 rounded bg-primary/90 px-1.5 py-0.5 text-[9px] font-bold text-primary-foreground">{i === 0 ? "Primary" : `#${i + 1}`}</span>
            </div>
          ))}
        </section>

        <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
          <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Before we run the checks</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-.035em]">A few quick details</h2>
          <p className="mt-1 text-sm text-muted-foreground">These help the rule engine pick the right exemptions and thresholds — most are quick to confirm.</p>

          <div className="mt-6 space-y-5">
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Product ID / SKU</label>
              <input value={productId} onChange={(e) => setProductId(e.target.value)} placeholder="e.g. TRAYA-VITAMIN-30CAP" className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Sale type</label>
                <select value={saleType} onChange={(e) => setSaleType(e.target.value as ScanDetails["saleType"])} className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15">
                  <option value="retail">Retail</option>
                  <option value="wholesale">Wholesale</option>
                  <option value="industrial">Industrial</option>
                  <option value="institutional">Institutional</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Category</label>
                <select value={category} onChange={(e) => setCategory(e.target.value)} className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15">
                  {CATEGORY_OPTIONS.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-[1fr_auto] gap-3">
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Net quantity</label>
                <input value={qtyValue} onChange={(e) => setQtyValue(e.target.value)} type="number" placeholder="30" className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15" />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Unit</label>
                <select value={qtyUnit} onChange={(e) => setQtyUnit(e.target.value)} className="mt-1.5 h-11 rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15">
                  {UNIT_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}
                </select>
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground">MRP (₹) — optional, improves unit-price check</label>
              <input value={mrp} onChange={(e) => setMrp(e.target.value)} type="number" placeholder="470" className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15" />
            </div>
          </div>
        </section>

        <Button
          className="w-full"
          disabled={!valid}
          onClick={() =>
            onSubmit({
              productId: productId.trim(),
              saleType,
              productCategory: category,
              netQuantityValue: Number(qtyValue),
              netQuantityUnit: qtyUnit,
              mrp: mrp ? Number(mrp) : undefined,
            })
          }
        >
          Run compliance check<ArrowRight className="h-4 w-4" />
        </Button>
      </main>
    </>
  );
}

function ProcessingRunner({
  onRun,
  onDone,
  onError,
}: {
  onRun: () => Promise<Inspection>;
  onDone: (inspection: Inspection) => void;
  onError: (message: string) => void;
}) {
  const steps = ["Image received", "Detecting package label", "Extracting declarations", "Checking Legal Metrology rules", "Preparing compliance report"];
  const [active, setActive] = useState(0);
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    const interval = window.setInterval(() => {
      setActive((value) => Math.min(value + 1, steps.length - 1));
    }, 650);

    const minDisplay = new Promise((resolve) => window.setTimeout(resolve, 1400));

    Promise.all([onRun(), minDisplay])
      .then(([inspection]) => {
        window.clearInterval(interval);
        setActive(steps.length);
        window.setTimeout(() => onDone(inspection), 350);
      })
      .catch((err: unknown) => {
        window.clearInterval(interval);
        const message = err instanceof ApiError ? err.message : "Something went wrong while analyzing this package.";
        onError(message);
      });

    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-brand-soft text-brand"><LoaderCircle className="breathe h-9 w-9" /></div>
        <p className="mt-8 text-xs font-bold uppercase tracking-[.2em] text-brand">Inspection pipeline</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-.05em]">Analyzing package</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">Extracting evidence and checking each declaration against the Legal Metrology rule set.</p>
        <div className="mt-10 space-y-3 text-left">
          {steps.map((step, index) => (
            <div key={step} className={`flex items-center gap-3 rounded-xl border px-4 py-3 transition-all ${index < active ? "border-success/20 bg-success-soft" : index === active ? "border-brand/30 bg-brand-soft" : "border-border bg-card"}`}>
              {index < active ? (
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-success text-success-foreground"><Check className="h-3.5 w-3.5" /></span>
              ) : index === active ? (
                <LoaderCircle className="h-6 w-6 animate-spin text-brand" />
              ) : (
                <span className="h-6 w-6 rounded-full border border-border" />
              )}
              <span className={`text-sm font-semibold ${index <= active ? "text-foreground" : "text-muted-foreground"}`}>{step}</span>
              {index === active && <span className="ml-auto text-[10px] font-bold uppercase tracking-widest text-brand">Working</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ProcessingErrorView({ message, onRetry, onCancel }: { message: string; onRetry: () => void; onCancel: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-danger-soft text-destructive"><WifiOff className="h-9 w-9" /></div>
        <h1 className="mt-8 text-2xl font-semibold tracking-[-.04em]">Couldn't complete the check</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{message}</p>
        <div className="mt-8 flex justify-center gap-3">
          <Button variant="secondary" onClick={onCancel}>Cancel</Button>
          <Button onClick={onRetry}><RefreshCcw className="h-4 w-4" />Try again</Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Result
// ---------------------------------------------------------------------------

function DeclarationRow({ declaration }: { declaration: Declaration }) {
  const statusMap: Record<DeclarationStatus, { label: string; className: string; icon: LucideIcon }> = {
    VERIFIED: { label: "Verified", className: "text-success", icon: Check },
    MISSING: { label: "Missing", className: "text-destructive", icon: XCircle },
    REVIEW: { label: "Review", className: "text-warning", icon: Info },
    EXEMPT: { label: "Exempt", className: "text-brand", icon: ShieldCheck },
  };
  const [expanded, setExpanded] = useState(false);
  const item = statusMap[declaration.status];
  const Icon = item.icon;
  return (
    <div className="border-b border-border/70 py-4 last:border-0">
      <button type="button" onClick={() => setExpanded((v) => !v)} className="grid w-full grid-cols-[1fr_auto] items-center gap-4 text-left sm:grid-cols-[1.1fr_1fr_auto]">
        <div>
          <p className="text-sm font-semibold">{declaration.field}</p>
          <p className="mt-1 truncate text-xs text-muted-foreground sm:hidden">{declaration.value}</p>
        </div>
        <p className="hidden truncate text-sm text-muted-foreground sm:block">{declaration.value}</p>
        <div className={`flex items-center gap-1.5 text-xs font-semibold ${item.className}`}>
          <Icon className="h-4 w-4" />{item.label}
          <span className="hidden text-[10px] text-muted-foreground sm:inline">{declaration.confidence}%</span>
          <ChevronRight className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`} />
        </div>
      </button>
      {expanded && (
        <div className="mt-3 rounded-lg bg-muted p-3 text-xs leading-5 text-muted-foreground">
          <p>{declaration.reason || "No further detail available for this field."}</p>
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
          <div key={i} className="flex items-center justify-between rounded-xl bg-muted p-4 text-sm">
            <span className="font-medium">Similar to {m.productId}</span>
            <span className="text-xs font-semibold text-muted-foreground">{(m.score * 100).toFixed(0)}% match</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function ResultView({
  inspection,
  onSave,
  onOpenEvidence,
  onOpenReport,
  onNew,
}: {
  inspection: Inspection;
  onSave: () => void;
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
            <div className="flex h-24 w-24 shrink-0 flex-col items-center justify-center rounded-full bg-card">
              <span className={`text-2xl font-semibold ${style.text}`}>{inspection.score}%</span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Score</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 border-t border-current/10 bg-card/50 p-5 sm:grid-cols-4">
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Product</p><p className="mt-1 text-sm font-semibold">{inspection.product}</p></div>
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Inspection</p><p className="mt-1 text-sm font-semibold">#{inspection.id}</p></div>
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Checked</p><p className="mt-1 text-sm font-semibold">{verified} / {total}</p></div>
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Time</p><p className="mt-1 text-sm font-semibold">{inspection.dateLabel}</p></div>
          </div>
        </section>

        <DisclaimerBanner text={inspection.disclaimer} />

        <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
          <div className="flex items-end justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Declarations</p>
              <h3 className="mt-2 text-xl font-semibold tracking-[-.035em]">Extracted information</h3>
            </div>
            <span className="text-sm font-semibold text-muted-foreground">{verified}/{total} verified</span>
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

        <div className="grid gap-3 sm:grid-cols-3">
          <Button onClick={onSave} variant={inspection.saved ? "secondary" : "primary"} disabled={inspection.saved}><BadgeCheck className="h-4 w-4" />{inspection.saved ? "Saved to register" : "Save inspection"}</Button>
          <Button onClick={onOpenEvidence} variant="secondary"><ScanLine className="h-4 w-4" />View evidence</Button>
          <Button onClick={onOpenReport} variant="secondary"><FileText className="h-4 w-4" />Report preview</Button>
        </div>
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// Evidence viewer — real pixel-bbox to percent conversion
// ---------------------------------------------------------------------------

function EvidenceView({ inspection, onBack }: { inspection: Inspection; onBack: () => void }) {
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
                    <span className="absolute -top-6 left-0 whitespace-nowrap rounded bg-brand px-1.5 py-1 text-[9px] font-bold text-brand-foreground">{region.label} · {region.confidence}%</span>
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

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------

function ReportView({ inspection, onBack }: { inspection: Inspection; onBack: () => void }) {
  const [pdfState, setPdfState] = useState<"idle" | "checking" | "available" | "unavailable">("idle");

  async function handleDownload() {
    setPdfState("checking");
    const available = await reportPdfAvailable(inspection.id);
    if (available) {
      window.open(reportPdfUrl(inspection.id), "_blank");
      setPdfState("available");
    } else {
      setPdfState("unavailable");
    }
  }

  return (
    <>
      <AppHeader title="Report preview" />
      <main className="mx-auto max-w-4xl space-y-5 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <div className="flex items-center justify-between">
          <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Back to result</button>
          <Button variant="secondary" onClick={handleDownload} disabled={pdfState === "checking"}>
            <Download className="h-4 w-4" />
            {pdfState === "checking" ? "Checking…" : pdfState === "available" ? "Opened" : "Download report"}
          </Button>
        </div>
        {pdfState === "unavailable" && (
          <ErrorBanner message="PDF generation isn't available on this backend yet — showing the on-screen preview only." />
        )}
        <article className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-10">
          <div className="flex flex-col justify-between gap-6 border-b border-border pb-7 sm:flex-row">
            <div>
              <div className="flex items-center gap-2 text-brand"><FileCheck2 className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[.18em]">Legal metrology</span></div>
              <h2 className="mt-3 text-3xl font-semibold tracking-[-.05em]">Inspection report</h2>
              <p className="mt-2 text-sm text-muted-foreground">Generated by THE INSPECTORS · SIH 2026</p>
            </div>
            <StatusBadge status={inspection.status} />
          </div>
          <div className="grid gap-5 border-b border-border py-7 sm:grid-cols-3">
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Product</p><p className="mt-2 text-sm font-semibold">{inspection.product}</p><p className="mt-1 text-xs text-muted-foreground">{inspection.manufacturer}</p></div>
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Inspection ID</p><p className="mt-2 text-sm font-semibold">#{inspection.id}</p><p className="mt-1 text-xs text-muted-foreground">{formatDate(inspection.timestamp)}</p></div>
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Final score</p><p className="mt-2 text-sm font-semibold">{inspection.score}% · {inspection.declarations.filter((item) => item.status === "VERIFIED" || item.status === "EXEMPT").length}/{inspection.declarations.length} verified</p><p className="mt-1 text-xs text-muted-foreground">Legal Metrology (Packaged Commodities) Rules, 2011</p></div>
          </div>
          <div className="py-7">
            <h3 className="text-base font-semibold">Extracted declarations</h3>
            <div className="mt-4 divide-y divide-border">
              {inspection.declarations.map((item) => (
                <div key={item.field} className="flex items-center justify-between py-3 text-sm">
                  <div>
                    <span>{item.field}</span>
                    {item.ruleId && <span className="ml-2 text-[10px] font-semibold text-muted-foreground">{item.ruleId}</span>}
                  </div>
                  <span className={item.status === "VERIFIED" || item.status === "EXEMPT" ? "font-semibold text-success" : item.status === "MISSING" ? "font-semibold text-destructive" : "font-semibold text-warning"}>{item.value}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-xl bg-muted p-5">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Reviewer recommendation</p>
            <p className="mt-2 text-sm leading-6">
              {inspection.status === "COMPLIANT" ? "Record may be added to the compliance register after officer confirmation." :
               inspection.status === "VIOLATION" ? "Issue a review notice for missing or incomplete declarations before verification." :
               inspection.status === "EXEMPT" ? "No further action required under these rules; confirm the exemption basis if challenged." :
               "Review the original evidence and request a clearer package image before deciding."}
            </p>
          </div>
          <p className="mt-6 text-xs leading-5 text-muted-foreground">{inspection.disclaimer}</p>
        </article>
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// Login — every endpoint but /health requires a Bearer token on this backend
// ---------------------------------------------------------------------------

function LoginView({ onLoggedIn }: { onLoggedIn: (user: AuthedUser) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(undefined);
    try {
      const user = await login(username.trim(), password);
      onLoggedIn(user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm rounded-2xl border border-border/70 bg-card p-7 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground"><ScanLine className="h-5 w-5" /></div>
          <div>
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">THE INSPECTORS</p>
            <h1 className="text-lg font-semibold tracking-[-.03em]">Sign in</h1>
          </div>
        </div>
        <p className="mt-4 text-sm text-muted-foreground">Every inspection action on this backend requires an authenticated inspector, reviewer, or admin account.</p>
        <div className="mt-6 space-y-4">
          <div>
            <label className="text-xs font-semibold text-muted-foreground">Username</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15" />
          </div>
          <div>
            <label className="text-xs font-semibold text-muted-foreground">Password</label>
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15" />
          </div>
        </div>
        {error && <div className="mt-4 flex items-center gap-2 rounded-lg bg-danger-soft px-3 py-2 text-xs text-destructive"><AlertTriangle className="h-4 w-4 shrink-0" />{error}</div>}
        <Button type="submit" className="mt-6 w-full" disabled={submitting || !username || !password}>
          {submitting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
        <p className="mt-4 text-center text-xs text-muted-foreground">No account yet? The first registration on a fresh database becomes admin — use your backend's <code>/auth/register</code> endpoint directly.</p>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Profile — real backend health
// ---------------------------------------------------------------------------

function ProfileView({ user, onLogout }: { user: AuthedUser | null; onLogout: () => void }) {
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");
  useEffect(() => {
    let cancelled = false;
    checkHealth().then((result) => { if (!cancelled) setHealth(result ? "ok" : "down"); });
    return () => { cancelled = true; };
  }, []);

  const systemRows: Array<[LucideIcon, string, string, "ok" | "checking" | "down"]> = [
    [ScanLine, "Inspection engine", health === "ok" ? "Connected · live" : health === "checking" ? "Checking…" : "Unreachable", health],
    [Sparkles, "OCR extraction", "Tesseract + rule-based classification", "ok"],
    [ShieldCheck, "Evidence storage", "Original images retained server-side per inspection", "ok"],
  ];

  return (
    <>
      <AppHeader title="Inspector profile" />
      <main className="mx-auto max-w-3xl space-y-5 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <section className="flex items-center gap-4 rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground"><UserRound className="h-7 w-7" /></div>
          <div>
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">{user?.role || "Inspector"}</p>
            <h2 className="mt-1 text-xl font-semibold">{user?.username || "Signed out"}</h2>
            <p className="mt-1 text-sm text-muted-foreground">Legal Metrology unit</p>
          </div>
          <BadgeCheck className="ml-auto h-5 w-5 text-success" />
        </section>
        <section className="rounded-2xl border border-border/70 bg-card">
          <div className="border-b border-border p-5">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Workspace</p>
            <h3 className="mt-2 text-xl font-semibold">System status</h3>
          </div>
          <div className="divide-y divide-border">
            {systemRows.map(([Icon, label, value, state]) => (
              <div key={label} className="flex items-center gap-3 p-5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-muted text-brand"><Icon className="h-4 w-4" /></div>
                <div className="flex-1"><p className="text-sm font-semibold">{label}</p><p className="mt-1 text-xs text-muted-foreground">{value}</p></div>
                <span className={`h-2 w-2 rounded-full ${state === "ok" ? "bg-success" : state === "checking" ? "bg-warning" : "bg-destructive"}`} />
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-2xl border border-border/70 bg-card">
          <div className="border-b border-border p-5">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Preferences</p>
            <h3 className="mt-2 text-xl font-semibold">Settings</h3>
          </div>
          {([[Bell, "Notifications", "Inspection reminders"], [Settings2, "Language", "English (India)"], [CircleHelp, "Help & feedback", "Product guidance"]] as Array<[LucideIcon, string, string]>).map(([Icon, label, value]) => (
            <button type="button" key={label} className="flex w-full items-center gap-3 border-b border-border p-5 text-left last:border-0 hover:bg-muted/50">
              <Icon className="h-5 w-5 text-muted-foreground" />
              <div className="flex-1"><p className="text-sm font-semibold">{label}</p><p className="mt-1 text-xs text-muted-foreground">{value}</p></div>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </button>
          ))}
        </section>
        <Button variant="secondary" className="w-full" onClick={onLogout}><LogOut className="h-4 w-4" />Sign out</Button>
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

export function InspectionApp() {
  const [user, setUser] = useState<AuthedUser | null>(() => (getStoredToken() ? getStoredUser() : null));
  const [view, setView] = useState<View>("home");
  const [inspections, setInspections] = useState<Inspection[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | undefined>(undefined);
  const [selected, setSelected] = useState<Inspection | undefined>(undefined);
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const [processingError, setProcessingError] = useState<string | undefined>(undefined);
  const [toast, setToast] = useState<string | undefined>(undefined);

  function handleAuthExpiry(err: unknown): boolean {
    if (err instanceof ApiError && err.status === 401) {
      setUser(null);
      return true;
    }
    return false;
  }

  async function refreshInspections() {
    setListLoading(true);
    setListError(undefined);
    try {
      const rows = await listInspections({ limit: 100 });
      setInspections(rows.map(fromInspectionRow));
    } catch (err) {
      if (handleAuthExpiry(err)) return;
      setListError(err instanceof ApiError ? err.message : "Could not load inspections.");
    } finally {
      setListLoading(false);
    }
  }

  useEffect(() => { if (user) refreshInspections(); }, [user]);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(undefined), 2600);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  function go(nextView: View) {
    setView(nextView);
    if (!["result", "detail", "evidence", "report"].includes(nextView)) setSelected(undefined);
    if (nextView === "scan") setPendingImages([]);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function handleOpen(inspection: Inspection) {
    setSelected(inspection);
    setView("detail");
    // Refresh full detail in the background — list rows may be summaries.
    getInspectionDetail(inspection.id)
      .then((row) => setSelected(fromInspectionRow(row)))
      .catch((err) => { handleAuthExpiry(err); /* otherwise keep the summary version */ });
  }

  function onCaptured(images: string[]) { setPendingImages(images); setView("scanDetails"); }

  const pendingRunRef = useRef<() => Promise<Inspection>>(() => Promise.reject(new Error("no scan queued")));

  /** Real multi-surface capture: open a session, upload every captured photo
   * as its own surface (first = FRONT, second = BACK, rest = SIDE — a
   * reasonable default given the capture screen's own guidance text), then
   * finalize once so the legal engine runs against the UNION of all photos
   * instead of just the first one. Replaces the earlier client-side-only
   * "extra photos are just kept as supplementary evidence" workaround, now
   * that the backend actually has a session endpoint for this. */
  async function runScanSession(details: ScanDetails): Promise<Inspection> {
    const session = await createSession({
      productId: details.productId,
      saleType: details.saleType,
      productCategory: details.productCategory,
      netQuantityValue: details.netQuantityValue,
      netQuantityUnit: details.netQuantityUnit,
      mrp: details.mrp,
      pdpAreaCm2: details.pdpAreaCm2,
      isExportOnly: details.isExportOnly,
      retailBundleCount: details.retailBundleCount,
      isImported: details.isImported,
    });

    const surfaceForIndex = (i: number): SurfaceType => (i === 0 ? "FRONT" : i === 1 ? "BACK" : "SIDE");
    for (let i = 0; i < pendingImages.length; i++) {
      const blob = dataUrlToBlob(pendingImages[i]);
      await addSessionCapture(session.session_id, blob, surfaceForIndex(i));
    }

    const inspection = await finalizeSession(session.session_id);
    return fromFinalizedInspection(inspection, { productId: details.productId }, pendingImages[0]);
  }

  function submitDetails(details: ScanDetails) {
    setProcessingError(undefined);
    setView("processing");
    pendingRunRef.current = () => runScanSession(details);
  }

  function handleProcessingDone(inspection: Inspection) {
    setSelected(inspection);
    setInspections((current) => [inspection, ...current]);
    setView("result");
  }

  function handleProcessingError(message: string) {
    setProcessingError(message);
  }

  async function saveAndRegister() {
    if (!selected) return;
    try {
      await markReviewed(selected.id, "Saved to compliance register by inspector.");
      const saved = { ...selected, saved: true, reviewed: true };
      setSelected(saved);
      setInspections((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      setToast("Added to Compliance Register");
    } catch (err) {
      if (handleAuthExpiry(err)) return;
      setToast(err instanceof ApiError ? err.message : "Could not save — check your connection.");
    }
  }

  function handleLogout() {
    clearSession();
    setUser(null);
    setInspections([]);
    setView("home");
  }

  if (!user) {
    return <LoginView onLoggedIn={setUser} />;
  }

  const content =
    view === "home" ? (
      <HomeView inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onNavigate={go} onOpen={handleOpen} />
    ) : view === "history" ? (
      <ListView kind="history" inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onOpen={handleOpen} onNavigate={go} />
    ) : view === "register" ? (
      <ListView kind="register" inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onOpen={handleOpen} onNavigate={go} />
    ) : view === "reviewQueue" ? (
      <ReviewQueueView inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onOpen={handleOpen} onNavigate={go} />
    ) : view === "profile" ? (
      <ProfileView user={user} onLogout={handleLogout} />
    ) : view === "scan" ? (
      <ScanView onCaptured={onCaptured} onBack={() => go("home")} />
    ) : view === "scanDetails" ? (
      <ScanDetailsView images={pendingImages} onSubmit={submitDetails} onBack={() => go("scan")} />
    ) : view === "processing" ? (
      processingError ? (
        <ProcessingErrorView message={processingError} onRetry={() => setProcessingError(undefined)} onCancel={() => go("home")} />
      ) : (
        <ProcessingRunner onRun={() => pendingRunRef.current()} onDone={handleProcessingDone} onError={handleProcessingError} />
      )
    ) : selected && (view === "result" || view === "detail") ? (
      <ResultView inspection={selected} onSave={saveAndRegister} onOpenEvidence={() => go("evidence")} onOpenReport={() => go("report")} onNew={() => go("scan")} />
    ) : selected && view === "evidence" ? (
      <EvidenceView inspection={selected} onBack={() => go("result")} />
    ) : selected && view === "report" ? (
      <ReportView inspection={selected} onBack={() => go("result")} />
    ) : (
      <HomeView inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onNavigate={go} onOpen={handleOpen} />
    );

  const inFocusedFlow = ["scan", "scanDetails", "processing"].includes(view);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {!inFocusedFlow && <DesktopRail view={view} onNavigate={go} />}
      {!inFocusedFlow && <div className="md:pl-64">{content}</div>}
      {inFocusedFlow && content}
      {!inFocusedFlow && <BottomNav view={view} onNavigate={go} />}
      {toast && (
        <div className="fixed bottom-24 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-xl md:bottom-8">
          <Check className="h-4 w-4 text-success" />{toast}
        </div>
      )}
    </div>
  );
}
