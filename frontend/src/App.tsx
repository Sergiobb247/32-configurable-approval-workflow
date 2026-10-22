import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Activity, ArrowDownLeft, ArrowRight, Bell, Check, CheckCheck, ChevronDown, CircleHelp,
  ClipboardCheck, Clock3, FileClock, FilePlus2, Files, Filter, LayoutDashboard, LogOut,
  Menu, Plus, Search, Settings2, ShieldCheck, SlidersHorizontal, Users, WalletCards, X,
  XCircle, AlertCircle, RefreshCw, Workflow as WorkflowIcon, CheckCircle2, CircleDashed,
  ChevronRight, Eye, CalendarDays, MessageSquareText, TrendingUp
} from "lucide-react";
import { api, ApprovalRequest, AuditEntry, RequestStatus, Role, User, Workflow, tokenStore } from "./api";

const money = (amount: string | number) => new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN", maximumFractionDigits: 0 }).format(Number(amount || 0));
const date = (value?: string) => value ? new Date(value).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "—";
const personName = (r: ApprovalRequest) => r.requester_name || (typeof r.requester === "string" ? r.requester : r.requester?.name || r.requester?.full_name) || (typeof r.submitted_by === "string" ? r.submitted_by : r.submitted_by?.full_name || r.submitted_by?.name) || "Team member";
const statusLabel: Record<RequestStatus, string> = { PENDING: "Pending", APPROVED: "Approved", REJECTED: "Rejected", DRAFT: "Draft", CANCELLED: "Cancelled" };
function roleHome(role: Role) {
  if (role === "ADMIN") return "/workflows";
  if (role === "MANAGER" || role === "FINANCE") return "/inbox";
  return "/requests";
}
function StatusBadge({ status }: { status: RequestStatus }) {
  return <span className={`status status-${status.toLowerCase()}`}><span className="status-dot" />{statusLabel[status] || status}</span>;
}
function Avatar({ user, size = "normal" }: { user?: User | null; size?: "normal" | "large" }) {
  const name = user?.name || user?.full_name || user?.email || "Flow user";
  return <span className={`avatar ${size === "large" ? "avatar-large" : ""}`} title={name}>{name.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map(n => n[0]).join("").toUpperCase()}</span>;
}
function ErrorBanner({ message, onClose }: { message: string; onClose: () => void }) {
  if (!message) return null;
  return <div className="alert alert-error" role="alert"><AlertCircle size={17}/><span>{message}</span><button className="icon-button" onClick={onClose} aria-label="Dismiss error"><X size={16}/></button></div>;
}
function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-icon"><Files size={23}/></span><h3>{title}</h3><p>{description}</p>{action}</div>;
}
function App() {
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
    api.me().then(u => { if (active) setUser(u); }).catch(() => {
      tokenStore.clear();
    }).finally(() => { if (active) setAuthLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => { setMobileOpen(false); setError(""); }, [location.pathname]);
  useEffect(() => {
    const expire = () => { setUser(null); navigate("/login", { replace: true, state: { message: "Please sign in again" } }); };
    window.addEventListener("flowapprove:auth-expired", expire);
    return () => window.removeEventListener("flowapprove:auth-expired", expire);
  }, [navigate]);
  const notify = (message: string) => { setToast(message); window.setTimeout(() => setToast(""), 3000); };
  const logout = async () => { try { await api.logout(); } catch { tokenStore.clear(); } setUser(null); navigate("/login"); };
  if (authLoading) return <div className="loading-screen"><div className="brand-mark">F</div><span className="spinner"/><p>Preparing your workspace…</p></div>;
  if (!user) return <Routes><Route path="/login" element={<Login onLogin={u => { setUser(u); navigate("/"); }}/>} /><Route path="*" element={<Navigate to="/login" replace/>}/></Routes>;

  if (location.pathname === "/login") return <Navigate to={roleHome(user.role)} replace/>;

  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
      <Link to="/" className="brand"><span className="brand-mark"><ShieldCheck size={21}/></span><span>Flow<span className="brand-light">Approve</span></span></Link>
      <div className="workspace-label">WORKSPACE</div>
      <nav className="nav-list" aria-label="Main navigation">
        <NavItem to="/requests" icon={<Files size={18}/>} label="My requests"/>
        {(user.role === "MANAGER" || user.role === "FINANCE" || user.role === "ADMIN") && <NavItem to="/inbox" icon={<ClipboardCheck size={18}/>} label="Approval inbox"/>}
        {user.role === "ADMIN" && <>
          <div className="nav-section">ADMINISTRATION</div>
          <NavItem to="/workflows" icon={<WorkflowIcon size={18}/>} label="Workflow builder"/>
          <NavItem to="/users" icon={<Users size={18}/>} label="Users & audit"/>
        </>}
      </nav>
      <div className="sidebar-bottom">
        <div className="help-card"><span className="help-icon"><CircleHelp size={17}/></span><div><strong>Need a hand?</strong><small>Ask your workspace admin.</small></div></div>
        <div className="sidebar-profile"><Avatar user={user}/><div className="profile-info"><strong>{user.name || user.full_name || user.email.split("@")[0]}</strong><small>{user.role.toLowerCase()}</small></div><button className="icon-button" onClick={logout} title="Sign out" aria-label="Sign out"><LogOut size={17}/></button></div>
      </div>
    </aside>
    {mobileOpen && <button className="mobile-scrim" onClick={() => setMobileOpen(false)} aria-label="Close menu"/>}
    <main className="main-area">
      <header className="topbar">
        <button className="mobile-menu icon-button" onClick={() => setMobileOpen(v => !v)} aria-label="Toggle navigation">{mobileOpen ? <X size={20}/> : <Menu size={20}/>}</button>
        <div className="breadcrumbs"><span>Workspace</span><ChevronRight size={14}/><strong>{pageTitle(location.pathname)}</strong></div>
        <div className="topbar-right"><span className="secure-label"><span className="secure-dot"/> Secure workspace</span><span className="role-badge">{user.role}</span><Avatar user={user}/><button className="button button-secondary button-small topbar-signout" onClick={logout}><LogOut size={15}/> Sign out</button></div>
      </header>
      <div className="page-wrap">
        <ErrorBanner message={error} onClose={() => setError("")}/>
        <Routes>
          <Route path="/" element={<Navigate to={roleHome(user.role)} replace/>} />
          <Route path="/requests" element={<RequestsPage user={user} setError={setError} notify={notify}/>} />
          <Route path="/requests/new" element={<NewRequest setError={setError} notify={notify}/>} />
          <Route path="/requests/:id" element={<RequestDetail user={user} setError={setError} notify={notify}/>} />
          <Route path="/inbox" element={(user.role === "MANAGER" || user.role === "FINANCE" || user.role === "ADMIN") ? <InboxPage setError={setError}/> : <Navigate to={roleHome(user.role)} replace/>} />
          <Route path="/workflows" element={user.role === "ADMIN" ? <WorkflowsPage setError={setError} notify={notify}/> : <Navigate to={roleHome(user.role)} replace/>}/>
          <Route path="/users" element={user.role === "ADMIN" ? <UsersPage user={user} setError={setError} notify={notify}/> : <Navigate to={roleHome(user.role)} replace/>}/>
          <Route path="/audit" element={user.role === "ADMIN" ? <Navigate to="/users?tab=audit" replace/> : <Navigate to={roleHome(user.role)} replace/>}/>
          <Route path="*" element={<Navigate to={roleHome(user.role)} replace/>}/>
        </Routes>
      </div>
      <footer className="footer"><span>FlowApprove</span><span>Every decision. One clear trail.</span></footer>
    </main>
    {toast && <div className="toast" role="status"><CheckCircle2 size={17}/>{toast}</div>}
  </div>;
}
function NavItem({ to, icon, label, end = false }: { to: string; icon: ReactNode; label: string; end?: boolean }) {
  return <NavLink to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`}>{icon}<span>{label}</span>{label === "Approval inbox" && <span className="nav-new-dot"/>}</NavLink>;
}
function pageTitle(path: string) {
  if (path === "/") return "Workspace";
  if (path.startsWith("/requests/new")) return "New request";
  if (path.startsWith("/requests/") && path !== "/requests") return "Request details";
  return ({ "/requests": "My requests", "/inbox": "Approval inbox", "/workflows": "Workflow builder", "/users": "Users", "/audit": "Global audit" } as Record<string,string>)[path] || "Workspace";
}
function PageHeading({ eyebrow, title, subtitle, action }: { eyebrow?: string; title: string; subtitle: string; action?: ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1><p>{subtitle}</p></div>{action && <div className="heading-action">{action}</div>}</div>;
}
function MetricCard({ label, value, detail, icon, tone = "blue" }: { label: string; value: string | number; detail: string; icon: ReactNode; tone?: string }) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon metric-${tone}`}>{icon}</span></div><div className="metric-value">{value}</div><div className="metric-detail">{detail}</div></div>;
}
function Dashboard({ user, setError, notify }: { user: User; setError: (s:string)=>void; notify:(s:string)=>void }) {
  const [requests, setRequests] = useState<ApprovalRequest[]>([]);
  const [inbox, setInbox] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const own = await api.requests(); setRequests(own);
      if (user.role === "MANAGER" || user.role === "FINANCE") setInbox(await api.inbox());
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't load dashboard data."); }
    finally { setLoading(false); }
  }, [setError, user.role]);
  useEffect(() => { load(); }, [load]);
  const pending = requests.filter(r => r.status === "PENDING").length;
  const approved = requests.filter(r => r.status === "APPROVED").length;
  const totalAmount = requests.filter(r => r.status === "APPROVED").reduce((sum,r)=>sum+Number(r.amount||0),0);
  const firstName = (user.name || user.full_name || user.email.split("@")[0]).split(" ")[0];
  return <div className="page-content">
    <PageHeading eyebrow="YOUR WORKSPACE" title={`Good day, ${firstName}`} subtitle="Here’s what’s happening with your requests today." action={<><button className="button button-secondary" onClick={load}><RefreshCw size={16}/> Refresh</button><Link className="button button-primary" to="/requests/new"><Plus size={17}/> New request</Link></>}/>
    <div className="welcome-strip"><div className="welcome-symbol"><Activity size={21}/></div><div><strong>Your approvals, in one place.</strong><p>Follow every request from submission to final decision, with a clear record at every step.</p></div><div className="welcome-art"><span/><span/><span/><span/><span/></div></div>
    <div className="metric-grid">
      <MetricCard label="Total requests" value={loading ? "—" : requests.length} detail="Requests you've submitted" icon={<Files size={19}/>} tone="blue"/>
      <MetricCard label="Awaiting decision" value={loading ? "—" : (user.role === "MANAGER" || user.role === "FINANCE" ? inbox.length : pending)} detail={user.role === "MANAGER" || user.role === "FINANCE" ? "In your approval inbox" : "Currently in progress"} icon={<Clock3 size={19}/>} tone="amber"/>
      <MetricCard label="Approved" value={loading ? "—" : approved} detail="Successfully completed" icon={<CheckCheck size={19}/>} tone="green"/>
      <MetricCard label="Approved value" value={loading ? "—" : money(totalAmount)} detail="Across your approved requests" icon={<WalletCards size={19}/>} tone="violet"/>
    </div>
    <div className="section-grid">
      <section className="panel recent-panel"><div className="panel-header"><div><h2>Recent requests</h2><p>Your latest submissions and their status</p></div><Link to="/requests" className="text-link">View all <ArrowRight size={15}/></Link></div>
        {loading ? <TableSkeleton/> : requests.length === 0 ? <EmptyState title="Nothing here yet" description="Create your first request and track it from this workspace." action={<Link className="button button-primary button-small" to="/requests/new"><Plus size={15}/> Create request</Link>}/> :
        <div className="table-scroll"><table><thead><tr><th>Request</th><th>Amount</th><th>Created</th><th>Status</th><th/></tr></thead><tbody>{requests.slice(0,5).map(r=><tr key={r.id}><td><Link className="request-title" to={`/requests/${r.id}`}>{r.title}</Link><small className="table-sub">REQ-{String(r.id).padStart(4,"0")}</small></td><td className="amount-cell">{money(r.amount)}</td><td>{date(r.submitted_at || r.created_at)}</td><td><StatusBadge status={r.status}/></td><td><Link to={`/requests/${r.id}`} className="table-action" aria-label={`View ${r.title}`}><ChevronRight size={17}/></Link></td></tr>)}</tbody></table></div>}
      </section>
      <section className="panel overview-panel"><div className="panel-header"><div><h2>Quick actions</h2><p>Pick up where you left off</p></div></div>
        <Link to="/requests/new" className="quick-action"><span className="quick-icon quick-blue"><FilePlus2 size={19}/></span><span><strong>Submit a request</strong><small>Start a new approval</small></span><ArrowRight size={16}/></Link>
        <Link to="/requests" className="quick-action"><span className="quick-icon quick-purple"><Files size={19}/></span><span><strong>Track a request</strong><small>See status and progress</small></span><ArrowRight size={16}/></Link>
        {(user.role === "MANAGER" || user.role === "FINANCE") && <Link to="/inbox" className="quick-action"><span className="quick-icon quick-amber"><ClipboardCheck size={19}/></span><span><strong>Review approvals</strong><small>{inbox.length} waiting for your decision</small></span><ArrowRight size={16}/></Link>}
        {user.role === "ADMIN" && <Link to="/workflows" className="quick-action"><span className="quick-icon quick-green"><WorkflowIcon size={19}/></span><span><strong>Manage workflows</strong><small>Configure approval steps</small></span><ArrowRight size={16}/></Link>}
        <div className="mini-note"><ShieldCheck size={17}/><span><strong>Built for accountability</strong><small>Actions are recorded in a permanent audit trail.</small></span></div>
      </section>
    </div>
  </div>;
}
function TableSkeleton() { return <div className="skeleton-wrap">{[1,2,3,4].map(n=><div className="skeleton-row" key={n}><span/><span/><span/></div>)}</div>; }

