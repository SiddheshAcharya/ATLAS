"""Phase 2 — Ingest one paper end to end.

    PaperMeta
      -> resolve_pdf            (source -> arXiv -> Unpaywall -> Europe PMC -> none)
      -> GROBID TEI | PyMuPDF flat | abstract-only   -> ParsedDoc  (normalized, offsets)
      -> chunk_doc              (section-aware, offsets preserved)
      -> embed_texts            (local bge-base, 768-dim)
      -> vector.upsert_chunks / upsert_abstract  (Qdrant, offsets in payload)
      -> db.set_paper_depth

The network half (resolve + GROBID) is async; chunk/embed/store is sync (CPU + local disk).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
import structlog

from atlas.config import settings
from atlas.contracts import PaperMeta, ParsedDoc
from atlas.ingest.chunk import chunk_doc
from atlas.ingest.embed import embed_texts
from atlas.ingest.grobid import (
    GrobidClient,
    abstract_only_doc,
    parse_tei,
    parse_with_pymupdf,
)
from atlas.ingest.pdf_fetch import PdfResolution, resolve_pdf
from atlas.store import db, vector

log = structlog.get_logger(__name__)


@dataclass
class IngestReport:
    paper_id: str
    pdf_via: str
    structure: str
    depth: str
    n_sections: int
    n_chunks: int
    n_references: int
    full_text_chars: int
    offsets_ok: bool
    warnings: list[str]
    elapsed_s: float

    def as_dict(self) -> dict[str, object]:
        return {
            "paper_id": self.paper_id,
            "pdf_via": self.pdf_via,
            "structure": self.structure,
            "depth": self.depth,
            "n_sections": self.n_sections,
            "n_chunks": self.n_chunks,
            "n_references": self.n_references,
            "full_text_chars": self.full_text_chars,
            "offsets_ok": self.offsets_ok,
            "warnings": self.warnings,
            "elapsed_s": round(self.elapsed_s, 1),
        }


async def _parse(
    paper: PaperMeta,
    *,
    prefer_grobid: bool,
    pdf_path: str | None,
) -> tuple[ParsedDoc, PdfResolution]:
    async with httpx.AsyncClient(
        headers={"User-Agent": f"ATLAS/0.1 (mailto:{settings.contact_email})"}
    ) as client:
        if pdf_path is not None:
            from pathlib import Path

            res = PdfResolution(paper.paper_id, Path(pdf_path), None, "local")
        else:
            res = await resolve_pdf(paper, client=client)

        if res.ok and res.path is not None:
            pdf_bytes = res.path.read_bytes()
            tei = await GrobidClient().process(pdf_bytes, client) if prefer_grobid else None
            doc = (
                parse_tei(tei, paper.paper_id)
                if tei
                else parse_with_pymupdf(str(res.path), paper.paper_id)
            )
        else:
            doc = abstract_only_doc(paper)
    return doc, res


def _offsets_ok(doc: ParsedDoc) -> bool:
    return all(doc.full_text[s.char_start : s.char_end] == s.text for s in doc.sections)


def run_ingest(
    paper: PaperMeta,
    *,
    run_id: str | None = None,
    prefer_grobid: bool = True,
    store: bool = True,
    pdf_path: str | None = None,
) -> tuple[ParsedDoc, IngestReport]:
    t0 = time.monotonic()
    doc, res = asyncio.run(_parse(paper, prefer_grobid=prefer_grobid, pdf_path=pdf_path))

    chunks = chunk_doc(doc)
    n_chunks = len(chunks)

    if store:
        client = vector.get_client()
        try:
            if chunks:
                vecs = embed_texts([c.text for c in chunks])
                n_chunks = vector.upsert_chunks(chunks, vecs, run_id=run_id, client=client)
            # Write-once, and the same representation the loop seeds with (a *document*
            # embedding of title + abstract). Overwriting it here with a query-prefixed,
            # abstract-only vector made a paper's seed relevance depend on whether an
            # earlier run had read it — the same query ranked differently on a warm cache.
            abs_text = f"{paper.title}\n{paper.abstract or doc.full_text[:2000]}".strip()
            if abs_text and not vector.get_abstract_vectors([paper.paper_id], client=client):
                vector.upsert_abstract(
                    paper.paper_id,
                    embed_texts([abs_text])[0],
                    run_id=run_id,
                    title=paper.title,
                    year=paper.year,
                    depth=doc.depth.value,
                    client=client,
                )
        finally:
            client.close()
        if db.get_paper(paper.paper_id) is not None:
            db.set_paper_depth(paper.paper_id, doc.depth.value)

    report = IngestReport(
        paper_id=paper.paper_id,
        pdf_via=res.via,
        structure=doc.structure,
        depth=doc.depth.value,
        n_sections=len(doc.sections),
        n_chunks=n_chunks,
        n_references=len(doc.references),
        full_text_chars=len(doc.full_text),
        offsets_ok=_offsets_ok(doc),
        warnings=list(doc.parse_warnings),
        elapsed_s=time.monotonic() - t0,
    )
    log.info("ingest.done", **{k: v for k, v in report.as_dict().items() if k != "warnings"})
    return doc, report
