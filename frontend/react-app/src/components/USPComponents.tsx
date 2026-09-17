import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  Info,
  LoaderCircle,
  Mic,
  MicOff,
  Send,
  ShieldAlert,
  Sparkles,
  Volume2,
  X,
  XCircle,
} from "lucide-react";
import {
  getPackageIntegrity,
  getFssaiVerification,
  submitConsumerReport,
  listAuthorityCases,
  takeAuthorityCaseAction,
  askAssistant,
  synthesizeSpeech,
  type IntegrityReportData,
  type FssaiVerificationData,
  type AuthorityCaseData,
} from "@/lib/api-client";
import { type Inspection } from "@/lib/types";

// ===========================================================================
// USP 1: Package Integrity Verification Component
// ===========================================================================

export function PackageIntegrityCard({
  inspectionId,
  productId,
}: {
  inspectionId: string;
  productId?: string;
}) {
  const [data, setData] = useState<IntegrityReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPackageIntegrity(inspectionId)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || "Integrity verification unavailable");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [inspectionId]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-border/70 bg-card p-5">
        <div className="flex items-center gap-3">
          <LoaderCircle className="h-5 w-5 animate-spin text-brand" />
          <p className="text-sm text-muted-foreground">Evaluating Package Integrity against Brand Reference Catalog…</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-2xl border border-border/70 bg-card p-5">
        <div className="flex items-center gap-3">
          <Info className="h-5 w-5 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Package Integrity: Unable to verify catalog standard.</p>
        </div>
      </div>
    );
  }

  const isNoDiff = data.status === "NO SIGNIFICANT DIFFERENCE DETECTED";
  const isPotentialAlt = data.status === "POTENTIAL ALTERATION DETECTED";

  const statusBg = isNoDiff
    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
    : isPotentialAlt
    ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
    : "bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400";

  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">USP 1 · Computer Vision</p>
            <span className="rounded-full bg-brand/10 border border-brand/20 px-2 py-0.5 text-[10px] font-bold text-brand">
              Advisory Signal
            </span>
          </div>
          <h3 className="mt-1 text-xl font-semibold tracking-tight">Package Integrity Verification</h3>
        </div>
        <div className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold ${statusBg}`}>
          {isNoDiff ? (
            <Check className="h-3.5 w-3.5" />
          ) : isPotentialAlt ? (
            <AlertTriangle className="h-3.5 w-3.5" />
          ) : (
            <Info className="h-3.5 w-3.5" />
          )}
          {data.status}
        </div>
      </div>

      <p className="text-sm leading-6 text-foreground">{data.explanation}</p>

      {/* Comparison grid if reference is available */}
      {data.has_reference ? (
        <div className="rounded-xl border border-border/60 bg-muted/40 p-4 space-y-3">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">Catalog Comparison Method:</span>
            <span className="font-mono">{data.comparison_method}</span>
            <span className="font-semibold text-foreground">Visual Fidelity Score:</span>
            <span className="font-bold text-brand">{(data.confidence_score * 100).toFixed(0)}%</span>
          </div>

          {data.detected_differences.length > 0 ? (
            <div className="space-y-2 pt-2 border-t border-border/40">
              <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Detected Variations ({data.detected_differences.length})</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {data.detected_differences.map((diff, i) => (
                  <div key={i} className="flex items-start gap-2 rounded-lg border border-border/70 bg-card p-2.5 text-xs">
                    <span className={`h-2 w-2 rounded-full mt-1 shrink-0 ${diff.severity === "HIGH" ? "bg-red-500" : "bg-amber-500"}`} />
                    <div>
                      <p className="font-medium text-foreground">{diff.description}</p>
                      <p className="text-[10px] text-muted-foreground">BBox: [{diff.bbox.join(", ")}] · Severity: {diff.severity}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
              <Check className="h-4 w-4" /> Packaging geometry, typography, and color histograms match genuine SKU standard.
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border/80 bg-muted/20 p-4 text-xs text-muted-foreground leading-relaxed">
          <p className="font-medium text-foreground mb-1">No Authorized Golden Reference in Brand Catalog</p>
          SKU '{productId || "Unknown"}' does not have a pre-registered digital golden master. LexMetra truthfully reports <strong className="text-foreground">UNABLE TO VERIFY</strong> rather than assuming compliance or tampering.
        </div>
      )}

      <p className="text-[11px] text-muted-foreground italic leading-4 border-t border-border/40 pt-2">
        {data.disclaimer}
      </p>
    </section>
  );
}

// ===========================================================================
// USP 2: FSSAI Cross-Verification Component
// ===========================================================================

export function FssaiVerificationCard({
  inspectionId,
  category: _category,
}: {
  inspectionId: string;
  category?: string;
}) {
  const [data, setData] = useState<FssaiVerificationData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getFssaiVerification(inspectionId)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [inspectionId]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-border/70 bg-card p-5">
        <div className="flex items-center gap-3">
          <LoaderCircle className="h-5 w-5 animate-spin text-brand" />
          <p className="text-sm text-muted-foreground">Checking FSSAI Regulatory License Database…</p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const isMatch = data.status === "VERIFIED / MATCH";
  const isMismatch = data.status === "MISMATCH DETECTED";
  const isNotApp = data.status === "NOT APPLICABLE";

  const badgeStyle = isMatch
    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
    : isMismatch
    ? "bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400"
    : isNotApp
    ? "bg-muted text-muted-foreground border-border/60"
    : "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400";

  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">USP 2 · Multi-Regulatory</p>
            <span className="rounded-full bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 text-[10px] font-bold text-blue-600 dark:text-blue-400">
              FSSAI Statutory Check
            </span>
          </div>
          <h3 className="mt-1 text-xl font-semibold tracking-tight">Food Safety & Standards (FSSAI) Cross-Verification</h3>
        </div>
        <div className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold ${badgeStyle}`}>
          {isMatch ? <Check className="h-3.5 w-3.5" /> : isMismatch ? <XCircle className="h-3.5 w-3.5" /> : <Info className="h-3.5 w-3.5" />}
          {data.status}
        </div>
      </div>

      <p className="text-sm leading-6 text-foreground">{data.explanation}</p>

      {data.is_food && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 rounded-xl border border-border/60 bg-muted/40 p-4 text-xs">
          <div>
            <span className="block text-[10px] uppercase font-bold text-muted-foreground">License Number</span>
            <span className="font-mono font-bold text-foreground">{data.license_number || "Not detected"}</span>
          </div>
          <div>
            <span className="block text-[10px] uppercase font-bold text-muted-foreground">Authority Type</span>
            <span className="font-semibold text-foreground">{data.registration_type || "Standard License"}</span>
          </div>
          <div>
            <span className="block text-[10px] uppercase font-bold text-muted-foreground">State Jurisdiction</span>
            <span className="font-semibold text-foreground">{data.state_jurisdiction || "Central / All India"}</span>
          </div>
          <div>
            <span className="block text-[10px] uppercase font-bold text-muted-foreground">Registered Licensee</span>
            <span className="font-semibold text-foreground truncate block">{data.registry_licensee || data.declared_manufacturer || "—"}</span>
          </div>
        </div>
      )}

      {data.evidence_text && (
        <div className="rounded-lg bg-muted/60 p-3 text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">Package Evidence Text: </span>
          <span className="font-mono">{data.evidence_text}</span>
        </div>
      )}

      <p className="text-[11px] text-muted-foreground italic">
        * Note: FSSAI verification operates independently under the Food Safety and Standards (Packaging and Labelling) Regulations. It does not alter LMPC 2011 Legal Metrology statutory determinations.
      </p>
    </section>
  );
}

