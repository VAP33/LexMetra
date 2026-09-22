// ---------------------------------------------------------------------------
// LexMetra - Privacy-First Analytics & Interaction Telemetry
// Tracks route navigation, scan completions, compliance violations, and errors
// ---------------------------------------------------------------------------

export type AnalyticsEventType =
  | "page_view"
  | "scan_initiated"
  | "scan_completed"
  | "scan_error"
  | "report_downloaded"
  | "register_saved"
  | "grievance_submitted"
  | "language_changed"
  | "cookie_consent_updated";

export interface AnalyticsEvent {
  type: AnalyticsEventType;
  view?: string;
  lang?: string;
  metadata?: Record<string, unknown>;
  timestamp: string;
}

const CONSENT_KEY = "lexmetra_cookie_consent";

export function getCookieConsent(): { accepted: boolean; analytics: boolean; decided: boolean } {
  try {
    const raw = localStorage.getItem(CONSENT_KEY);
    if (!raw) return { accepted: false, analytics: false, decided: false };
    const parsed = JSON.parse(raw);
    return {
      accepted: !!parsed.accepted,
      analytics: !!parsed.analytics,
      decided: true,
    };
  } catch {
    return { accepted: false, analytics: false, decided: false };
  }
}

export function setCookieConsent(accepted: boolean, allowAnalytics = true): void {
  try {
    localStorage.setItem(
      CONSENT_KEY,
      JSON.stringify({
        accepted,
        analytics: allowAnalytics,
        timestamp: new Date().toISOString(),
      })
    );
  } catch (err) {
    console.warn("[Analytics] Could not save cookie consent:", err);
  }
}

export function trackEvent(
  type: AnalyticsEventType,
  metadata: Record<string, unknown> = {}
): void {
  const consent = getCookieConsent();
  // Essential events (like cookie choice itself) are tracked; otherwise respect consent
  if (type !== "cookie_consent_updated" && consent.decided && !consent.analytics) {
    return;
  }

  const payload: AnalyticsEvent = {
    type,
    timestamp: new Date().toISOString(),
    view: window.location.hash || "#landing",
    metadata,
  };

  // Dispatch custom browser event for integrations or monitoring tools
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("lexmetra_telemetry", { detail: payload }));

    // If Google Analytics (gtag) or Plausible is configured on the window, forward the event
    const win = window as unknown as { gtag?: (...args: unknown[]) => void; plausible?: (ev: string, opts?: unknown) => void };
    if (typeof win.gtag === "function") {
      win.gtag("event", type, metadata);
    }
    if (typeof win.plausible === "function") {
      win.plausible(type, { props: metadata });
    }
  }

  // Development debug log
  if (import.meta.env.DEV) {
    console.debug(`[LexMetra Analytics] ${type}:`, metadata);
  }
}

export function trackPageView(viewName: string, lang = "en"): void {
  trackEvent("page_view", { view: viewName, lang });
}
