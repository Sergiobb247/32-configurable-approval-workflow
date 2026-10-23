"""Domain models — the single import surface for the data layer.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/schema.md §7 — everybody imports like this:

    from app.models import User, Request, RequestStatus, Role

never via a deep path. Everything importable from this package is listed in
`__all__`; anything not listed here is not part of the contract.
"""

from .audit_log import AuditAction, AuditLog, EntityType
from .request import Action, Request, RequestStatus, SnapshotStep
from .user import Role, User
from .workflow import Workflow
from .workflow_step import WorkflowStep

# models/refresh_token.py is owned by Person A (foundation layer), NOT by the
# contracts layer — it is listed here only so that importing this package
# registers the class and the User.refresh_tokens string relationship
# resolves when SQLAlchemy configures the mappers. The guard keeps the
# domain layer importable on its own (e.g. in B's own tests) before A's file
# lands; in the integrated repo the import always succeeds.
try:  # pragma: no cover - presence depends on integration state
    from .refresh_token import RefreshToken
except ModuleNotFoundError:  # pragma: no cover
    RefreshToken = None  # type: ignore[assignment, misc]

__all__ = [
    "Action",
    "AuditAction",
    "AuditLog",
    "EntityType",
    "RefreshToken",
    "Request",
    "RequestStatus",
    "Role",
    "SnapshotStep",
    "User",
    "Workflow",
    "WorkflowStep",
]
