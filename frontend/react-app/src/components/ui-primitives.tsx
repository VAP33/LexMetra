import React from "react";
import {
  Check,
  ChevronRight,
  Info,
  PackageCheck,
  ShieldCheck,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import {
  statusCopy,
  type Inspection,
  type InspectionStatus,
} from "@/lib/types";
import { type Language, getTranslation } from "@/lib/i18n";
import { type AppView as View } from "@/lib/nav-history";

export type { View };

export const statusStyles: Record<
  InspectionStatus,
  { dot: string; text: string; bg: string; border: string; icon: LucideIcon }
> = {
  COMPLIANT: { dot: "bg-success", text: "text-success", bg: "bg-success-soft", border: "border-success/20", icon: Check },
  VIOLATION: { dot: "bg-destructive", text: "text-destructive", bg: "bg-danger-soft", border: "border-destructive/20", icon: XCircle },
  UNCERTAIN: { dot: "bg-warning", text: "text-warning", bg: "bg-warning-soft", border: "border-warning/20", icon: Info },
  EXEMPT: { dot: "bg-brand", text: "text-brand", bg: "bg-brand-soft", border: "border-brand/20", icon: ShieldCheck },
};

export function statusLabel(status: InspectionStatus, lang?: Language) {
  if (lang) {
    const t = getTranslation(lang);
    if (status === "COMPLIANT") return t.compliant;
    if (status === "VIOLATION") return t.violation;
    if (status === "UNCERTAIN") return t.reviewRequired;
    if (status === "EXEMPT") return t.exempt;
  }
  return statusCopy[status].label;
}

export function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
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
    primary: "bg-purple-700 hover:bg-purple-800 text-white font-bold shadow-sm",
    secondary: "bg-white text-slate-900 border border-slate-300 hover:bg-slate-50 hover:text-black font-bold shadow-xs",
    quiet: "bg-transparent text-slate-700 hover:bg-slate-100 hover:text-slate-900 font-semibold",
    danger: "bg-red-600 hover:bg-red-700 text-white font-bold shadow-sm",
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

export function StatusBadge({ status, compact = false, lang }: { status: InspectionStatus; compact?: boolean; lang?: Language }) {
  const style = statusStyles[status];
  const Icon = style.icon;
  const label = lang ? statusLabel(status, lang) : (compact ? statusCopy[status].short : statusLabel(status));
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-[.08em] ${style.bg} ${style.text} ${style.border}`}>
      <Icon className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}

export function InspectionRow({ inspection, onOpen, lang }: { inspection: Inspection; onOpen: (inspection: Inspection) => void; lang?: Language }) {
  const needsReviewText = lang === "hi" ? "समीक्षा अपेक्षित" : lang === "mr" ? "तपासणी आवश्यक" : "Needs review";
  return (
    <button type="button" onClick={() => onOpen(inspection)} className="group flex w-full items-center gap-3 border-b border-border/70 py-4 text-left last:border-0 hover:bg-muted/40">
      <ProductThumb inspection={inspection} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-foreground">{inspection.product}</p>
        <p className="mt-1 truncate text-xs text-muted-foreground">
          {inspection.productId ? `#${inspection.productId} · ` : ""}{inspection.dateLabel}
        </p>
      </div>
      <div className="flex flex-col items-end gap-1">
        <StatusBadge status={inspection.status} compact lang={lang} />
        {inspection.reviewRequired && !inspection.reviewed && <span className="text-[10px] font-bold text-warning">{needsReviewText}</span>}
        <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </div>
    </button>
  );
}

export function LexMetraLogo({ className = "h-8 sm:h-9 w-auto" }: { className?: string }) {
  return (
    <img
      src="/lexmetra-logo-new.png"
      alt="LexMetra"
      className={className}
      draggable={false}
    />
  );
}
