import { useState } from "react";
import {
  AlertTriangle,
  LoaderCircle,
  Send,
  ShieldAlert,
  X,
} from "lucide-react";
import {
  submitConsumerReport,
} from "@/lib/api-client";
import { type Inspection } from "@/lib/types";

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

