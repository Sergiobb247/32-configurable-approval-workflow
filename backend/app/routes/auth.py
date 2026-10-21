"""Authentication routes — register, login, refresh rotation, logout, me.

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/technical-spec.md §6 (endpoints 1–5), §7.1, §8, §10.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AUTH_REQUIRED_DETAIL,
    get_current_user,
    optional_current_user,
)
from app.auth.security import (
    create_access_token,
    dummy_verify,
    ensure_utc,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expires_at,
    verify_password,
)
from app.database import get_db
from app.models import RefreshToken, Role, User
from app.models.common import utcnow
from app.schemas import (
    LoginIn,
    LoginOut,
    RefreshIn,
    RegisterIn,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS_DETAIL = "Invalid email or password"
EMAIL_TAKEN_DETAIL = "An account with this email already exists"
ACCOUNT_DEACTIVATED_DETAIL = "Account is deactivated"


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterIn,
    db: Session = Depends(get_db),
) -> User:
    """Create a new active `EMPLOYEE` account (schema.md §4.1, spec §7.1)."""
    existing = db.query(User).filter(User.email == payload.email).one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=EMAIL_TAKEN_DETAIL,
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=Role.EMPLOYEE,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=EMAIL_TAKEN_DETAIL,
        ) from exc
    db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=LoginOut,
    status_code=status.HTTP_200_OK,
)
def login(
    payload: LoginIn,
    db: Session = Depends(get_db),
) -> LoginOut:
    """Authenticate credentials and issue an access + rotating refresh pair."""
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None:
        dummy_verify()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS_DETAIL,
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS_DETAIL,
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ACCOUNT_DEACTIVATED_DETAIL,
        )

    raw_refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_token_expires_at(),
        )
    )
    db.commit()
    db.refresh(user)

    access_token = create_access_token(user.id, user.role)
    return LoginOut(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


@router.post(
    "/refresh",
    response_model=TokenOut,
    status_code=status.HTTP_200_OK,
)
def refresh_tokens(
    payload: RefreshIn,
    db: Session = Depends(get_db),
) -> TokenOut:
    """Atomically revoke the presented refresh token and issue a fresh pair."""
    now = utcnow()
    presented_hash = hash_refresh_token(payload.refresh_token)
    token_row = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == presented_hash)
        .one_or_none()
    )

    if (
        token_row is None
        or token_row.revoked_at is not None
        or ensure_utc(token_row.expires_at) <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_REQUIRED_DETAIL,
        )

    user = db.get(User, token_row.user_id)
    if user is None or not user.is_active:
        token_row.revoked_at = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_REQUIRED_DETAIL,
        )

    # Rotate in one transaction: old token becomes single-use, new row inserted.
    token_row.revoked_at = now
    new_raw_refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(new_raw_refresh),
            expires_at=refresh_token_expires_at(now),
        )
    )
    db.commit()

    return TokenOut(
        access_token=create_access_token(user.id, user.role),
        refresh_token=new_raw_refresh,
        token_type="bearer",
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def logout(
    payload: RefreshIn | None = Body(default=None),
    current_user: User | None = Depends(optional_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Revoke the session's refresh token(s) and return `204 No Content`.

    Supports both client styles seamlessly:
    * `POST /auth/logout` with `{"refresh_token": "..."}` (revokes that token)
    * `POST /auth/logout` with `Authorization: Bearer ...` and no body (revokes
      all active refresh tokens for that user)
    """
    if current_user is None and payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_REQUIRED_DETAIL,
        )

    now = utcnow()
    if payload is not None:
        token_hash = hash_refresh_token(payload.refresh_token)
        token_row = (
            db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .one_or_none()
        )
        if (
            token_row is not None
            and token_row.revoked_at is None
            and (current_user is None or token_row.user_id == current_user.id)
        ):
            token_row.revoked_at = now
    elif current_user is not None:
        (
            db.query(RefreshToken)
            .filter(
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked_at.is_(None),
            )
            .update({RefreshToken.revoked_at: now}, synchronize_session=False)
        )

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated caller's live profile and role."""
    return current_user
