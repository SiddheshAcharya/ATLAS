"""harvest orchestration + Job A prompt plumbing — no network, fake sources."""

from __future__ import annotations

from atlas.contracts import Keyword, PaperMeta, QueryPlan, SourceName
from atlas.harvest import harvest, run_harvest
from atlas.llm.schemas import render_prompt


class FakeSource:
    def __init__(self, name: SourceName, papers: list[PaperMeta]) -> None:
        self.name = name
        self._papers = papers

    async def search(self, plan: QueryPlan, *, per_keyword: int) -> list[PaperMeta]:
        return list(self._papers)


def _p(pid: str, src: SourceName, **kw) -> PaperMeta:
    return PaperMeta(paper_id=pid, title=pid, found_via=[src], **kw)


def _plan() -> QueryPlan:
    return QueryPlan.model_construct(
        query="q", keywords=[Keyword(text="k", tier="exact")], year_from=None, domain_hint=None
    )


async def test_harvest_fans_out_and_dedups_across_sources():
    oa = FakeSource(SourceName.OPENALEX, [_p("doi:1", SourceName.OPENALEX, pdf_url="http://x/p.pdf"),
                                          _p("doi:2", SourceName.OPENALEX)])
    pm = FakeSource(SourceName.PUBMED, [_p("doi:1", SourceName.PUBMED, abstract="abs")])
    papers, report = await harvest(_plan(), sources=[oa, pm])

    assert report.total_raw == 3
    assert report.total_unique == 2
    assert report.multi_source == 1
    assert report.with_pdf_url == 1
    assert report.per_source_raw == {"openalex": 2, "pubmed": 1}
    ids = {p.paper_id for p in papers}
    assert ids == {"doi:1", "doi:2"}


async def test_one_failing_source_does_not_sink_the_harvest():
    class Boom:
        name = SourceName.S2

        async def search(self, plan, *, per_keyword):
            raise RuntimeError("429 forever")

    ok = FakeSource(SourceName.OPENALEX, [_p("doi:9", SourceName.OPENALEX)])
    papers, report = await harvest(_plan(), sources=[ok, Boom()])
    assert [p.paper_id for p in papers] == ["doi:9"]
    assert any("semantic_scholar" in n for n in report.notes)


def test_run_harvest_no_llm_uses_the_raw_query_as_one_keyword():
    seen: list[QueryPlan] = []

    class Capture:
        name = SourceName.OPENALEX

        async def search(self, plan, *, per_keyword):
            seen.append(plan)
            return []

    run_harvest("my raw query", use_llm=False, sources=[Capture()])
    assert [k.text for k in seen[0].keywords] == ["my raw query"]


def test_render_prompt_substitutes_and_leaves_no_placeholder():
    out = render_prompt("keywords.v1.md", query="IoT women safety")
    assert "IoT women safety" in out
    assert "{query}" not in out
