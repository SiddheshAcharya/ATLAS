"""arXiv — preprints with guaranteed open-access PDFs.

Atom XML API, no key. Be gentle: ~1 request / 3 s (`min_interval`). Best full-text yield
of the four sources, so it is worth querying even for non-CS topics.
"""

from __future__ import annotations

import re

import structlog
from lxml import etree

from atlas.contracts import Author, PaperMeta, SourceName
from atlas.ids import canonical_id
from atlas.sources.base import HttpSource

log = structlog.get_logger(__name__)

_API = "https://export.arxiv.org/api/query"
_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
_WS = re.compile(r"\s+")
_YEAR = re.compile(r"^(\d{4})")


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    return _WS.sub(" ", text).strip() or None


def _entry_to_paper(entry: etree._Element) -> PaperMeta | None:
    raw_id = _clean(entry.findtext("a:id", namespaces=_NS))  # http://arxiv.org/abs/2301.01234v2
    title = _clean(entry.findtext("a:title", namespaces=_NS))
    if not raw_id or not title:
        return None

    published = entry.findtext("a:published", namespaces=_NS) or ""
    ym = _YEAR.match(published)
    year = int(ym.group(1)) if ym else None

    authors = [
        Author(name=n)
        for el in entry.findall("a:author/a:name", namespaces=_NS)
        if (n := _clean(el.text))
    ]
    doi = _clean(entry.findtext("arxiv:doi", namespaces=_NS))
    pdf_url = None
    for link in entry.findall("a:link", namespaces=_NS):
        if link.get("title") == "pdf":
            pdf_url = link.get("href")
            break

    try:
        pid = canonical_id(
            arxiv_id=raw_id,
            doi=doi,
            title=title,
            year=year,
            first_author=authors[0].name if authors else None,
        )
    except ValueError:
        return None

    return PaperMeta(
        paper_id=pid,
        title=title,
        abstract=_clean(entry.findtext("a:summary", namespaces=_NS)),
        year=year,
        venue="arXiv",
        authors=authors,
        doi=doi,
        arxiv_id=raw_id.rsplit("/", 1)[-1],
        pdf_url=pdf_url,
        license="arxiv-preprint",
        found_via=[SourceName.ARXIV],
    )


class ArxivSource(HttpSource):
    name = SourceName.ARXIV
    min_interval = 3.0

    async def search_keyword(self, keyword: str, *, limit: int) -> list[PaperMeta]:
        params = {
            "search_query": f'all:"{keyword}"',
            "start": 0,
            "max_results": min(limit, 100),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        body = await self._fetch_text(_API, params=params)
        if not body:
            return []
        try:
            root = etree.fromstring(body.encode("utf-8"))
        except etree.XMLSyntaxError:
            log.warning("arxiv.bad_xml", keyword=keyword)
            return []
        papers = [
            p
            for e in root.findall("a:entry", namespaces=_NS)
            if (p := _entry_to_paper(e)) is not None
        ]
        log.debug("arxiv.keyword", keyword=keyword, hits=len(papers))
        return papers
