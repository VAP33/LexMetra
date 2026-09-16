import { useEffect, useState } from "react";
import {
  Building2,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  Layers,
  MapPin,
  Play,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Store,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  getRegionalIntelligence,
  getSocialSummary,
  listSocialMentions,
  reprocessSocialPipeline,
  takeSocialMentionAction,
} from "@/lib/api-client";

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

interface SocialSummaryData {
  data_classification: string;
  total_signals_analyzed: number;
  region_breakdown: Array<{ city: string; count: number }>;
  domain_distribution: Record<string, number>;
  category_distribution: Record<string, number>;
  active_clusters: Array<{
    cluster_label: string;
    count: number;
    members: Array<{
      mention_id: string;
      author: string;
      city: string;
      brand?: string;
      priority_score: number;
    }>;
  }>;
  top_region: string;
  top_category: string;
  ai_regional_summary: string;
  timestamp: string;
}

export function SeniorRegionalDashboard({
  onBack,
  onOpenInspection,
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
  const [socialSummary, setSocialSummary] = useState<SocialSummaryData | null>(null);
  const [socialLoading, setSocialLoading] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [domainFilter, setDomainFilter] = useState("ALL");
  const [cityFilter, setCityFilter] = useState("ALL");
  const [selectedCity, setSelectedCity] = useState<string | null>(null);

  useEffect(() => {
    loadRegional();
  }, [lang]);

  useEffect(() => {
    if (activeTab === "SOCIAL_INTEL") {
      loadSocial();
    }
  }, [activeTab, domainFilter, cityFilter, lang]);

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
      const [mRes, sRes] = await Promise.all([
        listSocialMentions({
          domain: domainFilter !== "ALL" ? domainFilter : undefined,
          city: cityFilter !== "ALL" ? cityFilter : undefined,
        }),
        getSocialSummary(lang),
      ]);
      setMentions(mRes);
      setSocialSummary(sRes);
    } catch (err) {
      console.error("Failed to load social intelligence:", err);
    } finally {
      setSocialLoading(false);
    }
  }

  async function handleReprocessPipeline() {
    setReprocessing(true);
    try {
      await reprocessSocialPipeline();
      await loadSocial();
    } catch (e: any) {
      alert("Pipeline reprocess failed: " + e?.message);
    } finally {
      setReprocessing(false);
    }
  }

  async function handleConvertMention(mentionId: string) {
    try {
      await takeSocialMentionAction(mentionId, {
        new_status: "CONVERTED_TO_CASE",
        officer_notes: "Converted to official Legal Metrology Investigation Docket by Senior Officer.",
      });
      loadSocial();
    } catch (e: any) {
      alert("Failed to convert mention: " + e?.message);
    }
  }

  async function handleAssignInspector(mentionId: string) {
    try {
      await takeSocialMentionAction(mentionId, {
        new_status: "ASSIGNED_TO_INSPECTOR",
        officer_notes: "Dispatched field inspector for surprise physical audit and verification.",
        assigned_officer: "field_inspector_squad",
      });
      loadSocial();
    } catch (e: any) {
      alert("Failed to assign inspector: " + e?.message);
    }
  }

  async function handleDismissMention(mentionId: string) {
    try {
      await takeSocialMentionAction(mentionId, {
        new_status: "DISMISSED",
        officer_notes: "Dismissed by reviewing officer as unsubstantiated or non-statutory.",
      });
      loadSocial();
    } catch (e: any) {
      alert("Failed to dismiss mention: " + e?.message);
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
            Senior Inspector Regional Intelligence & Surveillance Center
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Regional non-compliance concentration, district-level enforcement, and public social grievance shortlisting.
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
            className="rounded-xl border border-border bg-card px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition"
          >
            Back to Command Center
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
          <span className="rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 px-2 py-0.2 text-[9px] font-bold uppercase">
            Live Engine
          </span>
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
                <p className="font-bold text-foreground">Geographic Coordinates ({selectedCity}):</p>
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
        <div className="space-y-6">
          {/* Prominent Demo & Regulatory Attribution Notice */}
          <div className="rounded-2xl border border-amber-500/40 bg-amber-500/10 p-4 text-xs space-y-1">
            <div className="flex items-center gap-2 text-amber-700 dark:text-amber-300 font-bold">
              <ShieldAlert className="h-4 w-4" />
              <span>SIMULATED PUBLIC INTELLIGENCE / DEMONSTRATION ENGINE</span>
            </div>
            <p className="text-amber-800 dark:text-amber-200 text-[11px] leading-relaxed">
              This pipeline demonstrates how LexMetra ingests, deduplicates, clusters, and dynamically prioritizes public consumer posts from X/Twitter, NCH, and FoSCoS mentions into actionable enforcement cases. Simulated data is strictly partitioned from verified statutory inspections.
            </p>
          </div>

          {/* Grounded AI Narrative from Processed Dataset */}
          {socialSummary?.ai_regional_summary && (
            <div className="rounded-2xl border border-brand/30 bg-brand/5 p-5 shadow-sm space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-brand" />
                  <span className="rounded-full bg-brand/15 px-2.5 py-0.5 text-[10px] font-bold text-brand uppercase">
                    AI Public Intelligence Synthesis
                  </span>
                  <span className="text-[11px] text-muted-foreground font-medium">
                    Grounded strictly in {socialSummary.total_signals_analyzed} processed public signals
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleReprocessPipeline}
                  disabled={reprocessing}
                  className="rounded-xl border border-brand/30 bg-background px-3 py-1.5 text-xs font-semibold text-brand hover:bg-brand/10 transition inline-flex items-center gap-1.5 disabled:opacity-50"
                >
                  <Play className={`h-3 w-3 ${reprocessing ? "animate-spin" : ""}`} />
                  {reprocessing ? "Reprocessing Pipeline…" : "Re-run 13-Stage Pipeline"}
                </button>
              </div>
              <p className="text-xs leading-relaxed text-foreground whitespace-pre-line font-medium">
                {socialSummary.ai_regional_summary}
              </p>
            </div>
          )}

          {/* Active Hotspot Clusters Grid */}
          {socialSummary?.active_clusters && socialSummary.active_clusters.length > 0 && (
            <div className="rounded-2xl border border-border/70 bg-card p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-border/60 pb-3">
                <div className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-brand" />
                  <h3 className="text-sm font-bold text-foreground">Detected Multi-Post Recurrent Clusters</h3>
                </div>
                <span className="text-xs text-muted-foreground">
                  Grouped by Brand, Region & Violation Pattern
                </span>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                {socialSummary.active_clusters.map((c, idx) => (
                  <div key={idx} className="rounded-xl border border-destructive/20 bg-destructive/5 p-3.5 text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="rounded-full bg-destructive/15 text-destructive font-bold px-2 py-0.5 text-[10px]">
                        {c.count} Related Public Grievances
                      </span>
                      <span className="text-[11px] font-bold text-foreground">Cluster #{idx + 1}</span>
                    </div>
                    <p className="font-semibold text-foreground text-xs">{c.cluster_label}</p>
                    <div className="flex flex-wrap gap-1 text-[10px] text-muted-foreground">
                      {c.members.map((m) => (
                        <span key={m.mention_id} className="rounded bg-background border border-border/60 px-1.5 py-0.5">
                          {m.author} ({m.city}) • Priority {m.priority_score}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Filter Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-border/60 pb-3">
            <div>
              <h2 className="text-sm font-bold text-foreground">
                Shortlisted Grievance Cases ({mentions.length})
              </h2>
              <p className="text-[11px] text-muted-foreground">
                Sorted by dynamic statutory priority score (0–100) calculated via safety impact, evidence, and clustering.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {/* Region Filter */}
              <div className="flex items-center gap-1 text-xs">
                <span className="text-muted-foreground font-semibold">Region:</span>
                <select
                  value={cityFilter}
                  onChange={(e) => setCityFilter(e.target.value)}
                  className="rounded-lg border border-border bg-background px-2 py-1 text-xs font-semibold text-foreground"
                >
                  <option value="ALL">All Regions</option>
                  <option value="Pune">Pune</option>
                  <option value="Mumbai">Mumbai</option>
                  <option value="Nashik">Nashik</option>
                  <option value="Nagpur">Nagpur</option>
                  <option value="Chhatrapati Sambhajinagar">Chhatrapati Sambhajinagar</option>
                  <option value="Thane">Thane</option>
                  <option value="Gurugram">Gurugram</option>
                </select>
              </div>

              {/* Domain Filter */}
              <div className="flex items-center gap-1 text-xs">
                <span className="text-muted-foreground font-semibold">Domain:</span>
                {["ALL", "LMPC", "FSSAI", "COUNTERFEIT"].map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDomainFilter(d)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
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
          </div>

          {/* Shortlisted Cases Cards Grid */}
          <div className="grid gap-4 md:grid-cols-2">
            {socialLoading ? (
              <p className="text-xs text-muted-foreground py-8">Ingesting and prioritizing public mentions…</p>
            ) : mentions.length === 0 ? (
              <p className="text-xs text-muted-foreground py-8 col-span-2 text-center">
                No public signals matching active filters.
              </p>
            ) : (
              mentions.map((m) => (
                <div
                  key={m.mention_id}
                  className="rounded-2xl border border-border/70 bg-card p-5 space-y-3.5 shadow-xs flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    {/* Top Row: Platform, Author, Dynamic Priority Score Badge */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="rounded-md bg-muted px-2 py-0.5 text-[10px] font-mono font-bold text-muted-foreground">
                          {m.source_platform}
                        </span>
                        <span className="text-xs text-muted-foreground font-semibold">{m.author_handle}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold ${
                            m.severity === "CRITICAL"
                              ? "bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20"
                              : m.severity === "HIGH"
                              ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                              : "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                          }`}
                        >
                          {m.severity} • {m.priority_score}/100
                        </span>
                      </div>
                    </div>

                    {/* Complaint Text */}
                    <p className="text-xs leading-relaxed text-foreground bg-muted/30 p-3 rounded-xl border border-border/40 font-medium">
                      "{m.clean_text}"
                    </p>

                    {/* Entity Matrix */}
                    <div className="grid grid-cols-2 gap-2 text-[11px] rounded-xl bg-muted/40 p-3">
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-bold">Product / Brand</span>
                        <strong className="text-foreground">{m.product_brand || "Packaged Commodity"}</strong>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-bold">Location</span>
                        <strong className="text-foreground">📍 {m.district_or_city}, {m.state}</strong>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-bold">Statutory Domain</span>
                        <span className="text-foreground font-semibold">{m.regulatory_domain}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-bold">Category</span>
                        <span className="text-foreground font-semibold">{m.complaint_category}</span>
                      </div>
                    </div>

                    {/* Evidence & Dynamic Prioritization Rationale */}
                    <div className="rounded-xl border border-border/60 bg-background/50 p-2.5 text-[11px] space-y-1">
                      <div className="flex items-center justify-between text-[10px] font-bold">
                        <span className="text-muted-foreground uppercase">Dynamic Prioritization Rationale:</span>
                        {m.has_evidence && (
                          <span className="text-emerald-600 dark:text-emerald-400">
                            📎 Evidence Attached ({m.evidence_type})
                          </span>
                        )}
                      </div>
                      <p className="text-muted-foreground leading-relaxed">
                        {m.prioritization_rationale}
                      </p>
                      {m.cluster_label && (
                        <span className="inline-block mt-1 rounded bg-brand/10 text-brand px-1.5 py-0.5 text-[10px] font-bold">
                          {m.cluster_label}
                        </span>
                      )}
                    </div>

                    {/* Related Correlated Inspection link */}
                    {m.related_inspection_id && (
                      <div className="flex items-center justify-between rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1.5 text-[11px]">
                        <span className="text-emerald-700 dark:text-emerald-300 font-semibold flex items-center gap-1">
                          <CheckCircle2 className="h-3.5 w-3.5" /> Correlated Ground Inspection Found
                        </span>
                        <button
                          type="button"
                          onClick={() => onOpenInspection?.(m.related_inspection_id)}
                          className="font-bold text-brand hover:underline inline-flex items-center gap-0.5"
                        >
                          View Docket <ExternalLink className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Human Officer Review Actions */}
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pt-3 border-t border-border/50 text-xs mt-2">
                    <span className="text-muted-foreground text-[11px]">
                      Status: <strong className="text-foreground">{m.review_status}</strong>
                    </span>

                    {m.review_status === "SHORTLISTED" ? (
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleConvertMention(m.mention_id)}
                          className="rounded-xl bg-destructive text-destructive-foreground font-bold px-2.5 py-1 text-[11px] hover:bg-destructive/90 transition shadow-2xs"
                        >
                          Convert to Case
                        </button>
                        <button
                          type="button"
                          onClick={() => handleAssignInspector(m.mention_id)}
                          className="rounded-xl border border-border bg-background text-foreground font-bold px-2.5 py-1 text-[11px] hover:bg-muted transition"
                        >
                          Dispatch Field Squad
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDismissMention(m.mention_id)}
                          className="text-muted-foreground hover:text-foreground text-[11px] px-1"
                        >
                          Dismiss
                        </button>
                      </div>
                    ) : m.review_status === "CONVERTED_TO_CASE" ? (
                      <span className="text-emerald-600 dark:text-emerald-400 font-bold inline-flex items-center gap-1 text-[11px]">
                        <CheckCircle2 className="h-3.5 w-3.5" /> Converted to Formal Investigation Docket
                      </span>
                    ) : m.review_status === "ASSIGNED_TO_INSPECTOR" ? (
                      <span className="text-blue-600 dark:text-blue-400 font-bold inline-flex items-center gap-1 text-[11px]">
                        <Users className="h-3.5 w-3.5" /> Field Inspection Squad Dispatched
                      </span>
                    ) : (
                      <span className="text-muted-foreground font-semibold text-[11px]">
                        Dismissed as Noise
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
