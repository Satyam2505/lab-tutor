"""Tier 3: abstain and hand the case to a human.

SIMPLIFICATION, STATED EXPLICITLY FOR THIS BUILD:

    Tier 3 is not a calibrated confidence model. There is no scoring, no
    probability, no prioritisation and no ranking of any kind. The entire
    rule is: *if Tier 1 and Tier 2 both fail to produce a diagnosis, mark
    the case unresolved and push it to the professor's review queue.*

Every escalation therefore looks identical to every other one, and the
queue is ordered by arrival. That is a deliberate scope decision for the
two-week pilot, not an unfinished feature -- a confidence model built on
one cohort's data would be calibrated on nothing. Prioritising the queue
by likely severity is listed as deferred work in ARCHITECTURE.md §2.

The value of this tier is that it exists at all: a system that always
produces an answer would produce a wrong one whenever it did not know,
and a wrong explanation of a student's mistake is worse than none.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EscalationDecision:
    """The outcome of abstaining. There is no confidence field, by design."""

    reason: str
    unresolved: bool = True


def escalate(reason: str) -> EscalationDecision:
    return EscalationDecision(reason=reason)


REASON_NO_SIGNATURE = (
    "Tier 1 found the reported result inconsistent with the student's own data "
    "but matched no known numeric signature, and Tier 2 matched no curated "
    "procedural mistake."
)
REASON_QUALITATIVE = (
    "This experiment is assessed on computational method choice, which has no "
    "deterministic check; a demonstrator must review it."
)
REASON_PLUGIN_UNAVAILABLE = (
    "No Tier 1 plugin is configured for this experiment, so no automatic "
    "diagnosis was attempted."
)

__all__ = [
    "EscalationDecision",
    "escalate",
    "REASON_NO_SIGNATURE",
    "REASON_QUALITATIVE",
    "REASON_PLUGIN_UNAVAILABLE",
]
