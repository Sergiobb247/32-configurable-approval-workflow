"""The approval engine — the ONE place that writes `request.status`.

Owner: Person C — Approval Engine (Eze Chebem).
Contract: docs/technical-spec.md section 3 (the five-step action), section 4
(state machine), section 8 (error catalogue); decisions log #3 and #4.

Every mutating action in the product goes through here, and every action follows
the same five steps, in this order:

    1. state machine   is the move legal at all?          else 409
    2. already acted?  has this user already decided?     else 403
    3. permissions     may THIS user make the move?       else 403
    4. transition      new status + step index; version += 1
    5. audit           one row, SAME transaction as the change
    then commit + refresh + return the row

Ordering matters: the state machine runs first, so a decided request always
answers "This request has already been decided" (409) rather than a
permission sentence (403). The most useful answer wins.

Optimistic locking. The caller holds the `version` it read; this module re-reads
the row and compares. If the database moved on, the caller gets 409 "This
request already moved to the next step" — that is how two approvers clicking at
once produce one approval and one clear message instead of two approvals.

One-writer rule. This module is the only writer of `Request.status`
(technical-spec.md section 2). Routes load and delegate; tests may set status in
fixtures only.

Audit ownership. `audit_logs` is written only by `app.services.audit.record()`
(Person D). This module calls it and never commits on its own (D's function
flushes, the caller commits). A clearly-marked fallback exists ONLY while D's
module is unmerged — see `_audit` below; delete it the moment D lands.
"""

from __future__ import annotations

from typing import Any, Sequence

from fastapi import HTTPException, status as http_status

# 422 is written literally: Starlette renamed the constant and pinning either
# spelling makes the suite warn or break depending on the installed version.
UNPROCESSABLE = 422
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import state_machine
from app.models import (
    Action,
    AuditAction,
    AuditLog,
    EntityType,
    Request,
    RequestStatus,
    Role,
    User,
    Workflow,
)
from app.models.common import utcnow
from app.permissions import (
    can_act,
    can_view,
    current_step_role,
    is_submitter,
    is_terminal,
)
from app.schemas import RequestOut, StepOut, StepState
from app.services import audit as audit_service

# --- catalogue sentences (technical-spec.md section 8) -----------------------

STALE_VERSION_DETAIL = "This request already moved to the next step"
REQUEST_NOT_FOUND_DETAIL = "Request not found"
WORKFLOW_NOT_FOUND_DETAIL = "Workflow not found"
WORKFLOW_INACTIVE_DETAIL = "This workflow is not active"
WORKFLOW_EMPTY_DETAIL = "A workflow needs at least one step"
REJECT_NEEDS_COMMENT_DETAIL = "A comment is required when rejecting"
ALREADY_ACTED_DETAIL = "You have already acted on this request"


# --- audit delegation --------------------------------------------------------


def _audit(
    db: Session,
    *,
    actor: User,
    action: str,
    entity_type: str = EntityType.REQUEST,
    entity_id: int,
    request_id: int | None = None,
    from_state: str | None = None,
    to_state: str | None = None,
    comment: str | None = None,
) -> Any:
    """Write one audit row, in the caller's transaction.

    Prefers Person D's `services/audit.record()`; D's function flushes but does
    not commit, which is exactly what we need (the status change and its audit
    row commit together or not at all).
     it delegates to audit.record()
    """
    return audit_service.record(
        db,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=request_id,
        from_state=from_state,
        to_state=to_state,
        comment=comment,
    )


# --- reads --------------------------------------------------------------------


def has_acted(db: Session, user: User, request: Request) -> bool:
    """True if this user already approved or rejected this request.

    The single fact behind the "one action per user per request" rule
    (decisions log #4) — a repeated role in a chain therefore needs two
    different people, and the audit trail never shows one person twice.
    """
    if user.id is None or request.id is None:
        return False
    existing = db.execute(
        select(AuditLog.id).where(
            AuditLog.request_id == request.id,
            AuditLog.actor_id == user.id,
            AuditLog.action.in_((AuditAction.APPROVED, AuditAction.REJECTED)),
        )
    ).first()
    return existing is not None


def _decision_audits(db: Session, request: Request) -> Sequence[AuditLog]:
    """Approve/reject rows for one request, oldest first."""
    return (
        db.execute(
            select(AuditLog)
            .where(
                AuditLog.request_id == request.id,
                AuditLog.action.in_((AuditAction.APPROVED, AuditAction.REJECTED)),
            )
            .order_by(AuditLog.created_at, AuditLog.id)
        )
        .scalars()
        .all()
    )


