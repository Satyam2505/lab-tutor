"""Classroom creation, joining, membership, and class-session lifecycle.

A classroom is persistent: one per lab section, created once and reused
all semester. What changes weekly is which `ClassSession` is ACTIVE for
it -- created when faculty/admin starts a class, closed when they end it.
Every submission and Socratic session is tagged from the resolved active
session, so students never type an experiment number and cannot submit
against a stale one once class has ended.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    ClassroomRole,
    ClassSession,
    Classroom,
    ClassroomMembership,
    Role,
    SessionStatus,
    User,
)
from backend.tier1_compute.experiments.registry import (
    UnknownExperimentError,
    get_plugin,
)

#: 20 base32 characters ~= 100 bits of entropy. A short code would be
#: enumerable: with ~70 students behind it, a guessable code lets an
#: outsider join a section and see its active experiment.
JOIN_CODE_BYTES = 13
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no I/L/O/0/1


class ClassroomError(RuntimeError):
    pass


class JoinClosed(ClassroomError):
    pass


class WrongCodeRole(ClassroomError):
    """A student presented the faculty code, or vice versa. Never silently
    resolved to "the closest role" -- rejected outright."""


class NotEnrolled(ClassroomError):
    pass


class SessionAlreadyActive(ClassroomError):
    pass


class NoActiveSession(ClassroomError):
    pass


def generate_join_code() -> str:
    """A high-entropy code, grouped for reading aloud in a lab."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(20))
    return "-".join(raw[i : i + 5] for i in range(0, 20, 5))


@dataclass(frozen=True)
class ClassroomView:
    id: str
    name: str
    join_open: bool
    active_experiment_id: str | None
    student_count: int = 0


async def _unique_code(db: AsyncSession, column) -> str:
    for _ in range(5):
        code = generate_join_code()
        clash = (await db.scalars(select(Classroom).where(column == code))).first()
        if clash is None:
            return code
    raise ClassroomError("Could not generate a unique join code")  # pragma: no cover


async def create_classroom(
    db: AsyncSession, *, creator_id: str, name: str, creator_is_faculty: bool = True
) -> Classroom:
    """Create a classroom.

    If the creator is a faculty member, they're enrolled as its first
    faculty peer. If the creator is admin, no membership row is created --
    admin authority is global and does not require joining (brief §8).
    """
    student_code = await _unique_code(db, Classroom.student_join_code)
    faculty_code = await _unique_code(db, Classroom.faculty_join_code)

    classroom = Classroom(
        name=name.strip() or "Untitled section",
        student_join_code=student_code,
        faculty_join_code=faculty_code,
    )
    db.add(classroom)
    await db.flush()
    if creator_is_faculty:
        db.add(
            ClassroomMembership(
                classroom_id=classroom.id, user_id=creator_id, role=ClassroomRole.FACULTY
            )
        )
        await db.flush()
    return classroom


async def join_classroom(
    db: AsyncSession, *, user: User, join_code: str
) -> Classroom:
    """Join by whichever code matches, but only if it matches the caller's
    own platform role. A student code never admits faculty and vice versa
    -- there is no "closest role" fallback.
    """
    code = (join_code or "").strip().upper()

    classroom = (
        await db.scalars(
            select(Classroom).where(
                (Classroom.student_join_code == code)
                | (Classroom.faculty_join_code == code)
            )
        )
    ).first()
    if classroom is None:
        raise ClassroomError("No classroom matches that code")

    if code == classroom.student_join_code:
        if user.role != Role.STUDENT:
            raise WrongCodeRole("This is a student join code")
        member_role = ClassroomRole.STUDENT
    else:
        if user.role != Role.FACULTY:
            raise WrongCodeRole("This is a faculty join code")
        member_role = ClassroomRole.FACULTY

    if member_role == ClassroomRole.STUDENT and not classroom.join_open:
        raise JoinClosed("Joining is closed for this classroom")

    existing = (
        await db.scalars(
            select(ClassroomMembership).where(
                ClassroomMembership.classroom_id == classroom.id,
                ClassroomMembership.user_id == user.id,
                ClassroomMembership.role == member_role,
            )
        )
    ).first()
    if existing is not None:
        if not existing.active:
            existing.active = True
            existing.removed_at = None
            await db.flush()
        return classroom

    db.add(
        ClassroomMembership(classroom_id=classroom.id, user_id=user.id, role=member_role)
    )
    try:
        await db.flush()
    except IntegrityError:
        # Lost a race against a concurrent join from the same user (e.g. two
        # browser tabs each with their own idempotency key) -- the unique
        # constraint caught it; treat as already-joined, not a crash.
        await db.rollback()
        classroom = (
            await db.scalars(select(Classroom).where(Classroom.id == classroom.id))
        ).first()
    return classroom


