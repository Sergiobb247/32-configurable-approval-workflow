"""Request endpoints — create, list, read, submit, cancel (13–17).

Owner: Person C — Approval Engine (Eze Chebem).
Contract: docs/technical-spec.md section 7.4 and the endpoint catalogue.

Thin by design: parse → load → authorise → call the engine → serialise. There is
no `if request.status == ...` in this file, because every rule already lives in
`permissions.py` (who) and `services/workflow_engine.py` (what is legal). If you
ever feel the urge to add one here, it belongs in the engine.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status as http_status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import Request, RequestStatus, User
from app.schemas import RequestCreate, RequestOut
from app.schemas.request import RequestList  # not re-exported by app.schemas yet
from app.services import workflow_engine as engine

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post(
    "",
    response_model=RequestOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a draft request",
)
def create_request(
    payload: RequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestOut:
    row = engine.create(
        db,
        current_user,
        workflow_id=payload.workflow_id,
        title=payload.title,
        description=payload.description,
        amount=payload.amount,
    )
    return engine.request_out(db, row, current_user)


@router.get("", response_model=RequestList, summary="List my requests")
def list_requests(
    status: RequestStatus | None = Query(
        default=None, description="Filter by state, e.g. PENDING"
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestList:
    query = engine.visible_requests_query(db, current_user)
    if status is not None:
        query = query.filter(Request.status == status)

    total = query.count()
    rows = (
        query.order_by(Request.created_at.desc(), Request.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return RequestList(
        items=[engine.request_out(db, row, current_user) for row in rows],
        total=total,
    )


@router.get(
    "/{request_id}",
    response_model=RequestOut,
    summary="One request, with step progress",
)
def get_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestOut:
    row = engine.load_request(db, request_id)
    engine.assert_visible(current_user, row)
    return engine.request_out(db, row, current_user)


@router.post(
    "/{request_id}/submit",
    response_model=RequestOut,
    summary="Submit a draft for approval (DRAFT -> PENDING)",
)
def submit_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestOut:
    row = engine.submit(db, current_user, engine.load_request(db, request_id))
    return engine.request_out(db, row, current_user)


@router.post(
    "/{request_id}/cancel",
    response_model=RequestOut,
    summary="Withdraw a request (submitter, or admin)",
)
def cancel_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestOut:
    row = engine.cancel(db, current_user, engine.load_request(db, request_id))
    return engine.request_out(db, row, current_user)
