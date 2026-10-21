"""OpenAlex — primary metadata + citation graph source.

No key needed; `mailto=` puts us in the polite pool (100k/day, 10 rps). Abstracts arrive
as an **inverted index** (`{word: [positions]}`) and must be reconstructed before use —
`_reconstruct_abstract` does that; nothing downstream should see the raw index.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from atlas.config import settings
from atlas.contracts import Author, PaperMeta, SourceName
from atlas.ids import canonical_id
from atlas.sources.base import HttpSource

log = structlog.get_logger(__name__)

_WORKS = "https://api.openalex.org/works"
_SELECT = (
    "id,doi,title,display_name,publication_year,primary_location,best_oa_location,"
    "authorships,cited_by_count,ids,abstract_inverted_index,language,type"
)
_PMID_DIGITS = re.compile(r"(\d+)")
_ARXIV_IN_URL = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", re.I)


def _reconstruct_abstract(inv: dict[str, list[int]] | None) -> str | None:
    if not inv:
        return None
    positions: list[tuple[int, str]] = [(i, w) for w, idxs in inv.items() for i in idxs]
    positions.sort()
    return " ".join(w for _, w in positions) or None


def _pmid(ids: dict[str, Any]) -> str | None:
    raw = ids.get("pmid")
    if not raw:
        return None
    m = _PMID_DIGITS.search(str(raw))
    return m.group(1) if m else None


def _arxiv_id(work: dict[str, Any]) -> str | None:
    for loc_key in ("primary_location", "best_oa_location"):
        loc = work.get(loc_key) or {}
        for url_key in ("landing_page_url", "pdf_url"):
            m = _ARXIV_IN_URL.search(str(loc.get(url_key) or ""))
            if m:
                return m.group(1)
    return None


def _authors(work: dict[str, Any]) -> list[Author]:
    out: list[Author] = []
    for a in work.get("authorships", []) or []:
        author = a.get("author") or {}
        name = author.get("display_name")
        if not name:
            continue
        aid = author.get("id") or ""
        out.append(
            Author(
                name=name,
                author_id=aid.rsplit("/", 1)[-1] or None,
                orcid=author.get("orcid"),
            )
        )
    return out


def _to_paper(work: dict[str, Any]) -> PaperMeta | None:
    title = work.get("title") or work.get("display_name")
    if not title:
        return None
    ids = work.get("ids") or {}
    authors = _authors(work)
    oa_pdf = (work.get("best_oa_location") or {}).get("pdf_url")
    prim_pdf = (work.get("primary_location") or {}).get("pdf_url")
    licence = (work.get("best_oa_location") or {}).get("license") or (
        work.get("primary_location") or {}
    ).get("license")
    venue = ((work.get("primary_location") or {}).get("source") or {}).get("display_name")

    try:
        pid = canonical_id(
            doi=work.get("doi"),
            arxiv_id=_arxiv_id(work),
            pmid=_pmid(ids),
            openalex_id=work.get("id"),
            title=title,
            year=work.get("publication_year"),
            first_author=authors[0].name if authors else None,
        )
    except ValueError:
        return None

    return PaperMeta(
        paper_id=pid,
        title=title,
        abstract=_reconstruct_abstract(work.get("abstract_inverted_index")),
        year=work.get("publication_year"),
        venue=venue,
        authors=authors,
        doi=work.get("doi"),
        arxiv_id=_arxiv_id(work),
        pmid=_pmid(ids),
        openalex_id=(work.get("id") or "").rsplit("/", 1)[-1] or None,
        pdf_url=oa_pdf or prim_pdf,
        license=licence,
        citation_count=work.get("cited_by_count"),
        found_via=[SourceName.OPENALEX],
    )


def _oa_short(oid: str | None) -> str | None:
    if not oid:
        return None
    return oid.rsplit("/", 1)[-1] or None


class OpenAlexSource(HttpSource):
    name = SourceName.OPENALEX
    min_interval = 0.15

    async def search_keyword(self, keyword: str, *, limit: int) -> list[PaperMeta]:
        params = {
            "search": keyword,
            "per-page": min(limit, 200),
            "select": _SELECT,
            "mailto": settings.contact_email,
        }
        data = await self._fetch_json(_WORKS, params=params)
        if not data or "results" not in data:
            return []
        papers = [p for w in data["results"] if (p := _to_paper(w)) is not None]
        log.debug("openalex.keyword", keyword=keyword, hits=len(papers))
        return papers

    # ── citation-graph expansion (Phase 3) ──────────────────────────────────

    async def _work(self, oa_path: str) -> dict[str, Any] | None:
        data = await self._fetch_json(
            f"{_WORKS}/{oa_path}",
            params={"select": _SELECT + ",referenced_works", "mailto": settings.contact_email},
        )
        return data if isinstance(data, dict) and data.get("id") else None

    async def resolve_openalex_id(self, paper: PaperMeta) -> str | None:
        if paper.openalex_id:
            return _oa_short(paper.openalex_id)
        if paper.doi:
            doi = paper.doi.rsplit("doi.org/", 1)[-1]
            work = await self._work(f"doi:{doi}")
            return _oa_short(work.get("id")) if work else None
        return None

    async def _fetch_by_ids(self, ids: list[str]) -> list[PaperMeta]:
        out: list[PaperMeta] = []
        for i in range(0, len(ids), 50):
            chunk = ids[i : i + 50]
            data = await self._fetch_json(
                _WORKS,
                params={
                    "filter": f"openalex_id:{'|'.join(chunk)}",
                    "per-page": 50,
                    "select": _SELECT,
                    "mailto": settings.contact_email,
                },
            )
            if data and data.get("results"):
                out.extend(p for w in data["results"] if (p := _to_paper(w)) is not None)
        return out

    async def references(self, paper: PaperMeta, *, limit: int = 60) -> list[PaperMeta]:
        oid = await self.resolve_openalex_id(paper)
        if not oid:
            return []
        work = await self._work(oid)
        if not work:
            return []
        ref_ids = [
            short for r in (work.get("referenced_works") or []) if (short := _oa_short(r))
        ][:limit]
        return await self._fetch_by_ids(ref_ids)

    async def citers(self, paper: PaperMeta, *, limit: int = 60) -> list[PaperMeta]:
        oid = await self.resolve_openalex_id(paper)
        if not oid:
            return []
        data = await self._fetch_json(
            _WORKS,
            params={
                "filter": f"cites:{oid}",
                "per-page": min(limit, 200),
                "sort": "cited_by_count:desc",
                "select": _SELECT,
                "mailto": settings.contact_email,
            },
        )
        if not data or not data.get("results"):
            return []
        return [p for w in data["results"] if (p := _to_paper(w)) is not None]
