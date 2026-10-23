# Domain & Contracts layer — Person B (Saviour Menebari Peba)

This is my part of the project: the shapes everyone else builds against.
**Nothing here talks to the network, and the state machine talks to nothing
at all** — that is what makes it trustworthy and fast to test.

```
backend/
├── app/
│   ├── models/                  # SQLAlchemy models — storage contract (docs/schema.md)
│   │   ├── __init__.py          # the ONLY import surface: from app.models import ...
│   │   ├── common.py            # utcnow(), created_at column, portable enum column
│   │   ├── user.py              # Role enum + User
│   │   ├── workflow.py          # Workflow
│   │   ├── workflow_step.py     # WorkflowStep (UNIQUE workflow_id+step_order)
│   │   ├── request.py           # RequestStatus + Action enums + Request (+ snapshot helpers)
│   │   └── audit_log.py         # AuditLog + the agreed action vocabulary
│   ├── schemas/                 # Pydantic models — wire contract (docs/technical-spec.md §7)
│   │   ├── common.py            # ApiModel base, UTC timestamps (…Z), ListResponse envelope
│   │   ├── auth.py  user.py  workflow.py  request.py  approval.py  audit.py
│   │   └── __init__.py          # from app.schemas import RequestOut, ...
│   └── state_machine.py         # the 5 legal transitions — pure Python, zero app imports
├── tests/
│   ├── factories.py             # make_user / make_workflow / make_request (nobody hand-builds rows)
│   ├── conftest.py              # db + client + auth_headers fixtures (fresh in-memory DB per test)
│   ├── test_state_machine.py    # EXHAUSTIVE: every state × action + step math + purity probe
│   └── test_integration_happy_path.py  # the demo path through the real API
└── docs/api-examples.md         # the contract as curl (E builds the frontend from these shapes)
```

## Contract map — which doc section each file implements

| Frozen doc section | File(s) |
|---|---|
| schema.md §3 (enums) | `models/user.py` (Role), `models/request.py` (RequestStatus, Action) |
| schema.md §4.5 (snapshot + version rules) | `models/request.py` (`snapshot_from_steps`, `version`, `current_step`) |
| schema.md §4.6 (audit vocabulary) | `models/audit_log.py` (`AuditAction`, `EntityType`) |
| technical-spec.md §4 (state machine) | `state_machine.py` |
| technical-spec.md §5 (casing, money, timestamps, lists) | `schemas/common.py` |
| technical-spec.md §7 (every request/response shape) | `schemas/*` |
| test-plan.md §2 (db, client, auth_headers, factories) | `tests/conftest.py`, `tests/factories.py` |
| test-plan.md §4.1 + §4.8 (my test cases) | `tests/test_state_machine.py`, `tests/test_integration_happy_path.py` |

## How everyone plugs in

- **A** imports `User`, `Role` and registers `models/refresh_token.py` — my
  `models/__init__.py` imports it defensively so the mapper resolves.
- **C** reads transitions ONLY via `state_machine.next_state(...)` and builds
  responses via `RequestOut.build(request, steps=..., can_act=...)` and the
  frozen snapshot via `Request.snapshot_from_steps(workflow.steps)`.
- **D** writes audit rows using the `AuditAction`/`EntityType` vocabulary and
  reads `Request.audit_logs` (already ordered oldest-first).
- **E** builds from `docs/api-examples.md` — the schemas here are that shape.

## Rules this layer enforces for free (no route code needed)

- reject without a comment → 422, message *"A comment is required when rejecting"*
- amount ≤ 0, > 9,999,999,999.99, or blank title → 422
- workflow with 0 steps, duplicate or gapped `step_order` → 422
- emails stored lowercase/trimmed (schema + model backstop); password hash
  appears in no output schema; money serialized as `"450000.00"` strings;
  timestamps as `…Z`

## Running my tests

```bash
cd backend
pytest tests/test_state_machine.py -v     # standalone — no app needed
pytest tests -v                            # everything (needs A/D/C code landed)
```

Dependencies this layer adds on top of D's `requirements.txt`: nothing —
`sqlalchemy>=2`, `pydantic>=2`, `email-validator`, `fastapi`, `httpx`,
`pytest`, `passlib[bcrypt]` are needed by the app anyway.

## Frozen-rule flag for the team

`state_machine.py` and `RequestOut` deliberately know nothing about admin
approval. Per the contracts ("an admin cannot approve a single request",
failure path #12, test-plan §4.5), my happy-path test uses
MANAGER → FINANCE → **MANAGER (a second manager)** instead of the ADMIN
final step sketched in `app-flow.md §4`. That doc inconsistency needs a
one-line decision at standup; code follows the *nobody can manufacture an
approval* rule.
