"""Turning a manifest-declared document into provenance-carrying chunks.

Reproducibility (brief §7) comes from three things working together:

* Chunk IDs are deterministic (`make_chunk_id`), keyed on
  `(document_id, version, locator)`. Re-ingesting the same PDF at the
  same version produces the same IDs; a revised manual (new `version`)
  produces new ones, so nothing is silently overwritten.
* Only documents declared in `docs/source_manifest.json` are ingested
  (`backend.sources.manifest`) -- an unlisted file in `manual/` is an
  unknown document, not "probably the manual".
* `experiment_id` is attached only when the manifest already says which
  experiments a document covers. When a document spans several (the
  whole IACHY102 manual does), per-chunk attribution falls back to
  scanning the chunk's own text against `backend/scope/ontology.py`'s
  *strong* terms only -- the same discriminative vocabulary the query
  router uses, so a manual chunk and a question about it are tagged by
  the same rule. Weak/ambiguous chunks are left unattributed
  (`experiment_id=None`) rather than guessed, which is what keeps
  Experiment 3 chunks from leaking into an Experiment 7 answer merely
  for sharing the word "concentration" -- see brief §6.

Chunking is by page and by paragraph within a page, not by an arbitrary
token window: a paragraph is the unit a manual actually reasons in, and
splitting mid-paragraph would sever a formula from the sentence that
explains its symbols.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.retrieval.chunks import Chunk, ContentType, make_chunk_id
from backend.retrieval.images import render_page_image, renderer_available
from backend.scope import ontology
from backend.sources.manifest import ManifestEntry, get_manifest
from backend.sources.tiers import SourceDocument

log = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 900

#: Cues that a paragraph documents a GUI step rather than wet-lab
#: procedure or theory. Used only to set `content_type` for citation
#: phrasing -- never to decide *which* experiment a chunk belongs to.
_SOFTWARE_STEP_RE = re.compile(
    r"\b(?:click|select|open|choose|menu|tab|button|dialog|window|drop-?down|"
    r"checkbox|toolbar|icon|input file|output file|\.inp\b|\.out\b)\b",
    re.IGNORECASE,
)
_FORMULA_HINT_RE = re.compile(r"[=≈][^=]{0,80}(?:\d|[a-zA-Z]\s*\()")
_TABLE_HINT_RE = re.compile(r"\btable\s+\d", re.IGNORECASE)
_FIGURE_HINT_RE = re.compile(r"\b(?:figure|fig\.|screenshot)\s*\d", re.IGNORECASE)
_WORKED_EXAMPLE_RE = re.compile(r"\bworked\s+example\b|\bsample\s+calculation\b", re.IGNORECASE)


@dataclass(frozen=True)
class IngestReport:
    """What ingesting one document actually produced.

    Distinguishes three outcomes that a bare `list[Chunk]` would
    collapse: successfully ingested, declared-but-blocked (the file is
    absent), and declared-but-excluded (superseded or non-indexable).
    Only the first contributes chunks; the other two are still reported,
    because a pipeline that quietly indexes nothing must not look
    identical to one that is working -- see `docs/current_state_audit.md`.
    """

    document_id: str
    status: str  # "ingested" | "blocked" | "excluded"
    chunk_count: int = 0
    page_count: int = 0
    reason: str = ""
    chunks: tuple[Chunk, ...] = field(default_factory=tuple, repr=False)


def ingest_document(
    entry: ManifestEntry, *, image_output_dir: str | Path | None = None
) -> IngestReport:
    document = entry.document

    if entry.is_superseded:
        return IngestReport(
            document_id=document.document_id,
            status="excluded",
            reason=f"superseded by {entry.superseded_by}",
        )
    if not entry.indexable:
        return IngestReport(
            document_id=document.document_id, status="excluded", reason="marked non-indexable"
        )
    if not document.present:
        return IngestReport(
            document_id=document.document_id,
            status="blocked",
            reason=f"file not present: {document.filename}",
        )

    path = Path(document.filename)
    if not path.exists():
        return IngestReport(
            document_id=document.document_id,
            status="blocked",
            reason=f"manifest says present=true but file not found at {path}",
        )

    pages = _extract_pages(path)
    if not pages:
        return IngestReport(
            document_id=document.document_id,
            status="blocked",
            reason="no extractable text (empty, corrupt, or image-only PDF)",
        )

    chunks: list[Chunk] = []
    for page_number, text in pages:
        image = None
        if image_output_dir is not None:
            image = render_page_image(
                path, page_number, document_id=document.document_id, output_dir=image_output_dir
            )
        chunks.extend(
            _chunk_page(text, page_number, document=document, entry=entry, image=image)
        )

    return IngestReport(
        document_id=document.document_id,
        status="ingested",
        chunk_count=len(chunks),
        page_count=len(pages),
        chunks=tuple(chunks),
    )


def ingest_all(*, image_output_dir: str | Path | None = None) -> list[IngestReport]:
    """Ingest every manifest entry. Every entry is reported, ingested or not."""
    return [
        ingest_document(entry, image_output_dir=image_output_dir) for entry in get_manifest()
    ]


def _extract_pages(path: Path) -> list[tuple[int, str]]:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - dependency is pinned
        log.error("pypdf is not installed; ingestion cannot read %s", path)
        return []

    try:
        reader = PdfReader(str(path))
        pages: list[tuple[int, str]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((page_number, text))
        return pages
    except Exception as exc:  # pragma: no cover - corrupt/locked PDF
        log.error("Failed to read %s: %s", path, exc)
        return []


def _chunk_page(
    text: str,
    page: int,
    *,
    document: SourceDocument,
    entry: ManifestEntry,
    image,
) -> list[Chunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    packed = _pack(paragraphs, MAX_CHUNK_CHARS)

    chunks: list[Chunk] = []
    for index, body in enumerate(packed):
        locator = f"p{page}#{index}"
        chunk_id = make_chunk_id(document.document_id, document.version, locator)
        experiment_id = _attribute_experiment(body, document)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=body,
                document_id=document.document_id,
                document_title=document.title,
                tier=document.tier,
                source_version=document.version,
                page=page,
                content_type=_classify_content(body),
                experiment_id=experiment_id,
                image=image,
            )
        )
    return chunks


def _pack(paragraphs: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        if buffer and len(buffer) + len(para) + 1 > max_chars:
            chunks.append(buffer.strip())
            buffer = para
        else:
            buffer = f"{buffer}\n{para}" if buffer else para
    if buffer.strip():
        chunks.append(buffer.strip())
    return chunks


def _classify_content(text: str) -> ContentType:
    if _WORKED_EXAMPLE_RE.search(text):
        return ContentType.WORKED_EXAMPLE
    if _TABLE_HINT_RE.search(text):
        return ContentType.TABLE
    if _FIGURE_HINT_RE.search(text):
        return ContentType.FIGURE_CAPTION
    if _SOFTWARE_STEP_RE.search(text):
        return ContentType.SOFTWARE_STEP
    if _FORMULA_HINT_RE.search(text):
        return ContentType.FORMULA
    return ContentType.GENERAL


def _attribute_experiment(text: str, document: SourceDocument) -> str | None:
    """Which experiment this chunk belongs to, if that is unambiguous.

    A document declared for exactly one experiment in the manifest is
    attributed to it outright. A document spanning many (the manual
    itself) is attributed per-chunk, and only when exactly one
    experiment's strong/software vocabulary is present -- ties or silence
    are left unattributed rather than guessed.
    """
    if len(document.experiments) == 1:
        return document.experiments[0]

    lowered = text.lower()
    hits: set[str] = set()
    for topic in ontology.routable_topics():
        if topic.id not in document.experiments and document.experiments:
            continue
        vocabulary = topic.strong_terms | topic.software
        if any(_word_in(term, lowered) for term in vocabulary):
            hits.add(topic.id)

    if len(hits) == 1:
        return hits.pop()
    return None


def _word_in(term: str, lowered_text: str) -> bool:
    if " " in term:
        return term in lowered_text
    return re.search(rf"\b{re.escape(term)}\b", lowered_text) is not None


def render_all_page_images(output_dir: str | Path) -> dict[str, bool]:
    """Coverage summary: which manifest documents got real page images.

    Used by the coverage-report tooling (`docs/handoff_phase2.md`) to
    show, per document, whether visual grounding is actually available or
    only architecturally supported.
    """
    return {
        entry.document_id: entry.visual and renderer_available() and entry.ingestible
        for entry in get_manifest()
    }
