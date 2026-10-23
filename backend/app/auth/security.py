"""Password hashing, HS256 access JWTs, and opaque SHA-256 refresh tokens.

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/technical-spec.md §10 and docs/schema.md §4.1–4.2.

Design choices (see docs/judge-qa.md §5 & §9):
* Passwords are hashed with bcrypt (direct `bcrypt` module first so Python 3.13
  / `bcrypt>=5` works cleanly without passlib's 72-byte self-test bug, matching
  `tests/factories.py`). Plain passwords are never stored or logged.
* Access tokens are short-lived HS256 JWTs (`ACCESS_TOKEN_MINUTES`, default 15)
  with `sub = str(user.id)` and `role = user.role.value`.
* Refresh tokens are 48 cryptographically random bytes (`token_urlsafe(48)`).
  Only `sha256(raw_token)` is stored in `refresh_tokens.token_hash`.
"""

from __future__ import annotations

import enum
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import settings
from app.models import Role
from app.models.common import utcnow

try:
    import bcrypt as _bcrypt
except ImportError:  # pragma: no cover - fallback for passlib-only environments
    _bcrypt = None
    from passlib.context import CryptContext

    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
_MAX_BCRYPT_BYTES = 72


class InvalidTokenError(Exception):
    """Raised when an access token is missing claims, malformed, tampered with,
    or expired."""


def ensure_utc(value: datetime) -> datetime:
    """Normalize datetimes read from SQLite (naive) or PostgreSQL (aware) to
    timezone-aware UTC so expiry comparisons never raise TypeError."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    encoded = plain_password.encode("utf-8")
    if len(encoded) > _MAX_BCRYPT_BYTES:
        raise ValueError("Password cannot exceed 72 UTF-8 bytes")
    if _bcrypt is not None:
        return _bcrypt.hashpw(encoded, _bcrypt.gensalt()).decode("utf-8")
    return _pwd_context.hash(plain_password)  # pragma: no cover


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash safely."""
    encoded = plain_password.encode("utf-8")
    if len(encoded) > _MAX_BCRYPT_BYTES or not password_hash:
        return False
    try:
        if _bcrypt is not None:
            return _bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
        return _pwd_context.verify(plain_password, password_hash)  # pragma: no cover
    except ValueError:
        return False


# Precomputed hash used on unknown-email logins so timing mirrors real checks.
_DUMMY_PASSWORD_HASH: str = hash_password("DummyTimingGuardPassword123!")


def dummy_verify() -> None:
    """Run a constant-work bcrypt check when a login email does not exist."""
    verify_password("wrong-password-placeholder", _DUMMY_PASSWORD_HASH)


def create_access_token(
    user_id: int,
    role: Role | str,
    *,
    expires_delta: timedelta | None = None,
    secret: str | None = None,
) -> str:
    """Mint a signed HS256 JWT access token with `sub = str(user_id)` (§10)."""
    now = utcnow()
    lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    )
    role_value = role.value if isinstance(role, enum.Enum) else str(role)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role_value,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": now + lifetime,
    }
    return jwt.encode(payload, secret or settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(
    token: str,
    *,
    secret: str | None = None,
) -> dict[str, Any]:
    """Verify signature, expiration, and subject claim of an access token."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            secret or settings.JWT_SECRET,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        if payload.get("type", "access") != "access":
            raise InvalidTokenError("Wrong token type")
        user_id = int(payload["sub"])
        if user_id <= 0:
            raise InvalidTokenError("Invalid subject claim")
        return payload
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidTokenError("Invalid or expired access token") from exc


def generate_refresh_token() -> str:
    """Generate a new opaque 48-byte cryptographically random token (§10)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    """Return the 64-char SHA-256 hex digest persisted in `refresh_tokens`."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_token_expires_at(now: datetime | None = None) -> datetime:
    """Compute the UTC expiry timestamp for a newly issued refresh token."""
    base = ensure_utc(now) if now is not None else utcnow()
    return base + timedelta(days=settings.REFRESH_TOKEN_DAYS)
