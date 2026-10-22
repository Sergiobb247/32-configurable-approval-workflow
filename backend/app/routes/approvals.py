"""Approval endpoints — inbox, approve, reject (18–20).

Owner: Person C — Approval Engine (Eze Chebem).
Contract: docs/technical-spec.md section 7.5.

The inbox is the only query in the product that filters on both the caller's
role and their own action history: a request must appear for the person whose
turn it is, and must not reappear for somebody who already acted on it (that is
what makes a chain with the same role twice work — decisions log #4).

Approve and reject are thin wrappers over `engine.decide`. Both return the
updated `RequestOut`, so the UI can re-render the chain and the timeline from one
response instead of re-fetching.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import Action, User
from app.schemas import ApproveIn, RejectIn, RequestOut
from app.schemas.request import RequestList  # not re-exported by app.schemas yet
from app.services import workflow_engine as engine

router = APIRouter(tags=["approvals"])


@router.get("/inbox", response_model=RequestList, summary="Requests waiting on my role")
def inbox(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestList:
    rows, total = engine.list_inbox(db, current_user, skip=skip, limit=limit)
    return RequestList(
        items=[engine.request_out(db, row, current_user) for row in rows],
        total=total,
    )


@router.post(
    "/requests/{request_id}/approve",
    response_model=RequestOut,
    summary="Approve the current step",
)
def approve_request(
    request_id: int,
    payload: ApproveIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestOut:
    row = engine.load_request(db, request_id)
    row = engine.decide(db, current_user, row, Action.APPROVE, payload.comment)
    return engine.request_out(db, row, current_user)


@router.post(
    "/requests/{request_id}/reject",
    response_model=RequestOut,
    summary="Reject the current step (comment required)",
)
def reject_request(
    request_id: int,
    payload: RejectIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestOut:
    row = engine.load_request(db, request_id)
    row = engine.decide(db, current_user, row, Action.REJECT, payload.comment)
    return engine.request_out(db, row, current_user)
