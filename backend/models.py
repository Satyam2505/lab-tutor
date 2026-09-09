"""SQLAlchemy ORM models.

Storage is continuous: messages, submissions and Socratic attempts are
written as they happen and tagged with (student, classroom, experiment).
There is no "close session" step -- summary generation reads whatever
exists at the moment the professor asks for it.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    STUDENT = "student"
    FACULTY = "faculty"


class DiagnosisStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    ESCALATED = "escalated"
    INVALID = "invalid"  # extraction/validation rejected the submission


class RemedialAction(str, enum.Enum):
    NONE = "none"
    FIX_IN_PLACE = "fix_in_place"
    REDO_STEP = "redo_step"
    RESTART = "restart"
    AWAIT_REVIEW = "await_review"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    # Persisted for display/audit only. Authorisation ALWAYS re-derives the
    # role from the verified email domain on the request -- never from here.
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Classroom(Base):
    __tablename__ = "classrooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # High-entropy join code (see classrooms/service.py) -- not a short
    # guessable string.
    join_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    join_open: Mapped[bool] = mapped_column(Boolean, default=True)
    # One persistent classroom per lab section, reused all semester. The
    # professor updates this before each week's session; submissions are
    # tagged from it, so students never self-report an experiment number.
    active_experiment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    owner: Mapped[User] = relationship()


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("classroom_id", "student_id", name="uq_enrollment"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), index=True)
    # Copied from the classroom's active experiment at submit time.
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    reported_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    diagnosis: Mapped["Diagnosis | None"] = relationship(back_populates="submission")


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id"), unique=True, index=True
    )
    # Denormalised so student-scoped queries need no join.
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), index=True)

    status: Mapped[DiagnosisStatus] = mapped_column(Enum(DiagnosisStatus), index=True)
    # 1, 2 or 3 -- which tier produced this outcome. 3 means "abstained".
    tier: Mapped[int] = mapped_column(Integer, index=True)
    signature_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    reported_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    action: Mapped[RemedialAction] = mapped_column(
        Enum(RemedialAction), default=RemedialAction.NONE
    )
    # Natural-language rendering. Produced by the LLM phrasing layer from
    # the already-determined diagnosis above, or by a deterministic
    # fallback template when inference is unavailable.
    phrased_text: Mapped[str] = mapped_column(Text, default="")
    phrasing_source: Mapped[str] = mapped_column(String(32), default="template")
    # True only for experiments whose plugin is explicitly low-confidence
    # (the LLM-assisted qualitative ordering check -- see ARCHITECTURE.md).
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    submission: Mapped[Submission] = relationship(back_populates="diagnosis")


class SocraticSession(Base):
    __tablename__ = "socratic_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), index=True)
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    # Set by server-side step verification only. The answer gate consults
    # this -- and nothing else -- to decide whether a reveal may happen.
    all_steps_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    revealed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class SocraticAttempt(Base):
    __tablename__ = "socratic_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("socratic_sessions.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    step_index: Mapped[int] = mapped_column(Integer)
    submitted_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean)
    # 0 = no hint needed; 1..3 = position on the adaptive hint ladder.
    hint_level: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ChatMessage(Base):
    """Continuous transcript storage. Written as messages happen."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("socratic_sessions.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), index=True)
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    author: Mapped[str] = mapped_column(String(16))  # "student" | "tutor"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SummaryJob(Base):
    __tablename__ = "summary_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), index=True)
    experiment_id: Mapped[str] = mapped_column(String(64))
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StudentSummary(Base):
    """Professor-visible only. Never returned on any student-facing route."""

    __tablename__ = "student_summaries"
    __table_args__ = (
        UniqueConstraint("student_id", "classroom_id", "experiment_id", name="uq_summary"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), index=True)
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    # A flagged transcript is still surfaced to the professor, never
    # silently dropped from the batch.
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("summary_jobs.id"), nullable=True)
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    diagnosis_id: Mapped[str] = mapped_column(ForeignKey("diagnoses.id"), index=True)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    """Queryable from the professor/TA dashboard.

    Every diagnosis, every Tier 3 escalation and every auth failure lands
    here with a timestamp and (where known) a user id.
    """

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    classroom_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class IdempotencyRecord(Base):
    """Server-side single-fire enforcement for state-changing endpoints.

    Client-side button disabling cannot survive a network retry or a
    second browser tab, so every costly action also claims a key here.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", "key", name="uq_idempotency"),
        Index("ix_idem_lookup", "user_id", "scope", "key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36))
    scope: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="in_flight")  # in_flight|done
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
