"""The retrieval unit, and every piece of provenance it must carry.

A `Chunk` is what the brief calls for in §5 and §6: not a bare string,
but text plus enough metadata that a retrieval result can be traced back
to an exact place in an exact document, filtered by experiment without
contaminating another one, and cited without fabricating a page number.

`chunk_id` is deterministic -- derived from `(document_id, version,
locator)` -- specifically so re-ingesting an unchanged manual produces
the same IDs (safe to upsert) while re-ingesting a *revised* manual
(different `version`) produces new ones rather than silently overwriting
passages that no longer say what they used to. See
`backend/sources/tiers.py::SourceDocument.version`.
"""

from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass, field

from backend.sources.tiers import SourceTier


class ContentType(str, enum.Enum):
    """What kind of material a chunk holds. Drives citation phrasing and
    lets a query for "the table" or "the screenshot" filter usefully."""

    PROCEDURE = "procedure"
    FORMULA = "formula"
    TABLE = "table"
    FIGURE_CAPTION = "figure_caption"
    CONCEPT = "concept"
    SOFTWARE_STEP = "software_step"
    WORKED_EXAMPLE = "worked_example"
    GENERAL = "general"


@dataclass(frozen=True)
class PageImageRef:
    """A pointer to the rasterised image of one manual page, if one exists.

    `asset_path` is None whenever rendering was not possible (no PDF
    renderer installed, or the source document is absent) -- see
    `backend/retrieval/images.py`. Chunks whose page has no image still
    carry this with `available=False` rather than omitting it, so a
    caller can always ask "is there a picture for this?" without a
    lookup that might silently fail.
    """

    document_id: str
    page: int
    available: bool
    asset_path: str | None = None
    caption: str = ""


@dataclass(frozen=True)
class Chunk:
    """One retrievable passage and its full provenance.

    Every field the brief's metadata list (§6) asks for is here:
    experiment_id, experiment_name is resolved via the ontology at
    citation time rather than duplicated, source_tier, document_name,
    page_number, section, content_type, visual_available, source_version.
    """

    chunk_id: str
    text: str
    document_id: str
    document_title: str
    tier: SourceTier
    source_version: str
    page: int
    section: str = ""
    content_type: ContentType = ContentType.GENERAL
    #: None means "not attributable to one experiment" (e.g. a general
    #: safety appendix). Never guessed at ingestion time; see
    #: `backend/retrieval/ingest.py`.
    experiment_id: str | None = None
    image: PageImageRef | None = None
    #: Nearby caption text, when this chunk sits next to a figure it does
    #: not itself contain -- lets a "which button?" question surface the
    #: caption even when the chunk's own text is procedural prose.
    nearby_caption: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def visual_available(self) -> bool:
        return bool(self.image and self.image.available)

    @property
    def is_retrievable_tier(self) -> bool:
        from backend.sources.tiers import is_retrievable

        return is_retrievable(self.tier)


def make_chunk_id(document_id: str, version: str, locator: str) -> str:
    """Deterministic ID for `(document, version, locator)`.

    `locator` should be something stable within a document version, e.g.
    ``"p12#0"`` for the first chunk carved from page 12. Changing the
    manual's version changes every ID it produces, which is what makes
    re-ingestion of a revised manual additive rather than corrupting.
    """
    digest = hashlib.sha256(f"{document_id}\x1f{version}\x1f{locator}".encode("utf-8"))
    return f"{document_id}:{digest.hexdigest()[:16]}"
