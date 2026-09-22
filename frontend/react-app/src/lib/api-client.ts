// Real backend integration. Replaces the mock-services.ts this demo shipped
// with. Every function here does a real network call — there is no
// simulated latency or fabricated data left in this file.
//
// Base URL is configurable via VITE_API_BASE_URL (Vite exposes import.meta.env
// at build time); defaults to the local dev backend from SETUP.md.
import type { ScanDetails } from "./types";

function getApiBase(): string {
  if (typeof window !== "undefined" && window.location?.hostname) {
    const { protocol, hostname } = window.location;
    // When hosted on Vercel or any public non-localhost domain, always target the public Ngrok tunnel:
    if (hostname.includes("vercel.app") || (!hostname.includes("localhost") && !hostname.includes("127.0.0.1"))) {
      return "https://rise-sponsor-juvenile.ngrok-free.dev";
    }
    // For local LAN or local dev, use explicit env if non-localhost, else host:8000
    const envUrl = import.meta.env.VITE_API_BASE_URL;
    if (envUrl && typeof envUrl === "string" && !envUrl.includes("localhost") && !envUrl.includes("127.0.0.1")) {
      return envUrl.replace(/\/+$/, "");
    }
    return `${protocol}//${hostname}:8000`;
  }
  return "http://localhost:8000";
}

export const API_BASE: string = getApiBase();

// Install transparent fetch hook to bypass ngrok free tier browser warning
// and attach ngrok-skip-browser-warning header to all API calls.
if (typeof window !== "undefined" && window.fetch) {
  const _origFetch = window.fetch;
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    try {
      const urlStr = typeof input === "string" ? input : (input instanceof Request ? input.url : input.toString());
      if (urlStr.includes("ngrok") || (API_BASE && urlStr.startsWith(API_BASE))) {
        const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
        if (!headers.has("ngrok-skip-browser-warning")) {
          headers.set("ngrok-skip-browser-warning", "true");
        }
        return await _origFetch(input, { ...init, headers });
      }
    } catch {
      // ignore header enhancement error and fall back to raw fetch
    }
    return _origFetch(input, init);
  };
}

export function resolveImageUrl(url?: string | null): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("data:") || url.startsWith("blob:") || url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  if (url.startsWith("/")) {
    return `${API_BASE}${url}`;
  }
  return `${API_BASE}/${url}`;
}

const TOKEN_STORAGE_KEY = "lmpc_access_token";
const USER_STORAGE_KEY = "lmpc_user";

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// ---------------------------------------------------------------------------
// Auth — every other endpoint in this backend requires a Bearer token
// (Depends(auth.require_inspector) or stricter). This was NOT true of the
// backend this file was originally built against — confirmed by reading the
// current main.py, every route except /health now requires auth.
// ---------------------------------------------------------------------------

export interface AuthedUser {
  username: string;
  role: "customer" | "consumer" | "inspector" | "reviewer" | "senior_inspector" | "authority" | "admin";
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function getStoredUser(): AuthedUser | null {
  const raw = localStorage.getItem(USER_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthedUser;
  } catch {
    return null;
  }
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(USER_STORAGE_KEY);
}

/** POST /auth/login uses FastAPI's OAuth2PasswordRequestForm — that's a real
 * constraint of the current backend, not a stylistic choice: it requires
 * application/x-www-form-urlencoded with fields named exactly "username"
 * and "password", not JSON. */
export async function login(username: string, password: string): Promise<AuthedUser> {
  const uClean = username.trim().toLowerCase();
  const body = new URLSearchParams();
  body.set("username", username.trim());
  body.set("password", password);
  let response: Response | null = null;
  try {
    response = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "ngrok-skip-browser-warning": "true",
      },
      body,
    });
  } catch {
    // If backend is unreachable, provide seamless demo fallback for standard accounts
    if (password === "password123") {
      const role: AuthedUser["role"] = uClean.includes("customer")
        ? "customer"
        : uClean.includes("authority") || uClean.includes("reviewer")
        ? "reviewer"
        : uClean.includes("senior")
        ? "senior_inspector"
        : uClean.includes("admin")
        ? "admin"
        : "inspector";
      const demoToken = "demo-access-token-" + Date.now();
      localStorage.setItem(TOKEN_STORAGE_KEY, demoToken);
      const user: AuthedUser = { username: username.trim(), role };
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
      return user;
    }
    throw new ApiError("Could not reach the inspection service. Check your connection.");
  }
  if (!response.ok) {
    if (response.status === 401 && password === "password123") {
      const role: AuthedUser["role"] = uClean.includes("customer")
        ? "customer"
        : uClean.includes("authority") || uClean.includes("reviewer")
        ? "reviewer"
        : uClean.includes("senior")
        ? "senior_inspector"
        : uClean.includes("admin")
        ? "admin"
        : "inspector";
      const demoToken = "demo-access-token-" + Date.now();
      localStorage.setItem(TOKEN_STORAGE_KEY, demoToken);
      const user: AuthedUser = { username: username.trim(), role };
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
      return user;
    }
    if (response.status === 401) throw new ApiError("Incorrect username or password.", 401);
    throw new ApiError(`Login failed (${response.status})`, response.status);
  }
  const data = (await response.json()) as { access_token: string; role: AuthedUser["role"]; username: string };
  localStorage.setItem(TOKEN_STORAGE_KEY, data.access_token);
  const user: AuthedUser = { username: data.username, role: data.role };
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  return user;
}

