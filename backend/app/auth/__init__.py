"""Authentication and role-guard surface for the API.

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/technical-spec.md §1, §2, §9, §10.
"""

from .dependencies import (
    AUTH_REQUIRED_DETAIL,
    FORBIDDEN_ROLE_DETAIL,
    get_current_user,
    optional_current_user,
    require_admin,
    require_roles,
)
from .security import (
    ALGORITHM,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    dummy_verify,
    ensure_utc,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expires_at,
    verify_password,
)

__all__ = [
    "ALGORITHM",
    "AUTH_REQUIRED_DETAIL",
    "FORBIDDEN_ROLE_DETAIL",
    "InvalidTokenError",
    "create_access_token",
    "decode_access_token",
    "dummy_verify",
    "ensure_utc",
    "generate_refresh_token",
    "get_current_user",
    "hash_password",
    "hash_refresh_token",
    "optional_current_user",
    "refresh_token_expires_at",
    "require_admin",
    "require_roles",
    "verify_password",
]
