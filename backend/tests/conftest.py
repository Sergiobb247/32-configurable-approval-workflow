"""Shared pytest fixtures — db, client, auth_headers.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/test-plan.md §2 — "conftest.py gives a working db and client"
is Person B's definition of done.

  db            one fresh in-memory SQLite schema per test; never the dev DB
  client        a FastAPI TestClient with the app's get_db dependency
                overridden onto that same test session
  auth_headers  auth_headers(role="MANAGER") -> {"Authorization": "Bearer ..."}
                obtained through the REAL login endpoint (Person A's), so
                every API test exercises the genuine auth path. Users are
                created via the factories with the default password and are
                reused when a test asks for the same email twice.

app.main is imported lazily INSIDE the client fixture: pure-domain suites
(test_state_machine.py) keep running even before the app shell exists.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Let `pytest backend/tests` work from the repository root as well as from
# backend/ itself, without an installed package.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import factories  # noqa: E402  (intentional: after the sys.path guard)
from app import models  # noqa: E402,F401  (register every table on Base.metadata)
from app.database import Base, get_db  # noqa: E402  (Person A's foundation)
from app.models import Role, User  # noqa: E402

# StaticPool pins the whole test run to ONE in-memory connection, so the
# schema created here is the schema the app writes to through the override.
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False
)


@pytest.fixture()
def db() -> Session:
    """A brand-new schema per test — tests are independent by construction."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db: Session):
    """A TestClient whose requests run against the test session above."""
    from fastapi.testclient import TestClient

    from app.main import app  # Person D's shell — imported lazily on purpose

    def override_get_db() -> Session:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(db: Session, client) -> Callable[..., dict[str, str]]:
    """Log in through the real endpoint and return a usable header.

    auth_headers(role="MANAGER")                 -> a fresh MANAGER account
    auth_headers(email=existing.email)           -> log in as that exact user
    auth_headers(role="FINANCE", password="...") -> custom credentials
    """
    cache: dict[str, dict[str, str]] = {}

    def build(
        role: Role | str = Role.EMPLOYEE,
        *,
        email: str | None = None,
        password: str = factories.DEFAULT_PASSWORD,
        full_name: str | None = None,
    ) -> dict[str, str]:
        role_value = role.value if isinstance(role, Role) else str(role)
        email = (email or f"{role_value.lower()}@test.io").strip().lower()
        if email not in cache:
            if db.query(User).filter_by(email=email).one_or_none() is None:
                factories.make_user(
                    db, email=email, role=role_value, password=password,
                    full_name=full_name,
                )
            response = client.post(
                "/auth/login", json={"email": email, "password": password}
            )
            assert response.status_code == 200, (
                f"login failed for {email}: {response.status_code} {response.text}"
            )
            cache[email] = {
                "Authorization": f"Bearer {response.json()['access_token']}"
            }
        return dict(cache[email])

    return build
