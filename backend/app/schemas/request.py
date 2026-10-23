"""Request shapes — including `RequestOut`, the most-used shape in the app.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/technical-spec.md §7.4, docs/schema.md §4.5.

Money rules (schema.md §1, §5): stored Numeric(12,2); input must be > 0 and
at most 9,999,999,999.99 with two decimals; output is a STRING with exactly
two decimals ("450000.00") so the frontend never does float maths.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from typing import TYPE_CHECKING, Iterable

from pydantic import Field, StringConstraints, condecimal, field_serializer, field_validator
from typing_extensions import Annotated

from app.models import RequestStatus, Role

from .common import ApiModel, ListResponse, UTCDateTime
from .user import UserSummary

if TYPE_CHECKING:  # pragma: no cover
    from app.models import Request

#: Contract limit (schema.md §4.5 / §5): fits Numeric(12,2) exactly.
MAX_AMOUNT = Decimal("9999999999.99")

# gt 0, <= MAX, 12 digits total, 2 decimal places. decimal_places quantises
# input ("100.5" -> "100.50"); values beyond the column limit are rejected
# with 422, not truncated by the database.
AmountIn = condecimal(gt=0, le=MAX_AMOUNT, max_digits=12, decimal_places=2)

Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


class RequestCreate(ApiModel):
    workflow_id: int = Field(ge=1)
    # Blank-after-trim is rejected -> "422 empty title" (§7.4).
    title: Annotated[Trimmed, StringConstraints(min_length=1, max_length=200)]
    description: Trimmed | None = Field(default=None, description="Blank is stored as null.")
    amount: AmountIn

    @field_validator("description", mode="before")
    @classmethod
    def _blank_description_is_none(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class StepState(str, enum.Enum):
    """Display state of one step inside RequestOut.steps."""

    DONE = "done"
    CURRENT = "current"
    UPCOMING = "upcoming"


class StepOut(ApiModel):
    """One chain entry as the UI shows it: the frozen snapshot fields
    (order/role/label) plus progress fields the engine fills in from the
    audit trail. Lowercase `state` values per technical-spec.md §7.4."""

    order: int
    role: Role
    label: str
    state: StepState
    acted_by: str | None
    acted_at: UTCDateTime | None


class RequestOut(ApiModel):
    """The one request shape — detail, lists and inbox all use it, so the
    frontend has exactly one component contract to code against.

    `submitted_by` is nested ({id, email, full_name, role}) — it is read from
    the ORM `submitter` relationship via the validation alias. `steps` and
    `can_act` are not columns: the route computes them (steps from the
    snapshot + audit trail; can_act = permissions.can_act(...).allowed for
    the CALLING user) and hands them to `RequestOut.build`, below.
    """

    id: int
    workflow_id: int
    title: str
    description: str | None
    amount: Decimal
    status: RequestStatus
    current_step_index: int
    submitted_by: UserSummary = Field(validation_alias="submitter")
    steps: list[StepOut]
    can_act: bool
    created_at: UTCDateTime
    decided_at: UTCDateTime | None

    @field_serializer("amount", when_used="json")
    def _amount_two_decimals(self, value: Decimal) -> str:
        # "450000.00" — a string with exactly two decimals, per §7.4.
        return f"{value:.2f}"

    @classmethod
    def build(
        cls,
        request: "Request",
        *,
        steps: Iterable[StepOut],
        can_act: bool,
    ) -> "RequestOut":
        """Assemble the response from the ORM row plus the route's computed
        parts. This is the single place the shape is assembled, so every
        endpoint returns byte-identical structure."""
        return cls(
            id=request.id,
            workflow_id=request.workflow_id,
            title=request.title,
            description=request.description,
            amount=request.amount,
            status=request.status,
            current_step_index=request.current_step_index,
            submitted_by=UserSummary.model_validate(request.submitter),
            steps=list(steps),
            can_act=can_act,
            created_at=request.created_at,
            decided_at=request.decided_at,
        )


RequestList = ListResponse[RequestOut]
