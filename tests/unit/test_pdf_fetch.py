"""PDF resolution chain — order, PDF sniffing, graceful give-up. No live network."""

from __future__ import annotations

import httpx
import respx

from atlas.config import settings
from atlas.contracts import PaperMeta
from atlas.ingest.pdf_fetch import _pdf_path, resolve_pdf

_PDF_BYTES = b"%PDF-1.4\n" + b"x" * 4000


async def test_returns_cached_file_without_network():
    p = PaperMeta(paper_id="doi:10.5/cached", title="T", arxiv_id="2101.00001")
    dest = _pdf_path(p.paper_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_PDF_BYTES)
    try:
        res = await resolve_pdf(p)  # no respx mock -> would raise if it hit the network
        assert res.ok and res.via == "cached"
    finally:
        dest.unlink(missing_ok=True)


@respx.mock
async def test_tries_candidates_in_order_and_sniffs_pdf():
    respx.get("https://example.org/paper.pdf").mock(return_value=httpx.Response(404))
    respx.get("https://arxiv.org/pdf/2101.00002.pdf").mock(
        return_value=httpx.Response(
            200, content=_PDF_BYTES, headers={"content-type": "application/pdf"}
        )
    )
    p = PaperMeta(
        paper_id="doi:10.5/order",
        title="T",
        pdf_url="https://example.org/paper.pdf",
        arxiv_id="2101.00002",
    )
    _pdf_path(p.paper_id).unlink(missing_ok=True)
    res = await resolve_pdf(p)
    assert res.ok and res.via == "arxiv"
    _pdf_path(p.paper_id).unlink(missing_ok=True)


@respx.mock
async def test_rejects_non_pdf_body():
    respx.get("https://example.org/notapdf").mock(
        return_value=httpx.Response(
            200, text="<html>paywall</html>", headers={"content-type": "text/html"}
        )
    )
    p = PaperMeta(paper_id="doi:10.5/html", title="T", pdf_url="https://example.org/notapdf")
    _pdf_path(p.paper_id).unlink(missing_ok=True)
    res = await resolve_pdf(p)
    assert not res.ok and res.via == "none"


@respx.mock
async def test_gives_up_gracefully_when_nothing_resolves(fresh_db):
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))
    p = PaperMeta(paper_id="doi:10.5/nope", title="T", doi="10.5/nope")
    _pdf_path(p.paper_id).unlink(missing_ok=True)
    res = await resolve_pdf(p)
    assert not res.ok
    assert res.error is not None


@respx.mock
async def test_unpaywall_lookup_is_cached(fresh_db, monkeypatch):
    """A second resolve_pdf() for the same DOI must not hit Unpaywall again — this is
    what makes a warm-cache rerun (E8, tests/e2e) actually offline for abstract-only
    papers, not just for papers that already have a downloaded PDF file."""
    monkeypatch.setattr("atlas.ingest.pdf_fetch.settings.cache_enabled", True)
    route = respx.get(url__regex=r"https://api\.unpaywall\.org/.*").mock(
        return_value=httpx.Response(200, json={"best_oa_location": None})
    )
    p = PaperMeta(paper_id="doi:10.5/cache-me", title="T", doi="10.5/cache-me")
    _pdf_path(p.paper_id).unlink(missing_ok=True)

    await resolve_pdf(p)
    assert route.call_count == 1

    await resolve_pdf(p)
    assert route.call_count == 1, "second call should be a cache hit, not a fresh request"


def test_pdf_path_is_filesystem_safe():
    path = _pdf_path("doi:10.1109/ACCESS.2020.1234")
    assert ":" not in path.name and "/" not in path.name
    assert path.parent == settings.data_dir / "pdfs"
