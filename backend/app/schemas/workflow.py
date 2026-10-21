"""Workflow shapes (endpoints 8–12, Person D's routes; B's contract).

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/technical-spec.md §7.3, docs/schema.md §4.3–4.4.

The step-list rules live in the *schema*, so a bad chain is a 422 from
validation — before any service code runs:

* at least one step       -> "A workflow needs at least one step" (spec §8)
* unique step_order       -> "Step order values must be unique..."
* 1-based and contiguous  -> "Step order must be 1-based and contiguous..."

Duplicate roles in one chain (MANAGER -> MANAGER) are ALLOWED (decision log
#4): the engine's one-action-per-user rule is what makes repeats safe.
"""

from __future__ import annotations

from pydantic import Field, StringConstraints, field_validator, model_validator
from typing_extensions import Annotated

from app.models import Role

from .common import ApiModel, ListResponse

Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


def _strip_to_none(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class WorkflowStepIn(ApiModel):
    step_order: int = Field(ge=1)
    required_role: Role
    label: Annotated[Trimmed, StringConstraints(min_length=1, max_length=120)]


def _validate_step_list(steps: list[WorkflowStepIn]) -> list[WorkflowStepIn]:
    """The three chain rules, shared by create and full-list replace."""
    if not steps:
        raise ValueError("A workflow needs at least one step")
    orders = [s.step_order for s in steps]
    if len(set(orders)) != len(orders):
        raise ValueError("Step order values must be unique within a workflow")
    if sorted(orders) != list(range(1, len(steps) + 1)):
        raise ValueError("Step order must be 1-based and contiguous (1, 2, 3, ...)")
    return steps


class WorkflowCreate(ApiModel):
    name: Annotated[Trimmed, StringConstraints(min_length=1, max_length=120)]
    description: Trimmed | None = Field(
        default=None, description="Blank is stored as null."
    )
    steps: list[WorkflowStepIn]

    _normalise_description = field_validator("description", mode="before")(_strip_to_none)
    _check_steps = field_validator("steps")(_validate_step_list)


class WorkflowStepsReplace(ApiModel):
    """POST /workflows/{id}/steps — full ordered replacement (§7.3).
    In-flight requests are untouched: they follow their snapshot (§4.5)."""

    steps: list[WorkflowStepIn]

    _check_steps = field_validator("steps")(_validate_step_list)


class WorkflowPatch(ApiModel):
    """PATCH /workflows/{id}. Absent fields are left alone; a workflow with
    zero steps cannot be ACTIVATED (that's a 422 raised by the route/service,
    since the patch body alone can't know the current step count)."""

    name: Annotated[Trimmed, StringConstraints(min_length=1, max_length=120)] | None = None
    description: Trimmed | None = None
    is_active: bool | None = None

    _normalise_description = field_validator("description", mode="before")(_strip_to_none)

    @model_validator(mode="after")
    def _must_change_something(self) -> "WorkflowPatch":
        # model_fields_set distinguishes "absent" from "explicitly null" —
        # {"description": null} is legal and CLEARS the description.
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        return self


class WorkflowStepOut(ApiModel):
    id: int
    step_order: int
    required_role: Role
    label: str


class WorkflowOut(ApiModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    created_by: int
    # Ordered — the Workflow.steps relationship sorts by step_order.
    steps: list[WorkflowStepOut]


WorkflowList = ListResponse[WorkflowOut]
