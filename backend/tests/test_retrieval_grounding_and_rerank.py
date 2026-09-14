"""Grounding gate and reranking business rules."""

from __future__ import annotations

from backend.retrieval.chunks import Chunk, ContentType
from backend.retrieval.grounding import is_grounded, overlap_terms
from backend.retrieval.index import ScoredChunk
from backend.retrieval.rerank import rerank
from backend.sources.tiers import SourceTier


def _chunk(cid: str, text: str, *, tier=SourceTier.OFFICIAL_MANUAL, content_type=ContentType.GENERAL) -> Chunk:
    return Chunk(
        chunk_id=cid, text=text, document_id="d", document_title="D", tier=tier,
        source_version="1.0", page=1, experiment_id="exp07", content_type=content_type,
    )


# ---------------------------------------------------------------------------
# Grounding: the "don't cite for the experiment number alone" rule
# ---------------------------------------------------------------------------


def test_chunk_sharing_only_the_experiment_number_is_not_grounded():
    chunk = _chunk("c1", "Experiment 7 Table 2 Page 12 Procedure Method Result")
    assert not is_grounded(chunk, "what is the homo energy in exp07")


def test_chunk_with_real_content_overlap_is_grounded():
    chunk = _chunk("c1", "The HOMO orbital energy is read from the ORCA output file.")
    assert is_grounded(chunk, "where do i find the homo orbital energy")


def test_overlap_terms_reports_the_actual_shared_vocabulary():
    chunk = _chunk("c1", "The HOMO orbital energy is read from the ORCA output file.")
    shared = overlap_terms(chunk, "where do i find the homo orbital energy")
    assert "homo" in shared and "orbital" in shared
    assert "experiment" not in shared


def test_empty_query_or_chunk_is_never_grounded():
    chunk = _chunk("c1", "")
    assert not is_grounded(chunk, "homo lumo")
    assert not is_grounded(_chunk("c2", "homo lumo orbital"), "")


# ---------------------------------------------------------------------------
# Reranking
# ---------------------------------------------------------------------------


def test_ungrounded_chunks_are_dropped_by_rerank():
    grounded = ScoredChunk(chunk=_chunk("c1", "The HOMO orbital energy appears in the output."), score=0.5)
    ungrounded = ScoredChunk(chunk=_chunk("c2", "Experiment 7 Table Page Method"), score=0.9)
    result = rerank([grounded, ungrounded], "where is the homo orbital energy")
    ids = {r.chunk.chunk_id for r in result}
    assert ids == {"c1"}


def test_official_tier_is_boosted_over_supplementary_at_similar_relevance():
    official = ScoredChunk(
        chunk=_chunk("c1", "The HOMO orbital energy is in the output file.", tier=SourceTier.OFFICIAL_MANUAL),
        score=0.50,
    )
    supplementary = ScoredChunk(
        chunk=_chunk("c2", "The HOMO orbital energy is in the output file.", tier=SourceTier.OFFICIAL_SUPPLEMENTARY),
        score=0.50,
    )
    result = rerank([supplementary, official], "homo orbital energy output file")
    assert result[0].chunk.tier is SourceTier.OFFICIAL_MANUAL


def test_visual_query_boosts_figure_and_software_step_chunks():
    text_only = ScoredChunk(
        chunk=_chunk("c1", "HOMO orbital energy theory background discussion.", content_type=ContentType.CONCEPT),
        score=0.60,
    )
    screenshot_chunk = ScoredChunk(
        chunk=_chunk("c2", "Click the Orbitals button to view the HOMO energy on screen.", content_type=ContentType.SOFTWARE_STEP),
        score=0.55,
    )
    result = rerank([text_only, screenshot_chunk], "where is the button to see homo energy screenshot")
    assert result[0].chunk.chunk_id == "c2"


def test_non_visual_query_does_not_apply_visual_boost():
    text_only = ScoredChunk(
        chunk=_chunk("c1", "The HOMO orbital energy is defined as the highest occupied level.", content_type=ContentType.CONCEPT),
        score=0.60,
    )
    screenshot_chunk = ScoredChunk(
        chunk=_chunk("c2", "Click the button to open the orbital energy screen.", content_type=ContentType.SOFTWARE_STEP),
        score=0.55,
    )
    result = rerank([text_only, screenshot_chunk], "what is the homo orbital energy definition")
    assert result[0].chunk.chunk_id == "c1"
