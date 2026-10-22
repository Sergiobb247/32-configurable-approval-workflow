"""Permission matrix — the security surface, tested cell by cell.

Owner: Person C — Approval Engine (Eze Chebem).
Contract: docs/test-plan.md section 4.2 and docs/technical-spec.md section 4.1.

These tests are deliberately free of the database and of FastAPI: `permissions`
is a pure module, so the whole matrix runs in milliseconds. Production passes ORM
rows; here we pass `SimpleNamespace` stand-ins with the same attributes, which is
also why a rule can never quietly depend on a session.

Naming: `test_<behaviour>_<condition>_<expected>` (test-plan.md section 2).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models import Action, RequestStatus, Role
from app.permissions import (
    DENY_ADMIN_DECIDE,
    DENY_ALREADY_ACTED,
    DENY_DECIDED,
    DENY_NOT_SUBMITTER,
    DENY_NOT_YOURS,
    DENY_SELF_APPROVAL,
    DENY_WRONG_ROLE,
    can_act,
    can_view,
    current_step_role,
)

# --- helpers -----------------------------------------------------------------


def user(role: Role | str = Role.EMPLOYEE, *, user_id: int = 100):
    return SimpleNamespace(id=user_id, role=Role(role), full_name=f"User {user_id}")


def request(
    *,
    status: RequestStatus | str = RequestStatus.PENDING,
    index: int = 0,
    roles: tuple[Role | str, ...] = (Role.MANAGER, Role.FINANCE),
    submitter_id: int = 1,
):
    snapshot = [
        {"order": position + 1, "role": Role(role).value, "label": f"Step {position + 1}"}
        for position, role in enumerate(roles)
    ]
    return SimpleNamespace(
        id=7,
        status=RequestStatus(status),
        current_step_index=index,
        steps_snapshot=snapshot,
        submitted_by=submitter_id,
    )


# --- viewing -----------------------------------------------------------------


def test_view_submitter_can_see_own_request():
    req = request(submitter_id=10)
    assert can_view(user(Role.EMPLOYEE, user_id=10), req).allowed


def test_view_unrelated_employee_is_refused():
    req = request(submitter_id=10)
    decision = can_view(user(Role.EMPLOYEE, user_id=11), req)
    assert not decision.allowed
    assert decision.reason == DENY_NOT_YOURS


def test_view_admin_can_see_any_request():
    req = request(submitter_id=10)
    assert can_view(user(Role.ADMIN, user_id=99), req).allowed


def test_view_role_in_the_chain_can_see_it():
    # A manager may open a request even when it is finance's turn: they are part
    # of the chain and will need the context when it comes back to them.
    req = request(index=1, submitter_id=10)
    assert can_view(user(Role.MANAGER, user_id=12), req).allowed


# --- submitting ---------------------------------------------------------------


def test_submit_submitter_is_allowed():
    req = request(status=RequestStatus.DRAFT, submitter_id=10)
    assert can_act(user(Role.EMPLOYEE, user_id=10), req, Action.SUBMIT).allowed


def test_submit_someone_else_is_refused():
    req = request(status=RequestStatus.DRAFT, submitter_id=10)
    decision = can_act(user(Role.EMPLOYEE, user_id=11), req, Action.SUBMIT)
    assert not decision.allowed
    assert decision.reason == DENY_NOT_SUBMITTER


# --- cancelling ---------------------------------------------------------------


def test_cancel_submitter_can_withdraw_pending_request():
    req = request(submitter_id=10)
    assert can_act(user(Role.EMPLOYEE, user_id=10), req, Action.CANCEL).allowed


def test_cancel_stranger_is_refused():
    req = request(submitter_id=10)
    decision = can_act(user(Role.EMPLOYEE, user_id=11), req, Action.CANCEL)
    assert not decision.allowed
    assert decision.reason == DENY_NOT_YOURS


def test_cancel_admin_can_stop_anyones_request():
    # Decisions log #3: stopping is safe and visible; approving is not.
    req = request(submitter_id=10)
    assert can_act(user(Role.ADMIN, user_id=99), req, Action.CANCEL).allowed


def test_cancel_after_approval_is_refused():
    req = request(status=RequestStatus.APPROVED, submitter_id=10)
    decision = can_act(user(Role.EMPLOYEE, user_id=10), req, Action.CANCEL)
    assert not decision.allowed
    assert decision.reason == DENY_DECIDED


# --- approving and rejecting --------------------------------------------------


def test_approve_current_step_role_is_allowed():
    req = request(index=0, roles=(Role.MANAGER, Role.FINANCE), submitter_id=10)
    assert can_act(user(Role.MANAGER, user_id=12), req, Action.APPROVE).allowed


def test_approve_future_step_role_is_refused():
    req = request(index=0, roles=(Role.MANAGER, Role.FINANCE), submitter_id=10)
    decision = can_act(user(Role.FINANCE, user_id=13), req, Action.APPROVE)
    assert not decision.allowed
    assert decision.reason == DENY_WRONG_ROLE


def test_approve_past_step_role_is_refused():
    req = request(index=1, roles=(Role.MANAGER, Role.FINANCE), submitter_id=10)
    decision = can_act(user(Role.MANAGER, user_id=12), req, Action.APPROVE)
    assert not decision.allowed
    assert decision.reason == DENY_WRONG_ROLE


def test_approve_own_request_is_refused():
    req = request(index=0, roles=(Role.MANAGER, Role.FINANCE), submitter_id=12)
    decision = can_act(user(Role.MANAGER, user_id=12), req, Action.APPROVE)
    assert not decision.allowed
    assert decision.reason == DENY_SELF_APPROVAL


def test_approve_by_admin_is_refused():
    # No override exists. This is the headline claim of the product.
    req = request(index=0, roles=(Role.MANAGER, Role.FINANCE), submitter_id=10)
    decision = can_act(user(Role.ADMIN, user_id=99), req, Action.APPROVE)
    assert not decision.allowed
    assert decision.reason == DENY_ADMIN_DECIDE


def test_approve_twice_by_same_user_is_refused():
    req = request(index=1, roles=(Role.MANAGER, Role.MANAGER), submitter_id=10)
    decision = can_act(
        user(Role.MANAGER, user_id=12), req, Action.APPROVE, already_acted=True
    )
    assert not decision.allowed
    assert decision.reason == DENY_ALREADY_ACTED


def test_approve_repeated_role_by_a_second_user_is_allowed():
    # MANAGER -> MANAGER needs two different managers, not one clicking twice.
    req = request(index=1, roles=(Role.MANAGER, Role.MANAGER), submitter_id=10)
    assert can_act(
        user(Role.MANAGER, user_id=14), req, Action.APPROVE, already_acted=False
    ).allowed


def test_reject_follows_the_same_rules_as_approve():
    req = request(index=0, roles=(Role.MANAGER,), submitter_id=10)
    assert can_act(user(Role.MANAGER, user_id=12), req, Action.REJECT).allowed
    assert not can_act(user(Role.EMPLOYEE, user_id=12), req, Action.REJECT).allowed


# --- terminal states -----------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [RequestStatus.APPROVED, RequestStatus.REJECTED, RequestStatus.CANCELLED],
)
@pytest.mark.parametrize("action", list(Action))
def test_terminal_request_refuses_every_action(status, action):
    req = request(status=status, submitter_id=10)
    decision = can_act(user(Role.ADMIN, user_id=99), req, action)
    assert not decision.allowed
    assert decision.reason == DENY_DECIDED


# --- step helpers ---------------------------------------------------------------


def test_current_step_role_is_none_unless_pending():
    assert current_step_role(request(status=RequestStatus.DRAFT)) is None
    assert current_step_role(request(index=0)) == Role.MANAGER
    assert current_step_role(request(index=1)) == Role.FINANCE


def test_current_step_role_is_none_when_index_is_outside_the_chain():
    req = request(index=5, roles=(Role.MANAGER,))
    assert current_step_role(req) is None
