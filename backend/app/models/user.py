"""User model and the Role enum.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/schema.md §4.1. Schema changes land in the same PR as the doc.

`Role` lives exactly here (`app/models/user.py`) per schema.md §7 and is
re-exported from `app/models/__init__.py` — import it as
`from app.models import Role`, never via a deep path.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base

from .common import created_at_column, role_enum_column

if TYPE_CHECKING:  # pragma: no cover - typing only, keys off runtime imports
    from .audit_log import AuditLog
    from .refresh_token import RefreshToken  # owned by Person A
    from .request import Request


class Role(str, enum.Enum):
    """The four roles (schema.md §3). Subclasses str so it serialises as a
    plain string in JSON for free."""

    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    FINANCE = "FINANCE"
    ADMIN = "ADMIN"


class User(Base):
    """An account. `password_hash` is write-only from the API's point of
    view: it must never be returned by any endpoint (schema.md §4.1)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[Role] = role_enum_column(Role, nullable=False, default=Role.EMPLOYEE)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = created_at_column()

    # --- relationships (schema.md §4.1) -------------------------------------
    requests: Mapped[list["Request"]] = relationship(
        back_populates="submitter",
        foreign_keys="Request.submitted_by",
    )
    # models/refresh_token.py is owned by Person A. The string reference is
    # resolved when A's model is imported (app/models/__init__.py does that
    # defensively); until then this relationship simply isn't used.
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    audit_entries: Mapped[list["AuditLog"]] = relationship(back_populates="actor")

    @validates("email")
    def _normalise_email(self, _key: str, value: str) -> str:
        """Emails are stored lowercase and trimmed (schema.md §4.1).

        The Pydantic schemas normalise too; this validator is the backstop so
        that seeders, scripts and tests cannot bypass the rule.
        """
        return value.strip().lower()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
