"""Exhaustive state machine tests — every state × every action.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/test-plan.md §4.1 and technical-spec.md §4.
Definition of done: this file proves the five legal arrows and forbids the
other fifteen — with no database, in milliseconds (test-plan §1).

Each test runs alone:  pytest tests/test_state_machine.py -v
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app import state_machine as sm
from app.models import Action, RequestStatus
from app.state_machine import (
    TERMINAL_STATES,
    TRANSITIONS,
    TransitionError,
    can_transition,
    is_terminal,
    legal_actions,
    next_state,
)

ALL_STATES = list(RequestStatus)
ALL_ACTIONS = list(Action)

# The five legal arrows (app-flow.md §1) — the whole contract in one set.
LEGAL = {
    (RequestStatus.DRAFT, Action.SUBMIT),
    (RequestStatus.DRAFT, Action.CANCEL),
    (RequestStatus.PENDING, Action.APPROVE),
    (RequestStatus.PENDING, Action.REJECT),
    (RequestStatus.PENDING, Action.CANCEL),
}

FULL_MATRIX = [
    pytest.param(status, action, (status, action) in LEGAL, id=f"{status.value}/{action.value}")
    for status in ALL_STATES
    for action in ALL_ACTIONS
]


# --- can_transition: the full 5 × 4 matrix --------------------------------

@pytest.mark.parametrize("status,action,expected", FULL_MATRIX)
def test_can_transition_matrix(status, action, expected):
    assert can_transition(status, action) is expected


def test_transitions_table_has_exactly_five_entries():
    # Drift guard: nobody sneaks a sixth arrow into the machine.
    assert len(TRANSITIONS) == 5


def test_terminal_states_are_derived_from_the_table():
    assert TERMINAL_STATES == frozenset(
        {RequestStatus.APPROVED.value, RequestStatus.REJECTED.value,
         RequestStatus.CANCELLED.value}
    )
    for status in ALL_STATES:
        assert is_terminal(status) is (status.value in TERMINAL_STATES)


def test_plain_strings_are_accepted():
    # The machine is import-free; strings and enum members are interchangeable.
    assert can_transition("DRAFT", "SUBMIT") is True
    assert can_transition("APPROVED", "APPROVE") is False
    assert legal_actions("DRAFT") == ("SUBMIT", "CANCEL")
    assert legal_actions("REJECTED") == ()


# --- next_state: the step arithmetic --------------------------------------

@pytest.mark.parametrize(
    "status,action,current,total,expected_status,expected_step",
    [
        pytest.param(RequestStatus.DRAFT, Action.SUBMIT, 0, 3,
                     RequestStatus.PENDING, 0, id="submit-lands-on-first-step"),
        pytest.param(RequestStatus.PENDING, Action.APPROVE, 0, 3,
                     RequestStatus.PENDING, 1, id="approve-mid-chain"),
        pytest.param(RequestStatus.PENDING, Action.APPROVE, 1, 3,
                     RequestStatus.PENDING, 2, id="approve-to-last-step"),
        pytest.param(RequestStatus.PENDING, Action.APPROVE, 2, 3,
                     RequestStatus.APPROVED, 3, id="approve-final-step-approves"),
        pytest.param(RequestStatus.PENDING, Action.REJECT, 1, 3,
                     RequestStatus.REJECTED, 1, id="reject-stops-the-chain-in-place"),
        pytest.param(RequestStatus.PENDING, Action.CANCEL, 1, 3,
                     RequestStatus.CANCELLED, 1, id="cancel-pending-stays-in-place"),
        pytest.param(RequestStatus.DRAFT, Action.CANCEL, 0, 1,
                     RequestStatus.CANCELLED, 0, id="cancel-draft"),
    ],
)
def test_next_state(status, action, current, total, expected_status, expected_step):
    new_status, new_step = next_state(status, action, current, total)
    # enum == str comparison is bidirectionally true for str-subclass enums
    assert new_status == expected_status
    assert new_step == expected_step


# --- terminal states reject everything, with the catalogue sentence --------

@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATES))
@pytest.mark.parametrize("action", ALL_ACTIONS)
def test_terminal_action_raises_transition_error(terminal, action):
    with pytest.raises(TransitionError, match="already been decided"):
        next_state(terminal, action, 0, 3)


def test_illegal_non_terminal_action_raises_transition_error():
    # DRAFT cannot be approved, and the message names the attempted action.
    with pytest.raises(TransitionError, match="Cannot approve"):
        next_state(RequestStatus.DRAFT, Action.APPROVE, 0, 3)


# --- step arithmetic misuse is a caller bug, never a 409 -------------------

@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(dict(status="DRAFT", action="SUBMIT", current_step=0, total_steps=0),
                     id="submit-with-empty-chain"),
        pytest.param(dict(status="PENDING", action="APPROVE", current_step=3, total_steps=3),
                     id="current-step-past-the-end"),
        pytest.param(dict(status="PENDING", action="APPROVE", current_step=-1, total_steps=3),
                     id="negative-current-step"),
    ],
)
def test_nonsense_step_math_raises_value_error(kwargs):
    with pytest.raises(ValueError):
        next_state(kwargs["status"], kwargs["action"],
                   kwargs["current_step"], kwargs["total_steps"])


# --- the module stays pure: no SQLAlchemy, no FastAPI ----------------------

def test_state_machine_imports_nothing_from_the_framework():
    """technical-spec.md §1: state_machine.py imports nothing from FastAPI
    or SQLAlchemy. Proven in a FRESH interpreter, so transitive imports
    count."""
    backend_root = Path(__file__).resolve().parents[1]
    probe = (
        "import sys; import app.state_machine; "
        "banned = [m for m in sys.modules if m.split('.')[0] "
        "in {'sqlalchemy', 'fastapi', 'starlette', 'pydantic'}]; "
        "sys.exit(1 if banned else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=backend_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"state_machine dragged in a framework:\n{result.stderr}"
    )
