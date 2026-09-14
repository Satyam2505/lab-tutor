"""Retrieval over the manual.

No test file existed for `backend/rag/retrieval.py` before this session
-- it was never exercised, which is how the "points at a nonexistent
BACHY105.pdf" and "pypdf can't parse the markdown transcription" bugs
both went unnoticed (see docs/final_audit.md). This covers the fix:
markdown ingestion via `_chunk_markdown`, and that `build_index`
dispatches to it for a `.md` path.
"""

from __future__ import annotations

from backend.rag.retrieval import Passage, build_index, retrieve, reset_index_cache

MANUAL_PATH = "manual/IACHY102_manual.md"


def test_manual_markdown_is_actually_indexed():
    idx = build_index(MANUAL_PATH)
    assert len(idx) > 0, "regression: retrieval must not silently return nothing"


def test_missing_file_returns_an_empty_index_not_an_exception():
    idx = build_index("manual/does_not_exist.pdf")
    assert len(idx) == 0


def test_experiment_7_query_retrieves_the_experiment_7_section():
    idx = build_index(MANUAL_PATH)
    results = idx.search("orca homo lumo avogadro orbital", k=3)
    assert results, "expected at least one passage"
    assert any("Experiment 7" in p.text for p in results)


def test_experiment_2_query_retrieves_the_experiment_2_section():
    idx = build_index(MANUAL_PATH)
    results = idx.search("ester hydrolysis titration rate constant", k=3)
    assert results
    assert any("Experiment 2" in p.text for p in results)


def test_passage_citation_names_the_current_manual_not_the_old_one():
    p = Passage(text="x", page="10-15")
    assert "IACHY102" in p.citation()
    assert "BACHY105" not in p.citation()


def test_retrieve_helper_uses_the_configured_default_path():
    reset_index_cache()
    results = retrieve("conformational analysis cyclohexane chair boat", k=2)
    assert results
    reset_index_cache()


if __name__ == "__main__":
    test_manual_markdown_is_actually_indexed()
    test_missing_file_returns_an_empty_index_not_an_exception()
    test_experiment_7_query_retrieves_the_experiment_7_section()
    test_experiment_2_query_retrieves_the_experiment_2_section()
    test_passage_citation_names_the_current_manual_not_the_old_one()
    test_retrieve_helper_uses_the_configured_default_path()
    print("retrieval self-check OK")
