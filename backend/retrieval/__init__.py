"""The image-aware, tier-filtered, hybrid retrieval pipeline.

This is the RAG core the brief calls for in §5-6: provenance-carrying
`Chunk`s (`chunks.py`), manifest-gated ingestion (`ingest.py`),
best-effort page images (`images.py`), hybrid lexical+local-semantic
search with structural source filtering (`index.py`), a grounding gate
(`grounding.py`), business-rule reranking (`rerank.py`), and the
end-to-end orchestrator (`pipeline.py`).

It supersedes `backend/rag/retrieval.py` for the Q&A product. That
module is kept as-is: it still serves the diagnosis pipeline's citation
needs (`backend/rag/phrasing.py`, `backend/rag/qualitative.py`), which
this phase did not touch, and duplicating its BM25 core here rather than
sharing it was a deliberate call -- the two have different metadata
requirements (single-document page numbers vs. multi-document, multi-tier
provenance) and forcing one implementation to serve both would have
made the simpler one (the diagnosis citation lookup) carry complexity it
does not need.
"""

from __future__ import annotations

from backend.retrieval.chunks import Chunk, ContentType, PageImageRef, make_chunk_id
from backend.retrieval.index import HybridIndex, ScoredChunk, get_index, reset_index_cache
from backend.retrieval.pipeline import AnswerResult, Citation, answer_question

__all__ = [
    "AnswerResult",
    "Chunk",
    "Citation",
    "ContentType",
    "HybridIndex",
    "PageImageRef",
    "ScoredChunk",
    "answer_question",
    "get_index",
    "make_chunk_id",
    "reset_index_cache",
]
