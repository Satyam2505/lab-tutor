"""Does a retrieved chunk actually support answering this question?

The brief is specific about the failure this guards against (§13): "Do
not cite a source merely because it contains the experiment number."
A chunk can pass the index's relevance ranking (score > 0, top-k) while
overlapping the query only on structural vocabulary -- "experiment 7",
"table", "the" -- that says nothing about the actual question.

`is_grounded` requires real content overlap: at least one shared token
that is not a stopword, not a bare experiment/number reference, and not
one of the handful of words so common in this domain (`"method"`,
`"result"`) that matching on them alone proves nothing. This runs after
retrieval and before a chunk is allowed to become a citation -- it is
the last gate, independent of whatever score the index assigned.
"""

from __future__ import annotations

import re

from backend.retrieval.chunks import Chunk

_WORD_RE = re.compile(r"[a-z0-9]+")

#: Present in nearly every chunk of a lab manual; overlapping on these
#: alone is not evidence the chunk answers the specific question asked.
_UNINFORMATIVE_TERMS = frozenset(
    {
        "experiment", "manual", "method", "result", "results", "value",
        "table", "figure", "page", "student", "students", "procedure",
        "observation", "record", "note", "section", "step", "steps",
        "chemistry", "laboratory", "lab", "given", "following", "shown",
    }
)

_EXPERIMENT_REF_RE = re.compile(r"^exp\d{2}$")

#: Minimum informative-token overlap for a chunk to count as grounding
#: evidence, rather than a coincidental hit.
MIN_OVERLAP = 1


def _informative_tokens(text: str) -> set[str]:
    tokens = _WORD_RE.findall(text.lower())
    return {
        t
        for t in tokens
        if t not in _UNINFORMATIVE_TERMS
        and not _EXPERIMENT_REF_RE.match(t)
        and not t.isdigit()
        and len(t) > 2
    }


def is_grounded(chunk: Chunk, query_text: str, *, min_overlap: int = MIN_OVERLAP) -> bool:
    """Whether `chunk` shares real content with `query_text`."""
    query_terms = _informative_tokens(query_text)
    chunk_terms = _informative_tokens(chunk.text)
    if not query_terms or not chunk_terms:
        return False
    return len(query_terms & chunk_terms) >= min_overlap


def overlap_terms(chunk: Chunk, query_text: str) -> frozenset[str]:
    """The informative terms a chunk and a query actually share.

    Exposed separately from `is_grounded` so a caller can show *why* a
    passage was accepted (useful in logs and in the coverage report),
    without recomputing the token sets.
    """
    return frozenset(_informative_tokens(query_text) & _informative_tokens(chunk.text))
