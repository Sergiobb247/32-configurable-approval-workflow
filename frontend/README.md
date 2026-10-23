# FlowApprove frontend

React + Vite + TypeScript frontend for the FlowApprove Configurable Approval Workflow API.

**The backend is not modified by this project.** Server-side authorization remains the source of
truth; the UI only reflects what the API allows.

## Prerequisites

- Node.js 18+
- npm 9+
- The FastAPI backend running (default `http://127.0.0.1:8000`)

## Install and run

```bash
cd backend && python -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python seed.py                      # demo data (idempotent)
./.venv/bin/uvicorn app.main:app --port 8000    # API on :8000

cd ../frontend
npm install
npm run dev                                     # app on :5173
```

> **Re-seeding:** stop the API first. SQLite keeps an open handle to `app.db`, so deleting that file
> underneath a running server leaves it writing to a deleted inode — every write then fails with
> `attempt to write a readonly database` and the UI shows the generic
> "Something went wrong on our side". The sequence is `Ctrl-C` → `rm app.db` → `seed.py` → start the
> API again. The file on disk is fine; only the running process is stale.

### How the app reaches the API

By default the browser calls **`/api`** on the same origin, and the Vite dev server proxies
`/api/*` to `http://127.0.0.1:8000/*` (`vite.config.ts`). That means:

- no CORS configuration is needed for local development, and
- no backend hostname is baked into the bundle.

To call a deployed API directly instead, create `frontend/.env`:

```env
VITE_API_URL=https://your-api-host.example.com
```

In that case the API's `CORS_ORIGINS` must include the frontend origin.

`server.allowedHosts: true` is set in `vite.config.ts` so the app also loads through a tunnel or
preview host, which Vite's default host check would otherwise reject with `403`.

## Production build

```bash
npm run build     # tsc --noEmit + vite build -> dist/
npm run preview   # serve dist/ locally (also proxies /api)
```

`dist/` is a static bundle: host it anywhere and point it at the API with `VITE_API_URL` at build
time, or reverse-proxy `/api` to the backend so the default same-origin path keeps working.

## Application routes

| Route | Who | Purpose |
|---|---|---|
| `/login` | public | Sign in; shows API health and demo accounts |
| `/register` | public | Create an account (`POST /auth/register`, lands as `EMPLOYEE`) |
| `/requests` | all | Own requests; **all** requests for an Admin |
| `/requests/new` | all | Create a draft against an active workflow |
| `/requests/:id` | those who may see it | Chain progress, audit timeline, and the actions available to you |
| `/inbox` | Manager, Finance | Requests waiting on *your role* |
| `/workflows` | Admin | Workflow builder: create, edit chain, activate/deactivate, details |
| `/users` | Admin | Users tab + Global audit tab (`/users?tab=audit`) |
| `/audit` | Admin | Alias that redirects to the Global audit tab |

`/` redirects each role to its landing screen. Unauthorised routes redirect to that landing screen;
the API still enforces every rule independently.

## Backend endpoint coverage

Every endpoint the API exposes is reachable from the UI.

| # | Endpoint | Where it is used |
|---|---|---|
| 1 | `POST /auth/register` | `/register` |
| 2 | `POST /auth/login` | `/login` |
| 3 | `POST /auth/refresh` | Automatic, one coordinated retry on `401` |
| 4 | `POST /auth/logout` | Sign out (both in sidebar and top bar) |
| 5 | `GET /auth/me` | Session restore on page load |
| 6 | `GET /users` | Users tab, and the "who submitted this" data |
| 7 | `PATCH /users/{id}` | Role select and activate/deactivate in Users tab |
| 8 | `GET /workflows` | Workflow builder, and the workflow picker on `/requests/new` |
| 9 | `POST /workflows` | "New workflow" form |
| 10 | `GET /workflows/{id}` | Workflow "Details" dialog; resolves the workflow name on a request |
| 11 | `PATCH /workflows/{id}` | Rename/redescribe on edit, activate/deactivate button |
| 12 | `POST /workflows/{id}/steps` | Editing the ordered chain |
| 13 | `POST /requests` | "Create draft" |
| 14 | `GET /requests` | `/requests` (status filter sent to the API as `?status=`) |
| 15 | `GET /requests/{id}` | Request detail |
| 16 | `POST /requests/{id}/submit` | "Submit for approval" |
| 17 | `POST /requests/{id}/cancel` | "Cancel request" (confirmed) |
| 18 | `GET /inbox` | Approval inbox + the live sidebar badge |
| 19 | `POST /requests/{id}/approve` | "Approve" with optional comment |
| 20 | `POST /requests/{id}/reject` | "Reject" — comment enforced client-side too |
| 21 | `GET /requests/{id}/audit` | Activity history on the request detail |
| 22 | `GET /audit` | Global audit tab, filterable by record type |
| 23 | `GET /health` | Sidebar API status pill (60s poll + on focus + click to retry) |

