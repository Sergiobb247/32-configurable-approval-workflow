"""Workflow configuration routes — endpoints 8–12.

Owner: Person D — Workflows, Audit & Ops (Moses Abigail).
Contract: docs/technical-spec.md §6 (endpoints 8–12), §7.3, §8;
docs/schema.md §4.3–4.4; docs/prd.md US-10, US-11.

Rules enforced here (the step-list shape rules already live in Person B's
schemas, so empty/duplicate/gapped chains arrive as a 422 before this code
runs — see `app/schemas/workflow.py`):

* Only admins create, edit, or re-chain workflows (`require_admin`, 403).
* Any logged-in user may read workflows, but non-admins only ever see
  *active* ones — an inactive workflow cannot receive new submissions, so it
  must not be offered to employees (schema.md §4.3, spec §7.3).
* A workflow with zero steps can never be (re)activated -> 422 (test-plan
  §4.6). This is the guard the PATCH route owns, because only the route can
  see the workflow's current step count (noted on `WorkflowPatch` itself).
* **No step may require the `ADMIN` role -> 422.** The team rule is absolute:
  an admin can *never* approve a request (no override; explanation.md §5,
  permission matrix §4.1 — confirmed by Persons A and B). A chain containing
  an ADMIN step could therefore never complete, so this file refuses to
  create, re-chain, or activate such a workflow at all. Person B's schema
  currently accepts any `Role` value, so the guard lives here at the
  configuration boundary Person D owns; Person C's engine still refuses any
  actual approve/reject attempt by an admin as the second line of defence.
* Replacing steps replaces the WHOLE ordered list (schema.md §4.4). The
  `steps` relationship is `delete-orphan`, so assigning a new list removes
  the old rows in the same transaction.
* Editing a workflow never touches in-flight requests: they follow the chain
  frozen into `requests.steps_snapshot` at submit time (the snapshot rule,
  schema.md §4.5). Nothing in this file reads or writes `Request` at all —
  that separation is precisely why the rule holds.
* Creating/updating a workflow writes a `WORKFLOW_CREATED` /
  `WORKFLOW_UPDATED` audit row via `services/audit.record()` in the SAME
  transaction (one-writer rule, technical-spec.md §2). This file never
  touches `audit_logs` — or `request.status` — directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models import AuditAction, EntityType, Role, User, Workflow, WorkflowStep
from app.schemas import (
    ListResponse,
    WorkflowCreate,
    WorkflowOut,
    WorkflowPatch,
    WorkflowStepsReplace,
)
from app.services import audit

router = APIRouter(prefix="/workflows", tags=["workflows"])

# Exact error-catalogue sentences (docs/technical-spec.md §8 style).
WORKFLOW_NOT_FOUND_DETAIL = "Workflow not found"
EMPTY_WORKFLOW_DETAIL = "A workflow needs at least one step"
# Extends the §8 catalogue sentence for "Admin tries to approve" to the
# moment the misconfiguration is attempted, so the admin learns the rule
# while building the chain instead of when a request deadlocks on it.
ADMIN_STEP_DETAIL = (
    "A workflow step cannot require the ADMIN role: "
    "admins configure workflows; they cannot approve requests"
)


def _build_steps(payload_steps) -> list[WorkflowStep]:
    """Build ordered WorkflowStep rows from validated schema steps.

    The schema has already proven the list is non-empty, 1-based, contiguous
    and duplicate-free; sorting is belt-and-braces so storage order always
    matches `step_order` even if a client sent the JSON out of order.
    """
    return [
        WorkflowStep(
            step_order=step.step_order,
            required_role=step.required_role,
            label=step.label,
        )
        for step in sorted(payload_steps, key=lambda s: s.step_order)
    ]


def _ensure_no_admin_steps(steps) -> None:
    """Refuse any chain that asks an admin to approve (422).

    Accepts schema steps (`WorkflowStepIn`) or ORM rows (`WorkflowStep`) —
    both expose `required_role` as a `Role`. Checked on create, on step
    replacement, and whenever a workflow would end up active, so there is
    no path by which a live workflow can wait on an ADMIN approver. An
    admin step is a *configuration* error (422, like an empty chain), not a
    permission error: the caller is an admin doing something allowed in
    general, just with a value this product will never accept.
    """
    if any(step.required_role == Role.ADMIN for step in steps):
        raise HTTPException(
            status_code=422,  # Unprocessable Entity (catalogue: malformed input)
            detail=ADMIN_STEP_DETAIL,
        )


def _get_workflow_or_404(db: Session, workflow_id: int) -> Workflow:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=WORKFLOW_NOT_FOUND_DETAIL,
        )
    return workflow


@router.get(
    "",
    response_model=ListResponse[WorkflowOut],
    status_code=status.HTTP_200_OK,
)
def list_workflows(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListResponse[WorkflowOut]:
    """List workflows. Non-admins see active workflows only (§7.3)."""
    query = db.query(Workflow)
    if current_user.role != Role.ADMIN:
        query = query.filter(Workflow.is_active.is_(True))

    total = query.count()
    items = query.order_by(Workflow.id.asc()).offset(skip).limit(limit).all()
    return ListResponse[WorkflowOut](
        items=[WorkflowOut.model_validate(w) for w in items],
        total=total,
    )


@router.post(
    "",
    response_model=WorkflowOut,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow(
    payload: WorkflowCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Workflow:
    """Create a workflow with its ordered chain (admin only, US-10).

    `WorkflowCreate` (Person B) already rejects an empty, duplicate-ordered
    or gapped step list with 422 before this handler runs. This handler adds
    the rule the schema cannot carry yet: no step may require `ADMIN`,
    because an admin can never approve (see module docstring).
    """
    _ensure_no_admin_steps(payload.steps)

    workflow = Workflow(
        name=payload.name,
        description=payload.description,
        is_active=True,
        created_by=current_admin.id,
    )
    workflow.steps = _build_steps(payload.steps)
    db.add(workflow)

    try:
        # Flush first so the audit row can reference the new workflow's id,
        # then record + commit as ONE transaction (technical-spec.md §3).
        db.flush()
        audit.record(
            db,
            actor=current_admin,
            action=AuditAction.WORKFLOW_CREATED,
            entity_type=EntityType.WORKFLOW,
            entity_id=workflow.id,
            request_id=None,
        )
        db.commit()
    except IntegrityError as exc:
        # Defence in depth for the (workflow_id, step_order) unique
        # constraint (schema.md §5) — normally caught by the schema first.
        db.rollback()
        raise HTTPException(
            status_code=422,  # Unprocessable Entity (catalogue: malformed input)
            detail="Step order values must be unique within a workflow",
        ) from exc

    db.refresh(workflow)
    return workflow


@router.get(
    "/{workflow_id}",
    response_model=WorkflowOut,
    status_code=status.HTTP_200_OK,
)
def get_workflow(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Workflow:
    """Fetch one workflow with its ordered steps.

    Inactive workflows are hidden from non-admins (404, as if absent): the
    list already filters them out for employees (§7.3), and the detail route
    must not be a back door around that same rule.
    """
    workflow = _get_workflow_or_404(db, workflow_id)
    if current_user.role != Role.ADMIN and not workflow.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=WORKFLOW_NOT_FOUND_DETAIL,
        )
    return workflow


@router.patch(
    "/{workflow_id}",
    response_model=WorkflowOut,
    status_code=status.HTTP_200_OK,
)
def update_workflow(
    workflow_id: int,
    payload: WorkflowPatch,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Workflow:
    """Patch name / description / is_active (admin only).

    Absent fields are left alone; `{"description": null}` explicitly clears
    the description (`model_fields_set` tells the two apart — see Person B's
    `WorkflowPatch`). A workflow may only end up *active* with a chain that
    can actually complete: activating one with no steps is refused (an
    active empty chain would let a request be "approved" by nobody,
    test-plan §4.6), and so is activating — or leaving active — one whose
    chain contains an ADMIN step, because an admin can never approve.
    Deactivating such a workflow is always allowed: that is how a bad
    legacy configuration gets retired.
    """
    workflow = _get_workflow_or_404(db, workflow_id)

    resulting_is_active = (
        payload.is_active if payload.is_active is not None else workflow.is_active
    )
    if resulting_is_active:
        if len(workflow.steps) == 0:
            raise HTTPException(
                status_code=422,  # Unprocessable Entity (catalogue: malformed input)
                detail=EMPTY_WORKFLOW_DETAIL,
            )
        _ensure_no_admin_steps(workflow.steps)

    if "name" in payload.model_fields_set and payload.name is not None:
        workflow.name = payload.name
    if "description" in payload.model_fields_set:
        workflow.description = payload.description
    if payload.is_active is not None:
        workflow.is_active = payload.is_active

    audit.record(
        db,
        actor=current_admin,
        action=AuditAction.WORKFLOW_UPDATED,
        entity_type=EntityType.WORKFLOW,
        entity_id=workflow.id,
        request_id=None,
    )
    db.commit()
    db.refresh(workflow)
    return workflow


@router.post(
    "/{workflow_id}/steps",
    response_model=WorkflowOut,
    status_code=status.HTTP_200_OK,
)
def replace_workflow_steps(
    workflow_id: int,
    payload: WorkflowStepsReplace,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Workflow:
    """Replace the whole ordered chain at once (admin only, §7.3).

    Individual step positions are never patched — replacing the full list is
    what guarantees orders stay 1-based and gap-free (schema.md §4.4).
    Requests already submitted against this workflow are unaffected: they
    walk their frozen snapshot, not these live rows (US-11). The new chain
    may not contain an ADMIN step (an admin can never approve); the check
    runs *before* the old chain is touched, so a rejected replacement
    leaves the existing workflow exactly as it was.
    """
    workflow = _get_workflow_or_404(db, workflow_id)
    _ensure_no_admin_steps(payload.steps)

    try:
        # Delete the old chain AND flush before inserting the new one:
        # inserting first would collide with the old rows on the
        # UNIQUE(workflow_id, step_order) constraint (schema.md §4.4).
        workflow.steps.clear()
        db.flush()
        workflow.steps = _build_steps(payload.steps)
        audit.record(
            db,
            actor=current_admin,
            action=AuditAction.WORKFLOW_UPDATED,
            entity_type=EntityType.WORKFLOW,
            entity_id=workflow.id,
            request_id=None,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,  # Unprocessable Entity (catalogue: malformed input)
            detail="Step order values must be unique within a workflow",
        ) from exc

    db.refresh(workflow)
    return workflow
