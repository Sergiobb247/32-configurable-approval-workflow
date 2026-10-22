# FlowApprove frontend

React + Vite frontend for the Configurable Approval Workflow API. The screens follow `APP_FLOW.md`; requests, inbox items, workflow configuration, user changes, and audit entries are loaded from the real API rather than replaced with demo data.

## Run locally

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Set the API URL in `.env`:

```env
VITE_API_URL=http://localhost:8000
```

The FastAPI CORS settings must allow `http://localhost:5173`.

## Role-based landing pages

- **EMPLOYEE** → My Requests
- **MANAGER / FINANCE** → Approval Inbox
- **ADMIN** → Workflow Builder

All authenticated users can open My Requests and a request detail page. The shared request detail view renders approval progress, the audit trail, and only the actions the API says are available (`can_act`). The server remains the authority for access and legal state transitions.

## Included flows

- Create a draft request, then submit it from Request Detail.
- Approve or reject from the shared Request Detail view; rejection requires a comment inline.
- Cancel a non-terminal request when allowed by the API.
- Create, edit, activate, deactivate, and re-chain workflows.
- Change another user's role or active status; self-modification is disabled in the UI.
- View request audit history and the global audit feed (as a tab within Users, keeping the screen map compact).
- Refresh an expired access token once; if refresh fails, clear the session and redirect to Login.
- Display API error details, including permission and conflict errors, instead of mock success states.

## Demo accounts

The seeded demo accounts use `Password123!` locally. The login page has quick-fill options for Employee, Manager, Finance, and Admin.

## Important workflow contract note

The supplied `APP_FLOW.md` demo describes `MANAGER → FINANCE → ADMIN`, with Admin approving the final step. The current backend explicitly rejects workflows containing an `ADMIN` approval step and says admins configure workflows but cannot approve requests. The frontend follows the backend's enforceable contract and currently offers Manager and Finance as approver roles. To make the Admin-final-approval demo work, the product flow and backend permissions must be reconciled before enabling an Admin step in the UI; otherwise the form would advertise a workflow the API rejects.

## Verification

Run `npm run build` after installing dependencies. The source files were syntax-checked in this environment, but a full build could not be completed here because `npm install` could not finish fetching packages.

