"""API schemas — the JSON contract between backend and frontend.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/technical-spec.md §7 in full. Import from this package:

    from app.schemas import RequestOut, WorkflowCreate, ApproveIn

Changes to these shapes are frozen contracts: they need a `chore(contract)`
pull request per docs/git-workflow.md §2.
"""

from .approval import ApproveIn, RejectIn
from .audit import AuditEntryDetailOut, AuditEntryOut
from .auth import LoginIn, LoginOut, RefreshIn, RegisterIn, TokenOut
from .common import ApiModel, HealthOut, ListResponse, UTCDateTime
from .request import AmountIn, MAX_AMOUNT, RequestCreate, RequestOut, StepOut, StepState
from .user import ActorSummary, UserOut, UserPatch, UserSummary
from .workflow import (
    WorkflowCreate,
    WorkflowOut,
    WorkflowPatch,
    WorkflowStepIn,
    WorkflowStepOut,
    WorkflowStepsReplace,
)

__all__ = [
    "ActorSummary",
    "AmountIn",
    "ApiModel",
    "ApproveIn",
    "AuditEntryDetailOut",
    "AuditEntryOut",
    "HealthOut",
    "ListResponse",
    "LoginIn",
    "LoginOut",
    "MAX_AMOUNT",
    "RefreshIn",
    "RegisterIn",
    "RejectIn",
    "RequestCreate",
    "RequestOut",
    "StepOut",
    "StepState",
    "TokenOut",
    "UTCDateTime",
    "UserOut",
    "UserPatch",
    "UserSummary",
    "WorkflowCreate",
    "WorkflowOut",
    "WorkflowPatch",
    "WorkflowStepIn",
    "WorkflowStepOut",
    "WorkflowStepsReplace",
]
