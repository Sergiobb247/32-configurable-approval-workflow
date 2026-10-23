"""Request model plus the RequestStatus and Action enums.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/schema.md §3 and §4.5. This is the table the whole product
turns on — read the snapshot rule and the version rule below before touching
anything.

The two enums live exactly here (`app/models/request.py`) per schema.md §7
and are re-exported from `app/models/__init__.py`.
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional, Sequence, TypedDict

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.state_machine import is_terminal as _sm_is_terminal

from .audit_log import AuditLog  # runtime import is safe: audit_log imports nothing back
from .common import created_at_column, role_enum_column, utcnow

if TYPE_CHECKING:  # pragma: no cover
    from .user import User
    from .workflow import Workflow
    from .workflow_step import WorkflowStep


class RequestStatus(str, enum.Enum):
    """schema.md §3. Terminal states: APPROVED, REJECTED, CANCELLED.
    Which transitions are legal is defined in `app/state_machine.py` —
    this enum deliberately carries no transition logic."""

    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class Action(str, enum.Enum):
    """The four actions that can drive a transition (schema.md §3)."""

    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CANCEL = "CANCEL"


class SnapshotStep(TypedDict):
    """One entry of `Request.steps_snapshot` — the frozen chain (§4.5).

    Plain JSON ({order, role, label}); the *richer* shape the API returns
    (with state, acted_by, acted_at) is built on top of this by the engine
    and defined in `app/schemas/request.py` as `StepOut`.
    """

    order: int
    role: str
    label: str


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = (
        # Defence in depth behind the Pydantic amount validator (§5).
        CheckConstraint("amount > 0", name="ck_requests_amount_positive"),
        # The inbox query filters on both columns (§4.5).
        Index("ix_requests_status_step", "status", "current_step_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Reference only — a request NEVER re-reads the workflow's live steps;
    # it follows `steps_snapshot`, frozen at submit time (the snapshot rule).
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    submitted_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Numeric(12,2) — never float (§1). Values come from Decimal.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # THE ENGINE IS THE ONLY WRITER of `status`. Not routes, not seeders,
    # not tests (fixtures may set it for setup). Enforced by review of the
    # one-writer rule in technical-spec.md §2.
    status: Mapped[RequestStatus] = role_enum_column(
        RequestStatus, nullable=False, default=RequestStatus.DRAFT, index=True
    )
    # 0-based index into steps_snapshot (§4.5). WorkflowStep.step_order is
    # 1-based; the snapshot keeps "order" 1-based to mirror the UI.
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Frozen copy of the chain at submit time. MutableList so in-place edits
    # (there should be none outside the engine) still flush.
    steps_snapshot: Mapped[list[SnapshotStep]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    # Optimistic lock (§4.5 "the version rule"): every engine action
    # increments it; a stale reader gets 409.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = created_at_column()
    decided_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    submitter: Mapped["User"] = relationship(
        back_populates="requests", foreign_keys=[submitted_by]
    )
    workflow: Mapped["Workflow"] = relationship(back_populates="requests")
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="request",
        # A timeline (§4.6): ascending by time, then id as the tie-breaker.
        order_by=(AuditLog.created_at, AuditLog.id),
    )

    # -- snapshot contract ---------------------------------------------------
    @staticmethod
    def snapshot_from_steps(steps: Sequence["WorkflowStep"]) -> list[SnapshotStep]:
        """Build the frozen chain stored at submit time (§4.5).

        This is the *single definition* of the snapshot format — the engine
        (Person C) calls this instead of hand-building dicts, so the JSON
        shape can't drift between writers.
        """
        return [
            {
                "order": s.step_order,
                "role": s.required_role.value
                if isinstance(s.required_role, enum.Enum)
                else str(s.required_role),
                "label": s.label,
            }
            for s in sorted(steps, key=lambda step: step.step_order)
        ]

    @property
    def current_step(self) -> Optional[SnapshotStep]:
        """The snapshot step the request is waiting on, or None."""
        if not self.steps_snapshot:
            return None
        if not 0 <= self.current_step_index < len(self.steps_snapshot):
            return None
        return self.steps_snapshot[self.current_step_index]

    @property
    def is_terminal(self) -> bool:
        """True in APPROVED / REJECTED / CANCELLED — delegated to the state
        machine so "terminal" has exactly one definition in the codebase."""
        return _sm_is_terminal(self.status)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Request id={self.id} status={self.status} step={self.current_step_index}>"
