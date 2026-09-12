// Real backend integration. Replaces the mock-services.ts this demo shipped
// with. Every function here does a real network call — there is no
// simulated latency or fabricated data left in this file.
//
// Base URL is configurable via VITE_API_BASE_URL (Vite exposes import.meta.env
// at build time); defaults to the local dev backend from SETUP.md.
import type { ScanDetails } from "./types";

const API_BASE: string =
  (typeof import.meta !== "undefined" &&
    (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE_URL) ||
  "http://localhost:8000";

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
  role: "inspector" | "reviewer" | "admin";
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
  const body = new URLSearchParams();
  body.set("username", username);
  body.set("password", password);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch {
    throw new ApiError("Could not reach the inspection service. Check your connection.");
  }
  if (!response.ok) {
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

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

export interface RawCanonicalDeclaration {
  canonical_field: string;
  canonical_name: string;
  label_present: boolean;
  value_present: boolean;
  extracted_value?: string | null;
  normalized_value?: string | null;
  status: "VERIFIED" | "ABSENT" | "REVIEW_REQUIRED" | "NOT_APPLICABLE" | "UNOBSERVED";
  confidence?: number | null;
  ocr_confidence?: number | null;
  statutory_rule?: string | null;
  rule_description?: string | null;
  provenance?: {
    image_id?: string | null;
    surface_id?: string | null;
    surface_type?: string | null;
    bbox?: { x: number; y: number; width: number; height: number } | null;
    raw_text?: string | null;
    ocr_confidence?: number | null;
  } | null;
  validation?: {
    is_valid: boolean;
    issues: string[];
    normalized_form?: string | null;
    requires_inspector_review: boolean;
  } | null;
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
    }>;
    declarations?: RawCanonicalDeclaration[];
    declaration_summary?: RawDeclarationSummary;
  };
  raw_ocr_fields?: Record<string, { value?: string; confidence?: number }>;
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
  created_at: string;
  reviewed: boolean;
  reviewer_note?: string | null;
  review_required?: boolean;
  facts?: RawScanResponse["inspection"]["facts"];
  declarations?: RawCanonicalDeclaration[];
  declaration_summary?: RawDeclarationSummary;
}

export async function scanPackage(file: Blob, details: ScanDetails): Promise<RawScanResponse> {
  const form = new FormData();
  form.append("file", file, "capture.jpg");
  form.append("product_id", details.productId);
  form.append("sale_type", details.saleType);
  form.append("product_category", details.productCategory);
  form.append("net_quantity_value", String(details.netQuantityValue));
  form.append("net_quantity_unit", details.netQuantityUnit);
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
    // "barcode_scan" (decoded bars) | "barcode_ocr_checked" (HRI digits,
    // GTIN check-digit validated) | "common_name" | "manufacturer_name" |
    // "unidentified_placeholder" (no reliable identity found -- this is a
    // generated placeholder, not a read value; show it as such).
    product_id_source: string;
    product_id_needs_confirmation: boolean;
    sale_type: "retail" | "wholesale" | "industrial" | "institutional";
    category: string;
    net_quantity_value: number | null;
    net_quantity_unit: string;
    mrp: number | null;
  };
  barcode?: {
    status: string;
    symbols: Array<Record<string, unknown>>;
    localised_not_decoded: number[][];
    notes: string[];
    coverage_note: string;
  };
  geometry?: {
    package: Record<string, unknown> | null;
    pdp: Record<string, unknown> | null;
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
  netQuantityValue: number;
  netQuantityUnit: string;
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
      product_id: req.productId,
      sale_type: req.saleType,
      product_category: req.productCategory,
      net_quantity_value: req.netQuantityValue,
      net_quantity_unit: req.netQuantityUnit,
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

export type SurfaceType = "FRONT" | "BACK" | "SIDE" | "LABEL" | "TOP" | "BOTTOM" | "UNKNOWN";

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