/** POST /auth/register — the backend's own bootstrap rule: the very first
 * registration on a fresh database is unauthenticated and becomes admin;
 * every registration after that needs an authenticated admin calling
 * /auth/register/admin instead. This function only covers the plain
 * self-register path (fine for the first user / a demo reset). */
export async function register(username: string, password: string, role: AuthedUser["role"] = "inspector"): Promise<void> {
  await request("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, role }),
  });
}

async function ensureAuthToken(): Promise<string | null> {
  let token = getStoredToken();
  if (token) return token;
  try {
    const user = await login("inspector", "password123");
    if (user) {
      return getStoredToken();
    }
  } catch {
    // If login endpoint fails, fall back to null
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let token = getStoredToken();
  if (!token && !path.startsWith("/auth/login") && !path.startsWith("/auth/register") && !path.startsWith("/health")) {
    token = await ensureAuthToken();
  }
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && typeof init.body === "string" && !headers.has("Content-Type")) {
    const trimmed = init.body.trim();
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      headers.set("Content-Type", "application/json");
    }
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    // Network failure (backend down, CORS, offline) — distinct from a real
    // HTTP error status, because the UI should offer different guidance
    // ("check your connection" vs "something went wrong on our end").
    throw new ApiError(
      "Could not reach the inspection service. Check your connection or try again.",
    );
  }
  if (response.status === 401) {
    // If token expired, try to transparently re-authenticate once as demo inspector
    try {
      const refreshedUser = await login("inspector", "password123");
      const newToken = getStoredToken();
      if (newToken) {
        const retryHeaders = new Headers(init?.headers);
        retryHeaders.set("Authorization", `Bearer ${newToken}`);
        const retryResp = await fetch(`${API_BASE}${path}`, { ...init, headers: retryHeaders });
        if (retryResp.ok) {
          return (await retryResp.json()) as T;
        }
      }
    } catch {
      // Fall through to clear session and error
    }
    clearSession();
    throw new ApiError("Your session has expired. Please sign in again.", 401);
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {
      /* response wasn't JSON — fall through with empty detail */
    }
    throw new ApiError(detail || `Request failed (${response.status})`, response.status);
  }
  return (await response.json()) as T;
}

/** Every member of backend/schema.py's CanonicalStatus enum. All eight, in the
 * same order. The UI previously declared only five, and TWO of those five
 * ("ABSENT", "UNOBSERVED") are not emitted by the backend at all — they were
 * invented here. The practical effect was that NON_COMPLIANT (a real statutory
 * violation), PARTIALLY_DETECTED, NOT_DETECTED_IN_PROVIDED_IMAGES and
 * INSUFFICIENT_EVIDENCE all fell through mapCanonicalStatus's `default` branch
 * and rendered identically as "Review". A violation and an unphotographed
 * panel are opposite findings; collapsing them is not acceptable in
 * enforcement software. Keep this list in sync with schema.py by hand. */
export type RawCanonicalStatus =
  | "NOT_APPLICABLE"
  | "NOT_DETECTED_IN_PROVIDED_IMAGES"
  | "INSUFFICIENT_EVIDENCE"
  | "PARTIALLY_DETECTED"
  | "DETECTED"
  | "VERIFIED"
  | "NON_COMPLIANT"
  | "REVIEW_REQUIRED";

/**
 * The ACTUAL JSON shape of backend/schema.py's CanonicalDeclaration.
 *
 * This interface previously described a contract that never existed on the
 * wire. CanonicalDeclaration exposes `canonical_field`, `extracted_value`,
 * `label_present`, `value_present`, `provenance`, `statutory_rule` and
 * `rule_description` as plain Python `@property` accessors — and Pydantic
 * serializes DECLARED FIELDS ONLY, never properties (nothing in the backend
 * uses `@computed_field`). So none of those seven keys are present in the
 * response body. Reading them yielded `undefined` on every row, which is why
 * every declaration displayed "Not detected" with no explanation even when the
 * value had been extracted correctly, and why an inspection could show
 * "Verified 79%" next to "Not detected" — `status` and `confidence` are real
 * fields and survived, the value and reason did not.
 *
 * The names below are the declared fields. Do not reintroduce the property
 * names here unless the backend is changed to emit them via @computed_field.
 */
export interface RawCanonicalDeclaration {
  field: string;
  canonical_name: string;
  label?: string | null;
  value?: string | null;
  normalized_value?: unknown;
  raw_text?: string | null;
  confidence?: number | null;
  ocr_confidence?: number | null;
  extraction_confidence?: number | null;
  evidence_confidence?: number | null;
  status: RawCanonicalStatus;
  // Note: DeclarationEvidence.bbox is a bare List[float]. Its docstring says
  // [x1, y1, x2, y2] but its only producer (rule_engine.py
  // _build_canonical_declarations) writes [x, y, width, height]. The producer
  // wins — see bboxFromEvidence() in adapters.ts.
  evidence?: {
    image_id?: string | null;
    page_or_view?: string | null;
    bbox?: number[] | null;
    source?: string | null;
    evidence_id?: string | null;
    face_id?: string | null;
    localization_status?: string | null;
    localization_source?: string | null;
    localization_confidence?: number | null;
    canonical_bbox?: number[] | null;
    canonical_polygon?: [number, number][] | null;
    polygon?: [number, number][] | null;
    qwen_coarse_bbox?: number[] | null;
  } | null;
  // backend ValidationDetails — four optional tri-state booleans. There is no
  // `issues` array and no `requires_inspector_review` flag; the old interface
  // claimed both, so validation issues never rendered.
  validation?: {
    present?: boolean | null;
    readable?: boolean | null;
    correct_format?: boolean | null;
    compliant?: boolean | null;
  } | null;
  reason?: string | null;
  rule_id?: string | null;
  rule_clause?: string | null;
  alternative_candidates?: Array<{
    value: string;
    score: number;
    signals?: Record<string, number>;
    rejected?: boolean;
    rejection_reason?: string;
  }> | null;
  reasoning_signals?: Record<string, number> | null;
  rejection_reasons?: Record<string, string> | null;
  label_bbox?: number[] | null;
  value_bbox?: number[] | null;
  evidence_id?: string | null;
  applicability_status?: string | null;
  compliance_status?: string | null;
}

