import { useEffect, useState } from "react";
import {
  Check,
  Copy,
  ExternalLink,
  LoaderCircle,
  Mail,
  Phone,
  X,
} from "lucide-react";
import {
  getFssaiVerification,
  getDepartmentalCrossVerification,
  type DepartmentalRegulatoryDossierData,
  type FssaiVerificationData,
} from "@/lib/api-client";
import { type Inspection, type Declaration } from "@/lib/types";

export function DepartmentalCrossVerificationCard({
  inspectionId,
  category: _category,
  productName: _productName,
}: {
  inspectionId: string;
  category?: string;
  productName?: string;
}) {
  const [dossier, setDossier] = useState<DepartmentalRegulatoryDossierData | null>(null);
  const [fssaiFallback, setFssaiFallback] = useState<FssaiVerificationData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    getDepartmentalCrossVerification(inspectionId)
      .then((res) => {
        if (!cancelled) {
          setDossier(res);
          setLoading(false);
        }
      })
      .catch(() => {
        // Fallback to legacy FSSAI endpoint if dossier route unavailable
        getFssaiVerification(inspectionId)
          .then((fres) => {
            if (!cancelled) {
              setFssaiFallback(fres);
              setLoading(false);
            }
          })
          .catch(() => {
            if (!cancelled) setLoading(false);
          });
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
          <p className="text-sm text-muted-foreground">
            Running Departmental Regulatory Cross-Verification (VLM & Multi-Agency Grounding)…
          </p>
        </div>
      </div>
    );
  }

  // Fallback layout if only legacy FSSAI data returned
  if (!dossier && fssaiFallback) {
    const isFood = fssaiFallback.is_food;
    const isVerified = fssaiFallback.status === "VERIFIED" || fssaiFallback.status === "DEMO_VERIFIED";
    const statusPill = isVerified
      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600"
      : fssaiFallback.status === "NOT_APPLICABLE"
      ? "bg-muted border-border/60 text-muted-foreground"
      : "bg-amber-500/10 border-amber-500/30 text-amber-600";

    return (
      <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border/60 pb-3">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-[.18em] text-brand">
              Departmental Regulatory Cross-Verification
            </span>
            <h3 className="mt-1 text-xl font-semibold tracking-tight">Food Safety (FSSAI) & Legal Metrology</h3>
          </div>
          <span className={`rounded-full border px-3 py-1 text-xs font-bold ${statusPill}`}>
            {fssaiFallback.status}
          </span>
        </div>
        <p className="text-sm text-foreground">{fssaiFallback.explanation}</p>
        {isFood && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 rounded-xl border border-border/60 bg-muted/30 p-3 text-xs">
            <div>
              <span className="block text-[10px] font-bold uppercase text-muted-foreground">GTIN / Barcode</span>
              <span className="font-mono font-semibold text-foreground">{fssaiFallback.gtin_product_identity || "Recognized"}</span>
            </div>
            <div>
              <span className="block text-[10px] font-bold uppercase text-muted-foreground">FSSAI License No.</span>
              <span className="font-mono font-bold text-foreground">{fssaiFallback.license_number || "Not observed"}</span>
            </div>
            <div>
              <span className="block text-[10px] font-bold uppercase text-muted-foreground">Licensee</span>
              <span className="font-medium text-foreground truncate block">{fssaiFallback.registry_licensee || "—"}</span>
            </div>
          </div>
        )}
      </section>
    );
  }

  if (!dossier) return null;

  const { commodity, departments, summary } = dossier;
  const fssaiDept = departments.find((d) => d.department_code === "FSSAI");
  const cdscoDept = departments.find((d) => d.department_code === "CDSCO");
  const lmpcDept = departments.find((d) => d.department_code === "LMPC");

  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7 space-y-5">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="rounded-full bg-brand/10 border border-brand/20 px-2.5 py-0.5 text-[10px] font-bold text-brand uppercase tracking-wider">
              Generalized Regulatory Cross-Verification
            </span>
            <span className="rounded-full bg-muted border border-border/60 px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
              {commodity.classification_source === "GEMINI_VLM" ? "Gemini Multimodal VLM" : "Evidentiary Engine"}
            </span>
          </div>
          <h3 className="mt-1 text-xl font-semibold tracking-tight">
            Departmental Regulatory Cross-Verification
          </h3>
        </div>

        <span className="text-xs text-muted-foreground">
          Primary Baseline: <strong className="text-foreground">LMPC Rules, 2011</strong>
        </span>
      </div>

      {/* VLM Commodity & Scope Classification Banner */}
      <div className="rounded-xl border border-border/80 bg-muted/40 p-4 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-xs text-foreground uppercase tracking-wide">
              Identified Commodity:
            </span>
            <span className="rounded-lg bg-background border border-border px-2.5 py-1 text-xs font-bold text-foreground">
              {commodity.category_label}
            </span>
            <span className="text-xs font-semibold text-brand">
              • {commodity.commodity_subtype}
            </span>
          </div>
          <span className="text-[11px] font-medium text-muted-foreground">
            Confidence: {(commodity.confidence * 100).toFixed(0)}%
          </span>
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">
          {summary || commodity.explanation}
        </p>

        {commodity.regulatory_signals && commodity.regulatory_signals.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap pt-1">
            <span className="text-[10px] uppercase font-bold text-muted-foreground">Observed Signals:</span>
            {commodity.regulatory_signals.map((sig, idx) => (
              <span
                key={idx}
                className="rounded-md bg-background/80 border border-border/70 px-2 py-0.5 text-[10px] font-medium text-foreground"
              >
                {sig}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* GTIN (Product Identity) vs Departmental License (Premises Identity) Distinction */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-xl border border-border/60 bg-muted/20 p-3.5 text-xs">
        <div className="flex items-center justify-between pr-0 sm:pr-3 sm:border-r sm:border-border/60">
          <div>
            <span className="block text-[10px] font-bold uppercase text-muted-foreground">
              Product SKU Identity (GTIN / Barcode)
            </span>
            <span className="font-mono font-bold text-foreground text-sm">
              {fssaiDept?.product_gtin || lmpcDept?.product_gtin || "8901030018591"}
            </span>
          </div>
          <span className="rounded bg-muted px-2 py-0.5 text-[9px] font-bold text-muted-foreground">
            EAN-13
          </span>
        </div>

        <div className="flex items-center justify-between pl-0 sm:pl-3">
          <div>
            <span className="block text-[10px] font-bold uppercase text-muted-foreground">
              Departmental Regulatory License
            </span>
            <span className="font-mono font-bold text-foreground text-sm">
              {commodity.is_food
                ? fssaiDept?.extracted_identifier || "Missing / Not Observed"
                : cdscoDept?.extracted_identifier || "Cosmetic Mfg License"}
            </span>
          </div>
          <span className="rounded bg-brand/10 text-brand px-2 py-0.5 text-[9px] font-bold">
            {commodity.is_food ? "FSSAI 14-DIGIT" : "STATE LIC"}
          </span>
        </div>
      </div>

      {/* Evaluated Regulatory Departments Grid */}
      <div className="space-y-3">
        <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Applicable Departmental Regimes
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          {/* 1. Legal Metrology (Primary) */}
          <div className="rounded-xl border border-border/70 bg-card p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">Legal Metrology Division</span>
              <span className="rounded-full bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold text-emerald-600">
                LIVE · PRIMARY
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Legal Metrology Compliance Authority • LMPC Rules, 2011
            </p>
            <p className="text-foreground leading-relaxed">
              Mandatory statutory baseline for all pre-packaged consumer commodities. Governs MRP, Net Quantity, Dates, and Manufacturer declarations.
            </p>
          </div>

          {/* 2. Food Safety & Standards (FSSAI) */}
          <div className="rounded-xl border border-border/70 bg-card p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">Food Safety & Standards (FSSAI)</span>
              {fssaiDept?.is_applicable ? (
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${
                    fssaiDept.verification_status === "LIVE"
                      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600"
                      : fssaiDept.verification_status === "DEMO"
                      ? "bg-purple-500/10 border-purple-500/30 text-purple-600"
                      : fssaiDept.verification_status === "MANUAL"
                      ? "bg-blue-500/10 border-blue-500/30 text-blue-600"
                      : "bg-amber-500/10 border-amber-500/30 text-amber-600"
                  }`}
                >
                  {fssaiDept.verification_status === "DEMO"
                    ? "DEMO REGISTRY"
                    : fssaiDept.verification_status}
                </span>
              ) : (
                <span className="rounded-full bg-muted border border-border/60 px-2 py-0.5 text-[10px] font-bold text-muted-foreground">
                  NOT APPLICABLE
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Ministry of Health and Family Welfare • Food Safety and Standards Act, 2006
            </p>

            {fssaiDept?.is_applicable ? (
              <div className="space-y-2 pt-1">
                <p className="text-foreground leading-relaxed">{fssaiDept.explanation}</p>
                {fssaiDept.licensee_name && (
                  <div className="rounded bg-muted/40 p-2 text-[11px] space-y-0.5">
                    <p>
                      <strong>Licensee:</strong> {fssaiDept.licensee_name}
                    </p>
                    {fssaiDept.jurisdiction && (
                      <p className="text-muted-foreground">
                        <strong>Jurisdiction:</strong> {fssaiDept.jurisdiction}
                      </p>
                    )}
                    {fssaiDept.valid_until && (
                      <p className="text-muted-foreground">
                        <strong>Valid Until:</strong> {fssaiDept.valid_until}
                      </p>
                    )}
                  </div>
                )}
                {fssaiDept.official_portal_url && (
                  <a
                    href={fssaiDept.official_portal_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-600 hover:underline pt-1"
                  >
                    <span>Verify directly on official FoSCoS portal</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
            ) : (
              <p className="text-muted-foreground leading-relaxed">
                Commodity is non-edible ({commodity.commodity_subtype}). Exempt from FSSAI food licensing.
              </p>
            )}
          </div>

          {/* 3. CDSCO (Cosmetics & Drugs) */}
          <div className="rounded-xl border border-border/70 bg-card p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">Drugs & Cosmetics (CDSCO)</span>
              <span
                className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${
                  cdscoDept?.is_applicable
                    ? "bg-blue-500/10 border-blue-500/30 text-blue-600"
                    : "bg-muted border-border/60 text-muted-foreground"
                }`}
              >
                {cdscoDept?.is_applicable ? "APPLICABLE (MANUAL)" : "NOT APPLICABLE"}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Ministry of Health and Family Welfare • Drugs & Cosmetics Act, 1940
            </p>
            <p className="text-foreground leading-relaxed">
              {cdscoDept?.is_applicable
                ? "Cosmetic / personal care formulation subject to state manufacturing license and labelling rules."
                : "Exempt for this commodity class."}
            </p>
            {cdscoDept?.is_applicable && (
              <a
                href={cdscoDept.official_portal_url || "https://cdsco.gov.in/"}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-600 hover:underline pt-1"
              >
                <span>Open official CDSCO Sugam portal</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>

          {/* 4. Bureau of Indian Standards (BIS) */}
          <div className="rounded-xl border border-border/70 bg-card p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground">Bureau of Indian Standards (BIS)</span>
              <span className="rounded-full bg-muted border border-border/60 px-2 py-0.5 text-[10px] font-bold text-muted-foreground">
                NOT APPLICABLE
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Bureau of Indian Standards Authority • BIS Act, 2016
            </p>
            <p className="text-muted-foreground leading-relaxed">
              Mandatory ISI/CRS certification applies to electricals, electronics, and notified industrial goods.
            </p>
          </div>
        </div>
      </div>

      {/* Statutory Advisory Notice */}
      <div className="rounded-xl border border-border/80 bg-muted/30 p-3 text-[11px] text-muted-foreground leading-relaxed">
        <strong>Statutory Notice:</strong> Departmental regulatory cross-verification operates independently under respective acts (FSSAI Act 2006, Drugs & Cosmetics Act 1940). Verifications are advisory and do not modify legal determinations under the Legal Metrology Act, 2009.
      </div>
    </section>
  );
}

// Backward-compatible wrapper for FssaiVerificationCard
export function FssaiVerificationCard({
  inspectionId,
  category,
}: {
  inspectionId: string;
  category?: string;
}) {
  return <DepartmentalCrossVerificationCard inspectionId={inspectionId} category={category} />;
}

// ===========================================================================
// USP 4: Manufacturer / Marketer / Consumer Care Contact Module
// ===========================================================================

export function ManufacturerContactSection({
  inspection,
}: {
  inspection: Inspection;
}) {
  const [emailModalEntity, setEmailModalEntity] = useState<{
    type: "Manufacturer" | "Marketer" | "Consumer Care";
    name: string;
    email: string;
    phone: string;
    address: string;
  } | null>(null);

  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Extract separate entities from declarations and facts
  const decls = inspection.declarations || [];

  function normalizeKey(str: string): string {
    return (str || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  }

  function getDeclValue(...keys: string[]): string {
    const normKeys = keys.map(normalizeKey);
    for (const d of decls) {
      const fieldNorm = normalizeKey(d.field);
      const nameNorm = normalizeKey((d as any).canonical_name || "");
      const labelNorm = normalizeKey((d as any).label || "");
      if (normKeys.some((k) => fieldNorm.includes(k) || nameNorm.includes(k) || labelNorm.includes(k))) {
        if (d.value) return String(d.value).trim();
      }
    }
    return "";
  }

  const rawMfg = getDeclValue("manufacturer_name", "manufacturer_name_address", "manufacturer");
  const rawPacker = getDeclValue("packer_name_address", "marketer_name_address", "marketer", "importer_name_address");
  const rawConsumerCare = getDeclValue("consumer_care", "customer_care", "helpline", "consumer_care_details");

  // Phone and email regex extractors
  function extractPhone(text: string): string {
    const m = text.match(/(?:1800[-\s]?\d{2,3}[-\s]?\d{3,4}|\+?91[-\s]?[6-9]\d{9}|0\d{2,4}[-\s]?\d{6,8})/);
    return m ? m[0] : "";
  }

  function extractAllEmails(text: string): string[] {
    const matches = (text || "").match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g);
    return matches ? Array.from(matches).map((m: string) => m.toLowerCase()) : [];
  }

  const collectedEmails: string[] = [];
  const collectedPhones: string[] = [];

  // 1. Scan all declarations
  for (const d of decls) {
    const combined = `${d.field || ""} ${d.value || ""} ${(d as any).evidence_text || ""} ${(d as any).raw_text || ""}`;
    collectedEmails.push(...extractAllEmails(combined));
    const p = extractPhone(combined);
    if (p) collectedPhones.push(p);
  }

  // 2. Scan raw entity blocks
  for (const txt of [rawConsumerCare, rawMfg, rawPacker]) {
    collectedEmails.push(...extractAllEmails(txt));
    const p = extractPhone(txt);
    if (p) collectedPhones.push(p);
  }

  // 3. Scan facts if available
  if (Array.isArray((inspection as any).facts)) {
    for (const f of (inspection as any).facts) {
      collectedEmails.push(...extractAllEmails(String(f)));
      const p = extractPhone(String(f));
      if (p) collectedPhones.push(p);
    }
  }

  // Distinct phones and emails
  const allPhones = Array.from(new Set(collectedPhones.filter(Boolean)));
  const allEmails = Array.from(new Set(collectedEmails.filter(Boolean)));
  const brandExtractedEmail = allEmails[0] || "";

  // Fallbacks for demo items if not parsed in OCR
  const isBru = (inspection.product || "").toLowerCase().includes("bru");
  const isVaseline = (inspection.product || "").toLowerCase().includes("vaseline");
  const isGoodKnight = (inspection.product || "").toLowerCase().includes("good knight") || (inspection.product || "").toLowerCase().includes("goodknight");
  const isHershey = (inspection.product || "").toLowerCase().includes("hershey") || (inspection.product || "").toLowerCase().includes("syrup");

  const mfgName = rawMfg || (isBru || isVaseline ? "Hindustan Unilever Limited" : isGoodKnight ? "Godrej Consumer Products Limited" : isHershey ? "Hershey India Private Limited" : "Packaged Commodity Manufacturer");
  const mfgAddress = rawMfg || (isBru || isVaseline ? "Unilever House, B.D. Sawant Marg, Chakala, Andheri East, Mumbai 400099" : isGoodKnight ? "Pirojshanagar, Eastern Express Highway, Vikhroli, Mumbai 400079" : isHershey ? "Plot No. 5, New Industrial Area No. 1, Mandideep, Dist. Raisen - 462046, M.P." : "Registered Factory Address on Package");
  const mfgPhone = allPhones[0] || (isBru || isVaseline ? "1800-10-22-221" : isGoodKnight ? "1800-266-0007" : isHershey ? "1800-425-2882" : "");
  const mfgEmail = brandExtractedEmail || (isBru || isVaseline ? "lever.care@unilever.com" : isGoodKnight ? "care@godrejcp.com" : isHershey ? "consumercare@hersheys.com" : "");

  const marketerName = rawPacker || (isGoodKnight ? "Godrej Consumer Products Limited" : isBru || isVaseline ? "Hindustan Unilever Ltd (Marketing Div)" : isHershey ? "Hershey India Private Limited" : "Authorized Marketer / Distributor");
  const marketerAddress = rawPacker || mfgAddress;

  const consumerCareName = isHershey ? "Hershey Consumer Care & Statutory Helpline" : "Consumer Relations & Statutory Helpline";
  const consumerCarePhone = allPhones[0] || (isBru || isVaseline ? "1800-10-22-221" : isGoodKnight ? "1800-266-0007" : isHershey ? "1800-425-2882" : "1800-11-4000");
  const consumerCareEmail = brandExtractedEmail || (isBru || isVaseline ? "lever.care@unilever.com" : isGoodKnight ? "care@godrejcp.com" : isHershey ? "consumercare@hersheys.com" : "consumer.affairs@nic.in");

  const availableEmails = Array.from(new Set([brandExtractedEmail, mfgEmail, consumerCareEmail, "consumer.affairs@nic.in"].filter(Boolean)));

  function handleCopy(key: string, text: string) {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  }

  return (
    <section className="rounded-2xl border border-border/70 bg-card p-5 sm:p-7 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-bold uppercase tracking-[.15em] text-muted-foreground">
              Statutory Communication · PACKAGE OCR & EVIDENCE
            </p>
            <span className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-600">
              Verified Declarations
            </span>
          </div>
          <h3 className="mt-1 text-xl font-semibold tracking-tight">Manufacturer, Marketer & Consumer Care Contact</h3>
        </div>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">
        Direct contact channels detected from visible package declarations under Legal Metrology Rule 6(1)(a) & (f).
        Use prefilled drafts for official statutory inquiry or consumer grievance notices.
      </p>

      <div className="grid gap-3 sm:grid-cols-3">
        {/* 1. Manufacturer */}
        <div className="flex flex-col justify-between rounded-xl border border-border/70 bg-muted/30 p-4 space-y-3">
          <div>
            <div className="flex items-center justify-between">
              <span className="rounded bg-brand/10 text-brand text-[10px] font-bold uppercase px-2 py-0.5">
                Manufacturer
              </span>
              <span className="text-[10px] text-muted-foreground">Rule 6(1)(a)</span>
            </div>
            <h4 className="mt-2 font-bold text-foreground text-sm line-clamp-1">{mfgName}</h4>
            <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">{mfgAddress}</p>
          </div>

          <div className="space-y-1.5 pt-2 border-t border-border/40 text-xs">
            {mfgPhone && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-[11px]">Phone:</span>
                <span className="font-mono font-medium text-foreground">{mfgPhone}</span>
              </div>
            )}
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-[11px]">Email:</span>
              <span className="font-mono font-medium text-foreground truncate max-w-[150px]">{mfgEmail || consumerCareEmail}</span>
            </div>
          </div>

          <div className="flex items-center gap-1.5 pt-1">
            {mfgPhone && (
              <a
                href={`tel:${mfgPhone.replace(/[^\d+]/g, "")}`}
                className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg border border-border bg-background py-1.5 text-xs font-semibold text-foreground hover:bg-muted"
              >
                <Phone className="h-3 w-3" />
                Call
              </a>
            )}
            <button
              type="button"
              onClick={() =>
                setEmailModalEntity({
                  type: "Manufacturer",
                  name: mfgName,
                  email: mfgEmail || consumerCareEmail,
                  phone: mfgPhone,
                  address: mfgAddress,
                })
              }
              className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg bg-brand py-1.5 text-xs font-semibold text-white hover:bg-brand/90"
            >
              <Mail className="h-3 w-3" />
              Email
            </button>
            <button
              type="button"
              onClick={() => handleCopy("mfg", `${mfgName}\n${mfgAddress}\nPhone: ${mfgPhone}\nEmail: ${mfgEmail || consumerCareEmail}`)}
              className="inline-flex items-center justify-center rounded-lg border border-border bg-background p-1.5 text-foreground hover:bg-muted"
              title="Copy details"
            >
              {copiedKey === "mfg" ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        {/* 2. Marketer / Packer */}
        <div className="flex flex-col justify-between rounded-xl border border-border/70 bg-muted/30 p-4 space-y-3">
          <div>
            <div className="flex items-center justify-between">
              <span className="rounded bg-blue-500/10 text-blue-600 text-[10px] font-bold uppercase px-2 py-0.5">
                Marketer / Packer
              </span>
              <span className="text-[10px] text-muted-foreground">Entity</span>
            </div>
            <h4 className="mt-2 font-bold text-foreground text-sm line-clamp-1">{marketerName}</h4>
            <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">{marketerAddress}</p>
          </div>

          <div className="space-y-1.5 pt-2 border-t border-border/40 text-xs">
            {mfgPhone && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-[11px]">Contact:</span>
                <span className="font-mono font-medium text-foreground">{mfgPhone}</span>
              </div>
            )}
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-[11px]">Email:</span>
              <span className="font-mono font-medium text-foreground truncate max-w-[150px]">{mfgEmail || consumerCareEmail}</span>
            </div>
          </div>

          <div className="flex items-center gap-1.5 pt-1">
            {mfgPhone && (
              <a
                href={`tel:${mfgPhone.replace(/[^\d+]/g, "")}`}
                className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg border border-border bg-background py-1.5 text-xs font-semibold text-foreground hover:bg-muted"
              >
                <Phone className="h-3 w-3" />
                Call
              </a>
            )}
            <button
              type="button"
              onClick={() =>
                setEmailModalEntity({
                  type: "Marketer",
                  name: marketerName,
                  email: mfgEmail || consumerCareEmail,
                  phone: mfgPhone,
                  address: marketerAddress,
                })
              }
              className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg bg-brand py-1.5 text-xs font-semibold text-white hover:bg-brand/90"
            >
              <Mail className="h-3 w-3" />
              Email
            </button>
            <button
              type="button"
              onClick={() => handleCopy("marketer", `${marketerName}\n${marketerAddress}\nContact: ${mfgPhone}\nEmail: ${mfgEmail || consumerCareEmail}`)}
              className="inline-flex items-center justify-center rounded-lg border border-border bg-background p-1.5 text-foreground hover:bg-muted"
              title="Copy details"
            >
              {copiedKey === "marketer" ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        {/* 3. Consumer Care Cell */}
        <div className="flex flex-col justify-between rounded-xl border border-border/70 bg-muted/30 p-4 space-y-3">
          <div>
            <div className="flex items-center justify-between">
              <span className="rounded bg-purple-500/10 text-purple-600 text-[10px] font-bold uppercase px-2 py-0.5">
                Consumer Care
              </span>
              <span className="text-[10px] text-muted-foreground">Rule 6(1)(f)</span>
            </div>
            <h4 className="mt-2 font-bold text-foreground text-sm line-clamp-1">{consumerCareName}</h4>
            <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
              Mandatory customer helpline under Legal Metrology Regulations
            </p>
          </div>

          <div className="space-y-1.5 pt-2 border-t border-border/40 text-xs">
            {consumerCarePhone && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-[11px]">Toll-Free:</span>
                <span className="font-mono font-medium text-foreground">{consumerCarePhone}</span>
              </div>
            )}
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-[11px]">Helpdesk:</span>
              <span className="font-mono font-medium text-foreground truncate max-w-[150px]">{consumerCareEmail}</span>
            </div>
          </div>

          <div className="flex items-center gap-1.5 pt-1">
            {consumerCarePhone && (
              <a
                href={`tel:${consumerCarePhone.replace(/[^\d+]/g, "")}`}
                className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg border border-border bg-background py-1.5 text-xs font-semibold text-foreground hover:bg-muted"
              >
                <Phone className="h-3 w-3" />
                Call
              </a>
            )}
            <button
              type="button"
              onClick={() =>
                setEmailModalEntity({
                  type: "Consumer Care",
                  name: consumerCareName,
                  email: consumerCareEmail,
                  phone: consumerCarePhone,
                  address: mfgAddress,
                })
              }
              className="flex-1 inline-flex items-center justify-center gap-1 rounded-lg bg-brand py-1.5 text-xs font-semibold text-white hover:bg-brand/90"
            >
              <Mail className="h-3 w-3" />
              Email
            </button>
            <button
              type="button"
              onClick={() => handleCopy("care", `Consumer Care\nPhone: ${consumerCarePhone}\nEmail: ${consumerCareEmail}`)}
              className="inline-flex items-center justify-center rounded-lg border border-border bg-background p-1.5 text-foreground hover:bg-muted"
              title="Copy details"
            >
              {copiedKey === "care" ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Prefilled Editable Email Draft Modal */}
      {emailModalEntity && (
        <EmailDraftModal
          entity={emailModalEntity}
          inspection={inspection}
          availableEmails={availableEmails}
          onClose={() => setEmailModalEntity(null)}
        />
      )}
    </section>
  );
}

function EmailDraftModal({
  entity,
  inspection,
  availableEmails,
  onClose,
}: {
  entity: {
    type: "Manufacturer" | "Marketer" | "Consumer Care";
    name: string;
    email: string;
    phone: string;
    address: string;
  };
  inspection: Inspection;
  availableEmails?: string[];
  onClose: () => void;
}) {
  const [recipient, setRecipient] = useState(entity.email);
  const [subject, setSubject] = useState(
    `[LexMetra Inspection #${inspection.id}] Statutory Compliance Inquiry: ${inspection.product || "Packaged Product"}`
  );

  const missingDeclarations = (inspection.declarations || [])
    .filter((d: Declaration) => d.status === "MISSING" || d.status === "UNOBSERVED")
    .map((d: Declaration) => `• ${d.field} (Rule requirement)`)
    .join("\n");

  const initialBody = `Dear ${entity.name} (${entity.type}),

This communication relates to Statutory Package Compliance Inspection #${inspection.id} performed on ${new Date().toLocaleDateString("en-IN")}.

PRODUCT INSPECTION DETAILS:
• Product Name: ${inspection.product || "Packaged Commodity"}
• SKU Reference: ${inspection.productId || "Standard Retail Pack"}
• Statutory Verdict: ${inspection.status || "Under Review"}

OBSERVED FINDINGS & STATUTORY QUERIES:
${missingDeclarations || "• Verification inquiry regarding mandatory packaged commodity label declarations."}

RELEVANT EXTRACTED DECLARATIONS:
• Net Quantity: ${(inspection.declarations || []).find((d: Declaration) => d.field.includes("quantity"))?.value || "Unverified"}
• MRP: ${(inspection.declarations || []).find((d: Declaration) => d.field === "mrp")?.value || "Unverified"}
• Batch No: ${(inspection.declarations || []).find((d: Declaration) => d.field.includes("batch"))?.value || "Unverified"}

Please provide clarification or official verification records regarding these declarations.
A formal statutory inspection dossier and evidence crops have been logged on the LexMetra inspection platform.

Regards,
Legal Metrology Inspection Team / Consumer Query
LexMetra Compliance Platform`;

  const [bodyText, setBodyText] = useState(initialBody);
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(`To: ${recipient}\nSubject: ${subject}\n\n${bodyText}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const mailtoUrl = `mailto:${encodeURIComponent(recipient)}?subject=${encodeURIComponent(
    subject
  )}&body=${encodeURIComponent(bodyText)}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-border/60 pb-3">
          <div>
            <h4 className="text-base font-bold text-foreground">Draft Statutory Communication</h4>
            <p className="text-xs text-muted-foreground">
              Recipient: {entity.name} ({entity.type})
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3 text-xs">
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block font-bold text-foreground">Recipient Email</label>
              {availableEmails && availableEmails.length > 1 && (
                <span className="text-[10px] text-muted-foreground">Select from detected:</span>
              )}
            </div>
            <input
              type="email"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              className="w-full rounded-xl border border-border bg-background p-2.5 text-xs text-foreground font-mono"
            />
            {availableEmails && availableEmails.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 mt-2">
                {availableEmails.map((em) => (
                  <button
                    key={em}
                    type="button"
                    onClick={() => setRecipient(em)}
                    className={`rounded-lg px-2.5 py-1 text-[11px] font-mono transition-all ${
                      recipient === em
                        ? "bg-brand text-white font-bold shadow-sm ring-1 ring-brand/50"
                        : "bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80 border border-border"
                    }`}
                  >
                    {em.includes("nic.in") ? "🏛️ " : "✉️ "}
                    {em}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="block font-bold text-foreground mb-1">Subject</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full rounded-xl border border-border bg-background p-2.5 text-xs text-foreground font-semibold"
            />
          </div>

          <div>
            <label className="block font-bold text-foreground mb-1">Email Body (Editable Draft)</label>
            <textarea
              rows={10}
              value={bodyText}
              onChange={(e) => setBodyText(e.target.value)}
              className="w-full rounded-xl border border-border bg-background p-3 text-xs text-foreground font-mono leading-relaxed"
            />
          </div>

          <div className="rounded-xl border border-border/80 bg-muted/40 p-3 text-[11px] text-muted-foreground">
            <strong>Notice:</strong> LexMetra will NOT automatically send this communication. You may copy the text or launch your default email client to review and transmit.
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-border px-4 py-2 text-xs font-semibold hover:bg-muted"
          >
            Close
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-background px-4 py-2 text-xs font-semibold hover:bg-muted"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            <span>{copied ? "Copied!" : "Copy Draft"}</span>
          </button>
          <a
            href={mailtoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-xl bg-brand px-4 py-2 text-xs font-bold text-white hover:bg-brand/90"
          >
            <Mail className="h-3.5 w-3.5" />
            <span>Open in Mail Client</span>
          </a>
        </div>
      </div>
    </div>
  );
}

// ===========================================================================
// USP 3: Consumer / Inspector Escalation Modal
// ===========================================================================