## Behaviour worth knowing

- **Session:** the access/refresh pair is stored as ONE atomic record, so the two tokens can never
  drift apart. Every storage read and write is guarded and mirrored in memory, because Web Storage
  can *throw* (SecurityError) in Safari private mode, when storage is disabled, and inside a
  sandboxed iframe — a signed-in session must not depend on that.
- **Refresh:** the access token is checked against its own `exp` before each request, so a restored
  session refreshes **proactively** instead of provoking a 401. Any 401 triggers exactly one shared
  refresh (refresh tokens are single-use, so parallel refreshes would kill the session).
- **Never signed out by accident:** only an authentication rejection (401/403) clears the session.
  A transport failure or a 5xx from whatever proxies the API shows a "Can't reach the API" screen
  with **Try again** and keeps your tokens. A cold start with a stale token returns to the login
  form *silently* — "your session expired" is only shown if a live session actually dies.
- **Confirmations are in-app, not `window.confirm`.** Native dialogs are silently suppressed in
  sandboxed iframes and many embedded webviews (they return `false` without rendering), which made
  Reject / Cancel / Deactivate appear to do nothing. Every terminal action now opens a real dialog.
- **Errors:** the API's human-readable `detail` sentence is always the thing shown to the user.
  A failed sign-in also probes `GET /health` to distinguish "the API is down" from "wrong password".
- **Success is never optimistic:** approve/reject/submit/cancel/workflow/user changes only report
  success after the API confirms, and the page re-reads authoritative state afterwards.
- **Status filtering** on `/requests` uses the API's `status` query parameter, so the footer count is
  the server's total for that filter, not a page-local guess.
- **Pagination:** lists load up to the API maximum (200 rows) and page client-side with 10/25/50/100
  rows per page.
- **Drafts** correctly show that the step snapshot is created when the request is submitted.
- **Terminal actions** (reject, cancel, deactivate workflow) ask for confirmation first.
- **Admins do not approve.** The workflow editor only offers Manager and Finance because the API
  rejects `ADMIN` steps with `422`; the UI states that rule rather than letting you discover it.
- **Self-service protection:** your own row in the Users tab has role/status controls disabled,
  because the API refuses self-modification with `409`.

## Demo accounts

Seeded accounts all use the password `Password123!`:

```text
admin@demo.io      manager1@demo.io     manager2@demo.io
finance@demo.io    employee1@demo.io    employee2@demo.io
```

The login screen has one-click buttons for the first four.

## Verified end-to-end

The following flow was exercised in a real browser against a live backend:

1. Employee signs in, creates a draft, submits it → chain snapshot appears, status `PENDING`.
2. Manager sees it in the inbox (badge count matches), approves with a comment → step 1 `Completed`.
3. Finance sees it next, approves → step 2 `Completed`, waiting on the second manager.
4. Second manager approves → `APPROVED`, `DECIDED` timestamp, full audit trail.
5. Rejection path: reject without a comment is blocked client-side; with a comment the chain stops,
   the step reads "Rejected here", and the comment appears in the timeline.
6. Cancellation path: confirm in the in-app dialog, then cancel → `CANCELLED` with an audit entry.
7. Admin creates a workflow with a two-step chain, reorders its steps, renames it, opens the Details
   dialog, deactivates it via the confirmation dialog (and "Keep it open" provably cancels), and
   reads the global audit with the record-type filter.
8. Admin changes another user's role → toast confirms, audit gains a `USER_ROLE_CHANGED` row.
9. `POST /auth/register` creates an account that can sign in immediately and lands on `/requests`.

Robustness checks, run deliberately:

10. **Storage blocked** — `localStorage` and `sessionStorage` redefined to throw `SecurityError`;
    sign-in still succeeds and the app runs normally.
11. **Expired access token + valid refresh token** — reload silently calls `POST /auth/refresh`
    and the session continues. No sign-out, no banner.
12. **Backend down** — reload shows "Can't reach the API" with the session intact; **Try again**
    reconnects to the same session once the API is back.
13. **Stale/garbage tokens** — returns to the login screen with no scary message and clears the pair.
14. `npm run build` succeeds (TypeScript strict + Vite).

## Backend-dependent limitations (not frontend gaps)

- An Admin cannot be an approver: the API rejects `ADMIN` workflow steps (`422`) and denies Admin
  approve/reject (`403`). The UI reflects that rule.
- There is no notification, email, export, or attachment capability in the API, so the frontend does
  not pretend to offer one.
- Audit records are append-only — every screen is read-only for audit by design.
