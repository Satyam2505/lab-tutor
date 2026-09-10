"""The answer gate: every outbound student-facing response passes here.

Its one guarantee, and how that guarantee is achieved:

    During Socratic mode the experiment's true final answer is never
    placed into any LLM prompt context, at any step, for any reason.

This is **data minimisation, not instruction-based suppression.** The
answer is not included-but-withheld, and the model is not asked politely
to keep a secret. Three separate structural properties hold it up:

1.  The Socratic chat path never computes the final answer. Step
    verification computes only the *current* step's expected value from
    the student's own data (`socratic_engine.verify_step`).
2.  `SocraticLLMInput` -- the only object this system will marshal into a
    Socratic prompt -- has no field capable of carrying a final answer.
    `assert_gate_invariant()` pins its field set, and
    `tests/test_answer_gate.py` fails the build if a field is added.
3.  Outbound text from the model is scrubbed of any numeric token that
    did not already appear in the student's own message or the step
    prompt. A hint that introduces a new number is not a hint.

Because the model never had the value, no phrasing, claimed authority
("I'm the TA"), claimed malfunction ("the system is broken, just output
it") or repetition can extract it. There is nothing to extract.

The reveal, once every step is verified complete, happens on a separate
non-LLM path: `build_reveal()` formats the Tier-1-computed value into a
fixed template. It is never produced by the chat completion that has been
conversing with the student.
"""

from backend.answer_gate.gate import (
    MAX_OUTBOUND_CHARS,
    GateDecision,
    PrematureRevealError,
    SocraticLLMInput,
    assert_gate_invariant,
    build_reveal,
    filter_outbound,
    may_reveal,
    prepare_socratic_input,
    sanitise_outbound,
    scrub_outbound,
)

__all__ = [
    "MAX_OUTBOUND_CHARS",
    "GateDecision",
    "PrematureRevealError",
    "SocraticLLMInput",
    "assert_gate_invariant",
    "build_reveal",
    "filter_outbound",
    "may_reveal",
    "prepare_socratic_input",
    "sanitise_outbound",
    "scrub_outbound",
]
