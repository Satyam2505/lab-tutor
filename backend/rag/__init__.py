"""Retrieval over the manual and the LLM phrasing layer.

Nothing here decides anything. `phrasing.phrase_diagnosis` renders a
`Tier1Result` that has already been determined; `templates` renders the
same thing without a model; `qualitative` holds the single, deliberately
contained exception for Experiments 7 and 8 (see its docstring).
"""

from backend.rag.phrasing import PhrasedOutput, phrase_diagnosis, validate_output
from backend.rag.qualitative import QualitativeNote, qualitative_note
from backend.rag.retrieval import Passage, retrieve

__all__ = [
    "PhrasedOutput",
    "Passage",
    "QualitativeNote",
    "phrase_diagnosis",
    "qualitative_note",
    "retrieve",
    "validate_output",
]
