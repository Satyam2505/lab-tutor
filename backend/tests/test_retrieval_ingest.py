"""Ingestion: chunking, provenance, and manifest-gated reporting."""

from __future__ import annotations

import pytest

from backend.retrieval import ingest
from backend.retrieval.chunks import ContentType
from backend.sources.manifest import ManifestEntry, get_manifest
from backend.sources.tiers import SourceDocument, SourceTier


def _entry(**overrides) -> ManifestEntry:
    document = SourceDocument(
        document_id=overrides.pop("document_id", "test_doc"),
        tier=overrides.pop("tier", SourceTier.OFFICIAL_MANUAL),
        filename=overrides.pop("filename", "manual/does_not_exist.pdf"),
        title=overrides.pop("title", "Test Document"),
        version=overrides.pop("version", "1.0"),
        experiments=overrides.pop("experiments", ()),
        present=overrides.pop("present", False),
    )
    return ManifestEntry(
        document=document,
        role=overrides.pop("role", "official_manual"),
        visual=overrides.pop("visual", True),
        indexable=overrides.pop("indexable", True),
        superseded_by=overrides.pop("superseded_by", None),
    )


# ---------------------------------------------------------------------------
# Reporting: blocked vs excluded vs ingested
# ---------------------------------------------------------------------------


def test_absent_document_is_reported_blocked_not_silently_empty():
    report = ingest.ingest_document(_entry(present=False))
    assert report.status == "blocked"
    assert report.chunk_count == 0
    assert "not present" in report.reason


def test_superseded_document_is_reported_excluded():
    report = ingest.ingest_document(_entry(superseded_by="newer_doc", present=True))
    assert report.status == "excluded"
    assert "superseded" in report.reason


def test_non_indexable_document_is_reported_excluded():
    report = ingest.ingest_document(_entry(indexable=False, present=True))
    assert report.status == "excluded"
    assert "non-indexable" in report.reason


def test_present_but_missing_on_disk_is_still_blocked_not_a_crash():
    report = ingest.ingest_document(
        _entry(present=True, filename="manual/definitely_not_here.pdf")
    )
    assert report.status == "blocked"


def test_manifest_documents_all_route_through_the_same_reporting(tmp_path):
    reports = ingest.ingest_all()
    ids = {r.document_id for r in reports}
    assert ids == {e.document_id for e in get_manifest()}
    for report in reports:
        assert report.status in ("blocked", "excluded", "ingested")


# ---------------------------------------------------------------------------
# Chunking mechanics (white-box: these are pure functions, not I/O)
# ---------------------------------------------------------------------------


def test_pack_respects_max_chars_and_keeps_paragraphs_intact():
    paragraphs = ["A" * 500, "B" * 500, "C" * 100]
    packed = ingest._pack(paragraphs, max_chars=900)
    assert len(packed) == 2
    assert packed[0] == "A" * 500
    assert "B" * 500 in packed[1] and "C" * 100 in packed[1]


def test_pack_never_splits_a_single_paragraph():
    huge = "X" * 5000
    packed = ingest._pack([huge], max_chars=900)
    assert packed == [huge]


def test_content_type_classification():
    assert ingest._classify_content("Table 3: calibration standards") == ContentType.TABLE
    assert ingest._classify_content("See Figure 2 below") == ContentType.FIGURE_CAPTION
    assert (
        ingest._classify_content("Click Optimize, then select the input file")
        == ContentType.SOFTWARE_STEP
    )
    assert ingest._classify_content("k = 0.014 min^-1 (t)") == ContentType.FORMULA
    assert (
        ingest._classify_content("Worked example: a student obtained...")
        == ContentType.WORKED_EXAMPLE
    )
    assert ingest._classify_content("This experiment studies reaction rates.") == ContentType.GENERAL


def test_deterministic_chunk_ids_are_stable_across_calls():
    document = SourceDocument(
        document_id="doc1", tier=SourceTier.OFFICIAL_MANUAL, filename="f.pdf",
        title="Doc", version="1.0",
    )
    entry = _entry(document_id="doc1", present=True)
    a = ingest._chunk_page("Some procedure text here.", 3, document=document, entry=entry, image=None)
    b = ingest._chunk_page("Some procedure text here.", 3, document=document, entry=entry, image=None)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]


