export type Role = "EMPLOYEE" | "MANAGER" | "FINANCE" | "ADMIN";
export type RequestStatus = "DRAFT" | "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";

export interface User {
  id: number | string;
  email: string;
  full_name?: string;
  name?: string;
  role: Role;
  is_active?: boolean;
  created_at?: string;
}

export interface ApprovalStep {
  id?: number | string;
  order?: number;
  step_order?: number;
  role?: Role;
  required_role?: Role;
  label?: string;
  state?: "done" | "current" | "upcoming" | string;
  acted_by?: string | null;
  acted_at?: string | null;
}

export interface ApprovalRequest {
  id: number | string;
  workflow_id: number | string;
  title: string;
  description: string | null;
  amount: string | number;
  status: RequestStatus;
  current_step_index: number;
  submitted_by: User | string;
  steps: ApprovalStep[];
  can_act: boolean;
  created_at: string;
  decided_at: string | null;
  version?: number;
  workflow_name?: string;
}

export interface Workflow {
  id: number | string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_by: number;
  steps: Array<{
    id?: number | string;
    step_order: number;
    required_role: Role;
    label: string;
  }>;
}

export interface AuditEntry {
  id: number | string;
  action: string;
  actor: { id: number; full_name: string } | string;
  from_state: string | null;
  to_state: string | null;
  comment: string | null;
  created_at: string;
  request_id?: number | string | null;
  entity_type?: string;
  entity_id?: number | string;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
}

export interface HealthStatus {
  status: string;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Base URL for the FastAPI service.
 *
 * - Production / cross-origin: set `VITE_API_URL` (e.g. https://api.example.com).
 * - Default: same-origin `/api`, which the Vite dev server proxies to
 *   `http://127.0.0.1:8000` (see vite.config.ts). A same-origin proxy means the
 *   browser never needs a CORS preflight, so the app also works inside a
 *   sandboxed preview host.
 */
const API_URL = (import.meta.env.VITE_API_URL || "/api").trim().replace(/\/$/, "");

/* ------------------------------------------------------------------------- */
/* Session storage                                                          */
/* ------------------------------------------------------------------------- */

const SESSION_KEY = "flowapprove.session.v2";
// Keys used by earlier builds — read once for migration, then dropped.
const LEGACY_ACCESS_KEY = "flowapprove_access_token";
const LEGACY_REFRESH_KEY = "flowapprove_refresh_token";

interface SessionPair {
  access_token: string;
  refresh_token: string;
}

/**
 * Web Storage can throw, not just return null: Safari private mode, browsers
 * with storage disabled, and sandboxed/opaque-origin documents (an <iframe>
 * with `sandbox="allow-scripts"`) all raise SecurityError on property access.
 * A signed-in session must never hinge on that, so every read/write is guarded
 * and an in-memory copy is always kept alongside.
 */
const memory = new Map<string, string>();

function storageGet(key: string): string | null {
  try {
    const fromLocal = window.localStorage.getItem(key);
    if (fromLocal !== null) return fromLocal;
  } catch { /* storage blocked — fall through */ }
  try {
    const fromSession = window.sessionStorage.getItem(key);
    if (fromSession !== null) return fromSession;
  } catch { /* storage blocked — fall through */ }
  return memory.get(key) ?? null;
}

function storageSet(key: string, value: string): void {
  memory.set(key, value);
  try { window.localStorage.setItem(key, value); } catch { /* memory copy stands in */ }
}

function storageRemove(key: string): void {
  memory.delete(key);
  try { window.localStorage.removeItem(key); } catch { /* nothing to clean up */ }
  try { window.sessionStorage.removeItem(key); } catch { /* nothing to clean up */ }
}

/**
 * The access and refresh tokens are stored as ONE value on purpose.
 * Keeping them in separate keys let them drift apart (an access token cleared
 * with its session while a newer refresh token survived), which produced a
 * "signed in but asked to sign in again" state. One atomic pair cannot drift.
 */
export const tokenStore = {
  pair(): SessionPair | null {
    const raw = storageGet(SESSION_KEY);
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as Partial<SessionPair>;
        if (parsed?.access_token && parsed?.refresh_token) {
          return { access_token: parsed.access_token, refresh_token: parsed.refresh_token };
        }
      } catch { /* fall through to legacy migration */ }
    }
    // Migrate a session written by an older build, if one is still around.
    const legacyAccess = storageGet(LEGACY_ACCESS_KEY);
    const legacyRefresh = storageGet(LEGACY_REFRESH_KEY);
    storageRemove(LEGACY_ACCESS_KEY);
    storageRemove(LEGACY_REFRESH_KEY);
    if (legacyAccess && legacyRefresh) {
      const migrated = { access_token: legacyAccess, refresh_token: legacyRefresh };
      storageSet(SESSION_KEY, JSON.stringify(migrated));
      return migrated;
    }
    return null;
  },
  access(): string | null {
    return tokenStore.pair()?.access_token ?? null;
  },
  refresh(): string | null {
    return tokenStore.pair()?.refresh_token ?? null;
  },
  save(access: string, refresh: string): void {
    storageSet(SESSION_KEY, JSON.stringify({ access_token: access, refresh_token: refresh }));
  },
  clear(): void {
    storageRemove(SESSION_KEY);
    storageRemove(LEGACY_ACCESS_KEY);
    storageRemove(LEGACY_REFRESH_KEY);
  },
};

