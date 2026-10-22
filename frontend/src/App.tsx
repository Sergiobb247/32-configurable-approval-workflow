import { Component, ErrorInfo, FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Activity, AlertCircle, ArrowLeft, ArrowRight, Check, CheckCheck, ChevronRight,
  CircleDashed, CircleHelp, ClipboardCheck, Clock3, FilePlus2, Files, Filter, GripVertical,
  LogOut, Menu, Plus, Search, ShieldCheck, SlidersHorizontal, Trash2, Users,
  WalletCards, Workflow as WorkflowIcon, X, XCircle, RefreshCw, Eye, ArrowUp, ArrowDown,
} from "lucide-react";
import { api, ApiError, ApprovalRequest, AuditEntry, RequestStatus, Role, User, Workflow, tokenStore } from "./api";

const money = (amount: string | number) => new Intl.NumberFormat("en-NG", {
  style: "currency", currency: "NGN", minimumFractionDigits: 2, maximumFractionDigits: 2,
}).format(Number(amount || 0));

const date = (value?: string | null) => value ? new Date(value).toLocaleDateString("en-GB", {
  day: "numeric", month: "short", year: "numeric",
}) : "—";

const dateTime = (value?: string | null) => value ? new Date(value).toLocaleString("en-GB", {
  day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
}) : "—";

const personName = (request: ApprovalRequest) => {
  const submitter = request.submitted_by;
  if (typeof submitter === "string") return submitter;
  return submitter?.full_name || submitter?.name || "Team member";
};

const userName = (user: User) => user.full_name || user.name || user.email.split("@")[0];
const roleLabel = (role?: Role | string | null) => role ? role.charAt(0) + role.slice(1).toLowerCase() : "—";
const statusLabel: Record<RequestStatus, string> = {
  PENDING: "Pending", APPROVED: "Approved", REJECTED: "Rejected", DRAFT: "Draft", CANCELLED: "Cancelled",
};

function roleHome(role: Role) {
  if (role === "ADMIN") return "/workflows";
  if (role === "MANAGER" || role === "FINANCE") return "/inbox";
  return "/requests";
}

function StatusBadge({ status }: { status: RequestStatus }) {
  return <span className={`status status-${status.toLowerCase()}`}><span className="status-dot" />{statusLabel[status]}</span>;
}

function Avatar({ user, size = "normal" }: { user?: User | null; size?: "normal" | "large" }) {
  const name = user ? userName(user) : "Flow user";
  const initials = name.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map(part => part[0]).join("").toUpperCase();
  return <span className={`avatar ${size === "large" ? "avatar-large" : ""}`} title={name}>{initials || "FU"}</span>;
}

function ErrorBanner({ message, onClose }: { message: string; onClose: () => void }) {
  if (!message) return null;
  return <div className="alert alert-error" role="alert"><AlertCircle size={17}/><span>{message}</span><button className="icon-button" onClick={onClose} aria-label="Dismiss error"><X size={16}/></button></div>;
}

function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-icon"><Files size={23}/></span><h3>{title}</h3><p>{description}</p>{action}</div>;
}

class AppErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) { /* Deliberately no sensitive logging. */ }
  render() {
    if (!this.state.hasError) return this.props.children;
    return <div className="loading-screen"><div className="brand-mark">F</div><h2>Something went wrong</h2><p>Refresh the page to return to your workspace.</p><button className="button button-primary" onClick={() => window.location.reload()}>Refresh application</button></div>;
  }
}

function App() {
  return <AppErrorBoundary><Workspace /></AppErrorBoundary>;
}

