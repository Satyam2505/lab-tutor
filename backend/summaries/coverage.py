"""A rough, deterministic per-experiment engagement/coverage indicator for
faculty. NOT a grade, NOT LLM-produced or LLM-adjusted -- per this repo's
hard rule (CLAUDE.md), a model never decides correctness or produces a
score. This module only counts already-stored, already-graded activity
(Tier 1/2/3 diagnosis outcomes, Socratic step pass/fail, submission and
Q&A counts) the exact same way `backend/summaries/jobs.py` does for a
single class session, just rolled up across a WHOLE classroom's history
per experiment instead of one session.

Granularity is per-experiment (`exp01`..`exp10`), not per sub-topic within
an experiment -- there is no finer topic taxonomy anywhere in this
codebase (`backend/scope/ontology.py`'s `ExperimentTopic` is
experiment-level routing vocabulary, not a sub-topic breakdown), and
building one is out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    ActorType,
    ChatMessage,
    ChatMessageKind,
    Diagnosis,
    DiagnosisStatus,
    SocraticAttempt,
    SocraticSession,
    Submission,
)


@dataclass
class TopicCoverage:
    experiment_id: str
    steps_attempted: int
    steps_passed: int
    submissions: int
    diagnoses_passed: int
    diagnoses_failed: int
    diagnoses_escalated: int
    qa_messages: int
    #: 0-100, deterministic. Never produced or adjusted by an LLM.
    coverage_score: int

    def as_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "steps_attempted": self.steps_attempted,
            "steps_passed": self.steps_passed,
            "submissions": self.submissions,
            "diagnoses_passed": self.diagnoses_passed,
            "diagnoses_failed": self.diagnoses_failed,
            "diagnoses_escalated": self.diagnoses_escalated,
            "qa_messages": self.qa_messages,
            "coverage_score": self.coverage_score,
        }


def _score(
    *, steps_attempted: int, steps_passed: int, submissions: int,
    diagnoses_passed: int, diagnoses_failed: int, diagnoses_escalated: int,
    qa_messages: int,
) -> int:
    """Fixed weighted formula: breadth of engagement (did they touch every
    part of the experiment) plus a correctness rate where one exists.
    Entirely arithmetic -- no model call anywhere in this function.
    """
    total_diagnoses = diagnoses_passed + diagnoses_failed + diagnoses_escalated
    engagement = min(
        40,
        (10 if steps_attempted else 0)
        + (10 if submissions else 0)
        + (10 if qa_messages else 0)
        + (10 if total_diagnoses else 0),
    )
    correctness = 0.0
    if total_diagnoses:
        correctness += 30 * (diagnoses_passed / total_diagnoses)
    elif steps_attempted:
        # No submission graded yet -- don't silently zero out this half of
        # the score just because that axis has no data yet.
        correctness += 30 * (steps_passed / steps_attempted)
    if steps_attempted:
        correctness += 30 * (steps_passed / steps_attempted)
    return int(round(min(100, engagement + correctness)))


async def compute_topic_coverage(
    db: AsyncSession, classroom_id: str, student_id: str
) -> list[TopicCoverage]:
    """Course-wide rollup across every class session for this student in
    this classroom, one row per experiment they have ANY recorded activity
    in. Only ActorType.STUDENT rows count -- faculty/admin test activity
    (including a promoted co-faculty's own testing) never contributes.
    """
    attempt_rows = list(
        (
            await db.execute(
                select(SocraticAttempt, SocraticSession.experiment_id)
                .join(SocraticSession, SocraticSession.id == SocraticAttempt.session_id)
                .where(
                    SocraticAttempt.student_id == student_id,
                    SocraticSession.classroom_id == classroom_id,
                    SocraticSession.actor_type == ActorType.STUDENT,
                )
            )
        ).all()
    )

    submissions = list(
        (
            await db.scalars(
                select(Submission).where(
                    Submission.student_id == student_id,
                    Submission.classroom_id == classroom_id,
                    Submission.actor_type == ActorType.STUDENT,
                )
            )
        ).all()
    )
    # Diagnosis has no experiment_id column of its own -- only reachable
    # via its Submission.
    diagnosis_rows = list(
        (
            await db.execute(
                select(Diagnosis, Submission.experiment_id)
                .join(Submission, Submission.id == Diagnosis.submission_id)
                .where(
                    Diagnosis.student_id == student_id,
                    Diagnosis.classroom_id == classroom_id,
                )
            )
        ).all()
    )
    qa_messages = list(
        (
            await db.scalars(
                select(ChatMessage).where(
                    ChatMessage.student_id == student_id,
                    ChatMessage.classroom_id == classroom_id,
                    ChatMessage.kind == ChatMessageKind.QA,
                    ChatMessage.actor_type == ActorType.STUDENT,
                    ChatMessage.author == "student",
                )
            )
        ).all()
    )

    experiment_ids: set[str] = set()
    for _attempt, experiment_id in attempt_rows:
        experiment_ids.add(experiment_id)
    for s in submissions:
        experiment_ids.add(s.experiment_id)
    for _d, experiment_id in diagnosis_rows:
        experiment_ids.add(experiment_id)
    for m in qa_messages:
        if m.experiment_id:
            experiment_ids.add(m.experiment_id)
    experiment_ids.discard("")

    out: list[TopicCoverage] = []
    for experiment_id in sorted(experiment_ids):
        exp_attempts = [a for a, eid in attempt_rows if eid == experiment_id]
        by_step: dict[int, list[SocraticAttempt]] = {}
        for a in exp_attempts:
            by_step.setdefault(a.step_index, []).append(a)
        steps_attempted = len(by_step)
        steps_passed = sum(
            1 for step_attempts in by_step.values() if any(a.passed for a in step_attempts)
        )

        exp_submissions = [s for s in submissions if s.experiment_id == experiment_id]
        exp_diagnoses = [d for d, eid in diagnosis_rows if eid == experiment_id]
        diagnoses_passed = sum(1 for d in exp_diagnoses if d.status == DiagnosisStatus.PASS)
        diagnoses_failed = sum(1 for d in exp_diagnoses if d.status == DiagnosisStatus.FAIL)
        diagnoses_escalated = sum(1 for d in exp_diagnoses if d.status == DiagnosisStatus.ESCALATED)
        exp_qa = [m for m in qa_messages if m.experiment_id == experiment_id]

        score = _score(
            steps_attempted=steps_attempted,
            steps_passed=steps_passed,
            submissions=len(exp_submissions),
            diagnoses_passed=diagnoses_passed,
            diagnoses_failed=diagnoses_failed,
            diagnoses_escalated=diagnoses_escalated,
            qa_messages=len(exp_qa),
        )
        out.append(
            TopicCoverage(
                experiment_id=experiment_id,
                steps_attempted=steps_attempted,
                steps_passed=steps_passed,
                submissions=len(exp_submissions),
                diagnoses_passed=diagnoses_passed,
                diagnoses_failed=diagnoses_failed,
                diagnoses_escalated=diagnoses_escalated,
                qa_messages=len(exp_qa),
                coverage_score=score,
            )
        )
    return out
