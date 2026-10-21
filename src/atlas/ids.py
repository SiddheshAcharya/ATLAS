"""Canonical paper identity (ADR-006).

Four sources return the same paper with different identifiers. Without one canonical
rule the frontier reads duplicates, PageRank is wrong, and citation counts inflate —
and every one of those errors shows up in the final report.

Nothing else in the codebase constructs a paper_id.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from atlas.contracts import PaperMeta

log = structlog.get_logger(__name__)

_DOI_PREFIX = re.compile(r"^(https?://)?(dx\.)?doi\.org/", re.I)
_ARXIV_CLEAN = re.compile(r"^(https?://)?arxiv\.org/(abs|pdf)/", re.I)
_ARXIV_VERSION = re.compile(r"v\d+$")
_OPENALEX_CLEAN = re.compile(r"^(https?://)?openalex\.org/", re.I)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = _DOI_PREFIX.sub("", doi.strip()).lower().rstrip("/")
    return d or None


def normalize_arxiv(aid: str | None) -> str | None:
    if not aid:
        return None
    a = _ARXIV_CLEAN.sub("", aid.strip())
    a = a.removesuffix(".pdf")
    a = _ARXIV_VERSION.sub("", a)  # 2301.01234v3 -> 2301.01234
    return a.lower() or None


def normalize_openalex(oid: str | None) -> str | None:
    if not oid:
        return None
    return _OPENALEX_CLEAN.sub("", oid.strip()).upper() or None


def normalize_title(title: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    t = unicodedata.normalize("NFKD", title)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = _NON_ALNUM.sub(" ", t.lower())
    return _WS.sub(" ", t).strip()


def canonical_id(
    *,
    doi: str | None = None,
    arxiv_id: str | None = None,
    pmid: str | None = None,
    openalex_id: str | None = None,
    s2_corpus_id: str | None = None,
    title: str | None = None,
    year: int | None = None,
    first_author: str | None = None,
) -> str:
    """Fixed precedence: doi > arxiv > pmid > openalex > s2 > title hash.

    The title-hash fallback can wrongly merge two papers sharing title+year+first author.
    Rare, but log every fallback assignment for audit (caller's responsibility).
    """
    if d := normalize_doi(doi):
        return f"doi:{d}"
    if a := normalize_arxiv(arxiv_id):
        return f"arxiv:{a}"
    if pmid and str(pmid).strip():
        return f"pmid:{str(pmid).strip()}"
    if o := normalize_openalex(openalex_id):
        return f"openalex:{o}"
    if s2_corpus_id and str(s2_corpus_id).strip():
        return f"s2:{str(s2_corpus_id).strip()}"
    if not title:
        raise ValueError("cannot build a canonical id without at least a title")
    surname = ""
    if first_author:
        surname = normalize_title(first_author).split(" ")[-1]
    seed = f"{normalize_title(title)}|{year or ''}|{surname}"
    return "sha1:" + hashlib.sha1(seed.encode()).hexdigest()[:16]


def is_fallback_id(paper_id: str) -> bool:
    """True for title-hash IDs — these should be logged and spot-checked."""
    return paper_id.startswith("sha1:")


# ─── cross-source dedup ─────────────────────────────────────────────────────

_SOURCE_ORDER = ("openalex", "arxiv", "pubmed", "semantic_scholar")


def _merge_pair(keep: PaperMeta, other: PaperMeta) -> PaperMeta:
    """Fold `other` into `keep`, field by field. Deterministic (R9)."""
    data = keep.model_dump()

    # identifiers / scalars: fill blanks from `other`
    for field in (
        "title", "year", "venue", "doi", "arxiv_id", "pmid",
        "openalex_id", "s2_corpus_id", "pdf_url", "license",
    ):
        if not data.get(field) and getattr(other, field):
            data[field] = getattr(other, field)

    # abstract: keep the longer one
    ka, oa = keep.abstract or "", other.abstract or ""
    if len(oa) > len(ka):
        data["abstract"] = other.abstract

    # citation_count: the larger known value
    counts = [c for c in (keep.citation_count, other.citation_count) if c is not None]
    data["citation_count"] = max(counts) if counts else None

    # authors: the more complete list
    if len(other.authors) > len(keep.authors):
        data["authors"] = [a.model_dump() for a in other.authors]

    # found_via: union, in canonical source order
    seen = {s.value for s in keep.found_via} | {s.value for s in other.found_via}
    data["found_via"] = [s for s in _SOURCE_ORDER if s in seen]

    return keep.model_validate(data)


def dedup_papers(papers: list[PaperMeta]) -> list[PaperMeta]:
    """Collapse a multi-source list to one record per canonical `paper_id`.

    Order is preserved by first appearance, so a fixed input order gives a fixed output.
    """
    merged: dict[str, PaperMeta] = {}
    for p in papers:
        existing = merged.get(p.paper_id)
        if existing is None:
            merged[p.paper_id] = p
            continue
        if (
            is_fallback_id(p.paper_id)
            and normalize_title(existing.title) != normalize_title(p.title)
        ):
            log.warning(
                "ids.fallback_merge_titles_differ",
                paper_id=p.paper_id,
                title_a=existing.title,
                title_b=p.title,
            )
        merged[p.paper_id] = _merge_pair(existing, p)
    return list(merged.values())
