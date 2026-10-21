"""PDF -> structured text.

GROBID (`/api/processFulltextDocument`) turns a PDF into TEI XML with real section
headings and a parsed bibliography. If GROBID is unreachable or times out (ADR-005,
R7), fall back to PyMuPDF flat text and mark `structure="flat"`. No PDF at all -> an
`abstract_only` doc (ADR-010).

Normalization happens **once, here** (`normalize.normalize_text`). Every `Section` and the
`full_text` it indexes are normalized, and `full_text[s.char_start:s.char_end] == s.text`
holds exactly — the grounding gate depends on it.
"""

from __future__ import annotations

import hashlib

import httpx
import structlog
from lxml import etree

from atlas.config import settings
from atlas.contracts import Author, Depth, PaperMeta, ParsedDoc, Section
from atlas.ids import canonical_id
from atlas.ingest.normalize import normalize_text, strip_page_numbers, strip_repeated_headers

log = structlog.get_logger(__name__)

_TEI = {"t": "http://www.tei-c.org/ns/1.0"}
GROBID_TIMEOUT = 60.0

# heading substring -> normalized SectionName (first match wins)
_SECTION_MAP: list[tuple[tuple[str, ...], str]] = [
    (("abstract",), "abstract"),
    (("introduction", "background", "motivation"), "intro"),
    (("related work", "prior work", "literature review", "state of the art"), "related"),
    (
        ("method", "methodology", "approach", "materials and methods", "proposed system",
         "system design", "implementation", "architecture", "experimental setup"),
        "methods",
    ),
    (("result", "evaluation", "experiment", "findings", "performance analysis"), "results"),
    (("discussion",), "discussion"),
    (("limitation", "threats to validity"), "limitations"),
    (("future work", "future direction", "further work", "future scope"), "future_work"),
    (("conclusion", "concluding remarks"), "conclusion"),
]


def _map_section(head: str) -> str:
    h = (head or "").lower().strip()
    for keys, name in _SECTION_MAP:
        if any(k in h for k in keys):
            return name
    return "other"


def _assemble(raw_sections: list[tuple[str, str, str]]) -> tuple[str, list[Section]]:
    """`raw_sections` is [(section_name, raw_head, raw_text)]. Returns (full_text, sections)
    with offsets such that full_text[start:end] == section.text exactly."""
    parts: list[str] = []
    sections: list[Section] = []
    cursor = 0
    for name, raw_head, raw_text in raw_sections:
        text = normalize_text(raw_text)
        if not text:
            continue
        if parts:
            cursor += 2  # the "\n\n" that join() inserts
        sections.append(
            Section(
                name=name,
                raw_name=raw_head or name,
                text=text,
                char_start=cursor,
                char_end=cursor + len(text),
            )
        )
        parts.append(text)
        cursor += len(text)
    return "\n\n".join(parts), sections


# ── GROBID / TEI ───────────────────────────────────────────────────────────


class GrobidClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.grobid_url).rstrip("/")

    async def is_alive(self, client: httpx.AsyncClient) -> bool:
        try:
            r = await client.get(f"{self.base_url}/api/isalive", timeout=10.0)
            return r.status_code == 200 and r.text.strip().lower() == "true"
        except httpx.HTTPError:
            return False

    async def process(self, pdf_bytes: bytes, client: httpx.AsyncClient) -> str | None:
        """Return TEI XML, from the on-disk cache if this PDF was parsed before."""
        digest = hashlib.sha1(pdf_bytes).hexdigest()
        cache_path = settings.data_dir / "tei" / f"{digest}.xml"
        if cache_path.exists():
            return cache_path.read_text(encoding="utf-8")

        if not await self.is_alive(client):
            log.warning("grobid.unavailable", base_url=self.base_url)
            return None
        try:
            r = await client.post(
                f"{self.base_url}/api/processFulltextDocument",
                files={"input": ("paper.pdf", pdf_bytes, "application/pdf")},
                data={"consolidateHeader": "1", "consolidateCitations": "0"},
                timeout=GROBID_TIMEOUT,
            )
        except httpx.HTTPError as e:
            log.warning("grobid.request_failed", error=str(e))
            return None
        if r.status_code != 200 or not r.text.strip():
            log.warning("grobid.bad_response", status=r.status_code)
            return None
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(r.text, encoding="utf-8")
        return r.text