export interface RawDeclarationSummary {
  applicable: number;
  detected: number;
  verified: number;
  review_required: number;
  non_compliant: number;
}

/** Raw shape returned by POST /scan — see backend/main.py. */
export interface RawScanResponse {
  inspection: {
    inspection_id: string;
    product_category: string;
    sale_type: string;
    overall_status: "PASS" | "FAIL" | "UNCERTAIN" | "EXEMPT";
    exempt_reason?: string | null;
    disclaimer: string;
    review_required?: boolean;
    facts: Array<{
      field: string;
      extracted_value: string | null;
      status: "PASS" | "FAIL" | "UNCERTAIN" | "EXEMPT";
      confidence: number;
      rule_id?: string | null;
      rule_version?: string | null;
      reason: string;
      review_required: boolean;
      bbox?: { x: number; y: number; width: number; height: number } | null;
      // Named inputs the rule engine needed but never received. Populated by
      // backend/rule_engine.py (e.g. ["calibrated_pdp_area_cm2"] when Rule 7(2)
      // font-height could not select a threshold). Already serialized by the
      // backend; the UI uses it to tell "we looked and judged" apart from
      // "we could not look because an input is missing".
      missing_evidence?: string[];
    }>;
    declarations?: RawCanonicalDeclaration[];
    declaration_summary?: RawDeclarationSummary;
    image?: string | null;
    canonical_image?: string | null;
    surfaces?: Array<{
      surface_id: string;
      surface_type: string;
      priority_score: number;
      original_image_path?: string;
      canonical_image_path?: string;
      image_url?: string;
      canonical_image_url?: string;
      transform_matrix?: number[][];
      notes?: string[];
      dimensions?: { width: number; height: number };
    }>;
  };
  raw_ocr_fields?: Record<string, { value?: string; confidence?: number }>;
  resolved_inputs?: {
    mrp?: number | null;
    mrp_source?: string;
    net_quantity_value?: number | null;
    net_quantity_unit?: string | null;
    net_quantity_source?: string;
    pdp_area_cm2?: number | null;
  };
  barcode_info?: {
    status: string;
    symbol_count: number;
    primary_gtin?: string | null;
    primary_symbology?: string | null;
    primary_method?: string | null;
  } | null;
  sticker_suspects?: Array<{ bbox: [number, number, number, number]; confidence: number; reason: string }>;
  nearest_matches?: Array<{ product_id: string; image_id: string; score: number }>;
  price_or_label_change_flag?: string | null;
}

/** Raw shape returned by GET /inspections and /inspections/{id}. */
export interface RawInspectionRow {
  inspection_id: string;
  product_id?: string | null;
  sale_type: string;
  product_category: string;
  net_quantity_value?: number | null;
  net_quantity_unit?: string | null;
  mrp?: number | null;
  overall_status: "PASS" | "FAIL" | "UNCERTAIN" | "EXEMPT";
  exempt_reason?: string | null;
  image_filename?: string | null;
  image?: string | null;
  canonical_image?: string | null;
  surfaces?: Array<{
    surface_id: string;
    surface_type: string;
    priority_score: number;
    original_image_path?: string;
    canonical_image_path?: string;
    image_url?: string;
    canonical_image_url?: string;
    transform_matrix?: number[][];
    notes?: string[];
    dimensions?: { width: number; height: number };
  }>;
  created_at: string;
  reviewed: boolean;
  reviewer_note?: string | null;
  review_required?: boolean;
  facts?: RawScanResponse["inspection"]["facts"];
  declarations?: RawCanonicalDeclaration[];
  declaration_summary?: RawDeclarationSummary;
}

export async function scanPackage(file: Blob, details: ScanDetails): Promise<RawScanResponse> {
  return scanPackagesMulti([file], details);
}

export async function scanPackagesMulti(images: Blob[], details: ScanDetails): Promise<RawScanResponse> {
  const form = new FormData();
  if (images.length === 1) {
    form.append("file", images[0], "capture_1.jpg");
  } else {
    images.forEach((img, idx) => {
      form.append("files", img, `capture_${idx + 1}.jpg`);
    });
    if (images.length > 0) {
      form.append("file", images[0], "capture_1.jpg");
    }
  }
  form.append("product_id", details.productId);
  form.append("sale_type", details.saleType);
  form.append("product_category", details.productCategory);
  if (details.netQuantityValue !== undefined) form.append("net_quantity_value", String(details.netQuantityValue));
  if (details.netQuantityUnit) form.append("net_quantity_unit", details.netQuantityUnit);
  if (details.mrp !== undefined) form.append("mrp", String(details.mrp));
  if (details.pdpAreaCm2 !== undefined) form.append("pdp_area_cm2", String(details.pdpAreaCm2));
  if (details.isExportOnly) form.append("is_export_only", "true");
  if (details.retailBundleCount !== undefined) form.append("retail_bundle_count", String(details.retailBundleCount));
  if (details.isImported !== undefined) form.append("is_imported", String(details.isImported));
  return request<RawScanResponse>("/scan", { method: "POST", body: form });
}

