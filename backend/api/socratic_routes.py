"""Socratic-mode routes.

The reveal endpoint is the only place a final answer leaves this system,
and it consults exactly one thing: the server-side `all_steps_complete`
flag, set by Tier 1 verification. The chat endpoint cannot reach that
value at all -- see `backend/answer_gate`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import audit, ratelimit
from backend.answer_gate import PrematureRevealError
from backend.auth import Principal, require_student
from backend.auth.dependencies import student_scope
from backend.data_access import StudentScope
from backend.db import get_session
from backend.extraction import ExtractionError, extract_submission, parse_number
from backend.models import ChatMessage, Classroom, SocraticAttempt, SocraticSession
from backend.rag import templates
from backend.socratic_engine import (
    compute_reveal,
    handle_attempt,
    present_step,
    steps_for,
    tutor_reply,
)
from backend.tier1_compute.experiments import (
    ManualNotTranscribedError,
    UnknownExperimentError,
    get_plugin,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/socratic", tags=["socratic"])


class StartSessionRequest(BaseModel):
    classroom_id: str


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class AttemptRequest(BaseModel):
    #: The student's own readings for this step.
    data: dict[str, Any] = Field(default_factory=dict)
    value: Any = None


async def _load_session(scope: StudentScope, session_id: str) -> SocraticSession:
    session = await scope.get(SocraticSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return session


def _plugin_for(session: SocraticSession):
    try:
        return get_plugin(session.experiment_id)
    except UnknownExperimentError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/session", status_code=status.HTTP_201_CREATED)
async def start_session(
    body: StartSessionRequest,
    principal: Principal = Depends(require_student),
    scope: StudentScope = Depends(student_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Resume the student's session for the classroom's active experiment."""
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

    existing = await scope.all(
        SocraticSession,
        SocraticSession.classroom_id == body.classroom_id,
        SocraticSession.experiment_id == classroom.active_experiment_id,
    )
    session = existing[0] if existing else None
    if session is None:
        session = SocraticSession(
            student_id=principal.id,
            classroom_id=body.classroom_id,
            experiment_id=classroom.active_experiment_id,
        )
        db.add(session)
        await db.flush()
        await db.commit()

    plugin = _plugin_for(session)
    try:
        prompt = present_step(plugin, session.current_step)
        total = len(steps_for(plugin))
    except ManualNotTranscribedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "This experiment is not set up for guided mode yet. "
                f"({exc})"
            ),
        ) from exc

    return {
        "session_id": session.id,
        "experiment_id": session.experiment_id,
        "current_step": session.current_step,
        "total_steps": total,
        "prompt": prompt,
        "complete": session.all_steps_complete,
    }


