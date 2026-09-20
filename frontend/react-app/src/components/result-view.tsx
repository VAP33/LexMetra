import React, { useState, useMemo } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  Building2,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  CircleSlash,
  Clock,
  Edit2,
  Eye,
  FileCheck,
  FileText,
  Info,
  Layers,
  MessageSquare,
  PackageCheck,
  Save,
  ScanLine,
  Share2,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  UserCheck,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { type Language, getTranslation } from "@/lib/i18n";
import { type Declaration, type DeclarationStatus, type Inspection, type InspectionStatus } from "@/lib/types";
import { markReviewed, type AuthedUser } from "@/lib/api-client";
import { type View, Button, StatusBadge, formatDate, statusStyles } from "./ui-primitives";
import { Header as AppHeader } from "./app-header";
import { DisclaimerBanner } from "./app-navigation";
import { fromInspectionRow } from "@/lib/adapters";
import {
  PackageIntegrityCard,
  DepartmentalCrossVerificationCard,
  ManufacturerContactSection,
  ConsumerReportModal,
} from "./usp-components";

export function renderFormattedValue(field: string, val?: string | null) {
  if (!val || val === "—" || val === "Not detected" || val === "Not applicable") {
    return <span className="text-sm text-muted-foreground italic">{val || "—"}</span>;
  }

  const fLower = field.toLowerCase();

  // Manufacturer / Marketer / Packer: format company name in bold, and postal address cleanly
  if (fLower.includes("manufacturer") || fLower.includes("marketer") || fLower.includes("packer")) {
    const match = val.match(/^([^,]+?(?:Private Limited|Pvt\.?\s*Ltd\.?|Limited|Ltd\.?|LLP|Inc\.?|Corp\.?|Company))\s*,\s*(.+)$/i) ||
                  val.match(/^([^,]{3,45}?),\s*(.+)$/);
    if (match) {
      const [, company, address] = match;
      return (
        <div className="text-xs leading-relaxed max-w-[640px]">
          <span className="font-bold text-foreground text-sm block sm:inline">{company}</span>
          <span className="text-muted-foreground block sm:inline sm:before:content-[',_'] font-normal">{address}</span>
        </div>
      );
    }
    return <span className="text-xs leading-relaxed text-foreground font-medium max-w-[640px] block">{val}</span>;
  }

  // Consumer Care Details: display email and phone as crisp tags
  if (fLower.includes("consumer care")) {
    const parts = val.split(/,\s*/);
    if (parts.length > 1) {
      return (
        <div className="flex flex-wrap items-center gap-1.5 text-xs py-0.5">
          {parts.map((p, i) => {
            const isEmail = p.includes("@");
            const isPhone = /\d{5,}/.test(p);
            return (
              <span
                key={i}
                className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${
                  isEmail
                    ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                    : isPhone
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-mono"
                    : "bg-muted text-foreground font-medium"
                }`}
              >
                {p}
              </span>
            );
          })}
        </div>
      );
    }
  }

  // Expiry / Best Before / Mfg dates: primary batch date in mono bold, ISO date in clean tag
  if (fLower.includes("date") || fLower.includes("expiry") || fLower.includes("mfg")) {
    const dateMatch = val.match(/^([^\(]+?)(?:\s*\(([^\)]+)\))?$/);
    if (dateMatch) {
      const [, primaryDate, isoDate] = dateMatch;
      return (
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-foreground text-sm">{primaryDate.trim()}</span>
          {isoDate && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground border border-border/60">
              {isoDate}
            </span>
          )}
        </div>
      );
    }
  }

  // MRP / Net Quantity / Unit Sale Price
  if (fLower.includes("mrp") || fLower.includes("price") || fLower.includes("quantity") || fLower.includes("weight")) {
    return <span className="font-mono font-bold text-foreground text-sm">{val}</span>;
  }

  // Product Name / Brand
  if (fLower.includes("product name") || fLower.includes("brand")) {
    return <span className="font-bold text-foreground text-sm tracking-tight">{val}</span>;
  }

  return <span className="text-sm text-foreground font-medium">{val}</span>;
}

function DeclarationRow({
  declaration,
  inspectionId,
  onFactUpdated,
}: {
  declaration: Declaration;
  inspectionId?: string;
  onFactUpdated?: (field: string, newVal: string, refreshed: any) => void;
}) {
  const statusMap: Record<DeclarationStatus, { label: string; className: string; icon: LucideIcon }> = {
    VERIFIED: { label: "Verified", className: "text-success", icon: Check },
    NON_COMPLIANT: { label: "Non-Compliant", className: "text-destructive", icon: XCircle },
    MISSING: { label: "Not detected", className: "text-destructive", icon: XCircle },
    REVIEW: { label: "Review", className: "text-warning", icon: Info },
    EXEMPT: { label: "Exempt", className: "text-brand", icon: ShieldCheck },
    UNOBSERVED: { label: "Not detected", className: "text-muted-foreground", icon: CircleHelp },
    NOT_APPLICABLE: { label: "Not applicable", className: "text-muted-foreground", icon: CircleSlash },
  };
  const [expanded, setExpanded] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(declaration.value || "");
  const [saving, setSaving] = useState(false);

  const item = statusMap[declaration.status] || statusMap.REVIEW;
  const Icon = item.icon;

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!inspectionId || !editValue.trim() || saving) return;
    setSaving(true);
    try {
      const { updateInspectionFact } = await import("@/lib/api-client");
      const res = await updateInspectionFact(inspectionId, {
        field: declaration.field,
        value: editValue.trim(),
        reviewer_notes: "Direct inspection result inline correction.",
      });
      if (onFactUpdated) {
        onFactUpdated(declaration.field, editValue.trim(), res.refreshed_detail);
      }
      setIsEditing(false);
    } catch (err: any) {
      alert("Failed to update fact: " + err?.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border-b border-border/70 py-2.5 sm:py-3 last:border-0">
      <div className="grid w-full grid-cols-[1fr_auto] items-start gap-4 text-left sm:grid-cols-[200px_1fr_auto] sm:items-center">
        <button type="button" onClick={() => setExpanded((v) => !v)} className="text-left shrink-0 sm:w-[200px]">
          <p className="text-sm font-semibold">{declaration.field}</p>
          <div className="mt-1 text-xs text-muted-foreground sm:hidden">{renderFormattedValue(declaration.field, declaration.value)}</div>
        </button>
        <div className="hidden sm:flex items-center gap-2 min-w-0 flex-1">
          {!isEditing ? (
            renderFormattedValue(declaration.field, declaration.value)
          ) : (
            <form onSubmit={handleSaveEdit} className="flex items-center gap-1.5 w-full">
              <input
                type="text"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                className="h-8 flex-1 rounded-lg border border-brand bg-background px-2.5 text-xs outline-none"
                autoFocus
              />
              <button
                type="submit"
                disabled={saving}
                className="h-8 rounded-lg bg-brand px-2 text-[11px] font-bold text-brand-foreground"
              >
                {saving ? "…" : "Save"}
              </button>
              <button
                type="button"
                onClick={() => setIsEditing(false)}
                className="h-8 rounded-lg border border-border px-2 text-[11px] text-muted-foreground"
              >
                Cancel
              </button>
            </form>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {inspectionId && !isEditing && (
            <button
              type="button"
              onClick={() => {
                setEditValue(declaration.value || "");
                setIsEditing(true);
              }}
              className="rounded-lg border border-border/70 bg-card px-2 py-1 text-[11px] font-semibold text-muted-foreground hover:border-brand hover:text-brand transition"
            >
              Edit
            </button>
          )}
          <div className={`flex items-center gap-1 text-xs font-semibold ${item.className}`}>
            <Icon className="h-4 w-4" />{item.label}
            <button type="button" onClick={() => setExpanded((v) => !v)} className="p-1">
              <ChevronRight className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`} />
            </button>
          </div>
        </div>
      </div>
      {expanded && (
        <div className="mt-3 rounded-lg bg-muted p-3 text-xs leading-5 text-muted-foreground space-y-2">
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


export function ResultView({
  inspection,
  onSave,
  onOpenEvidence,
  onOpenReport,
  onNew,
  onInspectionUpdated,
}: {
  inspection: Inspection;
  onSave: () => void;
  onOpenEvidence: () => void;
  onOpenReport: () => void;
  onNew: () => void;
  onInspectionUpdated?: (updated: Inspection) => void;
}) {
  const [showReportModal, setShowReportModal] = useState(false);
  const [showIntegrityModal, setShowIntegrityModal] = useState(false);
  const [showDepartmentalModal, setShowDepartmentalModal] = useState(false);
  const [reportTracking, setReportTracking] = useState<{ caseId: string; reportId: string } | null>(null);
  const [resultLang, setResultLang] = useState<"en" | "hi" | "mr">("en");

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

  const resultAiSummary = useMemo(() => {
    const prod = inspection.product || "Product";
    if (resultLang === "hi") {
      return `${prod} का विधिक मेट्रोलॉजी (पैकेज्ड कमोडिटीज) नियम, 2011 के अंतर्गत निरीक्षण: कुल ${total} में से ${verified} वैधानिक घोषणाएं सत्यापित। वर्तमान स्थिति: ${inspection.status === "VIOLATION" ? "उल्लंघन (अधिसूचना आवश्यक)" : inspection.status === "UNCERTAIN" ? "समीक्षाधीन (प्रमाण संदिग्ध)" : "पूर्णतः अनुरूप"}। किसी भी घोषणा को संपादित करने पर नियम पुनः स्वचालित रूप से पुनर्मूल्यांकित किए जाएंगे।`;
    }
    if (resultLang === "mr") {
      return `${prod} ची कायदेशीर मापनशास्त्र (पॅकेज्ड कमोडिटीज) नियम, २०११ अंतर्गत तपासणी: एकूण ${total} पैकी ${verified} वैधानिक बाबी पडताळल्या गेल्या. सद्यस्थिती: ${inspection.status === "VIOLATION" ? "उल्लंघन (नोटीस आवश्यक)" : inspection.status === "UNCERTAIN" ? "पुनरावलोकन आवश्यक" : "अनुरूप"}. कोणतीही माहिती संपादित केल्यास नियम आपोआप पुन्हा तपासले जातील.`;
    }
    return `Statutory Inspection Summary for ${prod} under Legal Metrology (Packaged Commodities) Rules, 2011: ${verified} of ${total} mandatory declarations verified. Status evaluated as ${inspection.status}. ${inspection.status === "VIOLATION" ? "Statutory non-compliance identified under Rule 6; formal review notice recommended." : inspection.status === "UNCERTAIN" ? "Evidentiary ambiguity detected; officer confirmation required before registration." : "All observed declarations satisfy prescribed statutory thresholds."} Inline edits dynamically re-execute rule checks.`;
  }, [resultLang, inspection, verified, total]);

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
          <div className="grid grid-cols-1 gap-4 border-t border-current/10 bg-card/50 p-5 sm:grid-cols-3">
            <div><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Product Name</p><p className="mt-1 text-sm font-semibold">{inspection.product || "Not detected"}</p></div>
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

        {/* Dynamic Multilingual AI Inspection Analysis Block */}
        <section className="rounded-2xl border border-brand/30 bg-gradient-to-br from-brand/5 via-card to-card p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-border/60 pb-3 mb-2.5">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-brand" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                AI Grounded Inspection Summary
              </h3>
            </div>
            <div className="inline-flex rounded-lg border border-border/70 bg-card p-0.5 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setResultLang("en")}
                className={`rounded-md px-2 py-0.5 transition ${resultLang === "en" ? "bg-brand text-brand-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"}`}
              >
                EN
              </button>
              <button
                type="button"
                onClick={() => setResultLang("hi")}
                className={`rounded-md px-2 py-0.5 transition ${resultLang === "hi" ? "bg-brand text-brand-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"}`}
              >
                HI
              </button>
              <button
                type="button"
                onClick={() => setResultLang("mr")}
                className={`rounded-md px-2 py-0.5 transition ${resultLang === "mr" ? "bg-brand text-brand-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"}`}
              >
                MR
              </button>
            </div>
          </div>
          <p className="text-xs leading-relaxed text-foreground/90 font-medium">
            {resultAiSummary}
          </p>
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
              <h3 className="mt-2 text-xl font-semibold tracking-[-.035em]">Extracted Information &amp; Inline Correction</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Edit any field below to trigger immediate, deterministic re-evaluation of statutory rules.
              </p>
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
          <div className="mt-4">
            {inspection.declarations.map((declaration) => (
              <DeclarationRow
                key={declaration.field}
                declaration={declaration}
                inspectionId={inspection.id}
                onFactUpdated={(_field, _val, refreshed) => {
                  if (refreshed && onInspectionUpdated) {
                    onInspectionUpdated(fromInspectionRow(refreshed));
                  }
                }}
              />
            ))}
          </div>
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

        {/* Escalation notification banner if already reported */}
        {reportTracking && (
          <div className="flex items-center justify-between rounded-2xl border border-destructive/40 bg-destructive/10 p-3.5 text-xs">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-destructive" />
              <span>
                Statutory Docket filed: <strong>{reportTracking.caseId}</strong> (Tracking ID: {reportTracking.reportId})
              </span>
            </div>
            <span className="font-bold text-destructive text-[11px]">SUBMITTED TO AUTHORITY</span>
          </div>
        )}

        {/* Compact Action Tablets / Command Strip */}
        <section className="rounded-2xl border border-border/70 bg-card p-3 sm:p-4 shadow-xs">
          <div className="flex items-center justify-between border-b border-border/50 pb-2 mb-3">
            <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
              Inspection Actions &amp; Regulatory Services
            </p>
            <span className="text-[10px] text-muted-foreground">6 available actions</span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {/* 1. Save Inspection */}
            <button
              type="button"
              onClick={onSave}
              disabled={inspection.saved}
              className={`group flex flex-col justify-between rounded-xl border p-3 text-left transition ${
                inspection.saved
                  ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400 cursor-default"
                  : "border-border/80 bg-background hover:border-brand/60 hover:bg-brand/5 shadow-xs"
              }`}
            >
              <div className="flex w-full items-center justify-between">
                <div className={`flex h-7 w-7 items-center justify-center rounded-lg ${inspection.saved ? "bg-emerald-500/15 text-emerald-600" : "bg-brand/10 text-brand"}`}>
                  <BadgeCheck className="h-4 w-4" />
                </div>
                {inspection.saved && (
                  <span className="rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase text-emerald-600 dark:text-emerald-400">
                    Saved
                  </span>
                )}
              </div>
              <div className="mt-2.5">
                <p className="text-xs font-bold leading-snug text-foreground">
                  {inspection.saved ? "Inspection Saved" : "Save Inspection"}
                </p>
                <p className="mt-0.5 text-[10px] text-muted-foreground truncate">
                  {inspection.saved ? "In database" : "Record findings"}
                </p>
              </div>
            </button>

            {/* 2. View Evidence */}
            <button
              type="button"
              onClick={onOpenEvidence}
              className="group flex flex-col justify-between rounded-xl border border-border/80 bg-background p-3 text-left shadow-xs hover:border-brand/60 hover:bg-brand/5 transition"
            >
              <div className="flex w-full items-center justify-between">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand/10 text-brand">
                  <ScanLine className="h-4 w-4" />
                </div>
                <span className="text-[10px] font-mono text-muted-foreground">Vector</span>
              </div>
              <div className="mt-2.5">
                <p className="text-xs font-bold leading-snug text-foreground">View Evidence</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground truncate">Visual bboxes</p>
              </div>
            </button>

            {/* 3. Report Preview */}
            <button
              type="button"
              onClick={onOpenReport}
              className="group flex flex-col justify-between rounded-xl border border-border/80 bg-background p-3 text-left shadow-xs hover:border-brand/60 hover:bg-brand/5 transition"
            >
              <div className="flex w-full items-center justify-between">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand/10 text-brand">
                  <FileText className="h-4 w-4" />
                </div>
                <span className="text-[10px] font-mono text-muted-foreground">PDF</span>
              </div>
              <div className="mt-2.5">
                <p className="text-xs font-bold leading-snug text-foreground">Report Preview</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground truncate">Statutory docket</p>
              </div>
            </button>

            {/* 4. Escalate to Authority */}
            <button
              type="button"
              onClick={() => setShowReportModal(true)}
              className="group flex flex-col justify-between rounded-xl border border-destructive/30 bg-background p-3 text-left shadow-xs hover:border-destructive hover:bg-destructive/5 transition"
            >
              <div className="flex w-full items-center justify-between">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
                  <ShieldAlert className="h-4 w-4" />
                </div>
                <span className="rounded-full bg-destructive/10 px-1.5 py-0.5 text-[9px] font-bold text-destructive">
                  Docket
                </span>
              </div>
              <div className="mt-2.5">
                <p className="text-xs font-bold leading-snug text-destructive">Escalate to Authority</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground truncate">Formal violation</p>
              </div>
            </button>

            {/* 5. Package Integrity */}
            <button
              type="button"
              onClick={() => setShowIntegrityModal(true)}
              className="group flex flex-col justify-between rounded-xl border border-border/80 bg-background p-3 text-left shadow-xs hover:border-brand/60 hover:bg-brand/5 transition"
            >
              <div className="flex w-full items-center justify-between">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand/10 text-brand">
                  <PackageCheck className="h-4 w-4" />
                </div>
                <span className="rounded-full bg-brand/10 px-1.5 py-0.5 text-[9px] font-bold text-brand">
                  CV Match
                </span>
              </div>
              <div className="mt-2.5">
                <p className="text-xs font-bold leading-snug text-foreground">Package Integrity</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground truncate">Reference check</p>
              </div>
            </button>

            {/* 6. Departmental Cross-Verification */}
            <button
              type="button"
              onClick={() => setShowDepartmentalModal(true)}
              className="group flex flex-col justify-between rounded-xl border border-border/80 bg-background p-3 text-left shadow-xs hover:border-brand/60 hover:bg-brand/5 transition"
            >
              <div className="flex w-full items-center justify-between">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand/10 text-brand">
                  <Building2 className="h-4 w-4" />
                </div>
                <span className="rounded-full bg-brand/10 px-1.5 py-0.5 text-[9px] font-bold text-brand">
                  4+ Bodies
                </span>
              </div>
              <div className="mt-2.5">
                <p className="text-xs font-bold leading-snug text-foreground">Departmental Cross-Verification</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground truncate">FSSAI, CDSCO, BIS, BEE</p>
              </div>
            </button>
          </div>
        </section>

        {/* USP 4: Manufacturer / Marketer / Consumer Care Contact */}
        <ManufacturerContactSection inspection={inspection} />

        {/* Modal: Escalate to Authority */}
        {showReportModal && (
          <ConsumerReportModal
            inspection={inspection}
            onClose={() => setShowReportModal(false)}
            onSuccess={(cId, rId) => {
              setReportTracking({ caseId: cId, reportId: rId });
              setShowReportModal(false);
            }}
          />
        )}

        {/* Modal: Package Integrity */}
        {showIntegrityModal && (
          <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 backdrop-blur-xs p-3 sm:p-6 animate-in fade-in duration-150">
            <div className="relative w-full max-w-5xl rounded-2xl border border-border/80 bg-card p-4 sm:p-6 shadow-2xl space-y-4 max-h-[92vh] overflow-y-auto">
              <div className="flex items-center justify-between border-b border-border/60 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand/10 text-brand">
                    <PackageCheck className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">Package Integrity Verification</h3>
                    <p className="text-xs text-muted-foreground">Comparative cross-check against reference standard packaging</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setShowIntegrityModal(false)}
                  className="rounded-xl border border-border p-2 text-muted-foreground hover:bg-muted hover:text-foreground transition"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <PackageIntegrityCard
                inspectionId={inspection.id}
                productId={inspection.productId}
                productName={inspection.product}
                initialData={inspection.packageIntegrity}
                onSave={(savedReport) => {
                  if (onInspectionUpdated) {
                    onInspectionUpdated({
                      ...inspection,
                      packageIntegrity: savedReport,
                      integrityStatus: savedReport.status,
                    });
                  }
                }}
              />

              <div className="flex items-center justify-between border-t border-border/60 pt-3">
                <p className="text-xs text-muted-foreground">
                  Saved package integrity audits are retained and included in the certified inspection report.
                </p>
                <button
                  type="button"
                  onClick={() => setShowIntegrityModal(false)}
                  className="rounded-xl border border-border px-4 py-2 text-xs font-semibold hover:bg-muted"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Modal: Departmental Regulatory Cross-Verification */}
        {showDepartmentalModal && (
          <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 backdrop-blur-xs p-3 sm:p-6 animate-in fade-in duration-150">
            <div className="relative w-full max-w-5xl rounded-2xl border border-border/80 bg-card p-4 sm:p-6 shadow-2xl space-y-4 max-h-[92vh] overflow-y-auto">
              <div className="flex items-center justify-between border-b border-border/60 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand/10 text-brand">
                    <Building2 className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">Departmental Regulatory Cross-Verification</h3>
                    <p className="text-xs text-muted-foreground">Multi-agency regulatory license validation (FSSAI, CDSCO, BIS, BEE)</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setShowDepartmentalModal(false)}
                  className="rounded-xl border border-border p-2 text-muted-foreground hover:bg-muted hover:text-foreground transition"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <DepartmentalCrossVerificationCard
                inspectionId={inspection.id}
                category={inspection.category}
                productName={inspection.product}
              />
            </div>
          </div>
        )}
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