function Workspace() {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    if (!tokenStore.get() && !tokenStore.refresh()) { setAuthLoading(false); return; }
    api.me().then(current => { if (active) setUser(current); }).catch(() => {
      tokenStore.clear();
    }).finally(() => { if (active) setAuthLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => { setMobileOpen(false); setError(""); }, [location.pathname, location.search]);

  useEffect(() => {
    const expire = () => {
      setUser(null);
      navigate("/login", { replace: true, state: { message: "Your session expired. Please sign in again." } });
    };
    window.addEventListener("flowapprove:auth-expired", expire);
    return () => window.removeEventListener("flowapprove:auth-expired", expire);
  }, [navigate]);

  const notify = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3000);
  }, []);

  const logout = async () => {
    try { await api.logout(); } catch { tokenStore.clear(); }
    setUser(null);
    navigate("/login", { replace: true });
  };

  if (authLoading) return <div className="loading-screen"><div className="brand-mark">F</div><span className="spinner"/><p>Preparing your workspace…</p></div>;
  if (!user) return <Routes><Route path="/login" element={<Login onLogin={current => { setUser(current); navigate("/", { replace: true }); }}/>} /><Route path="*" element={<Navigate to="/login" replace/>}/></Routes>;
  if (location.pathname === "/login") return <Navigate to={roleHome(user.role)} replace/>;

  const isAdmin = user.role === "ADMIN";
  const canInbox = user.role === "MANAGER" || user.role === "FINANCE";
  const requestLabel = isAdmin ? "All requests" : "My requests";

  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
      <Link to="/" className="brand"><span className="brand-mark"><ShieldCheck size={21}/></span><span>Flow<span className="brand-light">Approve</span></span></Link>
      <div className="workspace-label">WORKSPACE</div>
      <nav className="nav-list" aria-label="Main navigation">
        <NavItem to="/requests" icon={<Files size={18}/>} label={requestLabel}/>
        {canInbox && <NavItem to="/inbox" icon={<ClipboardCheck size={18}/>} label="Approval inbox"/>}
        {isAdmin && <>
          <div className="nav-section">ADMINISTRATION</div>
          <NavItem to="/workflows" icon={<WorkflowIcon size={18}/>} label="Workflow builder"/>
          <NavItem to="/users" icon={<Users size={18}/>} label="Users & audit"/>
        </>}
      </nav>
      <div className="sidebar-bottom">
        <div className="help-card"><span className="help-icon"><CircleHelp size={17}/></span><div><strong>Need a hand?</strong><small>Ask your workspace admin.</small></div></div>
        <div className="sidebar-profile"><Avatar user={user}/><div className="profile-info"><strong>{userName(user)}</strong><small>{roleLabel(user.role)}</small></div><button className="icon-button" onClick={logout} title="Sign out" aria-label="Sign out"><LogOut size={17}/></button></div>
      </div>
    </aside>
    {mobileOpen && <button className="mobile-scrim" onClick={() => setMobileOpen(false)} aria-label="Close menu"/>}
    <main className="main-area">
      <header className="topbar">
        <button className="mobile-menu icon-button" onClick={() => setMobileOpen(v => !v)} aria-label="Toggle navigation">{mobileOpen ? <X size={20}/> : <Menu size={20}/>}</button>
        <div className="breadcrumbs"><span>Workspace</span><ChevronRight size={14}/><strong>{pageTitle(location.pathname, location.search)}</strong></div>
        <div className="topbar-right"><span className="secure-label"><span className="secure-dot"/> Secure workspace</span><span className="role-badge">{user.role}</span><Avatar user={user}/><button className="button button-secondary button-small topbar-signout" onClick={logout}><LogOut size={15}/> Sign out</button></div>
      </header>
      <div className="page-wrap">
        <ErrorBanner message={error} onClose={() => setError("")}/>
        <Routes>
          <Route path="/" element={<Navigate to={roleHome(user.role)} replace/>}/>
          <Route path="/requests" element={<RequestsPage user={user} setError={setError}/>}/>
          <Route path="/requests/new" element={<NewRequest setError={setError} notify={notify}/>}/>
          <Route path="/requests/:id" element={<RequestDetail user={user} setError={setError} notify={notify}/>}/>
          <Route path="/inbox" element={canInbox ? <InboxPage setError={setError}/> : <Navigate to={roleHome(user.role)} replace/>}/>
          <Route path="/workflows" element={isAdmin ? <WorkflowsPage setError={setError} notify={notify}/> : <Navigate to={roleHome(user.role)} replace/>}/>
          <Route path="/users" element={isAdmin ? <UsersPage user={user} setError={setError} notify={notify}/> : <Navigate to={roleHome(user.role)} replace/>}/>
          <Route path="/audit" element={isAdmin ? <Navigate to="/users?tab=audit" replace/> : <Navigate to={roleHome(user.role)} replace/>}/>
          <Route path="*" element={<Navigate to={roleHome(user.role)} replace/>}/>
        </Routes>
      </div>
      <footer className="footer"><span>FlowApprove</span><span>Every decision. One clear trail.</span></footer>
    </main>
    {toast && <div className="toast" role="status"><CheckCheck size={17}/>{toast}</div>}
  </div>;
}