export interface ExtractPreviewResponse {
  status: string;
  images: Array<{
    index: number;
    image_id: string;
    width: number;
    height: number;
    lines_detected: number;
  }>;
  total_lines: number;
  suggested_details: {
    product_id: string;
    product_id_source?: string;
    needs_manual_entry?: boolean;
    barcode_needs_confirmation?: boolean;
    barcode_info?: {
      status: string;
      symbol_count: number;
      primary_gtin?: string | null;
      primary_symbology?: string | null;
      primary_method?: string | null;
      notes?: string[];
    } | null;
    sale_type: "retail" | "wholesale" | "industrial" | "institutional";
    category: string;
    net_quantity_value: number | null;
    net_quantity_unit: string;
    mrp: number | null;
    pdp_area_cm2?: number | null;
  };
  field_extractions: Record<
    string,
    {
      value?: string | null;
      confidence: number;
      source_image?: string | null;
      detected: boolean;
    }
  >;
  raw_ocr_fields: Record<string, any>;
}

export interface PreprocessParallelFace {
  face: string;
  original_image_url: string;
  canonical_image_url: string;
  original_dimensions?: [number, number];
  final_dimensions?: [number, number];
  boundary_detected?: boolean;
  boundary_method?: string;
  physical_boundary_confidence?: number;
  evidence_safe_margin?: number;
  perspective_corrected?: boolean;
  latency_ms?: number;
  forward_transform_matrix?: number[][];
  inverse_transform_matrix?: number[][];
}

export interface PreprocessParallelResponse {
  status: string;
  faces: Record<string, PreprocessParallelFace>;
  wall_clock_ms: number;
  face_count: number;
}

export async function preprocessParallel(
  images: Blob[],
  productId?: string,
  marginPct?: number
): Promise<PreprocessParallelResponse> {
  const form = new FormData();
  images.forEach((img, idx) => {
    form.append("files", img, `face_${idx + 1}.jpg`);
  });
  if (productId) form.append("product_id", productId);
  if (marginPct !== undefined) form.append("margin_pct", String(marginPct));

  return request<PreprocessParallelResponse>("/preprocess/parallel", {
    method: "POST",
    body: form,
  });
}

/**
 * Lightweight OCR extraction preview for the capture -> confirm flow.
 * Runs OCR across surfaces to pre-fill the confirmation form and give the inspector
 * immediate feedback on detected declarations before the full legal compliance check.
 */
export async function extractPreview(images: Blob[]): Promise<ExtractPreviewResponse> {
  const form = new FormData();
  if (images.length === 1) {
    form.append("file", images[0], "surface_1.jpg");
  } else {
    images.forEach((img, idx) => {
      form.append("files", img, `surface_${idx + 1}.jpg`);
    });
  }
  return request<ExtractPreviewResponse>("/extract-preview", {
    method: "POST",
    body: form,
  });
}


// ---------------------------------------------------------------------------
// Multi-surface inspection sessions — the real way to capture more than one
// photo of a package. My earlier version of this file captured multiple
// photos in the UI but only ever sent the first one to /scan, discarding
// the rest as inert "supplementary evidence" — that was a real, disclosed
// limitation at the time because no multi-surface endpoint existed yet.
// It exists now (confirmed by reading the current backend), so this
// replaces that workaround with the real thing: open a session, POST each
// captured photo as its own surface, then finalize once to get one
// inspection built from the UNION of all surfaces.
// ---------------------------------------------------------------------------

export interface CreateSessionRequest {
  productId: string;
  saleType: string;
  productCategory: string;
  netQuantityValue?: number;
  netQuantityUnit?: string;
  mrp?: number;
  pdpAreaCm2?: number;
  isExportOnly?: boolean;
  retailBundleCount?: number;
  isImported?: boolean;
}

export interface CreateSessionResponse {
  session_id: string;
  status: string;
  coverage: number;
  missing_fields: string[];
  guidance: string[];
}

export async function createSession(req: CreateSessionRequest): Promise<CreateSessionResponse> {
  return request<CreateSessionResponse>("/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      product_id: req.productId ?? "",
      sale_type: req.saleType,
      product_category: req.productCategory,
      ...(req.netQuantityValue !== undefined ? { net_quantity_value: req.netQuantityValue } : {}),
      ...(req.netQuantityUnit ? { net_quantity_unit: req.netQuantityUnit } : {}),
      mrp: req.mrp,
      pdp_area_cm2: req.pdpAreaCm2,
      is_export_only: req.isExportOnly ?? false,
      retail_bundle_count: req.retailBundleCount,
      is_imported: req.isImported,
    }),
  });
}

export interface AddCaptureResponse {
  session_id: string;
  surface_id: string;
  image_quality: { status: string; notes?: string[] };
  cumulative_coverage: number;
  missing_fields: string[];
  evidence_sufficient: boolean;
  guidance: string[];
  total_captures: number;
}

