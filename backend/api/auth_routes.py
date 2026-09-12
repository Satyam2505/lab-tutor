"""OAuth sign-in/out routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import audit
from backend.auth import Principal, current_user
from backend.auth import oauth, session as session_cookie
from backend.auth.roles import DomainNotPermitted
from backend.config import get_settings
from backend.db import get_session
from backend.models import User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def login() -> RedirectResponse:
    try:
        url, state = oauth.build_authorize_url()
    except oauth.OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    response = RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    settings = get_settings()
    response.set_cookie(
        session_cookie.OAUTH_STATE_COOKIE,
        state,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=oauth.STATE_MAX_AGE_SECONDS,
        path="/",
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_session),
):
    """Server-side domain verification happens here, before any session."""
    expected = request.cookies.get(session_cookie.OAUTH_STATE_COOKIE, "")
    if not oauth.verify_state(state, expected):
        await audit.record(
            db, audit.AUTH_FAILURE, detail={"reason": "bad_oauth_state"}, commit=True
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sign-in state"
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing authorisation code"
        )

    try:
        identity = await oauth.exchange_code(code)
    except oauth.OAuthError as exc:
        await audit.record(
            db, audit.AUTH_FAILURE, detail={"reason": "exchange_failed", "error": str(exc)},
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Sign-in with Google failed"
        ) from exc

    # The email comes from Google's response, never from the client.
    try:
        role = oauth.role_or_reject(identity)
    except DomainNotPermitted:
        await audit.record(
            db,
            audit.AUTH_FAILURE,
            detail={
                "reason": "domain_rejected",
                "email": identity.email,
                "email_verified": identity.email_verified,
            },
            commit=True,
        )
        log.warning("Rejected sign-in from disallowed domain: %s", identity.email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This service is limited to institutional accounts.",
        ) from None

    user = (
        await db.scalars(select(User).where(User.google_sub == identity.subject))
    ).first()
    if user is None:
        user = User(
            google_sub=identity.subject,
            email=identity.email,
            name=identity.name,
            role=role,
        )
        db.add(user)
    else:
        user.email = identity.email
        user.name = identity.name
        user.role = role
    await db.flush()

    await audit.record(
        db, audit.AUTH_SUCCESS, user_id=user.id, detail={"role": role.value}
    )
    await db.commit()

    settings = get_settings()
    response = RedirectResponse(
        f"{settings.public_url.rstrip('/')}/", status_code=status.HTTP_303_SEE_OTHER
    )
    response.set_cookie(
        session_cookie.COOKIE_NAME,
        session_cookie.issue(user.id, user.email),
        **session_cookie.cookie_kwargs(),
    )
    response.delete_cookie(session_cookie.OAUTH_STATE_COOKIE, path="/")
    return response


@router.post("/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(session_cookie.COOKIE_NAME, path="/")
    return response


@router.get("/me")
async def me(principal: Principal = Depends(current_user)) -> dict:
    return {
        "id": principal.id,
        "email": principal.email,
        "name": principal.name,
        "role": principal.role.value,
    }