function NavItem({ to, icon, label, end = false }: { to: string; icon: ReactNode; label: string; end?: boolean }) {
  return <NavLink to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`}>{icon}<span>{label}</span>{label === "Approval inbox" && <span className="nav-new-dot"/>}</NavLink>;
}

function pageTitle(path: string, search = "") {
  if (path === "/") return "Workspace";
  if (path.startsWith("/requests/new")) return "New request";
  if (path.startsWith("/requests/") && path !== "/requests") return "Request details";
  if (path === "/users" && new URLSearchParams(search).get("tab") === "audit") return "Global audit";
  return ({ "/requests": "Requests", "/inbox": "Approval inbox", "/workflows": "Workflow builder", "/users": "Users" } as Record<string, string>)[path] || "Workspace";
}

function PageHeading({ eyebrow, title, subtitle, action }: { eyebrow?: string; title: string; subtitle: string; action?: ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1><p>{subtitle}</p></div>{action && <div className="heading-action">{action}</div>}</div>;
}

function TableSkeleton() {
  return <div className="skeleton-wrap">{[1, 2, 3, 4].map(n => <div className="skeleton-row" key={n}><span/><span/><span/></div>)}</div>;
}

function RequestsPage({ user, setError }: { user: User; setError: (message: string) => void }) {
  const [rows, setRows] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"ALL" | RequestStatus>("ALL");
  const [sort, setSort] = useState<"newest" | "oldest" | "amount">("newest");

  const load = useCallback(async () => {
    setLoading(true);
    try { const response = await api.requests({ limit: 200 }); setRows(response.items); setError(""); }
    catch (error) { setError(error instanceof Error ? error.message : "Couldn't load requests."); }
    finally { setLoading(false); }
  }, [setError]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...rows]
      .filter(row => filter === "ALL" || row.status === filter)
      .filter(row => !q || `${row.title} ${personName(row)} ${row.id} ${row.workflow_id}`.toLowerCase().includes(q))
      .sort((a, b) => {
        if (sort === "amount") return Number(b.amount) - Number(a.amount);
        const left = new Date(a.created_at).getTime();
        const right = new Date(b.created_at).getTime();
        return sort === "newest" ? right - left : left - right;
      });
  }, [rows, filter, query, sort]);

  const title = user.role === "ADMIN" ? "All requests" : "My requests";
  const subtitle = user.role === "ADMIN" ? "Review every request visible to the workspace administrator." : "Keep track of the requests you have submitted.";

  return <div className="page-content">
    <PageHeading title={title} subtitle={subtitle} action={<><button className="button button-secondary" onClick={load}><RefreshCw size={16}/> Refresh</button><Link to="/requests/new" className="button button-primary"><Plus size={17}/> New request</Link></>}/>
    <div className="panel">
      <div className="toolbar">
        <div className="search-field"><Search size={17}/><input aria-label="Search requests" placeholder="Search by title, requester or ID…" value={query} onChange={e => setQuery(e.target.value)}/>{query && <button onClick={() => setQuery("")} aria-label="Clear search"><X size={14}/></button>}</div>
        <div className="filter-control"><Filter size={16}/><select aria-label="Filter by status" value={filter} onChange={e => setFilter(e.target.value as "ALL" | RequestStatus)}><option value="ALL">All statuses</option><option value="PENDING">Pending</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="DRAFT">Draft</option><option value="CANCELLED">Cancelled</option></select></div>
        <select className="toolbar-select" aria-label="Sort requests" value={sort} onChange={e => setSort(e.target.value as typeof sort)}><option value="newest">Newest</option><option value="oldest">Oldest</option><option value="amount">Highest amount</option></select>
      </div>
      {loading ? <TableSkeleton/> : filtered.length === 0 ? <EmptyState title={rows.length ? "No matching requests" : "No requests yet"} description={rows.length ? "Try another search or status filter." : "Create a request to start an approval workflow."} action={<Link className="button button-primary button-small" to="/requests/new"><Plus size={15}/> New request</Link>}/> :
        <div className="table-scroll"><table><thead><tr><th>Request</th><th>Requester</th><th>Amount</th><th>Created</th><th>Status</th><th/></tr></thead><tbody>{filtered.map(row => <tr key={row.id}><td><Link to={`/requests/${row.id}`} className="request-title">{row.title}</Link><small className="table-sub">REQ-{String(row.id).padStart(4, "0")}</small></td><td>{personName(row)}</td><td className="amount-cell">{money(row.amount)}</td><td>{date(row.created_at)}</td><td><StatusBadge status={row.status}/></td><td><Link className="table-action" to={`/requests/${row.id}`} aria-label={`Open ${row.title}`}><ChevronRight size={17}/></Link></td></tr>)}</tbody></table></div>}
      <div className="panel-foot"><span>{filtered.length} shown · {rows.length} loaded</span><span>Data comes directly from the approval API</span></div>
    </div>
  </div>;
}

function NewRequest({ setError, notify }: { setError: (message: string) => void; notify: (message: string) => void }) {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [workflowId, setWorkflowId] = useState("");

  useEffect(() => {
    api.workflows({ limit: 200 }).then(response => {
      const active = response.items.filter(workflow => workflow.is_active);
      setWorkflows(active);
      if (active[0]) setWorkflowId(String(active[0].id));
    }).catch(error => setError(error instanceof Error ? error.message : "Couldn't load workflows.")).finally(() => setLoading(false));
  }, [setError]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedTitle = title.trim();
    const numericAmount = Number(amount);
    if (!trimmedTitle) return setError("Request title is required.");
    if (!Number.isFinite(numericAmount) || numericAmount <= 0) return setError("Amount must be greater than zero.");
    if (!workflowId) return setError("Choose an active workflow before creating a request.");
    setSaving(true); setError("");
    try {
      const request = await api.createRequest({ title: trimmedTitle, description: description.trim() || null, amount: numericAmount.toFixed(2), workflow_id: workflowId });
      notify("Draft request created.");
      navigate(`/requests/${request.id}`);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Couldn't create the request.");
    } finally { setSaving(false); }
  };

  return <div className="page-content narrow-page">
    <PageHeading eyebrow="REQUESTS" title="New request" subtitle="Provide the information approvers need. The request remains a draft until you submit it."/>
    <form className="panel form-panel" onSubmit={submit}>
      <div className="form-section-title"><span className="form-section-icon"><FilePlus2 size={18}/></span><div><h2>Request details</h2><p>Required fields are marked with an asterisk.</p></div></div>
      <label className="field-label" htmlFor="request-title">Request title <span>*</span></label>
      <input id="request-title" className="text-input" value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Laptop replacement" maxLength={200} required/>
      <div className="field-help">Use a short, specific description of the request.</div>
      <label className="field-label" htmlFor="request-amount">Amount (NGN) <span>*</span></label>
      <div className="money-input"><span>₦</span><input id="request-amount" type="number" min="0.01" max="9999999999.99" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00" required/></div>
      <label className="field-label" htmlFor="request-workflow">Approval workflow <span>*</span></label>
      <select id="request-workflow" className="text-input" value={workflowId} onChange={e => setWorkflowId(e.target.value)} required disabled={loading || !workflows.length}><option value="">{loading ? "Loading workflows…" : "Choose a workflow"}</option>{workflows.map(workflow => <option key={workflow.id} value={workflow.id}>{workflow.name}</option>)}</select>
      {!loading && !workflows.length && <div className="inline-warning"><AlertCircle size={16}/>No active workflows are available. Ask an admin to configure one.</div>}
      <label className="field-label" htmlFor="request-description">Description</label>
      <textarea id="request-description" className="text-input textarea" value={description} onChange={e => setDescription(e.target.value)} placeholder="Explain why this is needed and include relevant context…" rows={5} maxLength={2000}/>
      <div className="form-note"><ShieldCheck size={16}/><span>Submitting the draft freezes the selected workflow chain for this request.</span></div>
      <div className="form-actions"><Link to="/requests" className="button button-secondary">Cancel</Link><button className="button button-primary" type="submit" disabled={saving || loading || !workflows.length}>{saving ? "Creating…" : "Create draft"}<ArrowRight size={16}/></button></div>
    </form>
  </div>;
}

function StepTimeline({ request }: { request: ApprovalRequest }) {
  if (request.status === "DRAFT") {
    return <div className="inline-info"><CircleDashed size={17}/><span><strong>Approval chain not started.</strong><br/>The backend creates the frozen step snapshot when this draft is submitted.</span></div>;
  }
  if (!request.steps?.length) {
    return <div className="inline-warning"><AlertCircle size={17}/><span>The API returned no approval steps for this submitted request.</span></div>;
  }
  return <div className="timeline">
    {request.steps.map((step, index) => {
      const state = String(step.state || "").toLowerCase();
      const done = state === "done";
      const current = state === "current";
      const terminalHere = current && (request.status === "REJECTED" || request.status === "CANCELLED");
      const role = step.role || step.required_role;
      const title = step.label || `${roleLabel(role)} approval`;
      const stateText = done ? "Completed" : terminalHere ? (request.status === "REJECTED" ? "Rejected here" : "Cancelled here") : current ? "Current step" : "Upcoming";
      return <div className="timeline-item" key={`${step.order || step.step_order || index}-${step.id || index}`}>
        <span className={`timeline-marker ${done ? "timeline-done" : terminalHere ? "timeline-stopped" : current ? "timeline-current" : ""}`}>{done ? <Check size={14}/> : index + 1}</span>
        <div className="timeline-content">
          <div className="timeline-title"><strong>{title}</strong><span className={`timeline-state ${terminalHere ? "timeline-state-stop" : ""}`}>{stateText}</span></div>
          <p>{step.acted_by ? <>Action recorded by <strong>{step.acted_by}</strong>{step.acted_at ? ` · ${dateTime(step.acted_at)}` : ""}</> : current ? `Waiting for ${roleLabel(role)} approval.` : "Not started yet."}</p>
        </div>
      </div>;
    })}
  </div>;
}

function RequestDetail({ user, setError, notify }: { user: User; setError: (message: string) => void; notify: (message: string) => void }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [request, setRequest] = useState<ApprovalRequest | null>(null);
  const [events, setEvents] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [inlineError, setInlineError] = useState("");

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [requestResponse, auditResponse] = await Promise.all([api.getRequest(id), api.requestAudit(id, { limit: 200 })]);
      setRequest(requestResponse);
      setEvents(auditResponse.items);
      setError("");
    } catch (error) {
      setRequest(null);
      setError(error instanceof Error ? error.message : "Couldn't load this request.");
    } finally { setLoading(false); }
  }, [id, setError]);

  useEffect(() => { load(); }, [load]);

  const submitAction = async (kind: "submit" | "approve" | "reject" | "cancel") => {
    if (!request || busy) return;
    if (kind === "reject" && !comment.trim()) { setInlineError("Add a reason before rejecting this request."); return; }
    if (kind === "reject" && !window.confirm("Reject this request? This decision cannot be undone.")) return;
    if (kind === "cancel" && !window.confirm("Cancel this request? This action cannot be undone.")) return;
    setBusy(true); setInlineError(""); setError("");
    try {
      if (kind === "submit") await api.submit(request.id);
      if (kind === "approve") await api.approve(request.id, comment.trim());
      if (kind === "reject") await api.reject(request.id, comment.trim());
      if (kind === "cancel") await api.cancel(request.id);
      notify(({ submit: "Request submitted for approval.", approve: "Approval recorded.", reject: "Request rejected.", cancel: "Request cancelled." } as const)[kind]);
      setComment("");
      await load();
    } catch (error) {
      const message = error instanceof Error ? error.message : "This action could not be saved.";
      setInlineError(message);
      if (error instanceof ApiError && (error.status === 401 || error.status === 403 || error.status === 409)) await load();
    } finally { setBusy(false); }
  };

  if (loading) return <div className="page-content"><TableSkeleton/></div>;
  if (!request) return <div className="page-content"><EmptyState title="Request unavailable" description="The request may not exist, may have been removed, or you may not have permission to view it." action={<Link to="/requests" className="button button-primary">Back to requests</Link>}/></div>;

  const submitter = request.submitted_by;
  const submitterId = typeof submitter === "object" ? submitter.id : undefined;
  const submitterName = typeof submitter === "string" ? submitter : userName(submitter);
  const isSubmitter = String(submitterId ?? "") === String(user.id);
  const canSubmit = request.status === "DRAFT" && isSubmitter;
  const canCancel = (request.status === "DRAFT" || request.status === "PENDING") && (isSubmitter || user.role === "ADMIN");
  const canDecide = request.status === "PENDING" && request.can_act === true;
  const waitingMessage = user.role === "ADMIN" ? "Admins configure workflows and can cancel requests, but they do not approve requests." : "This request is waiting for another role. It will appear in your inbox when it reaches your step.";

  return <div className="page-content">
    <button className="back-link" onClick={() => navigate(-1)}><ArrowLeft size={15}/> Back</button>
    <PageHeading eyebrow={`REQ-${String(request.id).padStart(4, "0")}`} title={request.title} subtitle={request.description || "Request details and approval history."} action={<StatusBadge status={request.status}/>}/>
    <div className="detail-grid">
      <section className="panel detail-main">
        <div className="detail-summary"><div><span className="detail-label">REQUEST AMOUNT</span><div className="detail-amount">{money(request.amount)}</div></div><div><span className="detail-label">SUBMITTED BY</span><strong>{submitterName}</strong></div><div><span className="detail-label">CREATED</span><strong>{date(request.created_at)}</strong></div></div>
        <div className="panel-subheading"><h2>Approval progress</h2><p>{request.status === "DRAFT" ? "The approval chain is created when the draft is submitted." : "The chain below is the frozen snapshot returned by the API."}</p></div>
        <StepTimeline request={request}/>
        {(canSubmit || canDecide || canCancel) && <div className="decision-panel">
          <div className="panel-subheading"><h2>{canSubmit ? "Submit request" : canDecide ? "Your decision" : "Request actions"}</h2><p>{canSubmit ? "Submitting starts the approval process." : canDecide ? `You are acting as ${roleLabel(user.role)}.` : "You can cancel a non-terminal request when permitted."}</p></div>
          {canDecide && <><label className="field-label" htmlFor="request-comment">Comment</label><textarea id="request-comment" className="text-input textarea" rows={3} maxLength={500} value={comment} onChange={e => setComment(e.target.value)} placeholder="Add context for your decision…"/><p className="field-help">A rejection requires a comment. An approval comment is optional.</p></>}
          {inlineError && <div className="inline-warning" role="alert"><AlertCircle size={16}/>{inlineError}</div>}
          <div className="decision-actions">
            {canSubmit && <button className="button button-primary" disabled={busy} onClick={() => submitAction("submit")}>{busy ? "Submitting…" : "Submit for approval"}<ArrowRight size={16}/></button>}
            {canDecide && <><button className="button button-danger" disabled={busy} onClick={() => submitAction("reject")}><XCircle size={16}/> Reject</button><button className="button button-success" disabled={busy} onClick={() => submitAction("approve")}><Check size={16}/> Approve</button></>}
            {canCancel && <button className="button button-secondary" disabled={busy} onClick={() => submitAction("cancel")}>Cancel request</button>}
          </div>
        </div>}
        {request.status === "PENDING" && !canDecide && !canCancel && <div className="inline-info detail-permission-note"><Eye size={17}/><span>{waitingMessage}</span></div>}
      </section>
      <aside className="panel detail-side"><div className="panel-subheading"><h2>Activity history</h2><p>Recorded actions for this request</p></div>{events.length ? <div className="audit-list">{events.map((event, index) => <div className="audit-item" key={event.id || index}><span className="audit-symbol"><Activity size={15}/></span><div><strong>{formatAuditAction(event.action)}</strong><p>{auditActor(event)}{event.to_state ? ` · ${event.to_state.toLowerCase()}` : ""}</p>{event.comment && <blockquote>{event.comment}</blockquote>}<small>{dateTime(event.created_at)}</small></div></div>)}</div> : <EmptyState title="No activity yet" description="Recorded actions will appear here."/>}</aside>
    </div>
  </div>;
}

function formatAuditAction(action: string) {
  return action.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, char => char.toUpperCase());
}
function auditActor(event: AuditEntry) {
  return typeof event.actor === "string" ? event.actor : event.actor?.full_name || "Team member";
}

function InboxPage({ setError }: { setError: (message: string) => void }) {
  const [rows, setRows] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { const response = await api.inbox({ limit: 200 }); setRows(response.items); setError(""); }
    catch (error) { setError(error instanceof Error ? error.message : "Couldn't load the approval inbox."); }
    finally { setLoading(false); }
  }, [setError]);
  useEffect(() => { load(); }, [load]);

  const filtered = rows.filter(row => `${row.title} ${personName(row)} ${row.id}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="page-content">
    <PageHeading title="Approval inbox" subtitle="Requests waiting for your role. Open one to review the chain, history, and available actions." action={<button className="button button-secondary" onClick={load}><RefreshCw size={16}/> Refresh</button>}/>
    <div className="panel"><div className="toolbar"><div className="search-field"><Search size={17}/><input aria-label="Search inbox" placeholder="Search waiting requests…" value={query} onChange={e => setQuery(e.target.value)}/></div><span className="toolbar-meta"><ClipboardCheck size={15}/>{rows.length} waiting</span></div>
      {loading ? <TableSkeleton/> : filtered.length === 0 ? <EmptyState title="Nothing waiting for you" description={rows.length ? "Try another search term." : "When a request reaches your role, it will appear here."}/> : <div className="table-scroll"><table><thead><tr><th>Request</th><th>Submitted by</th><th>Amount</th><th>Created</th><th>Status</th><th/></tr></thead><tbody>{filtered.map(row => <tr key={row.id}><td><Link to={`/requests/${row.id}`} className="request-title">{row.title}</Link><small className="table-sub">REQ-{String(row.id).padStart(4, "0")}</small></td><td>{personName(row)}</td><td className="amount-cell">{money(row.amount)}</td><td>{date(row.created_at)}</td><td><StatusBadge status={row.status}/></td><td><Link className="table-action" to={`/requests/${row.id}`} aria-label={`Review ${row.title}`}><ChevronRight size={17}/></Link></td></tr>)}</tbody></table></div>}
      <div className="panel-foot"><span>{filtered.length} request{filtered.length === 1 ? "" : "s"}</span><span>Only requests awaiting your role are returned by the API</span></div>
    </div>
  </div>;
}

