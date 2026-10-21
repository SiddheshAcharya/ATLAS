"""Semantic Scholar — enrichment: abstracts, TLDRs, open-access PDF links, citation counts.

Tight rate limits (shared ~100 req/5 min without a key; ~1 rps with one). Used only as a
harvest enrichment source here — **never** as the citation-graph walker (that is OpenAlex).
A 429 storm just yields an empty list; the harvest carries on.
"""

from __future__ import annotations

from typing import Any

import structlog

from atlas.config import settings
from atlas.contracts import Author, PaperMeta, SourceName
from atlas.ids import canonical_id
from atlas.sources.base import HttpSource

log = structlog.get_logger(__name__)

_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "title,abstract,year,venue,authors,externalIds,openAccessPdf,citationCount"


def _to_paper(item: dict[str, Any]) -> PaperMeta | None:
    title = item.get("title")
    if not title:
        return None
    ext = item.get("externalIds") or {}
    corpus_id = ext.get("CorpusId")
    authors = [
        Author(name=a["name"], author_id=a.get("authorId"))
        for a in (item.get("authors") or [])
        if a.get("name")
    ]
    try:
        pid = canonical_id(
            doi=ext.get("DOI"),
            arxiv_id=ext.get("ArXiv"),
            pmid=str(ext["PubMed"]) if ext.get("PubMed") else None,
            s2_corpus_id=str(corpus_id) if corpus_id else None,
            title=title,
            year=item.get("year"),
            first_author=authors[0].name if authors else None,
        )
    except ValueError:
        return None

    return PaperMeta(
        paper_id=pid,
        title=title,
        abstract=item.get("abstract"),
        year=item.get("year"),
        venue=item.get("venue") or None,
        authors=authors,
        doi=ext.get("DOI"),
        arxiv_id=ext.get("ArXiv"),
        pmid=str(ext["PubMed"]) if ext.get("PubMed") else None,
        s2_corpus_id=str(corpus_id) if corpus_id else None,
        pdf_url=(item.get("openAccessPdf") or {}).get("url"),
        citation_count=item.get("citationCount"),
        found_via=[SourceName.S2],
    )


class SemanticScholarSource(HttpSource):
    name = SourceName.S2
    min_interval = 1.1
    max_keywords = 8  # spare the shared rate-limit pool

    async def search_keyword(self, keyword: str, *, limit: int) -> list[PaperMeta]:
        headers = {}
        if settings.semantic_scholar_api_key:
            headers["x-api-key"] = settings.semantic_scholar_api_key
        params = {"query": keyword, "limit": min(limit, 100), "fields": _FIELDS}
        data = await self._fetch_json(_SEARCH, params=params, headers=headers)
        if not data or not data.get("data"):
            return []
        papers = [p for it in data["data"] if (p := _to_paper(it)) is not None]
        log.debug("s2.keyword", keyword=keyword, hits=len(papers))
        return papers
