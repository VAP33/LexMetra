import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Bell,
  Camera,
  CameraOff,
  Check,
  ChevronDown,
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
  type SurfaceEvidence,
} from "@/lib/types";
import {
  ApiError,
  addSessionCapture,
  checkHealth,
  clearSession,
  createSession,
  extractPreview,
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
  type ExtractPreviewResponse,
  type SurfaceType,
  preprocessParallel,
  resolveImageUrl,
} from "@/lib/api-client";
import { fromFinalizedInspection, fromInspectionRow } from "@/lib/adapters";
import { dataUrlToBlob } from "@/lib/data-url";
import { TeslaScannerAnimation } from "./TeslaScannerAnimation";
import { BeforeAfterSlider } from "./BeforeAfterSlider";
import { RegulatoryIntelligenceDashboard } from "./RegulatoryIntelligenceDashboard";

type View =
  | "home"
  | "history"
  | "register"
  | "reviewQueue"
  | "profile"
  | "scan"
  | "preprocessing"
  | "scanDetails"
  | "processing"
  | "result"
  | "detail"
  | "evidence"
  | "report"
  | "regulatory";

const navItems: Array<{ label: string; view: View; icon: LucideIcon }> = [
  { label: "Home", view: "home", icon: LayoutDashboard },
  { label: "History", view: "history", icon: HistoryIcon },
  { label: "Register", view: "register", icon: ClipboardCheck },
  { label: "Review", view: "reviewQueue", icon: ShieldAlert },
  { label: "Rules", view: "regulatory", icon: FileText },
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

function ErrorBanner({ message, onRetry, onLogout }: { message: string; onRetry?: () => void; onLogout?: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-destructive/25 bg-danger-soft p-4 text-sm">
      <AlertTriangle className="h-5 w-5 shrink-0 text-destructive" />
      <p className="flex-1 text-destructive">{message}</p>
      {onRetry && <Button variant="secondary" onClick={onRetry}><RefreshCcw className="h-4 w-4" />Retry</Button>}
      {onLogout && <Button variant="secondary" onClick={onLogout}><LogOut className="h-4 w-4" />Sign in</Button>}
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
    setCaptured((current) => {
      if (current.length >= 3) return current;
      return [...current, dataUrl];
    });
  }

  function capture() {
    if (!cameraActive || !videoRef.current || captured.length >= 3) return;
    const video = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 800;
    canvas.height = video.videoHeight || 1000;
    canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
    addImage(canvas.toDataURL("image/jpeg", 0.85));
  }

  function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    if (captured.length >= 3) return;
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
            <h1 className="mt-1 text-lg font-semibold">Scan product ({captured.length}/3 faces)</h1>
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
            Capture up to 3 package faces (Face 1, Face 2, Face 3) for the same commodity.
            All faces belong to the package and are analyzed together by multimodal perception.
          </p>
          {captured.length >= 3 && (
            <p className="mx-auto mt-2 text-center text-xs font-semibold text-brand">
              Maximum 3 faces reached. Ready to continue to inspection.
            </p>
          )}
          {cameraError && <div className="mx-auto mt-3 flex items-center gap-2 rounded-lg bg-warning/20 px-3 py-2 text-xs text-warning"><CameraOff className="h-4 w-4" />Camera unavailable — use gallery instead.</div>}

          {captured.length > 0 && (
            <div className="mx-auto mt-6 flex max-w-md gap-3 overflow-x-auto hide-scrollbar">
              {captured.map((img, index) => (
                <div key={index} className="relative h-20 w-16 shrink-0 overflow-hidden rounded-lg border border-primary-foreground/20">
                  <img src={img} alt={`Face ${index + 1}`} className="h-full w-full object-cover" />
                  <span className="absolute left-1 top-1 rounded bg-primary-foreground/90 px-1 text-[9px] font-bold text-primary">Face {index + 1}</span>
                  <button type="button" onClick={() => removeAt(index)} aria-label="Remove photo" className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-black/50"><X className="h-2.5 w-2.5" /></button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-end justify-between gap-5">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={captured.length >= 3}
            className="flex w-24 flex-col items-center gap-2 text-xs font-semibold text-primary-foreground/70 disabled:opacity-40"
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-foreground/10"><ImageIcon className="h-5 w-5" /></span>Gallery
          </button>
          <button
            type="button"
            onClick={capture}
            aria-label="Capture inspection image"
            disabled={!cameraActive || captured.length >= 3}
            className="flex h-20 w-20 items-center justify-center rounded-full border-[6px] border-primary-foreground/20 bg-primary-foreground text-primary transition-transform active:scale-95 disabled:opacity-40"
          >
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

  const [extracting, setExtracting] = useState(true);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<ExtractPreviewResponse | null>(null);
  const [showDetectedDeclarations, setShowDetectedDeclarations] = useState(false);
  const lastExtractedKeyRef = useRef<string>("");

  useEffect(() => {
    let cancelled = false;
    async function runPreview() {
      if (!images.length) {
        setExtracting(false);
        return;
      }
      // Deduplicate by face-set signature to prevent duplicate requests from React re-renders
      const requestKey = images.map((img, i) => `f${i}:${img.length}:${img.slice(0, 50)}`).join("|");
      if (lastExtractedKeyRef.current === requestKey && previewData) {
        setExtracting(false);
        return;
      }
      lastExtractedKeyRef.current = requestKey;

      try {
        setExtracting(true);
        setExtractError(null);
        const blobs = await Promise.all(
          images.map(async (img) => {
            if (img.startsWith("data:") || img.startsWith("blob:")) {
              return dataUrlToBlob(img);
            }
            const fullUrl = resolveImageUrl(img) || img;
            const fetched = await fetch(fullUrl);
            return await fetched.blob();
          })
        );
        const res = await extractPreview(blobs);
        if (cancelled) return;
        setPreviewData(res);

        if (res.suggested_details.product_id) {
          setProductId(res.suggested_details.product_id);
        }
        if (res.suggested_details.sale_type) {
          setSaleType(res.suggested_details.sale_type);
        }
        if (res.suggested_details.category && CATEGORY_OPTIONS.includes(res.suggested_details.category)) {
          setCategory(res.suggested_details.category);
        }
        if (res.suggested_details.net_quantity_value != null) {
          setQtyValue(String(res.suggested_details.net_quantity_value));
        }
        if (res.suggested_details.net_quantity_unit && UNIT_OPTIONS.includes(res.suggested_details.net_quantity_unit.toLowerCase())) {
          setQtyUnit(res.suggested_details.net_quantity_unit.toLowerCase());
        }
        if (res.suggested_details.mrp != null) {
          setMrp(String(res.suggested_details.mrp));
        }
      } catch (err) {
        if (cancelled) return;
        setExtractError(err instanceof Error ? err.message : "OCR preview unavailable");
      } finally {
        if (!cancelled) setExtracting(false);
      }
    }
    runPreview();
    return () => {
      cancelled = true;
    };
  }, [images]);

  const effectiveProductId = productId.trim() || previewData?.suggested_details?.product_id || "";
  const effectiveQty = Number(qtyValue) > 0 ? Number(qtyValue) : (previewData?.suggested_details?.net_quantity_value ?? undefined);
  const effectiveQtyUnit = qtyUnit || previewData?.suggested_details?.net_quantity_unit || undefined;
  const valid = true;

  const detectedDeclarationsList = useMemo(() => {
    if (!previewData?.field_extractions) return [];
    return Object.entries(previewData.field_extractions)
      .filter(([_, data]) => data && data.detected && data.value)
      .map(([field, data]) => ({
        field: field.replace(/_/g, " "),
        value: data.value,
        confidence: Math.round((data.confidence ?? 0) * 100),
        source: data.source_image,
      }));
  }, [previewData]);

  return (
    <>
      <AppHeader title="Confirm details" />
      <main className="mx-auto max-w-2xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />Retake photos
        </button>

        <section className="flex gap-3 overflow-x-auto rounded-2xl border border-border/70 bg-card p-4 hide-scrollbar">
          {images.map((img, i) => (
            <div key={i} className="relative h-24 w-20 shrink-0 overflow-hidden rounded-xl border border-border">
              <img src={resolveImageUrl(img) || img} alt={`Face ${i + 1}`} className="h-full w-full object-cover" />
              <span className="absolute left-1 top-1 rounded bg-primary/90 px-1.5 py-0.5 text-[9px] font-bold text-primary-foreground">
                Face {i + 1}
              </span>
            </div>
          ))}
        </section>

        {extracting ? (
          <div className="flex items-center gap-3 rounded-2xl border border-brand/25 bg-brand/5 p-4 text-xs text-brand">
            <LoaderCircle className="h-5 w-5 animate-spin shrink-0 text-brand" />
            <div>
              <p className="font-semibold text-sm">Reading mandatory declarations from label...</p>
              <p className="text-muted-foreground mt-0.5">Auto-extracting SKU, net quantity, MRP, and product category</p>
            </div>
          </div>
        ) : previewData ? (
          <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-4 text-xs text-emerald-800 dark:text-emerald-300">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Sparkles className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <div>
                  <p className="font-semibold text-sm">Details auto-filled from package photo</p>
                  <p className="text-muted-foreground mt-0.5">
                    {previewData.total_lines} text lines analyzed • Review and confirm below
                  </p>
                </div>
              </div>
              {detectedDeclarationsList.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowDetectedDeclarations((v) => !v)}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
                >
                  {showDetectedDeclarations ? "Hide declarations" : `${detectedDeclarationsList.length} detected`}
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showDetectedDeclarations ? "rotate-180" : ""}`} />
                </button>
              )}
            </div>

            {showDetectedDeclarations && (
              <div className="mt-4 pt-3 border-t border-emerald-500/15 space-y-2">
                <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Detected Declarations</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {detectedDeclarationsList.map((item) => (
                    <div key={item.field} className="rounded-xl border border-border/70 bg-card p-2.5 text-foreground">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground capitalize truncate">{item.field}</span>
                        <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">{item.confidence}%</span>
                      </div>
                      <p className="text-xs font-medium mt-1 truncate" title={item.value ?? ""}>{item.value}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : extractError ? (
          <div className="flex items-center gap-2.5 rounded-2xl border border-border/70 bg-muted/40 p-3.5 text-xs text-muted-foreground">
            <Info className="h-4 w-4 shrink-0" />
            <span>AI OCR preview unavailable ({extractError}). Please confirm details manually.</span>
          </div>
        ) : null}

        <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
          <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Before we run the checks</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-.035em]">Confirm details</h2>
          <p className="mt-1 text-sm text-muted-foreground">Pre-filled from package perception. Adjust if needed or proceed directly.</p>

          <div className="mt-6 space-y-5">
            <div>
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-muted-foreground">Product Name</label>
                {previewData?.field_extractions?.common_name?.value ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <BadgeCheck className="h-3 w-3" /> Detected from label
                  </span>
                ) : null}
              </div>
              <div className="mt-1.5 flex h-11 w-full items-center rounded-xl border border-border/80 bg-muted/30 px-3 text-sm font-medium text-foreground">
                {previewData?.field_extractions?.common_name?.value || "Not detected"}
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-muted-foreground">Product ID / SKU</label>
                {previewData?.suggested_details?.product_id_source === "unidentified-placeholder" || previewData?.suggested_details?.needs_manual_entry || !previewData?.suggested_details?.product_id ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                    <AlertTriangle className="h-3 w-3" /> Not detected on label
                  </span>
                ) : previewData?.suggested_details?.product_id_source?.startsWith("barcode") ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <BadgeCheck className="h-3 w-3" /> Decoded Barcode ({previewData.suggested_details.barcode_info?.primary_symbology || "EAN-13"})
                  </span>
                ) : previewData?.suggested_details?.product_id ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <Sparkles className="h-3 w-3" /> Detected on label
                  </span>
                ) : null}
              </div>
              <input
                value={productId}
                onChange={(e) => setProductId(e.target.value)}
                placeholder="Not detected (optional/manual entry)"
                className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
              />
              {(!productId.trim() && (!previewData?.suggested_details?.product_id || previewData?.suggested_details?.needs_manual_entry)) && (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  No printed Product ID / Barcode was detected on the package label.
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Sale type</label>
                <select
                  value={saleType}
                  onChange={(e) => setSaleType(e.target.value as ScanDetails["saleType"])}
                  className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                >
                  <option value="retail">Retail</option>
                  <option value="wholesale">Wholesale</option>
                  <option value="industrial">Industrial</option>
                  <option value="institutional">Institutional</option>
                </select>
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-muted-foreground">Category</label>
                  {previewData?.suggested_details?.category && (
                    <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400">Inferred</span>
                  )}
                </div>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                >
                  {CATEGORY_OPTIONS.map((c) => (
                    <option key={c} value={c}>
                      {c.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-[1fr_auto] gap-3">
              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-muted-foreground">Net quantity</label>
                  {previewData?.suggested_details?.net_quantity_value != null ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                      <Sparkles className="h-3 w-3" /> Auto-detected
                    </span>
                  ) : (
                    <span className="text-[11px] text-amber-600 dark:text-amber-400">Not reliably observed yet</span>
                  )}
                </div>
                <input
                  value={qtyValue}
                  onChange={(e) => setQtyValue(e.target.value)}
                  type="number"
                  placeholder="30"
                  className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Unit</label>
                <select
                  value={qtyUnit}
                  onChange={(e) => setQtyUnit(e.target.value)}
                  className="mt-1.5 h-11 rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                >
                  {UNIT_OPTIONS.map((u) => (
                    <option key={u} value={u}>
                      {u}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-muted-foreground">MRP (₹) — optional</label>
                {previewData?.suggested_details?.mrp != null && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <Sparkles className="h-3 w-3" /> Auto-detected
                  </span>
                )}
              </div>
              <input
                value={mrp}
                onChange={(e) => setMrp(e.target.value)}
                type="number"
                placeholder="470"
                className="mt-1.5 h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
              />
            </div>

            {previewData?.suggested_details?.pdp_area_cm2 != null && (
              <div className="flex items-center justify-between rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3.5 py-2.5 text-xs">
                <span className="font-medium text-muted-foreground flex items-center gap-1.5">
                  <span className="text-sm">📐</span> Calculated Principal Display Panel (PDP) Area
                </span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                  {previewData.suggested_details.pdp_area_cm2} cm²
                </span>
              </div>
            )}
          </div>
        </section>

        <Button
          className="w-full"
          disabled={!valid}
          onClick={() =>
            onSubmit({
              productId: effectiveProductId,
              saleType,
              productCategory: category,
              ...(effectiveQty !== undefined ? { netQuantityValue: effectiveQty } : {}),
              ...(effectiveQtyUnit ? { netQuantityUnit: effectiveQtyUnit } : {}),
              mrp: mrp ? Number(mrp) : (previewData?.suggested_details?.mrp ?? undefined),
              pdpAreaCm2: previewData?.suggested_details?.pdp_area_cm2 ?? undefined,
            })
          }
        >
          Run compliance check<ArrowRight className="h-4 w-4" />
        </Button>
      </main>
    </>
  );
}

function PreprocessingRunner({
  images,
  onDone,
  onError,
}: {
  images: string[];
  onDone: (canonicalUrls: string[]) => void;
  onError: (msg: string) => void;
}) {
  const [stageIdx, setStageIdx] = useState(0);
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    // Step through the 5 CV normalization stages
    const interval = window.setInterval(() => {
      setStageIdx((value) => Math.min(value + 1, 4));
    }, 600);

    const minDisplay = new Promise((resolve) => window.setTimeout(resolve, 1400));

    const executePreprocessing = async (): Promise<string[]> => {
      if (!images || images.length === 0) return [];
      const blobs = images.map(dataUrlToBlob);
      const res = await preprocessParallel(blobs);
      if (res && res.faces) {
        const canonicalUrls = Object.values(res.faces)
          .map((f) => f.canonical_image_url)
          .filter(Boolean);
        if (canonicalUrls.length > 0) {
          return canonicalUrls;
        }
      }
      return images;
    };

    Promise.all([executePreprocessing(), minDisplay])
      .then(([canonicalUrls]) => {
        window.clearInterval(interval);
        setStageIdx(4);
        window.setTimeout(() => onDone(canonicalUrls), 350);
      })
      .catch((err: unknown) => {
        window.clearInterval(interval);
        const message = err instanceof ApiError ? err.message : (err instanceof Error ? err.message : "Preprocessing failed.");
        onError(message);
      });

    return () => window.clearInterval(interval);
  }, [images, onDone, onError]);

  return (
    <div className="min-h-screen bg-white">
      <TeslaScannerAnimation stageIndex={stageIdx} />
    </div>
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
  const [stageIdx, setStageIdx] = useState(0);
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    // Advance truthful stages as progress unfolds
    const interval = window.setInterval(() => {
      setStageIdx((value) => Math.min(value + 1, 4));
    }, 700);

    const minDisplay = new Promise((resolve) => window.setTimeout(resolve, 1500));

    Promise.all([onRun(), minDisplay])
      .then(([inspection]) => {
        window.clearInterval(interval);
        setStageIdx(4);
        window.setTimeout(() => onDone(inspection), 300);
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
    <div className="min-h-screen bg-white">
      <TeslaScannerAnimation stageIndex={stageIdx} />
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
    MISSING: { label: "Not detected", className: "text-destructive", icon: XCircle },
    REVIEW: { label: "Review", className: "text-warning", icon: Info },
    EXEMPT: { label: "Exempt", className: "text-brand", icon: ShieldCheck },
    UNOBSERVED: { label: "Not detected", className: "text-muted-foreground", icon: CircleHelp },
  };
  const [expanded, setExpanded] = useState(false);
  const item = statusMap[declaration.status] || statusMap.REVIEW;
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
          <ChevronRight className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`} />
        </div>
      </button>
      {expanded && (
        <div className="mt-3 rounded-lg bg-muted p-3 text-xs leading-5 text-muted-foreground">
          <p className="font-medium text-foreground">{declaration.reason || "No further detail available for this field."}</p>

          <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-4 rounded-md bg-card p-2 border border-border/50 text-[11px]">
            <div>
              <span className="text-muted-foreground block text-[10px] uppercase font-bold">Rule / Provision</span>
              <span className="font-semibold text-foreground font-mono">{declaration.ruleId || "LMPC-2011"}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[10px] uppercase font-bold">Ruleset Version</span>
              <span className="font-semibold text-foreground font-mono">{declaration.ruleVersion || "2011-consolidated"}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[10px] uppercase font-bold">Applicability</span>
              <span className="font-semibold text-foreground">{declaration.applicabilityStatus || (declaration.status === "EXEMPT" ? "EXEMPTED" : "APPLICABLE")}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[10px] uppercase font-bold">Compliance Status</span>
              <span className={`font-semibold ${declaration.status === "VERIFIED" ? "text-emerald-500" : declaration.status === "EXEMPT" ? "text-blue-400" : "text-amber-500"}`}>
                {declaration.complianceStatus || (declaration.status === "VERIFIED" ? "PASS" : declaration.status === "EXEMPT" ? "EXEMPTED" : "REVIEW")}
              </span>
            </div>
          </div>

          {declaration.canonicalPolygonPx && (
            <p className="mt-2 inline-flex items-center gap-1.5 font-medium text-emerald-500 text-[11px]">
              <Check className="h-3.5 w-3.5" /> Tight text polygon localized from PaddleOCR
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
            <div className="flex shrink-0 items-center gap-3">
              {/* A FRACTION, NOT A PERCENTAGE, AND DELIBERATELY SO.
                  Two failure modes were rejected here. Showing verified-of-all
                  as "11%" made a correct single-panel capture (1 field read, 8
                  never visible in frame) look like a failing product. Showing
                  verified-of-judgeable instead reported that same capture as
                  "100%", which is worse -- it reads as "fully compliant" when
                  8 checks never ran. A fraction carries its own denominator, so
                  neither misreading is available. */}
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
              {/* When most checks could not be assessed, say so in words. The
                  fraction alone still invites "1/9 = bad product" when the
                  correct reading is "this frame did not show 8 of the panels". */}
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
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Product Name</p><p className="mt-1 text-sm font-semibold">{inspection.product || "Not detected"}</p></div>
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Product ID</p><p className="mt-1 text-sm font-semibold">{inspection.productId || "Not detected"}</p></div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Checked</p>
              <p className="mt-1 text-sm font-semibold">
                {inspection.declarationSummary ? `${inspection.declarationSummary.verified} / ${inspection.declarationSummary.applicable}` : `${verified} / ${total}`}
                {inspection.pdpAreaCm2 ? ` · ${inspection.pdpAreaCm2} cm² PDP` : ""}
              </p>
            </div>
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Inspection</p><p className="mt-1 text-sm font-semibold">#{inspection.id}</p></div>
          </div>
        </section>

        <DisclaimerBanner text={inspection.disclaimer} />

        <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7">
          <div className="flex items-end justify-between">
            <div>
              <div className="flex items-center gap-2">
                <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Declarations</p>
                <span className="rounded-full bg-brand/10 border border-brand/20 px-2 py-0.5 text-[10px] font-mono font-bold text-brand">
                  Ruleset: {inspection.declarations[0]?.ruleVersion || "IN-LMPC-2011:2011-consolidated"}
                </span>
              </div>
              <h3 className="mt-2 text-xl font-semibold tracking-[-.035em]">Extracted information & Regulatory Intelligence</h3>
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

// ---------------------------------------------------------------------------
// Evidence viewer — Multi-surface, bidirectional investigation interface
// (User Requirements 11, 12, 19, 20, 21, 22, 23)
// ---------------------------------------------------------------------------

function getSvgColors(label: string, isSelected: boolean) {
  const l = label.toLowerCase();
  if (l.includes("mrp") || l.includes("retail") || l.includes("price")) {
    return {
      stroke: isSelected ? "#10b981" : "#059669",
      fill: isSelected ? "rgba(16, 185, 129, 0.35)" : "rgba(16, 185, 129, 0.18)",
    };
  }
  if (l.includes("unit") || l.includes("usp")) {
    return {
      stroke: isSelected ? "#06b6d4" : "#0891b2",
      fill: isSelected ? "rgba(6, 182, 212, 0.35)" : "rgba(6, 182, 212, 0.18)",
    };
  }
  if (l.includes("batch") || l.includes("lot")) {
    return {
      stroke: isSelected ? "#6366f1" : "#4f46e5",
      fill: isSelected ? "rgba(99, 102, 241, 0.35)" : "rgba(99, 102, 241, 0.18)",
    };
  }
  if (l.includes("net") || l.includes("qty") || l.includes("volume") || l.includes("weight")) {
    return {
      stroke: isSelected ? "#f59e0b" : "#d97706",
      fill: isSelected ? "rgba(245, 158, 11, 0.35)" : "rgba(245, 158, 11, 0.18)",
    };
  }
  if (l.includes("date") || l.includes("mfd") || l.includes("exp") || l.includes("before")) {
    return {
      stroke: isSelected ? "#a855f7" : "#9333ea",
      fill: isSelected ? "rgba(168, 85, 247, 0.35)" : "rgba(168, 85, 247, 0.18)",
    };
  }
  return {
    stroke: isSelected ? "#3b82f6" : "#2563eb",
    fill: isSelected ? "rgba(59, 130, 246, 0.35)" : "rgba(59, 130, 246, 0.18)",
  };
}

function DynamicEvidenceCrop({
  imageSrc,
  bbox,
  polygon,
  localizationStatus,
  label,
  value,
  confidence,
}: {
  imageSrc: string;
  bbox?: { x: number; y: number; width: number; height: number };
  polygon?: [number, number][];
  localizationStatus?: string;
  label: string;
  value?: string;
  confidence?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [loadError, setLoadError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [cropStats, setCropStats] = useState<{
    cropW: number;
    cropH: number;
    zoomFactor: number;
    naturalW: number;
    naturalH: number;
  } | null>(null);

  useEffect(() => {
    if (!bbox || bbox.width <= 0 || bbox.height <= 0 || !imageSrc) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setLoadError(false);
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      setLoading(false);
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const nw = img.naturalWidth;
      const nh = img.naturalHeight;

      // Add generous padding (40% of dimensions or at least 35-40px)
      const padX = Math.max(bbox.width * 0.4, 40);
      const padY = Math.max(bbox.height * 0.4, 30);

      const cropX = Math.max(0, bbox.x - padX);
      const cropY = Math.max(0, bbox.y - padY);
      const cropRight = Math.min(nw, bbox.x + bbox.width + padX);
      const cropBottom = Math.min(nh, bbox.y + bbox.height + padY);

      const cropW = Math.max(1, cropRight - cropX);
      const cropH = Math.max(1, cropBottom - cropY);

      const targetWidth = 720;
      const aspect = cropH / cropW;
      const targetHeight = Math.max(260, Math.min(Math.round(targetWidth * aspect), 520));

      canvas.width = targetWidth;
      canvas.height = targetHeight;

      // Clear dark background
      ctx.fillStyle = "#09090b";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Fit cropped region inside canvas preserving aspect ratio
      const scale = Math.min(canvas.width / cropW, canvas.height / cropH);
      const renderW = cropW * scale;
      const renderH = cropH * scale;
      const offsetX = (canvas.width - renderW) / 2;
      const offsetY = (canvas.height - renderH) / 2;

      ctx.drawImage(img, cropX, cropY, cropW, cropH, offsetX, offsetY, renderW, renderH);

      // Bounding box within canvas
      const boxCanvasX = offsetX + (bbox.x - cropX) * scale;
      const boxCanvasY = offsetY + (bbox.y - cropY) * scale;
      const boxCanvasW = bbox.width * scale;
      const boxCanvasH = bbox.height * scale;

      // Draw tight polygon if available, else rectangle
      if (polygon && polygon.length >= 3) {
        ctx.beginPath();
        const startX = offsetX + (polygon[0][0] - cropX) * scale;
        const startY = offsetY + (polygon[0][1] - cropY) * scale;
        ctx.moveTo(startX, startY);
        for (let i = 1; i < polygon.length; i++) {
          ctx.lineTo(offsetX + (polygon[i][0] - cropX) * scale, offsetY + (polygon[i][1] - cropY) * scale);
        }
        ctx.closePath();
        ctx.fillStyle = "rgba(16, 185, 129, 0.22)";
        ctx.fill();
        ctx.strokeStyle = "#10b981";
        ctx.lineWidth = 3;
        ctx.stroke();
      } else {
        ctx.fillStyle = "rgba(16, 185, 129, 0.16)";
        ctx.fillRect(boxCanvasX, boxCanvasY, boxCanvasW, boxCanvasH);
        ctx.strokeStyle = "#10b981";
        ctx.lineWidth = 3;
        ctx.strokeRect(boxCanvasX, boxCanvasY, boxCanvasW, boxCanvasH);
      }

      // Badge label
      const badgeText = `${label}${value ? `: ${value}` : ""}${confidence ? ` (${confidence}%)` : ""}`;
      ctx.font = "bold 13px system-ui, -apple-system, sans-serif";
      const textMetrics = ctx.measureText(badgeText);
      const badgeW = textMetrics.width + 16;
      const badgeH = 24;
      const badgeX = Math.max(offsetX, Math.min(boxCanvasX, canvas.width - badgeW - 10));
      const badgeY = Math.max(badgeH + 6, boxCanvasY - 6);

      ctx.fillStyle = "rgba(15, 23, 42, 0.95)";
      ctx.beginPath();
      if (typeof ctx.roundRect === "function") {
        ctx.roundRect(badgeX, badgeY - badgeH, badgeW, badgeH, 6);
      } else {
        ctx.rect(badgeX, badgeY - badgeH, badgeW, badgeH);
      }
      ctx.fill();
      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      ctx.fillStyle = "#34d399";
      ctx.fillText(badgeText, badgeX + 8, badgeY - 7);

      setCropStats({
        cropW: Math.round(cropW),
        cropH: Math.round(cropH),
        zoomFactor: Number(scale.toFixed(1)),
        naturalW: nw,
        naturalH: nh,
      });
    };

    img.onerror = () => {
      setLoading(false);
      setLoadError(true);
    };

    img.src = imageSrc;
  }, [imageSrc, bbox, polygon, label, confidence]);

  if (!bbox || bbox.width <= 0 || bbox.height <= 0) {
    const isAmbiguous = localizationStatus === "AMBIGUOUS_MATCH";
    const isUnavailable = localizationStatus === "LOCALIZER_UNAVAILABLE";
    const heading = isAmbiguous
      ? "Evidence location uncertain"
      : isUnavailable
      ? "Localization service unavailable"
      : "Evidence location unavailable";
    const desc = isAmbiguous
      ? `Multiple candidate text locations detected on this face for "${label}". Coarse fallback box suppressed for statutory precision.`
      : isUnavailable
      ? "The localization engine was unavailable during this scan."
      : `No verified tight text polygon could be localized for "${label}" on this package face. Physical verification is required.`;

    return (
      <div className="flex flex-col items-center justify-center p-8 text-center bg-card rounded-xl border border-warning/30 min-h-[320px]">
        <ShieldAlert className="h-12 w-12 text-warning mb-3 animate-pulse" />
        <h4 className="text-base font-bold text-foreground">{heading}</h4>
        <p className="text-xs text-muted-foreground mt-1.5 max-w-sm">{desc}</p>
        <div className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-warning/10 px-3 py-1 text-[11px] font-semibold text-warning border border-warning/20">
          Status: {localizationStatus || "UNLOCALIZED"}
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center bg-card rounded-xl border border-danger/30 min-h-[320px]">
        <AlertTriangle className="h-10 w-10 text-danger mb-2" />
        <p className="text-sm font-semibold text-foreground">Failed to load evidence crop</p>
        <p className="text-xs text-muted-foreground mt-1">Image resource could not be rendered.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col space-y-2">
      <div className="relative aspect-[4/3] w-full overflow-hidden rounded-xl border border-border/70 bg-neutral-950 flex items-center justify-center">
        {loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-neutral-950/80 z-10 text-xs text-muted-foreground">
            <LoaderCircle className="h-6 w-6 animate-spin text-brand mb-2" />
            Rendering dynamic crop...
          </div>
        )}
        <canvas ref={canvasRef} className="max-h-full max-w-full object-contain rounded-lg" />
      </div>
      {cropStats && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[11px] font-mono text-muted-foreground">
          <span>
            <strong>Dynamic Crop:</strong> {cropStats.cropW}×{cropStats.cropH}px (Source: {cropStats.naturalW}×{cropStats.naturalH}px)
          </span>
          <span>
            <strong>Zoom:</strong> {cropStats.zoomFactor}× Centered
          </span>
        </div>
      )}
    </div>
  );
}

function EvidenceView({ inspection, onBack }: { inspection: Inspection; onBack: () => void }) {
  // Synthesize or use populated surfaces from inspection
  const surfaces: SurfaceEvidence[] = useMemo(() => {
    if (inspection.surfaces && inspection.surfaces.length > 0) {
      return inspection.surfaces;
    }
    return [
      {
        surfaceId: "face_1",
        surfaceType: "Face 1",
        faceLabel: "Face 1",
        priorityScore: 1.0,
        imageUrl: inspection.image,
        canonicalImageUrl: inspection.canonicalImage || inspection.image,
        regions: inspection.evidence,
        transformHistory: [
          "Original Sensor Capture (Raw)",
          "Package Boundary & Object Detection",
          "Perspective Homography H-Matrix",
          "Illumination Normalization",
          "Canonical Surface Normalization",
        ],
        ocrConfidence: inspection.declarations[0]?.ocrConfidence ?? 90,
      },
    ];
  }, [inspection]);

  const [activeSurfaceType, setActiveSurfaceType] = useState<string>(
    surfaces[0]?.surfaceType || "Face 1"
  );

  // Per-face natural image dimensions for zero-distortion bounding boxes
  const [faceNaturalSizes, setFaceNaturalSizes] = useState<Record<string, { w: number; h: number }>>({});

  // Per-face view mode ("canonical" vs "original" photograph)
  const [faceViewModes, setFaceViewModes] = useState<Record<string, "canonical" | "original">>({});

  // Active face for Before/After dual-slider comparison
  const [sliderFace, setSliderFace] = useState<SurfaceEvidence | null>(null);

  // Selected declaration / region (Bidirectional navigation)
  const [selectedLabel, setSelectedLabel] = useState<string>(
    inspection.evidence[0]?.label || inspection.declarations[0]?.field || "MRP"
  );

  const activeSurface = useMemo(() => {
    return surfaces.find((s) => s.surfaceType === activeSurfaceType) || surfaces[0];
  }, [surfaces, activeSurfaceType]);

  // Synchronize active declaration and region bidirectionally
  const activeDecl = useMemo(() => {
    return (
      inspection.declarations.find(
        (d) =>
          d.field.toLowerCase() === selectedLabel.toLowerCase() ||
          d.canonicalField?.toLowerCase() === selectedLabel.toLowerCase() ||
          selectedLabel.toLowerCase().includes(d.field.toLowerCase())
      ) || inspection.declarations[0]
    );
  }, [selectedLabel, inspection.declarations]);

  const activeRegion = useMemo(() => {
    const pool = activeSurface?.regions?.length ? activeSurface.regions : inspection.evidence;
    return (
      pool.find(
        (r) =>
          r.label.toLowerCase() === selectedLabel.toLowerCase() ||
          r.label.toLowerCase().includes(selectedLabel.toLowerCase())
      ) ||
      pool[0]
    );
  }, [selectedLabel, activeSurface, inspection.evidence]);

  // Target bounding box for evidence crop (raw pixel space)
  const targetBbox = activeRegion?.bboxPx || activeDecl?.evidenceBboxPx;

  function handleSelectDeclaration(field: string, targetFace?: string) {
    setSelectedLabel(field);
    const decl = inspection.declarations.find((d) => d.field.toLowerCase() === field.toLowerCase());
    const surfaceType = targetFace || decl?.provenance?.surfaceType;
    if (surfaceType) {
      const match = surfaces.find(
        (s) =>
          s.surfaceType.toLowerCase() === surfaceType.toLowerCase() ||
          s.faceLabel?.toLowerCase() === surfaceType.toLowerCase()
      );
      if (match) {
        setActiveSurfaceType(match.surfaceType);
      }
    }
  }

  // Package-level unobserved declarations (Zero false absence warning)
  const unobservedDeclarations = useMemo(() => {
    return inspection.declarations.filter(
      (d) => d.status === "MISSING" || d.status === "UNOBSERVED" || d.status === "REVIEW"
    );
  }, [inspection.declarations]);

  return (
    <>
      <AppHeader title="Legal Metrology Evidence Investigator" />
      <main className="mx-auto max-w-7xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-8">
        {/* Top bar: Back & Evidence Meta */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/70 pb-4">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground transition"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to inspection result
          </button>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">Inspection:</span> {inspection.id}
            <span className="h-3 w-px bg-border" />
            <span className="font-semibold text-foreground">Category:</span> {inspection.category}
            <span className="h-3 w-px bg-border" />
            <span className="rounded-full bg-brand-soft px-2.5 py-0.5 font-bold text-brand text-[10px]">
              3-FACE AUTHORITATIVE EVIDENCE
            </span>
          </div>
        </div>

        {/* Active Before/After Comparison Slider */}
        {sliderFace && (
          <div className="relative">
            <BeforeAfterSlider
              originalUrl={sliderFace.imageUrl || inspection.image || ""}
              canonicalUrl={sliderFace.canonicalImageUrl || sliderFace.imageUrl || inspection.image || ""}
              faceLabel={sliderFace.faceLabel || sliderFace.surfaceType}
              naturalWidth={faceNaturalSizes[sliderFace.surfaceType]?.w}
              naturalHeight={faceNaturalSizes[sliderFace.surfaceType]?.h}
              marginPercent={6.0}
              onClose={() => setSliderFace(null)}
            />
          </div>
        )}

        {/* Authoritative 3-Face Side-by-Side Canonical Panels */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[.18em] text-muted-foreground">
                Authoritative Multi-Surface Analysis
              </p>
              <h2 className="text-lg font-bold tracking-tight text-foreground">
                All Canonical Preprocessed Faces ({surfaces.length} Registered Surfaces)
              </h2>
            </div>
            <span className="text-xs text-muted-foreground hidden sm:inline">
              Face-isolated overlays · Dual canonical/original projection · Homography normalized
            </span>
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
            {surfaces.map((st, idx) => {
              const currentMode = faceViewModes[st.surfaceType] || "canonical";
              const displayUrl =
                currentMode === "original"
                  ? st.imageUrl || st.canonicalImageUrl || inspection.image
                  : st.canonicalImageUrl || st.imageUrl || inspection.image;
              const isPanelActive = activeSurfaceType === st.surfaceType;
              const priority = st.priorityScore ?? (1.0 - idx * 0.05);

              // Filter regions strictly belonging to this face with valid polygons or bboxes
              const faceRegionsWithBox = (st.regions || []).filter(
                (r) => (r.polygonPx && r.polygonPx.length >= 3) || (r.bboxPx && r.bboxPx.width > 0 && r.bboxPx.height > 0)
              );

              return (
                <div
                  key={st.surfaceId || st.surfaceType || idx}
                  className={`flex flex-col rounded-2xl border bg-card p-4 shadow-sm transition-all ${
                    isPanelActive
                      ? "border-brand ring-2 ring-brand/30 shadow-md"
                      : "border-border/70 hover:border-border"
                  }`}
                >
                  {/* Face Header: Sleek, decluttered minimalist toolbar */}
                  <div className="flex items-center justify-between border-b border-border/60 pb-2 mb-3">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setActiveSurfaceType(st.surfaceType)}
                        className="text-left group flex items-center gap-1.5"
                      >
                        <span className="text-sm font-bold text-foreground group-hover:text-brand transition">
                          {st.faceLabel || st.surfaceType || `Face ${idx + 1}`}
                        </span>
                      </button>
                      <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[9px] font-bold text-brand">
                        P{(priority * 100).toFixed(0)}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      {/* Segmented Pill Switcher */}
                      <div className="inline-flex rounded-lg border border-border/70 bg-muted/60 p-0.5 text-[10px] font-medium">
                        <button
                          type="button"
                          onClick={() => {
                            setFaceViewModes((prev) => ({
                              ...prev,
                              [st.surfaceType]: "canonical",
                            }));
                          }}
                          className={`rounded-md px-2 py-0.5 transition ${
                            currentMode === "canonical"
                              ? "bg-background text-foreground font-bold shadow-xs"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          Scan
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setFaceViewModes((prev) => ({
                              ...prev,
                              [st.surfaceType]: "original",
                            }));
                          }}
                          className={`rounded-md px-2 py-0.5 transition ${
                            currentMode === "original"
                              ? "bg-background text-foreground font-bold shadow-xs"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          Raw
                        </button>
                      </div>

                      {/* Before / After Slider Toggle */}
                      <button
                        type="button"
                        onClick={() => setSliderFace(st)}
                        className="rounded-lg border border-border/70 bg-card p-1 text-muted-foreground hover:bg-brand-soft hover:text-brand transition"
                        title="Open interactive Before/After comparison slider"
                      >
                        <SlidersHorizontal className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Canvas Viewport with Face-Isolated Overlays */}
                  <div className="relative aspect-[4/3] w-full overflow-hidden rounded-xl border border-border/60 bg-neutral-950 flex items-center justify-center">
                    {displayUrl ? (
                      <div className="relative flex items-center justify-center h-full w-full">
                        <img
                          src={displayUrl}
                          alt={`${st.faceLabel || st.surfaceType} scan`}
                          className="max-h-full max-w-full object-contain select-none block"
                          onLoad={(e) => {
                            const img = e.currentTarget;
                            setFaceNaturalSizes((prev) => ({
                              ...prev,
                              [st.surfaceType]: { w: img.naturalWidth, h: img.naturalHeight },
                            }));
                          }}
                        />
                        {/* SVG Polygon & Vector Overlay (Canonical Mode) */}
                        {currentMode === "canonical" && faceNaturalSizes[st.surfaceType] && (
                          <svg
                            className="absolute inset-0 w-full h-full pointer-events-none"
                            viewBox={`0 0 ${faceNaturalSizes[st.surfaceType].w} ${faceNaturalSizes[st.surfaceType].h}`}
                            preserveAspectRatio="xMidYMid meet"
                          >
                            {faceRegionsWithBox.map((region) => {
                              const isSelected = selectedLabel.toLowerCase() === region.label.toLowerCase();
                              const cols = getSvgColors(region.label, isSelected);

                              if (region.polygonPx && region.polygonPx.length >= 3) {
                                const pts = region.polygonPx.map(([px, py]) => `${px},${py}`).join(" ");
                                const [firstX, firstY] = region.polygonPx[0];
                                return (
                                  <g
                                    key={region.label}
                                    className="pointer-events-auto cursor-pointer group"
                                    onClick={() => handleSelectDeclaration(region.label, st.surfaceType)}
                                  >
                                    <polygon
                                      points={pts}
                                      fill={cols.fill}
                                      stroke={cols.stroke}
                                      strokeWidth={isSelected ? 4 : 2}
                                      strokeLinejoin="round"
                                      className="transition-all hover:fill-opacity-50"
                                    />
                                    <rect
                                      x={firstX}
                                      y={Math.max(4, firstY - 20)}
                                      width={region.label.length * 8 + 14}
                                      height={18}
                                      rx={4}
                                      fill="#0f172a"
                                      fillOpacity={0.9}
                                      stroke={cols.stroke}
                                      strokeWidth={1}
                                    />
                                    <text
                                      x={firstX + 6}
                                      y={Math.max(16, firstY - 7)}
                                      fill="#ffffff"
                                      fontSize="11"
                                      fontWeight="bold"
                                    >
                                      {region.label}
                                    </text>
                                  </g>
                                );
                              } else if (region.bboxPx) {
                                return (
                                  <g
                                    key={region.label}
                                    className="pointer-events-auto cursor-pointer group"
                                    onClick={() => handleSelectDeclaration(region.label, st.surfaceType)}
                                  >
                                    <rect
                                      x={region.bboxPx.x}
                                      y={region.bboxPx.y}
                                      width={region.bboxPx.width}
                                      height={region.bboxPx.height}
                                      rx={3}
                                      fill={cols.fill}
                                      stroke={cols.stroke}
                                      strokeWidth={isSelected ? 4 : 2}
                                      className="transition-all hover:fill-opacity-50"
                                    />
                                    <rect
                                      x={region.bboxPx.x}
                                      y={Math.max(4, region.bboxPx.y - 20)}
                                      width={region.label.length * 8 + 14}
                                      height={18}
                                      rx={4}
                                      fill="#0f172a"
                                      fillOpacity={0.9}
                                      stroke={cols.stroke}
                                      strokeWidth={1}
                                    />
                                    <text
                                      x={region.bboxPx.x + 6}
                                      y={Math.max(16, region.bboxPx.y - 7)}
                                      fill="#ffffff"
                                      fontSize="11"
                                      fontWeight="bold"
                                    >
                                      {region.label}
                                    </text>
                                  </g>
                                );
                              }
                              return null;
                            })}
                          </svg>
                        )}
                      </div>
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                        No image capture
                      </div>
                    )}
                  </div>

                  {/* Surface Declarations Pill List - Decluttered & Compact */}
                  <div className="mt-3 flex flex-wrap items-center gap-1.5 max-h-24 overflow-y-auto pr-0.5">
                    {st.regions && st.regions.length > 0 ? (
                      st.regions.map((r) => {
                        const isSelected = selectedLabel.toLowerCase() === r.label.toLowerCase();
                        return (
                          <button
                            key={r.label}
                            type="button"
                            onClick={() => handleSelectDeclaration(r.label, st.surfaceType)}
                            className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-semibold transition ${
                              isSelected
                                ? "bg-brand text-brand-foreground shadow-xs ring-1 ring-brand"
                                : "bg-muted/70 text-muted-foreground hover:bg-muted hover:text-foreground"
                            }`}
                          >
                            <span>{r.label}:</span>
                            <span className="font-mono text-[9px] opacity-90 truncate max-w-[70px]">
                              {r.value}
                            </span>
                          </button>
                        );
                      })
                    ) : (
                      <span className="text-[11px] italic text-muted-foreground">
                        {st.faceLabel === "Face 1"
                          ? "Principal display branding / title"
                          : "No statutory declarations isolated on this surface"}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Statutory Package-Level Unobserved Declarations (Zero False Absence Warning) */}
        {unobservedDeclarations.length > 0 && (
          <section className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 sm:p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
              <div className="space-y-1">
                <h3 className="text-sm font-bold text-foreground">
                  Package-Level Unobserved Declarations ({unobservedDeclarations.length})
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  These statutory items were not observed across <strong>any of the 3 captured package surfaces</strong>.
                  Under Legal Metrology Rules, absence is evaluated across the package as a whole; this is <strong>not</strong> an error or omission of Face 1 or Face 2 individually.
                </p>
                <div className="mt-2.5 flex flex-wrap gap-2">
                  {unobservedDeclarations.map((d) => (
                    <div
                      key={d.field}
                      className="inline-flex items-center gap-2 rounded-lg border border-amber-500/20 bg-background/80 px-2.5 py-1 text-xs"
                    >
                      <span className="font-semibold text-foreground">{d.field}</span>
                      <span className="rounded bg-amber-500/10 px-1.5 py-0.2 text-[10px] font-bold text-amber-500 uppercase">
                        {d.status}
                      </span>
                      {d.reason && (
                        <span className="text-[11px] text-muted-foreground max-w-xs truncate">
                          ({d.reason})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Dynamic Evidence Crop & Multi-Signal Audit Drawer */}
        <div className="grid gap-6 lg:grid-cols-[1.3fr_0.95fr]">
          {/* Left: Dynamic Evidence Crop & Coordinate Projection */}
          <section className="flex flex-col space-y-3 rounded-2xl border border-border/70 bg-card p-4 sm:p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">
                  Dynamic Evidence Crop · {activeDecl?.field || selectedLabel}
                </p>
                <h3 className="text-lg font-semibold tracking-tight">
                  Located on {activeSurface?.faceLabel || activeSurface?.surfaceType} (P{((activeSurface?.priorityScore ?? 1.0) * 100).toFixed(0)})
                </h3>
              </div>
              <span className="rounded-full bg-brand-soft px-3 py-1 text-xs font-bold text-brand">
                Target Crop Active
              </span>
            </div>

            {/* Coordinate Projection Info */}
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/60 px-3 py-1.5 text-[11px] font-mono text-muted-foreground">
              <span>
                <strong>Coordinate Space:</strong> DYNAMIC_CROP (
                {faceNaturalSizes[activeSurface.surfaceType]
                  ? `${faceNaturalSizes[activeSurface.surfaceType].w}×${faceNaturalSizes[activeSurface.surfaceType].h}px`
                  : "Reading..."}
                )
              </span>
              <span>
                <strong>Projection:</strong> In-plane Rectified Canonical ↔ Sensor
              </span>
            </div>

            {/* Dynamic Crop Component */}
            <DynamicEvidenceCrop
              imageSrc={
                activeSurface.canonicalImageUrl ||
                activeSurface.imageUrl ||
                inspection.canonicalImage ||
                inspection.image ||
                ""
              }
              bbox={targetBbox}
              polygon={activeDecl?.canonicalPolygonPx || activeDecl?.polygonPx || activeRegion?.canonicalPolygonPx || activeRegion?.polygonPx}
              localizationStatus={activeRegion?.localizationStatus || (targetBbox ? "VERIFIED_MATCH" : "UNLOCALIZED")}
              label={activeDecl?.field || selectedLabel}
              value={activeDecl?.value || activeRegion?.value}
              confidence={activeDecl?.confidence ?? activeRegion?.confidence}
            />

            {/* Transformation History Provenance Chain */}
            <div className="rounded-xl border border-border/60 bg-muted/40 p-3">
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
                Transformation Provenance Chain ({activeSurface?.faceLabel || activeSurface?.surfaceType}):
              </p>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-foreground/80">
                {(activeSurface.transformHistory || [
                  "Original Camera Sensor Capture",
                  "OpenCV Dual-Threshold Contouring",
                  "Perspective Homography H-Matrix",
                  "Safe +6% Outward Margin Rectification",
                  "Declaration Boundary Localized",
                ]).map((step: string, idx: number, arr: string[]) => (
                  <span key={step} className="inline-flex items-center gap-1.5">
                    <span className="rounded bg-card px-2 py-0.5 border border-border/80 text-[11px] font-medium">
                      {step}
                    </span>
                    {idx < arr.length - 1 && <ChevronRight className="h-3 w-3 text-muted-foreground" />}
                  </span>
                ))}
              </div>
            </div>

            {/* Quick Declaration Inspector Selector Chips */}
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[.15em] text-muted-foreground mb-2">
                Quick Declaration Inspector
              </p>
              <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto pr-1">
                {inspection.declarations.map((d) => {
                  const isSelected = selectedLabel.toLowerCase() === d.field.toLowerCase();
                  return (
                    <button
                      key={d.field}
                      type="button"
                      onClick={() => handleSelectDeclaration(d.field)}
                      className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                        isSelected
                          ? "bg-brand text-brand-foreground shadow-xs ring-1 ring-brand"
                          : "border border-border/60 bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      {d.field}
                    </button>
                  );
                })}
              </div>
            </div>
          </section>

          {/* Right: Rich Explainability & Reasoning Signals */}
          <section className="flex flex-col space-y-4 rounded-2xl border border-border/70 bg-card p-5 sm:p-6 shadow-sm overflow-y-auto">
            <div className="flex items-center justify-between border-b border-border/70 pb-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">Declaration Audit</p>
                <h3 className="text-xl font-bold tracking-tight text-foreground">{activeDecl?.field || selectedLabel}</h3>
              </div>
              <div className="text-right">
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ${
                  activeDecl?.status === "VERIFIED"
                    ? "bg-success-soft text-success"
                    : activeDecl?.status === "MISSING"
                    ? "bg-danger-soft text-danger"
                    : "bg-warning-soft text-warning"
                }`}>
                  {activeDecl?.status || "DETECTED"}
                </span>
                <p className="mt-1 text-[11px] font-mono text-muted-foreground">
                  Status: {activeDecl?.status === "VERIFIED" ? "Verified" : (activeDecl?.status === "REVIEW" ? "Review" : "Not detected")}
                </p>
              </div>
            </div>

            {/* Selected Value Card */}
            <div className="rounded-xl border border-border/80 bg-muted/40 p-4">
              <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Resolved Value</p>
              <p className="mt-1.5 text-2xl font-black tracking-tight text-foreground">
                {activeDecl?.value || activeRegion?.value || "Not Detected"}
              </p>
              {activeDecl?.ruleId && (
                <p className="mt-2 text-xs font-medium text-muted-foreground">
                  Governed under: <strong className="text-foreground">{activeDecl.ruleId}</strong>
                </p>
              )}
            </div>

            {/* Statutory Finding & Legal Notes */}
            <div className="rounded-xl border border-border/80 bg-muted/30 p-3.5 text-xs text-muted-foreground space-y-1">
              <p className="font-semibold text-foreground">
                Statutory Rule Analysis: {activeDecl?.ruleId || "Rule 6 - Declarations on Pre-packaged Commodities"}
              </p>
              <p className="leading-relaxed">
                {activeDecl?.reason || "Declaration is fully compliant with legal metrology statutory formatting and position standards."}
              </p>
            </div>
          </section>
        </div>
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
            <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Product Name</p>
                <p className="mt-2 text-sm font-semibold">{inspection.product}</p>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  <span className="font-medium">Product ID:</span>{" "}
                  <span className={inspection.productId && inspection.productId !== "Not detected" ? "text-foreground" : "text-amber-500"}>
                    {inspection.productId || "Not detected"}
                  </span>
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">{inspection.manufacturer}</p>
              </div>
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Inspection ID</p><p className="mt-2 text-sm font-semibold">#{inspection.id}</p><p className="mt-1 text-xs text-muted-foreground">{formatDate(inspection.timestamp)}</p></div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Final scores</p>
              <p className="mt-2 text-sm font-semibold">
                {inspection.scoreBreakdown
                  ? `Verified: ${inspection.scoreBreakdown.verifiedCount} of ${inspection.scoreBreakdown.applicableCount} applicable · Assessed: ${inspection.scoreBreakdown.judgeableCount} of ${inspection.scoreBreakdown.applicableCount}`
                  : `Verified: ${inspection.verifiedScore ?? inspection.score}% · Reviewed: ${inspection.reviewedScore ?? inspection.score}%`}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {inspection.declarations.filter((item) => item.status === "VERIFIED" || item.status === "EXEMPT").length}/{inspection.declarations.length} verified
                {inspection.pdpAreaCm2 ? ` · PDP: ${inspection.pdpAreaCm2} cm²` : ""}
              </p>
            </div>
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
        <div className="mt-4 rounded-xl border border-border/60 bg-muted/40 p-3">
          <p className="text-[11px] font-medium text-muted-foreground mb-2">Default demo credentials (click to fill):</p>
          <div className="flex gap-2">
            <button
              type="button"
              id="fill-admin-btn"
              onClick={() => { setUsername("admin"); setPassword("password123"); }}
              className="flex-1 rounded-lg border border-border/80 bg-background py-1.5 text-xs font-medium hover:bg-muted transition-colors"
            >
              Admin (password123)
            </button>
            <button
              type="button"
              id="fill-inspector-btn"
              onClick={() => { setUsername("inspector"); setPassword("password123"); }}
              className="flex-1 rounded-lg border border-border/80 bg-background py-1.5 text-xs font-medium hover:bg-muted transition-colors"
            >
              Inspector (password123)
            </button>
          </div>
        </div>
        {error && <div className="mt-4 flex items-center gap-2 rounded-lg bg-danger-soft px-3 py-2 text-xs text-destructive"><AlertTriangle className="h-4 w-4 shrink-0" />{error}</div>}
        <Button type="submit" className="mt-4 w-full" disabled={submitting || !username || !password}>
          {submitting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
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
  const [canonicalImages, setCanonicalImages] = useState<string[]>([]);
  const [preprocessingError, setPreprocessingError] = useState<string | undefined>(undefined);
  const [processingError, setProcessingError] = useState<string | undefined>(undefined);
  const [toast, setToast] = useState<string | undefined>(undefined);

  function handleAuthExpiry(err: unknown): boolean {
    if (err instanceof ApiError && err.status === 401) {
      clearSession();
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
    if (nextView === "scan") {
      setPendingImages([]);
      setCanonicalImages([]);
    }
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

  function onCaptured(images: string[]) {
    setPendingImages(images);
    setCanonicalImages([]);
    setPreprocessingError(undefined);
    setView("preprocessing");
  }

  function handlePreprocessingDone(canonUrls: string[]) {
    setCanonicalImages(canonUrls);
    setView("scanDetails");
  }

  function handlePreprocessingError(message: string) {
    setPreprocessingError(message);
  }

  const pendingRunRef = useRef<() => Promise<Inspection>>(() => Promise.reject(new Error("no scan queued")));

  /** Real multi-surface capture: open a session, upload every preprocessed canonical photo
   * as its own surface (Face 1, Face 2, Face 3), then
   * finalize once so the legal engine and perception run against the preprocessed canonical images. */
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

    const surfaceForIndex = (i: number): SurfaceType => `Face ${i + 1}`;
    // Prefer clean canonical images, fall back to pendingImages if unavailable
    const targetImages = canonicalImages.length > 0 ? canonicalImages : pendingImages;

    for (let i = 0; i < targetImages.length; i++) {
      const imgRef = targetImages[i];
      let blob: Blob;
      if (imgRef.startsWith("data:") || imgRef.startsWith("blob:")) {
        blob = dataUrlToBlob(imgRef);
      } else {
        const fullUrl = resolveImageUrl(imgRef) || imgRef;
        const fetched = await fetch(fullUrl);
        blob = await fetched.blob();
      }
      await addSessionCapture(session.session_id, blob, surfaceForIndex(i));
    }

    const inspection = await finalizeSession(session.session_id);
    return fromFinalizedInspection(inspection, { productId: details.productId }, pendingImages[0] || canonicalImages[0]);
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
      <HomeView inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onLogout={handleLogout} onNavigate={go} onOpen={handleOpen} />
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
    ) : view === "preprocessing" ? (
      preprocessingError ? (
        <ProcessingErrorView message={preprocessingError} onRetry={() => onCaptured(pendingImages)} onCancel={() => go("home")} />
      ) : (
        <PreprocessingRunner images={pendingImages} onDone={handlePreprocessingDone} onError={handlePreprocessingError} />
      )
    ) : view === "scanDetails" ? (
      <ScanDetailsView images={canonicalImages.length > 0 ? canonicalImages : pendingImages} onSubmit={submitDetails} onBack={() => go("scan")} />
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
    ) : view === "regulatory" ? (
      <RegulatoryIntelligenceDashboard onBack={() => go("home")} />
    ) : (
      <HomeView inspections={inspections} loading={listLoading} error={listError} onRetry={refreshInspections} onNavigate={go} onOpen={handleOpen} />
    );

  const inFocusedFlow = ["scan", "preprocessing", "scanDetails", "processing"].includes(view);

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
