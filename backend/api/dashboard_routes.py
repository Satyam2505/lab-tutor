"""Professor/TA dashboard routes.

Minimal by intent -- a working internal tool for the pilot, not a
polished product. Every route is faculty-gated *and* ownership-scoped:
`FacultyScope` restricts each query to classrooms this account owns, so
one section's staff cannot read another's.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import audit, idempotency
from backend.auth import Principal, require_faculty
from backend.auth.dependencies import faculty_scope
from backend.classrooms import roster_with_users
from backend.config import get_settings
from backend.data_access import FacultyScope
from backend.db import get_session
from backend.models import (
    AuditLog,
    Diagnosis,
    Escalation,
    StudentSummary,
    Submission,
    SummaryJob,
    User,
)
from backend.summaries import run_job, start_job

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class GenerateSummariesRequest(BaseModel):
    #: Named students to regenerate. Empty means "only those not yet done",
    #: which is what makes re-clicking the button free.
    refresh_student_ids: list[str] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=128)


class ResolveRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


async def _owned(scope: FacultyScope, classroom_id: str) -> None:
    if not await scope.owns_classroom(classroom_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Classroom not found"
        )


@router.get("/classrooms/{classroom_id}/submissions")
async def submissions(
    classroom_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    scope: FacultyScope = Depends(faculty_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """All submissions in a classroom with pass/fail/escalated status."""
    await _owned(scope, classroom_id)

    stmt = scope.select(Submission).where(Submission.classroom_id == classroom_id)
    rows = list((await db.scalars(stmt)).all())
    diag_rows = list(
        (
            await db.scalars(
                scope.select(Diagnosis).where(Diagnosis.classroom_id == classroom_id)
            )
        ).all()
    )
    diagnoses = {d.submission_id: d for d in diag_rows}
    emails = {
        u.id: u.email
        for u in (await db.scalars(select(User))).all()
    }

    out = []
    for submission in sorted(rows, key=lambda s: s.created_at, reverse=True):
        diagnosis = diagnoses.get(submission.id)
        record = {
            "submission_id": submission.id,
            "student_id": submission.student_id,
            "student_email": emails.get(submission.student_id, ""),
            "experiment_id": submission.experiment_id,
            "created_at": submission.created_at.isoformat(),
            "status": diagnosis.status.value if diagnosis else "pending",
            "tier": diagnosis.tier if diagnosis else None,
            "signature": diagnosis.signature_code if diagnosis else None,
            "expected_value": diagnosis.expected_value if diagnosis else None,
            "reported_value": submission.reported_value,
            "explanation": diagnosis.phrased_text if diagnosis else "",
            "low_confidence": diagnosis.low_confidence if diagnosis else False,
        }
        if status_filter and record["status"] != status_filter:
            continue
        out.append(record)
    return {"submissions": out}


@router.get("/classrooms/{classroom_id}/escalations")
async def escalations(
    classroom_id: str,
    unresolved_only: bool = Query(default=True),
    scope: FacultyScope = Depends(faculty_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """The Tier 3 review queue -- the cases needing a human during the pilot."""
    await _owned(scope, classroom_id)
    stmt = scope.select(Escalation).where(Escalation.classroom_id == classroom_id)
    if unresolved_only:
        stmt = stmt.where(Escalation.resolved.is_(False))
    rows = list((await db.scalars(stmt)).all())

    diagnoses = {
        d.id: d
        for d in (
            await db.scalars(
                scope.select(Diagnosis).where(Diagnosis.classroom_id == classroom_id)
            )
        ).all()
    }
    emails = {u.id: u.email for u in (await db.scalars(select(User))).all()}

    return {
        "escalations": [
            {
                "id": e.id,
                "student_id": e.student_id,
                "student_email": emails.get(e.student_id, ""),
                "reason": e.reason,
                "resolved": e.resolved,
                "created_at": e.created_at.isoformat(),
                "expected_value": (
                    diagnoses[e.diagnosis_id].expected_value
                    if e.diagnosis_id in diagnoses
                    else None
                ),
                "reported_value": (
                    diagnoses[e.diagnosis_id].reported_value
                    if e.diagnosis_id in diagnoses
                    else None
                ),
                "experiment_id": (
                    diagnoses[e.diagnosis_id].detail.get("experiment")
                    if e.diagnosis_id in diagnoses
                    else None
                ),
            }
            for e in sorted(rows, key=lambda e: e.created_at, reverse=True)
        ]
    }


@router.post("/escalations/{escalation_id}/resolve")
async def resolve_escalation(
    escalation_id: str,
    body: ResolveRequest,
    principal: Principal = Depends(require_faculty),
    scope: FacultyScope = Depends(faculty_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    escalation = await scope.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Escalation not found"
        )
    escalation.resolved = True
    escalation.resolved_by = principal.id
    escalation.resolution_note = body.note or None
    await db.commit()
    return {"id": escalation.id, "resolved": True}


@router.get("/audit")
async def audit_log(
    event: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    principal: Principal = Depends(require_faculty),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Diagnoses, escalations and auth failures, newest first."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if event:
        stmt = stmt.where(AuditLog.event == event)
    rows = list((await db.scalars(stmt)).all())
    return {
        "events": [
            {
                "id": r.id,
                "event": r.event,
                "user_id": r.user_id,
                "classroom_id": r.classroom_id,
                "detail": r.detail,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/classrooms/{classroom_id}/summaries", status_code=status.HTTP_202_ACCEPTED)
async def generate_summaries(
    classroom_id: str,
    body: GenerateSummariesRequest,
    background: BackgroundTasks,
    principal: Principal = Depends(require_faculty),
    scope: FacultyScope = Depends(faculty_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Start the async summary job. Returns immediately with a job id."""
    classroom = await scope.get_classroom(classroom_id)
    if classroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Classroom not found"
        )
    if not classroom.active_experiment_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Set the active experiment before generating summaries.",
        )
    experiment_id = classroom.active_experiment_id

    key = body.idempotency_key or idempotency.derive_key(
        "summaries", classroom_id, experiment_id, sorted(body.refresh_student_ids)
    )
    try:
        claim = await idempotency.claim(
            db, user_id=principal.id, scope="summaries", key=key
        )
    except idempotency.DuplicateInFlight as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not claim.fresh:
        return claim.replayed_response or {}

    roster = await roster_with_users(db, classroom_id)
    student_ids = [user.id for _, user in roster]

    # An explicit refresh is the only thing that deletes existing summaries.
    if body.refresh_student_ids:
        await scope.purge_summaries(
            classroom_id, experiment_id, body.refresh_student_ids
        )

    job = await start_job(
        db,
        classroom_id=classroom_id,
        experiment_id=experiment_id,
        requested_by=principal.id,
        student_ids=student_ids,
    )
    payload = {"job_id": job.id, "total": job.total, "status": job.status}
    await idempotency.complete(db, claim, payload)
    await db.commit()

    background.add_task(
        run_job, job.id, student_ids, workers=get_settings().summary_workers
    )
    return payload


