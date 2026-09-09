"""Scoped data access -- the single place student isolation is enforced.

The rule this module exists to make structural: **a student's data is
never fetched and then filtered in application code.** The owner
predicate is welded onto the SELECT before it reaches the database, so
a forgotten `if row.student_id != me` check cannot leak anything.

Endpoints serving student data must go through `StudentScope`. They must
not build their own `select(Submission)`; the tests in
`tests/test_data_isolation.py` cover the boundary, and
`tests/test_scope_contract.py` asserts that every owned model actually
carries the column the scope filters on.

Faculty access is scoped the same way, one level out: a professor reaches
student rows only through a classroom they own.
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Base,
    ChatMessage,
    Classroom,
    Diagnosis,
    Enrollment,
    Escalation,
    SocraticAttempt,
    SocraticSession,
    StudentSummary,
    Submission,
)

T = TypeVar("T", bound=Base)

#: Models that hold per-student data. Every one carries a `student_id`
#: column, which is what makes the scoping below uniform.
STUDENT_OWNED_MODELS: tuple[type[Base], ...] = (
    Submission,
    Diagnosis,
    SocraticSession,
    SocraticAttempt,
    ChatMessage,
    Enrollment,
    StudentSummary,
    Escalation,
)


class ScopeViolation(RuntimeError):
    """Raised when a query is built against a model this scope cannot own."""


class StudentScope:
    """Every query built here is filtered to one student id.

    Construct it from the authenticated session only -- never from a
    user id supplied in a path, query string or request body.
    """

    def __init__(self, session: AsyncSession, student_id: str) -> None:
        if not student_id:
            raise ScopeViolation("StudentScope requires a concrete student id")
        self._session = session
        self._student_id = student_id

    @property
    def student_id(self) -> str:
        return self._student_id

    def select(self, model: type[T]) -> Select[tuple[T]]:
        """A SELECT already constrained to this student.

        Raises for any model that has no `student_id` column rather than
        silently returning an unscoped query.
        """
        if model not in STUDENT_OWNED_MODELS:
            raise ScopeViolation(
                f"{model.__name__} is not student-owned; it cannot be fetched "
                "through StudentScope. Use an explicitly reviewed query."
            )
        return select(model).where(model.student_id == self._student_id)  # type: ignore[attr-defined]

    async def all(self, model: type[T], *criteria: Any) -> list[T]:
        stmt = self.select(model)
        for c in criteria:
            stmt = stmt.where(c)
        return list((await self._session.scalars(stmt)).all())

    async def get(self, model: type[T], obj_id: str) -> T | None:
        """Fetch one row by id **and** owner.

        A direct object reference to another student's row returns None
        here -- the row is not fetched at all, so there is nothing for a
        later check to forget.
        """
        stmt = self.select(model).where(model.id == obj_id)  # type: ignore[attr-defined]
        return (await self._session.scalars(stmt)).first()

    async def count(self, model: type[T], *criteria: Any) -> int:
        stmt = select(func.count()).select_from(model).where(
            model.student_id == self._student_id  # type: ignore[attr-defined]
        )
        for c in criteria:
            stmt = stmt.where(c)
        return int((await self._session.scalar(stmt)) or 0)

    async def is_enrolled(self, classroom_id: str) -> bool:
        return await self.count(Enrollment, Enrollment.classroom_id == classroom_id) > 0

    async def active_classroom_ids(self) -> list[str]:
        rows = await self.all(Enrollment)
        return [r.classroom_id for r in rows]


class FacultyScope:
    """Scopes faculty reads to classrooms the faculty member owns.

    A professor is not granted blanket access to every student row; the
    ownership predicate on `classrooms.owner_id` is applied in the same
    query that selects the student data.
    """

    def __init__(self, session: AsyncSession, faculty_id: str) -> None:
        if not faculty_id:
            raise ScopeViolation("FacultyScope requires a concrete faculty id")
        self._session = session
        self._faculty_id = faculty_id

    @property
    def faculty_id(self) -> str:
        return self._faculty_id

    def _owned_classroom_ids(self) -> Select[tuple[str]]:
        return select(Classroom.id).where(Classroom.owner_id == self._faculty_id)

    def select_classrooms(self) -> Select[tuple[Classroom]]:
        return select(Classroom).where(Classroom.owner_id == self._faculty_id)

    async def get_classroom(self, classroom_id: str) -> Classroom | None:
        stmt = self.select_classrooms().where(Classroom.id == classroom_id)
        return (await self._session.scalars(stmt)).first()

    async def owns_classroom(self, classroom_id: str) -> bool:
        return await self.get_classroom(classroom_id) is not None

    def select(self, model: type[T]) -> Select[tuple[T]]:
        """A SELECT constrained to classrooms this faculty member owns."""
        if not hasattr(model, "classroom_id"):
            raise ScopeViolation(
                f"{model.__name__} has no classroom_id; it cannot be scoped to faculty."
            )
        return select(model).where(
            model.classroom_id.in_(self._owned_classroom_ids())  # type: ignore[attr-defined]
        )

    async def all(self, model: type[T], *criteria: Any) -> list[T]:
        stmt = self.select(model)
        for c in criteria:
            stmt = stmt.where(c)
        return list((await self._session.scalars(stmt)).all())

    async def get(self, model: type[T], obj_id: str) -> T | None:
        stmt = self.select(model).where(model.id == obj_id)  # type: ignore[attr-defined]
        return (await self._session.scalars(stmt)).first()

    async def roster(self, classroom_id: str) -> list[Enrollment]:
        """Empty list for a classroom this faculty member does not own."""
        if not await self.owns_classroom(classroom_id):
            return []
        stmt = select(Enrollment).where(Enrollment.classroom_id == classroom_id)
        return list((await self._session.scalars(stmt)).all())

    async def purge_summaries(self, classroom_id: str, experiment_id: str, student_ids: list[str]):
        """Used only by an explicit professor-requested summary refresh."""
        if not await self.owns_classroom(classroom_id) or not student_ids:
            return
        await self._session.execute(
            delete(StudentSummary).where(
                StudentSummary.classroom_id == classroom_id,
                StudentSummary.experiment_id == experiment_id,
                StudentSummary.student_id.in_(student_ids),
            )
        )
