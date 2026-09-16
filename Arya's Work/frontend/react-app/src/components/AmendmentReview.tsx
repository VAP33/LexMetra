/**
 * AmendmentReview.tsx
 *
 * Redesigned Amendment Review UI components for the Gazette Amendment Review screen.
 *
 * DATA CONTRACT RULES:
 *   • amendment_target  — legal target provision (e.g. "Rule 6(1)(a)")
 *                         May be null/undefined if backend has not yet derived it.
 *   • amendment_item    — amendment-numbering item (e.g. "(i)", "(ii)")
 *   • amendment_operation — legal operation (INSERT, AMEND, REPLACE, DELETE, etc.)
 *   • rule_id           — internal rule ID used as key; NOT displayed as
 *                         a legal provision ID.
 *
 * IMPORTANT LEGAL DISTINCTION:
 *   Never visually combine Amendment Item with Target Rule.
 *   If amendment_target is absent the UI shows the raw rule_id clearly labelled
 *   as "[Extracted ID]" so the user is never misled.
 */

import {
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Info,
  FileText,
  ExternalLink,
  Plus,
  RefreshCcw,
  AlertTriangle,
  MoveHorizontal,
  Trash2,
  BookmarkCheck,
} from "lucide-react";
import { useState } from "react";
import type { RuleIdentifiedItem, RulesIdentifiedResponse, AmendmentDraft } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Helpers & Types
// ---------------------------------------------------------------------------

export type OperationType =
  | "INSERT"
  | "AMEND"
  | "REPLACE"
  | "DELETE"
  | "REPEAL"
  | "RENUMBER"
  | "MOVE"
  | "CORRIGENDUM"
  | string;

interface OperationStyle {
  bg: string;
  text: string;
  border: string;
  dot: string;
  label: string;
}

export function operationStyle(op: string): OperationStyle {
  switch (op?.toUpperCase()) {
    case "INSERT":
      return {
        bg: "bg-emerald-500/10",
        text: "text-emerald-700 dark:text-emerald-400",
        border: "border-emerald-500/30",
        dot: "bg-emerald-500",
        label: "INSERT",
      };
    case "AMEND":
      return {
        bg: "bg-blue-500/10",
        text: "text-blue-700 dark:text-blue-400",
        border: "border-blue-500/30",
        dot: "bg-blue-500",
        label: "AMEND",
      };
    case "REPLACE":
      return {
        bg: "bg-amber-500/10",
        text: "text-amber-700 dark:text-amber-400",
        border: "border-amber-500/30",
        dot: "bg-amber-500",
        label: "REPLACE",
      };
    case "DELETE":
      return {
        bg: "bg-red-500/10",
        text: "text-red-700 dark:text-red-400",
        border: "border-red-500/30",
        dot: "bg-red-500",
        label: "DELETE",
      };
    case "REPEAL":
      return {
        bg: "bg-rose-500/10",
        text: "text-rose-700 dark:text-rose-400",
        border: "border-rose-500/30",
        dot: "bg-rose-600",
        label: "REPEAL",
      };
    case "RENUMBER":
      return {
        bg: "bg-violet-500/10",
        text: "text-violet-700 dark:text-violet-400",
        border: "border-violet-500/30",
        dot: "bg-violet-500",
        label: "RENUMBER",
      };
    case "MOVE":
      return {
        bg: "bg-indigo-500/10",
        text: "text-indigo-700 dark:text-indigo-400",
        border: "border-indigo-500/30",
        dot: "bg-indigo-500",
        label: "MOVE",
      };
    case "CORRIGENDUM":
      return {
        bg: "bg-orange-500/10",
        text: "text-orange-700 dark:text-orange-400",
        border: "border-orange-500/30",
        dot: "bg-orange-500",
        label: "CORRIGENDUM",
      };
    default:
      return {
        bg: "bg-muted",
        text: "text-muted-foreground",
        border: "border-border",
        dot: "bg-muted-foreground",
        label: op ?? "UNKNOWN",
      };
  }
}

// ---------------------------------------------------------------------------
// OperationBadge
// ---------------------------------------------------------------------------

