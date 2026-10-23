"""Test factories — make_user, make_workflow, make_request.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/test-plan.md §2 — "Nobody hand-builds rows in a test."

* Factories commit by default: API tests need rows visible to the request
  lifecycle, and a row that is only flushed surprises beginners. Pass
  ``commit=False`` when a test wants to manage its own transaction (e.g.
  Person D's rollback tests).
* Fixture setup may write `Request.status` directly — that is the explicit
  "beyond fixtures" exception to the one-writer rule (technical-spec.md §2).
  Nothing else outside the engine may.
* User emails are auto-unique per test run (`user3@test.io`), so tests never
  collide on the unique constraint unless they choose the same email on
  purpose.
"""

from __future__ import annotations

import enum
import itertools
from decimal import Decimal
from typing import Sequence

from sqlalchemy.orm import Session

from app.models import (
    Request,
    RequestStatus,
    Role,
    User,
    Workflow,
    WorkflowStep,
)

DEFAULT_PASSWORD = "Password123!"  # same as the demo accounts (schema.md §6)

# Hashing uses bcrypt directly (NOT app.auth.security and NOT passlib):
# factories must stay honest regardless of how Person A wires hashing, and
# passlib 1.7.4 is incompatible with bcrypt>=5 (its self-test raises
# "password cannot be longer than 72 bytes"). Direct bcrypt.hashpw produces
# standard $2b$ hashes that any verifier — passlib included — accepts.
try:  # pragma: no cover - the fallback exists for passlib-only installs
    import bcrypt as _bcrypt
except ImportError:  # pragma: no cover
    _bcrypt = None
    from passlib.context import CryptContext

    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_hash_cache: dict[str, str] = {}

_email_counter = itertools.count(1)


def hash_password(raw: str) -> str:
    """A real bcrypt hash. One hash per distinct password per test run —
    hashing is deliberately slow; the suite shouldn't pay for it 73 times."""
    if raw not in _hash_cache:
        if _bcrypt is not None:
            _hash_cache[raw] = _bcrypt.hashpw(
                raw.encode("utf-8"), _bcrypt.gensalt()
            ).decode("utf-8")
        else:  # pragma: no cover
            _hash_cache[raw] = _pwd_context.hash(raw)
    return _hash_cache[raw]


def _as_role(role: Role | str) -> Role:
    return role if isinstance(role, Role) else Role(str(role))


def _as_status(status: RequestStatus | str) -> RequestStatus:
    return status if isinstance(status, RequestStatus) else RequestStatus(str(status))


def make_user(
    db: Session,
    *,
    email: str | None = None,
    full_name: str | None = None,
    role: Role | str = Role.EMPLOYEE,
    password: str = DEFAULT_PASSWORD,
    is_active: bool = True,
    commit: bool = True,
) -> User:
    """A user with a real bcrypt hash of `password`, so login tests exercise
    the genuine verify path."""
    email = email or f"user{next(_email_counter)}@test.io"
    user = User(
        email=email,
        full_name=full_name or email.split("@")[0].replace(".", " ").title(),
        role=_as_role(role),
        password_hash=hash_password(password),
        is_active=is_active,
    )
    db.add(user)
    _finish(db, user, commit)
    return user


def make_workflow(
    db: Session,
    *,
    name: str = "Expense approval",
    description: str | None = None,
    steps: Sequence[tuple[Role | str, str]] = (
        (Role.MANAGER, "Line manager"),
        (Role.FINANCE, "Finance review"),
    ),
    is_active: bool = True,
    created_by: User | None = None,
    commit: bool = True,
) -> Workflow:
    """A workflow with an ordered chain.

    `steps` is a sequence of (required_role, label) pairs; positions are
    assigned 1-based and contiguous — workflows built here never violate the
    chain rules. Pass an empty sequence to test the "≥ 1 step" guards.
    """
    if created_by is None:
        created_by = make_user(db, role=Role.ADMIN, full_name="Factory Admin")
    workflow = Workflow(
        name=name,
        description=description,
        is_active=is_active,
        created_by=created_by.id,
    )
    workflow.steps = [
        WorkflowStep(
            step_order=index,
            required_role=_as_role(role),
            label=label,
        )
        for index, (role, label) in enumerate(steps, start=1)
    ]
    db.add(workflow)
    _finish(db, workflow, commit)
    return workflow


def make_request(
    db: Session,
    *,
    workflow: Workflow | None = None,
    submitter: User | None = None,
    title: str = "Laptop replacement",
    description: str | None = None,
    amount: Decimal | int | str = "450000.00",
    status: RequestStatus | str = RequestStatus.DRAFT,
    current_step_index: int = 0,
    snapshot: list[dict] | None = None,
    version: int = 1,
    decided_at=None,
    commit: bool = True,
) -> Request:
    """A request in any state.

    Two conveniences keep fixtures honest:

    * when the request is past DRAFT and no snapshot is given, the chain is
      frozen from the workflow's live steps via `Request.snapshot_from_steps`
      — the same function the engine calls at submit time;
    * when the status is terminal and `decided_at` is not given, it is set to
      now, preserving the invariant "terminal => decided_at set".
    """
    status = _as_status(status)
    if workflow is None:
        workflow = make_workflow(db)
    if submitter is None:
        submitter = make_user(db, full_name="Factory Submitter")
    if snapshot is None and status != RequestStatus.DRAFT:
        snapshot = Request.snapshot_from_steps(workflow.steps)
    if decided_at is None and status in (
        RequestStatus.APPROVED,
        RequestStatus.REJECTED,
        RequestStatus.CANCELLED,
    ):
        decided_at = _now()
    request = Request(
        workflow_id=workflow.id,
        submitted_by=submitter.id,
        title=title,
        description=description,
        amount=amount if isinstance(amount, Decimal) else Decimal(str(amount)),
        status=status,
        current_step_index=current_step_index,
        steps_snapshot=snapshot or [],
        version=version,
        decided_at=decided_at,
    )
    request.submitter = submitter
    request.workflow = workflow
    db.add(request)
    _finish(db, request, commit)
    return request


def _now():
    from app.models.common import utcnow

    return utcnow()


def _finish(db: Session, obj, commit: bool) -> None:
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(obj)


# The enum re-exports keep factory call sites terse:
#     make_request(db, status=RequestStatus.PENDING)
__all__ = [
    "DEFAULT_PASSWORD",
    "RequestStatus",
    "Role",
    "hash_password",
    "make_request",
    "make_user",
    "make_workflow",
]

# Silence a false positive: `enum` documents intended use for role coercion.
assert enum.Enum is not None
