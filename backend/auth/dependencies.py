"""FastAPI dependencies for authentication and role gating.

The rule these implement: **every role-gated endpoint re-checks the
caller's role, server-side, on that specific request.** Not at login, not
from a cookie claim, not from anything the client sent. `current_user`
loads the user row and re-derives the role from the verified email
against the environment's domain lists every single time.

That costs one indexed lookup per request and removes a whole class of
bug -- a role that was correct at login but should not be now, a cookie
edited by hand, a client that decided it was faculty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import audit
from backend.auth import session as session_cookie
from backend.auth.roles import DomainNotPermitted, role_for_email
from backend.data_access import FacultyScope, StudentScope
from backend.db import get_session
from backend.models import Role, User

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, with a freshly re-derived role."""

    id: str
    email: str
    name: str
    role: Role

    @property
    def is_faculty(self) -> bool:
        return self.role is Role.FACULTY

    @property
    def is_student(self) -> bool:
        return self.role is Role.STUDENT


async def current_user(
    request: Request, db: AsyncSession = Depends(get_session)
) -> Principal:
    data = session_cookie.read(request.cookies.get(session_cookie.COOKIE_NAME))
    if not data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in"
        )

    user = (
        await db.scalars(select(User).where(User.id == data["uid"]))
    ).first()
    if user is None:
        await audit.record(
            db, audit.AUTH_FAILURE,
            detail={"reason": "session_user_missing", "uid": data["uid"]},
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer valid"
        )

    # Re-derive, every request. The stored role is display metadata only.
    try:
        role = role_for_email(user.email)
    except DomainNotPermitted:
        await audit.record(
            db, audit.AUTH_FAILURE,
            user_id=user.id,
            detail={"reason": "domain_no_longer_permitted", "email": user.email},
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account's email domain is not permitted",
        ) from None

    return Principal(id=user.id, email=user.email, name=user.name, role=role)


async def require_student(
    principal: Principal = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> Principal:
    if not principal.is_student:
        await audit.record(
            db, audit.AUTH_FAILURE,
            user_id=principal.id,
            detail={"reason": "student_role_required", "actual": principal.role.value},
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Students only"
        )
    return principal


async def require_faculty(
    principal: Principal = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> Principal:
    if not principal.is_faculty:
        await audit.record(
            db, audit.AUTH_FAILURE,
            user_id=principal.id,
            detail={"reason": "faculty_role_required", "actual": principal.role.value},
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Staff only"
        )
    return principal


async def student_scope(
    principal: Principal = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> StudentScope:
    """The only sanctioned way to read student data on a student route."""
    return StudentScope(db, principal.id)


async def faculty_scope(
    principal: Principal = Depends(require_faculty),
    db: AsyncSession = Depends(get_session),
) -> FacultyScope:
    return FacultyScope(db, principal.id)
