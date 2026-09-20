import { Header as AppHeader } from "./app-header";
import { EmptyState, ErrorBanner } from "./app-navigation";
import { type AuthedUser } from "@/lib/api-client";
import React from "react";
import { ShieldAlert } from "lucide-react";
import { type Inspection } from "@/lib/types";
import { type Language } from "@/lib/i18n";
import { type View, InspectionRow } from "./ui-primitives";

export function ReviewQueueView({
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
  const pending = inspections.filter((item) => item.reviewRequired && !item.reviewed);
  const title = lang === "hi" ? "समीक्षा कतार" : lang === "mr" ? "पुनरावलोकन रांग" : "Review queue";
  const subtitle =
    lang === "hi"
      ? "कम विश्वसनीयता वाले निष्कर्ष, स्टीकर/छेड़छाड़ संदेह और अन्य एआई संकेत जिन्हें अंतिम निर्णय से पहले मानवीय समीक्षा की आवश्यकता है।"
      : lang === "mr"
      ? "कमी विश्वासार्हता असलेले निष्कर्ष, लेबल फेरफार संशय आणि मानवी पडताळणी आवश्यक असलेले AI संकेत."
      : "Low-confidence extractions, sticker/alteration suspicions, and other AI signals that need a person to look before anything is finalized. Nothing here has been auto-decided.";

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
        <div>
          <p className="text-sm font-semibold text-brand">
            {lang === "hi" ? "मानव-समीक्षा नियंत्रण" : lang === "mr" ? "मानवी पडताळणी नियंत्रण" : "Human-in-the-loop"}
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-[-.05em]">{title}</h2>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">{subtitle}</p>
        </div>
        {error && <ErrorBanner message={error} onRetry={onRetry} />}
        {loading ? (
          <div className="space-y-3 rounded-2xl border border-border/70 bg-card p-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded-xl bg-muted" />
            ))}
          </div>
        ) : pending.length ? (
          <div className="rounded-2xl border border-border/70 bg-card px-4">
            {pending.map((inspection) => (
              <InspectionRow key={inspection.id} inspection={inspection} onOpen={onOpen} />
            ))}
          </div>
        ) : (
          <EmptyState
            title={lang === "hi" ? "कतार खाली है" : lang === "mr" ? "रांग पूर्णपणे रिकामी आहे" : "Queue is clear"}
            description={
              lang === "hi"
                ? "इस समय मानवीय समीक्षा के लिए कुछ भी लंबित नहीं है।"
                : lang === "mr"
                ? "सध्या मानवी पुनरावलोकनासाठी कोणतीही बाब प्रलंबित नाही."
                : "Nothing is waiting on human review right now."
            }
            onAction={() => onNavigate("scan")}
            actionLabel={lang === "hi" ? "स्कैन शुरू करें" : lang === "mr" ? "स्कॅन सुरू करा" : "Start a scan"}
          />
        )}
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// Scan flow: capture (multi-photo) -> details -> processing -> result
// ---------------------------------------------------------------------------


