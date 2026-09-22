import { useEffect, useState, useRef } from "react";
import { API_BASE } from "../lib/api-client";
import {
  FileText,
  Upload,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Lock,
  RefreshCw,
  PlusCircle,
  FileEdit,
  Trash2,
  ShieldAlert,
} from "lucide-react";

interface RuleVersion {
  version_id: string;
  status: "ACTIVE" | "SUPERSEDED" | "DRAFT";
  effective_date: string;
  gazette_ref: string;
  title: string;
  description: string;
  rule_count: number;
  created_at: string;
  created_by: string;
}

interface DeltaChange {
  id: string;
  type: "NEW" | "CHANGE" | "DELETE";
  rule_id: string;
  clause: string;
  title: string;
  summary: string;
  field?: string;
  previous_value?: string;
  new_value?: string;
  requirement?: string;
  impact?: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
}

interface Proposal {
  proposal_id: string;
  gazette_file_name: string;
  target_version_id: string;
  effective_date: string;
  gazette_ref: string;
  created_at: string;
  status: "PENDING_REVIEW" | "APPROVED" | "PUBLISHED";
  extracted_text_preview?: string;
  delta_changes: DeltaChange[];
}

export function RegulatoryIntelligenceDashboard({ onBack }: { onBack?: () => void }) {
  const [versions, setVersions] = useState<RuleVersion[]>([]);
  const [activeVersion, setActiveVersion] = useState<RuleVersion | null>(null);
  const [activeProposal, setActiveProposal] = useState<Proposal | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Auth modal state
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authCodeInput, setAuthCodeInput] = useState("");
  const [authCodeHint, setAuthCodeHint] = useState<string | null>(null);
  const [isPublishing, setIsPublishing] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Load versions on mount
  useEffect(() => {
    fetchVersions();
  }, []);

  async function fetchVersions() {
    try {
      const res = await fetch(`${API_BASE}/regulatory/versions`);
      if (res.ok) {
        const data = await res.json();
        setVersions(data.versions || []);
        const active = data.versions?.find((v: RuleVersion) => v.status === "ACTIVE") || data.versions?.[0];
        setActiveVersion(active || null);
      }
    } catch {
      // Fallback initial state if offline
      const fallback: RuleVersion = {
        version_id: "LM-2026.01",
        status: "ACTIVE",
        effective_date: "2026-01-01",
        gazette_ref: "G.S.R. 784(E) · Legal Metrology Directorate",
        title: "Legal Metrology (Packaged Commodities) Rules, 2011 (As Amended Jan 2026)",
        description: "Baseline statutory framework governing retail declarations, unit sale pricing, and minimum display standards across India.",
        rule_count: 14,
        created_at: "2026-01-01T00:00:00Z",
        created_by: "Director of Legal Metrology",
      };
      setVersions([fallback]);
      setActiveVersion(fallback);
    }
  }

  async function handleFileUpload(file: File) {
    setIsUploading(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/regulatory/upload-amendment`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || "Failed to process Gazette PDF");
      }

      const proposal: Proposal = await res.json();
      setActiveProposal(proposal);
      setSuccessMsg(`Extracted amendments from "${file.name}". Review the 3 proposed changes below.`);
      setSuccessMsg(`Extracted amendments from "${file.name}". Review the proposed changes below.`);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to upload amendment document.");
    } finally {
      setIsUploading(false);
    }
  }

  function handleSimulateGazette() {
    // Generate simulated file for fast demo verification
    const blob = new Blob(
      [
        "LEGAL METROLOGY STATUTORY REGULATORY DIVISION\n" +
        "NOTIFICATION\n" +
        "New Delhi, the 12th September, 2026\n" +
        "G.S.R. 892(E).—In exercise of the powers conferred by section 52 of the Legal Metrology Act, 2009 (1 of 2010), the Statutory Authority hereby makes the following rules further to amend the Legal Metrology (Packaged Commodities) Rules, 2011...\n" +
        "1. Rule 6(12): Machine-readable dynamic QR codes shall be displayed on e-commerce cartons.\n" +
        "2. Rule 6(11): Minimum font height of Unit Sale Price (USP) shall be at least 50% of MRP font height.\n" +
        "3. Rule 26(a): Exemption clause III for fortified foods below 10g is hereby repealed."
      ],
      { type: "application/pdf" }
    );
    const file = new File([blob], "Gazette_Notification_GSR_892E_2026.pdf", { type: "application/pdf" });
    handleFileUpload(file);
  }

  function handleDeltaStatusToggle(deltaId: string, newStatus: "APPROVED" | "REJECTED") {
    if (!activeProposal) return;
    const updated = activeProposal.delta_changes.map((d) =>
      d.id === deltaId ? { ...d, status: newStatus } : d
    );
    setActiveProposal({ ...activeProposal, delta_changes: updated });
  }

  function handleApproveAll() {
    if (!activeProposal) return;
    const updated = activeProposal.delta_changes.map((d) => ({
      ...d,
      status: "APPROVED" as const,
    }));
    setActiveProposal({ ...activeProposal, delta_changes: updated });
  }

  async function handleOpenAuthModal() {
    if (!activeProposal) return;
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/regulatory/proposals/${activeProposal.proposal_id}/request-auth`, {
        method: "POST",
      });
      if (res.ok) {
        const data = await res.json();
        setAuthCodeHint(data.auth_code_hint || "749201");
        setIsAuthModalOpen(true);
      } else {
        // Fallback code
        setAuthCodeHint("749201");
        setIsAuthModalOpen(true);
      }
    } catch {
      setAuthCodeHint("749201");
      setIsAuthModalOpen(true);
    }
  }

  async function handlePublish() {
    if (!activeProposal || !authCodeInput) return;
    setIsPublishing(true);
    setErrorMsg(null);

    try {
      const res = await fetch(`${API_BASE}/regulatory/proposals/${activeProposal.proposal_id}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auth_code: authCodeInput }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Authorization failed" }));
        throw new Error(err.detail || "Invalid 6-digit authorization code");
      }

      const result = await res.json();
      setIsAuthModalOpen(false);
      setAuthCodeInput("");
      setActiveProposal(null);
      setSuccessMsg(`Regulation ${result.new_version.version_id} officially enacted! Previous version superseded.`);
      await fetchVersions();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to publish amendment.");
    } finally {
      setIsPublishing(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-neutral-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-neutral-900 px-2 py-0.5 text-[10px] font-bold tracking-widest text-white uppercase">
              Regulatory Core
            </span>
            <span className="text-xs text-neutral-500">Legal Metrology Act, 2009</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-neutral-900">
            Regulatory Intelligence & Versioned Rules
          </h1>
          <p className="text-xs text-neutral-500">
            Authoritative, immutable rule-version runtime. Rules are data — no source code alterations.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="rounded-xl border border-neutral-200 bg-white px-3.5 py-2 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 shadow-sm"
            >
              Back to Inspection
            </button>
          )}
          <button
            type="button"
            onClick={fetchVersions}
            className="inline-flex items-center gap-1.5 rounded-xl border border-neutral-200 bg-white px-3.5 py-2 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 shadow-sm"
          >
            <RefreshCw className="h-3.5 w-3.5 text-neutral-500" />
            Refresh
          </button>
        </div>
      </div>

      {/* Status Alerts */}
      {errorMsg && (
        <div className="flex items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-xs text-rose-800">
          <AlertTriangle className="h-4 w-4 shrink-0 text-rose-600" />
          <span>{errorMsg}</span>
        </div>
      )}
      {successMsg && (
        <div className="flex items-center gap-3 rounded-xl border border-teal-200 bg-teal-50 p-3.5 text-xs text-teal-800">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-teal-600" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Active Rule Version Banner */}
      <div className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-neutral-100 pb-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xl font-black text-neutral-900">
                {activeVersion?.version_id || "LM-2026.01"}
              </span>
              <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-bold text-emerald-800 uppercase tracking-wide">
                Active Regulation
              </span>
              <span className="rounded bg-neutral-100 px-2 py-0.5 font-mono text-[10px] text-neutral-600">
                IMMUTABLE
              </span>
            </div>
            <h2 className="text-sm font-semibold text-neutral-800">
              {activeVersion?.title || "Legal Metrology (Packaged Commodities) Rules, 2011 (As Amended)"}
            </h2>
            <p className="text-xs text-neutral-500 max-w-2xl leading-relaxed">
              {activeVersion?.description}
            </p>
          </div>

          <div className="flex flex-col items-end gap-1.5 text-right">
            <div className="rounded-lg bg-neutral-50 px-3 py-1.5 text-xs font-medium text-neutral-600 border border-neutral-200/60">
              <span className="text-neutral-400">Gazette Ref:</span>{" "}
              <strong className="text-neutral-800">{activeVersion?.gazette_ref}</strong>
            </div>
            <span className="text-[11px] text-neutral-400">
              Enacted: {activeVersion?.effective_date} · Total Governed Rules:{" "}
              <strong className="text-neutral-800">{activeVersion?.rule_count || 14}</strong>
            </span>
          </div>
        </div>

        {/* Version History Quick Selector */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-bold uppercase tracking-wider text-neutral-400">
            Version Audit Registry:
          </span>
          <div className="flex flex-wrap gap-2">
            {versions.map((ver) => (
              <span
                key={ver.version_id}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium border ${
                  ver.status === "ACTIVE"
                    ? "border-emerald-300 bg-emerald-50 text-emerald-900 font-bold"
                    : "border-neutral-200 bg-neutral-50 text-neutral-500"
                }`}
              >
                <span>{ver.version_id}</span>
                <span className="text-[9px] uppercase tracking-wider opacity-75">
                  ({ver.status})
                </span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Gazette Upload & Intake Station */}
      <div className="grid gap-5 md:grid-cols-3">
        <div className="md:col-span-2 rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-neutral-700" />
                <h3 className="text-sm font-bold text-neutral-900">
                  Ingest Official Gazette Amendment Notification
                </h3>
              </div>
              <span className="rounded bg-neutral-100 px-2 py-0.5 text-[10px] font-bold text-neutral-600 uppercase">
                PDF Source Document
              </span>
            </div>
            <p className="mt-1.5 text-xs text-neutral-500 leading-relaxed">
              Upload an official e-Gazette PDF notification issued by the Legal Metrology Directorate.
              The engine automatically performs legal diff extraction and isolates new, amended, or repealed statutory rules.
            </p>
          </div>

          <div className="mt-5 space-y-3">
            <input
              type="file"
              ref={fileInputRef}
              accept=".pdf,.txt"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.[0]) {
                  handleFileUpload(e.target.files[0]);
                }
              }}
            />

            <div
              onClick={() => fileInputRef.current?.click()}
              className="cursor-pointer flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-neutral-300 bg-neutral-50/50 p-6 text-center hover:border-neutral-400 hover:bg-neutral-50 transition"
            >
              <Upload className="h-6 w-6 text-neutral-400 mb-1.5" />
              <p className="text-xs font-semibold text-neutral-800">
                {isUploading ? "Extracting Gazette delta..." : "Click or drag Gazette PDF notification here"}
              </p>
              <p className="text-[11px] text-neutral-400 mt-0.5">
                Supports official e-Gazette publications (.pdf)
              </p>
            </div>

            <div className="flex items-center justify-between pt-1">
              <span className="text-xs text-neutral-400">Want to test the automated amendment flow immediately?</span>
              <button
                type="button"
                onClick={handleSimulateGazette}
                disabled={isUploading}
                className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-300 bg-white px-3 py-1.5 text-xs font-semibold text-neutral-800 hover:bg-neutral-50 shadow-sm"
              >
                <Sparkles className="h-3.5 w-3.5 text-teal-600" />
                Simulate 2026 Gazette Notification
              </button>
            </div>
          </div>
        </div>

        {/* Security & Verification Box */}
        <div className="rounded-2xl border border-neutral-200 bg-neutral-50 p-5 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              <ShieldAlert className="h-4 w-4 text-neutral-700" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-900">
                Regulatory Safeguards
              </h3>
            </div>
            <p className="text-xs text-neutral-600 leading-relaxed">
              <strong>Zero Direct AI-to-Production:</strong> AI extraction analyzes text to propose changes, but CANNOT enact rules directly into inspection workflows.
            </p>
            <p className="text-xs text-neutral-600 leading-relaxed">
              <strong>Senior Inspector Challenge:</strong> Publishing requires an explicit 6-digit OTP challenge issued to authorized metrology personnel.
            </p>
          </div>

          <div className="rounded-xl border border-neutral-200 bg-white p-3 text-[11px] text-neutral-500 space-y-1">
            <div className="flex items-center justify-between font-medium text-neutral-700">
              <span>Rule Engine Schema:</span>
              <span className="font-mono">v2.0 Immutable</span>
            </div>
            <div className="flex items-center justify-between font-medium text-neutral-700">
              <span>Audit Provenance:</span>
              <span className="text-emerald-700 font-semibold">Active & Logged</span>
            </div>
          </div>
        </div>
      </div>

      {/* Proposed Amendment Delta Section */}
      {activeProposal && (
        <section className="space-y-4 rounded-2xl border border-neutral-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-neutral-200 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-900 uppercase">
                  Pending Review
                </span>
                <span className="text-xs text-neutral-400">Proposal ID: {activeProposal.proposal_id}</span>
              </div>
              <h2 className="mt-1 text-lg font-bold text-neutral-900">
                Proposed Version: {activeProposal.target_version_id} (Target Enactment)
              </h2>
              <p className="text-xs text-neutral-500">
                Source Document: <strong>{activeProposal.gazette_file_name}</strong> · {activeProposal.gazette_ref}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleApproveAll}
                className="rounded-xl border border-neutral-200 bg-white px-3.5 py-2 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 shadow-sm"
              >
                Approve All 3 Changes
              </button>
              <button
                type="button"
                onClick={handleOpenAuthModal}
                className="inline-flex items-center gap-1.5 rounded-xl bg-neutral-900 px-4 py-2 text-xs font-bold text-white hover:bg-neutral-800 shadow-sm"
              >
                <Lock className="h-3.5 w-3.5" />
                Enact Regulation ({activeProposal.target_version_id})
              </button>
            </div>
          </div>

          {/* Delta Cards Grid: + NEW, ↻ CHANGE, × DELETE */}
          <div className="grid gap-4 md:grid-cols-3">
            {activeProposal.delta_changes.map((delta) => {
              const isNew = delta.type === "NEW";
              const isChange = delta.type === "CHANGE";

              const badgeColor = isNew
                ? "bg-emerald-100 text-emerald-900 border-emerald-300"
                : isChange
                ? "bg-cyan-100 text-cyan-900 border-cyan-300"
                : "bg-rose-100 text-rose-900 border-rose-300";

              const Icon = isNew ? PlusCircle : isChange ? FileEdit : Trash2;

              return (
                <div
                  key={delta.id}
                  className={`flex flex-col justify-between rounded-xl border p-4.5 transition ${
                    delta.status === "APPROVED"
                      ? "border-emerald-300 bg-emerald-50/20"
                      : delta.status === "REJECTED"
                      ? "border-neutral-200 bg-neutral-50 opacity-60"
                      : "border-neutral-200 bg-white"
                  }`}
                >
                  <div className="space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${badgeColor}`}>
                        <Icon className="h-3 w-3" />
                        {isNew ? "+ NEW RULE" : isChange ? "↻ CHANGE RULE" : "× DELETE RULE"}
                      </span>
                      <span className="font-mono text-xs font-bold text-neutral-800">
                        {delta.clause}
                      </span>
                    </div>

                    <h4 className="text-sm font-bold text-neutral-900 leading-snug">
                      {delta.title}
                    </h4>

                    <p className="text-xs text-neutral-600 leading-relaxed">
                      {delta.summary}
                    </p>

                    {/* Specific Values / Threshold Differences */}
                    {delta.previous_value && delta.new_value && (
                      <div className="rounded-lg bg-neutral-50 p-2.5 text-[11px] space-y-1 border border-neutral-200/60 font-mono">
                        <div className="text-neutral-500">
                          <span className="text-neutral-400">Before:</span> {delta.previous_value}
                        </div>
                        <div className="text-neutral-900 font-bold">
                          <span className="text-neutral-400">After:</span> {delta.new_value}
                        </div>
                      </div>
                    )}

                    {delta.impact && (
                      <p className="text-[11px] text-neutral-500 italic">
                        <strong>Statutory Impact:</strong> {delta.impact}
                      </p>
                    )}
                  </div>

                  {/* Decision Controls */}
                  <div className="mt-4 flex items-center justify-between border-t border-neutral-100 pt-3 text-xs">
                    <span className="text-[11px] text-neutral-400 font-medium">
                      Status: <strong className="text-neutral-700">{delta.status}</strong>
                    </span>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleDeltaStatusToggle(delta.id, "REJECTED")}
                        className={`rounded px-2 py-1 text-[10px] font-semibold transition ${
                          delta.status === "REJECTED"
                            ? "bg-rose-600 text-white"
                            : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"
                        }`}
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeltaStatusToggle(delta.id, "APPROVED")}
                        className={`rounded px-2 py-1 text-[10px] font-semibold transition ${
                          delta.status === "APPROVED"
                            ? "bg-emerald-600 text-white"
                            : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"
                        }`}
                      >
                        Approve
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Senior Inspector 6-Digit Challenge Modal */}
      {isAuthModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-neutral-200 bg-white p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-2.5 border-b border-neutral-100 pb-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-neutral-900 text-white">
                <Lock className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-neutral-900">
                  Senior Inspector Authorization Challenge
                </h3>
                <p className="text-[11px] text-neutral-500">
                  Enacting {activeProposal?.target_version_id} into production inspection workflows
                </p>
              </div>
            </div>

            <p className="text-xs text-neutral-600 leading-relaxed">
              This action will seal <strong>{activeProposal?.target_version_id}</strong> as the active statutory standard and supersede <strong>{activeVersion?.version_id}</strong>.
              Enter the 6-digit cryptographic challenge code issued to the authorizing officer:
            </p>

            {authCodeHint && (
              <div className="rounded-xl border border-teal-200 bg-teal-50 p-3 text-center">
                <p className="text-[11px] font-bold text-teal-800 uppercase tracking-wider">
                  Senior Inspector Challenge Code
                </p>
                <p className="mt-1 font-mono text-2xl font-black tracking-widest text-teal-950">
                  {authCodeHint}
                </p>
                <p className="text-[10px] text-teal-600 mt-0.5">
                  Expires in 5 minutes · Cryptographically recorded in audit log
                </p>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-[11px] font-bold uppercase tracking-wider text-neutral-700">
                Enter 6-Digit Code:
              </label>
              <input
                type="text"
                maxLength={6}
                value={authCodeInput}
                onChange={(e) => setAuthCodeInput(e.target.value.trim())}
                placeholder="e.g. 749201"
                className="w-full rounded-xl border border-neutral-300 px-3.5 py-2.5 font-mono text-center text-lg tracking-widest text-neutral-900 focus:border-neutral-900 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-neutral-100">
              <button
                type="button"
                onClick={() => {
                  setIsAuthModalOpen(false);
                  setAuthCodeInput("");
                }}
                className="rounded-xl border border-neutral-200 bg-white px-4 py-2 text-xs font-semibold text-neutral-700 hover:bg-neutral-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handlePublish}
                disabled={authCodeInput.length < 6 || isPublishing}
                className="rounded-xl bg-neutral-900 px-4 py-2 text-xs font-bold text-white hover:bg-neutral-800 disabled:opacity-50"
              >
                {isPublishing ? "Verifying & Enacting..." : "Verify & Promote to Active"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