type DraftStep = { key: string; required_role: "MANAGER" | "FINANCE"; label: string };

function WorkflowsPage({ setError, notify }: { setError: (message: string) => void; notify: (message: string) => void }) {
  const [rows, setRows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Workflow | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState<DraftStep[]>([{ key: crypto.randomUUID(), required_role: "MANAGER", label: "Manager review" }]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const response = await api.workflows({ limit: 200 }); setRows(response.items); setError(""); }
    catch (error) { setError(error instanceof Error ? error.message : "Couldn't load workflows."); }
    finally { setLoading(false); }
  }, [setError]);
  useEffect(() => { load(); }, [load]);

  const resetForm = () => {
    setShowForm(false); setEditing(null); setName(""); setDescription("");
    setSteps([{ key: crypto.randomUUID(), required_role: "MANAGER", label: "Manager review" }]);
  };

  const startCreate = () => {
    setEditing(null); setName(""); setDescription("");
    setSteps([{ key: crypto.randomUUID(), required_role: "MANAGER", label: "Manager review" }]);
    setShowForm(true);
  };

  const startEdit = (workflow: Workflow) => {
    setEditing(workflow); setName(workflow.name); setDescription(workflow.description || "");
    setSteps((workflow.steps || []).map(step => ({ key: String(step.id ?? crypto.randomUUID()), required_role: step.required_role === "FINANCE" ? "FINANCE" : "MANAGER", label: step.label })));
    setShowForm(true);
  };

  const addStep = () => setSteps(previous => [...previous, { key: crypto.randomUUID(), required_role: "FINANCE", label: "Finance review" }]);
  const removeStep = (key: string) => setSteps(previous => previous.filter(step => step.key !== key));
  const updateStep = (key: string, patch: Partial<DraftStep>) => setSteps(previous => previous.map(step => step.key === key ? { ...step, ...patch } : step));
  const moveStep = (index: number, direction: -1 | 1) => setSteps(previous => {
    const next = [...previous]; const target = index + direction;
    if (target < 0 || target >= next.length) return previous;
    [next[index], next[target]] = [next[target], next[index]];
    return next;
  });

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return setError("Workflow name is required.");
    if (!steps.length) return setError("A workflow needs at least one approval step.");
    if (steps.some(step => !step.label.trim())) return setError("Every approval step needs a label.");
    setBusy(true); setError("");
    const payloadSteps = steps.map((step, index) => ({ step_order: index + 1, required_role: step.required_role, label: step.label.trim() }));
    try {
      if (editing) {
        await api.replaceWorkflowSteps(editing.id, payloadSteps);
        await api.updateWorkflow(editing.id, { name: trimmedName, description: description.trim() || null });
        notify("Workflow updated. Requests already in progress keep their frozen approval chain.");
      } else {
        await api.createWorkflow({ name: trimmedName, description: description.trim() || null, steps: payloadSteps });
        notify("Workflow created.");
      }
      resetForm();
      await load();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Couldn't save the workflow.");
    } finally { setBusy(false); }
  };

  const toggleActive = async (workflow: Workflow) => {
    const next = !workflow.is_active;
    if (!next && !window.confirm(`Deactivate “${workflow.name}”? New requests will no longer be able to use it.`)) return;
    try {
      const updated = await api.updateWorkflow(workflow.id, { is_active: next });
      setRows(previous => previous.map(item => item.id === updated.id ? updated : item));
      notify(next ? "Workflow activated." : "Workflow deactivated.");
    } catch (error) { setError(error instanceof Error ? error.message : "Couldn't update workflow status."); }
  };

  return <div className="page-content">
    <PageHeading title="Workflow builder" subtitle="Configure the ordered approval chains used by new requests. Admins configure workflows; they are not approval steps." action={<button className="button button-primary" onClick={() => showForm ? resetForm() : startCreate()}><Plus size={17}/>{showForm ? "Close form" : "New workflow"}</button>}/>
    {showForm && <form className="panel workflow-form" onSubmit={save}>
      <div className="form-section-title"><span className="form-section-icon"><WorkflowIcon size={18}/></span><div><h2>{editing ? "Edit workflow" : "Create workflow"}</h2><p>Steps are saved as one ordered chain. Requests already submitted keep their existing snapshot.</p></div></div>
      <label className="field-label" htmlFor="workflow-name">Workflow name <span>*</span></label><input className="text-input" id="workflow-name" value={name} onChange={e => setName(e.target.value)} maxLength={120} required placeholder="e.g. Expense approval"/>
      <label className="field-label" htmlFor="workflow-description">Description</label><textarea className="text-input textarea" id="workflow-description" value={description} onChange={e => setDescription(e.target.value)} rows={2} maxLength={500} placeholder="What is this workflow used for?"/>
      <div className="workflow-step-editor-header"><div><label className="field-label">Approval steps <span>*</span></label><p className="field-help">Only Manager and Finance roles are permitted by the existing API contract.</p></div><button type="button" className="button button-secondary button-small" onClick={addStep}><Plus size={14}/> Add step</button></div>
      <div className="workflow-step-editor">{steps.map((step, index) => <div className="workflow-step-row" key={step.key}>
        <span className="workflow-drag"><GripVertical size={16}/><strong>{index + 1}</strong></span>
        <select className="text-input" value={step.required_role} onChange={e => updateStep(step.key, { required_role: e.target.value as "MANAGER" | "FINANCE" })}><option value="MANAGER">Manager</option><option value="FINANCE">Finance</option></select>
        <input className="text-input" value={step.label} maxLength={120} onChange={e => updateStep(step.key, { label: e.target.value })} placeholder="Step label" aria-label={`Label for step ${index + 1}`}/>
        <div className="step-row-actions"><button type="button" className="icon-button" disabled={index === 0} onClick={() => moveStep(index, -1)} aria-label={`Move step ${index + 1} up`}><ArrowUp size={15}/></button><button type="button" className="icon-button" disabled={index === steps.length - 1} onClick={() => moveStep(index, 1)} aria-label={`Move step ${index + 1} down`}><ArrowDown size={15}/></button><button type="button" className="icon-button danger-icon" disabled={steps.length === 1} onClick={() => removeStep(step.key)} aria-label={`Remove step ${index + 1}`}><Trash2 size={15}/></button></div>
      </div>)}</div>
      <div className="form-note"><ShieldCheck size={16}/><span>The backend rejects ADMIN approval steps. This editor intentionally does not offer Admin as an approver.</span></div>
      <div className="form-actions"><button type="button" className="button button-secondary" onClick={resetForm}>Cancel</button><button type="submit" className="button button-primary" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Create workflow"}</button></div>
    </form>}
    {loading ? <div className="panel"><TableSkeleton/></div> : rows.length === 0 ? <div className="panel"><EmptyState title="No workflows found" description="Create an approval chain to get started." action={<button className="button button-primary button-small" onClick={startCreate}><Plus size={15}/> New workflow</button>}/></div> :
      <div className="workflow-grid">{rows.map(workflow => <div className="panel workflow-card" key={workflow.id}>
        <div className="workflow-card-top"><span className="workflow-symbol"><WorkflowIcon size={19}/></span><span className={`status ${workflow.is_active ? "status-approved" : "status-cancelled"}`}><span className="status-dot"/>{workflow.is_active ? "Active" : "Inactive"}</span></div>
        <h2>{workflow.name}</h2><p>{workflow.description || "Approval workflow"}</p>
        <div className="workflow-steps">{workflow.steps.map((step, index) => <div className="workflow-step" key={step.id || `${workflow.id}-${index}`}><span>{step.step_order}</span><div><strong>{step.label}</strong><small>{roleLabel(step.required_role)}</small></div>{index < workflow.steps.length - 1 && <div className="workflow-connector"/>}</div>)}</div>
        <div className="workflow-card-foot"><span><SlidersHorizontal size={14}/> {workflow.steps.length} step{workflow.steps.length === 1 ? "" : "s"}</span><span>WF-{String(workflow.id).padStart(3, "0")}</span></div>
        <div className="workflow-card-actions"><button className="button button-secondary button-small" onClick={() => startEdit(workflow)}>Edit workflow</button><button className="button button-secondary button-small" onClick={() => toggleActive(workflow)}>{workflow.is_active ? "Deactivate" : "Activate"}</button></div>
      </div>)}</div>}
  </div>;
}

