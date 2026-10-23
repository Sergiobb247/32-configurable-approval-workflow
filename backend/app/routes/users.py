"""Admin user management routes — list accounts, update role / active flag.

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/technical-spec.md §6 (endpoints 6–7), §7.2, and docs/prd.md US-13.

One-writer invariant respected:
`routes/users.py` NEVER writes directly to `audit_logs`. Role changes and deactivations delegate to `audit.record(...)`
(Person D, `app/services/audit.py`) inside the same database transaction,
before `db.commit()`
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models import AuditAction, EntityType, RefreshToken, User
from app.models.common import utcnow
from app.schemas import ListResponse, UserOut, UserPatch
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])

USER_NOT_FOUND_DETAIL = "User not found"
SELF_MODIFICATION_DETAIL = "You cannot modify your own role or active status"

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
        audit.record(
            db,
            actor=current_admin,
            action=AuditAction.USER_ROLE_CHANGED,
            entity_type=EntityType.USER,
            entity_id=target.id,
            from_state=previous_role.value,
            to_state=target.role.value,
        )

    if was_active and not target.is_active:
        audit.record(
            db,
            actor=current_admin,
            action=AuditAction.USER_DEACTIVATED,
            entity_type=EntityType.USER,
            entity_id=target.id,
            from_state="active",
            to_state="inactive",
    )

    db.commit()
    db.refresh(target)
    return target
