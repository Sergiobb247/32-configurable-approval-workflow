# FlowApprove frontend

Professional React + Vite frontend for the existing FlowApprove Configurable Approval Workflow API.

The frontend is intentionally adapted to the existing FastAPI contract. **The backend is not modified by this project.** Server-side authorization remains the source of truth.

## Prerequisites

- Node.js 18+
- npm 9+
- The existing FlowApprove FastAPI backend running and reachable from the browser

## Install and run

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Set the backend URL in `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
```

The FastAPI backend must allow the Vite origin (`http://localhost:5173`) through its existing CORS configuration.

## Production build

```bash
npm run build
```

Preview the production build with:

```bash
npm run preview
```

## Application routes

- `/login` — authentication
- `/requests` — My Requests for normal users; All Requests for Admin
- `/requests/new` — create a draft request
- `/requests/:id` — request details, approval progress, and audit history
- `/inbox` — Manager / Finance approval inbox
- `/workflows` — Admin workflow builder
- `/users` — Admin user management and global audit tab

The root route (`/`) redirects to the appropriate landing screen for the signed-in role.

## Supported role behaviour

- **Employee:** creates and tracks their own requests.
- **Manager:** sees the approval inbox when a request reaches a Manager step.
- **Finance:** sees the approval inbox when a request reaches a Finance step.
- **Admin:** manages workflows and users, can view all requests, and can cancel requests when the backend permits it. Admins do **not** approve requests.

The workflow editor only offers Manager and Finance as approval roles because the existing backend explicitly rejects `ADMIN` workflow steps.

## Frontend/API behaviour

- Access tokens are kept in session storage; refresh tokens use the existing refresh-token contract.
- A failed access-token request attempts one coordinated refresh before the session is cleared.
- API errors preserve the backend's human-readable `detail` message.
- Request detail renders the real `steps` returned by the API. Drafts correctly show that the approval snapshot is created when submitted instead of claiming that step data is missing.
- Approval, rejection, submission, cancellation, workflow changes, and user changes only show success after the real API confirms the operation.
- Rejection and cancellation require confirmation because they are terminal actions.
- Stale/conflicting approval actions refresh the authoritative request state after the backend response.

## Demo accounts

The seeded local backend accounts use:

```text
Password123!
```

Typical accounts from the existing seed data include:

```text
employee1@demo.io
manager1@demo.io
finance@demo.io
admin@demo.io
```

## Verification

The final frontend source was checked for TypeScript/JSX syntax with the available TypeScript compiler in this environment. A complete `npm run build` could not be executed here because this uploaded project did not include `node_modules` and package installation could not complete within the available execution window.

To perform the final local verification in VS Code:

```bash
cd frontend
npm install
npm run build
npm run dev
```

Then run the end-to-end role flow against the existing backend:

1. Admin → create/activate a Manager → Finance workflow.
2. Employee → create a draft → submit it.
3. Manager → approve from Inbox.
4. Finance → approve from Inbox.
5. Employee/Admin → open the request and verify the final status and complete audit trail.
6. Confirm Admin has no approval action and cannot be configured as a workflow approver.

## Backend-dependent limitations

- The frontend cannot make an Admin an approver because the existing backend rejects `ADMIN` workflow steps and denies Admin approval actions.
- Request and audit pagination is available through the API; the frontend loads up to 200 records per screen for the current business-scale UI and performs search/filtering client-side.
- The frontend does not invent notification, email, export, or other capabilities that are not provided by the existing backend.
