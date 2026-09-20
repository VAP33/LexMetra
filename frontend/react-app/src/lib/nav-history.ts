// ---------------------------------------------------------------------------
// LexMetra - Platform Navigation & Browser History Sync
// Ensures native Back/Forward browser buttons work seamlessly across all views
// ---------------------------------------------------------------------------

export type AppView =
  | "landing"
  | "login"
  | "home"
  | "history"
  | "register"
  | "reviewQueue"
  | "profile"
  | "scan"
  | "preprocessing"
  | "scanDetails"
  | "processing"
  | "result"
  | "detail"
  | "evidence"
  | "report"
  | "regulatory"
  | "authority"
  | "customer"
  | "seniorRegional";

export interface NavRouteState {
  view: AppView;
  id?: string;
}

const VIEW_HASH_MAP: Record<AppView, string> = {
  landing: "landing",
  login: "login",
  home: "home",
  history: "history",
  register: "register",
  reviewQueue: "review-queue",
  profile: "profile",
  scan: "scan",
  preprocessing: "preprocessing",
  scanDetails: "scan-details",
  processing: "processing",
  result: "result",
  detail: "detail",
  evidence: "evidence",
  report: "report",
  regulatory: "regulatory",
  authority: "authority",
  customer: "customer",
  seniorRegional: "regional",
};

const HASH_VIEW_MAP: Record<string, AppView> = {
  landing: "landing",
  login: "login",
  home: "home",
  history: "history",
  register: "register",
  "review-queue": "reviewQueue",
  reviewqueue: "reviewQueue",
  profile: "profile",
  scan: "scan",
  preprocessing: "preprocessing",
  "scan-details": "scanDetails",
  scandetails: "scanDetails",
  processing: "processing",
  result: "result",
  detail: "detail",
  evidence: "evidence",
  report: "report",
  regulatory: "regulatory",
  authority: "authority",
  customer: "customer",
  regional: "seniorRegional",
  seniorregional: "seniorRegional",
};

/**
 * Format route state into a clean browser hash URL
 */
export function formatRouteHash(view: AppView, id?: string): string {
  const hashKey = VIEW_HASH_MAP[view] || view;
  return id ? `#${hashKey}/${encodeURIComponent(id)}` : `#${hashKey}`;
}

/**
 * Parse current browser URL hash into route state
 */
export function parseRouteHash(rawHash = window.location.hash): NavRouteState | null {
  if (!rawHash || rawHash === "#" || rawHash === "#/") {
    return null;
  }
  const clean = rawHash.replace(/^#\/?/, "").trim();
  if (!clean) return null;

  const parts = clean.split("/");
  const key = parts[0].toLowerCase();
  const id = parts[1] ? decodeURIComponent(parts[1]) : undefined;

  const view = HASH_VIEW_MAP[key];
  if (view) {
    return { view, id };
  }
  return null;
}

/**
 * Push new view to browser history
 */
export function pushNavRoute(view: AppView, id?: string): void {
  const hash = formatRouteHash(view, id);
  if (window.location.hash !== hash) {
    window.history.pushState({ view, id }, "", hash);
  }
}

/**
 * Replace current view in browser history (e.g. for intermediate processing screens)
 */
export function replaceNavRoute(view: AppView, id?: string): void {
  const hash = formatRouteHash(view, id);
  window.history.replaceState({ view, id }, "", hash);
}

/**
 * Attach listeners for browser Back & Forward navigation
 */
export function setupNavListener(onNavigate: (route: NavRouteState) => void): () => void {
  const handlePopState = (event: PopStateEvent) => {
    if (event.state && event.state.view) {
      onNavigate({ view: event.state.view, id: event.state.id });
      return;
    }
    const fromHash = parseRouteHash();
    if (fromHash) {
      onNavigate(fromHash);
    }
  };

  window.addEventListener("popstate", handlePopState);
  return () => {
    window.removeEventListener("popstate", handlePopState);
  };
}
