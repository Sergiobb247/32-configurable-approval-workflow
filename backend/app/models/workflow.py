"""Workflow model.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/schema.md §4.3.

A workflow is an ordered chain of steps, each requiring a role. Requests are
submitted *against* a workflow, then follow a frozen snapshot of the chain
(schema.md §4.5, "the snapshot rule") — so editing a workflow can never
mutate an in-flight request.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

from .common import created_at_column
from .workflow_step import WorkflowStep  # runtime import is safe: step imports nothing back

if TYPE_CHECKING:  # pragma: no cover
    from .request import Request


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Inactive workflows cannot receive new submissions (schema.md §4.3).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = created_at_column()

    # Ordered by step_order; delete-orphan because the API replaces the whole
    # ordered list at once rather than patching individual positions
    # (schema.md §4.4, "rules").
    steps: Mapped[list["WorkflowStep"]] = relationship(
        back_populates="workflow",
        order_by=WorkflowStep.step_order,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    requests: Mapped[list["Request"]] = relationship(back_populates="workflow")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Workflow id={self.id} name={self.name!r} steps={len(self.steps)}>"
