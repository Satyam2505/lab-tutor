"""Classroom routes.

Every route here re-checks the caller's role through `require_faculty` /
`require_student`, and every faculty route additionally proves ownership
of the specific classroom through `FacultyScope` before touching it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import classrooms as classroom_service
from backend import idempotency
from backend.auth import Principal, require_faculty, require_student
from backend.data_access import FacultyScope, StudentScope
from backend.auth.dependencies import faculty_scope, student_scope
from backend.db import get_session
from backend.models import Classroom, Enrollment
from backend.tier1_compute.experiments import all_plugins

router = APIRouter(prefix="/api/classrooms", tags=["classrooms"])


class CreateClassroomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=128)


class JoinRequest(BaseModel):
    join_code: str = Field(min_length=1, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=128)


class ActiveExperimentRequest(BaseModel):
    experiment_id: str | None = None


class JoinOpenRequest(BaseModel):
    join_open: bool


@router.get("/experiments")
async def list_experiments(principal: Principal = Depends(require_faculty)) -> dict:
    """Experiments a professor may set as active, and whether each is usable."""
    return {
        "experiments": [
            {
                "id": p.id,
                "title": p.title,
                "kind": p.kind,
                "ready": p.is_ready,
                "manual_reference": p.manual_reference,
            }
            for p in all_plugins()
        ]
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_classroom(
    body: CreateClassroomRequest,
    principal: Principal = Depends(require_faculty),
    db: AsyncSession = Depends(get_session),
) -> dict:
    key = body.idempotency_key or idempotency.derive_key("create_classroom", body.name)
    try:
        claim = await idempotency.claim(
            db, user_id=principal.id, scope="create_classroom", key=key
        )
    except idempotency.DuplicateInFlight as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not claim.fresh:
        return claim.replayed_response or {}

    classroom = await classroom_service.create_classroom(
        db, owner_id=principal.id, name=body.name
    )
    payload = {
        "id": classroom.id,
        "name": classroom.name,
        "join_code": classroom.join_code,
        "join_open": classroom.join_open,
        "active_experiment_id": classroom.active_experiment_id,
    }
    await idempotency.complete(db, claim, payload)
    await db.commit()
    return payload


@router.get("/mine")
async def my_classrooms(
    scope: FacultyScope = Depends(faculty_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    rows = list((await db.scalars(scope.select_classrooms())).all())
    out = []
    for classroom in rows:
        out.append(
            {
                "id": classroom.id,
                "name": classroom.name,
                "join_code": classroom.join_code,
                "join_open": classroom.join_open,
                "active_experiment_id": classroom.active_experiment_id,
                "student_count": await classroom_service.student_count(db, classroom.id),
            }
        )
    return {"classrooms": out}


@router.get("/enrolled")
async def enrolled_classrooms(
    scope: StudentScope = Depends(student_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """A student sees only classrooms they are enrolled in, and no join code."""
    enrollments = await scope.all(Enrollment)
    ids = [e.classroom_id for e in enrollments]
    if not ids:
        return {"classrooms": []}
    rows = list((await db.scalars(select(Classroom).where(Classroom.id.in_(ids)))).all())
    return {
        "classrooms": [
            {
                "id": c.id,
                "name": c.name,
                "active_experiment_id": c.active_experiment_id,
            }
            for c in rows
        ]
    }


@router.post("/join")
async def join(
    body: JoinRequest,
    principal: Principal = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict:
    key = body.idempotency_key or idempotency.derive_key("join", body.join_code)
    try:
        claim = await idempotency.claim(db, user_id=principal.id, scope="join", key=key)
    except idempotency.DuplicateInFlight as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not claim.fresh:
        return claim.replayed_response or {}

    try:
        classroom = await classroom_service.join_classroom(
            db, student_id=principal.id, join_code=body.join_code
        )
    except classroom_service.JoinClosed as exc:
        await idempotency.release(db, claim)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except classroom_service.ClassroomError as exc:
        await idempotency.release(db, claim)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    payload = {
        "id": classroom.id,
        "name": classroom.name,
        "active_experiment_id": classroom.active_experiment_id,
    }
    await idempotency.complete(db, claim, payload)
    await db.commit()
    return payload


async def _owned_classroom(scope: FacultyScope, classroom_id: str) -> Classroom:
    classroom = await scope.get_classroom(classroom_id)
    if classroom is None:
        # Indistinguishable from "does not exist": a professor should not be
        # able to probe for the existence of another section's classroom.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Classroom not found"
        )
    return classroom


@router.patch("/{classroom_id}/active-experiment")
async def set_active_experiment(
    classroom_id: str,
    body: ActiveExperimentRequest,
    scope: FacultyScope = Depends(faculty_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    classroom = await _owned_classroom(scope, classroom_id)
    try:
        await classroom_service.set_active_experiment(
            db, classroom, experiment_id=body.experiment_id
        )
    except classroom_service.ClassroomError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    await db.commit()
    return {"id": classroom.id, "active_experiment_id": classroom.active_experiment_id}


@router.patch("/{classroom_id}/join-open")
async def set_join_open(
    classroom_id: str,
    body: JoinOpenRequest,
    scope: FacultyScope = Depends(faculty_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    classroom = await _owned_classroom(scope, classroom_id)
    await classroom_service.set_join_open(db, classroom, open_=body.join_open)
    await db.commit()
    return {"id": classroom.id, "join_open": classroom.join_open}


@router.get("/{classroom_id}/roster")
async def roster(
    classroom_id: str,
    scope: FacultyScope = Depends(faculty_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    await _owned_classroom(scope, classroom_id)
    rows = await classroom_service.roster_with_users(db, classroom_id)
    return {
        "students": [
            {"id": user.id, "email": user.email, "name": user.name,
             "joined_at": enrollment.joined_at.isoformat()}
            for enrollment, user in rows
        ]
    }
