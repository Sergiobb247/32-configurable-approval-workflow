"""Audit read routes — endpoints 21–22.

Owner: Person D — Workflows, Audit & Ops (Moses Abigail).
Contract: docs/technical-spec.md §6 (endpoints 21–22), §7.6, §4.1;
docs/schema.md §4.6; docs/prd.md US-12.

These routes live in their OWN file (frozen decision #1, progress.md §5):
workflow configuration and audit reading are separate concerns, and the
request-scoped route has no business living in a workflows file.

The trail is APPEND-ONLY. This module deliberately exposes exactly two
reads and no writes of any kind — there is no POST, PATCH, PUT or DELETE
for audit anywhere in the API, not even for admins. Rows are created only
by `services/audit.record()` (one-writer rule). "A trail you can edit is
not a trail" (judge-qa.md §11).

Ordering (schema.md §4.6):
* per-request timeline  -> `created_at ASC, id ASC`   (a story, oldest first)
* global admin feed     -> `created_at DESC, id DESC` (a feed, newest first)

Visibility mirrors the permission matrix (technical-spec.md §4.1 "Read the
audit trail: own only / own inbox only / admin all"): a submitter reads
their own request's trail, an approver currently responsible for the
request (or who has already acted on it) reads it, an admin reads
everything, and everyone else is refused with 403. Person C owns the
canonical permission matrix in `permissions.py` for the engine; until that
file lands, `_ensure_can_view` below encodes the same §4.1 row for reads so
this endpoint is secure standing alone — the check is deliberately isolated
in one small function so it can delegate to C's module in one line when it
arrives.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models import AuditLog, Request, Role, User
from app.schemas import AuditEntryDetailOut, AuditEntryOut, ListResponse

router = APIRouter(tags=["audit"])

REQUEST_NOT_FOUND_DETAIL = "Request not found"
NOT_YOUR_REQUEST_DETAIL = "This request belongs to someone else"


def _ensure_can_view(db: Session, current_user: User, request: Request) -> None:
    """Raise 403 unless `current_user` may read this request's trail (§4.1)."""
    if current_user.role == Role.ADMIN:
        return
    if request.submitted_by == current_user.id:
        return

    # The approver responsible for the step the request is waiting on.
    current_step = request.current_step
    if (
        current_step is not None
        # RequestStatus subclasses str, so == "PENDING" is an exact check.
        and request.status == "PENDING"
        and str(current_step.get("role")) == current_user.role.value
    ):
        return

    # An approver who has already acted on this request keeps read access to
    # the history that contains their own decision (read-only; acting again
    # is still refused by the engine's one-action-per-user rule).
    already_acted = (
        db.query(AuditLog.id)
        .filter(
            AuditLog.request_id == request.id,
            AuditLog.actor_id == current_user.id,
        )
        .first()
    )
    if already_acted is not None:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=NOT_YOUR_REQUEST_DETAIL,
    )


@router.get(
    "/requests/{request_id}/audit",
    response_model=ListResponse[AuditEntryOut],
    status_code=status.HTTP_200_OK,
)
def get_request_audit(
    request_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListResponse[AuditEntryOut]:
    """The chronological timeline for one request (§7.6)."""
    request = db.get(Request, request_id)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=REQUEST_NOT_FOUND_DETAIL,
        )
    _ensure_can_view(db, current_user, request)

    query = (
        db.query(AuditLog)
        .options(selectinload(AuditLog.actor))
        .filter(AuditLog.request_id == request.id)
    )
    total = query.count()
    items = (
        query.order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return ListResponse[AuditEntryOut](
        items=[AuditEntryOut.model_validate(e) for e in items],
        total=total,
    )


@router.get(
    "/audit",
    response_model=ListResponse[AuditEntryDetailOut],
    status_code=status.HTTP_200_OK,
)
def get_global_audit(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ListResponse[AuditEntryDetailOut]:
    """The global trail across all requests (admin only, newest first)."""
    query = db.query(AuditLog).options(selectinload(AuditLog.actor))
    total = query.count()
    items = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return ListResponse[AuditEntryDetailOut](
        items=[AuditEntryDetailOut.model_validate(e) for e in items],
        total=total,
    )
