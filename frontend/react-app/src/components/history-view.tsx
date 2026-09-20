import { Header as AppHeader } from "./app-header";
import { EmptyState, ErrorBanner } from "./app-navigation";
import { type AuthedUser } from "@/lib/api-client";
import React, { useState, useMemo } from "react";
import {
  AlertTriangle,
  Camera,
  Check,
  ChevronDown,
  Filter,
  PackageCheck,
  Search,
  SlidersHorizontal,
  XCircle,
} from "lucide-react";
import { type Inspection, type InspectionStatus } from "@/lib/types";
import { type Language, getTranslation } from "@/lib/i18n";
import { type View, Button, InspectionRow, statusLabel } from "./ui-primitives";

export function FilterBar({
  search,
  setSearch,
  filter,
  setFilter,
  lang = "en",
}: {
  search: string;
  setSearch: (value: string) => void;
  filter: "ALL" | InspectionStatus;
  setFilter: (value: "ALL" | InspectionStatus) => void;
  lang?: Language;
}) {
  const allLabel = lang === "hi" ? "सभी" : lang === "mr" ? "सर्व" : "All";
  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={
            lang === "hi"
              ? "उत्पाद या निरीक्षण आईडी खोजें..."
              : lang === "mr"
              ? "उत्पादन किंवा तपासणी आयडी शोधा..."
              : "Search products or inspection IDs"
          }
          className="h-11 w-full rounded-xl border border-border bg-card pl-10 pr-4 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/15"
        />
      </div>
      <div className="flex items-center gap-2 overflow-x-auto pb-1 hide-scrollbar">
        <Filter className="h-4 w-4 shrink-0 text-muted-foreground" />
        {(["ALL", "COMPLIANT", "VIOLATION", "UNCERTAIN", "EXEMPT"] as const).map((item) => (
          <button
            type="button"
            key={item}
            onClick={() => setFilter(item)}
            className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-bold transition-colors shadow-xs ${
              filter === item
                ? "bg-purple-700 text-white shadow-xs"
                : "bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 hover:text-black"
            }`}
          >
            {item === "ALL" ? allLabel : statusLabel(item, lang)}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ListView({
  kind,
  inspections,
  loading,
  error,
  onRetry,
  onOpen,
  onNavigate,
  lang = "en",
  onLanguageChange,
  user,
  onLogout,
}: {
  kind: "history" | "register";
  inspections: Inspection[];
  loading: boolean;
  error?: string;
  onRetry: () => void;
  onOpen: (inspection: Inspection) => void;
  onNavigate: (view: View) => void;
  lang?: Language;
  onLanguageChange?: (l: Language) => void;
  user?: AuthedUser | null;
  onLogout?: () => void;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"ALL" | InspectionStatus>("ALL");
  const filtered = useMemo(
    () =>
      inspections.filter(
        (item) =>
          (kind === "history" || item.saved) &&
          (filter === "ALL" || item.status === filter) &&
          `${item.product} ${item.id} ${item.manufacturer}`.toLowerCase().includes(search.toLowerCase()),
      ),
    [filter, inspections, kind, search],
  );

  const title =
    kind === "history"
      ? lang === "hi"
        ? "निरीक्षण इतिहास"
        : lang === "mr"
        ? "तपासणी इतिहास"
        : "Inspection history"
      : lang === "hi"
      ? "वैधानिक रजिस्टर"
      : lang === "mr"
      ? "वैधानिक नोंदवही"
      : "Compliance register";

  const subtitle =
    kind === "history"
      ? lang === "hi"
        ? "प्रत्येक पॅकेज निरीक्षण एकाच ठिकाणी."
        : lang === "mr"
        ? "प्रत्येक पॅकेज तपासणी एकाच ठिकाणी."
        : "Every package inspection, in one place."
      : lang === "hi"
      ? "आपके द्वारा सत्यापित या समीक्षा किए गए उत्पाद।"
      : lang === "mr"
      ? "आपण तपासलेली व जतन केलेली उत्पादने."
      : "Products you have explicitly verified or reviewed.";

  const eyebrowText =
    kind === "history"
      ? lang === "hi"
        ? "ऑडिट ट्रेल"
        : lang === "mr"
        ? "तपासणी नोंदी"
        : "Audit trail"
      : lang === "hi"
      ? "वैधानिक अभिलेख"
      : lang === "mr"
      ? "कायदेशीर दस्तऐवज"
      : "Statutory records";

  return (
    <>
      <AppHeader
        title={title}
        online={!error}
        lang={lang}
        onLanguageChange={onLanguageChange}
        user={user}
        onLogout={onLogout}
        onNavigate={onNavigate}
      />
      <main className="mx-auto max-w-6xl space-y-6 px-4 pb-28 pt-6 sm:px-6 md:pb-10 lg:px-8 lg:pt-10">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="text-sm font-semibold text-brand">{eyebrowText}</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-[-.05em]">{title}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>
          </div>
          <div className="rounded-xl bg-muted px-4 py-3 text-sm">
            <span className="text-muted-foreground">
              {lang === "hi" ? "दिखाए जा रहे " : lang === "mr" ? "दाखवत आहे " : "Showing "}
            </span>
            <strong>{filtered.length}</strong>
            <span className="text-muted-foreground">
              {lang === "hi" ? " रिकॉर्ड" : lang === "mr" ? " नोंदी" : " records"}
            </span>
          </div>
        </div>
        {error && <ErrorBanner message={error} onRetry={onRetry} />}
        <FilterBar search={search} setSearch={setSearch} filter={filter} setFilter={setFilter} lang={lang} />
        {loading ? (
          <div className="space-y-3 rounded-2xl border border-border/70 bg-card p-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded-xl bg-muted" />
            ))}
          </div>
        ) : filtered.length ? (
          <div className="rounded-2xl border border-border/70 bg-card px-4">
            {filtered.map((inspection: Inspection) => (
              <InspectionRow key={inspection.id} inspection={inspection} onOpen={onOpen} />
            ))}
          </div>
        ) : (
          <EmptyState
            title={
              search || filter !== "ALL"
                ? lang === "hi"
                  ? "कोई मेल खाता रिकॉर्ड नहीं"
                  : lang === "mr"
                  ? "कोणतीही जुळणारी नोंद नाही"
                  : "No matching records"
                : kind === "history"
                ? lang === "hi"
                  ? "अभी तक कोई निरीक्षण नहीं"
                  : lang === "mr"
                  ? "अद्याप कोणतीही तपासणी नाही"
                  : "No inspections yet"
                : lang === "hi"
                ? "आपका रजिस्टर खाली है"
                : lang === "mr"
                ? "आपली नोंदवही रिकामी आहे"
                : "Your register is empty"
            }
            description={
              search || filter !== "ALL"
                ? lang === "hi"
                  ? "कृपया भिन्न खोज या फ़िल्टर आज़माएं।"
                  : lang === "mr"
                  ? "कृपया वेगळा शोध किंवा फिल्टर वापरून पहा."
                  : "Try a different search or filter."
                : kind === "history"
                ? lang === "hi"
                  ? "पहला उत्पाद स्कैन करें और निरीक्षण इतिहास बनाना शुरू करें।"
                  : lang === "mr"
                  ? "आपली तपासणी नोंद सुरू करण्यासाठी पहिले उत्पादन स्कॅन करा."
                  : "Scan your first product to start building your inspection history."
                : lang === "hi"
                ? "आपके द्वारा सत्यापित और सहेजे गए उत्पाद यहाँ दिखाई देंगे।"
                : lang === "mr"
                ? "आपण सत्यापित आणि जतन केलेली उत्पादने येथे दिसतील."
                : "Products you verify and save will appear here."
            }
            onAction={() => onNavigate("scan")}
          />
        )}
      </main>
    </>
  );
}


