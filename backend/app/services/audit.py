"""Audit service — the ONLY writer of `audit_logs`.

Owner: Person D — Workflows, Audit & Ops (Moses Abigail).
Contract: docs/schema.md §4.6, docs/technical-spec.md §2–§3, §7.6.

The two invariants this file exists to keep:

1. **One writer.** Only `record()` below creates `AuditLog` rows. Not routes,
   not the engine, not the seeder — everybody calls here. That is how the
   team can promise "every state change has a matching audit row": there is
   exactly one code path that produces them, and it is this short.

2. **Flush, never commit.** `record()` adds the row and flushes it (so the
   entry gets its `id`/`created_at` and is visible to queries in the same
   session), but it deliberately does NOT commit. The caller owns the
   transaction. The engine therefore commits the status change and the audit
   entry that describes it in ONE atomic transaction: if the change rolls
   back, the audit row disappears with it, and if it commits, the row is
   guaranteed to exist. A `record()` that committed on its own could leave a
   permanent record of something that never actually happened — a trail that
   can lie is worse than no trail.

Canonical usage (this is the signature Person C's engine codes against):

    from app.models import AuditAction, EntityType
    from app.services import audit

    audit.record(
        db,
        actor=current_user,                    # a User, or actor_id=<int>
        action=AuditAction.APPROVED,           # schema.md §4.6 vocabulary
        entity_type=EntityType.REQUEST,        # "request" | "workflow" | "user"
        entity_id=request.id,
        request_id=request.id,                 # None for workflow/user events
        from_state="PENDING",
        to_state="PENDING",
        comment="Within budget",
    )
    db.commit()                                # <- the CALLER commits

For request events, `entity_type`/`entity_id` may be omitted when
`request_id` is given — they are inferred as ("request", request_id).
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Union

from sqlalchemy.orm import Session

from app.models import AuditLog, EntityType

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models import User


def _as_plain(value: object) -> str | None:
    """Normalise an enum-or-string value to the string stored in the row."""
    if value is None:
        return None
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)


def record(
    db: Session,
    *,
    actor: Union["User", int, None] = None,
    actor_id: int | None = None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    request_id: int | None = None,
    from_state: str | enum.Enum | None = None,
    to_state: str | enum.Enum | None = None,
    comment: str | None = None,
) -> AuditLog:
    """Write one append-only audit entry and flush (never commit).

    Args:
        db: the caller's session — the entry joins the caller's transaction.
        actor: the `User` who acted (or pass `actor_id=` instead).
        actor_id: id of the user who acted, when no `User` object is handy.
        action: one of the `AuditAction` vocabulary strings (schema.md §4.6).
        entity_type: one of the `EntityType` values. Inferred as "request"
            when omitted and `request_id` is given.
        entity_id: id of the affected row. Inferred from `request_id` under
            the same condition as `entity_type`.
        request_id: the request the entry belongs to, or None for
            workflow/user events (schema.md §4.6).
        from_state / to_state: the transition, for request events.
        comment: the approver's note / rejection reason, if any.

    Returns:
        The flushed `AuditLog` row (it has an `id`, but it is NOT committed —
        rolling back the caller's transaction removes it).

    Raises:
        ValueError: a caller bug — no actor, no action, or no entity. These
            are programming errors, not user errors, so they must never be
            converted into an HTTP response.
    """
    # --- resolve who acted ---------------------------------------------------
    resolved_actor_id = actor_id
    if actor is not None:
        resolved_actor_id = actor if isinstance(actor, int) else actor.id
    if resolved_actor_id is None:
        raise ValueError("audit.record() requires an actor (or actor_id)")

    # --- resolve what was acted on -------------------------------------------
    resolved_entity_type = _as_plain(entity_type)
    resolved_entity_id = entity_id
    if request_id is not None:
        if resolved_entity_type is None:
            resolved_entity_type = EntityType.REQUEST
        if resolved_entity_id is None:
            resolved_entity_id = request_id
    if not action:
        raise ValueError("audit.record() requires an action")
    if resolved_entity_type is None or resolved_entity_id is None:
        raise ValueError(
            "audit.record() requires entity_type and entity_id "
            "(or request_id, from which they are inferred)"
        )

    entry = AuditLog(
        actor_id=resolved_actor_id,
        request_id=request_id,
        action=_as_plain(action),
        entity_type=resolved_entity_type,
        entity_id=resolved_entity_id,
        from_state=_as_plain(from_state),
        to_state=_as_plain(to_state),
        comment=comment,
    )
    db.add(entry)
    # THE rule of this file: flush so the row exists inside the transaction,
    # but NEVER commit — the caller owns the transaction boundary.
    db.flush()
    return entry


__all__ = ["record"]
