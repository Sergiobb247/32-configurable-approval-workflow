"""Approval flow — the happy path plus one failure per rule.

Owner: Person C — Approval Engine (Eze Chebem).
Contract: docs/test-plan.md section 4.5, edge cases section 6 (#1–#7, #11).

Every test drives the REAL HTTP surface: real login tokens from `auth_headers`,
real routes, real engine, real database. Nothing is mocked except the workflow
itself, which is created with B's `make_workflow` factory because Person D's
workflow endpoints are a separate part of the product.

The `client` fixture mirrors A's pattern in `test_auth.py`: use Person D's
`app.main:app` when it exists, otherwise mount C's routers on a bare FastAPI
instance so this suite runs standalone before integration.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import factories
from fastapi import HTTPException
from app.database import get_db
from app.models import Action, AuditLog, Request, RequestStatus, Role
from app.routes.approvals import router as approvals_router
from app.routes.auth import router as auth_router
from app.routes.requests import router as requests_router
from app.routes.users import router as users_router
from app.services import workflow_engine as engine


@pytest.fixture()
def client(db):
    """Person D's app when merged; otherwise C's routers on a bare instance."""
    try:
        from app.main import app  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(users_router)
        app.include_router(requests_router)
        app.include_router(approvals_router)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


# --- helpers -----------------------------------------------------------------


def make_chain(db, roles=(Role.MANAGER, Role.FINANCE, Role.MANAGER)):
    """A workflow whose chain is explicit about who acts at each step."""
    return factories.make_workflow(
        db,
        name="Demo chain",
        steps=[(role, f"Step {position + 1}") for position, role in enumerate(roles)],
    )


def create_request(client, headers, workflow, *, title="Laptop", amount="450000.00"):
    response = client.post(
        "/requests",
        json={
            "workflow_id": workflow.id,
            "title": title,
            "description": "demo",
            "amount": amount,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, headers, request_id):
    response = client.post(f"/requests/{request_id}/submit", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def approve(client, headers, request_id, comment="ok"):
    return client.post(
        f"/requests/{request_id}/approve", json={"comment": comment}, headers=headers
    )


def reject(client, headers, request_id, comment="over budget"):
    return client.post(
        f"/requests/{request_id}/reject", json={"comment": comment}, headers=headers
    )


def audit_actions(db, request_id):
    return [
        row.action
        for row in db.query(AuditLog)
        .filter(AuditLog.request_id == request_id)
        .order_by(AuditLog.created_at, AuditLog.id)
        .all()
    ]


# --- happy path ----------------------------------------------------------------


def test_full_chain_approval_ends_approved(db, client, auth_headers):
    workflow = make_chain(db)
    employee = factories.make_user(db, role=Role.EMPLOYEE, email="e1@test.io")
    manager1 = factories.make_user(db, role=Role.MANAGER, email="m1@test.io")
    factories.make_user(db, role=Role.MANAGER, email="m2@test.io")
    factories.make_user(db, role=Role.FINANCE, email="f1@test.io")

    employee_h = auth_headers(email=employee.email)
    manager1_h = auth_headers(email=manager1.email)
    manager2_h = auth_headers(email="m2@test.io")
    finance_h = auth_headers(email="f1@test.io")

    created = create_request(client, employee_h, workflow)
    assert created["status"] == "DRAFT"
    assert created["steps"] == []          # nothing is frozen until submit
    assert created["can_act"] is False     # an employee cannot approve

    submitted = submit(client, employee_h, created["id"])
    assert submitted["status"] == "PENDING"
    assert submitted["current_step_index"] == 0
    assert [step["state"] for step in submitted["steps"]] == ["current", "upcoming", "upcoming"]

    first = approve(client, manager1_h, created["id"])
    assert first.status_code == 200, first.text
    assert first.json()["current_step_index"] == 1

    second = approve(client, finance_h, created["id"])
    assert second.status_code == 200, second.text
    assert second.json()["current_step_index"] == 2

    third = approve(client, manager2_h, created["id"])
    assert third.status_code == 200, third.text
    final = third.json()
    assert final["status"] == "APPROVED"
    assert final["decided_at"] is not None
    assert [step["state"] for step in final["steps"]] == ["done", "done", "done"]

    # The trail is the proof: created, submitted, three approvals.
    assert audit_actions(db, created["id"]) == [
        "REQUEST_CREATED",
        "SUBMITTED",
        "APPROVED",
        "APPROVED",
        "APPROVED",
    ]


# --- rejections -----------------------------------------------------------------


def test_reject_at_second_step_stops_the_chain(db, client, auth_headers):
    workflow = make_chain(db)
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e2@test.io")
    manager_h = auth_headers(role=Role.MANAGER, email="m3@test.io")
    finance_h = auth_headers(role=Role.FINANCE, email="f2@test.io")

    created = create_request(client, employee_h, workflow)
    submit(client, employee_h, created["id"])
    assert approve(client, manager_h, created["id"]).status_code == 200

    rejected = reject(client, finance_h, created["id"], comment="not this quarter")
    assert rejected.status_code == 200, rejected.text
    body = rejected.json()
    assert body["status"] == "REJECTED"
    assert body["current_step_index"] == 1
    assert body["decided_at"] is not None

    # Terminal: the third step never runs, and nothing can move it any more.
    later = approve(client, auth_headers(role=Role.MANAGER, email="m4@test.io"), created["id"])
    assert later.status_code == 409
    assert later.json()["detail"] == "This request has already been decided"


def test_reject_without_comment_is_refused(db, client, auth_headers):
    workflow = make_chain(db, roles=(Role.MANAGER,))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e3@test.io")
    manager_h = auth_headers(role=Role.MANAGER, email="m5@test.io")

    created = create_request(client, employee_h, workflow)
    submit(client, employee_h, created["id"])

    assert client.post(
        f"/requests/{created['id']}/reject", json={}, headers=manager_h
    ).status_code == 422
    assert client.post(
        f"/requests/{created['id']}/reject", json={"comment": "   "}, headers=manager_h
    ).status_code == 422


# --- refusals -------------------------------------------------------------------


def test_wrong_role_approval_is_refused(db, client, auth_headers):
    workflow = make_chain(db, roles=(Role.MANAGER, Role.FINANCE))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e4@test.io")
    finance_h = auth_headers(role=Role.FINANCE, email="f3@test.io")

    created = create_request(client, employee_h, workflow)
    submit(client, employee_h, created["id"])

    refused = approve(client, finance_h, created["id"])
    assert refused.status_code == 403
    assert refused.json()["detail"] == "This request is waiting on another role"


def test_self_approval_is_refused(db, client, auth_headers):
    # An EMPLOYEE step makes the submitter also the required approver.
    workflow = make_chain(db, roles=(Role.EMPLOYEE, Role.MANAGER))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e5@test.io")

    created = create_request(client, employee_h, workflow)
    submit(client, employee_h, created["id"])

    refused = approve(client, employee_h, created["id"])
    assert refused.status_code == 403
    assert refused.json()["detail"] == "You cannot approve your own request"


def test_admin_cannot_approve_anything(db, client, auth_headers):
    workflow = make_chain(db, roles=(Role.MANAGER,))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e6@test.io")
    admin_h = auth_headers(role=Role.ADMIN, email="admin-approver@test.io")

    created = create_request(client, employee_h, workflow)
    submit(client, employee_h, created["id"])

    refused = approve(client, admin_h, created["id"])
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Admins configure workflows; they cannot approve requests"


def test_admin_may_cancel_someone_elses_request(db, client, auth_headers):
    workflow = make_chain(db, roles=(Role.MANAGER,))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e7@test.io")
    admin_h = auth_headers(role=Role.ADMIN, email="admin-cancel@test.io")

    created = create_request(client, employee_h, workflow)
    submit(client, employee_h, created["id"])

    cancelled = client.post(f"/requests/{created['id']}/cancel", headers=admin_h)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
    assert audit_actions(db, created["id"])[-1] == "CANCELLED"


def test_second_approval_with_stale_version_is_refused(db, client, auth_headers):
    """Two approvers, one request: the second must lose cleanly, not overwrite."""
    workflow = make_chain(db, roles=(Role.MANAGER, Role.FINANCE))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e8@test.io")
    manager_h = auth_headers(role=Role.MANAGER, email="m6@test.io")
    finance = factories.make_user(db, role=Role.FINANCE, email="f4@test.io")

    created = create_request(client, employee_h, workflow)
    submit(client, employee_h, created["id"])

    # What the second clicker loaded, before the first one's approval landed.
    seen_version = engine.load_request(db, created["id"]).version
    assert approve(client, manager_h, created["id"]).status_code == 200

    stale = SimpleNamespace(id=created["id"], version=seen_version)
    with pytest.raises(HTTPException) as exc:
        engine.decide(db, finance, stale, Action.APPROVE)

    assert exc.value.status_code == 409
    assert exc.value.detail == "This request already moved to the next step"

    # Exactly one approval for that step; no phantom second audit row.
    assert audit_actions(db, created["id"]).count("APPROVED") == 1


def test_cancel_after_approval_is_refused(db, client, auth_headers):
    workflow = make_chain(db, roles=(Role.MANAGER,))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e9@test.io")
    manager_h = auth_headers(role=Role.MANAGER, email="m7@test.io")

    created = create_request(client, employee_h, workflow)
    submit(client, employee_h, created["id"])
    assert approve(client, manager_h, created["id"]).status_code == 200

    refused = client.post(f"/requests/{created['id']}/cancel", headers=employee_h)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "This request has already been decided"


def test_workflow_with_no_steps_cannot_take_a_request(db, client, auth_headers):
    empty = factories.make_workflow(db, name="Empty", steps=[])
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e10@test.io")

    response = client.post(
        "/requests",
        json={"workflow_id": empty.id, "title": "Nope", "amount": "10.00"},
        headers=employee_h,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "A workflow needs at least one step"


def test_amount_must_be_positive(db, client, auth_headers):
    workflow = make_chain(db, roles=(Role.MANAGER,))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e11@test.io")

    response = client.post(
        "/requests",
        json={"workflow_id": workflow.id, "title": "Zero", "amount": "0.00"},
        headers=employee_h,
    )
    assert response.status_code == 422


# --- inbox ----------------------------------------------------------------------


def test_inbox_shows_who_is_waiting_and_hides_who_already_acted(db, client, auth_headers):
    workflow = make_chain(db, roles=(Role.MANAGER, Role.MANAGER))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="e12@test.io")
    manager1_h = auth_headers(role=Role.MANAGER, email="m8@test.io")
    manager2_h = auth_headers(role=Role.MANAGER, email="m9@test.io")

    created = create_request(client, employee_h, workflow)

    # A draft is nobody's inbox item.
    assert client.get("/inbox", headers=manager1_h).json()["total"] == 0

    submit(client, employee_h, created["id"])

    first_inbox = client.get("/inbox", headers=manager1_h).json()
    assert [item["id"] for item in first_inbox["items"]] == [created["id"]]
    # The submitter never sees their own request in an inbox.
    assert client.get("/inbox", headers=employee_h).json()["total"] == 0

    assert approve(client, manager1_h, created["id"]).status_code == 200

    # Step 2 also needs a manager — but not the one who already acted.
    assert client.get("/inbox", headers=manager1_h).json()["total"] == 0
    second_inbox = client.get("/inbox", headers=manager2_h).json()
    assert [item["id"] for item in second_inbox["items"]] == [created["id"]]


def test_my_requests_lists_only_my_own(db, client, auth_headers):
    workflow = make_chain(db, roles=(Role.MANAGER,))
    employee_a_h = auth_headers(role=Role.EMPLOYEE, email="ea@test.io")
    employee_b_h = auth_headers(role=Role.EMPLOYEE, email="eb@test.io")

    mine = create_request(client, employee_a_h, workflow, title="Mine")
    create_request(client, employee_b_h, workflow, title="Theirs")

    listing = client.get("/requests", headers=employee_a_h).json()
    assert [item["id"] for item in listing["items"]] == [mine["id"]]
    assert listing["total"] == 1


def test_request_detail_is_refused_to_a_stranger(db, client, auth_headers):
    workflow = make_chain(db, roles=(Role.MANAGER,))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="ec@test.io")
    stranger_h = auth_headers(role=Role.EMPLOYEE, email="ed@test.io")

    created = create_request(client, employee_h, workflow)
    refused = client.get(f"/requests/{created['id']}", headers=stranger_h)
    assert refused.status_code == 403
    assert refused.json()["detail"] == "This request belongs to someone else"


def test_step_progress_names_the_actor_who_approved(db, client, auth_headers):
    workflow = make_chain(db, roles=(Role.MANAGER, Role.FINANCE))
    employee_h = auth_headers(role=Role.EMPLOYEE, email="ee@test.io")
    manager = factories.make_user(db, role=Role.MANAGER, email="m10@test.io", full_name="Bola Ade")

    created = create_request(client, employee_h, workflow)
    submit(client, employee_h, created["id"])
    approve(client, auth_headers(email=manager.email), created["id"])

    body = client.get(f"/requests/{created['id']}", headers=employee_h).json()
    assert body["steps"][0]["state"] == "done"
    assert body["steps"][0]["acted_by"] == "Bola Ade"
    assert body["steps"][1]["state"] == "current"