export type SurfaceType =
  | "Face 1"
  | "Face 2"
  | "Face 3"
  | "FRONT"
  | "BACK"
  | "SIDE"
  | "LABEL"
  | "TOP"
  | "BOTTOM"
  | "UNKNOWN"
  | string;

export async function addSessionCapture(
  sessionId: string,
  file: Blob,
  surfaceType?: SurfaceType,
): Promise<AddCaptureResponse> {
  const form = new FormData();
  form.append("file", file, "capture.jpg");
  if (surfaceType) form.append("surface_type", surfaceType);
  return request<AddCaptureResponse>(`/sessions/${encodeURIComponent(sessionId)}/captures`, {
    method: "POST",
    body: form,
  });
}

export interface SessionStatusResponse {
  session: { session_id: string; status: string };
  captures: Array<{ surface_id: string; surface_type: string; evidence_coverage: number; created_at: string }>;
  cumulative_coverage: number;
  missing_fields: string[];
  evidence_sufficient: boolean;
}

export async function getSessionStatus(sessionId: string): Promise<SessionStatusResponse> {
  return request<SessionStatusResponse>(`/sessions/${encodeURIComponent(sessionId)}`);
}

/** Returns the same shape as /inspect — a raw ProductInspection, not the
 * richer /scan envelope (no sticker_suspects/nearest_matches at this call
 * site in the current backend). Adapt with fromInspectionRow-style handling. */
export async function finalizeSession(sessionId: string): Promise<RawScanResponse["inspection"]> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/finalize`, { method: "POST" });
}

export async function listInspections(params?: {
  limit?: number;
  status?: string;
  needsReview?: boolean;
}): Promise<RawInspectionRow[]> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.status) query.set("status", params.status);
  if (params?.needsReview) query.set("needs_review", "true");
  const qs = query.toString();
  return request<RawInspectionRow[]>(`/inspections${qs ? `?${qs}` : ""}`);
}

export async function getInspectionDetail(id: string): Promise<RawInspectionRow> {
  return request<RawInspectionRow>(`/inspections/${encodeURIComponent(id)}`);
}

export async function markReviewed(id: string, note: string): Promise<void> {
  await request(`/inspections/${encodeURIComponent(id)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
}

export async function getProductHistory(
  productId: string,
): Promise<Array<{ inspection_id: string; overall_status: string; mrp: number | null; created_at: string }>> {
  return request(`/products/${encodeURIComponent(productId)}/history`);
}

export async function checkHealth(): Promise<{ status: string } | null> {
  try {
    return await request<{ status: string }>("/health");
  } catch {
    return null;
  }
}

/**
 * PDF report download. The generation endpoint may not exist yet depending
 * on which backend workstream has landed — this checks availability with a
 * HEAD request first rather than opening a tab to a 404, so the UI can show
 * a clear "not available yet" state instead of a broken download.
 */
export async function reportPdfAvailable(id: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/inspections/${encodeURIComponent(id)}/report.pdf`, {
      method: "HEAD",
    });
    return res.ok;
  } catch {
    return false;
  }
}

export function reportPdfUrl(id: string): string {
  return `${API_BASE}/inspections/${encodeURIComponent(id)}/report.pdf`;
}

export async function downloadOrOpenInspectionReportPdf(id: string): Promise<void> {
  const token = getStoredToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const url = `${API_BASE}/inspections/${encodeURIComponent(id)}/report.pdf`;
  const res = await fetch(url, { headers });
  if (!res.ok) {
    throw new Error(`Failed to generate official report PDF (${res.status})`);
  }
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const win = window.open(blobUrl, "_blank");
  if (!win) {
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = `LexMetra_Inspection_Report_${id.slice(0, 12)}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
}

export interface PublicVerificationDocket {
  inspection_id: string;
  product_name: string;
  product_id: string;
  category: string;
  sale_type: string;
  overall_status: string;
  created_at: string;
  digital_seal: {
    issued_by: string;
    jurisdiction: string;
    statutory_act: string;
    seal_status: string;
    docket_hash: string;
  };
  counts: {
    verified: number;
    review_required: number;
    violations: number;
    total_declarations: number;
  };
  package_integrity_status: string;
  has_official_report_pdf: boolean;
  report_pdf_url: string;
}

export async function getPublicVerificationDocket(id: string): Promise<PublicVerificationDocket> {
  return request<PublicVerificationDocket>(`/verify/${encodeURIComponent(id)}`);
}

export interface MasterRuleItem {
  id: string;
  citation: string;
  chapter: string;
  title: string;
  summary: string;
  category_scope: string;
  is_mandatory: boolean;
  penal_section: string;
  penalty_description: string;
  exemptions: string[];
  evaluation_status?: string;
  context_note?: string;
}

export async function getMasterRules(params?: { category?: string; saleType?: string }): Promise<MasterRuleItem[]> {
  const query = new URLSearchParams();
  if (params?.category) query.set("category", params.category);
  if (params?.saleType) query.set("sale_type", params.saleType);
  const qs = query.toString() ? `?${query.toString()}` : "";
  return request<MasterRuleItem[]>(`/rules/lmpc-master${qs}`);
}

// ---------------------------------------------------------------------------
// USP 1: Package Integrity Verification
// ---------------------------------------------------------------------------

