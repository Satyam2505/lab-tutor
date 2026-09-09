"""Deterministic trajectory features from a student's stored history.

Counting is done here, in code, before any model is involved. The model's
job is to turn these counts into two readable lines, not to infer them
from a transcript -- inferred counts would be unreliable and would vary
between runs of the same data.

None of this is a grade. It characterises how a student moved through the
experiment: how much scaffolding they needed, whether they recovered on
their own, how many times they retried. Learning-outcome validation is the
professor's separate pen-and-paper test.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from backend.models import ChatMessage, Diagnosis, SocraticAttempt, Submission


@dataclass
class Trajectory:
    student_id: str
    total_attempts: int = 0
    steps_attempted: int = 0
    steps_passed: int = 0
    first_try_steps: int = 0
    #: Steps passed after a hint -- the student was nudged, not told.
    self_corrected_steps: int = 0
    #: Steps that needed the third rung, where the issue is named outright.
    told_directly_steps: int = 0
    hints_by_level: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    max_attempts_on_one_step: int = 0
    student_messages: int = 0
    submissions: int = 0
    diagnoses_failed: int = 0
    diagnoses_escalated: int = 0
    completed: bool = False

    @property
    def total_hints(self) -> int:
        return sum(self.hints_by_level.values())

    @property
    def is_empty(self) -> bool:
        return (
            self.total_attempts == 0
            and self.student_messages == 0
            and self.submissions == 0
        )

    def as_facts(self) -> dict[str, object]:
        return {
            "steps_attempted": self.steps_attempted,
            "steps_passed": self.steps_passed,
            "passed_first_try": self.first_try_steps,
            "passed_after_a_hint": self.self_corrected_steps,
            "needed_the_issue_named": self.told_directly_steps,
            "total_attempts": self.total_attempts,
            "total_hints": self.total_hints,
            "hints_by_level": dict(sorted(self.hints_by_level.items())),
            "most_attempts_on_a_single_step": self.max_attempts_on_one_step,
            "chat_messages_sent": self.student_messages,
            "submissions": self.submissions,
            "failed_diagnoses": self.diagnoses_failed,
            "escalated_to_review": self.diagnoses_escalated,
            "reached_the_end": self.completed,
        }


def build_trajectory(
    student_id: str,
    *,
    attempts: list[SocraticAttempt],
    messages: list[ChatMessage],
    submissions: list[Submission],
    diagnoses: list[Diagnosis],
    all_steps_complete: bool = False,
) -> Trajectory:
    traj = Trajectory(student_id=student_id, completed=all_steps_complete)

    by_step: dict[int, list[SocraticAttempt]] = defaultdict(list)
    for attempt in sorted(attempts, key=lambda a: a.created_at):
        by_step[attempt.step_index].append(attempt)
        traj.total_attempts += 1
        if attempt.hint_level:
            traj.hints_by_level[attempt.hint_level] += 1

    traj.steps_attempted = len(by_step)
    for step_attempts in by_step.values():
        traj.max_attempts_on_one_step = max(
            traj.max_attempts_on_one_step, len(step_attempts)
        )
        if not any(a.passed for a in step_attempts):
            continue
        traj.steps_passed += 1
        if step_attempts[0].passed:
            traj.first_try_steps += 1
        elif max((a.hint_level for a in step_attempts if not a.passed), default=0) >= 3:
            traj.told_directly_steps += 1
        else:
            traj.self_corrected_steps += 1

    traj.student_messages = sum(1 for m in messages if m.author == "student")
    traj.submissions = len(submissions)
    for diagnosis in diagnoses:
        if diagnosis.status.value == "fail":
            traj.diagnoses_failed += 1
        elif diagnosis.status.value == "escalated":
            traj.diagnoses_escalated += 1
    return traj


def deterministic_summary(traj: Trajectory) -> str:
    """Two-line fallback used when inference is unavailable.

    Reads flatly, but it is always available and always accurate.
    """
    if traj.is_empty:
        return (
            "No recorded activity for this experiment.\n"
            "There is nothing to characterise yet."
        )

    line1 = (
        f"Worked through {traj.steps_passed} of {traj.steps_attempted} attempted "
        f"steps over {traj.total_attempts} attempts, needing {traj.total_hints} hint(s)."
    )
    if traj.told_directly_steps:
        line2 = (
            f"Needed the issue named outright on {traj.told_directly_steps} step(s); "
            f"recovered independently on {traj.self_corrected_steps}."
        )
    elif traj.self_corrected_steps:
        line2 = (
            f"Recovered independently after a nudge on {traj.self_corrected_steps} "
            "step(s), without being told the problem directly."
        )
    else:
        line2 = (
            f"Passed {traj.first_try_steps} step(s) first time with no hints needed."
        )
    return f"{line1}\n{line2}"