/** Decode a JWT payload without verifying it (the server is the authority). */
function jwtExpiry(token: string): number | null {
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    const normalised = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalised.padEnd(Math.ceil(normalised.length / 4) * 4, "=");
    const claims = JSON.parse(atob(padded)) as { exp?: number };
    return typeof claims.exp === "number" ? claims.exp * 1000 : null;
  } catch {
    return null;
  }
}

/** Treat a token as stale slightly early so a request never races its expiry. */
function isUsable(accessToken: string | null): boolean {
  if (!accessToken) return false;
  const expiresAt = jwtExpiry(accessToken);
  if (expiresAt === null) return true; // opaque token: let the server judge
  return expiresAt - Date.now() > 30_000;
}

let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = tokenStore.refresh();
  if (!refreshToken) return false;
  // One in-flight refresh shared by every caller: refresh tokens are
  // single-use, so two parallel refreshes would invalidate the session.
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async response => {
        if (!response.ok) return false;
        const tokens = (await response.json()) as Partial<SessionPair>;
        if (!tokens?.access_token || !tokens?.refresh_token) return false;
        tokenStore.save(tokens.access_token, tokens.refresh_token);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

/**
 * On a cold start there is no established session yet, so a rejected refresh
 * token must NOT be reported to the user as "your session expired" — it just
 * means the browser holds nothing valid. Only a failure while the app was
 * already signed in is worth a message.
 */
let sessionEstablished = false;

async function parseError(response: Response): Promise<ApiError> {
  let detail = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // Keep the stable fallback above for non-JSON responses.
  }
  return new ApiError(response.status, detail);
}

interface RequestOptions {
  /** Send the bearer token and react to 401 (default true). */
  auth?: boolean;
  /** Internal: a 401 has already triggered one refresh attempt. */
  retried?: boolean;
}

async function request<T>(path: string, init: RequestInit = {}, options: RequestOptions = {}): Promise<T> {
  const { auth = true, retried = false } = options;

  // Proactive refresh: avoids sending a token that is about to expire, and
  // avoids a guaranteed 401 on the first request of a restored session.
  if (auth && !isUsable(tokenStore.access()) && tokenStore.refresh()) {
    await refreshAccessToken();
  }

  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = tokenStore.access();
  if (auth && token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "The API is unavailable. Check the backend and your network connection.");
  }

  if (response.status === 401 && auth && !retried) {
    if (await refreshAccessToken()) {
      return request<T>(path, init, { auth, retried: true });
    }
    tokenStore.clear();
    if (sessionEstablished) {
      sessionEstablished = false;
      window.dispatchEvent(new Event("flowapprove:auth-expired"));
    }
  }

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/**
 * Resolve the session once at start-up.
 *
 * Returns the signed-in user, `null` when there is simply no valid session, and
 * `offline: true` when the API could not be reached at all — in which case the
 * tokens are deliberately KEPT, because a network blip is not a sign-out.
 */
export async function bootstrapSession(): Promise<{ user: User | null; offline: boolean }> {
  if (!tokenStore.access() && !tokenStore.refresh()) return { user: null, offline: false };
  try {
    const user = await request<User>("/auth/me", {}, { auth: true });
    sessionEstablished = true;
    return { user, offline: false };
  } catch (error) {
    // Only an authentication rejection ends a session. A transport failure
    // (status 0) or a gateway error from whatever proxies the API (5xx) means
    // the server is unreachable — the tokens stay, and the UI offers a retry.
    if (error instanceof ApiError && (error.status === 0 || error.status >= 500)) {
      return { user: null, offline: true };
    }
    tokenStore.clear();
    return { user: null, offline: false };
  }
}

