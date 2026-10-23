"""Permission rules — may THIS user act on THIS request?

Owner: Person C — Approval Engine (Eze Chebem).
Contract: docs/technical-spec.md section 4.1, docs/explanation.md section 5.

This module answers exactly one question: *may this user do this thing to this
request?* It does NOT decide whether the transition is legal — that is
`app/state_machine.py`, and the engine asks both, in that order.

Design rules this file keeps:

* **Pure.** No database session, no FastAPI imports, no HTTP exceptions. It
  takes plain objects (the ORM models in production, ``SimpleNamespace`` in
  unit tests) and returns a ``Decision``. That is why the whole matrix can be
  tested in milliseconds and why a rule can never accidentally write a row.
* **Every refusal carries a sentence** the frontend shows verbatim
  (technical-spec.md section 8). A denial nobody can read is a support ticket.
* **No admin override.** Admins configure workflows and may cancel any
  request, but can never approve or reject one. Decisions log #3: nobody can
  manufacture an approval.
* **One action per user per request.** A user who already approved or rejected
  a request cannot act on it again. This is what makes a chain containing the
  same role twice (MANAGER -> MANAGER -> FINANCE) safe: it needs two different
  managers, not one manager clicking twice (decisions log #4).

The "already acted" fact lives in the audit trail, so the caller supplies it as
``already_acted=True``. Keeping it a parameter rather than a query is what
keeps this module free of the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.models import Action, RequestStatus, Role

# --- the catalogue sentences (technical-spec.md section 8) -------------------

DENY_SELF_APPROVAL = "You cannot approve your own request"
DENY_ADMIN_DECIDE = "Admins configure workflows; they cannot approve requests"
DENY_WRONG_ROLE = "This request is waiting on another role"
DENY_NOT_YOURS = "This request belongs to someone else"
DENY_ALREADY_ACTED = "You have already acted on this request"
DENY_NOT_SUBMITTER = "Only the person who created this request can do this"
DENY_DECIDED = "This request has already been decided"


@dataclass(frozen=True)
class Decision:
    """The verdict, plus the sentence to show if it is a refusal."""

    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:  # `if can_view(...):` reads naturally
        return self.allowed


_ALLOW = Decision(True)


def _deny(reason: str) -> Decision:
    return Decision(False, reason)


# --- small readers over the frozen snapshot ---------------------------------


def _roles(request: Any) -> list[Role]:
    """The role required at each step of the request's frozen chain."""
    roles: list[Role] = []
    for step in request.steps_snapshot or []:
        raw = step.get("role") if isinstance(step, dict) else getattr(step, "role", None)
        try:
            roles.append(Role(raw))
        except (ValueError, TypeError):  # unknown role in a snapshot: skip it
            continue
    return roles


def current_step_role(request: Any) -> Role | None:
    """The role the request is waiting on, or None if it is not waiting.

    Step indices are 0-based (Request.current_step_index); snapshot steps carry
    a 1-based ``order`` for display only. Do not confuse the two.
    """
    if request.status != RequestStatus.PENDING:
        return None
    roles = _roles(request)
    index = request.current_step_index
    if not 0 <= index < len(roles):
        return None
    return roles[index]


def is_submitter(user: Any, request: Any) -> bool:
    return request.submitted_by == user.id


def is_terminal(request: Any) -> bool:
    return request.status in {
        RequestStatus.APPROVED,
        RequestStatus.REJECTED,
        RequestStatus.CANCELLED,
    }


# --- the two questions the engine and the routes ask ------------------------


def can_view(user: Any, request: Any) -> Decision:
    """Who may see a request: the submitter, an admin, or anyone whose role
    appears anywhere in the chain (technical-spec.md section 4.1)."""
    if user.role == Role.ADMIN:
        return _ALLOW
    if is_submitter(user, request):
        return _ALLOW
    if user.role in _roles(request):
        return _ALLOW
    return _deny(DENY_NOT_YOURS)


def can_act(
    user: Any,
    request: Any,
    action: Action,
    *,
    already_acted: bool = False,
) -> Decision:
    """May `user` perform `action` on `request`?

    ``already_acted`` is supplied by the caller (the engine reads it from the
    audit trail). It is only meaningful for APPROVE / REJECT.
    """
    if is_terminal(request):
        return _deny(DENY_DECIDED)

    if action == Action.SUBMIT:
        # Only the submitter files their own draft. An admin does not fill in
        # somebody else's request — configuring the rules is their job.
        if is_submitter(user, request):
            return _ALLOW
        return _deny(DENY_NOT_SUBMITTER)

    if action == Action.CANCEL:
        # The submitter withdraws their own; an admin may stop any request
        # (decisions log #3: stopping is safe and visible, approving is not).
        if user.role == Role.ADMIN or is_submitter(user, request):
            return _ALLOW
        return _deny(DENY_NOT_YOURS)

    if action in (Action.APPROVE, Action.REJECT):
        # Order matters: the most specific, most useful sentence wins.
        if user.role == Role.ADMIN:
            return _deny(DENY_ADMIN_DECIDE)
        if is_submitter(user, request):
            return _deny(DENY_SELF_APPROVAL)
        required = current_step_role(request)
        if required is None or user.role != required:
            return _deny(DENY_WRONG_ROLE)
        if already_acted:
            return _deny(DENY_ALREADY_ACTED)
        return _ALLOW

    return _deny(DENY_WRONG_ROLE)  # unreachable: Action has four members


def can_view_any(user: Any, requests: Iterable[Any]) -> list[Any]:
    """Convenience for list endpoints: the subset `user` may see."""
    return [request for request in requests if can_view(user, request)]