// ===========================================================================
// USP 3: Consumer / Inspector Escalation Modal
// ===========================================================================

export function ConsumerReportModal({
  inspection,
  onClose,
  onSuccess,
}: {
  inspection: Inspection;
  onClose: () => void;
  onSuccess: (caseId: string, reportId: string) => void;
}) {
  const [issueCategory, setIssueCategory] = useState("Misleading Net Weight / Quantity Shortage");
  const [retailerName, setRetailerName] = useState("");
  const [location, setLocation] = useState("");
  const [reporterName, setReporterName] = useState("");
  const [reporterContact, setReporterContact] = useState("");
  const [details, setDetails] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const missingViolationsCount = inspection.declarations.filter(
    (d) => d.status === "MISSING" || d.status === "UNOBSERVED"
  ).length;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitConsumerReport({
        inspection_id: inspection.id,
        product_name: inspection.product || "Packaged Commodity",
        product_id: inspection.productId || undefined,
        category: inspection.category || "Packaged Commodity",
        issue_category: issueCategory,
        details: details.trim() || `Automated escalation for ${inspection.product}. Identified ${missingViolationsCount} statutory discrepancy findings under LMPC 2011.`,
        reporter_name: reporterName.trim() || undefined,
        reporter_contact: reporterContact.trim() || undefined,
        retailer_name: retailerName.trim() || undefined,
        location: location.trim() || undefined,
        lmpc_verdict: inspection.status,
        lmpc_violations_count: missingViolationsCount,
        evidence_image_urls: inspection.image ? [inspection.image] : [],
      });
      onSuccess(res.case_id, res.report_id);
    } catch (err: any) {
      setError(err?.message || "Failed to submit escalation docket.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="w-full max-w-lg rounded-2xl border border-border/80 bg-card p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-border/60 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
              <ShieldAlert className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">Escalate to Legal Metrology Authority</h3>
              <p className="text-xs text-muted-foreground">Direct Consumer & Inspector Enforcement Gateway</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="rounded-xl border border-border/70 bg-muted/40 p-3.5 text-xs space-y-1.5">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Product:</span>
            <span className="font-bold text-foreground">{inspection.product}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Inspection ID:</span>
            <span className="font-mono text-foreground">#{inspection.id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">LMPC Status:</span>
            <span className={`font-bold ${inspection.status === "VIOLATION" ? "text-destructive" : "text-amber-500"}`}>
              {inspection.status} ({missingViolationsCount} Issues)
            </span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3.5 text-xs">
          <div>
            <label className="block font-semibold text-muted-foreground mb-1">Violation Category *</label>
            <select
              value={issueCategory}
              onChange={(e) => setIssueCategory(e.target.value)}
              className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
            >
              <option value="Misleading Net Weight / Quantity Shortage">Misleading Net Weight / Quantity Shortage</option>
              <option value="Missing Mandatory Declarations (Rule 6)">Missing Mandatory Declarations (Rule 6)</option>
              <option value="Missing Unit Sale Price (USP Mandate)">Missing Unit Sale Price (USP Mandate)</option>
              <option value="Price Alteration / Dual MRP / Overcharging">Price Alteration / Dual MRP / Overcharging</option>
              <option value="Expired / Past Best Before Date">Expired / Past Best Before Date</option>
              <option value="Suspected Alteration / Non-genuine Label">Suspected Alteration / Non-genuine Label</option>
            </select>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="block font-semibold text-muted-foreground">Purchase / Retail Store Location *</label>
              <span className="text-[10px] text-brand font-medium">Map Pin & Store Selector</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <input
                  type="text"
                  placeholder="Store name (e.g. D-Mart, Sector 14)"
                  value={retailerName}
                  onChange={(e) => setRetailerName(e.target.value)}
                  className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
                />
              </div>
              <div>
                <input
                  type="text"
                  placeholder="City / Area (e.g. Pune, Maharashtra)"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
                />
              </div>
            </div>

            {/* Quick Location & Map Pin Chips */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[10px] text-muted-foreground">Quick Pin:</span>
              {[
                { name: "Pune, MH", lat: 18.5204, lng: 73.8567 },
                { name: "Mumbai, MH", lat: 19.0760, lng: 72.8777 },
                { name: "Gurugram, HR", lat: 28.4595, lng: 77.0266 },
                { name: "Bengaluru, KA", lat: 12.9716, lng: 77.5946 },
                { name: "Delhi NCT", lat: 28.6139, lng: 77.2090 },
              ].map((pin) => (
                <button
                  key={pin.name}
                  type="button"
                  onClick={() => {
                    setLocation(pin.name);
                    if (!retailerName) setRetailerName("Local Retail Merchant");
                  }}
                  className={`rounded-lg px-2 py-0.5 text-[10px] font-medium border transition ${
                    location === pin.name
                      ? "border-brand bg-brand/10 text-brand"
                      : "border-border/60 bg-muted/40 text-muted-foreground hover:border-border"
                  }`}
                >
                  📍 {pin.name}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Your Name (Optional)</label>
              <input
                type="text"
                placeholder="Anonymous or Inspector Name"
                value={reporterName}
                onChange={(e) => setReporterName(e.target.value)}
                className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
              />
            </div>
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Contact Email/Phone (Optional)</label>
              <input
                type="text"
                placeholder="For status SMS/email"
                value={reporterContact}
                onChange={(e) => setReporterContact(e.target.value)}
                className="h-9 w-full rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
              />
            </div>
          </div>

          <div>
            <label className="block font-semibold text-muted-foreground mb-1">Statutory Details / Observations</label>
            <textarea
              rows={3}
              placeholder="Describe observations, shelf location, or evidence context..."
              value={details}
              onChange={(e) => setDetails(e.target.value)}
              className="w-full rounded-xl border border-border bg-background p-3 text-xs outline-none focus:border-brand"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-destructive/10 p-2.5 text-xs text-destructive">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
            <button
              type="button"
              onClick={onClose}
              className="h-9 px-4 rounded-xl border border-border bg-background font-semibold text-muted-foreground hover:bg-muted"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="h-9 px-5 rounded-xl bg-destructive text-destructive-foreground font-semibold flex items-center gap-1.5 shadow-md hover:bg-destructive/90 disabled:opacity-50"
            >
              {submitting ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
              {submitting ? "Filing Docket…" : "File Statutory Docket"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ===========================================================================
// USP 3: Authority Dashboard View
// ===========================================================================

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
          className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground transition"
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
          <p className="text-[10px] font-bold uppercase tracking-widest text-amber-600 dark:text-amber-400">New Inquiries</p>
          <p className="mt-1 text-2xl font-bold text-amber-600 dark:text-amber-400">{counts.submitted}</p>
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
            className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
              statusFilter === st
                ? "bg-foreground text-background"
                : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
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

// ===========================================================================
// USP 4: Multilingual Voice/Text Assistant Widget
// ===========================================================================

export function MultilingualAssistantWidget({
  currentInspection,
}: {
  currentInspection?: Inspection;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [lang, setLang] = useState<"en" | "hi" | "mr">("en");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; text: string; sources?: string[] }>>([
    {
      role: "assistant",
      text: "Namaste! I am LexMetra's Legal Metrology & Multi-Regulatory Assistant. I can explain statutory LMPC 2011 requirements, FSSAI compliance, and Package Integrity in English, हिन्दी, or मराठी.",
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  // Speech Recognition support
  function toggleListening() {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser. Please type your question.");
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = lang === "hi" ? "hi-IN" : lang === "mr" ? "mr-IN" : "en-IN";
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);
      recognition.onresult = (e: any) => {
        const transcript = e.results[0][0].transcript;
        if (transcript) {
          setInput(transcript);
          handleSend(transcript);
        }
      };
      recognition.start();
    } catch (e) {
      setIsListening(false);
    }
  }

  // Text-to-Speech support: Sarvam AI Bulbul v3 with fallback to browser speechSynthesis
  async function speakText(text: string) {
    if (!text) return;
    setIsSpeaking(true);

    try {
      const audioUrl = await synthesizeSpeech(text, lang);
      if (audioUrl) {
        const audio = new Audio(audioUrl);
        audio.onended = () => setIsSpeaking(false);
        audio.onerror = () => {
          setIsSpeaking(false);
          fallbackBrowserSpeech(text);
        };
        await audio.play();
        return;
      }
    } catch {
      // fallback
    }

    fallbackBrowserSpeech(text);
  }

  function fallbackBrowserSpeech(text: string) {
    if (!window.speechSynthesis) {
      setIsSpeaking(false);
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang === "hi" ? "hi-IN" : lang === "mr" ? "mr-IN" : "en-IN";
    utterance.rate = 0.95;
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    window.speechSynthesis.speak(utterance);
  }

  async function handleSend(textToSend?: string) {
    const q = (textToSend || input).trim();
    if (!q || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setLoading(true);

    try {
      const res = await askAssistant({
        query: q,
        language: lang,
        inspection_id: currentInspection?.id,
        inspection_context: currentInspection,
      });

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: res.response_text,
          sources: res.grounding_sources,
        },
      ]);
      speakText(res.speech_text);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Sorry, I could not process your query at this moment. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed bottom-20 right-4 md:bottom-6 md:right-6 z-40">
      {!isOpen ? (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="flex h-14 items-center gap-2.5 rounded-full bg-brand px-5 text-brand-foreground shadow-xl shadow-brand/25 transition-transform hover:scale-105 active:scale-95"
        >
          <Sparkles className="h-5 w-5" />
          <span className="text-xs font-bold uppercase tracking-wider">Assistant</span>
        </button>
      ) : (
        <div className="flex h-[520px] w-[360px] sm:w-[400px] flex-col rounded-3xl border border-border/80 bg-card shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border/60 bg-muted/40 px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-brand text-brand-foreground">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-bold text-foreground">LexMetra Multilingual AI</p>
                <p className="text-[10px] text-muted-foreground">Grounded Legal Metrology Voice Assistant</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {isSpeaking && (
                <Volume2 className="h-4 w-4 text-brand animate-pulse mr-1" />
              )}
              {/* Language Switcher */}
              <div className="inline-flex rounded-lg border border-border/60 bg-background p-0.5 text-[10px] font-semibold">
                <button
                  type="button"
                  onClick={() => setLang("en")}
                  className={`px-1.5 py-0.5 rounded ${lang === "en" ? "bg-brand text-brand-foreground" : "text-muted-foreground"}`}
                >
                  EN
                </button>
                <button
                  type="button"
                  onClick={() => setLang("hi")}
                  className={`px-1.5 py-0.5 rounded ${lang === "hi" ? "bg-brand text-brand-foreground" : "text-muted-foreground"}`}
                >
                  हिन्दी
                </button>
                <button
                  type="button"
                  onClick={() => setLang("mr")}
                  className={`px-1.5 py-0.5 rounded ${lang === "mr" ? "bg-brand text-brand-foreground" : "text-muted-foreground"}`}
                >
                  मराठी
                </button>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Intuitive Action / Common Task Menu */}
          <div className="flex gap-1.5 overflow-x-auto border-b border-border/40 bg-muted/20 px-3 py-2 text-[10px] no-scrollbar">
            {[
              { label: "Explain inspection", q: "Explain this inspection and its overall findings" },
              { label: "Explain violation", q: "Explain the violations found on this package" },
              { label: "Why uncertain?", q: "Why is this inspection or declaration marked uncertain?" },
              { label: "Show evidence", q: "Show supporting evidence and localized polygon regions" },
              { label: "Explain rule", q: "Explain the applicable Legal Metrology rules for MRP and Net Weight" },
              { label: "Summarize", q: "Summarize findings for this package" },
              { label: "Generate report", q: "Generate report for this inspection" },
              { label: "🔊 Read aloud", q: "Read summary aloud" },
            ].map((chip, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  if (chip.label === "🔊 Read aloud") {
                    const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
                    if (lastAssistant) {
                      speakText(lastAssistant.text);
                      return;
                    }
                  }
                  handleSend(chip.q);
                }}
                className="shrink-0 rounded-full border border-border/70 bg-card px-2.5 py-1 font-medium text-foreground hover:border-brand hover:text-brand transition shadow-2xs"
              >
                {chip.label}
              </button>
            ))}
          </div>

          {/* Messages */}
          <div className="flex-1 space-y-3 overflow-y-auto p-4 text-xs">
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl p-3 leading-relaxed ${
                    m.role === "user"
                      ? "bg-brand text-brand-foreground rounded-br-xs"
                      : "bg-muted text-foreground border border-border/60 rounded-bl-xs"
                  }`}
                >
                  <p>{m.text}</p>
                  {m.sources && m.sources.length > 0 && (
                    <div className="mt-2 border-t border-border/40 pt-1 text-[10px] text-muted-foreground">
                      <strong>Statutory Sources:</strong> {m.sources.join(" · ")}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <LoaderCircle className="h-3.5 w-3.5 animate-spin text-brand" /> Legal Metrology grounding in progress…
              </div>
            )}
          </div>

          {/* Input Bar */}
          <div className="border-t border-border/60 bg-muted/30 p-3">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex items-center gap-2"
            >
              <button
                type="button"
                onClick={toggleListening}
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition ${
                  isListening
                    ? "border-red-500 bg-red-500/10 text-red-500 animate-pulse"
                    : "border-border bg-card text-muted-foreground hover:text-foreground"
                }`}
                title="Voice input"
              >
                {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <input
                type="text"
                placeholder={lang === "hi" ? "अपना प्रश्न पूछें..." : lang === "mr" ? "तुमचा प्रश्न विचारा..." : "Ask compliance question..."}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="h-9 flex-1 rounded-xl border border-border bg-background px-3 text-xs outline-none focus:border-brand"
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand text-brand-foreground disabled:opacity-40"
              >
                <Send className="h-4 w-4" />
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