function RequestsPage({ user, setError, notify }: { user:User; setError:(s:string)=>void; notify:(s:string)=>void }) {
  const [rows,setRows]=useState<ApprovalRequest[]>([]); const [loading,setLoading]=useState(true); const [query,setQuery]=useState(""); const [filter,setFilter]=useState("ALL");
  const load=useCallback(async()=>{setLoading(true);try{setRows(await api.requests());setError("");}catch(e){setError(e instanceof Error?e.message:"Couldn't load requests.");}finally{setLoading(false);}},[setError]);
  useEffect(()=>{load();},[load]);
  const filtered=useMemo(()=>rows.filter(r=>(filter==="ALL"||r.status===filter)&&`${r.title} ${personName(r)} ${r.id}`.toLowerCase().includes(query.toLowerCase())),[rows,filter,query]);
  return <div className="page-content"><PageHeading title="My requests" subtitle="Keep track of the requests you've submitted." action={<Link to="/requests/new" className="button button-primary"><Plus size={17}/> New request</Link>}/>
    <div className="panel"><div className="toolbar"><div className="search-field"><Search size={17}/><input aria-label="Search requests" placeholder="Search requests…" value={query} onChange={e=>setQuery(e.target.value)}/>{query&&<button onClick={()=>setQuery("")} aria-label="Clear search"><X size={14}/></button>}</div><div className="filter-control"><Filter size={16}/><select aria-label="Filter by status" value={filter} onChange={e=>setFilter(e.target.value)}><option value="ALL">All statuses</option><option value="PENDING">Pending</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="DRAFT">Draft</option><option value="CANCELLED">Cancelled</option></select></div><button className="button button-secondary button-small" onClick={load}><RefreshCw size={15}/> Refresh</button></div>
    {loading?<TableSkeleton/>:filtered.length===0?<EmptyState title="No matching requests" description={rows.length?"Try another search or status filter.":"Your submitted requests will appear here."} action={<Link className="button button-primary button-small" to="/requests/new"><Plus size={15}/> New request</Link>}/>:<div className="table-scroll"><table><thead><tr><th>Request</th><th>Workflow</th><th>Amount</th><th>Created</th><th>Status</th><th/></tr></thead><tbody>{filtered.map(r=><tr key={r.id}><td><Link to={`/requests/${r.id}`} className="request-title">{r.title}</Link><small className="table-sub">REQ-{String(r.id).padStart(4,"0")}</small></td><td>{r.workflow_name||(r.workflow_id?`Workflow #${r.workflow_id}`:"—")}</td><td className="amount-cell">{money(r.amount)}</td><td>{date(r.created_at)}</td><td><StatusBadge status={r.status}/></td><td><Link className="table-action" to={`/requests/${r.id}`} aria-label={`Open ${r.title}`}><ChevronRight size={17}/></Link></td></tr>)}</tbody></table></div>}
    <div className="panel-foot"><span>{filtered.length} request{filtered.length===1?"":"s"}</span><span>Showing your accessible requests</span></div></div>
  </div>;
}

