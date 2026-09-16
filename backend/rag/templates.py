"""Deterministic phrasing templates.

Used whenever the LLM is unavailable or its reply fails validation, and
for the Socratic reveal, which never goes through a model at all. Because
these are string formatting over Tier 1 output, every one of them is
reproducible and safe to show without review.
"""

from __future__ import annotations

from backend.tier1_compute.shared.types import Action, Outcome, Tier1Result

_ACTION_SENTENCES: dict[Action, str] = {
    Action.NONE: "nothing -- the record is consistent",
    Action.FIX_IN_PLACE: "correct the calculation on the record sheet; the measurements are fine",
    Action.REDO_STEP: "repeat the affected part of the measurement",
    Action.RESTART: "start the experiment again",
    Action.AWAIT_REVIEW: "wait for a demonstrator to look at this",
}


def action_sentence(action: Action) -> str:
    return _ACTION_SENTENCES.get(action, "check with a demonstrator")


def diagnosis_text(result: Tier1Result, experiment_title: str) -> str:
    """Plain-language rendering of a determined diagnosis."""
    if result.outcome is Outcome.PASS:
        return (
            f"Your reported result for {experiment_title} is consistent with your "
            "own measurements when the manual's formula is applied to them."
        )

    if result.outcome is Outcome.INVALID:
        problems = "; ".join(result.errors) or "the submission was incomplete"
        return (
            f"This submission could not be checked: {problems}. "
            "Correct the entry and submit again."
        )

    if result.outcome is Outcome.NOT_APPLICABLE:
        return (
            f"{experiment_title} is assessed on the method you chose rather than "
            "on a single measured value, so it has been passed to a demonstrator "
            "for review."
        )

    parts: list[str] = []
    if result.expected_value is not None and result.reported_value is not None:
        parts.append(
            f"Recomputing from your own readings gives {result.expected_value:g}, "
            f"but you reported {result.reported_value:g}."
        )
    else:
        parts.append("Your reported result is not consistent with your own readings.")

    if result.signature is not None:
        parts.append(result.signature.detail)
    else:
        parts.append(
            "The cause is not one this system recognises, so it has been sent to a "
            "demonstrator for review."
        )

    parts.append(f"Next step: {action_sentence(result.action())}.")
    return " ".join(parts)


def hint_text(level: int, ladder: tuple[str, str, str]) -> str:
    """One rung of the hint ladder. Level is clamped to the ladder's length."""
    if not any(ladder):
        return "Look again at the step you are on and check your working."
    index = max(1, min(level, len(ladder))) - 1
    return ladder[index]


def step_pass_text(step_number: int, total: int) -> str:
    if step_number >= total:
        return "That step checks out, and it was the last one."
    return f"That step checks out. Move on to step {step_number + 1} of {total}."


def step_acknowledged_text(step_number: int, total: int) -> str:
    """Experiments 7/8 only: this experiment has no pass/fail check for a
    method-choice step, so wording must not claim one -- distinct from
    `step_pass_text`, which says something "checks out"."""
    if step_number >= total:
        return (
            "Logged. This experiment's final assessment is a demonstrator "
            "review, not an automatic pass -- that was the last step."
        )
    return (
        f"Logged. Move on to step {step_number + 1} of {total}; this experiment's "
        "steps are recorded for review rather than automatically verified."
    )


def refusal_text() -> str:
    """The standing refusal used for direct answer requests.

    Worth noting what this is *not*: it is not what keeps the answer safe.
    The answer is unavailable to the model regardless of what it says.
    This text only explains the situation politely.
    """
    return (
        "I can't give you the final value -- working it out is the point of the "
        "exercise. I can tell you whether the step you are on is consistent with "
        "your own data, and nudge you if it isn't."
    )
