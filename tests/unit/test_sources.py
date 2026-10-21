"""Source mappers — real captured API responses -> PaperMeta. No live network."""

from __future__ import annotations

import httpx
import respx

from atlas.contracts import QueryPlan, SourceName
from atlas.sources.arxiv import ArxivSource
from atlas.sources.openalex import OpenAlexSource, _reconstruct_abstract
from atlas.sources.pubmed import _EFETCH, _ESEARCH, PubMedSource
from atlas.sources.semantic_scholar import SemanticScholarSource
from tests.unit.conftest import fixture


def test_reconstruct_inverted_index():
    inv = {"Hello": [0], "world": [1, 3], "big": [2]}
    assert _reconstruct_abstract(inv) == "Hello world big world"
    assert _reconstruct_abstract(None) is None
    assert _reconstruct_abstract({}) is None


@respx.mock
async def test_openalex_maps_real_response():
    respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, text=fixture("api/openalex_search.json"))
    )
    async with OpenAlexSource() as s:
        papers = await s.search_keyword("women safety alert system", limit=20)

    assert len(papers) == 3
    p = papers[0]
    assert p.title
    assert p.found_via == [SourceName.OPENALEX]
    assert p.paper_id.split(":")[0] in {"doi", "arxiv", "pmid", "openalex", "sha1"}
    # abstract reconstructed to text, not left as an inverted index
    assert p.abstract is None or isinstance(p.abstract, str)


@respx.mock
async def test_arxiv_maps_real_response():
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=fixture("api/arxiv_search.xml"))
    )
    async with ArxivSource() as s:
        papers = await s.search_keyword("human activity recognition", limit=20)

    assert len(papers) == 2
    assert all(p.paper_id.startswith("arxiv:") for p in papers)
    assert all(p.pdf_url and "arxiv.org" in p.pdf_url for p in papers)
    assert all(p.found_via == [SourceName.ARXIV] for p in papers)


@respx.mock
async def test_pubmed_two_step_maps_real_response():
    respx.get(_ESEARCH).mock(
        return_value=httpx.Response(200, text=fixture("api/pubmed_esearch.json"))
    )
    respx.get(_EFETCH).mock(
        return_value=httpx.Response(200, text=fixture("api/pubmed_efetch.xml"))
    )
    async with PubMedSource() as s:
        papers = await s.search_keyword("women safety IoT device", limit=20)

    assert len(papers) == 2
    assert all(p.pmid for p in papers)
    assert all(p.found_via == [SourceName.PUBMED] for p in papers)


@respx.mock
async def test_s2_maps_real_response():
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, text=fixture("api/s2_search.json"))
    )
    async with SemanticScholarSource() as s:
        papers = await s.search_keyword("IoT safety device", limit=20)

    assert len(papers) == 3
    assert all(p.found_via == [SourceName.S2] for p in papers)


@respx.mock
async def test_source_serves_second_call_from_cache(fresh_db: None, monkeypatch):
    monkeypatch.setattr("atlas.sources.base.settings.cache_enabled", True)
    route = respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, text=fixture("api/openalex_search.json"))
    )
    async with OpenAlexSource() as s:
        await s.search_keyword("q", limit=5)
        await s.search_keyword("q", limit=5)

    assert route.call_count == 1  # the second call hit the api_cache, not the network


@respx.mock
async def test_source_outage_yields_empty_not_crash():
    respx.get("https://api.openalex.org/works").mock(return_value=httpx.Response(500))
    plan = QueryPlan.model_construct(query="q", keywords=[], year_from=None, domain_hint=None)
    async with OpenAlexSource() as s:
        assert await s.search_keyword("q", limit=5) == []
        assert await s.search(plan, per_keyword=5) == []