def test_chunk_id_changes_with_document_version():
    doc_v1 = SourceDocument(
        document_id="doc1", tier=SourceTier.OFFICIAL_MANUAL, filename="f.pdf",
        title="Doc", version="1.0",
    )
    doc_v2 = SourceDocument(
        document_id="doc1", tier=SourceTier.OFFICIAL_MANUAL, filename="f.pdf",
        title="Doc", version="2.0",
    )
    entry = _entry(document_id="doc1", present=True)
    a = ingest._chunk_page("Some text.", 1, document=doc_v1, entry=entry, image=None)
    b = ingest._chunk_page("Some text.", 1, document=doc_v2, entry=entry, image=None)
    assert a[0].chunk_id != b[0].chunk_id, (
        "a revised manual must produce new chunk IDs, not overwrite old ones"
    )


# ---------------------------------------------------------------------------
# Experiment attribution -- the anti-contamination rule
# ---------------------------------------------------------------------------


def test_single_experiment_document_attributes_every_chunk_to_it():
    document = SourceDocument(
        document_id="exp07_script", tier=SourceTier.OFFICIAL_SUPPLEMENTARY,
        filename="f.pdf", title="Exp7 script", version="1.0", experiments=("exp07",),
    )
    entry = _entry(document_id="exp07_script", present=True, experiments=("exp07",))
    chunks = ingest._chunk_page("Nothing chemistry-specific here at all.", 1, document=document, entry=entry, image=None)
    assert chunks[0].experiment_id == "exp07"


def test_manual_wide_document_attributes_by_strong_vocabulary():
    document = SourceDocument(
        document_id="manual", tier=SourceTier.OFFICIAL_MANUAL, filename="f.pdf",
        title="Manual", version="1.0", experiments=("exp07", "exp08", "exp02", "exp03"),
    )
    entry = _entry(document_id="manual", present=True, experiments=("exp07", "exp08", "exp02", "exp03"))
    homo_chunk = ingest._chunk_page(
        "Record the HOMO and LUMO orbital energies from the output file.",
        12, document=document, entry=entry, image=None,
    )
    assert homo_chunk[0].experiment_id == "exp07"

    kinetics_chunk = ingest._chunk_page(
        "The pseudo first order rate constant for ethyl acetate hydrolysis is calculated from the slope.",
        30, document=document, entry=entry, image=None,
    )
    assert kinetics_chunk[0].experiment_id == "exp02"


def test_ambiguous_manual_wide_chunk_is_left_unattributed_not_guessed():
    """Two computational experiments share vocabulary. A chunk hitting
    both must not be arbitrarily assigned to one of them."""
    document = SourceDocument(
        document_id="manual", tier=SourceTier.OFFICIAL_MANUAL, filename="f.pdf",
        title="Manual", version="1.0", experiments=("exp07", "exp08"),
    )
    entry = _entry(document_id="manual", present=True, experiments=("exp07", "exp08"))
    chunks = ingest._chunk_page(
        "Open Avogadro and run the optimisation before reading the energy.",
        5, document=document, entry=entry, image=None,
    )
    # Neither HOMO/LUMO nor staggered/chair vocabulary appears -- this is
    # generic software-workflow language shared by both, so it must stay
    # unattributed rather than land on whichever experiment happens first.
    assert chunks[0].experiment_id is None


def test_generic_wet_lab_sentence_does_not_get_attributed_to_a_computational_experiment():
    document = SourceDocument(
        document_id="manual", tier=SourceTier.OFFICIAL_MANUAL, filename="f.pdf",
        title="Manual", version="1.0", experiments=("exp02", "exp03"),
    )
    entry = _entry(document_id="manual", present=True, experiments=("exp02", "exp03"))
    chunks = ingest._chunk_page(
        "Record your observations in the table provided.",
        1, document=document, entry=entry, image=None,
    )
    assert chunks[0].experiment_id is None
