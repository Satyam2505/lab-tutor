"""Diagnostic-mode routes: submit a finished record, get a diagnosis back."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import audit, idempotency, ratelimit
from backend.auth import Principal, require_student
from backend.auth.dependencies import student_scope
from backend.data_access import StudentScope
from backend.db import get_session
from backend.extraction import extract_submission
from backend.models import Classroom, Diagnosis, DiagnosisStatus, Escalation, Submission
from backend.pipeline import run_diagnosis
from backend.tier1_compute.experiments import UnknownExperimentError, get_plugin

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/submissions", tags=["diagnostic"])


class SubmissionRequest(BaseModel):
    classroom_id: str
    #: Raw form fields. The experiment is NOT taken from here -- it comes
    #: from the classroom's active experiment, so a student cannot submit
    #: against a different one.
    data: dict[str, Any] = Field(default_factory=dict)
    reported_value: Any = None
    remarks: str = ""
    idempotency_key: str | None = Field(default=None, max_length=128)


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit(
    body: SubmissionRequest,
    principal: Principal = Depends(require_student),
    scope: StudentScope = Depends(student_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    limit = ratelimit.check_submission(principal.id)
    if not limit.allowed:
        await audit.record(
            db, audit.RATE_LIMITED, user_id=principal.id,
            detail={"scope": "submission"}, commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many submissions; wait a moment before trying again.",
            headers={"Retry-After": str(int(limit.retry_after_seconds) + 1)},
        )

    if not await scope.is_enrolled(body.classroom_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Classroom not found"
        )

    classroom = (
        await db.scalars(select(Classroom).where(Classroom.id == body.classroom_id))
    ).first()
    if classroom is None or not classroom.active_experiment_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active experiment is set for this classroom yet.",
        )
    experiment_id = classroom.active_experiment_id

    try:
        plugin = get_plugin(experiment_id)
    except UnknownExperimentError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    key = body.idempotency_key or idempotency.derive_key(
        "submit", body.classroom_id, experiment_id, sorted(body.data.items()),
        body.reported_value,
    )
    try:
        claim = await idempotency.claim(
            db, user_id=principal.id, scope="submit", key=key
        )
    except idempotency.DuplicateInFlight as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not claim.fresh:
        await audit.record(
            db, audit.IDEMPOTENT_REPLAY, user_id=principal.id,
            classroom_id=body.classroom_id, detail={"scope": "submit"}, commit=True,
        )
        return claim.replayed_response or {}

    # --- extraction -------------------------------------------------------
    numeric_keys = tuple(
        k for k, v in body.data.items() if not isinstance(v, (list, tuple))
    )
    series_keys = tuple(
        k for k, v in body.data.items() if isinstance(v, (list, tuple))
    )
    extracted = extract_submission(
        body.data, numeric_fields=numeric_keys, series_fields=series_keys
    )

    reported: float | None = None
    if body.reported_value is not None:
        from backend.extraction import ExtractionError, parse_number

        try:
            reported = parse_number(body.reported_value, "reported_value")
        except ExtractionError as exc:
            extracted.errors.append(str(exc))

    submission = Submission(
        student_id=principal.id,
        classroom_id=body.classroom_id,
        experiment_id=experiment_id,
        raw_payload={"data": body.data, "reported_value": body.reported_value,
                     "remarks": body.remarks},
        reported_value=reported,
    )
    db.add(submission)
    await db.flush()

    if not extracted.ok:
        diagnosis = Diagnosis(
            submission_id=submission.id,
            student_id=principal.id,
            classroom_id=body.classroom_id,
            status=DiagnosisStatus.INVALID,
            tier=1,
            reported_value=reported,
            detail={"errors": extracted.errors},
            phrased_text="This submission could not be checked: "
            + "; ".join(extracted.errors),
        )
        db.add(diagnosis)
        payload = _diagnosis_payload(submission, diagnosis)
        await idempotency.complete(db, claim, payload)
        await audit.record(
            db, audit.DIAGNOSIS_MADE, user_id=principal.id,
            classroom_id=body.classroom_id,
            detail={"status": "invalid", "experiment": experiment_id},
        )
        await db.commit()
        return payload

    # --- tiers 1-3, then phrasing ----------------------------------------
    outcome = await run_diagnosis(
        plugin,
        inputs=extracted.values,
        reported_value=reported,
        remarks=body.remarks,
        student_text=body.remarks,
    )

    diagnosis = Diagnosis(
        submission_id=submission.id,
        student_id=principal.id,
        classroom_id=body.classroom_id,
        status=outcome.status,
        tier=outcome.tier,
        signature_code=outcome.signature_code,
        expected_value=outcome.expected_value,
        reported_value=outcome.reported_value,
        detail=outcome.detail,
        action=outcome.action,
        phrased_text=outcome.phrased_text,
        phrasing_source=outcome.phrasing_source,
        low_confidence=outcome.low_confidence,
    )
    db.add(diagnosis)
    await db.flush()

    if outcome.escalated:
        db.add(
            Escalation(
                diagnosis_id=diagnosis.id,
                classroom_id=body.classroom_id,
                student_id=principal.id,
                reason=outcome.escalate_reason or "unresolved",
            )
        )
        await audit.record(
            db, audit.TIER3_ESCALATION, user_id=principal.id,
            classroom_id=body.classroom_id,
            detail={"experiment": experiment_id, "reason": outcome.escalate_reason},
        )

    await audit.record(
        db, audit.DIAGNOSIS_MADE, user_id=principal.id,
        classroom_id=body.classroom_id,
        detail={
            "experiment": experiment_id,
            "status": outcome.status.value,
            "tier": outcome.tier,
            "signature": outcome.signature_code,
            "phrasing_source": outcome.phrasing_source,
        },
    )

    payload = _diagnosis_payload(submission, diagnosis, citation=outcome.citation)
    await idempotency.complete(db, claim, payload)
    await db.commit()
    return payload


def _diagnosis_payload(
    submission: Submission, diagnosis: Diagnosis, citation: str = ""
) -> dict:
    """What a student sees. Never includes another student's anything."""
    return {
        "submission_id": submission.id,
        "experiment_id": submission.experiment_id,
        "status": diagnosis.status.value,
        "tier": diagnosis.tier,
        "action": diagnosis.action.value,
        "explanation": diagnosis.phrased_text,
        "citation": citation,
        "low_confidence": diagnosis.low_confidence,
    }