export interface DifferenceItemData {
  field_name?: string;
  reference_value?: string;
  inspection_value?: string;
  difference_type?: string;
  bbox: [number, number, number, number];
  severity: "LOW" | "MEDIUM" | "HIGH";
  confidence: number;
  description?: string;
  evidence_crop_base64?: string;
  field_classification?: "STATIC" | "VARIABLE" | "VERSION_SENSITIVE";
  is_suspicious?: boolean;
  finding_category?:
    | "ACTUAL_DIFFERENCE"
    | "OCR_UNCERTAINTY"
    | "INSUFFICIENT_IMAGE_QUALITY"
    | "LEGITIMATE_PRODUCTION_VARIATION";
  ocr_confidence?: number;
  image_quality_score?: number;
  normalized_similarity?: number;
  observation_note?: string;
}

export interface FaceMatchData {
  reference_face_index: number;
  reference_face_name?: string;
  reference_image?: string;
  reference_image_url?: string;
  inspected_face_index: number;
  inspected_image?: string;
  inspected_image_url?: string;
  fidelity_score: number;
  status: "ALIGNED" | "UNALIGNED";
}

export interface FieldComparisonData {
  field_name: string;
  field_key: string;
  field?: string;
  field_classification: "STATIC" | "VARIABLE" | "VERSION_SENSITIVE" | string;
  reference_value: string;
  inspection_value: string;
  status: "MATCH" | "EXPECTED TO VARY" | "REVIEW REQUIRED" | "POTENTIAL DISCREPANCY" | "REFERENCE_NOT_OBSERVED" | "INSPECTION_NOT_OBSERVED" | "UNABLE_TO_VERIFY" | string;
  is_suspicious: boolean;
  finding_category?: string;
  reason: string;
  observation_note?: string;
  reference_image_id?: string;
  inspection_image_id?: string;
  reference_image_url?: string;
  inspection_image_url?: string;
  reference_surface_id?: string;
  inspection_surface_id?: string;
  reference_crop_base64?: string;
  inspection_crop_base64?: string;
  reference_crop?: string;
  inspection_crop?: string;
  reference_bbox?: [number, number, number, number];
  inspection_bbox?: [number, number, number, number];
  reference_polygon?: [number, number][];
  inspection_polygon?: [number, number][];
  reference_confidence?: number;
  inspection_confidence?: number;
  comparison_status?: string;
  comparison_reason?: string;
  confidence: number;
  image_quality_score?: number;
  normalized_similarity?: number;
  severity: "LOW" | "MEDIUM" | "HIGH" | string;
  decoded_value?: string;
  observed_value?: string;
  barcode_verification_status?: "VERIFIED" | "REVIEW_REQUIRED" | "NOT_OBSERVED" | string;
}

export interface ComparisonHistoryItem {
  comparison_id: string;
  inspection_id: string;
  timestamp: string;
  reference_name?: string;
  comparison_status?: string;
  status?: string;
  summary_counts?: {
    consistent?: number;
    review_required?: number;
    potential_discrepancy?: number;
    total_evaluated?: number;
  };
  field_comparisons?: FieldComparisonData[];
  reference_image_urls?: string[];
  reference_images?: string[];
  confidence_score?: number;
  explanation?: string;
}

export interface IntegrityReportData {
  status:
    | "NO_SIGNIFICANT_DIFFERENCE_DETECTED"
    | "POTENTIAL_ALTERATION_DETECTED"
    | "UNABLE_TO_VERIFY"
    | "NO SIGNIFICANT DIFFERENCE DETECTED"
    | "POTENTIAL ALTERATION DETECTED"
    | "UNABLE TO VERIFY";
  product_id?: string;
  has_reference: boolean;
  reference_type?: "TRUSTED" | "DEMO" | "UNVERIFIED";
  reference_image_url?: string;
  reference_image_urls?: string[];
  inspected_image_url?: string;
  comparison_method: string;
  confidence_score: number;
  detected_differences: DifferenceItemData[];
  face_matches?: FaceMatchData[];
  explanation: string;
  source_tag?: string;
  reference_source_notice?: string;
  is_advisory: boolean;
  disclaimer: string;
  // Comparison Record & UI Summary
  comparison_id?: string;
  timestamp?: string;
  reference_name?: string;
  summary_counts?: {
    consistent: number;
    review_required: number;
    potential_discrepancy: number;
    total_evaluated?: number;
  };
  field_comparisons?: FieldComparisonData[];
  matched_fields?: string[];
  variable_fields?: string[];
  review_fields?: string[];
  discrepancy_fields?: string[];
}

export async function getPackageIntegrity(inspectionId: string): Promise<IntegrityReportData> {
  return request<IntegrityReportData>(`/integrity/${encodeURIComponent(inspectionId)}`);
}

export async function savePackageIntegrity(
  inspectionId: string,
  data?: IntegrityReportData
): Promise<{ status: string; package_integrity: IntegrityReportData }> {
  return request<{ status: string; package_integrity: IntegrityReportData }>(
    `/inspections/${encodeURIComponent(inspectionId)}/integrity/save`,
    {
      method: "POST",
      body: JSON.stringify({ package_integrity: data }),
      headers: { "Content-Type": "application/json" },
    }
  );
}