def _tei_text(node: etree._Element | None) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def _tei_references(root: etree._Element) -> list[PaperMeta]:
    refs: list[PaperMeta] = []
    for bibl in root.findall(".//t:back//t:listBibl/t:biblStruct", _TEI):
        title_el = bibl.find(".//t:title[@level='a']", _TEI)
        if title_el is None:
            title_el = bibl.find(".//t:title", _TEI)
        title = _tei_text(title_el)
        if not title:
            continue
        authors = [
            Author(name=name)
            for pers in bibl.findall(".//t:author/t:persName", _TEI)
            if (name := _tei_text(pers))
        ]
        date = bibl.find(".//t:imprint/t:date", _TEI)
        year = None
        if date is not None and date.get("when"):
            year = int(date.get("when")[:4]) if date.get("when")[:4].isdigit() else None
        doi_el = bibl.find(".//t:idno[@type='DOI']", _TEI)
        doi = _tei_text(doi_el) or None
        try:
            pid = canonical_id(
                doi=doi, title=title, year=year,
                first_author=authors[0].name if authors else None,
            )
        except ValueError:
            continue
        refs.append(
            PaperMeta(
                paper_id=pid, title=title, year=year, doi=doi, authors=authors,
                found_via=[],
            )
        )
    return refs


def parse_tei(tei_xml: str, paper_id: str) -> ParsedDoc:
    root = etree.fromstring(tei_xml.encode("utf-8"))
    raw_sections: list[tuple[str, str, str]] = []

    abstract = root.find(".//t:profileDesc/t:abstract", _TEI)
    abs_text = ""
    if abstract is not None:
        abs_text = " ".join(_tei_text(p) for p in abstract.findall(".//t:p", _TEI))
    if abs_text:
        raw_sections.append(("abstract", "Abstract", abs_text))

    for div in root.findall(".//t:text/t:body/t:div", _TEI):
        head = _tei_text(div.find("t:head", _TEI))
        body = "\n\n".join(_tei_text(p) for p in div.findall("t:p", _TEI) if _tei_text(p))
        if body:
            raw_sections.append((_map_section(head), head, body))

    full_text, sections = _assemble(raw_sections)
    warnings: list[str] = []
    if not sections:
        warnings.append("grobid returned no usable sections")
    return ParsedDoc(
        paper_id=paper_id,
        depth=Depth.FULL_TEXT if sections else Depth.ABSTRACT_ONLY,
        structure="grobid",
        full_text=full_text,
        sections=sections,
        references=_tei_references(root),
        parse_warnings=warnings,
    )


# ── PyMuPDF fallback / abstract-only ───────────────────────────────────────


def parse_with_pymupdf(pdf_path: str, paper_id: str) -> ParsedDoc:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        pages = [page.get_text() for page in doc]
    finally:
        doc.close()
    pages = strip_page_numbers(strip_repeated_headers(pages))
    full_text, sections = _assemble([("other", "", "\n\n".join(pages))])
    return ParsedDoc(
        paper_id=paper_id,
        depth=Depth.FULL_TEXT if full_text else Depth.ABSTRACT_ONLY,
        structure="flat",
        full_text=full_text,
        sections=sections,
        parse_warnings=["pymupdf fallback — no section structure"],
    )


def abstract_only_doc(paper: PaperMeta) -> ParsedDoc:
    full_text, sections = _assemble([("abstract", "Abstract", paper.abstract or "")])
    return ParsedDoc(
        paper_id=paper.paper_id,
        depth=Depth.ABSTRACT_ONLY if sections else Depth.METADATA_ONLY,
        structure="none",
        full_text=full_text,
        sections=sections,
        parse_warnings=[] if sections else ["no PDF and no abstract"],
    )
