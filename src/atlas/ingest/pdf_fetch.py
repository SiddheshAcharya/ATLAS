"""PDF resolution chain (R1, ADR-010).

Order of attempts, first hit wins:

    source-provided pdf_url -> arXiv -> Unpaywall -> Europe PMC -> give up

"Give up" is not an error — the paper continues as `abstract_only` (ADR-010). ~40-60%
of papers legitimately have no open PDF. Only legal OA routes are used (R10): no Sci-Hub,
no paywalled scraping.

Downloaded PDFs are the cache: a file already on disk is returned without a network call.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import structlog

from atlas.config import settings
from atlas.contracts import PaperMeta
from atlas.ids import normalize_arxiv, normalize_doi
from atlas.store import cache
from atlas.store.cache import make_key

log = structlog.get_logger(__name__)
_UNPAYWALL_CACHE_TTL = timedelta(days=30)  # matches sources/base.py's CACHE_TTL convention

MAX_PDF_BYTES = 60 * 1024 * 1024
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_PDF_MAGIC = b"%PDF-"


@dataclass
class PdfResolution:
    paper_id: str
    path: Path | None
    url: str | None
    via: str  # cached | source_url | arxiv | unpaywall | europepmc | none
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.path is not None


def _pdf_path(paper_id: str) -> Path:
    return settings.data_dir / "pdfs" / f"{_UNSAFE.sub('_', paper_id)}.pdf"


async def _download(client: httpx.AsyncClient, url: str, dest: Path) -> bool:
    """Stream `url` to `dest` if it is really a PDF and within the size cap."""
    try:
        async with client.stream("GET", url, timeout=60.0, follow_redirects=True) as resp:
            if resp.status_code != 200:
                return False
            ctype = resp.headers.get("content-type", "")
            first = b""
            total = 0
            tmp = dest.with_suffix(".part")
            with tmp.open("wb") as fh:
                async for block in resp.aiter_bytes(65536):
                    if not first:
                        first = block[:5]
                        if _PDF_MAGIC not in first and "pdf" not in ctype.lower():
                            fh.close()
                            tmp.unlink(missing_ok=True)
                            return False
                    total += len(block)
                    if total > MAX_PDF_BYTES:
                        fh.close()
                        tmp.unlink(missing_ok=True)
                        return False
                    fh.write(block)
            if total < 1024:
                tmp.unlink(missing_ok=True)
                return False
            tmp.replace(dest)
            return True
    except (httpx.HTTPError, OSError) as e:
        log.debug("pdf.download_failed", url=url, error=str(e))
        return False


async def _unpaywall_pdf_url(client: httpx.AsyncClient, doi: str) -> str | None:
    """Cached like every other external call (invariant 5) — previously a raw,
    uncached `client.get`, so a warm-cache rerun still made a fresh Unpaywall lookup
    for every abstract-only paper every time. Caches the resolved URL itself (or
    `""` for "no OA location found", which is a real, cacheable answer, not a miss)."""
    url = f"https://api.unpaywall.org/v2/{doi}"
    params = {"email": settings.contact_email}
    key = make_key("GET", url, json.dumps(params, sort_keys=True))
    if settings.cache_enabled:
        hit = cache.api_cache_get(key)
        if hit is not None:
            return str(hit["response"]) or None

    resolved = ""
    try:
        r = await client.get(url, params=params, timeout=30.0)
        if r.status_code == 200:
            loc = r.json().get("best_oa_location") or {}
            resolved = loc.get("url_for_pdf") or loc.get("url") or ""
    except (httpx.HTTPError, ValueError):
        return None  # network/parse failure — don't cache, worth retrying next time

    cache.api_cache_put(
        key, source="unpaywall", response=resolved, status_code=200,
        expires_at=datetime.now(UTC) + _UNPAYWALL_CACHE_TTL,
    )
    return resolved or None


async def resolve_pdf(
    paper: PaperMeta,
    *,
    client: httpx.AsyncClient | None = None,
    download: bool = True,
) -> PdfResolution:
    (settings.data_dir / "pdfs").mkdir(parents=True, exist_ok=True)
    dest = _pdf_path(paper.paper_id)
    if dest.exists() and dest.stat().st_size > 1024:
        return PdfResolution(paper.paper_id, dest, None, "cached")

    owns = client is None
    client = client or httpx.AsyncClient(
        headers={"User-Agent": f"ATLAS/0.1 (mailto:{settings.contact_email})"}
    )
    try:
        arxiv = normalize_arxiv(paper.arxiv_id)
        doi = normalize_doi(paper.doi)
        candidates: list[tuple[str, str]] = []
        if paper.pdf_url:
            candidates.append(("source_url", str(paper.pdf_url)))
        if arxiv:
            candidates.append(("arxiv", f"https://arxiv.org/pdf/{arxiv}.pdf"))
        if doi:
            uw = await _unpaywall_pdf_url(client, doi)
            if uw:
                candidates.append(("unpaywall", uw))
        if paper.pmid:
            candidates.append(
                (
                    "europepmc",
                    f"https://www.ebi.ac.uk/europepmc/webservices/rest/MED/{paper.pmid}/fullTextPDF",
                )
            )

        if not download:
            via, url = (candidates[0] if candidates else ("none", None))
            return PdfResolution(paper.paper_id, None, url, via if candidates else "none")

        for via, url in candidates:
            if await _download(client, url, dest):
                log.info("pdf.resolved", paper_id=paper.paper_id, via=via)
                return PdfResolution(paper.paper_id, dest, url, via)

        return PdfResolution(paper.paper_id, None, None, "none", error="no OA pdf found")
    finally:
        if owns:
            await client.aclose()
