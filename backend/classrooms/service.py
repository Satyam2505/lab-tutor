"""Classroom creation, joining, and active-experiment management.

A classroom is persistent: one per lab section, created once and reused
all semester. What changes weekly is `active_experiment_id`, which the
professor sets before each session. Every submission and Socratic session
is tagged from that field, so students never type an experiment number
and cannot submit against the wrong one.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Classroom, Enrollment, Role, User
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


class NotEnrolled(ClassroomError):
    pass


def generate_join_code() -> str:
    """A high-entropy code, grouped for reading aloud in a lab."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(20))
    return "-".join(raw[i : i + 5] for i in range(0, 20, 5))


@dataclass(frozen=True)
class ClassroomView:
    id: str
    name: str
    join_code: str | None
    join_open: bool
    active_experiment_id: str | None
    student_count: int = 0


async def create_classroom(
    db: AsyncSession, *, owner_id: str, name: str
) -> Classroom:
    for _ in range(5):
        code = generate_join_code()
        clash = (
            await db.scalars(select(Classroom).where(Classroom.join_code == code))
        ).first()
        if clash is None:
            break
    else:  # pragma: no cover - astronomically unlikely
        raise ClassroomError("Could not generate a unique join code")

    classroom = Classroom(name=name.strip() or "Untitled section", owner_id=owner_id, join_code=code)
    db.add(classroom)
    await db.flush()
    return classroom


async def join_classroom(
    db: AsyncSession, *, student_id: str, join_code: str
) -> Classroom:
    code = (join_code or "").strip().upper()
    classroom = (
        await db.scalars(select(Classroom).where(Classroom.join_code == code))
    ).first()
    if classroom is None:
        raise ClassroomError("No classroom matches that code")
    if not classroom.join_open:
        raise JoinClosed("Joining is closed for this classroom")

    existing = (
        await db.scalars(
            select(Enrollment).where(
                Enrollment.classroom_id == classroom.id,
                Enrollment.student_id == student_id,
            )
        )
    ).first()
    if existing is None:
        db.add(Enrollment(classroom_id=classroom.id, student_id=student_id))
        await db.flush()
    return classroom


async def set_join_open(
    db: AsyncSession, classroom: Classroom, *, open_: bool
) -> Classroom:
    """Lock the roster once the section has joined."""
    classroom.join_open = open_
    await db.flush()
    return classroom


async def set_active_experiment(
    db: AsyncSession, classroom: Classroom, *, experiment_id: str | None
) -> Classroom:
    """Set the week's experiment. Validated against the plugin registry."""
    if experiment_id is not None:
        try:
            get_plugin(experiment_id)
        except UnknownExperimentError as exc:
            raise ClassroomError(str(exc)) from exc
    classroom.active_experiment_id = experiment_id
    await db.flush()
    return classroom


async def require_active_experiment(classroom: Classroom) -> str:
    if not classroom.active_experiment_id:
        raise ClassroomError(
            "This classroom has no active experiment set. The demonstrator "
            "sets it before the session begins."
        )
    return classroom.active_experiment_id


async def student_count(db: AsyncSession, classroom_id: str) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(Enrollment).where(
                Enrollment.classroom_id == classroom_id
            )
        )
        or 0
    )


async def roster_with_users(
    db: AsyncSession, classroom_id: str
) -> list[tuple[Enrollment, User]]:
    rows = await db.execute(
        select(Enrollment, User)
        .join(User, User.id == Enrollment.student_id)
        .where(Enrollment.classroom_id == classroom_id, User.role == Role.STUDENT)
        .order_by(User.email)
    )
    return list(rows.all())
