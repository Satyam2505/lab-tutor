"""Question scope: which experiment, which level, which status.

See `statuses.py` for why "we found nothing" and "that is not our
subject" must never collapse into the same answer, and `classifier.py`
for the ordering constraint that makes the separation structural.
"""

from __future__ import annotations

from backend.scope.classifier import (
    EvidenceSummary,
    ScopeDecision,
    classify_and_resolve,
    classify_scope,
    resolve_status,
)
from backend.scope.normalize import NormalizedQuery, normalize
from backend.scope.statuses import AnswerStatus, ScopeLevel, fallback_text

__all__ = [
    "AnswerStatus",
    "EvidenceSummary",
    "NormalizedQuery",
    "ScopeDecision",
    "ScopeLevel",
    "classify_and_resolve",
    "classify_scope",
    "fallback_text",
    "normalize",
    "resolve_status",
]
