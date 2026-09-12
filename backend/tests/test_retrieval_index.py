"""Hybrid index: relevance ranking, and the source-filtering invariant."""

from __future__ import annotations

from backend.retrieval.chunks import Chunk, ContentType
from backend.retrieval.index import HybridIndex
from backend.sources.tiers import SourceTier, Usage


def _chunk(
    cid: str,
    text: str,
    *,
    tier: SourceTier = SourceTier.OFFICIAL_MANUAL,
    experiment_id: str | None = "exp07",
    content_type: ContentType = ContentType.GENERAL,
) -> Chunk:
    return Chunk(
        chunk_id=cid,
        text=text,
        document_id="manual",
        document_title="Test Manual",
        tier=tier,
        source_version="1.0",
        page=1,
        experiment_id=experiment_id,
        content_type=content_type,
    )


EXP07_CHUNKS = [
    _chunk("c1", "Open Gabedit and build the methane molecule using the draw tool.", experiment_id="exp07"),
    _chunk("c2", "Run the geometry optimisation in ORCA before requesting orbital energies.", experiment_id="exp07"),
    _chunk("c3", "The HOMO and LUMO orbital contributions appear in the output file after the job completes.", experiment_id="exp07"),
]

EXP03_CHUNKS = [
    _chunk("c4", "Prepare Ni2+ standard solutions and record their absorbance for the calibration curve.", experiment_id="exp03"),
    _chunk("c5", "Extract the RGB values from the smartphone photo of each standard.", experiment_id="exp03"),
]

GENERAL_CHUNKS = [
    _chunk("c6", "Wear safety goggles and a lab coat at all times in the laboratory.", experiment_id=None),
]


def test_relevant_chunk_outranks_irrelevant_ones():
    index = HybridIndex(EXP07_CHUNKS + EXP03_CHUNKS)
    results = index.search("where is HOMO LUMO orbital", usage=Usage.EXPERIMENT_INSTRUCTION, experiment_id="exp07")
    assert results
    assert results[0].chunk.chunk_id == "c3"


def test_experiment_filter_excludes_other_experiments_even_with_shared_words():
    """The brief's own example: 'concentration'-style shared vocabulary
    must not let one experiment's chunks answer another's question."""
    index = HybridIndex(EXP07_CHUNKS + EXP03_CHUNKS)
    results = index.search(
        "calibration curve concentration method", usage=Usage.EXPERIMENT_INSTRUCTION, experiment_id="exp07"
    )
    ids = {r.chunk.chunk_id for r in results}
    assert not ids & {"c4", "c5"}, "experiment 3 chunks leaked into an experiment 7 query"


def test_general_unattributed_chunks_are_eligible_regardless_of_experiment():
    index = HybridIndex(EXP07_CHUNKS + GENERAL_CHUNKS)
    results = index.search("safety goggles lab coat", usage=Usage.EXPERIMENT_INSTRUCTION, experiment_id="exp07")
    assert any(r.chunk.chunk_id == "c6" for r in results)


def test_no_experiment_context_only_returns_general_chunks():
    """Without a routed experiment, an experiment-specific chunk must not
    win just because the corpus happens to be dominated by one experiment."""
    index = HybridIndex(EXP07_CHUNKS * 5 + GENERAL_CHUNKS)
    results = index.search("safety in the laboratory", usage=Usage.EXPERIMENT_INSTRUCTION, experiment_id=None)
    ids = {r.chunk.chunk_id for r in results}
    assert ids == {"c6"} or ids == set()


def test_curated_adjacent_tier_is_excluded_from_experiment_instruction_usage():
    """Tier C must not answer a direct procedural question, however well
    it happens to match the words."""
    adjacent = _chunk(
        "c7", "General DFT theory explains why optimisation converges the way it does.",
        tier=SourceTier.CURATED_ADJACENT, experiment_id="exp07",
    )
    index = HybridIndex(EXP07_CHUNKS + [adjacent])
    results = index.search("optimisation converges DFT theory", usage=Usage.EXPERIMENT_INSTRUCTION, experiment_id="exp07")
    assert all(r.chunk.tier is not SourceTier.CURATED_ADJACENT for r in results)


def test_curated_adjacent_tier_is_included_for_adjacent_explanation_usage():
    adjacent = _chunk(
        "c7", "General DFT theory explains why optimisation converges the way it does.",
        tier=SourceTier.CURATED_ADJACENT, experiment_id="exp07",
    )
    index = HybridIndex(EXP07_CHUNKS + [adjacent])
    results = index.search("DFT theory converges", usage=Usage.ADJACENT_EXPLANATION, experiment_id="exp07")
    assert any(r.chunk.chunk_id == "c7" for r in results)


def test_empty_query_returns_nothing():
    index = HybridIndex(EXP07_CHUNKS)
    assert index.search("   ", usage=Usage.EXPERIMENT_INSTRUCTION, experiment_id="exp07") == []


def test_empty_index_returns_nothing_without_crashing():
    index = HybridIndex([])
    assert index.search("anything", usage=Usage.EXPERIMENT_INSTRUCTION) == []
    assert len(index) == 0


def test_k_limits_results():
    index = HybridIndex(EXP07_CHUNKS)
    results = index.search("orbital energy optimisation gabedit", usage=Usage.EXPERIMENT_INSTRUCTION, experiment_id="exp07", k=1)
    assert len(results) <= 1