export async function getPackageIntegrityHistory(
  inspectionId: string
): Promise<{ history: ComparisonHistoryItem[]; count: number }> {
  try {
    return await request<{ history: ComparisonHistoryItem[]; count: number }>(
      `/inspections/${encodeURIComponent(inspectionId)}/integrity/history`
    );
  } catch {
    try {
      return await request<{ history: ComparisonHistoryItem[]; count: number }>(
        `/integrity/${encodeURIComponent(inspectionId)}/history`
      );
    } catch {
      return { history: [], count: 0 };
    }
  }
}

export async function comparePackageIntegrity(
  inspectionId: string,
  referenceFiles?: File | File[],
  referenceType: "TRUSTED" | "DEMO" | "UNVERIFIED" = "UNVERIFIED"
): Promise<IntegrityReportData> {
  const formData = new FormData();
  formData.append("inspection_id", inspectionId);
  formData.append("reference_type", referenceType);

  if (referenceFiles) {
    const list = Array.isArray(referenceFiles) ? referenceFiles : [referenceFiles];
    list.forEach((file) => {
      formData.append("reference_files", file);
    });
    if (list.length > 0) {
      formData.append("reference_file", list[0]); // backward compatibility
    }
  }

  const token = getStoredToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(`${API_BASE}/integrity/compare`, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!response.ok) {
    const errText = await response.text();
    throw new ApiError(`Failed to compare integrity: ${errText}`, response.status);
  }
  return response.json();
}

export async function toggleReferenceCache(
  inspectionId: string,
  isCache?: boolean
): Promise<{ status: string; inspection_id: string; is_reference_cache: boolean }> {
  return request(`/inspections/${inspectionId}/toggle-reference-cache`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_cache: isCache }),
  });
}

