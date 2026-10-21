"""The request state machine — pure, exhaustive, and import-free.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/technical-spec.md §4 and docs/app-flow.md §1.

    class TransitionError(Exception): ...
    TRANSITIONS: dict[tuple[RequestStatus, Action], RequestStatus]
    def can_transition(status, action) -> bool
    def next_state(status, action, current_step, total_steps) -> (status, step)

WHY THIS MODULE IMPORTS NOTHING FROM THE APP
--------------------------------------------
technical-spec.md §1: "state_machine.py imports nothing from FastAPI or
SQLAlchemy — it is plain Python." That rule is what makes the core rule of
the product exhaustively testable in milliseconds (test_state_machine.py
runs the full 5-states × 4-actions matrix with no database), and it lets
Person C trust the engine's brain without standing up the app.

The enums (`RequestStatus`, `Action`) are defined in `app/models/` per
schema.md §7 — but they subclass ``str``, so a member compares and hashes
exactly like its value ("DRAFT"). This module therefore keeps the table in
plain strings at runtime and accepts either strings or enum members on the
way in. Type annotations reference the real contract types; the runtime
never imports them. There is one test (test_state_machine_imports_nothing_
from_the_framework) that proves this module loads without SQLAlchemy or
FastAPI present at all.

WHERE ERRORS GO
---------------
* TransitionError  -> the engine maps it to HTTP 409 ("not now, or not any
  more"). When the current state is terminal the message is the catalogue
  sentence "This request has already been decided" (technical-spec.md §8).
* ValueError       -> invalid step arithmetic (total_steps < 1, or a current
  step outside the chain). That is a caller bug or a validation gap — the
  workflow "≥ 1 step" rule must have already rejected it with 422 — so it
  must never surface as an HTTP response.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - annotations only, never resolved at runtime
    from app.models import Action, RequestStatus

# --- the five states and four actions, as strings (see module docstring) -----
DRAFT = "DRAFT"
PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
CANCELLED = "CANCELLED"

SUBMIT = "SUBMIT"
APPROVE = "APPROVE"
REJECT = "REJECT"
CANCEL = "CANCEL"

ALL_STATES: tuple[str, ...] = (DRAFT, PENDING, APPROVED, REJECTED, CANCELLED)
ALL_ACTIONS: tuple[str, ...] = (SUBMIT, APPROVE, REJECT, CANCEL)

# The whole machine in one table (app-flow.md §1): every (state, action) pair
# NOT listed here is illegal. Five entries — that is the entire contract.
#
# Typed by contract as dict[tuple[RequestStatus, Action], RequestStatus];
# stored with str keys, which is the same thing at lookup time because those
# enums subclass str (RequestStatus.DRAFT == "DRAFT" and hashes alike).
TRANSITIONS: dict[tuple[str, str], str] = {
    (DRAFT, SUBMIT): PENDING,       # submitter files the draft -> step 1 waits
    (DRAFT, CANCEL): CANCELLED,     # withdraw before anyone sees it
    (PENDING, APPROVE): PENDING,    # advance one step (final step -> APPROVED,
                                    # resolved inside next_state)
    (PENDING, REJECT): REJECTED,    # chain stops immediately
    (PENDING, CANCEL): CANCELLED,   # withdrawn while waiting (audited)
}

# States with no outgoing arrow. Derived from the table — never edited by
# hand — so "terminal" has exactly one definition in the codebase.
TERMINAL_STATES: frozenset[str] = frozenset(
    state for state in ALL_STATES if all(source != state for source, _ in TRANSITIONS)
)

# The catalogue sentence for acting on a terminal request (technical-spec §8).
_ALREADY_DECIDED = "This request has already been decided"


class TransitionError(Exception):
    """Raised by next_state when the (status, action) pair is illegal.
    can_transition never raises — use it when you want a boolean."""


def _norm(value: "RequestStatus | Action | str") -> str:
    """Accept a contract enum member or a plain string; return the string."""
    return value.value if isinstance(value, Enum) else str(value)


def can_transition(status: "RequestStatus | str", action: "Action | str") -> bool:
    """True iff (status, action) is one of the five legal pairs."""
    return (_norm(status), _norm(action)) in TRANSITIONS


def is_terminal(status: "RequestStatus | str") -> bool:
    """True in APPROVED / REJECTED / CANCELLED."""
    return _norm(status) in TERMINAL_STATES


def legal_actions(status: "RequestStatus | str") -> tuple[str, ...]:
    """The actions allowed from `status` (empty for terminal states)."""
    source = _norm(status)
    return tuple(action for (s, action) in TRANSITIONS if s == source)


def next_state(
    status: "RequestStatus | str",
    action: "Action | str",
    current_step: int,
    total_steps: int,
) -> tuple[str, int]:
    """Apply `action` and return (new_status, new_current_step_index).

    Step indices are 0-based, matching Request.current_step_index (§4.5):

    * DRAFT --SUBMIT--> (PENDING, 0)
    * PENDING --APPROVE--> (PENDING, current_step + 1) on an intermediate step
    * PENDING --APPROVE--> (APPROVED, total_steps) on the final step
    * --REJECT--> (REJECTED, current_step)   — index stays where it was refused
    * --CANCEL--> (CANCELLED, current_step)

    Raises:
        TransitionError: the (status, action) pair is illegal -> HTTP 409.
        ValueError: impossible step arithmetic -> a caller bug, never HTTP.
    """
    source, move = _norm(status), _norm(action)

    if not can_transition(source, move):
        if is_terminal(source):
            raise TransitionError(_ALREADY_DECIDED)
        raise TransitionError(f"Cannot {move.lower()} a request that is {source}")

    if move == SUBMIT:
        # From DRAFT, always onto the first step of the chain.
        if total_steps < 1:
            raise ValueError("A workflow needs at least one step")
        return TRANSITIONS[(source, move)], 0

    if move == APPROVE and source == PENDING:
        if total_steps < 1:
            raise ValueError("A workflow needs at least one step")
        if not 0 <= current_step < total_steps:
            raise ValueError(
                f"current_step {current_step} is outside a chain of {total_steps}"
            )
        if current_step + 1 == total_steps:
            return APPROVED, total_steps
        return PENDING, current_step + 1

    # REJECT or CANCEL: chain stops, index stays where the request died.
    return TRANSITIONS[(source, move)], current_step