@router.get("/mine")
async def my_submissions(
    scope: StudentScope = Depends(student_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    submissions = await scope.all(Submission)
    diagnoses = {d.submission_id: d for d in await scope.all(Diagnosis)}
    return {
        "submissions": [
            {
                "id": s.id,
                "experiment_id": s.experiment_id,
                "created_at": s.created_at.isoformat(),
                "status": (
                    diagnoses[s.id].status.value if s.id in diagnoses else "pending"
                ),
                "explanation": (
                    diagnoses[s.id].phrased_text if s.id in diagnoses else ""
                ),
            }
            for s in sorted(submissions, key=lambda s: s.created_at, reverse=True)
        ]
    }


@router.get("/{submission_id}")
async def get_submission(
    submission_id: str,
    scope: StudentScope = Depends(student_scope),
) -> dict:
    """Scoped fetch.

    Another student's id returns 404 because the row is never selected --
    the owner predicate is part of the query, not a check afterwards.
    """
    submission = await scope.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    diagnoses = await scope.all(Diagnosis, Diagnosis.submission_id == submission_id)
    diagnosis = diagnoses[0] if diagnoses else None
    return {
        "id": submission.id,
        "experiment_id": submission.experiment_id,
        "created_at": submission.created_at.isoformat(),
        "reported_value": submission.reported_value,
        "status": diagnosis.status.value if diagnosis else "pending",
        "explanation": diagnosis.phrased_text if diagnosis else "",
        "action": diagnosis.action.value if diagnosis else "none",
    }