def build_steps(db: Session, request: Request) -> list[StepOut]:
    """The chain as the UI shows it: frozen snapshot + progress from the trail.

    Mapping rule: one decision per step, in order, so the k-th approval belongs
    to step k. A rejection belongs to the step where the request died.
    """
    snapshot = list(request.steps_snapshot or [])
    if not snapshot:
        return []

    decisions = _decision_audits(db, request)
    approvals = [row for row in decisions if row.action == AuditAction.APPROVED]
    rejection = next(
        (row for row in decisions if row.action == AuditAction.REJECTED), None
    )
    index = request.current_step_index

    steps: list[StepOut] = []
    for position, entry in enumerate(snapshot):
        if request.status == RequestStatus.APPROVED:
            state = StepState.DONE
        elif position < index:
            state = StepState.DONE
        elif position == index and request.status in (
            RequestStatus.PENDING,
            RequestStatus.REJECTED,
            RequestStatus.CANCELLED,
        ):
            # PENDING: waiting here. REJECTED / CANCELLED: this is where it died,
            # shown as the current step so the UI can point at it.
            state = StepState.CURRENT
        else:
            state = StepState.UPCOMING

        acted = None
        if position < len(approvals):
            acted = approvals[position]
        elif rejection is not None and position == index:
            acted = rejection

        steps.append(
            StepOut(
                order=entry.get("order", position + 1),
                role=entry.get("role"),
                label=entry.get("label", ""),
                state=state,
                acted_by=acted.actor.full_name if acted and acted.actor else None,
                acted_at=acted.created_at if acted else None,
            )
        )
    return steps


def request_out(db: Session, request: Request, viewer: User) -> RequestOut:
    """The single assembly point for `RequestOut` — every endpoint that returns
    a request goes through here, so the shape cannot drift."""
    return RequestOut.build(
        request,
        steps=build_steps(db, request),
        can_act=can_act(
            viewer,
            request,
            Action.APPROVE,
            already_acted=has_acted(db, viewer, request),
        ).allowed,
    )


def visible_requests_query(db: Session, viewer: User):
    """Rows the caller may list from `GET /requests`: everything for an admin,
    their own submissions for everybody else."""
    query = db.query(Request)
    if viewer.role != Role.ADMIN:
        query = query.filter(Request.submitted_by == viewer.id)
    return query


def list_inbox(
    db: Session, viewer: User, *, skip: int = 0, limit: int = 50
) -> tuple[list[Request], int]:
    """Requests waiting on the caller's role and not yet acted on by them.

    Role and "already acted" are evaluated against the request's frozen
    snapshot, not the live workflow, because that is the chain this request is
    actually walking. Candidates are filtered in Python: the snapshot is JSON
    and index expressions differ between SQLite and Postgres — one portable
    query beats two dialect-specific ones at this scale.
    """
    candidates = (
        db.query(Request)
        .filter(
            Request.status == RequestStatus.PENDING,
            Request.submitted_by != viewer.id,
        )
        .order_by(Request.created_at, Request.id)
        .all()
    )

    waiting: list[Request] = []
    for request in candidates:
        if current_step_role(request) != viewer.role:
            continue
        if has_acted(db, viewer, request):
            continue
        waiting.append(request)

    total = len(waiting)
    return waiting[skip : skip + limit], total


# --- guards -------------------------------------------------------------------


def load_request(db: Session, request_id: int) -> Request:
    row = db.get(Request, request_id)
    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=REQUEST_NOT_FOUND_DETAIL,
        )
    return row


def _check_version(db: Session, row: Request, seen_version: int) -> None:
    """Optimistic lock: the caller tells us the version it read."""
    assert row.id is not None
    current = db.execute(
        select(Request.version).where(Request.id == row.id)
    ).scalar_one_or_none()
    if current is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=REQUEST_NOT_FOUND_DETAIL,
        )
    if current != seen_version:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=STALE_VERSION_DETAIL
        )


def _assert_transition(
    row: Request, action: Action, *, total_steps: int | None = None
) -> tuple[RequestStatus, int]:
    """Step 1. Maps the state machine's answers onto HTTP status codes.

    `total_steps` is supplied by `submit`, which measures the workflow's LIVE
    chain — the snapshot is still empty at that moment. Every other action
    measures the frozen snapshot, which is the chain the request is walking.
    """
    chain_length = (
        total_steps if total_steps is not None else len(row.steps_snapshot or [])
    )
    try:
        new_status, new_index = state_machine.next_state(
            row.status,
            action,
            row.current_step_index,
            chain_length,
        )
    except state_machine.TransitionError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        # Impossible step arithmetic is a validation gap upstream (a workflow
        # with no steps), never a client error on this endpoint.
        raise HTTPException(
            status_code=UNPROCESSABLE, detail=str(exc)
        ) from exc
    return RequestStatus(new_status), new_index


def _assert_allowed(
    user: User, row: Request, action: Action, *, already_acted: bool = False
) -> None:
    """Steps 2 and 3."""
    if action in (Action.APPROVE, Action.REJECT) and already_acted:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail=ALREADY_ACTED_DETAIL
        )
    decision = can_act(user, row, action, already_acted=already_acted)
    if not decision.allowed:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail=decision.reason
        )


# --- the four actions ---------------------------------------------------------