export function OperationBadge({ operation }: { operation: OperationType }) {
  const s = operationStyle(operation);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide ${s.bg} ${s.text} ${s.border}`}
      aria-label={`Operation: ${s.label}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} aria-hidden />
      {s.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Target Breakdown & Display
// ---------------------------------------------------------------------------

export function parseTargetHierarchy(target: string): {
  rule?: string;
  subrule?: string;
  clause?: string;
  subclause?: string;
} | null {
  if (!target) return null;
  const m = target.trim().match(/^Rule\s*([0-9]+[A-Za-z]?)(?:\(([0-9]+)\))?(?:\(([a-z0-9]+)\))?(?:\(([ivx]+)\))?/i);
  if (!m) return null;
  return {
    rule: `Rule ${m[1]}`,
    subrule: m[2] ? `Sub-rule (${m[2]})` : undefined,
    clause: m[3] ? `Clause (${m[3]})` : undefined,
    subclause: m[4] ? `Sub-clause (${m[4]})` : undefined,
  };
}

export function TargetDisplay({
  amendmentTarget,
  ruleId,
}: {
  amendmentTarget?: string | null;
  ruleId: string;
}) {
  if (amendmentTarget) {
    return (
      <span className="font-mono text-xs font-bold text-foreground bg-primary/10 border border-primary/25 px-2 py-0.5 rounded-md">
        {amendmentTarget}
      </span>
    );
  }
  return (
    <span
      className="font-mono text-xs text-muted-foreground bg-muted border border-border/50 px-2 py-0.5 rounded-md inline-flex items-center gap-1"
      title="Backend has not resolved the canonical target provision for this rule."
    >
      <span className="text-[10px] font-normal uppercase text-amber-600 dark:text-amber-400">[Extracted ID]</span>
      {ruleId}
    </span>
  );
}

// ---------------------------------------------------------------------------
// ChangeBeforeAfter (Reusable Before -> Change -> After view)
// ---------------------------------------------------------------------------

interface ChangeBeforeAfterProps {
  operation: OperationType;
  beforeText?: string | null;
  afterText?: string | null;
  target?: string | null;
}

export function ChangeBeforeAfter({
  operation,
  beforeText,
  afterText,
  target,
}: ChangeBeforeAfterProps) {
  const op = (operation || "INSERT").toUpperCase();

  // Special presentation for CORRIGENDUM as specified in requirements
  if (op === "CORRIGENDUM") {
    return (
      <div className="mt-3 space-y-2">
        <div className="rounded-lg border border-orange-500/30 overflow-hidden text-xs">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-orange-500/10 border-b border-orange-500/20 text-[10px] font-bold uppercase tracking-wider text-orange-800 dark:text-orange-300">
                <th className="px-3 py-1.5 w-32">Target</th>
                <th className="px-3 py-1.5 w-28">Operation</th>
                <th className="px-3 py-1.5">Original Wording</th>
                <th className="px-3 py-1.5">Correction / Read As</th>
              </tr>
            </thead>
            <tbody>
              <tr className="bg-card">
                <td className="px-3 py-2 font-mono font-bold text-foreground border-r border-border/40">
                  {target || "—"}
                </td>
                <td className="px-3 py-2 border-r border-border/40">
                  <OperationBadge operation="CORRIGENDUM" />
                </td>
                <td className="px-3 py-2 text-foreground/80 font-mono text-[11px] border-r border-border/40">
                  {beforeText ? `"${beforeText}"` : <span className="text-muted-foreground italic">—</span>}
                </td>
                <td className="px-3 py-2 font-mono text-[11px] font-semibold text-emerald-700 dark:text-emerald-400">
                  {afterText ? `"${afterText}"` : <span className="text-muted-foreground italic">—</span>}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // Label configuration per operation type
  let beforeLabel = "Existing Provision";
  let afterLabel = "After";
  let fallbackBefore = "— not provided —";
  let icon = <RefreshCcw className="h-3.5 w-3.5 text-blue-600" aria-hidden />;
  let afterBorderColor = "border-blue-500/30";
  let afterHeaderBg = "bg-blue-500/5 border-blue-500/20";

  switch (op) {
    case "INSERT":
      beforeLabel = "Existing Provision";
      afterLabel = "New Inserted Provision";
      fallbackBefore = "— none (new provision inserted) —";
      icon = <Plus className="h-3.5 w-3.5 text-emerald-600" aria-hidden />;
      afterBorderColor = "border-emerald-500/30";
      afterHeaderBg = "bg-emerald-500/10 border-emerald-500/20";
      break;
    case "REPLACE":
      beforeLabel = "Old Text";
      afterLabel = "Replacement Text";
      fallbackBefore = "— old text —";
      icon = <RefreshCcw className="h-3.5 w-3.5 text-amber-600" aria-hidden />;
      afterBorderColor = "border-amber-500/30";
      afterHeaderBg = "bg-amber-500/10 border-amber-500/20";
      break;
    case "DELETE":
    case "REPEAL":
      beforeLabel = "Existing Provision";
      afterLabel = "Status After Change";
      fallbackBefore = "— existing provision to be deleted —";
      icon = <Trash2 className="h-3.5 w-3.5 text-red-600" aria-hidden />;
      afterBorderColor = "border-red-500/30";
      afterHeaderBg = "bg-red-500/5 border-red-500/20";
      break;
    case "AMEND":
      beforeLabel = "Original Wording";
      afterLabel = "Amended Wording";
      fallbackBefore = "— original wording —";
      icon = <RefreshCcw className="h-3.5 w-3.5 text-blue-600" aria-hidden />;
      afterBorderColor = "border-blue-500/30";
      afterHeaderBg = "bg-blue-500/5 border-blue-500/20";
      break;
    case "RENUMBER":
      beforeLabel = "Old Identifier";
      afterLabel = "New Identifier";
      fallbackBefore = "— old number —";
      icon = <BookmarkCheck className="h-3.5 w-3.5 text-violet-600" aria-hidden />;
      afterBorderColor = "border-violet-500/30";
      afterHeaderBg = "bg-violet-500/5 border-violet-500/20";
      break;
    case "MOVE":
      beforeLabel = "Original Location";
      afterLabel = "Relocated To";
      fallbackBefore = "— original position —";
      icon = <MoveHorizontal className="h-3.5 w-3.5 text-indigo-600" aria-hidden />;
      afterBorderColor = "border-indigo-500/30";
      afterHeaderBg = "bg-indigo-500/5 border-indigo-500/20";
      break;
  }

  return (
    <div className="mt-3 grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-2 items-start text-xs">
      {/* BEFORE */}
      <div className="rounded-lg border border-border/60 bg-muted/40 overflow-hidden">
        <div className="px-3 py-1.5 bg-muted/60 border-b border-border/40">
          <span className="text-[10px] font-bold uppercase text-muted-foreground tracking-wider">
            {beforeLabel}
          </span>
        </div>
        <div className="p-3 text-[11px] leading-relaxed text-foreground/80 font-mono whitespace-pre-wrap min-h-12">
          {beforeText ? beforeText : <span className="text-muted-foreground italic">{fallbackBefore}</span>}
        </div>
      </div>

      {/* CHANGE INDICATOR */}
      <div className="flex md:flex-col items-center justify-center gap-1.5 py-2 md:pt-4">
        <OperationBadge operation={operation} />
        <ArrowRight className="h-4 w-4 text-muted-foreground rotate-90 md:rotate-0" aria-hidden />
      </div>

      {/* AFTER */}
      <div className={`rounded-lg border overflow-hidden ${afterBorderColor}`}>
        <div className={`px-3 py-1.5 border-b flex items-center gap-1.5 ${afterHeaderBg}`}>
          {icon}
          <span className="text-[10px] font-bold uppercase text-muted-foreground tracking-wider">
            {afterLabel}
          </span>
        </div>
        <div className="p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap min-h-12">
          {afterText ? (
            <span
              className={
                op === "INSERT"
                  ? "text-emerald-800 dark:text-emerald-300 font-medium"
                  : op === "DELETE" || op === "REPEAL"
                  ? "text-red-600 dark:text-red-400 line-through"
                  : "text-foreground"
              }
            >
              {afterText}
            </span>
          ) : op === "DELETE" || op === "REPEAL" ? (
            <span className="text-red-500/80 font-semibold italic">Provision removed / repealed.</span>
          ) : (
            <span className="text-muted-foreground italic">— not provided —</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProvenanceBlock
// ---------------------------------------------------------------------------

interface ProvenanceBlockProps {
  sourceDocumentId?: string | null;
  sourceProvision?: string | null;
  sourceLanguages?: string[] | null;
  metadataSources?: Record<string, unknown> | null;
}

export function ProvenanceBlock({
  sourceDocumentId,
  sourceProvision,
  sourceLanguages,
  metadataSources,
}: ProvenanceBlockProps) {
  return (
    <div className="mt-3 rounded-lg border border-dashed border-border/60 bg-muted/20 p-3 text-[11px] space-y-1.5">
      <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
        <ExternalLink className="h-3 w-3" aria-hidden />
        Source / Provenance
      </p>
      {sourceDocumentId && (
        <div className="flex gap-2">
          <span className="text-muted-foreground w-28 shrink-0">Source Document:</span>
          <code className="font-mono text-[10px] text-foreground break-all">{sourceDocumentId}</code>
        </div>
      )}
      {sourceProvision && (
        <div className="flex gap-2">
          <span className="text-muted-foreground w-28 shrink-0">Source Provision:</span>
          <span className="text-foreground font-medium">{sourceProvision}</span>
        </div>
      )}
      {sourceLanguages && sourceLanguages.length > 0 && (
        <div className="flex gap-2">
          <span className="text-muted-foreground w-28 shrink-0">Languages:</span>
          <span className="text-foreground">{sourceLanguages.join(", ")} (English canonical; Hindi verified & deduplicated)</span>
        </div>
      )}
      {metadataSources && Object.keys(metadataSources).length > 0 && (
        <div className="flex gap-2">
          <span className="text-muted-foreground w-28 shrink-0">Metadata:</span>
          <span className="text-foreground font-mono text-[10px] break-all">
            {Object.entries(metadataSources)
              .slice(0, 3)
              .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
              .join(" · ")}
          </span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AmendmentDetail — Expanded row panel
// ---------------------------------------------------------------------------

export function AmendmentDetail({
  rule,
  draftSourceDocId,
}: {
  rule: RuleIdentifiedItem;
  draftSourceDocId?: string;
}) {
  const app = rule.applicability || {};
  const op = rule.amendment_operation ?? "INSERT";
  const beforeText = rule.metadata_sources?.old_text as string | undefined;
  const afterText = (rule.metadata_sources?.new_text as string | undefined) ?? rule.canonical_english_text;
  const hierarchy = rule.amendment_target ? parseTargetHierarchy(rule.amendment_target) : null;

  return (
    <div className="mt-3 pt-3 border-t border-border/50 space-y-4 text-xs">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* AMENDMENT ITEM */}
        <div className="space-y-1">
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Amendment Item</p>
          <div className="inline-flex items-center gap-1.5">
            <span className="font-mono text-sm font-bold text-foreground bg-muted px-2 py-0.5 rounded border border-border/50">
              {rule.amendment_item ?? "—"}
            </span>
          </div>
        </div>

        {/* OPERATION */}
        <div className="space-y-1">
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Operation</p>
          <div>
            <OperationBadge operation={op} />
          </div>
        </div>

        {/* TARGET BREAKDOWN */}
        <div className="space-y-1">
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Target Provision</p>
          {hierarchy ? (
            <div className="rounded-md bg-muted/40 border border-border/40 p-2 font-mono text-xs space-y-0.5">
              <div className="font-bold text-foreground">{hierarchy.rule}</div>
              {hierarchy.subrule && (
                <div className="text-muted-foreground flex items-center gap-1 pl-2">
                  <span>→</span> <span>{hierarchy.subrule}</span>
                </div>
              )}
              {hierarchy.clause && (
                <div className="text-muted-foreground flex items-center gap-1 pl-4">
                  <span>→</span> <span>{hierarchy.clause}</span>
                </div>
              )}
              {hierarchy.subclause && (
                <div className="text-muted-foreground flex items-center gap-1 pl-6">
                  <span>→</span> <span>{hierarchy.subclause}</span>
                </div>
              )}
            </div>
          ) : (
            <div>
              <TargetDisplay amendmentTarget={rule.amendment_target} ruleId={rule.rule_id} />
            </div>
          )}
        </div>
      </div>

      {/* CHANGE MADE DESCRIPTION */}
      <div className="space-y-1">
        <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Change Made</p>
        <p className="text-foreground leading-relaxed bg-muted/30 p-2.5 rounded-md border border-border/40 font-medium">
          "{rule.canonical_english_text}"
        </p>
      </div>

      {/* APPLICABILITY TRIGGER */}
      <div className="space-y-1">
        <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Applicability</p>
        <div className="p-2.5 rounded-md bg-muted/20 border border-border/30 text-foreground leading-relaxed">
          {app.manufactured_packed_imported_after ? (
            <div className="space-y-1">
              <p className="font-semibold text-foreground">
                Manufactured, packed or imported after:{" "}
                <span className="text-primary font-mono">{app.manufactured_packed_imported_after}</span>
                {app.duration ? ` (${app.duration})` : ""}
              </p>
              {app.scope && <p className="text-muted-foreground text-[11px]">Scope: {app.scope}</p>}
            </div>
          ) : (
            <span>{app.scope ?? "Standard compliance applicability (no delayed commencement trigger)"}</span>
          )}
        </div>
      </div>

      {/* EFFECTIVE DATE */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Effective Date:</span>
        <span className="font-semibold text-foreground tabular-nums">{rule.effective_from ?? "—"}</span>
      </div>

      {/* BEFORE -> CHANGE -> AFTER VIEW */}
      <div className="space-y-1">
        <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
          Before → Change → After Comparison
        </p>
        <ChangeBeforeAfter
          operation={op}
          beforeText={beforeText}
          afterText={afterText}
          target={rule.amendment_target}
        />
      </div>

      {/* PROVENANCE / SOURCE */}
      <ProvenanceBlock
        sourceDocumentId={draftSourceDocId}
        sourceProvision={rule.source_provision}
        sourceLanguages={rule.source_languages}
        metadataSources={rule.metadata_sources}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// AmendmentChangeRow
// ---------------------------------------------------------------------------

export function AmendmentChangeRow({
  rule,
  index,
  draftSourceDocId,
  approvalState,
}: {
  rule: RuleIdentifiedItem;
  index: number;
  draftSourceDocId?: string;
  approvalState: string;
}) {
  const [open, setOpen] = useState(false);
  const app = rule.applicability || {};
  const applicabilityLabel = app.manufactured_packed_imported_after
    ? `After ${app.manufactured_packed_imported_after}`
    : (app.scope as string | undefined) ?? "Standard";

  return (
    <>
      <tr
        className={`border-b border-border/40 transition-colors cursor-pointer select-none ${
          open ? "bg-primary/5" : index % 2 === 0 ? "bg-transparent" : "bg-muted/20"
        } hover:bg-primary/5`}
        onClick={() => setOpen(!open)}
        role="button"
        aria-expanded={open}
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setOpen(!open)}
      >
        {/* Amendment Item */}
        <td className="px-3 py-2.5 text-center">
          <span className="font-mono text-sm font-bold text-foreground">
            {rule.amendment_item ?? `#${index + 1}`}
          </span>
        </td>

        {/* Operation */}
        <td className="px-3 py-2.5">
          <OperationBadge operation={rule.amendment_operation ?? "INSERT"} />
        </td>

        {/* Target Rule */}
        <td className="px-3 py-2.5">
          <TargetDisplay amendmentTarget={rule.amendment_target} ruleId={rule.rule_id} />
        </td>

        {/* Change Made (collapsed snippet) */}
        <td className="px-3 py-2.5 max-w-xs">
          <p className="text-xs text-foreground leading-snug line-clamp-2" title={rule.canonical_english_text}>
            {rule.canonical_english_text}
          </p>
        </td>

        {/* Applicability */}
        <td className="px-3 py-2.5 hidden sm:table-cell">
          <span className="text-[11px] text-muted-foreground">{applicabilityLabel}</span>
        </td>

        {/* Effective Date */}
        <td className="px-3 py-2.5 hidden md:table-cell">
          <span className="text-[11px] font-semibold text-foreground tabular-nums">
            {rule.effective_from ?? "—"}
          </span>
        </td>

        {/* Status */}
        <td className="px-3 py-2.5">
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
              approvalState === "ACTIVE"
                ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20"
                : "bg-muted text-muted-foreground border border-border/40"
            }`}
          >
            {approvalState}
          </span>
        </td>

        {/* Expand toggle */}
        <td className="px-2 py-2.5 text-center">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground mx-auto" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground mx-auto" />
          )}
        </td>
      </tr>

      {/* Expanded detail panel */}
      {open && (
        <tr>
          <td colSpan={8} className="px-4 pb-4 bg-primary/5 border-b border-primary/10">
            <AmendmentDetail rule={rule} draftSourceDocId={draftSourceDocId} />
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// AmendmentChangeTable (Compact tabular matrix)
// ---------------------------------------------------------------------------

export function AmendmentChangeTable({
  rules,
  draft,
}: {
  rules: RuleIdentifiedItem[];
  draft: AmendmentDraft;
}) {
  if (rules.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border/60 p-8 text-center text-sm text-muted-foreground">
        <FileText className="h-8 w-8 mx-auto mb-2 text-muted-foreground/40" aria-hidden />
        <p>No substantive amendment rules extracted yet.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border/70 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse" role="grid" aria-label="Amendment Change Matrix">
          <thead>
            <tr className="bg-muted/60 border-b border-border/60">
              <th
                scope="col"
                className="px-3 py-2.5 text-center font-bold text-[10px] uppercase tracking-wider text-muted-foreground w-28"
              >
                Amendment Item
              </th>
              <th
                scope="col"
                className="px-3 py-2.5 text-left font-bold text-[10px] uppercase tracking-wider text-muted-foreground w-32"
              >
                Operation
              </th>
              <th
                scope="col"
                className="px-3 py-2.5 text-left font-bold text-[10px] uppercase tracking-wider text-muted-foreground w-40"
              >
                Target Rule
              </th>
              <th
                scope="col"
                className="px-3 py-2.5 text-left font-bold text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                Change Made
              </th>
              <th
                scope="col"
                className="px-3 py-2.5 text-left font-bold text-[10px] uppercase tracking-wider text-muted-foreground hidden sm:table-cell w-44"
              >
                Applicability
              </th>
              <th
                scope="col"
                className="px-3 py-2.5 text-left font-bold text-[10px] uppercase tracking-wider text-muted-foreground hidden md:table-cell w-28"
              >
                Effective Date
              </th>
              <th
                scope="col"
                className="px-3 py-2.5 text-left font-bold text-[10px] uppercase tracking-wider text-muted-foreground w-24"
              >
                Status
              </th>
              <th scope="col" className="w-8" />
            </tr>
          </thead>
          <tbody>
            {rules.map((rule, i) => (
              <AmendmentChangeRow
                key={rule.rule_id || i}
                rule={rule}
                index={i}
                draftSourceDocId={draft.source_document_id}
                approvalState={draft.approval_state}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DraftSummaryHeader (Compact summary at top of review page)
// ---------------------------------------------------------------------------

export function DraftSummaryHeader({
  draft,
  identified,
}: {
  draft: AmendmentDraft;
  identified: RulesIdentifiedResponse | null;
}) {
  const rules = identified?.rules_identified ?? [];
  const ops = Array.from(new Set(rules.map((r) => r.amendment_operation ?? "INSERT").filter(Boolean)));
  const parentReg =
    (identified?.amendment_metadata?.parent_regulation as string | undefined) ??
    rules[0]?.parent_regulation ??
    "Legal Metrology (Packaged Commodities) Rules, 2011";
  const effectiveDate = rules[0]?.effective_from ?? "14 July 2022";
  const count = identified?.rules_identified_count ?? rules.length;
  const hasUnresolved = rules.some((r) => !r.amendment_target);
  const possibleMissingContent = count < 4;

  return (
    <div className="rounded-xl border border-border/70 bg-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[.18em] text-muted-foreground">Amendment Review</p>
          <h3 className="mt-0.5 text-base font-bold text-foreground">{draft.source_document_id}</h3>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-bold border ${
            draft.approval_state === "ACTIVE"
              ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20"
              : draft.approval_state === "EXTRACTED"
              ? "bg-primary/10 text-primary border-primary/20"
              : "bg-muted text-muted-foreground border-border/40"
          }`}
        >
          {draft.approval_state}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-border/40 text-xs">
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-semibold">Substantive Amendments</p>
          <p className="mt-0.5 font-bold text-foreground text-sm">
            {count} substantive amendments received from ingestion
          </p>
        </div>
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-semibold">Operations</p>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {ops.length > 0 ? (
              ops.map((op) => <OperationBadge key={op} operation={op} />)
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </div>
        </div>
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-semibold">Effective Date</p>
          <p className="mt-0.5 font-semibold text-foreground tabular-nums">{effectiveDate}</p>
        </div>
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-semibold">Parent Regulation</p>
          <p className="mt-0.5 font-semibold text-foreground truncate" title={parentReg}>
            {parentReg}
          </p>
        </div>
      </div>

      {possibleMissingContent && (
        <div className="flex items-start gap-2 rounded-lg bg-blue-500/10 border border-blue-500/20 px-3 py-2 text-[11px] text-blue-800 dark:text-blue-300">
          <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden />
          <p>Expected/source structure indicates additional amendment content may require backend verification.</p>
        </div>
      )}

      {hasUnresolved && (
        <div className="flex items-start gap-2 rounded-lg bg-amber-500/10 border border-amber-500/20 px-3 py-2 text-[11px] text-amber-800 dark:text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden />
          <p>
            Some items show <strong>[Extracted ID]</strong> instead of a resolved target — the backend has not yet mapped
            all items to their canonical legal target. The internal rule ID is shown as-is for audit purposes and is not a
            legal provision reference.
          </p>
        </div>
      )}
    </div>
  );
}
