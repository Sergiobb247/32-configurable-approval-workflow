"""API tests for admin user management (Endpoints 6–7).

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/test-plan.md §4.4, §6 (#10), docs/technical-spec.md §7.2, US-13.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import factories
from app.database import get_db
from app.models import Role
from app.routes.auth import router as auth_router
from app.routes.users import router as users_router


@pytest.fixture()
def client(db):
    """Use Person D's `app.main:app` once merged; otherwise mount A's routers on
    a minimal FastAPI instance so Part A tests run standalone on Day 1."""
    try:
        from app.main import app  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(users_router)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role", [Role.EMPLOYEE, Role.MANAGER, Role.FINANCE])
def test_list_users_when_non_admin_returns_403(auth_headers, client, role):
    headers = auth_headers(role=role)

    response = client.get("/users", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Your role cannot do this"


def test_patch_user_when_non_admin_returns_403(db, auth_headers, client):
    target = factories.make_user(db, email="target@demo.io", role=Role.EMPLOYEE)
    manager_headers = auth_headers(role=Role.MANAGER)

    response = client.patch(
        f"/users/{target.id}",
        json={"role": "FINANCE"},
        headers=manager_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Your role cannot do this"


def test_admin_changes_role_persists_and_appears_immediately_in_me(
    db, auth_headers, client
):
    employee = factories.make_user(
        db,
        email="promote.me@demo.io",
        role=Role.EMPLOYEE,
        full_name="Ada Obi",
    )
    employee_headers = auth_headers(email=employee.email)
    admin_headers = auth_headers(role=Role.ADMIN)

    patch_res = client.patch(
        f"/users/{employee.id}",
        json={"role": "FINANCE"},
        headers=admin_headers,
    )
    assert patch_res.status_code == 200, patch_res.text
    assert patch_res.json()["role"] == "FINANCE"

    # Existing access token immediately sees updated role from DB (US-13)
    me_res = client.get("/auth/me", headers=employee_headers)
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "FINANCE"

    # Also reflected in admin's paginated user list
    list_res = client.get("/users?skip=0&limit=50", headers=admin_headers)
    assert list_res.status_code == 200
    body = list_res.json()
    assert body["total"] >= 2
    matching = [u for u in body["items"] if u["id"] == employee.id]
    assert len(matching) == 1
    assert matching[0]["role"] == "FINANCE"


def test_admin_deactivating_or_demoting_self_returns_409(db, auth_headers, client):
    admin = factories.make_user(
        db,
        email="self.admin@demo.io",
        role=Role.ADMIN,
    )
    admin_headers = auth_headers(email=admin.email)

    demote_res = client.patch(
        f"/users/{admin.id}",
        json={"role": "EMPLOYEE"},
        headers=admin_headers,
    )
    assert demote_res.status_code == 409

    deactivate_res = client.patch(
        f"/users/{admin.id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate_res.status_code == 409


def test_admin_deactivating_user_invalidates_live_access_and_refresh_tokens(
    db, auth_headers, client
):
    victim = factories.make_user(
        db,
        email="active.employee@demo.io",
        password="Password123!",
        role=Role.EMPLOYEE,
    )
    login_body = client.post(
        "/auth/login",
        json={"email": victim.email, "password": "Password123!"},
    ).json()
    admin_headers = auth_headers(role=Role.ADMIN)

    patch_res = client.patch(
        f"/users/{victim.id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_active"] is False

    # Live access token is rejected on the very next request
    me_res = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login_body['access_token']}"},
    )
    assert me_res.status_code == 401
    assert me_res.json()["detail"] == "Please sign in again"

    # Existing refresh token is also rejected
    refresh_res = client.post(
        "/auth/refresh",
        json={"refresh_token": login_body["refresh_token"]},
    )
    assert refresh_res.status_code == 401


def test_patch_unknown_user_returns_404(auth_headers, client):
    admin_headers = auth_headers(role=Role.ADMIN)

    response = client.patch(
        "/users/999999",
        json={"role": "MANAGER"},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"
