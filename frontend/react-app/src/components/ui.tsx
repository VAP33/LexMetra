import {
  AlertTriangle,
  Check,
  ChevronRight,
  Info,
  LogOut,
  PackageCheck,
  RefreshCcw,
  ScanLine,
  ShieldCheck,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { formatMrp } from "@/lib/format";
import { statusCopy, type Inspection, type InspectionStatus } from "@/lib/types";

export const statusStyles: Record<
  InspectionStatus,
  { dot: string; text: string; bg: string; border: string; icon: LucideIcon }
> = {
  COMPLIANT: { dot: "bg-success", text: "text-success", bg: "bg-success-soft", border: "border-success/20", icon: Check },
  VIOLATION: { dot: "bg-destructive", text: "text-destructive", bg: "bg-danger-soft", border: "border-destructive/20", icon: XCircle },
  UNCERTAIN: { dot: "bg-warning", text: "text-warning", bg: "bg-warning-soft", border: "border-warning/20", icon: Info },
  EXEMPT: { dot: "bg-brand", text: "text-brand", bg: "bg-brand-soft", border: "border-brand/20", icon: ShieldCheck },
};

export function statusLabel(status: InspectionStatus) {
  return statusCopy[status].label;
}

export function Button({
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

export function ProductThumb({ inspection, large = false }: { inspection: Inspection; large?: boolean }) {
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

export function StatusBadge({ status, compact = false }: { status: InspectionStatus; compact?: boolean }) {
  const style = statusStyles[status];
  const Icon = style.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-[.08em] ${style.bg} ${style.text} ${style.border}`}>
      <Icon className="h-3.5 w-3.5" />
      {compact ? statusCopy[status].short : statusLabel(status)}
    </span>
  );
}

export function Metric({ label, value, accent, loading = false }: { label: string; value: number; accent?: InspectionStatus; loading?: boolean }) {
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

export function InspectionRow({ inspection, onOpen }: { inspection: Inspection; onOpen: (inspection: Inspection) => void }) {
  return (
    <button type="button" onClick={() => onOpen(inspection)} className="group flex w-full items-center gap-3 border-b border-border/70 py-4 text-left last:border-0 hover:bg-muted/40">
      <ProductThumb inspection={inspection} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-foreground">{inspection.product}</p>
        <p className="mt-1 truncate text-xs text-muted-foreground">
          {inspection.id} · {formatMrp(inspection.mrp)} · {inspection.dateLabel}
        </p>
      </div>
      <div className="flex flex-col items-end gap-1">
        <StatusBadge status={inspection.status} compact />
        {inspection.reviewed ? (
          <span className="text-[10px] font-bold text-success">Reviewed</span>
        ) : inspection.reviewRequired ? (
          <span className="text-[10px] font-bold text-warning">Needs review</span>
        ) : null}
        <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </div>
    </button>
  );
}

export function EmptyState({ title, description, onAction, actionLabel = "Scan Product" }: { title: string; description: string; onAction: () => void; actionLabel?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-card px-6 py-12 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground"><PackageCheck className="h-6 w-6" /></div>
      <h3 className="mt-4 text-base font-semibold">{title}</h3>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{description}</p>
      <Button className="mt-6" onClick={onAction}><ScanLine className="h-4 w-4" />{actionLabel}</Button>
    </div>
  );
}

export function ErrorBanner({ message, onRetry, onLogout }: { message: string; onRetry?: () => void; onLogout?: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-destructive/25 bg-danger-soft p-4 text-sm">
      <AlertTriangle className="h-5 w-5 shrink-0 text-destructive" />
      <p className="flex-1 text-destructive">{message}</p>
      {onRetry && <Button variant="secondary" onClick={onRetry}><RefreshCcw className="h-4 w-4" />Retry</Button>}
      {onLogout && <Button variant="secondary" onClick={onLogout}><LogOut className="h-4 w-4" />Sign in</Button>}
    </div>
  );
}

export function DisclaimerBanner({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/70 bg-muted/60 p-4 text-xs leading-5 text-muted-foreground">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <p>{text}</p>
    </div>
  );
}
