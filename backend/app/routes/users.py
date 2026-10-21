"""Admin user management routes — list accounts, update role / active flag.

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/technical-spec.md §6 (endpoints 6–7), §7.2, and docs/prd.md US-13.

One-writer invariant respected:
`routes/users.py` NEVER writes directly to `audit_logs`. When Person D's
`app.services.audit.record` module is present, role changes and deactivations
delegate to `audit.record(...)` inside the same database transaction before
`db.commit()`.
"""

from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models import AuditAction, EntityType, RefreshToken, User
from app.models.common import utcnow
from app.schemas import ListResponse, UserOut, UserPatch

router = APIRouter(prefix="/users", tags=["users"])

USER_NOT_FOUND_DETAIL = "User not found"
SELF_MODIFICATION_DETAIL = "You cannot modify your own role or active status"


def _record_user_audit_if_available(
    db: Session,
    *,
    actor: User,
    target: User,
    action: str,
    from_state: str | None = None,
    to_state: str | None = None,
) -> None:
    """Delegate to Person D's `app.services.audit.record` once merged without
    violating the one-writer rule (`only services/audit.record() writes
    audit_logs`, technical-spec.md §2)."""
    try:
        from app.services import audit  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return

    record_fn = getattr(audit, "record", None)
    if not callable(record_fn):
        return

    params = inspect.signature(record_fn).parameters
    kwargs: dict[str, Any] = {}
    if "actor" in params:
        kwargs["actor"] = actor
    elif "user" in params:
        kwargs["user"] = actor
    elif "actor_id" in params:
        kwargs["actor_id"] = actor.id

    if "action" in params:
        kwargs["action"] = action
    if "entity_type" in params:
        kwargs["entity_type"] = EntityType.USER
    if "entity_id" in params:
        kwargs["entity_id"] = target.id
    if "from_state" in params:
        kwargs["from_state"] = from_state
    if "to_state" in params:
        kwargs["to_state"] = to_state
    if "request_id" in params:
        kwargs["request_id"] = None

    record_fn(db, **kwargs)


@router.get(
    "",
    response_model=ListResponse[UserOut],
    status_code=status.HTTP_200_OK,
)
def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ListResponse[UserOut]:
    """List users with total count (admin only, technical-spec.md §7.2)."""
    total = db.query(User).count()
    items = (
        db.query(User)
        .order_by(User.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return ListResponse[UserOut](
        items=[UserOut.model_validate(u) for u in items],
        total=total,
    )


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
)
def update_user(
    user_id: int,
    payload: UserPatch,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    """Change another user's role and/or active flag (admin only).

    Self-demotion and self-deactivation are refused with `409` (US-13,
    schema.md §4.1, technical-spec.md §7.2).
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=USER_NOT_FOUND_DETAIL,
        )

    if target.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=SELF_MODIFICATION_DETAIL,
        )

    previous_role = target.role
    was_active = target.is_active

    if payload.role is not None:
        target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active

    if was_active and not target.is_active:
        (
            db.query(RefreshToken)
            .filter(
                RefreshToken.user_id == target.id,
                RefreshToken.revoked_at.is_(None),
            )
            .update({RefreshToken.revoked_at: utcnow()}, synchronize_session=False)
        )

    if payload.role is not None and previous_role != target.role:
        _record_user_audit_if_available(
            db,
            actor=current_admin,
            target=target,
            action=AuditAction.USER_ROLE_CHANGED,
            from_state=previous_role.value,
            to_state=target.role.value,
        )
    if was_active and not target.is_active:
        _record_user_audit_if_available(
            db,
            actor=current_admin,
            target=target,
            action=AuditAction.USER_DEACTIVATED,
            from_state="active",
            to_state="inactive",
        )

    db.commit()
    db.refresh(target)
    return target
