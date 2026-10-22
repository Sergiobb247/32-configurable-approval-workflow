"""API tests for workflow configuration (Endpoints 8–12).

Owner: Person D — Workflows, Audit & Ops (Moses Abigail).
Contract: docs/test-plan.md §4.6, §6 (#4, #5), docs/technical-spec.md §7.3,
docs/prd.md US-10, US-11.

Naming convention: `test_<behaviour>_<condition>_<expected>` (test-plan.md §2).
Uses the shared `db` / `client` / `auth_headers` fixtures (Person B) against
the real app shell (`app.main:app`, Person D) and the real login endpoint
(Person A) — no auth is faked anywhere in these tests.
"""

from __future__ import annotations

import factories
from app.models import AuditLog, Request, Role, Workflow
from app.routes.workflows import ADMIN_STEP_DETAIL

CHAIN = [
    {"step_order": 1, "required_role": "MANAGER", "label": "Line manager"},
    {"step_order": 2, "required_role": "FINANCE", "label": "Finance review"},
    {"step_order": 3, "required_role": "MANAGER", "label": "Second manager"},
]


def test_create_workflow_when_admin_with_three_steps_returns_201_ordered(
    db, client, auth_headers
):
    admin_h = auth_headers(role=Role.ADMIN)

    response = client.post(
        "/workflows",
        json={
            "name": "Expense approval (> ₦100,000)",
            "description": "Manager, then finance, then a second manager",
            # Sent out of order on purpose: storage must follow step_order.
            "steps": [CHAIN[1], CHAIN[2], CHAIN[0]],
        },
        headers=admin_h,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Expense approval (> ₦100,000)"
    assert body["is_active"] is True
    assert [s["step_order"] for s in body["steps"]] == [1, 2, 3]
    assert [s["required_role"] for s in body["steps"]] == [
        "MANAGER",
        "FINANCE",
        "MANAGER",
    ]

    # Creation is audited by the one writer, in the same transaction (§2).
    rows = db.query(AuditLog).filter_by(action="WORKFLOW_CREATED").all()
    assert len(rows) == 1
    assert rows[0].entity_type == "workflow"
    assert rows[0].entity_id == body["id"]
    assert rows[0].request_id is None


def test_create_workflow_when_employee_returns_403(client, auth_headers):
    employee_h = auth_headers(role=Role.EMPLOYEE)

    response = client.post(
        "/workflows",
        json={"name": "Sneaky workflow", "steps": CHAIN},
        headers=employee_h,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Your role cannot do this"


def test_create_workflow_when_zero_steps_returns_422(client, auth_headers):
    admin_h = auth_headers(role=Role.ADMIN)

    response = client.post(
        "/workflows",
        json={"name": "Empty chain", "steps": []},
        headers=admin_h,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "A workflow needs at least one step"


def test_create_workflow_when_duplicate_step_order_returns_422(
    client, auth_headers
):
    admin_h = auth_headers(role=Role.ADMIN)

    response = client.post(
        "/workflows",
        json={
            "name": "Duplicated position",
            "steps": [
                {"step_order": 1, "required_role": "MANAGER", "label": "First"},
                {"step_order": 1, "required_role": "FINANCE", "label": "Also first"},
            ],
        },
        headers=admin_h,
    )

    assert response.status_code == 422
    assert "unique" in response.json()["detail"]


def test_create_workflow_when_step_requires_admin_returns_422(
    db, client, auth_headers
):
    # Agreed by Persons A and B, enforced by Person D: an admin can NEVER
    # approve, at any step, ever. A chain that asks one to would deadlock
    # with a request waiting forever, so it cannot even be saved.
    admin_h = auth_headers(role=Role.ADMIN)

    response = client.post(
        "/workflows",
        json={
            "name": "Impossible chain",
            "steps": [
                {"step_order": 1, "required_role": "MANAGER", "label": "Line manager"},
                {"step_order": 2, "required_role": "ADMIN", "label": "Admin sign-off"},
                {"step_order": 3, "required_role": "FINANCE", "label": "Finance review"},
            ],
        },
        headers=admin_h,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == ADMIN_STEP_DETAIL
    assert response.json()["detail"].endswith(
        "admins configure workflows; they cannot approve requests"
    )
    # Nothing was persisted and nothing was audited for the refused config.
    assert db.query(Workflow).count() == 0
    assert db.query(AuditLog).filter_by(action="WORKFLOW_CREATED").count() == 0


def test_replace_steps_when_step_requires_admin_returns_422_and_keeps_old_chain(
    db, client, auth_headers
):
    workflow = factories.make_workflow(
        db,
        steps=((Role.MANAGER, "Line manager"), (Role.FINANCE, "Finance review")),
    )

    response = client.post(
        f"/workflows/{workflow.id}/steps",
        json={
            "steps": [
                {"step_order": 1, "required_role": "ADMIN", "label": "Admin sign-off"}
            ]
        },
        headers=auth_headers(role=Role.ADMIN),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == ADMIN_STEP_DETAIL

    # The guard runs before the old chain is touched: no half-written config.
    db.refresh(workflow)
    assert [(s.step_order, s.required_role) for s in workflow.steps] == [
        (1, Role.MANAGER),
        (2, Role.FINANCE),
    ]


def test_activate_workflow_when_step_requires_admin_returns_422(
    db, client, auth_headers
):
    # A legacy/factory row can hold an ADMIN step while inactive; the PATCH
    # guard is what stops it from ever going live and trapping a request.
    impossible = factories.make_workflow(
        db,
        steps=((Role.MANAGER, "Line manager"), (Role.ADMIN, "Admin sign-off")),
        is_active=False,
    )

    response = client.patch(
        f"/workflows/{impossible.id}",
        json={"is_active": True},
        headers=auth_headers(role=Role.ADMIN),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == ADMIN_STEP_DETAIL

    db.refresh(impossible)
    assert impossible.is_active is False


def test_activate_workflow_when_no_steps_returns_422(db, client, auth_headers):
    # Factories may build an (inactive) zero-step workflow on purpose; the
    # API itself can never create one. The PATCH guard is what stops such a
    # row from ever going live (test-plan §4.6).
    empty = factories.make_workflow(db, steps=(), is_active=False)
    admin_h = auth_headers(role=Role.ADMIN)

    response = client.patch(
        f"/workflows/{empty.id}",
        json={"is_active": True},
        headers=admin_h,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "A workflow needs at least one step"

    db.refresh(empty)
    assert empty.is_active is False


def test_edit_workflow_when_request_in_flight_does_not_change_its_snapshot(
    db, client, auth_headers
):
    # US-11 / the snapshot rule: an in-flight request follows the chain it
    # was submitted with, even after an admin rewrites the live workflow.
    workflow = factories.make_workflow(
        db,
        steps=((Role.MANAGER, "Line manager"), (Role.FINANCE, "Finance review")),
    )
    in_flight = factories.make_request(
        db, workflow=workflow, status="PENDING", current_step_index=0
    )
    frozen_before = [dict(step) for step in in_flight.steps_snapshot]

    admin_h = auth_headers(role=Role.ADMIN)
    response = client.post(
        f"/workflows/{workflow.id}/steps",
        json={
            "steps": [
                {"step_order": 1, "required_role": "FINANCE", "label": "Finance first"},
            ]
        },
        headers=admin_h,
    )
    assert response.status_code == 200, response.text
    assert [s["required_role"] for s in response.json()["steps"]] == ["FINANCE"]

    refreshed = db.get(Request, in_flight.id)
    assert [dict(step) for step in refreshed.steps_snapshot] == frozen_before
    assert [(s["order"], s["role"]) for s in refreshed.steps_snapshot] == [
        (1, "MANAGER"),
        (2, "FINANCE"),
    ]


def test_list_workflows_when_non_admin_shows_active_only(
    db, client, auth_headers
):
    factories.make_workflow(db, name="Live workflow", is_active=True)
    factories.make_workflow(db, name="Retired workflow", is_active=False)

    employee_res = client.get("/workflows", headers=auth_headers(role=Role.EMPLOYEE))
    assert employee_res.status_code == 200
    assert [w["name"] for w in employee_res.json()["items"]] == ["Live workflow"]
    assert employee_res.json()["total"] == 1

    admin_res = client.get("/workflows", headers=auth_headers(role=Role.ADMIN))
    assert admin_res.status_code == 200
    assert admin_res.json()["total"] == 2


def test_get_workflow_when_unknown_id_returns_404(client, auth_headers):
    response = client.get(
        "/workflows/999999", headers=auth_headers(role=Role.ADMIN)
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow not found"


def test_get_inactive_workflow_when_non_admin_returns_404(
    db, client, auth_headers
):
    retired = factories.make_workflow(db, name="Retired", is_active=False)

    response = client.get(
        f"/workflows/{retired.id}", headers=auth_headers(role=Role.EMPLOYEE)
    )

    assert response.status_code == 404


def test_patch_workflow_when_non_admin_returns_403(db, client, auth_headers):
    workflow = factories.make_workflow(db)

    response = client.patch(
        f"/workflows/{workflow.id}",
        json={"name": "Renamed by a manager"},
        headers=auth_headers(role=Role.MANAGER),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Your role cannot do this"


def test_patch_workflow_when_admin_updates_fields_and_audits(
    db, client, auth_headers
):
    workflow = factories.make_workflow(db, name="Old name")

    response = client.patch(
        f"/workflows/{workflow.id}",
        json={"name": "New name", "is_active": False},
        headers=auth_headers(role=Role.ADMIN),
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "New name"
    assert response.json()["is_active"] is False
    assert (
        db.query(AuditLog)
        .filter_by(action="WORKFLOW_UPDATED", entity_id=workflow.id)
        .count()
        == 1
    )


def test_list_workflows_when_unauthenticated_returns_401(client):
    response = client.get("/workflows")

    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in again"
