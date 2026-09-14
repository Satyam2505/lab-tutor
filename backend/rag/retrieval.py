"""Retrieval over the course manual PDF.

Lexical BM25 over page-anchored chunks. Deliberately not an embedding
index: retrieval here serves short, vocabulary-heavy queries ("endpoint",
"normality", "conductometric") against one small domain-specific
document, where BM25 is competitive, and it adds no second provider, no
API key, no network hop and no cold-start cost on a machine serving ~70
concurrent students.

Every returned passage carries its page number so phrased output can cite
where in the manual the statement came from.

If the PDF is absent -- the current state of this repository -- retrieval
degrades to returning nothing. Callers must treat an empty result as
"phrase without a citation", never as a reason to invent one.
"""

from __future__ import annotations

import logging
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from backend.config import get_settings

log = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the
    to was were will with this these those which what when where how you your""".split()
)


@dataclass(frozen=True)
class Passage:
    text: str
    #: A single page for a PDF-sourced passage; a "p.10-15"-style range
    #: string for a markdown-transcription-sourced one (see
    #: `_chunk_markdown`), since the manual doc cites experiments by page
    #: range rather than a single page.
    page: int | str
    score: float = 0.0

    def citation(self) -> str:
        return f"IACHY102 manual, p. {self.page}"


def _tokenise(text: str) -> list[str]:
    return [t for t in _WORD_RE.findall(text.lower()) if t not in _STOPWORDS]


class ManualIndex:
    """In-memory BM25 index over the manual's pages."""

    K1 = 1.5
    B = 0.75

    def __init__(self, passages: list[Passage]) -> None:
        self.passages = passages
        self._tokens = [_tokenise(p.text) for p in passages]
        self._lengths = [len(t) for t in self._tokens]
        self._avg_len = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0
        self._tf = [Counter(t) for t in self._tokens]
        self._df: Counter[str] = Counter()
        for tokens in self._tokens:
            self._df.update(set(tokens))
        self._n = len(passages)

    def __len__(self) -> int:
        return self._n

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1.0 + (self._n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = 3) -> list[Passage]:
        terms = _tokenise(query)
        if not terms or self._n == 0:
            return []
        scored: list[Passage] = []
        for i, passage in enumerate(self.passages):
            score = 0.0
            length = self._lengths[i] or 1
            for term in terms:
                tf = self._tf[i].get(term, 0)
                if tf == 0:
                    continue
                denom = tf + self.K1 * (
                    1 - self.B + self.B * length / (self._avg_len or 1)
                )
                score += self._idf(term) * (tf * (self.K1 + 1)) / denom
            if score > 0:
                scored.append(Passage(text=passage.text, page=passage.page, score=score))
        scored.sort(key=lambda p: p.score, reverse=True)
        return scored[:k]


def _chunk_page(
    text: str, page: int | str, max_chars: int = 900, prefix: str = ""
) -> list[Passage]:
    """Split a page on blank lines, packing paragraphs up to `max_chars`.

    `prefix`, when given, is prepended to EVERY chunk, not just the
    first. Found this session (Explore-agent sweep, verified live): a
    long section split into several chunks lost its identifying context
    (e.g. the "Experiment 1 ... Zn-Cu system" heading) from every chunk
    after the first, so a mid-section chunk like a worked example ended
    up competing at retrieval with no experiment-identifying terms of
    its own -- an unrelated experiment's chunk that coincidentally
    shared a few words could and did outrank it. `_chunk_markdown` uses
    this for the section heading; the PDF path leaves it unset (a raw
    PDF page has no comparable heading to prepend).
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[Passage] = []
    buffer = ""

    def _flush(buf: str) -> Passage:
        body = f"{prefix}\n{buf}".strip() if prefix else buf.strip()
        return Passage(text=body, page=page)

    for para in paragraphs:
        if buffer and len(buffer) + len(para) + 1 > max_chars:
            chunks.append(_flush(buffer))
            buffer = para
        else:
            buffer = f"{buffer}\n{para}" if buffer else para
    if buffer.strip():
        chunks.append(_flush(buffer))
    return chunks


_MD_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_MD_PAGE_RE = re.compile(r"p\.\s*(\d+(?:\s*[-–]\s*\d+)?)")


#: Only a per-experiment section is eligible for retrieval/citation.
#: Found live during this session's evaluation run: a short front-matter
#: table listing all 10 experiment titles in one compact chunk
#: out-ranked the real Experiment 2/3 sections for their own queries,
#: because BM25 rewards a shorter document containing the same query
#: terms (length normalisation) -- Recall@1 was 0.0 for both until this
#: filter. That table (and the closing per-experiment summary table) are
#: navigational aids about the manual, not manual content a citation
#: should ever point to.
_EXPERIMENT_HEADING_RE = re.compile(r"^Experiment\s+\d+\b")


def _chunk_markdown(text: str, max_chars: int = 900) -> list[Passage]:
    """Chunk a manual transcribed as markdown (see `manual/README.md`).

    Splits on `## ` section headings and tags each chunk with the
    page/page range parsed from that heading's `(p.X-Y)` suffix (see
    `manual/IACHY102_manual.md`'s own heading format). Only sections
    headed "Experiment N ..." are indexed -- see
    `_EXPERIMENT_HEADING_RE`'s docstring for why everything else
    (front matter, summary tables) is deliberately excluded.
    """
    headings = list(_MD_HEADING_RE.finditer(text))
    if not headings:
        # No `##` structure at all -- treat the whole file as one section
        # rather than returning nothing.
        return _chunk_page(text, page="whole document", max_chars=max_chars)

    passages: list[Passage] = []
    for i, match in enumerate(headings):
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        heading = match.group(1)
        if not _EXPERIMENT_HEADING_RE.match(heading):
            continue
        body = text[start:end]
        page_match = _MD_PAGE_RE.search(heading) or _MD_PAGE_RE.search(
            body[:200]
        )
        page = page_match.group(1).replace(" ", "") if page_match else "front matter"
        body = body.strip()
        if body:
            passages.extend(
                _chunk_page(body, page, max_chars=max_chars, prefix=heading)
            )
    return passages


def build_index(pdf_path: str | Path) -> ManualIndex:
    path = Path(pdf_path)
    if not path.exists():
        log.warning(
            "Manual not found at %s -- retrieval will return no passages and "
            "phrased output will carry no citation.",
            path,
        )
        return ManualIndex([])

    if path.suffix.lower() == ".md":
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - unreadable file
            log.error("Failed to read manual markdown %s: %s", path, exc)
            return ManualIndex([])
        passages = _chunk_markdown(text)
        log.info("Indexed %d passages from %s (markdown)", len(passages), path)
        return ManualIndex(passages)

    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - dependency is pinned
        log.error("pypdf is not installed; retrieval disabled")
        return ManualIndex([])

    passages = []
    try:
        reader = PdfReader(str(path))
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                passages.extend(_chunk_page(text, page_number))
    except Exception as exc:  # pragma: no cover - corrupt/locked PDF
        log.error("Failed to read manual PDF %s: %s", path, exc)
        return ManualIndex([])

    log.info("Indexed %d passages from %s", len(passages), path)
    return ManualIndex(passages)


_index: ManualIndex | None = None
_index_lock = threading.Lock()


def get_index() -> ManualIndex:
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                _index = build_index(get_settings().manual_pdf)
    return _index


def retrieve(query: str, k: int = 3) -> list[Passage]:
    """Top-k manual passages for a query. Empty when no manual is indexed."""
    return get_index().search(query, k=k)


def reset_index_cache() -> None:
    global _index
    with _index_lock:
        _index = None