@router.get("/summaries/jobs/{job_id}")
async def summary_job_status(
    job_id: str,
    scope: FacultyScope = Depends(faculty_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Progress for the visible status indicator."""
    job = (await db.scalars(select(SummaryJob).where(SummaryJob.id == job_id))).first()
    if job is None or not await scope.owns_classroom(job.classroom_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {
        "job_id": job.id,
        "status": job.status,
        "total": job.total,
        "completed": job.completed,
        "skipped": job.skipped,
        "error": job.error,
    }


@router.get("/classrooms/{classroom_id}/summaries")
async def list_summaries(
    classroom_id: str,
    scope: FacultyScope = Depends(faculty_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Professor-visible only. No student route returns these."""
    await _owned(scope, classroom_id)
    rows = list(
        (
            await db.scalars(
                scope.select(StudentSummary).where(
                    StudentSummary.classroom_id == classroom_id
                )
            )
        ).all()
    )
    emails = {u.id: u.email for u in (await db.scalars(select(User))).all()}
    return {
        "summaries": [
            {
                "student_id": s.student_id,
                "student_email": emails.get(s.student_id, ""),
                "experiment_id": s.experiment_id,
                "text": s.text,
                "flagged": s.flagged,
                "flag_reason": s.flag_reason,
                "generated_at": s.generated_at.isoformat(),
            }
            for s in sorted(rows, key=lambda s: emails.get(s.student_id, ""))
        ]
    }
