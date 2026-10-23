"""Application shell — app factory, CORS, error handlers, route table.

Owner: Person D — Workflows, Audit & Ops (Moses Abigail).
Contract: docs/technical-spec.md §1–§2, §5, §8, §9, §11; docs/schema.md §7.

What this file owns (progress.md task 7): creating the FastAPI app, the
public `GET /health` endpoint (endpoint 23), CORS from settings, the error
handlers that keep every error response shaped as
`{"detail": "a sentence a human can read"}` (spec §5), schema creation on
startup, and registering every router exactly once.

What this file deliberately does NOT do: any business logic. Routes live
with their owners (A: auth/users, C: requests/approvals, D:
workflows/audit), rules live in the domain layer, and no import in this
file reaches for `request.status` or `audit_logs` (the one-writer rules).

Every router is imported and registered directly. C's routers (endpoints
13–20) are part of the tree, so a broken import here fails at startup — loudly
— instead of silently serving a smaller API.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.config import settings
from app.database import Base, engine
from app.routes import approvals as approval_routes
from app.routes import audit as audit_routes
from app.routes import auth as auth_routes
from app.routes import requests as request_routes
from app.routes import users as users_routes
from app.routes import workflows as workflow_routes
from app.schemas import HealthOut


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create tables on startup (schema.md §7 — no Alembic by decision).

    `create_all` is a no-op when the tables already exist, so restarts are
    safe. Tests build their own in-memory schema via `tests/conftest.py`
    and override `get_db`; this only touches the configured database.
    """
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Configurable Approval Workflow",
    description=(
        "Employees submit requests, admins define the approval chain, "
        "approvers act in order, and nothing happens without a trace."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# --- CORS (technical-spec.md §9): explicit origins only, never "*". ---------
# The frontend (Vercel) and API (Render) are different origins; auth travels
# in an Authorization header, not cookies, so credentials are not allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# --- Error handlers: every error is {"detail": "<one readable sentence>"} ---
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Keep HTTP errors in the catalogue shape, detail always a sentence."""
    detail = exc.detail if isinstance(exc.detail, str) else "Something went wrong"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=getattr(exc, "headers", None) or {},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Flatten Pydantic's 422 list into the first human-readable sentence.

    Person B's schema validators already phrase their messages as the
    verbatim catalogue sentences of technical-spec.md §8 (e.g. "A workflow
    needs at least one step", "A comment is required when rejecting"), so
    surfacing the first one as `detail` gives the frontend one string it can
    display as-is, instead of a nested validation tree.
    """
    errors = exc.errors()
    detail = "Please check the submitted fields"
    if errors:
        message = str(errors[0].get("msg", "")).strip()
        # Pydantic prefixes ValueError messages with "Value error, ".
        if message.lower().startswith("value error,"):
            message = message[len("value error,") :].strip()
        if message:
            detail = message[0].upper() + message[1:] if len(message) > 1 else message
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    _request: Request, _exc: Exception
) -> JSONResponse:
    """Last-resort guard: never leak a stack trace to the client.

    (Registered here rather than letting Starlette's default 500 bubble up
    as plain text, so the frontend error handling has exactly one shape to
    understand. The exception itself is still logged by the server.)
    """
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side"},
    )


# --- Health (endpoint 23, public — technical-spec.md §7.6, §11) -------------
@app.get("/health", response_model=HealthOut, tags=["ops"])
def health() -> HealthOut:
    """Uptime probe for the host and the post-deploy smoke test."""
    return HealthOut(status="ok")


# --- Route table: register each owner's router exactly once (spec §6) -------
app.include_router(auth_routes.router)       # A — endpoints 1–5
app.include_router(users_routes.router)      # A — endpoints 6–7
app.include_router(workflow_routes.router)   # D — endpoints 8–12
app.include_router(audit_routes.router)      # D — endpoints 21–22


# C — endpoints 13–20 (requests + approvals). Picked up automatically the
# moment `routes/requests.py` / `routes/approvals.py` are merged; no edit to
# this file will be needed at integration time.
app.include_router(request_routes.router)    # C — endpoints 13–17
app.include_router(approval_routes.router)   # C — endpoints 18–20
