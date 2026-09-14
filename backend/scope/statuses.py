"""The six answer statuses, and why they are six and not one.

The failure this module exists to prevent is collapsing everything the
system cannot answer into "I don't know". Those cases are not the same,
they have different causes, and they need different responses:

* A student asking a perfectly normal Experiment 7 question that
  retrieval happened to miss needs to hear that the question is fine and
  the source lookup failed — and that failure should be *logged as a
  retrieval gap for someone to fix*.

* A student asking about GPUs needs a scope boundary, and nothing should
  be logged as a gap.

Telling the first student "that's outside what I cover" is both wrong and
corrosive: it teaches them the tool does not know their own experiment,
and they stop asking. That is why `IN_SCOPE_RETRIEVAL_INSUFFICIENT` and
`OUT_OF_SCOPE` are separate values that cannot be produced by the same
code path — see `backend/scope/classifier.py`, where scope is decided
*before* retrieval runs and cannot be revised by its result.
"""

from __future__ import annotations

import enum


class ScopeLevel(str, enum.Enum):
    """How a question relates to the documented experiment material."""

    #: Explicitly supported by official material: procedure, software
    #: step, formula, concept, table, interpretation, screenshot.
    DIRECT = "level_1_direct"
    #: Meaningfully related, not directly covered by the manual.
    ADJACENT = "level_2_adjacent"
    #: Unrelated to the experiments or to what this product does.
    OUT_OF_SCOPE = "level_3_out_of_scope"


class AnswerStatus(str, enum.Enum):
    """The outcome of scope classification plus evidence assessment."""

    #: In scope, and sufficient official evidence was retrieved.
    IN_SCOPE_SUPPORTED = "in_scope_supported"
    #: In scope, but the sources did not yield enough to answer from.
    #: A product gap, not a student error. Logged for repair.
    IN_SCOPE_RETRIEVAL_INSUFFICIENT = "in_scope_retrieval_insufficient"
    #: Adjacent, and curated supplementary material covers it.
    ADJACENT_SUPPORTED = "adjacent_supported"
    #: Adjacent, and no trustworthy supplementary source exists.
    ADJACENT_UNSUPPORTED = "adjacent_unsupported"
    #: Outside the experiments and outside what this product does.
    OUT_OF_SCOPE = "out_of_scope"
    #: Cannot be settled automatically, or a source conflict was found.
    NEEDS_HUMAN_REVIEW = "needs_human_review"

    @property
    def answerable(self) -> bool:
        """Whether the system will attempt a substantive answer."""
        return self in (
            AnswerStatus.IN_SCOPE_SUPPORTED,
            AnswerStatus.ADJACENT_SUPPORTED,
        )

    @property
    def requires_citation(self) -> bool:
        return self.answerable

    @property
    def requires_supplementary_label(self) -> bool:
        return self is AnswerStatus.ADJACENT_SUPPORTED

    @property
    def is_retrieval_gap(self) -> bool:
        """Whether this outcome is a defect in *our* coverage.

        These are the ones worth an alert. A question we should be able to
        answer and cannot is the signal that the corpus, the chunking or
        the router needs work.
        """
        return self in (
            AnswerStatus.IN_SCOPE_RETRIEVAL_INSUFFICIENT,
            AnswerStatus.ADJACENT_UNSUPPORTED,
        )

    @property
    def scope_level(self) -> ScopeLevel | None:
        return _LEVEL_OF.get(self)


_LEVEL_OF: dict[AnswerStatus, ScopeLevel] = {
    AnswerStatus.IN_SCOPE_SUPPORTED: ScopeLevel.DIRECT,
    AnswerStatus.IN_SCOPE_RETRIEVAL_INSUFFICIENT: ScopeLevel.DIRECT,
    AnswerStatus.ADJACENT_SUPPORTED: ScopeLevel.ADJACENT,
    AnswerStatus.ADJACENT_UNSUPPORTED: ScopeLevel.ADJACENT,
    AnswerStatus.OUT_OF_SCOPE: ScopeLevel.OUT_OF_SCOPE,
}


#: What the student sees when the system is not answering substantively.
#: Deterministic text: these must be identical whether inference is
#: healthy or unreachable, and they must not be improvised by a model
#: that might soften "I could not find this" into a guess.
FALLBACK_TEMPLATES: dict[AnswerStatus, str] = {
    AnswerStatus.IN_SCOPE_RETRIEVAL_INSUFFICIENT: (
        "That is a question about {experiment}, and it is a fair one — I "
        "just could not find enough in the course material to answer it "
        "properly, and I am not going to guess at something you are being "
        "assessed on. Your demonstrator or the manual section for this "
        "step will have it. I have logged the gap."
    ),
    AnswerStatus.ADJACENT_UNSUPPORTED: (
        "That is related to {experiment} but goes past what the manual "
        "covers, and I do not have a supplementary source I trust enough "
        "to answer from. I would rather say so than improvise background "
        "theory at you."
    ),
    AnswerStatus.OUT_OF_SCOPE: (
        "That is outside what I cover — I am here for the Engineering "
        "Chemistry Laboratory experiments and the software they use. Ask "
        "me about the experiment you are on and I will help with that."
    ),
    AnswerStatus.NEEDS_HUMAN_REVIEW: (
        "I am not confident enough to answer this one, so I am flagging it "
        "for your demonstrator rather than giving you something that might "
        "be wrong."
    ),
}


def fallback_text(status: AnswerStatus, *, experiment_label: str = "this experiment") -> str:
    """The deterministic student-facing text for a non-answering status."""
    template = FALLBACK_TEMPLATES.get(status)
    if template is None:
        raise ValueError(
            f"{status} is an answering status; it has no fallback text. "
            "Build the answer from retrieved evidence instead."
        )
    return template.format(experiment=experiment_label)