export function markSessionEstablished(): void {
  sessionEstablished = true;
}

export function clearSession(): void {
  sessionEstablished = false;
  tokenStore.clear();
}

function list<T>(data: ListResponse<T>): ListResponse<T> {
  return { items: Array.isArray(data?.items) ? data.items : [], total: Number(data?.total || 0) };
}

const query = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  const value = search.toString();
  return value ? `?${value}` : "";
};

export const api = {
  /** GET /health — public uptime probe, used by the connection indicator. */
  health: () => request<HealthStatus>("/health"),

  /** POST /auth/register — creates an active EMPLOYEE account (201). */
  register: (payload: { full_name: string; email: string; password: string }) =>
    request<User>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),

  async login(email: string, password: string) {
    const data = await request<{ access_token: string; refresh_token: string; user: User }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      { auth: false },
    );
    if (!data?.access_token || !data?.refresh_token) {
      throw new ApiError(0, "The API did not return a session. Please try again.");
    }
    tokenStore.save(data.access_token, data.refresh_token);
    markSessionEstablished();
    return data.user;
  },

  me: () => request<User>("/auth/me"),

  logout: async () => {
    const refreshToken = tokenStore.refresh();
    const hadSession = Boolean(tokenStore.access() || refreshToken);
    try {
      // Revoke the refresh token when we have one; best effort by design.
      await request(
        "/auth/logout",
        refreshToken
          ? { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) }
          : { method: "POST" },
        { retried: true },
      );
    } catch {
      // Signing out locally must succeed even if the API is unreachable.
    } finally {
      if (hadSession) clearSession();
      else tokenStore.clear();
    }
  },

  requests: (params: { status?: RequestStatus; skip?: number; limit?: number } = {}) =>
    request<ListResponse<ApprovalRequest>>(`/requests${query(params)}`),

  getRequest: (id: string | number) => request<ApprovalRequest>(`/requests/${id}`),

  inbox: (params: { skip?: number; limit?: number } = {}) =>
    request<ListResponse<ApprovalRequest>>(`/inbox${query(params)}`),

  createRequest: (payload: { title: string; description?: string | null; amount: string; workflow_id: string | number }) =>
    request<ApprovalRequest>("/requests", { method: "POST", body: JSON.stringify(payload) }),

  submit: (id: string | number) => request<ApprovalRequest>(`/requests/${id}/submit`, { method: "POST" }),
  cancel: (id: string | number) => request<ApprovalRequest>(`/requests/${id}/cancel`, { method: "POST" }),

  approve: (id: string | number, comment = "") =>
    request<ApprovalRequest>(`/requests/${id}/approve`, { method: "POST", body: JSON.stringify({ comment }) }),

  reject: (id: string | number, comment: string) =>
    request<ApprovalRequest>(`/requests/${id}/reject`, { method: "POST", body: JSON.stringify({ comment }) }),

  workflows: (params: { skip?: number; limit?: number } = {}) =>
    request<ListResponse<Workflow>>(`/workflows${query(params)}`),

  createWorkflow: (payload: { name: string; description?: string | null; steps: Array<{ step_order: number; required_role: Role; label: string }> }) =>
    request<Workflow>("/workflows", { method: "POST", body: JSON.stringify(payload) }),

  getWorkflow: (id: string | number) => request<Workflow>(`/workflows/${id}`),

  updateWorkflow: (id: string | number, payload: { name?: string; description?: string | null; is_active?: boolean }) =>
    request<Workflow>(`/workflows/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  replaceWorkflowSteps: (id: string | number, steps: Array<{ step_order: number; required_role: Role; label: string }>) =>
    request<Workflow>(`/workflows/${id}/steps`, { method: "POST", body: JSON.stringify({ steps }) }),

  users: (params: { skip?: number; limit?: number } = {}) =>
    request<ListResponse<User>>(`/users${query(params)}`),

  updateUser: (id: string | number, payload: { role?: Role; is_active?: boolean }) =>
    request<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  audit: (params: { skip?: number; limit?: number } = {}) =>
    request<ListResponse<AuditEntry>>(`/audit${query(params)}`),

  requestAudit: (id: string | number, params: { skip?: number; limit?: number } = {}) =>
    request<ListResponse<AuditEntry>>(`/requests/${id}/audit${query(params)}`),
};
