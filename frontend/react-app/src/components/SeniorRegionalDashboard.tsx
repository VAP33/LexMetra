import { useEffect, useState } from "react";
import {
  Building2,
  CheckCircle2,
  ChevronRight,
  MapPin,
  RefreshCw,
  Store,
  TrendingUp,
} from "lucide-react";
import { getRegionalIntelligence, listSocialMentions, takeSocialMentionAction } from "@/lib/api-client";

interface RegionalData {
  total_cases: number;
  city_breakdown: Array<{
    city: string;
    state: string;
    lat: number;
    lng: number;
    total_cases: number;
    violations: number;
    fssai_issues: number;
    integrity_alerts: number;
    consumer_reports: number;
    high_priority: number;
    retailer_count: number;
  }>;
  top_retailers: Array<{
    retailer: string;
    case_count: number;
  }>;
  domain_distribution: Record<string, number>;
  category_distribution: Record<string, number>;
  ai_regional_analysis: string;
  timestamp: string;
}

export function SeniorRegionalDashboard({
  onBack,
  onOpenInspection: _onOpenInspection,
}: {
  onBack: () => void;
  onOpenInspection?: (id: string) => void;
}) {
  const [lang, setLang] = useState<"en" | "hi" | "mr">("en");
  const [data, setData] = useState<RegionalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"REGIONAL" | "SOCIAL_INTEL">("REGIONAL");

  // Social Intelligence State
  const [mentions, setMentions] = useState<any[]>([]);
  const [socialLoading, setSocialLoading] = useState(false);
  const [domainFilter, setDomainFilter] = useState("ALL");
  const [selectedCity, setSelectedCity] = useState<string | null>(null);

  useEffect(() => {
    loadRegional();
  }, [lang]);

  useEffect(() => {
    if (activeTab === "SOCIAL_INTEL") {
      loadSocial();
    }
  }, [activeTab, domainFilter]);

  async function loadRegional() {
    setLoading(true);
    try {
      const res = await getRegionalIntelligence(lang);
      setData(res);
      if (res.city_breakdown?.length > 0 && !selectedCity) {
        setSelectedCity(res.city_breakdown[0].city);
      }
    } catch (err) {
      console.error("Failed to load regional intelligence:", err);
    } finally {
      setLoading(false);
    }
  }

  async function loadSocial() {
    setSocialLoading(true);
    try {
      const res = await listSocialMentions({ domain: domainFilter });
      setMentions(res);
    } catch (err) {
      console.error("Failed to load social intelligence:", err);
    } finally {
      setSocialLoading(false);
    }
  }

  async function handleConvertMention(mentionId: string) {
    try {
      await takeSocialMentionAction(mentionId, {
        new_status: "CONVERTED_TO_CASE",
        officer_notes: "Converted to official Legal Metrology Investigation Docket by Senior Inspector.",
      });
      loadSocial();
    } catch (e: any) {
      alert("Failed to convert mention: " + e?.message);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-8">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border/70 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-brand/10 border border-brand/20 px-2.5 py-0.5 text-[10px] font-bold text-brand">
              Executive Directorate
            </span>
            <span className="text-xs text-muted-foreground">Department of Consumer Affairs</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-foreground">
            Senior Inspector Regional Intelligence & Geographic Surveillance
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Surveillance of non-compliance concentrations, district-level violations, and public social grievance shortlisting.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Language Switcher */}
          <div className="inline-flex rounded-xl border border-border/80 bg-card p-1 text-xs font-semibold shadow-2xs">
            <button
              type="button"
              onClick={() => setLang("en")}
              className={`rounded-lg px-2.5 py-1 ${lang === "en" ? "bg-brand text-brand-foreground" : "text-muted-foreground"}`}
            >
              English
            </button>
            <button
              type="button"
              onClick={() => setLang("hi")}
              className={`rounded-lg px-2.5 py-1 ${lang === "hi" ? "bg-brand text-brand-foreground" : "text-muted-foreground"}`}
            >
              हिन्दी
            </button>
            <button
              type="button"
              onClick={() => setLang("mr")}
              className={`rounded-lg px-2.5 py-1 ${lang === "mr" ? "bg-brand text-brand-foreground" : "text-muted-foreground"}`}
            >
              मराठी
            </button>
          </div>

          <button
            type="button"
            onClick={onBack}
            className="rounded-xl border border-border bg-card px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground"
          >
            Back to Dashboard
          </button>
        </div>
      </div>

      {/* Mode Switcher Tabs */}
      <div className="flex items-center gap-2 border-b border-border/60 pb-3">
        <button
          type="button"
          onClick={() => setActiveTab("REGIONAL")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition ${
            activeTab === "REGIONAL"
              ? "bg-foreground text-background"
              : "bg-muted text-muted-foreground hover:text-foreground"
          }`}
        >
          <MapPin className="h-4 w-4" />
          Geographic & District Surveillance
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("SOCIAL_INTEL")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition ${
            activeTab === "SOCIAL_INTEL"
              ? "bg-foreground text-background"
              : "bg-muted text-muted-foreground hover:text-foreground"
          }`}
        >
          <TrendingUp className="h-4 w-4" />
          Social / Public Report Intelligence Engine (USP)
        </button>
      </div>

      {activeTab === "REGIONAL" && (
        <div className="space-y-6">
          {loading && !data && (
            <div className="py-8 text-center text-xs text-muted-foreground animate-pulse">
              Loading regional surveillance data...
            </div>
          )}
          {/* Grounded AI Regional Analysis Banner */}
          {data?.ai_regional_analysis && (
            <div className="rounded-2xl border border-brand/30 bg-brand/5 p-5 shadow-sm space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-brand/15 px-2 py-0.5 text-[10px] font-bold text-brand uppercase">
                    AI Pattern Intelligence
                  </span>
                  <span className="text-[11px] text-muted-foreground">Persisted Regional Inferences</span>
                </div>
                <button
                  type="button"
                  onClick={loadRegional}
                  className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
                >
                  <RefreshCw className="h-3 w-3" /> Refresh
                </button>
              </div>
              <p className="text-xs leading-relaxed text-foreground whitespace-pre-line font-medium">
                {data.ai_regional_analysis}
              </p>
            </div>
          )}

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-2xl border border-border/70 bg-card p-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Total Monitored Cases</p>
              <p className="mt-1 text-2xl font-bold text-foreground">{data?.total_cases ?? "…"}</p>
              <span className="text-[11px] text-muted-foreground">Ground inspection + consumer tickets</span>
            </div>
            <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-destructive">LMPC Violations</p>
              <p className="mt-1 text-2xl font-bold text-destructive">{data?.domain_distribution?.LMPC ?? 0}</p>
              <span className="text-[11px] text-muted-foreground">Short weight / MRP overcharge</span>
            </div>
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-amber-600 dark:text-amber-400">FSSAI Infractions</p>
              <p className="mt-1 text-2xl font-bold text-amber-600 dark:text-amber-400">{data?.domain_distribution?.FSSAI ?? 0}</p>
              <span className="text-[11px] text-muted-foreground">Missing license / Expiry breaches</span>
            </div>
            <div className="rounded-2xl border border-blue-500/30 bg-blue-500/5 p-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-blue-500">Package Alterations</p>
              <p className="mt-1 text-2xl font-bold text-blue-500">{data?.domain_distribution?.INTEGRITY ?? 0}</p>
              <span className="text-[11px] text-muted-foreground">Catalog discrepancy heatmaps</span>
            </div>
          </div>

          {/* Interactive Geographic Split: District Table + Interactive City Card */}
          <div className="grid gap-6 lg:grid-cols-3">
            {/* Districts / Cities List */}
            <div className="lg:col-span-2 rounded-2xl border border-border/70 bg-card p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-border/60 pb-3">
                <div className="flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-brand" />
                  <h2 className="text-sm font-bold text-foreground">District & City Surveillance Grid</h2>
                </div>
                <span className="text-xs text-muted-foreground">Click region to drill down</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-border/50 text-muted-foreground font-semibold">
                      <th className="pb-2.5">Region / City</th>
                      <th className="pb-2.5">Total Dockets</th>
                      <th className="pb-2.5">Violations</th>
                      <th className="pb-2.5">FSSAI Issues</th>
                      <th className="pb-2.5">Retail Outlets</th>
                      <th className="pb-2.5 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {data?.city_breakdown.map((c) => (
                      <tr
                        key={c.city}
                        onClick={() => setSelectedCity(c.city)}
                        className={`cursor-pointer transition hover:bg-muted/50 ${
                          selectedCity === c.city ? "bg-muted font-medium" : ""
                        }`}
                      >
                        <td className="py-3 flex items-center gap-2">
                          <MapPin className="h-3.5 w-3.5 text-brand" />
                          <span>{c.city}, {c.state}</span>
                        </td>
                        <td className="py-3 font-semibold">{c.total_cases}</td>
                        <td className="py-3">
                          <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-destructive font-bold">
                            {c.violations}
                          </span>
                        </td>
                        <td className="py-3">{c.fssai_issues}</td>
                        <td className="py-3">{c.retailer_count} monitored</td>
                        <td className="py-3 text-right">
                          <button
                            type="button"
                            className="inline-flex items-center gap-1 text-[11px] font-bold text-brand hover:underline"
                          >
                            Inspect <ChevronRight className="h-3 w-3" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Selected District Detail & Hotspot Analysis */}
            <div className="rounded-2xl border border-border/70 bg-card p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-border/60 pb-3">
                <div className="flex items-center gap-2">
                  <Store className="h-4 w-4 text-amber-500" />
                  <h3 className="text-sm font-bold text-foreground">Top Problematic Retail Outlets</h3>
                </div>
              </div>

              <div className="space-y-3">
                {data?.top_retailers?.map((r, idx) => (
                  <div key={idx} className="rounded-xl border border-border/60 bg-muted/30 p-3 text-xs flex justify-between items-center">
                    <div>
                      <p className="font-semibold text-foreground">{r.retailer}</p>
                      <span className="text-[10px] text-muted-foreground">Recurrent violation notice candidate</span>
                    </div>
                    <span className="rounded-full bg-destructive/15 text-destructive font-bold px-2 py-0.5 text-[11px]">
                      {r.case_count} Cases
                    </span>
                  </div>
                ))}
              </div>

              <div className="rounded-xl border border-border/60 bg-muted/20 p-3.5 text-xs space-y-2 pt-3">
                <p className="font-bold text-foreground">Geographic Coordinates:</p>
                <p className="text-muted-foreground font-mono text-[11px]">
                  Lat: {data?.city_breakdown?.find(c => c.city === selectedCity)?.lat.toFixed(4) || "18.5204"}, 
                  Lng: {data?.city_breakdown?.find(c => c.city === selectedCity)?.lng.toFixed(4) || "73.8567"}
                </p>
                <span className="text-[10px] text-muted-foreground block">
                  Ground enforcement teams can coordinate GPS field visits directly from these coordinates.
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Social Media / Public Report Intelligence Engine */}
      {activeTab === "SOCIAL_INTEL" && (
        <div className="space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-border/60 pb-3">
            <div>
              <h2 className="text-base font-bold text-foreground">
                Public Mention Ingestion & Case Shortlisting Engine
              </h2>
              <p className="text-xs text-muted-foreground">
                NLP entity extraction across citizen tweets, NCH complaints, and FoSCoS portal mentions.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground font-semibold">Domain:</span>
              {["ALL", "LMPC", "FSSAI", "COUNTERFEIT"].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDomainFilter(d)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
                    domainFilter === d
                      ? "bg-foreground text-background"
                      : "bg-muted text-muted-foreground hover:bg-muted/80"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {socialLoading ? (
              <p className="text-xs text-muted-foreground">Ingesting public mentions…</p>
            ) : mentions.map((m) => (
              <div
                key={m.mention_id}
                className="rounded-2xl border border-border/70 bg-card p-5 space-y-3 shadow-xs"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded-md bg-muted px-2 py-0.5 text-[10px] font-mono font-bold text-muted-foreground">
                      {m.source_platform}
                    </span>
                    <span className="text-xs text-muted-foreground font-semibold">{m.author_handle}</span>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                      m.severity === "CRITICAL"
                        ? "bg-red-500/10 text-red-500"
                        : m.severity === "HIGH"
                        ? "bg-amber-500/10 text-amber-500"
                        : "bg-blue-500/10 text-blue-500"
                    }`}
                  >
                    {m.severity} SEVERITY
                  </span>
                </div>

                <p className="text-xs leading-relaxed text-foreground bg-muted/30 p-3 rounded-xl border border-border/40">
                  "{m.clean_text}"
                </p>

                <div className="grid grid-cols-2 gap-2 text-[11px] rounded-lg bg-muted/40 p-2.5">
                  <div>
                    <span className="text-muted-foreground block text-[10px]">Brand Extracted:</span>
                    <strong className="text-foreground">{m.product_brand || "General"}</strong>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[10px]">Location Pin:</span>
                    <strong className="text-foreground">📍 {m.detected_location}</strong>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[10px]">Statutory Domain:</span>
                    <span className="text-foreground font-medium">{m.regulatory_domain}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[10px]">AI Confidence:</span>
                    <span className="text-brand font-bold">{(m.confidence_score * 100).toFixed(0)}%</span>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-border/50 text-xs">
                  <span className="text-muted-foreground text-[11px]">
                    Status: <strong>{m.review_status}</strong>
                  </span>
                  {m.review_status === "SHORTLISTED" ? (
                    <button
                      type="button"
                      onClick={() => handleConvertMention(m.mention_id)}
                      className="rounded-xl bg-destructive text-destructive-foreground font-bold px-3 py-1.5 text-xs hover:bg-destructive/90 transition"
                    >
                      Convert to Formal Case
                    </button>
                  ) : (
                    <span className="text-emerald-500 font-bold inline-flex items-center gap-1 text-[11px]">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Investigation Docket Created
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
