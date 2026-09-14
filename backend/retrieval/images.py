"""Best-effort page-image rendering, honest about what it cannot do.

Experiments 7 and 8 are procedural and visual: the brief is explicit
that "which button?" and "what does this screen look like?" must be
answerable by pointing at the actual manual page. That requires
rasterising PDF pages to images.

No PDF-rasterisation library (PyMuPDF/`fitz`, `pdf2image`) is installed
in this environment, and this module does not install one on your
behalf -- see `backend/requirements.txt`, where `pymupdf` is added as a
pinned, commented-out-by-default note for Phase 2. Importing it here is
therefore wrapped exactly like `pypdf` is in the legacy retrieval module:
optional, logged, and degrading to "no image" rather than failing
ingestion.

This mirrors the codebase's existing stance on the missing manual
itself: a missing capability is reported, never silently absorbed into
a result that looks the same as success.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from backend.retrieval.chunks import PageImageRef

log = logging.getLogger(__name__)

try:
    import fitz  # type: ignore  # PyMuPDF -- optional, see module docstring
except ImportError:  # pragma: no cover - exercised by test_images.py directly
    fitz = None  # type: ignore[assignment]


def renderer_available() -> bool:
    return fitz is not None


def render_page_image(
    pdf_path: str | Path,
    page_number: int,
    *,
    document_id: str,
    output_dir: str | Path,
    caption: str = "",
) -> PageImageRef:
    """Render one page to a PNG under `output_dir`, or report it can't.

    `page_number` is 1-indexed, matching every other page reference in
    this codebase (`Chunk.page`, the legacy `Passage.page`).
    """
    if fitz is None:
        return PageImageRef(
            document_id=document_id, page=page_number, available=False, caption=caption
        )

    path = Path(pdf_path)
    if not path.exists():
        return PageImageRef(
            document_id=document_id, page=page_number, available=False, caption=caption
        )

    try:
        doc = fitz.open(str(path))
        try:
            if not (1 <= page_number <= doc.page_count):
                return PageImageRef(
                    document_id=document_id,
                    page=page_number,
                    available=False,
                    caption=caption,
                )
            page = doc.load_page(page_number - 1)
            pix = page.get_pixmap(dpi=150)
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            name = _asset_name(document_id, page_number)
            target = out_dir / name
            pix.save(str(target))
        finally:
            doc.close()
    except Exception as exc:  # pragma: no cover - corrupt/locked PDF
        log.error("Failed to render page %d of %s: %s", page_number, path, exc)
        return PageImageRef(
            document_id=document_id, page=page_number, available=False, caption=caption
        )

    return PageImageRef(
        document_id=document_id,
        page=page_number,
        available=True,
        asset_path=str(target),
        caption=caption,
    )


def _asset_name(document_id: str, page_number: int) -> str:
    digest = hashlib.sha256(f"{document_id}\x1f{page_number}".encode()).hexdigest()[:12]
    return f"{document_id}_p{page_number:04d}_{digest}.png"
