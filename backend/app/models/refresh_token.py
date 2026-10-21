"""RefreshToken model — hashed, revocable, rotating session tokens.

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/schema.md §4.2 and docs/technical-spec.md §10.

Security invariants:
* `token_hash` stores ONLY the 64-character SHA-256 hex digest of the opaque
  48-byte raw token — never the raw token itself.
* Using a refresh token revokes that row (`revoked_at` set) and inserts a
  replacement row inside the same transaction (rotation).
* `user` relationship matches `User.refresh_tokens` in `app/models/user.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

from .common import created_at_column

if TYPE_CHECKING:  # pragma: no cover
    from .user import User


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at_column()

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<RefreshToken id={self.id} user_id={self.user_id} "
            f"revoked={self.revoked_at is not None}>"
        )
