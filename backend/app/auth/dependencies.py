"""FastAPI dependencies for authentication and role enforcement.

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/technical-spec.md §5.1, §8, §10 and docs/prd.md US-13.

Key security rule (docs/judge-qa.md §5 & §9):
`get_current_user` ALWAYS re-reads the `User` row from the database on every
request instead of trusting claims baked into the JWT. Role changes and user
deactivations (`is_active = False`) therefore take effect immediately on the
very next HTTP request.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, User

from .security import InvalidTokenError, decode_access_token

# Exact error catalogue sentences from docs/technical-spec.md §8
AUTH_REQUIRED_DETAIL = "Please sign in again"
FORBIDDEN_ROLE_DETAIL = "Your role cannot do this"

_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=AUTH_REQUIRED_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _resolve_user(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    token = credentials.credentials.strip()
    if not token:
        raise _unauthorized()
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError) as exc:
        raise _unauthorized() from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Return the active authenticated `User`, or raise `401`."""
    return _resolve_user(credentials, db)


def optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Return `None` when no `Authorization` header is sent; otherwise validate
    strictly (invalid/expired/inactive tokens still raise `401`)."""
    if credentials is None:
        return None
    return _resolve_user(credentials, db)


def require_roles(*allowed_roles: Role) -> Callable[..., User]:
    """Dependency factory requiring the caller to hold one of `allowed_roles`."""
    allowed_set = frozenset(allowed_roles)

    def _guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=FORBIDDEN_ROLE_DETAIL,
            )
        return current_user

    return _guard


require_admin = require_roles(Role.ADMIN)
