"""Page-image rendering degrades honestly when no renderer is installed."""

from __future__ import annotations

from backend.retrieval import images


def test_renderer_availability_matches_import_success():
    assert images.renderer_available() == (images.fitz is not None)


def test_render_page_image_reports_unavailable_without_a_renderer(tmp_path):
    # No PyMuPDF in this environment (see backend/requirements.txt).
    if images.renderer_available():
        return  # pragma: no cover - only relevant if fitz is later installed
    ref = images.render_page_image(
        tmp_path / "does_not_matter.pdf", 3, document_id="doc1", output_dir=tmp_path
    )
    assert ref.available is False
    assert ref.asset_path is None
    assert ref.page == 3
    assert ref.document_id == "doc1"


def test_render_page_image_reports_unavailable_for_a_missing_file(tmp_path, monkeypatch):
    """Even with a renderer, a missing PDF must degrade, not raise."""
    class _FakeFitz:
        pass

    monkeypatch.setattr(images, "fitz", _FakeFitz())
    ref = images.render_page_image(
        tmp_path / "missing.pdf", 1, document_id="doc1", output_dir=tmp_path
    )
    assert ref.available is False
