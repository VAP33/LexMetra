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
    <svg
      viewBox="0 0 420 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="LexMetra Statutory Compliance Platform"
    >
      <defs>
        <linearGradient id="shieldGradLM" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#1E3A8A" />
          <stop offset="100%" stopColor="#0F172A" />
        </linearGradient>
        <linearGradient id="tricolorLM" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#FF9933" />
          <stop offset="50%" stopColor="#CBD5E1" />
          <stop offset="100%" stopColor="#138808" />
        </linearGradient>
      </defs>

      {/* Emblem Icon (Left) */}
      <g transform="translate(10, 10)">
        <path
          d="M40 0 L72 18 L72 58 L40 78 L8 58 L8 18 Z"
          fill="url(#shieldGradLM)"
          stroke="#3B82F6"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        <line x1="16" y1="28" x2="22" y2="28" stroke="#93C5FD" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="16" y1="36" x2="25" y2="36" stroke="#F59E0B" strokeWidth="2" strokeLinecap="round" />
        <line x1="16" y1="44" x2="22" y2="44" stroke="#93C5FD" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="16" y1="52" x2="25" y2="52" stroke="#10B981" strokeWidth="2" strokeLinecap="round" />

        {/* Scales of Justice / Legal Metrology */}
        <path d="M40 16 L40 62" stroke="#E2E8F0" strokeWidth="2.5" strokeLinecap="round" />
        <path d="M26 26 L54 26" stroke="#F59E0B" strokeWidth="2.5" strokeLinecap="round" />
        <path d="M26 26 L22 40 L30 40 Z" fill="none" stroke="#CBD5E1" strokeWidth="1.5" />
        <path d="M20 40 Q26 46 32 40" fill="none" stroke="#F59E0B" strokeWidth="2" strokeLinecap="round" />
        <path d="M54 26 L50 40 L58 40 Z" fill="none" stroke="#CBD5E1" strokeWidth="1.5" />
        <path d="M48 40 Q54 46 60 40" fill="none" stroke="#F59E0B" strokeWidth="2" strokeLinecap="round" />
        <circle cx="40" cy="26" r="3.5" fill="#38BDF8" stroke="#0F172A" strokeWidth="1" />

        {/* Tricolor Ribbon at Base */}
        <rect x="22" y="66" width="36" height="3" rx="1.5" fill="url(#tricolorLM)" />
      </g>

      {/* Brand Typography */}
      <text
        x="100"
        y="46"
        fontFamily="system-ui, -apple-system, sans-serif"
        fontSize="34"
        fontWeight="900"
        letterSpacing="3"
        fill="#0F172A"
      >
        LEX<tspan fill="#2563EB">METRA</tspan>
      </text>

      {/* DCA IND Pill */}
      <rect x="306" y="24" width="76" height="24" rx="6" fill="#EFF6FF" stroke="#3B82F6" strokeWidth="1.5" />
      <text
        x="344"
        y="40"
        fontFamily="system-ui, -apple-system, sans-serif"
        fontSize="11"
        fontWeight="800"
        fill="#1D4ED8"
        textAnchor="middle"
        letterSpacing="1"
      >
        DCA IND
      </text>

      {/* Subtitle */}
      <text
        x="102"
        y="70"
        fontFamily="system-ui, -apple-system, sans-serif"
        fontSize="10"
        fontWeight="700"
        letterSpacing="2"
        fill="#047857"
      >
        LEGAL METROLOGY DIVISION · GOVT OF INDIA
      </text>
    </svg>
  );
}
