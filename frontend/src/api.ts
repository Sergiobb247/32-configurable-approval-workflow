export type Role = "EMPLOYEE" | "MANAGER" | "FINANCE" | "ADMIN";
export type RequestStatus = "DRAFT" | "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";

export interface User {
  id: number | string;
  name?: string;
  full_name?: string;
  email: string;
  role: Role;
  is_active?: boolean;
}
export interface ApprovalRequest {
  id: number | string;
  title: string;
  description?: string;
  amount: string | number;
  currency?: string;
  status: RequestStatus;
  created_at?: string;
  submitted_at?: string;
  requester?: User | string;
  requester_name?: string;
  submitted_by?: User | string;
  workflow_name?: string;
  workflow_id?: number | string;
  current_step_index?: number;
  can_act?: boolean;
  decided_at?: string;
  steps?: Array<{ order?: number; step_order?: number; role?: Role; required_role?: Role; label?: string; state?: string; status?: string; acted_by?: string | null; acted_at?: string | null; actor_name?: string }>;
  version?: number;
}
export interface Workflow {
  id: number | string;
  name: string;
  description?: string;
  is_active?: boolean;
  active?: boolean;
  steps?: Array<{ id?: number | string; order?: number; step_order?: number; role?: Role; required_role?: Role; label?: string }>;
}
export interface AuditEntry {
  id: number | string;
  action: string;
  actor_name?: string;
  actor?: User | string;
  from_state?: string | null;
  to_state?: string | null;
  comment?: string | null;
  created_at?: string;
  timestamp?: string;
  request_id?: number | string;
  entity_type?: string;
  entity_id?: number | string;
  request_title?: string;
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

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (response.status === 401 && path !== "/auth/login" && path !== "/auth/refresh") {
    if (retry && tokenStore.refresh()) {
      try {
        const refreshed = await fetch(`${API_URL}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: tokenStore.refresh() }),
        });
        if (refreshed.ok) {
          const tokens = await refreshed.json();
          tokenStore.save(tokens.access_token, tokens.refresh_token);
          return request<T>(path, init, false);
        }
      } catch { /* revoked or unavailable refresh token */ }
    }
    tokenStore.clear();
    window.dispatchEvent(new Event("flowapprove:auth-expired"));
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : message;
    } catch { /* non-JSON error response */ }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
function list<T>(data: T[] | { items: T[] }): T[] {
  return Array.isArray(data) ? data : data.items || [];
}
export const api = {
  async login(email: string, password: string) {
    const data = await request<{ access_token: string; refresh_token: string; user: User }>(
      "/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, false
    );
    tokenStore.save(data.access_token, data.refresh_token);
    return data.user;
  },
  me: () => request<User>("/auth/me"),
  logout: async () => {
    try { await request("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: tokenStore.refresh() }) }); }
    finally { tokenStore.clear(); }
  },
  async requests() { return list(await request<ApprovalRequest[] | {items: ApprovalRequest[]}>("/requests")); },
  getRequest: (id: string | number) => request<ApprovalRequest>(`/requests/${id}`),
  async inbox() { return list(await request<ApprovalRequest[] | {items: ApprovalRequest[]}>("/inbox")); },
  createRequest: (payload: { title: string; description: string; amount: string; workflow_id: string | number }) =>
    request<ApprovalRequest>("/requests", { method: "POST", body: JSON.stringify(payload) }),
  submit: (id: string | number) => request<ApprovalRequest>(`/requests/${id}/submit`, { method: "POST" }),
  cancel: (id: string | number) => request<ApprovalRequest>(`/requests/${id}/cancel`, { method: "POST" }),
  approve: (id: string | number, comment: string) =>
    request<ApprovalRequest>(`/requests/${id}/approve`, { method: "POST", body: JSON.stringify({ comment }) }),
  reject: (id: string | number, comment: string) =>
    request<ApprovalRequest>(`/requests/${id}/reject`, { method: "POST", body: JSON.stringify({ comment }) }),
  async workflows() { return list(await request<Workflow[] | {items: Workflow[]}>("/workflows")); },
  createWorkflow: (payload: { name: string; description: string; steps: Array<{ step_order: number; required_role: Role; label: string }> }) =>
    request<Workflow>("/workflows", { method: "POST", body: JSON.stringify(payload) }),
  updateWorkflow: (id: string | number, payload: { name?: string; description?: string | null; is_active?: boolean }) =>
    request<Workflow>(`/workflows/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  replaceWorkflowSteps: (id: string | number, steps: Array<{ step_order: number; required_role: Role; label: string }>) =>
    request<Workflow>(`/workflows/${id}/steps`, { method: "POST", body: JSON.stringify({ steps }) }),
  async users() { return list(await request<User[] | {items: User[]}>("/users")); },
  updateUser: (id: string | number, payload: { role?: Role; is_active?: boolean }) =>
    request<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  async audit() { return list(await request<AuditEntry[] | {items: AuditEntry[]}>("/audit")); },
  async requestAudit(id: string | number) { return list(await request<AuditEntry[] | {items: AuditEntry[]}>(`/requests/${id}/audit`)); },
};