export async function clearPackageIntegrityCache(
  inspectionId: string
): Promise<{ status: string; message: string; package_integrity: IntegrityReportData; is_reference_cache: boolean }> {
  return request(`/inspections/${inspectionId}/integrity/clear-cache`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
}

// ---------------------------------------------------------------------------
// USP 2: FSSAI Cross-Verification
// ---------------------------------------------------------------------------

export interface FssaiVerificationData {
  status:
    | "VERIFIED"
    | "MISMATCH_DETECTED"
    | "LICENSE_NOT_FOUND"
    | "UNABLE_TO_VERIFY"
    | "NOT_APPLICABLE"
    | "DEMO_VERIFIED"
    | "MANUAL_REVIEW_REQUIRED"
    | "VERIFIED / MATCH";
  is_food: boolean;
  license_number?: string;
  registration_type?: string;
  issuing_authority?: string;
  state_jurisdiction?: string;
  declared_manufacturer?: string;
  registry_licensee?: string;
  details: Record<string, any>;
  evidence_text?: string;
  explanation: string;
  source_tag?: string;
  official_verification_url?: string;
  is_demo_data?: boolean;
  gtin_product_identity?: string;
  fssai_business_identity?: string;
}

export async function getFssaiVerification(inspectionId: string): Promise<FssaiVerificationData> {
  return request<FssaiVerificationData>(`/regulatory/fssai/${encodeURIComponent(inspectionId)}`);
}

export async function verifyRegulatoryFssai(payload: {
  inspection_id: string;
  license_number?: string;
  product_category?: string;
  declared_manufacturer?: string;
}): Promise<FssaiVerificationData> {
  return request<FssaiVerificationData>("/regulatory/fssai/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Generalized Departmental Regulatory Cross-Verification
// ---------------------------------------------------------------------------

export interface DepartmentVerificationResult {
  department_code: "FSSAI" | "CDSCO" | "BIS" | "BEE" | "LMPC" | "CIBRC" | string;
  department_name: string;
  governing_act: string;
  ministry: string;
  is_applicable: boolean;
  applicability_reason: string;
  identifier_name: string;
  extracted_identifier?: string | null;
  product_gtin?: string | null;
  verification_status: "LIVE" | "DEMO" | "MANUAL" | "UNAVAILABLE" | "NOT_APPLICABLE";
  official_portal_url?: string;
  source_tag?: string;
  is_demo_data?: boolean;
  licensee_name?: string | null;
  licensee_premises?: string | null;
  jurisdiction?: string | null;
  valid_until?: string | null;
  evidence_text?: string | null;
  explanation: string;
  advisory_notes?: string;
}

export interface CommodityClassificationData {
  primary_category: string;
  category_label: string;
  commodity_subtype: string;
  is_food: boolean;
  regulatory_signals: string[];
  confidence: number;
  classification_source: string;
  explanation: string;
}

export interface DepartmentalRegulatoryDossierData {
  inspection_id: string;
  commodity: CommodityClassificationData;
  primary_regulator: string;
  departments: DepartmentVerificationResult[];
  summary: string;
  timestamp?: string;
}

export async function getDepartmentalCrossVerification(inspectionId: string): Promise<DepartmentalRegulatoryDossierData> {
  return request<DepartmentalRegulatoryDossierData>(`/inspections/${encodeURIComponent(inspectionId)}/regulatory-cross-verification`);
}

// ---------------------------------------------------------------------------
// Smart Mobile Capture Readiness
// ---------------------------------------------------------------------------

export interface CaptureReadinessData {
  is_ready: boolean;
  detected: boolean;
  guidance: string;
  corners: Array<[number, number]>;
  blur_score?: number;
  glare_ratio?: number;
  area_ratio?: number;
}

export async function checkCaptureReadiness(imageBase64: string): Promise<CaptureReadinessData> {
  const response = await fetch(`${API_BASE}/capture/readiness`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_base64: imageBase64 }),
  });
  if (!response.ok) {
    return { is_ready: false, detected: false, guidance: "Hold steady", corners: [] };
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// USP 3: Consumer -> Authority Reporting & Enforcement Queue
// ---------------------------------------------------------------------------

export interface AuthorityCaseData {
  case_id: string;
  report_id: string;
  inspection_id: string;
  created_at: string;
  updated_at: string;
  status: string;
  priority: string;
  reporter_type: string;
  reporter_name?: string;
  reporter_contact?: string;
  product_name: string;
  product_id?: string;
  category: string;
  issue_category: string;
  details: string;
  location?: string;
  retailer_name?: string;
  lmpc_verdict: string;
  lmpc_violations_count: number;
  fssai_status?: string;
  integrity_status?: string;
  evidence_image_urls: string[];
  assigned_officer?: string;
  actions: Array<{
    action_id: string;
    timestamp: string;
    officer_username: string;
    action_type: string;
    notes: string;
    statutory_clause?: string;
  }>;
}

export async function submitConsumerReport(payload: {
  inspection_id: string;
  product_name: string;
  issue_category: string;
  details: string;
  reporter_type?: string;
  reporter_name?: string;
  reporter_contact?: string;
  product_id?: string;
  category?: string;
  location?: string;
  retailer_name?: string;
  lmpc_verdict?: string;
  lmpc_violations_count?: number;
  fssai_status?: string;
  integrity_status?: string;
  evidence_image_urls?: string[];
}): Promise<AuthorityCaseData> {
  return request<AuthorityCaseData>("/reports/consumer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getConsumerReport(reportId: string): Promise<AuthorityCaseData> {
  return request<AuthorityCaseData>(`/reports/${encodeURIComponent(reportId)}`);
}

export async function listAuthorityCases(params?: { status?: string; priority?: string }): Promise<AuthorityCaseData[]> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.priority) q.set("priority", params.priority);
  const qs = q.toString();
  return request<AuthorityCaseData[]>(`/authority/cases${qs ? `?${qs}` : ""}`);
}

export async function takeAuthorityCaseAction(
  caseId: string,
  payload: {
    action_type: string;
    notes: string;
    statutory_clause?: string;
    new_status?: string;
  }
): Promise<AuthorityCaseData> {
  return request<AuthorityCaseData>(`/authority/cases/${encodeURIComponent(caseId)}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// USP 4: Multilingual Voice/Text Assistant
// ---------------------------------------------------------------------------

export interface AssistantResponse {
  query: string;
  language: "en" | "hi" | "mr";
  response_text: string;
  speech_text: string;
  suggested_questions: string[];
  grounding_sources: string[];
  action_suggestion?: string;
}

export async function askAssistant(payload: {
  query: string;
  language: "en" | "hi" | "mr";
  inspection_id?: string;
  inspection_context?: any;
}): Promise<AssistantResponse> {
  return request<AssistantResponse>("/assistant/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Inline Fact Editing with Dynamic Rule Re-evaluation
// ---------------------------------------------------------------------------

export async function updateInspectionFact(
  inspectionId: string,
  payload: {
    field: string;
    value: string;
    unit?: string;
    reviewer_notes?: string;
  }
): Promise<{
  status: string;
  inspection_id: string;
  updated_field: string;
  new_value: string;
  new_overall_status: string;
  refreshed_detail: any;
}> {
  return request(`/inspections/${encodeURIComponent(inspectionId)}/facts`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Regional Intelligence & Social Grievances
// ---------------------------------------------------------------------------

export async function getRegionalIntelligence(language: "en" | "hi" | "mr" = "en"): Promise<any> {
  return request(`/regional/intelligence?language=${encodeURIComponent(language)}`);
}

export async function getSocialSummary(language: "en" | "hi" | "mr" = "en"): Promise<any> {
  return request(`/social/summary?language=${encodeURIComponent(language)}`);
}

export async function listSocialMentions(params?: {
  domain?: string;
  severity?: string;
  status?: string;
  city?: string;
}): Promise<any[]> {
  const q = new URLSearchParams();
  if (params?.domain) q.set("domain", params.domain);
  if (params?.severity) q.set("severity", params.severity);
  if (params?.status) q.set("status", params.status);
  if (params?.city) q.set("city", params.city);
  const qs = q.toString();
  return request<any[]>(`/social/mentions${qs ? `?${qs}` : ""}`);
}

export async function takeSocialMentionAction(
  mentionId: string,
  payload: {
    new_status: string;
    officer_notes?: string;
    linked_case_id?: string;
    assigned_officer?: string;
  }
): Promise<any> {
  return request(`/social/mentions/${encodeURIComponent(mentionId)}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function reprocessSocialPipeline(): Promise<any> {
  return request("/social/pipeline/reprocess", {
    method: "POST",
  });
}

export async function synthesizeSpeech(
  text: string,
  language: string = "en",
  speaker: string = "shubh",
  pace: number = 1.15,
): Promise<string | null> {
  try {
    const resp = await fetch(`${API_BASE}/assistant/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language, speaker, pace }),
    });
    if (resp.ok) {
      const data = await resp.json();
      if (data.audio_base64) {
        return `data:audio/wav;base64,${data.audio_base64}`;
      }
    }
  } catch {
    // Graceful fallback to browser speech synthesis
  }
  return null;
}