async def regenerate_join_code(
    db: AsyncSession, classroom: Classroom, *, which: str
) -> Classroom:
    if which == "student":
        classroom.student_join_code = await _unique_code(db, Classroom.student_join_code)
    elif which == "faculty":
        classroom.faculty_join_code = await _unique_code(db, Classroom.faculty_join_code)
    else:
        raise ClassroomError("which must be 'student' or 'faculty'")
    await db.flush()
    return classroom


async def set_join_open(
    db: AsyncSession, classroom: Classroom, *, open_: bool
) -> Classroom:
    """Lock the roster once the section has joined."""
    classroom.join_open = open_
    await db.flush()
    return classroom


async def remove_faculty(
    db: AsyncSession, classroom_id: str, *, user_id: str
) -> None:
    stmt = select(ClassroomMembership).where(
        ClassroomMembership.classroom_id == classroom_id,
        ClassroomMembership.user_id == user_id,
        ClassroomMembership.role == ClassroomRole.FACULTY,
        ClassroomMembership.active.is_(True),
    )
    membership = (await db.scalars(stmt)).first()
    if membership is None:
        return
    from backend.models import _now

    membership.active = False
    membership.removed_at = _now()
    await db.flush()


# --- class session lifecycle ------------------------------------------------


async def get_active_session(db: AsyncSession, classroom_id: str) -> ClassSession | None:
    stmt = select(ClassSession).where(
        ClassSession.classroom_id == classroom_id,
        ClassSession.status == SessionStatus.ACTIVE,
    )
    return (await db.scalars(stmt)).first()


async def start_session(
    db: AsyncSession, classroom_id: str, *, experiment_id: str, started_by: str
) -> ClassSession:
    """Start a class. Validates the experiment, then inserts the ACTIVE
    session inside the same flush that would collide with a concurrent
    start -- two faculty pressing Start at once must not both succeed.
    """
    try:
        get_plugin(experiment_id)
    except UnknownExperimentError as exc:
        raise ClassroomError(str(exc)) from exc

    existing = await get_active_session(db, classroom_id)
    if existing is not None:
        raise SessionAlreadyActive(
            "A session is already active for this classroom. End it before "
            "starting a new one."
        )

    session = ClassSession(
        classroom_id=classroom_id,
        experiment_id=experiment_id,
        status=SessionStatus.ACTIVE,
        started_by=started_by,
    )
    db.add(session)
    try:
        await db.flush()
    except IntegrityError as exc:
        # Postgres partial-unique-index race: the loser of two concurrent
        # starts lands here instead of silently creating a second ACTIVE
        # session. (SQLite, used only by the test harness, cannot express
        # a partial unique index; the check-then-insert above is this
        # code path's best-effort equivalent there -- a known test-fidelity
        # gap, not a production one.)
        await db.rollback()
        raise SessionAlreadyActive(
            "A session is already active for this classroom."
        ) from exc
    return session


async def end_session(
    db: AsyncSession, session: ClassSession, *, ended_by: str
) -> ClassSession:
    from backend.models import _now

    if session.status != SessionStatus.ACTIVE:
        raise NoActiveSession("This session is not active.")
    session.status = SessionStatus.ENDED
    session.ended_at = _now()
    session.ended_by = ended_by
    await db.flush()
    return session


async def require_active_session(db: AsyncSession, classroom_id: str) -> ClassSession:
    session = await get_active_session(db, classroom_id)
    if session is None:
        raise ClassroomError(
            "This classroom has no active class session right now. "
            "A demonstrator starts one before the session begins."
        )
    return session


async def student_count(db: AsyncSession, classroom_id: str) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(ClassroomMembership).where(
                ClassroomMembership.classroom_id == classroom_id,
                ClassroomMembership.role == ClassroomRole.STUDENT,
                ClassroomMembership.active.is_(True),
            )
        )
        or 0
    )


async def roster_with_users(
    db: AsyncSession, classroom_id: str
) -> list[tuple[ClassroomMembership, User]]:
    rows = await db.execute(
        select(ClassroomMembership, User)
        .join(User, User.id == ClassroomMembership.user_id)
        .where(
            ClassroomMembership.classroom_id == classroom_id,
            ClassroomMembership.role == ClassroomRole.STUDENT,
            ClassroomMembership.active.is_(True),
        )
        .order_by(User.email)
    )
    return list(rows.all())


async def faculty_roster_with_users(
    db: AsyncSession, classroom_id: str
) -> list[tuple[ClassroomMembership, User]]:
    rows = await db.execute(
        select(ClassroomMembership, User)
        .join(User, User.id == ClassroomMembership.user_id)
        .where(
            ClassroomMembership.classroom_id == classroom_id,
            ClassroomMembership.role == ClassroomRole.FACULTY,
            ClassroomMembership.active.is_(True),
        )
        .order_by(User.email)
    )
    return list(rows.all())