function NewRequest({ setError, notify }: { setError:(s:string)=>void; notify:(s:string)=>void }) {
  const navigate=useNavigate(); const [workflows,setWorkflows]=useState<Workflow[]>([]); const [loading,setLoading]=useState(true); const [saving,setSaving]=useState(false);
  const [title,setTitle]=useState(""); const [description,setDescription]=useState(""); const [amount,setAmount]=useState(""); const [workflowId,setWorkflowId]=useState("");
  useEffect(()=>{api.workflows().then(data=>{const active=data.filter(w=>w.is_active!==false&&w.active!==false);setWorkflows(active);if(active[0])setWorkflowId(String(active[0].id));}).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[setError]);
  const submit=async(e:FormEvent)=>{e.preventDefault();if(Number(amount)<=0){setError("Amount must be greater than zero.");return;}if(!workflowId){setError("Choose an active workflow before creating a request.");return;}setSaving(true);setError("");try{const r=await api.createRequest({title:title.trim(),description:description.trim(),amount,workflow_id:workflowId});notify("Draft request created.");navigate(`/requests/${r.id}`);}catch(e){setError(e instanceof Error?e.message:"Couldn't create request.");}finally{setSaving(false);}};
  return <div className="page-content narrow-page"><PageHeading eyebrow="REQUESTS" title="New request" subtitle="Share the details. Your request will follow the selected approval workflow."/>
    <form className="panel form-panel" onSubmit={submit}><div className="form-section-title"><span className="form-section-icon"><FilePlus2 size={18}/></span><div><h2>Request details</h2><p>Be clear and specific so approvers have what they need.</p></div></div>
      <label className="field-label" htmlFor="request-title">Request title <span>*</span></label><input id="request-title" className="text-input" value={title} onChange={e=>setTitle(e.target.value)} placeholder="e.g. Laptop replacement" maxLength={140} required/>
      <div className="field-help">A short summary of what you're requesting.</div>
      <label className="field-label" htmlFor="request-amount">Amount (NGN) <span>*</span></label><div className="money-input"><span>₦</span><input id="request-amount" type="number" min="0.01" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)} placeholder="0.00" required/></div>
      <label className="field-label" htmlFor="request-workflow">Approval workflow <span>*</span></label><select id="request-workflow" className="text-input" value={workflowId} onChange={e=>setWorkflowId(e.target.value)} required disabled={loading||!workflows.length}><option value="">{loading?"Loading workflows…":"Choose a workflow"}</option>{workflows.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select>
      {!loading&&!workflows.length&&<div className="inline-warning"><AlertCircle size={16}/>No active workflows are available. Ask an admin to configure one.</div>}
      <label className="field-label" htmlFor="request-description">Description <span>*</span></label><textarea id="request-description" className="text-input textarea" value={description} onChange={e=>setDescription(e.target.value)} placeholder="Explain why this is needed, what it will be used for, and any relevant context…" rows={5} required/>
      <div className="form-note"><ShieldCheck size={16}/><span>After submission, the approval steps are fixed for this request and each decision is recorded.</span></div>
      <div className="form-actions"><Link to="/requests" className="button button-secondary">Cancel</Link><button className="button button-primary" type="submit" disabled={saving||loading||!workflows.length}>{saving?"Creating…":"Create draft"} <ArrowRight size={16}/></button></div>
    </form>
  </div>;
}
function RequestDetail({ user, setError, notify }: { user:User; setError:(s:string)=>void; notify:(s:string)=>void }) {
  const {id}=useParams(); const navigate=useNavigate(); const [request,setRequest]=useState<ApprovalRequest|null>(null); const [events,setEvents]=useState<AuditEntry[]>([]); const [loading,setLoading]=useState(true); const [comment,setComment]=useState(""); const [busy,setBusy]=useState(false); const [inlineError,setInlineError]=useState("");
  const load=useCallback(async()=>{if(!id)return;setLoading(true);try{const [r,a]=await Promise.all([api.getRequest(id),api.requestAudit(id)]);setRequest(r);setEvents(a);setError("");}catch(e){setRequest(null);setError(e instanceof Error?e.message:"Couldn't load this request.");}finally{setLoading(false);}},[id,setError]);
  useEffect(()=>{load();},[load]);
  const submitAction=async(kind:"submit"|"approve"|"reject"|"cancel")=>{if(!request)return;if(kind==="reject"&&!comment.trim()){setInlineError("Add a reason before rejecting this request.");return;}setBusy(true);setInlineError("");setError("");try{if(kind==="submit")await api.submit(request.id);if(kind==="approve")await api.approve(request.id,comment.trim());if(kind==="reject")await api.reject(request.id,comment.trim());if(kind==="cancel")await api.cancel(request.id);notify(({submit:"Request submitted for approval.",approve:"Approval recorded.",reject:"Request rejected.",cancel:"Request cancelled."})[kind]);setComment("");await load();}catch(e){const message=e instanceof Error?e.message:"This action could not be saved.";if(/already moved on|already been decided|already acted/i.test(message)){setInlineError(message);await load();}else setInlineError(message);}finally{setBusy(false);}};
  if(loading)return <div className="page-content"><TableSkeleton/></div>;
  if(!request)return <div className="page-content"><EmptyState title="Request unavailable" description="This request may not exist or you may not have permission to view it." action={<Link to="/requests" className="button button-primary">Back to requests</Link>}/></div>;
  const steps=request.steps||[]; const submitter=request.submitted_by||request.requester; const submitterId=typeof submitter==="object"&&submitter?submitter.id:undefined; const submitterName=typeof submitter==="string"?submitter:(submitter as User|undefined)?.full_name||(submitter as User|undefined)?.name||request.requester_name||"Team member"; const isSubmitter=String(submitterId??"")===String(user.id); const canSubmit=request.status==="DRAFT"&&isSubmitter; const canCancel=(request.status==="DRAFT"||request.status==="PENDING")&&(isSubmitter||user.role==="ADMIN"); const canDecide=request.status==="PENDING"&&request.can_act===true;
  return <div className="page-content"><button className="back-link" onClick={()=>navigate(-1)}><ArrowDownLeft size={15}/> Back</button><PageHeading eyebrow={`REQ-${String(request.id).padStart(4,"0")}`} title={request.title} subtitle={request.description||"Request details and approval history."} action={<StatusBadge status={request.status}/>}/>
    <div className="detail-grid"><section className="panel detail-main"><div className="detail-summary"><div><span className="detail-label">REQUEST AMOUNT</span><div className="detail-amount">{money(request.amount)}</div></div><div><span className="detail-label">SUBMITTED BY</span><strong>{submitterName}</strong></div><div><span className="detail-label">CREATED</span><strong>{date(request.created_at)}</strong></div></div>
      <div className="panel-subheading"><h2>Approval progress</h2><p>The chain is fixed when the request is submitted.</p></div>
      {steps.length?<div className="timeline">{steps.map((step,i)=>{const state=(step.state||step.status||"").toLowerCase();const done=state==="done"||state==="approved";const current=state==="current"||(!state&&i===request.current_step_index&&request.status==="PENDING");const role=step.role||step.required_role||"MANAGER";return <div className="timeline-item" key={step.order||step.step_order||i}><span className={`timeline-marker ${done?"timeline-done":""}`}>{done?<Check size={14}/>:i+1}</span><div className="timeline-content"><div className="timeline-title"><strong>{step.label||role.toLowerCase().replace("_"," ")}</strong><span className="timeline-state">{done?"Completed":current?"Current step":request.status==="REJECTED"?"Stopped":"Upcoming"}</span></div><p>{step.acted_by||step.actor_name?`Action recorded by ${step.acted_by||step.actor_name}`:current?`Waiting for ${role.toLowerCase()} approval`:"Not started yet"}</p></div></div>})}</div>:<div className="inline-info"><CircleDashed size={17}/> Approval steps have not been provided by the API.</div>}
      {(canSubmit||canDecide||canCancel)&&<div className="decision-panel"><div className="panel-subheading"><h2>{canSubmit?"Submit request":canDecide?"Your decision":"Request actions"}</h2><p>{canSubmit?"Submitting freezes the approval chain.":canDecide?"Your action will be recorded in the audit trail.":"You can cancel a request that has not reached a terminal state."}</p></div>{canDecide&&<><label className="field-label" htmlFor="request-comment">Comment</label><textarea id="request-comment" className="text-input textarea" rows={3} value={comment} onChange={e=>setComment(e.target.value)} placeholder="Add context for your decision…"/><p className="field-help">A rejection requires a comment. An approval comment is optional.</p></>}{inlineError&&<div className="inline-warning" role="alert"><AlertCircle size={16}/>{inlineError}</div>}<div className="decision-actions">{canSubmit&&<button className="button button-primary" disabled={busy} onClick={()=>submitAction("submit")}>{busy?"Submitting…":"Submit for approval"}<ArrowRight size={16}/></button>}{canDecide&&<><button className="button button-danger" disabled={busy} onClick={()=>submitAction("reject")}><XCircle size={16}/> Reject</button><button className="button button-success" disabled={busy} onClick={()=>submitAction("approve")}><Check size={16}/> Approve</button></>}{canCancel&&<button className="button button-secondary" disabled={busy} onClick={()=>submitAction("cancel")}>Cancel request</button>}</div></div>}
    </section><aside className="panel detail-side"><div className="panel-subheading"><h2>Activity history</h2><p>Recorded actions for this request</p></div>{events.length?<div className="audit-list">{events.map((ev,i)=><div className="audit-item" key={ev.id||i}><span className="audit-symbol"><Activity size={15}/></span><div><strong>{(ev.action||"Action").replaceAll("_"," ").toLowerCase()}</strong><p>{ev.actor_name||(typeof ev.actor==="string"?ev.actor:ev.actor?.full_name||ev.actor?.name)||"Team member"}{ev.to_state?` · ${ev.to_state.toLowerCase()}`:""}</p>{ev.comment&&<blockquote>{ev.comment}</blockquote>}<small>{date(ev.created_at||ev.timestamp)}</small></div></div>)}</div>:<EmptyState title="No activity yet" description="Recorded actions will appear here."/>}</aside></div>
  </div>;
}

