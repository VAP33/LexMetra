import { useEffect, useState } from "react";
import {
  ShieldCheck,
  FileText,
  AlertTriangle,
  XCircle,
  ExternalLink,
  CheckCircle2,
  Calendar,
  Tag,
  Building2,
  Lock,
  Loader2,
  X,
} from "lucide-react";
import {
  getPublicVerificationDocket,
  downloadOrOpenInspectionReportPdf,
  type PublicVerificationDocket,
} from "../lib/api-client";
import { LexMetraLogo, Button } from "./ui-primitives";

interface PublicVerificationViewProps {
  inspectionId: string;
  onClose?: () => void;
}

export function PublicVerificationView({ inspectionId, onClose }: PublicVerificationViewProps) {
  const [docket, setDocket] = useState<PublicVerificationDocket | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openingPdf, setOpeningPdf] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getPublicVerificationDocket(inspectionId)
      .then((res) => {
        setDocket(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err?.message || "Public statutory docket could not be retrieved or is unverified.");
        setLoading(false);
      });
  }, [inspectionId]);

  async function handleOpenPdf() {
    setOpeningPdf(true);
    try {
      await downloadOrOpenInspectionReportPdf(inspectionId);
    } catch (err: any) {
      alert("Failed to load PDF dossier: " + (err?.message || "Network error"));
    } finally {
      setOpeningPdf(false);
    }
  }

  const isPass = docket?.overall_status === "PASS" || docket?.overall_status === "COMPLIANT";
  const isViolation = docket?.overall_status === "FAIL" || docket?.overall_status === "VIOLATION";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 overflow-y-auto">
      <div className="relative w-full max-w-2xl bg-card border border-border shadow-2xl rounded-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200 my-8">
        
        {/* Header Ribbon */}
        <div className="bg-gradient-to-r from-blue-950 via-slate-900 to-indigo-950 p-6 text-white border-b border-border/40 relative">
          {onClose && (
            <button
              onClick={onClose}
              className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white/80 hover:text-white transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          )}

          <div className="flex items-center gap-3 mb-3">
            <LexMetraLogo className="h-9 w-auto" />
          </div>

          <div className="flex items-center gap-2 text-xs font-mono text-emerald-400 font-semibold tracking-wider uppercase">
            <Lock className="h-3.5 w-3.5" />
            Official Public Statutory Verification Portal
          </div>
          <h1 className="text-xl font-black tracking-tight text-white mt-1">
            STATUTORY COMPLIANCE DOCKET VERIFICATION
          </h1>
          <p className="text-xs text-slate-300 mt-1 max-w-lg">
            Government of India &bull; Department of Consumer Affairs &bull; Legal Metrology (Packaged Commodities) Rules, 2011
          </p>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6">
          {loading ? (
            <div className="py-16 text-center space-y-3">
              <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto" />
              <p className="text-sm text-muted-foreground font-medium">
                Verifying digital seal with Central Metrology Registry…
              </p>
            </div>
          ) : error || !docket ? (
            <div className="py-10 text-center space-y-3">
              <AlertTriangle className="h-10 w-10 text-amber-500 mx-auto" />
              <h2 className="text-base font-bold text-foreground">Statutory Record Unavailable</h2>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                {error || "No recorded compliance docket matches this identification token."}
              </p>
              {onClose && (
                <Button variant="secondary" onClick={onClose} className="mt-4">
                  Close Portal
                </Button>
              )}
            </div>
          ) : (
            <>
              {/* Authenticity Seal Banner */}
              <div className="flex items-start gap-4 p-4 rounded-xl border bg-muted/40 border-border/60">
                <div className="p-2.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5">
                  <ShieldCheck className="h-7 w-7" />
                </div>
                <div className="space-y-1 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-foreground">
                      GOVERNMENT DIGITAL SEAL AFFIRMED
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-700 dark:text-emerald-300">
                      AUTHENTIC
                    </span>
                  </div>
                  <p className="text-muted-foreground">
                    This docket is an authenticated statutory screening record registered under the{" "}
                    <strong>Legal Metrology Act, 2009</strong> and <strong>LMPC Rules, 2011</strong>.
                  </p>
                  <div className="font-mono text-[11px] text-primary pt-1">
                    Seal Hash: <strong>{docket.digital_seal.docket_hash}</strong>
                  </div>
                </div>
              </div>

              {/* Product Info Card */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                <div className="p-3 rounded-lg border bg-card/60">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                    <Tag className="h-3 w-3" /> Product / Commodity
                  </span>
                  <p className="font-bold text-foreground text-sm mt-1 truncate">
                    {docket.product_name}
                  </p>
                </div>
                <div className="p-3 rounded-lg border bg-card/60">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                    <Building2 className="h-3 w-3" /> SKU / Product ID
                  </span>
                  <p className="font-mono font-bold text-foreground text-sm mt-1 truncate">
                    {docket.product_id}
                  </p>
                </div>
                <div className="p-3 rounded-lg border bg-card/60">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                    <Calendar className="h-3 w-3" /> Audit Timestamp
                  </span>
                  <p className="font-mono text-foreground mt-1">
                    {new Date(docket.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                  </p>
                </div>
              </div>

              {/* Status & Compliance Numbers */}
              <div className="p-4 rounded-xl border bg-card/80 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground">
                    SCREENING DETERMINATION
                  </span>
                  <span className={`px-2.5 py-1 rounded-md text-xs font-black tracking-wider ${
                    isPass
                      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30"
                      : isViolation
                        ? "bg-rose-500/15 text-rose-700 dark:text-rose-400 border border-rose-500/30"
                        : "bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30"
                  }`}>
                    {docket.overall_status}
                  </span>
                </div>

                <div className="grid grid-cols-4 gap-2 text-center text-xs pt-1">
                  <div className="p-2 rounded-lg bg-muted/50 border border-border/40">
                    <div className="text-lg font-black text-emerald-600 dark:text-emerald-400">
                      {docket.counts.verified}
                    </div>
                    <div className="text-[10px] text-muted-foreground font-medium">Verified</div>
                  </div>
                  <div className="p-2 rounded-lg bg-muted/50 border border-border/40">
                    <div className="text-lg font-black text-amber-600 dark:text-amber-400">
                      {docket.counts.review_required}
                    </div>
                    <div className="text-[10px] text-muted-foreground font-medium">Review Req.</div>
                  </div>
                  <div className="p-2 rounded-lg bg-muted/50 border border-border/40">
                    <div className="text-lg font-black text-rose-600 dark:text-rose-400">
                      {docket.counts.violations}
                    </div>
                    <div className="text-[10px] text-muted-foreground font-medium">Violations</div>
                  </div>
                  <div className="p-2 rounded-lg bg-muted/50 border border-border/40">
                    <div className="text-lg font-black text-foreground">
                      {docket.counts.total_declarations}
                    </div>
                    <div className="text-[10px] text-muted-foreground font-medium">Total Rules</div>
                  </div>
                </div>
              </div>

              {/* Package Integrity Status */}
              <div className="p-3.5 rounded-xl border bg-muted/30 flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-primary" />
                  <span className="font-semibold text-foreground">Package Integrity Verification</span>
                </div>
                <span className="font-mono font-bold text-muted-foreground">
                  {docket.package_integrity_status.replace(/_/g, " ")}
                </span>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-col sm:flex-row gap-3 pt-2">
                <Button
                  onClick={handleOpenPdf}
                  disabled={openingPdf}
                  className="flex-1 bg-primary hover:bg-primary/90 text-primary-foreground font-bold py-2.5 shadow-lg flex items-center justify-center gap-2"
                >
                  {openingPdf ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Compiling Statutory PDF…</>
                  ) : (
                    <><FileText className="h-4 w-4" /> Open Official 3-Page Dossier (PDF) <ExternalLink className="h-3.5 w-3.5 ml-1" /></>
                  )}
                </Button>
                {onClose && (
                  <Button variant="secondary" onClick={onClose} className="border-border/80">
                    Dismiss
                  </Button>
                )}
              </div>

              {/* Statutory Footnote */}
              <p className="text-[10px] text-muted-foreground text-center leading-normal pt-1">
                Issued under the authority of the Legal Metrology Act, 2009. This verification reflects certified
                computer-vision &amp; statutory rules engine evaluations recorded in the Central Metrology Registry.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