function UsersPage({ user, setError, notify }: { user: User; setError: (message: string) => void; notify: (message: string) => void }) {
  const [rows, setRows] = useState<User[]>([]);
  const [auditRows, setAuditRows] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [savingId, setSavingId] = useState<string | number | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const auditMode = new URLSearchParams(location.search).get("tab") === "audit";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [people, audit] = await Promise.all([api.users({ limit: 200 }), api.audit({ limit: 200 })]);
      setRows(people.items); setAuditRows(audit.items); setError("");
    } catch (error) { setError(error instanceof Error ? error.message : "Couldn't load admin data."); }
    finally { setLoading(false); }
  }, [setError]);
  useEffect(() => { load(); }, [load]);

  const update = async (target: User, payload: { role?: Role; is_active?: boolean }) => {
    if (String(target.id) === String(user.id)) return;
    setSavingId(target.id);
    try {
      const updated = await api.updateUser(target.id, payload);
      setRows(previous => previous.map(item => item.id === updated.id ? updated : item));
      notify("User updated.");
    } catch (error) { setError(error instanceof Error ? error.message : "Couldn't update user."); }
    finally { setSavingId(null); }
  };

  const filteredUsers = rows.filter(person => `${userName(person)} ${person.email} ${person.role}`.toLowerCase().includes(query.trim().toLowerCase()));
  const filteredAudit = auditRows.filter(event => `${event.action} ${auditActor(event)} ${event.request_id || ""} ${event.entity_type || ""} ${event.comment || ""}`.toLowerCase().includes(query.trim().toLowerCase()));

  return <div className="page-content">
    <PageHeading title={auditMode ? "Global audit" : "Users"} subtitle={auditMode ? "A read-only record of workflow, account, and request changes." : "Manage workspace roles and account access. You cannot change your own role or deactivate yourself."}/>
    <div className="panel">
      <div className="admin-tabs"><button className={!auditMode ? "admin-tab admin-tab-active" : "admin-tab"} onClick={() => { setQuery(""); navigate("/users"); }}>Users</button><button className={auditMode ? "admin-tab admin-tab-active" : "admin-tab"} onClick={() => { setQuery(""); navigate("/users?tab=audit"); }}>Global audit</button></div>
      <div className="toolbar"><div className="search-field"><Search size={17}/><input placeholder={auditMode ? "Search audit events…" : "Search users…"} aria-label={auditMode ? "Search audit events" : "Search users"} value={query} onChange={e => setQuery(e.target.value)}/></div><span className="toolbar-meta">{auditMode ? `${filteredAudit.length} events` : `${filteredUsers.length} users`}</span><button className="button button-secondary button-small" onClick={load}><RefreshCw size={15}/> Refresh</button></div>
      {loading ? <TableSkeleton/> : auditMode ? (filteredAudit.length === 0 ? <EmptyState title="No audit events found" description="Events will appear as the team creates workflows, submits requests, and makes decisions."/> : <div className="table-scroll"><table><thead><tr><th>Action</th><th>Actor</th><th>Record</th><th>Transition</th><th>Date</th></tr></thead><tbody>{filteredAudit.map((event, index) => <tr key={event.id || index}><td><strong>{formatAuditAction(event.action)}</strong></td><td>{auditActor(event)}</td><td>{event.request_id ? `Request #${event.request_id}` : `${event.entity_type || "Record"} #${event.entity_id ?? "—"}`}</td><td><span className="transition-text">{event.from_state || "—"} <ArrowRight size={12}/> {event.to_state || "—"}</span></td><td>{dateTime(event.created_at)}</td></tr>)}</tbody></table></div>) : (filteredUsers.length === 0 ? <EmptyState title="No users found" description="Try another search term."/> : <div className="table-scroll"><table><thead><tr><th>User</th><th>Email</th><th>Role</th><th>Account</th></tr></thead><tbody>{filteredUsers.map(person => <tr key={person.id}><td><div className="person-cell"><Avatar user={person}/><strong>{userName(person)}</strong></div></td><td>{person.email}</td><td><select className="table-select" aria-label={`Role for ${person.email}`} value={person.role} disabled={String(person.id) === String(user.id) || savingId === person.id} onChange={e => update(person, { role: e.target.value as Role })}><option value="EMPLOYEE">Employee</option><option value="MANAGER">Manager</option><option value="FINANCE">Finance</option><option value="ADMIN">Admin</option></select></td><td><button className={`status-toggle ${person.is_active === false ? "status-toggle-off" : ""}`} disabled={String(person.id) === String(user.id) || savingId === person.id} onClick={() => update(person, { is_active: person.is_active === false })}>{savingId === person.id ? "Saving…" : person.is_active === false ? "Inactive · Activate" : "Active · Deactivate"}</button></td></tr>)}</tbody></table></div>)}
      <div className="panel-foot"><span>{auditMode ? `${filteredAudit.length} events` : `${filteredUsers.length} users`}</span><span>{auditMode ? "Audit records are read-only" : "Changes are recorded by the backend"}</span></div>
    </div>
  </div>;
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const stateMessage = (location.state as { message?: string } | null)?.message || "";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try { onLogin(await api.login(email.trim().toLowerCase(), password)); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Couldn't sign in. Check your details and try again."); }
    finally { setBusy(false); }
  };

  return <div className="login-page">
    <div className="login-decoration"><div className="login-orbit orbit-one"/><div className="login-orbit orbit-two"/><div className="login-brand"><span className="brand-mark"><ShieldCheck size={21}/></span><span>Flow<span className="brand-light">Approve</span></span></div><div className="login-message"><div className="login-kicker"><span/> CLEAR DECISIONS. REAL ACCOUNTABILITY.</div><h1>Good work<br/>moves forward.</h1><p>One place for requests, approvals, and the decisions that keep your team moving.</p><div className="login-proof"><span><CheckCheck size={16}/> Structured approvals</span><span><CheckCheck size={16}/> Clear audit trail</span><span><CheckCheck size={16}/> Role-based access</span></div></div><div className="login-decoration-foot">FLOWAPPROVE · WORKSPACE</div></div>
    <div className="login-form-area"><form className="login-form" onSubmit={submit}><div className="mobile-login-brand"><span className="brand-mark"><ShieldCheck size={21}/></span><span>Flow<span className="brand-light">Approve</span></span></div><div className="eyebrow">WELCOME BACK</div><h2>Sign in to your workspace</h2><p className="login-intro">Enter your account details to continue.</p>{(error || stateMessage) && <div className="alert alert-error"><AlertCircle size={16}/><span>{error || stateMessage}</span></div>}
      <label className="field-label" htmlFor="email">Email address</label><div className="login-input-wrap"><Users size={17}/><input id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="username" placeholder="you@company.com" required/></div>
      <label className="field-label" htmlFor="password">Password</label><div className="login-input-wrap"><ShieldCheck size={17}/><input id="password" type={showPassword ? "text" : "password"} value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required/><button type="button" className="show-password" onClick={() => setShowPassword(value => !value)}>{showPassword ? "Hide" : "Show"}</button></div>
      <button className="button button-primary login-submit" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}<ArrowRight size={17}/></button>
      <div className="login-security"><ShieldCheck size={15}/> Your session is protected by role-based access.</div>
      <details className="demo-accounts"><summary>Demo account details</summary><p>Seeded local accounts use password <code>Password123!</code></p><button type="button" onClick={() => { setEmail("employee1@demo.io"); setPassword("Password123!"); }}>Employee</button><button type="button" onClick={() => { setEmail("manager1@demo.io"); setPassword("Password123!"); }}>Manager</button><button type="button" onClick={() => { setEmail("finance@demo.io"); setPassword("Password123!"); }}>Finance</button><button type="button" onClick={() => { setEmail("admin@demo.io"); setPassword("Password123!"); }}>Admin</button></details>
    </form><div className="login-bottom">© {new Date().getFullYear()} FlowApprove <span>•</span> Built for teams that need clarity.</div></div>
  </div>;
}

export default App;