function InboxPage({ setError }: { setError:(s:string)=>void }) {
  const [rows,setRows]=useState<ApprovalRequest[]>([]); const [loading,setLoading]=useState(true); const [query,setQuery]=useState("");
  const load=useCallback(async()=>{setLoading(true);try{setRows(await api.inbox());setError("");}catch(e){setError(e instanceof Error?e.message:"Couldn't load inbox.");}finally{setLoading(false);}},[setError]);
  useEffect(()=>{load();},[load]);
  const filtered=rows.filter(r=>`${r.title} ${personName(r)} ${r.id}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="page-content"><PageHeading title="Approval inbox" subtitle="Requests waiting for your role. Open one to review the chain, history, and available actions." action={<button className="button button-secondary" onClick={load}><RefreshCw size={16}/> Refresh</button>}/>
    <div className="panel"><div className="toolbar"><div className="search-field"><Search size={17}/><input aria-label="Search inbox" placeholder="Search waiting requests…" value={query} onChange={e=>setQuery(e.target.value)}/></div><span className="toolbar-meta">{rows.length} waiting</span></div>{loading?<TableSkeleton/>:filtered.length===0?<EmptyState title="Nothing waiting for you" description={rows.length?"Try another search term.":"When a request reaches your role, it will appear here."}/>:<div className="table-scroll"><table><thead><tr><th>Request</th><th>Submitted by</th><th>Amount</th><th>Created</th><th>Status</th><th/></tr></thead><tbody>{filtered.map(r=><tr key={r.id}><td><Link to={`/requests/${r.id}`} className="request-title">{r.title}</Link><small className="table-sub">REQ-{String(r.id).padStart(4,"0")}</small></td><td>{personName(r)}</td><td className="amount-cell">{money(r.amount)}</td><td>{date(r.created_at)}</td><td><StatusBadge status={r.status}/></td><td><Link className="table-action" to={`/requests/${r.id}`} aria-label={`Review ${r.title}`}><ChevronRight size={17}/></Link></td></tr>)}</tbody></table></div>}<div className="panel-foot"><span>{filtered.length} request{filtered.length===1?"":"s"}</span><span>Only requests awaiting your role appear here</span></div></div>
  </div>;
}

function WorkflowsPage({ setError, notify }: { setError:(s:string)=>void; notify:(s:string)=>void }) {
  const [rows,setRows]=useState<Workflow[]>([]); const [loading,setLoading]=useState(true); const [showForm,setShowForm]=useState(false); const [editing,setEditing]=useState<Workflow|null>(null); const [name,setName]=useState(""); const [description,setDescription]=useState(""); const [roles,setRoles]=useState<Role[]>(["MANAGER"]); const [busy,setBusy]=useState(false);
  const load=useCallback(async()=>{setLoading(true);try{setRows(await api.workflows());setError("");}catch(e){setError(e instanceof Error?e.message:"Couldn't load workflows.");}finally{setLoading(false);}},[setError]);
  useEffect(()=>{load();},[load]);
  const resetForm=()=>{setShowForm(false);setEditing(null);setName("");setDescription("");setRoles(["MANAGER"]);};
  const startCreate=()=>{setEditing(null);setName("");setDescription("");setRoles(["MANAGER"]);setShowForm(true);};
  const startEdit=(w:Workflow)=>{setEditing(w);setName(w.name);setDescription(w.description||"");setRoles((w.steps||[]).map(s=>s.required_role||s.role).filter((r):r is Role=>r==="MANAGER"||r==="FINANCE"));setShowForm(true);};
  const toggleRole=(role:Role)=>setRoles(prev=>{const next=prev.includes(role)?prev.filter(r=>r!==role):[...prev,role];return (["MANAGER","FINANCE"] as Role[]).filter(r=>next.includes(r));});
  const save=async(e:FormEvent)=>{e.preventDefault();if(!roles.length){setError("Choose at least one approval step.");return;}setBusy(true);setError("");const steps=roles.map((role,i)=>({step_order:i+1,required_role:role,label:role.charAt(0)+role.slice(1).toLowerCase()+" review"}));try{if(editing){await api.updateWorkflow(editing.id,{name:name.trim(),description:description.trim()||null});await api.replaceWorkflowSteps(editing.id,steps);notify("Workflow updated. Requests already in progress keep their original approval chain.");}else{await api.createWorkflow({name:name.trim(),description:description.trim(),steps});notify("Workflow created.");}resetForm();await load();}catch(e){setError(e instanceof Error?e.message:"Couldn't save workflow.");}finally{setBusy(false);}};
  const toggleActive=async(w:Workflow)=>{try{const currentlyActive=w.is_active??w.active??true;const updated=await api.updateWorkflow(w.id,{is_active:!currentlyActive});setRows(prev=>prev.map(item=>item.id===updated.id?updated:item));notify(updated.is_active?"Workflow activated.":"Workflow deactivated.");}catch(e){setError(e instanceof Error?e.message:"Couldn't update workflow status.");}};
  return <div className="page-content"><PageHeading title="Workflow builder" subtitle="Configure the ordered approval chain used by new requests. Changes never alter requests already in progress." action={<button className="button button-primary" onClick={()=>showForm?resetForm():startCreate()}><Plus size={17}/>{showForm?"Close form":"New workflow"}</button>}/>
    {showForm&&<form className="panel workflow-form" onSubmit={save}><div className="form-section-title"><span className="form-section-icon"><WorkflowIcon size={18}/></span><div><h2>{editing?"Edit workflow":"Create workflow"}</h2><p>Steps run in order. Existing requests keep their snapshotted chain.</p></div></div><label className="field-label" htmlFor="workflow-name">Workflow name <span>*</span></label><input className="text-input" id="workflow-name" value={name} onChange={e=>setName(e.target.value)} required placeholder="e.g. Expense approval"/><label className="field-label" htmlFor="workflow-description">Description</label><textarea className="text-input textarea" id="workflow-description" value={description} onChange={e=>setDescription(e.target.value)} rows={2} placeholder="What is this workflow used for?"/><label className="field-label">Approval steps <span>*</span></label><div className="role-options">{(["MANAGER","FINANCE"] as Role[]).map(role=><label className={`role-option ${roles.includes(role)?"role-option-active":""}`} key={role}><input type="checkbox" checked={roles.includes(role)} onChange={()=>toggleRole(role)}/><span className="role-check">{roles.includes(role)&&<Check size={13}/>}</span><span><strong>{role==="MANAGER"?"Manager review":"Finance review"}</strong><small>{role==="MANAGER"?"Line manager approval":"Budget and finance approval"}</small></span></label>)}</div><p className="field-help">The API currently allows Manager and Finance approvers only. Admins configure workflows but cannot approve requests.</p><div className="form-actions"><button type="button" className="button button-secondary" onClick={resetForm}>Cancel</button><button type="submit" className="button button-primary" disabled={busy}>{busy?"Saving…":editing?"Save changes":"Create workflow"}</button></div></form>}
    {loading?<div className="panel"><TableSkeleton/></div>:rows.length===0?<div className="panel"><EmptyState title="No workflows found" description="Create an approval chain to get started." action={<button className="button button-primary button-small" onClick={startCreate}><Plus size={15}/> New workflow</button>}/></div>:<div className="workflow-grid">{rows.map(w=><div className="panel workflow-card" key={w.id}><div className="workflow-card-top"><span className="workflow-symbol"><WorkflowIcon size={19}/></span><span className={`status ${w.is_active===false||w.active===false?"status-cancelled":"status-approved"}`}><span className="status-dot"/>{w.is_active===false||w.active===false?"Inactive":"Active"}</span></div><h2>{w.name}</h2><p>{w.description||"Approval workflow"}</p><div className="workflow-steps">{(w.steps||[]).map((step,i)=><div className="workflow-step" key={step.id||i}><span>{step.step_order||step.order||i+1}</span><div><strong>{step.label||step.required_role||step.role||"Approval step"}</strong><small>{step.required_role||step.role}</small></div>{i<(w.steps||[]).length-1&&<div className="workflow-connector"/>}</div>)}</div><div className="workflow-card-foot"><span><SlidersHorizontal size={14}/> {w.steps?.length||0} steps</span><span>WF-{String(w.id).padStart(3,"0")}</span></div><div className="workflow-card-actions"><button className="button button-secondary button-small" onClick={()=>startEdit(w)}>Edit workflow</button><button className="button button-secondary button-small" onClick={()=>toggleActive(w)}>{w.is_active===false||w.active===false?"Activate":"Deactivate"}</button></div></div>)}</div>}
  </div>;
}
function UsersPage({ user, setError, notify }: { user:User; setError:(s:string)=>void; notify:(s:string)=>void }) {
  const [rows,setRows]=useState<User[]>([]);const [auditRows,setAuditRows]=useState<AuditEntry[]>([]);const [loading,setLoading]=useState(true);const [query,setQuery]=useState("");const [savingId,setSavingId]=useState<string|number|null>(null);const location=useLocation();const navigate=useNavigate();const auditMode=new URLSearchParams(location.search).get("tab")==="audit";
  const load=useCallback(async()=>{setLoading(true);try{const [people,audit]=await Promise.all([api.users(),api.audit()]);setRows(people);setAuditRows(audit);setError("");}catch(e){setError(e instanceof Error?e.message:"Couldn't load admin data.");}finally{setLoading(false);}},[setError]);
  useEffect(()=>{load();},[load]);
  const update=async(target:User,payload:{role?:Role;is_active?:boolean})=>{setSavingId(target.id);try{const updated=await api.updateUser(target.id,payload);setRows(prev=>prev.map(u=>u.id===updated.id?updated:u));notify("User updated.");}catch(e){setError(e instanceof Error?e.message:"Couldn't update user.");}finally{setSavingId(null);}};
  const filtered=rows.filter(u=>`${u.name||u.full_name||""} ${u.email} ${u.role}`.toLowerCase().includes(query.toLowerCase()));
  const filteredAudit=auditRows.filter(a=>`${a.action} ${a.actor_name||""} ${typeof a.actor==="string"?a.actor:a.actor?.full_name||""} ${a.request_id||""} ${a.entity_type||""} ${a.comment||""}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="page-content"><PageHeading title={auditMode?"Global audit":"Users"} subtitle={auditMode?"A chronological, read-only record of workflow, account, and request decisions.":"Manage workspace roles and account access. You cannot change your own role or deactivate yourself."}/><div className="panel"><div className="admin-tabs"><button className={!auditMode?"admin-tab admin-tab-active":"admin-tab"} onClick={()=>{setQuery("");navigate("/users");}}>Users</button><button className={auditMode?"admin-tab admin-tab-active":"admin-tab"} onClick={()=>{setQuery("");navigate("/users?tab=audit");}}>Global audit</button></div><div className="toolbar"><div className="search-field"><Search size={17}/><input placeholder={auditMode?"Search audit events…":"Search users…"} aria-label={auditMode?"Search audit events":"Search users"} value={query} onChange={e=>setQuery(e.target.value)}/></div><span className="toolbar-meta">{auditMode?`${auditRows.length} events`:`${rows.length} users`}</span><button className="button button-secondary button-small" onClick={load}><RefreshCw size={15}/> Refresh</button></div>{loading?<TableSkeleton/>:auditMode?(filteredAudit.length===0?<EmptyState title="No audit events found" description="Events will appear here as the team creates workflows, submits requests, and makes decisions."/>:<div className="table-scroll"><table><thead><tr><th>Action</th><th>Actor</th><th>Record</th><th>Transition</th><th>Date</th></tr></thead><tbody>{filteredAudit.map((a,i)=><tr key={a.id||i}><td><span className="action-cell"><span className="audit-mini"><Activity size={14}/></span><strong>{(a.action||"Action").replaceAll("_"," ")}</strong></span></td><td>{a.actor_name||(typeof a.actor==="string"?a.actor:a.actor?.full_name||a.actor?.name)||"—"}</td><td>{a.request_id?`Request #${a.request_id}`:`${a.entity_type||"Record"} #${a.entity_id??"—"}`}</td><td><span className="transition-text">{a.from_state||"—"} <ArrowRight size={12}/> {a.to_state||"—"}</span></td><td>{date(a.created_at||a.timestamp)}</td></tr>)}</tbody></table></div>):(filtered.length===0?<EmptyState title="No users found" description="Try another search term."/>:<div className="table-scroll"><table><thead><tr><th>User</th><th>Email</th><th>Role</th><th>Account</th></tr></thead><tbody>{filtered.map(u=><tr key={u.id}><td><div className="person-cell"><Avatar user={u}/><strong>{u.full_name||u.name||"Team member"}</strong></div></td><td>{u.email}</td><td><select className="table-select" aria-label={`Role for ${u.email}`} value={u.role} disabled={String(u.id)===String(user.id)||savingId===u.id} onChange={e=>update(u,{role:e.target.value as Role})}><option value="EMPLOYEE">Employee</option><option value="MANAGER">Manager</option><option value="FINANCE">Finance</option><option value="ADMIN">Admin</option></select></td><td><button className={`status-toggle ${u.is_active===false?"status-toggle-off":""}`} disabled={String(u.id)===String(user.id)||savingId===u.id} onClick={()=>update(u,{is_active:u.is_active===false})}>{savingId===u.id?"Saving…":u.is_active===false?"Inactive · Activate":"Active · Deactivate"}</button></td></tr>)}</tbody></table></div>)}<div className="panel-foot"><span>{auditMode?`${filteredAudit.length} events`:`${filtered.length} users`}</span><span>{auditMode?"Audit records are read-only":"Changes are recorded in the global audit trail"}</span></div></div></div>;
}
function AuditPage({ setError }: { setError:(s:string)=>void }) {
  const [rows,setRows]=useState<AuditEntry[]>([]);const [loading,setLoading]=useState(true);const [query,setQuery]=useState("");
  useEffect(()=>{api.audit().then(setRows).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[setError]);
  const filtered=rows.filter(a=>`${a.action} ${a.actor_name||""} ${a.request_title||""} ${a.comment||""}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="page-content"><PageHeading title="Audit trail" subtitle="A chronological record of decisions and changes across the workspace."/><div className="panel"><div className="toolbar"><div className="search-field"><Search size={17}/><input placeholder="Search audit events…" aria-label="Search audit events" value={query} onChange={e=>setQuery(e.target.value)}/></div><span className="toolbar-meta"><ShieldCheck size={15}/> Append-only record</span></div>{loading?<TableSkeleton/>:filtered.length===0?<EmptyState title="No audit events found" description="Events will appear as people submit requests and make decisions."/>:<div className="table-scroll"><table><thead><tr><th>Action</th><th>Actor</th><th>Request</th><th>Transition</th><th>Date</th></tr></thead><tbody>{filtered.map((a,i)=><tr key={a.id||i}><td><span className="action-cell"><span className="audit-mini"><Activity size={14}/></span><strong>{(a.action||"Action").replaceAll("_"," ")}</strong></span></td><td>{a.actor_name||(typeof a.actor==="string"?a.actor:a.actor?.full_name||a.actor?.name)||"—"}</td><td>{a.request_title||"—"}</td><td><span className="transition-text">{a.from_state||"—"} <ArrowRight size={12}/> {a.to_state||"—"}</span></td><td>{date(a.created_at||a.timestamp)}</td></tr>)}</tbody></table></div>}<div className="panel-foot"><span>{filtered.length} event{filtered.length===1?"":"s"}</span><span>Audit records are not editable</span></div></div></div>;
}

function Login({ onLogin }: { onLogin:(user:User)=>void }) {
  const location = useLocation();
  const [email,setEmail]=useState("");const [password,setPassword]=useState("");const [showPassword,setShowPassword]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const submit=async(e:FormEvent)=>{e.preventDefault();setBusy(true);setError("");try{const user=await api.login(email.trim(),password);onLogin(user);}catch(e){setError(e instanceof Error?e.message:"Couldn't sign in. Check your details and try again.");}finally{setBusy(false);}};
  return <div className="login-page"><div className="login-decoration"><div className="login-orbit orbit-one"/><div className="login-orbit orbit-two"/><div className="login-brand"><span className="brand-mark"><ShieldCheck size={21}/></span><span>Flow<span className="brand-light">Approve</span></span></div><div className="login-message"><div className="login-kicker"><span/> CLEAR DECISIONS. REAL ACCOUNTABILITY.</div><h1>Good work<br/>moves forward.</h1><p>One place for requests, approvals, and the decisions that keep your team moving.</p><div className="login-proof"><span><CheckCircle2 size={16}/> Structured approvals</span><span><CheckCircle2 size={16}/> Clear audit trail</span><span><CheckCircle2 size={16}/> Role-based access</span></div></div><div className="login-decoration-foot">FLOWAPPROVE · WORKSPACE</div></div>
    <div className="login-form-area"><form className="login-form" onSubmit={submit}><div className="mobile-login-brand"><span className="brand-mark"><ShieldCheck size={21}/></span><span>Flow<span className="brand-light">Approve</span></span></div><div className="eyebrow">WELCOME BACK</div><h2>Sign in to your workspace</h2><p className="login-intro">Enter your account details to continue.</p>{(error||(location.state as {message?:string}|null)?.message)&&<div className="alert alert-error"><AlertCircle size={16}/>{error||(location.state as {message?:string}|null)?.message}</div>}
      <label className="field-label" htmlFor="email">Email address</label><div className="login-input-wrap"><Users size={17}/><input id="email" type="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="username" placeholder="you@company.com" required/></div>
      <label className="field-label" htmlFor="password">Password</label><div className="login-input-wrap"><ShieldCheck size={17}/><input id="password" type={showPassword?"text":"password"} value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" required/><button type="button" className="show-password" onClick={()=>setShowPassword(v=>!v)}>{showPassword?"Hide":"Show"}</button></div>
      <button className="button button-primary login-submit" type="submit" disabled={busy}>{busy?"Signing in…":"Sign in"} <ArrowRight size={17}/></button>
      <div className="login-security"><ShieldCheck size={15}/> Your session is protected by role-based access.</div>
      <details className="demo-accounts"><summary>Demo account details</summary><p>All demo accounts use password <code>Password123!</code></p><button type="button" onClick={()=>{setEmail("employee1@demo.io");setPassword("Password123!");}}>Employee</button><button type="button" onClick={()=>{setEmail("manager1@demo.io");setPassword("Password123!");}}>Manager</button><button type="button" onClick={()=>{setEmail("finance@demo.io");setPassword("Password123!");}}>Finance</button><button type="button" onClick={()=>{setEmail("admin@demo.io");setPassword("Password123!");}}>Admin</button></details>
    </form><div className="login-bottom">© {new Date().getFullYear()} FlowApprove <span>•</span> Built for teams that need clarity.</div></div>
  </div>;
}
export default App;