@router.post("/session/{session_id}/attempt")
async def attempt(
    session_id: str,
    body: AttemptRequest,
    principal: Principal = Depends(require_student),
    scope: StudentScope = Depends(student_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Verify the current step against the student's own data."""
    session = await _load_session(scope, session_id)
    if session.all_steps_complete:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Every step is already verified for this session.",
        )
    plugin = _plugin_for(session)

    numeric_keys = tuple(k for k, v in body.data.items() if not isinstance(v, (list, tuple)))
    series_keys = tuple(k for k, v in body.data.items() if isinstance(v, (list, tuple)))
    extracted = extract_submission(
        body.data, numeric_fields=numeric_keys, series_fields=series_keys
    )
    if not extracted.ok:
        return {
            "passed": False,
            "current_step": session.current_step,
            "message": "; ".join(extracted.errors),
            "hint_level": 0,
        }

    submitted: float | None = None
    if body.value is not None:
        try:
            submitted = parse_number(body.value, "value")
        except ExtractionError as exc:
            return {
                "passed": False,
                "current_step": session.current_step,
                "message": str(exc),
                "hint_level": 0,
            }

    # Accumulate the student's own readings across steps.
    merged = dict(session.student_data or {})
    merged.update(extracted.values)

    attempts_on_step = int(
        await db.scalar(
            select(func.count())
            .select_from(SocraticAttempt)
            .where(
                SocraticAttempt.session_id == session.id,
                SocraticAttempt.step_index == session.current_step,
            )
        )
        or 0
    )

    try:
        outcome = handle_attempt(
            plugin,
            step_index=session.current_step,
            attempts_on_step=attempts_on_step,
            student_data=merged,
            submitted_value=submitted,
        )
    except ManualNotTranscribedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    db.add(
        SocraticAttempt(
            session_id=session.id,
            student_id=principal.id,
            step_index=session.current_step,
            submitted_value=submitted,
            passed=outcome.passed,
            hint_level=outcome.hint_level,
            detail=outcome.detail,
        )
    )

    session.student_data = merged
    if outcome.passed:
        if outcome.advanced_to is not None:
            session.current_step = outcome.advanced_to
        if outcome.all_steps_complete:
            session.all_steps_complete = True
            await audit.record(
                db, audit.REVEAL_GRANTED, user_id=principal.id,
                classroom_id=session.classroom_id,
                detail={"session": session.id, "experiment": session.experiment_id},
            )

    db.add(
        ChatMessage(
            session_id=session.id,
            student_id=principal.id,
            classroom_id=session.classroom_id,
            experiment_id=session.experiment_id,
            author="tutor",
            content=outcome.message,
        )
    )
    await db.commit()

    total = len(steps_for(plugin))
    return {
        "passed": outcome.passed,
        "current_step": session.current_step,
        "total_steps": total,
        "message": outcome.message,
        "hint_level": outcome.hint_level,
        "complete": session.all_steps_complete,
        "prompt": (
            present_step(plugin, session.current_step)
            if not session.all_steps_complete
            else ""
        ),
    }


@router.post("/session/{session_id}/message")
async def message(
    session_id: str,
    body: MessageRequest,
    principal: Principal = Depends(require_student),
    scope: StudentScope = Depends(student_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """One conversational turn.

    Whatever the student writes -- including a demand for the answer, a
    claim of being staff, or a claim that the system is broken -- the
    model answering them was never given the final value.
    """
    session = await _load_session(scope, session_id)
    plugin = _plugin_for(session)

    limit = ratelimit.check_socratic_turn(principal.id)
    if not limit.allowed:
        await audit.record(
            db, audit.RATE_LIMITED, user_id=principal.id,
            classroom_id=session.classroom_id, detail={"scope": "socratic"}, commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You are sending messages too quickly; wait a moment.",
            headers={"Retry-After": str(int(limit.retry_after_seconds) + 1)},
        )

    db.add(
        ChatMessage(
            session_id=session.id,
            student_id=principal.id,
            classroom_id=session.classroom_id,
            experiment_id=session.experiment_id,
            author="student",
            content=body.message,
        )
    )

    try:
        steps = steps_for(plugin)
    except ManualNotTranscribedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    step = steps[min(session.current_step, len(steps) - 1)]
    attempts_on_step = int(
        await db.scalar(
            select(func.count())
            .select_from(SocraticAttempt)
            .where(
                SocraticAttempt.session_id == session.id,
                SocraticAttempt.step_index == session.current_step,
            )
        )
        or 0
    )

    # The hint rung is chosen here, by attempt count -- not by the model,
    # and not by anything in the student's message.
    hint = (
        templates.hint_text(min(attempts_on_step, 3), step.hints)
        if attempts_on_step
        else ""
    )

    reply = await tutor_reply(
        student_message=body.message,
        step_prompt=step.prompt,
        step_index=session.current_step,
        total_steps=len(steps),
        hint_text=hint or templates.refusal_text(),
        attempts_on_this_step=attempts_on_step,
        all_steps_complete=session.all_steps_complete,
        retrieval_query=f"{plugin.title} {step.key}",
    )

    if reply.redacted:
        await audit.record(
            db, audit.ANSWER_GATE_REDACTION, user_id=principal.id,
            classroom_id=session.classroom_id,
            detail={"session": session.id, "step": session.current_step},
        )

    db.add(
        ChatMessage(
            session_id=session.id,
            student_id=principal.id,
            classroom_id=session.classroom_id,
            experiment_id=session.experiment_id,
            author="tutor",
            content=reply.text,
        )
    )
    await db.commit()

    return {
        "reply": reply.text,
        "current_step": session.current_step,
        "total_steps": len(steps),
        "complete": session.all_steps_complete,
    }


@router.post("/session/{session_id}/reveal")
async def reveal(
    session_id: str,
    principal: Principal = Depends(require_student),
    scope: StudentScope = Depends(student_scope),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """The separate, non-LLM reveal path. Refuses until verification passes."""
    session = await _load_session(scope, session_id)
    plugin = _plugin_for(session)

    try:
        text = compute_reveal(
            plugin,
            all_steps_complete=session.all_steps_complete,
            student_data=session.student_data or {},
            student_final_value=None,
        )
    except PrematureRevealError:
        # Deliberately the same response whatever the reason, so probing
        # this endpoint reveals nothing about how close the student is.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "The final value is available once every step has been "
                "verified. Keep going -- the current step is still open."
            ),
        ) from None
    except ManualNotTranscribedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    session.revealed = True
    db.add(
        ChatMessage(
            session_id=session.id,
            student_id=principal.id,
            classroom_id=session.classroom_id,
            experiment_id=session.experiment_id,
            author="tutor",
            content=text,
        )
    )
    await db.commit()
    return {"reveal": text, "source": "template"}
