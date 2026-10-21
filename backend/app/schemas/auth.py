"""Auth shapes (endpoints 1–5, owned by Person A; the SHAPES are B's contract).

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/technical-spec.md §7.1 and §10.

Emails are normalised (trimmed + lowercased) in the schema, before hashing
or lookup — matching the storage rule in schema.md §4.1 so that
"Employee1@Demo.io " and "employee1@demo.io" are the same account.
"""

from __future__ import annotations

from pydantic import BeforeValidator, EmailStr, Field, StringConstraints
from typing_extensions import Annotated

from .common import ApiModel
from .user import UserOut


def _normalise(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


# EmailStr validates the format; the BeforeValidator applies the storage rule.
NormalEmail = Annotated[EmailStr, BeforeValidator(_normalise)]

Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


class RegisterIn(ApiModel):
    email: NormalEmail
    # 8+ per the demo password rule; bcrypt silently truncates past 72
    # bytes, so the schema rejects them instead of storing a surprise.
    password: str = Field(min_length=8, max_length=72)
    full_name: Annotated[Trimmed, StringConstraints(min_length=1, max_length=120)]


class LoginIn(ApiModel):
    email: NormalEmail
    password: str = Field(min_length=1)


class RefreshIn(ApiModel):
    refresh_token: str = Field(min_length=1)


class TokenOut(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginOut(TokenOut):
    """POST /auth/login — the token pair plus who you are."""

    user: UserOut
