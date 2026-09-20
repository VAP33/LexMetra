import { useEffect, useState } from "react";
import {
  LoaderCircle,
  X,
} from "lucide-react";
import {
  listAuthorityCases,
  takeAuthorityCaseAction,
  type AuthorityCaseData,
} from "@/lib/api-client";

export function AuthorityDashboardView({ onBack }: { onBack: () => void }) {
  const [cases, setCases] = useState<AuthorityCaseData[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [selectedCase, setSelectedCase] = useState<AuthorityCaseData | null>(null);
  const [actionModal, setActionModal] = useState<string | null>(null); // "SHOW_CAUSE_NOTICE", "SEIZURE_ORDERED", "CLOSED"
  const [actionNotes, setActionNotes] = useState("");
  const [actionClause, setActionClause] = useState("Section 36(1) of Legal Metrology Act, 2009");
  const [submittingAction, setSubmittingAction] = useState(false);

  function loadCases() {
    setLoading(true);
    listAuthorityCases({ status: statusFilter !== "ALL" ? statusFilter : undefined })
      .then((res) => {
        setCases(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }

  useEffect(() => {
    loadCases();
  }, [statusFilter]);

  async function handleTakeAction() {
    if (!selectedCase || !actionModal) return;
    setSubmittingAction(true);
    try {
      const updated = await takeAuthorityCaseAction(selectedCase.case_id, {
        action_type: actionModal,
        notes: actionNotes.trim() || `Statutory action recorded: ${actionModal}`,
        statutory_clause: actionClause,
      });
      setSelectedCase(updated);
      setActionModal(null);
      setActionNotes("");
      loadCases();
    } catch (e: any) {
      alert("Failed to record officer action: " + e?.message);
    } finally {
      setSubmittingAction(false);
    }
  }

  const counts = {
    total: cases.length,
    highPriority: cases.filter((c) => c.priority === "HIGH").length,
    submitted: cases.filter((c) => c.status === "SUBMITTED").length,
    notices: cases.filter((c) => c.status === "NOTICE_ISSUED").length,
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border/70 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-destructive/10 border border-destructive/20 px-2.5 py-0.5 text-[10px] font-bold text-destructive">
              Official Enforcement Channel
            </span>
            <span className="text-xs text-muted-foreground">Department of Consumer Affairs</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-foreground">
            Legal Metrology & FSSAI Authority Enforcement Queue
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Direct statutory escalation dockets filed by field inspectors and consumers under LM Act 2009.
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-bold text-slate-800 hover:bg-slate-50 hover:text-black transition shadow-xs"
        >
          Back to home
        </button>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-2xl border border-border/70 bg-card p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Active Dockets</p>
          <p className="mt-1 text-2xl font-bold text-foreground">{counts.total}</p>
          <span className="text-[11px] text-muted-foreground">In enforcement queue</span>
        </div>
        <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-destructive">High Priority</p>
          <p className="mt-1 text-2xl font-bold text-destructive">{counts.highPriority}</p>
          <span className="text-[11px] text-muted-foreground">Violations & Alterations</span>
        </div>
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-amber-600">New Inquiries</p>
          <p className="mt-1 text-2xl font-bold text-amber-600">{counts.submitted}</p>
          <span className="text-[11px] text-muted-foreground">Awaiting assignment</span>
        </div>
        <div className="rounded-2xl border border-brand/30 bg-brand/5 p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-brand">Notices Issued</p>
          <p className="mt-1 text-2xl font-bold text-brand">{counts.notices}</p>
          <span className="text-[11px] text-muted-foreground">Form 4 Show Cause</span>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border/60 pb-3">
        {["ALL", "SUBMITTED", "UNDER_REVIEW", "NOTICE_ISSUED", "INVESTIGATION_ORDERED", "RESOLVED"].map((st) => (
          <button
            key={st}
            type="button"
            onClick={() => setStatusFilter(st)}
            className={`rounded-xl px-3 py-1.5 text-xs font-bold transition shadow-xs ${
              statusFilter === st
                ? "bg-purple-700 text-white shadow-xs"
                : "bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 hover:text-black"
            }`}
          >
            {st.replace("_", " ")}
          </button>
        ))}
      </div>

      {/* Cases List */}
      {loading ? (
        <div className="flex items-center justify-center p-12 text-muted-foreground">
          <LoaderCircle className="h-6 w-6 animate-spin text-brand mr-2" /> Loading authority dockets…
        </div>
      ) : cases.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border/70 p-12 text-center text-muted-foreground">
          No cases matching '{statusFilter}'.
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {cases.map((c) => (
            <div
              key={c.case_id}
              onClick={() => setSelectedCase(c)}
              className="cursor-pointer rounded-2xl border border-border/70 bg-card p-5 shadow-xs transition-all hover:border-brand hover:shadow-md space-y-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-muted-foreground">{c.case_id}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                    c.priority === "HIGH" ? "bg-red-500/10 text-red-500" : "bg-blue-500/10 text-blue-500"
                  }`}
                >
                  {c.priority} PRIORITY
                </span>
              </div>

              <div>
                <h3 className="font-bold text-foreground line-clamp-1">{c.product_name}</h3>
                <p className="text-xs text-muted-foreground mt-0.5">{c.issue_category}</p>
              </div>

              <div className="rounded-xl bg-muted/50 p-2.5 text-[11px] space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">LMPC Verdict:</span>
                  <span className={`font-bold ${c.lmpc_verdict === "VIOLATION" ? "text-destructive" : "text-amber-500"}`}>
                    {c.lmpc_verdict}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">FSSAI Status:</span>
                  <span className="font-semibold text-foreground">{c.fssai_status || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Reporter:</span>
                  <span className="text-foreground">{c.reporter_type} ({c.reporter_name})</span>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-border/50 text-[11px]">
                <span className="rounded-md bg-brand-soft px-2 py-0.5 font-bold text-brand">
                  {c.status.replace("_", " ")}
                </span>
                <span className="text-muted-foreground">
                  {new Date(c.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Case Details Modal */}
      {selectedCase && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-2xl rounded-2xl border border-border/80 bg-card p-6 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-brand">{selectedCase.case_id}</span>
                  <span className="text-xs text-muted-foreground">Docket {selectedCase.report_id}</span>
                </div>
                <h2 className="text-lg font-bold text-foreground mt-0.5">{selectedCase.product_name}</h2>
              </div>
              <button
                type="button"
                onClick={() => setSelectedCase(null)}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 rounded-xl border border-border/70 bg-muted/40 p-3 text-xs">
              <div>
                <span className="block text-[10px] uppercase font-bold text-muted-foreground">LMPC Verdict</span>
                <span className="font-bold text-destructive">{selectedCase.lmpc_verdict}</span>
              </div>
              <div>
                <span className="block text-[10px] uppercase font-bold text-muted-foreground">FSSAI Status</span>
                <span className="font-semibold text-foreground">{selectedCase.fssai_status || "N/A"}</span>
              </div>
              <div>
                <span className="block text-[10px] uppercase font-bold text-muted-foreground">Integrity</span>
                <span className="font-semibold text-foreground">{selectedCase.integrity_status || "UNABLE TO VERIFY"}</span>
              </div>
              <div>
                <span className="block text-[10px] uppercase font-bold text-muted-foreground">Current Status</span>
                <span className="font-bold text-brand">{selectedCase.status.replace("_", " ")}</span>
              </div>
            </div>

            <div className="space-y-2 text-xs">
              <p className="font-bold text-muted-foreground uppercase tracking-wider">Complaint & Evidence Details</p>
              <p className="rounded-xl border border-border/60 bg-card p-3 leading-relaxed text-foreground">
                {selectedCase.details}
              </p>
              <div className="flex flex-wrap gap-4 text-muted-foreground pt-1">
                <span><strong>Retailer:</strong> {selectedCase.retailer_name || "N/A"}</span>
                <span><strong>Location:</strong> {selectedCase.location || "N/A"}</span>
                <span><strong>Reporter:</strong> {selectedCase.reporter_type} ({selectedCase.reporter_name})</span>
              </div>
            </div>

            {/* Statutory Action Timeline */}
            <div className="space-y-2 text-xs">
              <p className="font-bold text-muted-foreground uppercase tracking-wider">Statutory Case History & Audit Trail</p>
              <div className="divide-y divide-border/60 rounded-xl border border-border/60 bg-muted/30">
                {selectedCase.actions.map((act) => (
                  <div key={act.action_id} className="p-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-foreground">{act.action_type.replace("_", " ")}</span>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        {new Date(act.timestamp).toLocaleString("en-IN")}
                      </span>
                    </div>
                    <p className="text-muted-foreground">{act.notes}</p>
                    {act.statutory_clause && (
                      <span className="inline-block font-mono text-[10px] text-brand">
                        Authority: {act.statutory_clause} · Officer: @{act.officer_username}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Officer Actions Bar */}
            <div className="flex flex-wrap items-center justify-end gap-2 pt-3 border-t border-border/60">
              <button
                type="button"
                onClick={() => {
                  setActionModal("SHOW_CAUSE_NOTICE");
                  setActionNotes("Form 4 Show Cause Notice issued to Packer under Section 36(1) of Legal Metrology Act, 2009 for missing mandatory declarations.");
                  setActionClause("Rule 6(1) & Section 36(1) LM Act");
                }}
                className="h-9 px-3.5 rounded-xl border border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-semibold text-xs hover:bg-amber-500/20"
              >
                Issue Show Cause Notice
              </button>
              <button
                type="button"
                onClick={() => {
                  setActionModal("SEIZURE_ORDERED");
                  setActionNotes("Seizure of non-standard packaged commodity ordered under Section 15 of Legal Metrology Act, 2009.");
                  setActionClause("Section 15 & 36 LM Act");
                }}
                className="h-9 px-3.5 rounded-xl border border-red-500/40 bg-red-500/10 text-red-500 font-semibold text-xs hover:bg-red-500/20"
              >
                Order Seizure & Investigation
              </button>
              <button
                type="button"
                onClick={() => {
                  setActionModal("CLOSED");
                  setActionNotes("Compliance verified / fine compounded; case closed.");
                  setActionClause("Section 48 (Compounding of Offences)");
                }}
                className="h-9 px-3.5 rounded-xl border border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold text-xs hover:bg-emerald-500/20"
              >
                Close Docket
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Confirmation Modal */}
      {actionModal && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-md rounded-2xl border border-border/80 bg-card p-6 shadow-2xl space-y-4 text-xs">
            <h3 className="text-sm font-bold text-foreground">Record Statutory Enforcement Action</h3>
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Action Type</label>
              <input
                disabled
                value={actionModal}
                className="h-9 w-full rounded-xl border border-border bg-muted px-3 text-xs font-mono"
              />
            </div>
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Statutory Clause / Rule</label>
              <input
                value={actionClause}
                onChange={(e) => setActionClause(e.target.value)}
                className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs font-mono"
              />
            </div>
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Officer Notes / Order Details</label>
              <textarea
                rows={3}
                value={actionNotes}
                onChange={(e) => setActionNotes(e.target.value)}
                className="w-full rounded-xl border border-border bg-background p-3 text-xs outline-none focus:border-brand"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setActionModal(null)}
                className="h-9 px-4 rounded-xl border border-border bg-background font-semibold text-muted-foreground"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleTakeAction}
                disabled={submittingAction}
                className="h-9 px-4 rounded-xl bg-brand text-brand-foreground font-semibold flex items-center gap-1.5"
              >
                {submittingAction && <LoaderCircle className="h-3.5 w-3.5 animate-spin" />}
                Confirm & Seal Order
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
