"""Socratic mode: step decomposition, per-step verification, hint ladder.

Pure logic, no database and no I/O, so every rule below is directly
testable. The API layer in `backend/api/socratic.py` persists what this
returns.

Two properties matter most, and both are structural rather than
prompt-based:

* **This module never computes the experiment's final answer during a
  conversation.** `verify_step` evaluates only the step the student is
  on, against the student's own prior data. The final value is computed
  in exactly one place, `compute_reveal`, which refuses to run until
  server-side verification has marked every step complete.
* **Hint content is chosen by Tier 1, not by a model.** The ladder rung
  is a function of how many times the student has attempted this step;
  the text comes from the plugin's fixed ladder. A model may re-word a
  rung, but it cannot pick one or invent one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.answer_gate import PrematureRevealError, build_reveal
from backend.rag import templates
from backend.tier1_compute.experiments.registry import (
    ExperimentPlugin,
    ManualNotTranscribedError,
)
from backend.tier1_compute.shared.types import Outcome, StepSpec, Tier1Result

#: The ladder has three rungs and stops there. Beyond the third attempt
#: the student keeps getting the third rung -- escalating forever would
#: converge on simply telling them the answer.
MAX_HINT_LEVEL = 3


class SessionComplete(RuntimeError):
    pass


@dataclass
class StepOutcome:
    """What the engine decided about one attempt."""

    passed: bool
    step_index: int
    hint_level: int = 0
    hint: str = ""
    message: str = ""
    advanced_to: int | None = None
    all_steps_complete: bool = False
    result: Tier1Result | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def steps_for(plugin: ExperimentPlugin) -> tuple[StepSpec, ...]:
    steps = plugin.steps()
    if not steps:
        raise ManualNotTranscribedError(
            f"{plugin.id}: no Socratic steps configured. Transcribe the ordered "
            "procedure from the IACHY102 manual before enabling this experiment."
        )
    return steps


def current_step(plugin: ExperimentPlugin, step_index: int) -> StepSpec:
    steps = steps_for(plugin)
    if step_index < 0 or step_index >= len(steps):
        raise SessionComplete(
            f"{plugin.id}: step {step_index} is outside the procedure "
            f"(0..{len(steps) - 1})"
        )
    return steps[step_index]


def present_step(plugin: ExperimentPlugin, step_index: int) -> str:
    """The prompt for the current step, and only the current step.

    Later steps are not shown: a student who can read the whole procedure
    at once can often shortcut to the answer without doing the reasoning
    each step is there to force.
    """
    step = current_step(plugin, step_index)
    total = len(steps_for(plugin))
    return f"Step {step.index + 1} of {total}: {step.prompt}"


def hint_level_for(attempts_on_step: int) -> int:
    """Attempts already made on this step -> ladder rung.

    First failure gets a vague nudge, second something specific, third and
    beyond names the likely issue. No rung names the number.
    """
    return max(1, min(attempts_on_step + 1, MAX_HINT_LEVEL))


def verify_step(
    plugin: ExperimentPlugin,
    step_index: int,
    *,
    student_data: dict[str, Any],
    submitted_value: float | None,
) -> Tier1Result:
    """Tier 1 verification of ONE step against the student's own data.

    Never touches the final answer, and never calls a model.
    """
    return plugin.check_step(step_index, student_data, submitted_value)


def handle_attempt(
    plugin: ExperimentPlugin,
    *,
    step_index: int,
    attempts_on_step: int,
    student_data: dict[str, Any],
    submitted_value: float | None,
) -> StepOutcome:
    """Verify an attempt, then either advance or hand back a hint rung."""
    steps = steps_for(plugin)
    step = current_step(plugin, step_index)
    total = len(steps)

    result = verify_step(
        plugin, step_index, student_data=student_data, submitted_value=submitted_value
    )

    if result.outcome is Outcome.PASS:
        is_last = step_index >= total - 1
        return StepOutcome(
            passed=True,
            step_index=step_index,
            message=templates.step_pass_text(step_index + 1, total),
            advanced_to=None if is_last else step_index + 1,
            all_steps_complete=is_last,
            result=result,
        )

    level = hint_level_for(attempts_on_step)
    hint = templates.hint_text(level, step.hints)

    # An invalid entry is a data problem, not a wrong answer: say what is
    # missing rather than spending a ladder rung on it.
    if result.outcome is Outcome.INVALID:
        message = "; ".join(result.errors) or "That entry could not be checked."
        return StepOutcome(
            passed=False,
            step_index=step_index,
            hint_level=0,
            hint="",
            message=message,
            result=result,
        )

    return StepOutcome(
        passed=False,
        step_index=step_index,
        hint_level=level,
        hint=hint,
        message=hint,
        result=result,
        detail={"signature": result.signature_code},
    )


def compute_reveal(
    plugin: ExperimentPlugin,
    *,
    all_steps_complete: bool,
    student_data: dict[str, Any],
    student_final_value: float | None,
) -> str:
    """The one place the final answer is computed, after full verification.

    Raises `PrematureRevealError` if verification has not completed. The
    returned text is built by `answer_gate.build_reveal` from the Tier 1
    value directly -- no model is called on this path, which is why no
    amount of conversation can bring it forward.
    """
    if not all_steps_complete:
        raise PrematureRevealError(
            "Refusing to compute the final answer: step verification is incomplete."
        )

    # Ask for the value, not a verdict: `check` needs something to compare
    # against and reports INVALID without one, which is correct for a
    # submission and wrong here.
    try:
        computed = plugin.compute_expected(student_data)
    except NotImplementedError as exc:
        raise PrematureRevealError(
            f"{plugin.id} has no computable final value to reveal."
        ) from exc

    steps = steps_for(plugin)
    final_step = next((s for s in steps if s.is_final), steps[-1])
    tolerance = final_step.tolerance

    return build_reveal(
        all_steps_complete=True,
        computed_value=computed,
        label=final_step.key.replace("_", " "),
        student_value=student_final_value,
        tolerance_description=tolerance.describe() if tolerance else "",
    )
