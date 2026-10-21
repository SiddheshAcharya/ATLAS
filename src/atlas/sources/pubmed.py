"""PubMed E-utilities — biomedical coverage.

Two-step: `esearch` (keyword -> PMIDs) then `efetch` (PMIDs -> article XML). Only really
matters for biomedical queries, but it is free to include and the pipeline diagram
promises it. Optional `NCBI_API_KEY` raises the rate limit from ~3 to ~10 rps.
"""

from __future__ import annotations

import re

import httpx
import structlog
from lxml import etree

from atlas.config import settings
from atlas.contracts import Author, PaperMeta, SourceName
from atlas.ids import canonical_id
from atlas.sources.base import HttpSource

log = structlog.get_logger(__name__)

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_DIGITS4 = re.compile(r"(\d{4})")


def _text(node: etree._Element | None) -> str | None:
    if node is None:
        return None
    return "".join(node.itertext()).strip() or None


def _year(article: etree._Element) -> int | None:
    y = article.findtext(".//Journal/JournalIssue/PubDate/Year")
    if not y:
        md = article.findtext(".//Journal/JournalIssue/PubDate/MedlineDate") or ""
        m = _DIGITS4.search(md)
        y = m.group(1) if m else None
    return int(y) if y else None


def _authors(article: etree._Element) -> list[Author]:
    out: list[Author] = []
    for a in article.findall(".//AuthorList/Author"):
        last = a.findtext("LastName")
        fore = a.findtext("ForeName")
        collective = a.findtext("CollectiveName")
        name = " ".join(p for p in (fore, last) if p) or collective
        if not name:
            continue
        orcid = None
        for ident in a.findall("Identifier"):
            if ident.get("Source") == "ORCID":
                orcid = (ident.text or "").strip() or None
        out.append(Author(name=name, orcid=orcid))
    return out


def _doi(pubmed_article: etree._Element) -> str | None:
    for xp in (
        ".//Article/ELocationID[@EIdType='doi']",
        ".//PubmedData/ArticleIdList/ArticleId[@IdType='doi']",
    ):
        el = pubmed_article.find(xp)
        if el is not None and el.text:
            return str(el.text).strip()
    return None


def _article_to_paper(pubmed_article: etree._Element) -> PaperMeta | None:
    pmid = pubmed_article.findtext(".//MedlineCitation/PMID")
    article = pubmed_article.find(".//MedlineCitation/Article")
    if pmid is None or article is None:
        return None
    title = _text(article.find("ArticleTitle"))
    if not title:
        return None

    abstract_parts = [
        _text(node) for node in article.findall(".//Abstract/AbstractText")
    ]
    abstract = " ".join(p for p in abstract_parts if p) or None
    authors = _authors(article)
    doi = _doi(pubmed_article)

    try:
        pid = canonical_id(
            doi=doi,
            pmid=pmid.strip(),
            title=title,
            year=_year(article),
            first_author=authors[0].name if authors else None,
        )
    except ValueError:
        return None

    return PaperMeta(
        paper_id=pid,
        title=title,
        abstract=abstract,
        year=_year(article),
        venue=article.findtext(".//Journal/Title"),
        authors=authors,
        doi=doi,
        pmid=pmid.strip(),
        found_via=[SourceName.PUBMED],
    )


class PubMedSource(HttpSource):
    name = SourceName.PUBMED
    max_keywords = 10

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(client)
        self.min_interval = 0.11 if settings.ncbi_api_key else 0.34

    def _common_params(self) -> dict[str, str]:
        p = {"db": "pubmed", "tool": "atlas", "email": settings.contact_email}
        if settings.ncbi_api_key:
            p["api_key"] = settings.ncbi_api_key
        return p

    async def search_keyword(self, keyword: str, *, limit: int) -> list[PaperMeta]:
        search = await self._fetch_json(
            _ESEARCH,
            params={**self._common_params(), "term": keyword, "retmax": limit, "retmode": "json"},
        )
        idlist = (((search or {}).get("esearchresult")) or {}).get("idlist") or []
        if not idlist:
            return []

        body = await self._fetch_text(
            _EFETCH,
            params={**self._common_params(), "id": ",".join(idlist[:100]), "retmode": "xml"},
        )
        if not body:
            return []
        try:
            root = etree.fromstring(body.encode("utf-8"))
        except etree.XMLSyntaxError:
            log.warning("pubmed.bad_xml", keyword=keyword)
            return []
        papers = [
            p for a in root.findall(".//PubmedArticle") if (p := _article_to_paper(a)) is not None
        ]
        log.debug("pubmed.keyword", keyword=keyword, hits=len(papers))
        return papers
