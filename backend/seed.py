"""Seed the demo data — idempotent, synthetic, safe to re-run.

Owner: Person D — Workflows, Audit & Ops (Moses Abigail).
Contract: docs/schema.md §6, docs/technical-spec.md §11.

Usage:
    cd backend && python seed.py

Creates (schema.md §6): 6 users across all four roles (all with the
demo-only password `Password123!`), 2 workflows, and 4 requests in
different states so every screen has something honest to show — an inbox
with an item in it, a finished approval, a rejection with a comment, and a
draft.

Two deliberate notes for the team:

1. **The large-expense chain ends in a SECOND MANAGER, not ADMIN.**
   The team rule — confirmed by Persons A and B — is absolute: an admin
   can never approve any request (explanation.md §5, test-plan §4.2/§4.5).
   Person D enforces it at configuration time: `routes/workflows.py`
   refuses (422) to create, re-chain, or activate any workflow containing
   an ADMIN step, because such a chain could never complete. The seed
   therefore uses MANAGER -> FINANCE -> MANAGER (two *different* managers,
   per the one-action-per-user rule), matching Person B's integration
   test chain.

2. **Seeded requests are historical fixtures.** Runtime state changes go
   through Person C's engine only (the one-writer rule). Like Person B's
   test factories — the documented fixture exception — this script
   constructs demo requests in their seeded states, and writes the matching
   audit history for every one of them through `services/audit.record()`
   in the same transaction, so no seeded state is ever unaudited.

Idempotency (schema.md §6): if ANY user already exists, the script prints
"already seeded" and exits without changing anything.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app import models  # noqa: F401  (register every table on Base.metadata)
from app.auth.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models import (
    AuditAction,
    EntityType,
    Request,
    RequestStatus,
    Role,
    User,
    Workflow,
    WorkflowStep,
)
from app.models.common import utcnow
from app.services import audit

DEMO_PASSWORD = "Password123!"  # demo-only, documented in the README (§6)


def _make_user(db: Session, *, email: str, full_name: str, role: Role) -> User:
    user = User(
        email=email,
        full_name=full_name,
        role=role,
        password_hash=hash_password(DEMO_PASSWORD),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _make_workflow(
    db: Session,
    *,
    name: str,
    description: str,
    steps: list[tuple[Role, str]],
    created_by: User,
) -> Workflow:
    workflow = Workflow(
        name=name,
        description=description,
        is_active=True,
        created_by=created_by.id,
    )
    workflow.steps = [
        WorkflowStep(step_order=index, required_role=role, label=label)
        for index, (role, label) in enumerate(steps, start=1)
    ]
    db.add(workflow)
    db.flush()
    audit.record(
        db,
        actor=created_by,
        action=AuditAction.WORKFLOW_CREATED,
        entity_type=EntityType.WORKFLOW,
        entity_id=workflow.id,
        request_id=None,
    )
    return workflow


def _record_request_history(
    db: Session, request: Request, history: list[tuple]
) -> None:
    """Write a seeded request's audit history through the one writer.

    Each entry is (actor, action, from_state, to_state, comment).
    """
    for actor, action, from_state, to_state, comment in history:
        audit.record(
            db,
            actor=actor,
            action=action,
            entity_type=EntityType.REQUEST,
            entity_id=request.id,
            request_id=request.id,
            from_state=from_state,
            to_state=to_state,
            comment=comment,
        )


def seed(db: Session) -> bool:
    """Populate demo data. Returns True if seeding happened, else False."""
    if db.query(User).first() is not None:
        print("already seeded")
        return False

    # --- users (schema.md §6) ------------------------------------------------
    admin = _make_user(
        db, email="admin@demo.io", full_name="Chidi Eze", role=Role.ADMIN
    )
    manager1 = _make_user(
        db, email="manager1@demo.io", full_name="Bola Ade", role=Role.MANAGER
    )
    manager2 = _make_user(
        db, email="manager2@demo.io", full_name="Tunde Okafor", role=Role.MANAGER
    )
    finance = _make_user(
        db, email="finance@demo.io", full_name="Ngozi Eze", role=Role.FINANCE
    )
    employee1 = _make_user(
        db, email="employee1@demo.io", full_name="Ada Obi", role=Role.EMPLOYEE
    )
    employee2 = _make_user(
        db, email="employee2@demo.io", full_name="Ibrahim Musa", role=Role.EMPLOYEE
    )
    # manager2 exists for the concurrency + repeated-role demos (§6);
    # employee2 exists so empty states can be shown honestly. Finance has
    # not acted yet at seed time — the laptop request is waiting for her.
    _ = (manager2, finance, employee2)

    # --- workflows (see the ADMIN-step note in the module docstring) ---------
    large_expense = _make_workflow(
        db,
        name="Expense approval (> ₦100,000)",
        description="Manager, then finance, then a second manager",
        steps=[
            (Role.MANAGER, "Line manager"),
            (Role.FINANCE, "Finance review"),
            (Role.MANAGER, "Second manager sign-off"),
        ],
        created_by=admin,
    )
    small_expense = _make_workflow(
        db,
        name="Small expense (≤ ₦100,000)",
        description="Line manager only",
        steps=[(Role.MANAGER, "Line manager")],
        created_by=admin,
    )

    # --- requests (schema.md §6), each with its matching audit history -------
    now = utcnow()

    # 1. Laptop replacement — PENDING at step 2, so finance has an inbox item.
    laptop = Request(
        workflow_id=large_expense.id,
        submitted_by=employee1.id,
        title="Laptop replacement",
        description="MacBook died — replacement needed to keep working.",
        amount=Decimal("450000.00"),
        status=RequestStatus.PENDING,
        current_step_index=1,
        steps_snapshot=Request.snapshot_from_steps(large_expense.steps),
        version=3,  # created (1) -> submitted (2) -> approved at step 1 (3)
        decided_at=None,
    )
    db.add(laptop)
    db.flush()
    _record_request_history(
        db,
        laptop,
        [
            (employee1, AuditAction.REQUEST_CREATED, None, "DRAFT", None),
            (employee1, AuditAction.SUBMITTED, "DRAFT", "PENDING", None),
            (manager1, AuditAction.APPROVED, "PENDING", "PENDING", "Within budget"),
        ],
    )

    # 2. Team lunch — APPROVED (single-step chain, decided).
    lunch = Request(
        workflow_id=small_expense.id,
        submitted_by=employee1.id,
        title="Team lunch",
        description="End-of-sprint team lunch.",
        amount=Decimal("75000.00"),
        status=RequestStatus.APPROVED,
        current_step_index=1,  # == total_steps: final step approved (§4.5)
        steps_snapshot=Request.snapshot_from_steps(small_expense.steps),
        version=3,
        decided_at=now,
    )
    db.add(lunch)
    db.flush()
    _record_request_history(
        db,
        lunch,
        [
            (employee1, AuditAction.REQUEST_CREATED, None, "DRAFT", None),
            (employee1, AuditAction.SUBMITTED, "DRAFT", "PENDING", None),
            (manager1, AuditAction.APPROVED, "PENDING", "APPROVED", "Approved"),
        ],
    )

    # 3. Conference travel — REJECTED at step 1, with the mandatory comment.
    travel = Request(
        workflow_id=large_expense.id,
        submitted_by=employee1.id,
        title="Conference travel",
        description="Flights and hotel for an overseas conference.",
        amount=Decimal("1200000.00"),
        status=RequestStatus.REJECTED,
        current_step_index=0,  # rejected where it stood; chain stopped
        steps_snapshot=Request.snapshot_from_steps(large_expense.steps),
        version=3,
        decided_at=now,
    )
    db.add(travel)
    db.flush()
    _record_request_history(
        db,
        travel,
        [
            (employee1, AuditAction.REQUEST_CREATED, None, "DRAFT", None),
            (employee1, AuditAction.SUBMITTED, "DRAFT", "PENDING", None),
            (
                manager1,
                AuditAction.REJECTED,
                "PENDING",
                "REJECTED",
                "Over budget this quarter",
            ),
        ],
    )

    # 4. Monitor arm — still a DRAFT (no snapshot until submit, §4.5).
    monitor_arm = Request(
        workflow_id=small_expense.id,
        submitted_by=employee1.id,
        title="Monitor arm",
        description="Ergonomic monitor arm for the desk setup.",
        amount=Decimal("40000.00"),
        status=RequestStatus.DRAFT,
        current_step_index=0,
        steps_snapshot=[],
        version=1,
        decided_at=None,
    )
    db.add(monitor_arm)
    db.flush()
    _record_request_history(
        db,
        monitor_arm,
        [(employee1, AuditAction.REQUEST_CREATED, None, "DRAFT", None)],
    )

    # The seeder owns this transaction: audit rows above were only flushed,
    # so everything (users, workflows, requests, history) lands atomically.
    db.commit()
    print("seeded: 6 users, 2 workflows, 4 requests (demo password: Password123!)")
    return True


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
