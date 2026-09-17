"""Unified AI Chat routes: modern ChatGPT-style multi-thread chat interface.

Integrates grounded retrieval Q&A and deterministic Tier 1-3 diagnostic
checking behind a single chat surface.

NOTE (found during a live verification pass, not yet resolved): this route
does NOT implement genuine step-by-step Socratic guided verification.
Any message containing numeric data is scored as a one-shot FINAL
diagnostic via the same Tier 1-3 pipeline `/api/submissions` uses --
there is no per-step hint ladder, no "step N of M" progression, and no
answer-gate-protected reveal. The real step-by-step engine
(`backend.socratic_engine.handle_attempt`, the `SocraticSession`/
`SocraticAttempt` models, and the still-fully-functional
`/api/socratic/session/*` routes in `backend/api/socratic_routes.py`) is
not called anywhere in this file. Treat "Socratic mode" as NOT present in
this unified chat surface until that gap is deliberately addressed --
see docs/handoff_phase3.md for the full writeup.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import audit, ratelimit
from backend import classrooms as classroom_service
from backend.auth import Principal, current_user
from backend.data_access import FacultyScope, StudentScope
from backend.db import get_session
from backend.models import (
    ActorType,
    ChatMessage,
    ChatMessageKind,
    ChatThread,
    Diagnosis,
    Escalation,
    RemedialAction,
    Submission,
)
from backend.pipeline import run_diagnosis
from backend.retrieval.pipeline import answer_question
from backend.socratic_engine import triage
from backend.tier1_compute.experiments import (
    UnknownExperimentError,
    get_plugin,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


def derive_title(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return "New chat"
    if len(cleaned) <= 40:
        return cleaned
    return cleaned[:40].rstrip() + "…"


class CreateThreadRequest(BaseModel):
    classroom_id: str
    experiment_id: str
    title: str | None = None


class RenameThreadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class SendChatMessageRequest(BaseModel):
    classroom_id: str
    experiment_id: str
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None


async def _actor_type_for(db: AsyncSession, principal: Principal, classroom_id: str) -> ActorType:
    if principal.is_admin:
        return ActorType.ADMIN_TEST
    if principal.is_faculty:
        return ActorType.FACULTY_TEST
    if await classroom_service.can_act_as_faculty(db, principal, classroom_id):
        return ActorType.FACULTY_TEST
    return ActorType.STUDENT


async def _resolve_session_and_experiment(
    db: AsyncSession, principal: Principal, actor_type: ActorType, classroom_id: str, experiment_id: str
) -> tuple[str | None, str]:
    if actor_type is ActorType.STUDENT:
        scope = StudentScope(db, principal.id)
        if not await scope.is_enrolled(classroom_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Classroom not found"
            )
        active = await classroom_service.get_active_session(db, classroom_id)
        if active is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No active class session for this classroom yet.",
            )
        if active.experiment_id != experiment_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Active class session experiment is {active.experiment_id}, not {experiment_id}.",
            )
        return active.id, active.experiment_id

    fscope = FacultyScope(db, principal.id)
    if not (principal.is_admin or await fscope.is_member(classroom_id)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Classroom not found"
        )
    active = await classroom_service.get_active_session(db, classroom_id)
    class_session_id = active.id if (active and active.experiment_id == experiment_id) else None
    return class_session_id, experiment_id


def _extract_numbers_dict(text: str) -> dict[str, Any]:
    """Parse key=value pairs or plain list of numbers from text for diagnostic processing."""
    result: dict[str, Any] = {}

    # Look for key=value or key: value pairs
    pairs = re.findall(r"([a-zA-Z0-9_]+)\s*[:=]\s*([-\d\.,\s\[\]]+)", text)
    for key, val_str in pairs:
        k = key.strip().lower()
        val_str = val_str.strip(" ,[]")
        if not val_str:
            continue
        if "," in val_str or " " in val_str:
            nums = [p for p in re.split(r"[\s,]+", val_str) if p]
            try:
                result[k] = [float(n) for n in nums]
            except ValueError:
                pass
        else:
            try:
                result[k] = float(val_str)
            except ValueError:
                pass

    return result



@router.get("/threads")
async def list_threads(
    classroom_id: str = Query(...),
    experiment_id: str = Query(...),
    principal: Principal = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    stmt = (
        select(ChatThread)
        .where(
            ChatThread.user_id == principal.id,
            ChatThread.classroom_id == classroom_id,
            ChatThread.experiment_id == experiment_id,
        )
        .order_by(ChatThread.updated_at.desc())
    )
    threads = list((await db.scalars(stmt)).all())
    return {
        "threads": [
            {
                "id": t.id,
                "title": t.title,
                "classroom_id": t.classroom_id,
                "experiment_id": t.experiment_id,
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat(),
            }
            for t in threads
        ]
    }


@router.post("/threads", status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: CreateThreadRequest,
    principal: Principal = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    actor_type = await _actor_type_for(db, principal, body.classroom_id)
    class_session_id, exp_id = await _resolve_session_and_experiment(
        db, principal, actor_type, body.classroom_id, body.experiment_id
    )

    thread = ChatThread(
        user_id=principal.id,
        classroom_id=body.classroom_id,
        class_session_id=class_session_id,
        experiment_id=exp_id,
        title=(body.title or "New chat").strip(),
    )
    db.add(thread)
    await db.commit()
    return {
        "id": thread.id,
        "title": thread.title,
        "classroom_id": thread.classroom_id,
        "experiment_id": thread.experiment_id,
        "created_at": thread.created_at.isoformat(),
        "updated_at": thread.updated_at.isoformat(),
    }


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    principal: Principal = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    thread = (
        await db.scalars(
            select(ChatThread).where(
                ChatThread.id == thread_id, ChatThread.user_id == principal.id
            )
        )
    ).first()
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chat thread not found"
        )

    stmt = (
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = list((await db.scalars(stmt)).all())
    return {
        "thread": {
            "id": thread.id,
            "title": thread.title,
            "classroom_id": thread.classroom_id,
            "experiment_id": thread.experiment_id,
        },
        "messages": [
            {
                "id": m.id,
                "author": m.author,
                "content": m.content,
                "kind": m.kind.value,
                "metadata": m.metadata_json or {},
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.patch("/threads/{thread_id}")
async def rename_thread(
    thread_id: str,
    body: RenameThreadRequest,
    principal: Principal = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    thread = (
        await db.scalars(
            select(ChatThread).where(
                ChatThread.id == thread_id, ChatThread.user_id == principal.id
            )
        )
    ).first()
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chat thread not found"
        )

    thread.title = body.title.strip()
    await db.commit()
    return {"id": thread.id, "title": thread.title}


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    principal: Principal = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    thread = (
        await db.scalars(
            select(ChatThread).where(
                ChatThread.id == thread_id, ChatThread.user_id == principal.id
            )
        )
    ).first()
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chat thread not found"
        )

    msgs = (
        await db.scalars(
            select(ChatMessage).where(ChatMessage.thread_id == thread_id)
        )
    ).all()
    for m in msgs:
        await db.delete(m)
    await db.delete(thread)
    await db.commit()
    return {"deleted": True}


@router.post("/messages")
async def send_message(
    body: SendChatMessageRequest,
    principal: Principal = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    actor_type = await _actor_type_for(db, principal, body.classroom_id)
    class_session_id, experiment_id = await _resolve_session_and_experiment(
        db, principal, actor_type, body.classroom_id, body.experiment_id
    )

    limit = ratelimit.check_qa_turn(principal.id)
    if not limit.allowed:
        await audit.record(
            db, audit.RATE_LIMITED, user_id=principal.id,
            classroom_id=body.classroom_id, detail={"scope": "chat"}, commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You are sending messages too quickly; wait a moment.",
            headers={"Retry-After": str(int(limit.retry_after_seconds) + 1)},
        )

    # Get or create thread
    thread: ChatThread | None = None
    if body.thread_id:
        thread = (
            await db.scalars(
                select(ChatThread).where(
                    ChatThread.id == body.thread_id, ChatThread.user_id == principal.id
                )
            )
        ).first()

    if thread is None:
        thread = ChatThread(
            user_id=principal.id,
            classroom_id=body.classroom_id,
            class_session_id=class_session_id,
            experiment_id=experiment_id,
            title=derive_title(body.message),
        )
        db.add(thread)
        await db.flush()
    elif thread.title == "New chat":
        thread.title = derive_title(body.message)

    # Record student message
    student_msg = ChatMessage(
        thread_id=thread.id,
        kind=ChatMessageKind.QA,
        session_id=None,
        class_session_id=class_session_id,
        student_id=principal.id,
        classroom_id=body.classroom_id,
        experiment_id=experiment_id,
        actor_type=actor_type,
        author="student",
        content=body.message,
    )
    db.add(student_msg)
    await db.flush()

    # --- Intelligence Routing ---
    # 1. Safety Triage
    intent = triage.classify(body.message)
    if triage.short_circuits(intent):
        reply_text = triage.fixed_response(intent) or ""
        msg_kind = ChatMessageKind.QA
        meta = {"type": "triage", "intent": intent.value}

        if actor_type is ActorType.STUDENT and triage.needs_staff_attention(intent):
            await audit.record(
                db, audit.STUDENT_FLAG, user_id=principal.id,
                classroom_id=body.classroom_id,
                detail={"intent": intent.value, "message": body.message[:500]},
            )
    else:
        # 2. Diagnostic Data Check
        extracted_dict = _extract_numbers_dict(body.message)
        plugin = None
        try:
            plugin = get_plugin(experiment_id)
        except UnknownExperimentError:
            pass

        run_diag = False
        if plugin is not None and extracted_dict:
            run_diag = True


        if run_diag and plugin is not None:
            outcome = await run_diagnosis(
                plugin,
                inputs=extracted_dict,
                reported_value=extracted_dict.get("reported_value"),
                remarks=body.message,
                student_text=body.message,
            )

            submission = Submission(
                student_id=principal.id,
                classroom_id=body.classroom_id,
                class_session_id=class_session_id,
                experiment_id=experiment_id,
                actor_type=actor_type,
                raw_payload={"data": extracted_dict, "remarks": body.message},
                reported_value=outcome.reported_value,
            )
            db.add(submission)
            await db.flush()

            diagnosis = Diagnosis(
                submission_id=submission.id,
                student_id=principal.id,
                classroom_id=body.classroom_id,
                class_session_id=class_session_id,
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

            # Anything that tells the caller to wait for a demonstrator
            # must actually reach one -- same rule and same shape as
            # backend/api/diagnostic_routes.py::submit. Without this, a
            # diagnosis computed as "escalated" or "await_review" through
            # the unified chat would never appear in the faculty review
            # queue at all.
            needs_human = outcome.escalated or outcome.action is RemedialAction.AWAIT_REVIEW
            if needs_human:
                db.add(
                    Escalation(
                        diagnosis_id=diagnosis.id,
                        classroom_id=body.classroom_id,
                        class_session_id=class_session_id,
                        student_id=principal.id,
                        reason=outcome.escalate_reason
                        or (
                            "Diagnosed, but the remedy is human review: "
                            f"{outcome.signature_code or 'unspecified'}"
                        ),
                    )
                )
                await audit.record(
                    db, audit.TIER3_ESCALATION, user_id=principal.id,
                    classroom_id=body.classroom_id,
                    class_session_id=class_session_id,
                    detail={"experiment": experiment_id, "reason": outcome.escalate_reason},
                )

            await audit.record(
                db, audit.DIAGNOSIS_MADE, user_id=principal.id,
                classroom_id=body.classroom_id,
                class_session_id=class_session_id,
                detail={"status": outcome.status.value, "experiment": experiment_id},
            )

            reply_text = outcome.phrased_text
            msg_kind = ChatMessageKind.DIAGNOSTIC
            meta = {
                "type": "diagnostic",
                "status": outcome.status.value,
                "tier": outcome.tier,
                "action": outcome.action.value,
                "explanation": outcome.phrased_text,
                "citation": outcome.citation,
                "low_confidence": outcome.low_confidence,
            }
        else:
            # 3. Grounded Q&A with Manual Retrieval
            result = await answer_question(body.message, active_experiment=experiment_id)
            reply_text = result.text
            msg_kind = ChatMessageKind.QA
            meta = {
                "type": "qa",
                "status": result.status.value,
                "citations": [
                    {"text": c.text, "page": c.page, "tier": c.tier.value}
                    for c in result.citations
                ],
                "answer_source": result.answer_source,
                "intent": intent.value,
            }

    # Record Assistant Message
    assistant_msg = ChatMessage(
        thread_id=thread.id,
        kind=msg_kind,
        session_id=None,
        class_session_id=class_session_id,
        student_id=principal.id,
        classroom_id=body.classroom_id,
        experiment_id=experiment_id,
        actor_type=actor_type,
        author="tutor",
        content=reply_text,
        metadata_json=meta,
    )
    db.add(assistant_msg)
    thread.title = thread.title  # touched
    await db.commit()

    return {
        "thread_id": thread.id,
        "thread_title": thread.title,
        "message": {
            "id": assistant_msg.id,
            "author": "tutor",
            "content": reply_text,
            "kind": msg_kind.value,
            "metadata": meta,
            "created_at": assistant_msg.created_at.isoformat(),
        },
    }
