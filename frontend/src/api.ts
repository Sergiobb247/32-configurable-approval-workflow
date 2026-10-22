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

const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "flowapprove_access_token";
const REFRESH_KEY = "flowapprove_refresh_token";

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  refresh: () => localStorage.getItem(REFRESH_KEY),
  save: (access: string, refresh?: string) => {
    sessionStorage.setItem(TOKEN_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear: () => {
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = tokenStore.refresh();
  if (!refreshToken) return false;
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async response => {
        if (!response.ok) return false;
        const tokens = await response.json();
        if (!tokens.access_token) return false;
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

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "The API is unavailable. Check the backend and your network connection.");
  }

  if (response.status === 401 && retry && path !== "/auth/login" && path !== "/auth/refresh") {
    if (await refreshAccessToken()) return request<T>(path, init, false);
    tokenStore.clear();
    window.dispatchEvent(new Event("flowapprove:auth-expired"));
  }

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
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
  async login(email: string, password: string) {
    const data = await request<{ access_token: string; refresh_token: string; user: User }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false,
    );
    tokenStore.save(data.access_token, data.refresh_token);
    return data.user;
  },

  me: () => request<User>("/auth/me"),

  logout: async () => {
    try {
      await request("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: tokenStore.refresh() }),
      });
    } finally {
      tokenStore.clear();
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
