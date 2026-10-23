"""WorkflowStep model.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/schema.md §4.4.

`step_order` is 1-based, contiguous and unique per workflow. The "unique per
workflow" half is enforced here at the database level; the "1-based and
contiguous" half is a validation rule enforced in `app/schemas/workflow.py`
(the API replaces the whole ordered list at once, never patches positions).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

from .common import role_enum_column
from .user import Role

if TYPE_CHECKING:  # pragma: no cover
    from .workflow import Workflow


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_id", "step_order", name="uq_workflow_steps_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        ForeignKey("workflows.id"), nullable=False, index=True
    )
    # 1-based position in the chain (schema.md §4.4). The request snapshot
    # carries this as "order"; the 0-based current_step_index on Request is a
    # *separate* index and the two must not be conflated.
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    required_role: Mapped[Role] = role_enum_column(Role, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)

    workflow: Mapped["Workflow"] = relationship(back_populates="steps")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<WorkflowStep workflow={self.workflow_id} "
            f"order={self.step_order} role={self.required_role}>"
        )
