"""Socratic mode: ordered steps, per-step Tier 1 verification, hint ladder.

`engine` holds the rules (pure, testable, no I/O). `chat` phrases a turn
for the student through the answer gate. Neither computes the final
answer during a conversation -- see `engine.compute_reveal`.
"""

from backend.socratic_engine import triage
from backend.socratic_engine.chat import TutorReply, tutor_reply
from backend.socratic_engine.triage import Intent
from backend.socratic_engine.engine import (
    MAX_HINT_LEVEL,
    SessionComplete,
    StepOutcome,
    compute_reveal,
    current_step,
    handle_attempt,
    hint_level_for,
    present_step,
    steps_for,
    verify_step,
)

__all__ = [
    "MAX_HINT_LEVEL",
    "SessionComplete",
    "StepOutcome",
    "Intent",
    "TutorReply",
    "triage",
    "compute_reveal",
    "current_step",
    "handle_attempt",
    "hint_level_for",
    "present_step",
    "steps_for",
    "tutor_reply",
    "verify_step",
]
