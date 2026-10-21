"""Phase 2 — sectioning, offset integrity, chunking. No network."""

from __future__ import annotations

import pytest

from atlas.contracts import Depth, PaperMeta, ParsedDoc
from atlas.ingest.chunk import chunk_doc
from atlas.ingest.grobid import _assemble, _map_section, abstract_only_doc, parse_tei
from tests.unit.conftest import fixture


def test_map_section_headings():
    assert _map_section("1. Introduction") == "intro"
    assert _map_section("3  RELATED WORK") == "related"
    assert _map_section("Proposed System Architecture") == "methods"
    assert _map_section("5. Results and Discussion") == "results"
    assert _map_section("Limitations") == "limitations"
    assert _map_section("Future Work") == "future_work"
    assert _map_section("Acknowledgements") == "other"


def test_assemble_offsets_round_trip_exactly():
    raw = [
        ("abstract", "Abstract", "  This is the   abstract.\n\n"),
        ("intro", "1 Introduction", "First para.\n\nSecond para of intro."),
        ("methods", "2 Methods", "We did things."),
    ]
    full_text, sections = _assemble(raw)
    assert len(sections) == 3
    for s in sections:
        assert full_text[s.char_start : s.char_end] == s.text
    # sections joined by exactly one blank line
    assert full_text.count("\n\n") >= 2


def test_assemble_skips_empty_sections():
    _, sections = _assemble([("intro", "Intro", "   "), ("methods", "M", "content")])
    assert [s.name for s in sections] == ["methods"]


def test_parse_tei_sections_offsets_and_references():
    doc = parse_tei(fixture("tei/sample.tei.xml"), "doi:10.1/paper")
    assert doc.structure == "grobid"
    assert doc.depth == Depth.FULL_TEXT

    names = [s.name for s in doc.sections]
    assert names[0] == "abstract"
    assert {"intro", "methods", "results", "limitations", "future_work"} <= set(names)

    for s in doc.sections:
        assert doc.full_text[s.char_start : s.char_end] == s.text

    # bibliography parsed; the real DOI is picked up, the DOI-less ref falls back
    assert len(doc.references) == 2
    assert any(r.paper_id == "doi:10.1109/cvpr.2016.90" for r in doc.references)
    assert any(r.paper_id.startswith("sha1:") for r in doc.references)


def test_abstract_only_doc_paths():
    with_abs = abstract_only_doc(
        PaperMeta(paper_id="doi:1", title="T", abstract="An abstract here.")
    )
    assert with_abs.structure == "none"
    assert with_abs.depth == Depth.ABSTRACT_ONLY
    assert [s.name for s in with_abs.sections] == ["abstract"]

    no_abs = abstract_only_doc(PaperMeta(paper_id="doi:2", title="T"))
    assert no_abs.depth == Depth.METADATA_ONLY
    assert no_abs.sections == []


def _doc_with_long_section() -> ParsedDoc:
    body = " ".join(f"sentence number {i} in the body." for i in range(400))
    full, secs = _assemble([("abstract", "Abstract", "Short abstract."), ("methods", "M", body)])
    return ParsedDoc(
        paper_id="doi:x",
        depth=Depth.FULL_TEXT,
        structure="grobid",
        full_text=full,
        sections=secs,
    )


def test_chunk_offsets_map_back_to_full_text():
    doc = _doc_with_long_section()
    chunks = chunk_doc(doc)
    assert len(chunks) > 1
    for c in chunks:
        assert doc.full_text[c.char_start : c.char_end] == c.text
        assert c.section in {"abstract", "methods"}
    # chunk indexes are contiguous from 0
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_abstract_is_never_chunked():
    doc = _doc_with_long_section()
    abstract_chunks = [c for c in chunk_doc(doc) if c.section == "abstract"]
    assert len(abstract_chunks) == 1
    assert abstract_chunks[0].text == "Short abstract."


def test_chunks_never_span_two_sections():
    body_a = " ".join(f"alpha {i}." for i in range(300))
    body_b = " ".join(f"beta {i}." for i in range(300))
    full, secs = _assemble([("methods", "M", body_a), ("results", "R", body_b)])
    doc = ParsedDoc(
        paper_id="doi:y", depth=Depth.FULL_TEXT, structure="grobid", full_text=full, sections=secs
    )
    for c in chunk_doc(doc):
        assert ("alpha" in c.text) != ("beta" in c.text)  # exactly one, never both


def test_ingest_never_overwrites_a_cached_abstract_vector(fresh_db: None, monkeypatch):
    """Reading a paper used to replace its seed vector (title+abstract, document-style)
    with a query-style abstract-only one, so the same query ranked papers differently
    depending on what earlier runs had read (found re-seeding tests/fixtures/e2e).
    The abstract vector is write-once, in the representation the loop seeds with."""
    from qdrant_client import QdrantClient

    from atlas.ingest import pipeline
    from atlas.ingest.embed import embed_texts
    from atlas.ingest.pdf_fetch import PdfResolution
    from atlas.store import vector

    shared = QdrantClient(location=":memory:")
    monkeypatch.setattr(shared, "close", lambda: None)  # run_ingest closes its client
    monkeypatch.setattr(vector, "get_client", lambda: shared)

    async def fake_parse(paper, *, prefer_grobid, pdf_path):
        return abstract_only_doc(paper), PdfResolution(paper.paper_id, None, None, "none")

    monkeypatch.setattr(pipeline, "_parse", fake_parse)

    def stored(pid: str) -> list[float]:
        return vector.get_abstract_vectors([pid], client=shared)[pid]

    cached = PaperMeta(paper_id="doi:10.1/cached", title="Wearable panic alert",
                       abstract="A wrist-worn device sends GPS alerts over GSM.")
    sentinel = [1.0] + [0.0] * (len(embed_texts(["x"])[0]) - 1)
    vector.upsert_abstracts_bulk([(cached.paper_id, sentinel, cached.title, None, None)],
                                 client=shared)
    pipeline.run_ingest(cached, run_id="r1", prefer_grobid=False)
    assert stored(cached.paper_id) == sentinel

    fresh = PaperMeta(paper_id="doi:10.1/fresh", title="Fall detection on the edge",
                      abstract="An accelerometer model runs on a microcontroller.")
    pipeline.run_ingest(fresh, run_id="r1", prefer_grobid=False)
    expected = embed_texts([f"{fresh.title}\n{fresh.abstract}"])[0]
    assert stored(fresh.paper_id) == pytest.approx(expected, abs=1e-5)