def create(
    db: Session,
    user: User,
    *,
    workflow_id: int,
    title: str,
    description: str | None,
    amount: Any,
) -> Request:
    """Create a DRAFT request. No transition yet — nothing has moved."""
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=WORKFLOW_NOT_FOUND_DETAIL,
        )
    if not workflow.is_active:
        raise HTTPException(
            status_code=UNPROCESSABLE,
            detail=WORKFLOW_INACTIVE_DETAIL,
        )
    if not workflow.steps:
        raise HTTPException(
            status_code=UNPROCESSABLE,
            detail=WORKFLOW_EMPTY_DETAIL,
        )

    row = Request(
        workflow_id=workflow.id,
        submitted_by=user.id,
        title=title,
        description=description,
        amount=amount,
        status=RequestStatus.DRAFT,
        current_step_index=0,
        steps_snapshot=[],
        version=1,
    )
    db.add(row)
    db.flush()  # row.id is needed for the audit entry

    _audit(
        db,
        actor=user,
        action=AuditAction.REQUEST_CREATED,
        entity_id=row.id,
        request_id=row.id,
        from_state=None,
        to_state=RequestStatus.DRAFT.value,
    )
    db.commit()
    db.refresh(row)
    return row


def submit(db: Session, user: User, request: Request) -> Request:
    """DRAFT -> PENDING at step 1, freezing the workflow's chain onto the row."""
    row = load_request(db, request.id)
    _check_version(db, row, request.version)

    # The workflow is validated first: the chain it contributes is the one the
    # request will walk, and the state machine needs its length.
    workflow = db.get(Workflow, row.workflow_id)
    if workflow is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=WORKFLOW_NOT_FOUND_DETAIL,
        )
    if not workflow.is_active:
        raise HTTPException(status_code=UNPROCESSABLE, detail=WORKFLOW_INACTIVE_DETAIL)
    if not workflow.steps:
        raise HTTPException(status_code=UNPROCESSABLE, detail=WORKFLOW_EMPTY_DETAIL)

    new_status, new_index = _assert_transition(
        row, Action.SUBMIT, total_steps=len(workflow.steps)
    )
    _assert_allowed(user, row, Action.SUBMIT)

    previous = row.status
    # THE SNAPSHOT RULE: the chain is frozen here and never re-read (schema.md).
    row.steps_snapshot = Request.snapshot_from_steps(workflow.steps)
    row.status = new_status
    row.current_step_index = new_index
    row.version += 1

    _audit(
        db,
        actor=user,
        action=AuditAction.SUBMITTED,
        entity_id=row.id,
        request_id=row.id,
        from_state=previous.value,
        to_state=row.status.value,
    )
    db.commit()
    db.refresh(row)
    return row


def decide(
    db: Session,
    user: User,
    request: Request,
    action: Action,
    comment: str | None = None,
) -> Request:
    """APPROVE or REJECT one step. `comment` is required on reject."""
    if action not in (Action.APPROVE, Action.REJECT):
        raise ValueError("decide() handles APPROVE and REJECT only")

    row = load_request(db, request.id)
    _check_version(db, row, request.version)
    new_status, new_index = _assert_transition(row, action)
    _assert_allowed(user, row, action, already_acted=has_acted(db, user, row))

    cleaned = (comment or "").strip() or None
    if action == Action.REJECT and cleaned is None:
        # The schema (`RejectIn`) already guarantees this over HTTP; this is the
        # backstop for any non-HTTP caller (technical-spec.md section 7.5).
        raise HTTPException(
            status_code=UNPROCESSABLE,
            detail=REJECT_NEEDS_COMMENT_DETAIL,
        )

    previous = row.status
    row.status = new_status
    row.current_step_index = new_index
    row.version += 1
    if is_terminal(row):
        row.decided_at = utcnow()

    _audit(
        db,
        actor=user,
        action=(
            AuditAction.APPROVED if action == Action.APPROVE else AuditAction.REJECTED
        ),
        entity_id=row.id,
        request_id=row.id,
        from_state=previous.value,
        to_state=row.status.value,
        comment=cleaned,
    )
    db.commit()
    db.refresh(row)
    return row


def cancel(db: Session, user: User, request: Request) -> Request:
    """Withdraw a request. The submitter, or an admin (audited as the actor)."""
    row = load_request(db, request.id)
    _check_version(db, row, request.version)
    new_status, new_index = _assert_transition(row, Action.CANCEL)
    _assert_allowed(user, row, Action.CANCEL)

    previous = row.status
    row.status = new_status
    row.current_step_index = new_index
    row.version += 1
    row.decided_at = utcnow()

    _audit(
        db,
        actor=user,
        action=AuditAction.CANCELLED,
        entity_id=row.id,
        request_id=row.id,
        from_state=previous.value,
        to_state=row.status.value,
        comment=None if is_submitter(user, row) else "Cancelled by an admin",
    )
    db.commit()
    db.refresh(row)
    return row


def assert_visible(user: User, request: Request) -> None:
    """Raise 403 unless `user` may read this request (route-level guard)."""
    decision = can_view(user, request)
    if not decision.allowed:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail=decision.reason
        )
