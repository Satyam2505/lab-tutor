"""The reranking stage: business rules the index doesn't know about.

`HybridIndex.search` answers "how relevant is this chunk to these
words". Reranking answers a different question: "given what we know
about this *query* and this *document set*, which relevant chunks should
actually be trusted first". Three adjustments, applied in order:

1. **Tier priority.** Between two chunks of comparable relevance, the
   official manual (Tier A) is preferred over supplementary material
   (Tier B), per the source hierarchy (brief §0, `backend/sources/`).
2. **Content-type match.** A question that names a visual artefact
   ("screenshot", "button", "which screen") is boosted toward chunks
   carrying a page image or classified as `FIGURE_CAPTION` /
   `SOFTWARE_STEP`, so "where do I click" doesn't lose to a text-only
   theory paragraph that happens to share more words.
3. **Grounding gate.** Anything that fails `grounding.is_grounded`
   against the query is dropped here, not merely down-weighted --
   brief §13's rule that a citation must be supported, not just
   score-adjacent.
"""

from __future__ import annotations

from dataclasses import replace

from backend.retrieval.grounding import is_grounded
from backend.retrieval.index import ScoredChunk
from backend.retrieval.chunks import ContentType
from backend.sources.tiers import SourceTier

#: Applied as a multiplier on the combined score. Small and monotone in
#: tier rank, so it breaks ties without letting a marginal Tier A chunk
#: beat a strongly relevant Tier B one outright.
_TIER_BOOST: dict[SourceTier, float] = {
    SourceTier.OFFICIAL_MANUAL: 1.15,
    SourceTier.OFFICIAL_SUPPLEMENTARY: 1.05,
    SourceTier.CURATED_ADJACENT: 1.0,
}

_VISUAL_QUERY_MARKERS = (
    "screenshot", "screen", "button", "click", "menu", "window", "tab",
    "figure", "image", "picture", "look like", "where is", "which option",
)

_VISUAL_CONTENT_TYPES = frozenset({ContentType.FIGURE_CAPTION, ContentType.SOFTWARE_STEP})

_VISUAL_BOOST = 1.2


def rerank(
    scored: list[ScoredChunk], query_text: str, *, require_grounding: bool = True
) -> list[ScoredChunk]:
    """Reorder and filter one experiment/tier-filtered result set."""
    wants_visual = any(marker in query_text.lower() for marker in _VISUAL_QUERY_MARKERS)

    adjusted: list[ScoredChunk] = []
    for item in scored:
        if require_grounding and not is_grounded(item.chunk, query_text):
            continue
        score = item.score * _TIER_BOOST.get(item.chunk.tier, 1.0)
        if wants_visual and (
            item.chunk.visual_available or item.chunk.content_type in _VISUAL_CONTENT_TYPES
        ):
            score *= _VISUAL_BOOST
        adjusted.append(replace(item, score=score))

    adjusted.sort(key=lambda s: s.score, reverse=True)
    return adjusted
