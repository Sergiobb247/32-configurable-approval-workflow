"""User shapes.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/technical-spec.md §7.1–7.2.

`password_hash` appears in NO schema in this package — that is a rule, not
an oversight. Three levels of user exposure:

* ActorSummary  — audit trail entries: {id, full_name}
* UserSummary   — nested `submitted_by` on a request: {id, email, full_name, role}
* UserOut       — auth responses and the admin /users list: adds flags + date
"""

from __future__ import annotations

from pydantic import model_validator

from app.models import Role

from .common import ApiModel, ListResponse, UTCDateTime


class ActorSummary(ApiModel):
    id: int
    full_name: str


class UserSummary(ApiModel):
    id: int
    email: str
    full_name: str
    role: Role


class UserOut(ApiModel):
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: UTCDateTime


class UserPatch(ApiModel):
    """PATCH /users/{id} (admin). Both fields optional — "patch the role,
    deactivate, or both" — but an empty patch is a client error, not a no-op.
    Self-demotion/self-deactivation is rejected with 409 by the route. Both
    set to null is also rejected: null is not a meaningful value for either."""

    role: Role | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _must_change_something(self) -> "UserPatch":
        if self.role is None and self.is_active is None:
            raise ValueError("Provide at least one field to update")
        return self


UserList = ListResponse[UserOut]
