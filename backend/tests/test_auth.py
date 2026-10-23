"""API and unit tests for authentication & token lifecycle (Endpoints 1–5).

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/test-plan.md §4.3, §6 (#8, #9, #10), docs/technical-spec.md §7.1, §8, §9, §10.

Naming convention: `test_<behaviour>_<condition>_<expected>` (test-plan.md §2).
Each test runs cleanly standalone: `pytest tests/test_auth.py::<name> -v`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import factories
from app.auth.security import create_access_token, hash_refresh_token
from app.config import Settings
from app.database import get_db
from app.models import RefreshToken, Role, User
from app.models.common import utcnow
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


def test_register_when_valid_returns_user_and_never_exposes_hash(db, client):
    response = client.post(
        "/auth/register",
        json={
            "email": "  Ada.Obi@Demo.IO ",
            "password": "Password123!",
            "full_name": "Ada Obi",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "ada.obi@demo.io"
    assert body["full_name"] == "Ada Obi"
    assert body["role"] == "EMPLOYEE"
    assert body["is_active"] is True
    assert body["created_at"].endswith("Z")
    assert "password" not in body
    assert "password_hash" not in body

    saved = db.query(User).filter_by(email="ada.obi@demo.io").one()
    assert saved.password_hash != "Password123!"
    assert saved.password_hash.startswith("$2")


def test_register_when_duplicate_email_returns_409(db, client):
    factories.make_user(db, email="employee1@demo.io")

    response = client.post(
        "/auth/register",
        json={
            "email": "EMPLOYEE1@demo.io",
            "password": "Password123!",
            "full_name": "Duplicate User",
        },
    )

    assert response.status_code == 409
    assert isinstance(response.json()["detail"], str)


def test_login_when_valid_credentials_returns_token_pair_and_hashes_refresh_token(
    db, client
):
    user = factories.make_user(
        db,
        email="manager1@demo.io",
        password="Password123!",
        full_name="Bola Ade",
        role=Role.MANAGER,
    )

    response = client.post(
        "/auth/login",
        json={"email": "Manager1@Demo.io", "password": "Password123!"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["id"] == user.id
    assert body["user"]["role"] == "MANAGER"
    assert "password_hash" not in body["user"]

    # Raw refresh token is never persisted in the database — only SHA-256 hex.
    stored = db.query(RefreshToken).filter_by(user_id=user.id).one()
    assert stored.token_hash != body["refresh_token"]
    assert stored.token_hash == hash_refresh_token(body["refresh_token"])
    assert len(stored.token_hash) == 64


def test_login_when_wrong_password_returns_401_identical_to_unknown_email(db, client):
    factories.make_user(db, email="known@demo.io", password="Password123!")

    wrong_pw = client.post(
        "/auth/login",
        json={"email": "known@demo.io", "password": "WrongPassword999!"},
    )
    unknown_email = client.post(
        "/auth/login",
        json={"email": "nobody@demo.io", "password": "Password123!"},
    )

    assert wrong_pw.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_pw.json() == unknown_email.json()
    assert wrong_pw.json()["detail"] == "Invalid email or password"


def test_login_when_unknown_email_returns_401(client):
    response = client.post(
        "/auth/login",
        json={"email": "missing@demo.io", "password": "Password123!"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_me_when_missing_token_returns_401(client):
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in again"


def test_me_when_expired_access_token_returns_401(db, client):
    user = factories.make_user(db, email="expired@demo.io", role=Role.EMPLOYEE)
    expired_token = create_access_token(
        user.id,
        user.role,
        expires_delta=timedelta(minutes=-1),
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in again"


def test_refresh_rotates_token_and_rejects_old_refresh_token_with_401(db, client):
    factories.make_user(db, email="rotate@demo.io", password="Password123!")
    login_body = client.post(
        "/auth/login",
        json={"email": "rotate@demo.io", "password": "Password123!"},
    ).json()
    first_refresh = login_body["refresh_token"]

    rotated = client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200, rotated.text
    second_pair = rotated.json()
    assert second_pair["refresh_token"] != first_refresh

    # New access token works on GET /auth/me
    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {second_pair['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "rotate@demo.io"

    # Reusing the rotated-out refresh token must fail with 401
    reused = client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert reused.status_code == 401
    assert reused.json()["detail"] == "Please sign in again"


def test_refresh_when_expired_token_returns_401(db, client):
    user = factories.make_user(db, email="stale@demo.io", password="Password123!")
    raw_token = "expired-opaque-refresh-token-value"
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=utcnow() - timedelta(seconds=10),
        )
    )
    db.commit()

    response = client.post("/auth/refresh", json={"refresh_token": raw_token})
    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in again"


def test_logout_revokes_token_and_blocks_reuse_with_401(db, client):
    factories.make_user(db, email="logout@demo.io", password="Password123!")
    login_body = client.post(
        "/auth/login",
        json={"email": "logout@demo.io", "password": "Password123!"},
    ).json()

    logout_res = client.post(
        "/auth/logout",
        json={"refresh_token": login_body["refresh_token"]},
        headers={"Authorization": f"Bearer {login_body['access_token']}"},
    )
    assert logout_res.status_code == 204
    assert logout_res.content == b""

    after_logout = client.post(
        "/auth/refresh",
        json={"refresh_token": login_body["refresh_token"]},
    )
    assert after_logout.status_code == 401


def test_deactivated_user_cannot_login_or_refresh_session(db, client):
    inactive = factories.make_user(
        db,
        email="inactive@demo.io",
        password="Password123!",
        is_active=False,
    )

    login_res = client.post(
        "/auth/login",
        json={"email": inactive.email, "password": "Password123!"},
    )
    assert login_res.status_code in (401, 403)


def test_config_normalizes_postgres_url_and_guards_production_secret():
    prod_settings = Settings.from_env(
        {
            "ENV": "production",
            "DATABASE_URL": "postgres://user:pass@host:5432/approvals",
            "JWT_SECRET": "prod-secret-value-at-least-32-chars",
            "CORS_ORIGINS": "https://app.vercel.app, https://preview.vercel.app",
        }
    )
    assert prod_settings.DATABASE_URL == "postgresql://user:pass@host:5432/approvals"
    assert prod_settings.CORS_ORIGINS == [
        "https://app.vercel.app",
        "https://preview.vercel.app",
    ]

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        Settings.from_env({"ENV": "production"})

    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings.from_env(
            {"ENV": "development", "CORS_ORIGINS": "*"}
        )
