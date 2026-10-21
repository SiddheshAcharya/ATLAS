"""Phase 1 — Harvest: research question -> deduplicated `PaperMeta` list.

    query --(Job A)--> QueryPlan --(4 sources, in parallel)--> raw PaperMeta
          --> ids.dedup_papers --> unique PaperMeta  (+ a HarvestReport)

`harvest()` is pure over its inputs (mock the sources / pass a `plan` to test offline).
Persisting to Postgres is the caller's choice (`cli.py` / `store.db.upsert_papers`).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field

import structlog

from atlas.contracts import Keyword, PaperMeta, QueryPlan
from atlas.ids import dedup_papers
from atlas.llm.client import LLMClient
from atlas.llm.schemas import expand_query
from atlas.sources.arxiv import ArxivSource
from atlas.sources.base import Source
from atlas.sources.openalex import OpenAlexSource
from atlas.sources.pubmed import PubMedSource
from atlas.sources.semantic_scholar import SemanticScholarSource

log = structlog.get_logger(__name__)


@dataclass
class HarvestReport:
    query: str
    keywords: list[Keyword]
    per_source_raw: dict[str, int]
    total_raw: int
    total_unique: int
    multi_source: int
    with_pdf_url: int
    with_abstract: int
    elapsed_s: float
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "keywords": [k.model_dump() for k in self.keywords],
            "per_source_raw": self.per_source_raw,
            "total_raw": self.total_raw,
            "total_unique": self.total_unique,
            "multi_source": self.multi_source,
            "with_pdf_url": self.with_pdf_url,
            "with_abstract": self.with_abstract,
            "elapsed_s": round(self.elapsed_s, 1),
            "notes": self.notes,
        }


def default_sources() -> list[Source]:
    return [OpenAlexSource(), ArxivSource(), PubMedSource(), SemanticScholarSource()]


async def harvest(
    plan: QueryPlan,
    *,
    per_keyword: int = 25,
    sources: list[Source] | None = None,
) -> tuple[list[PaperMeta], HarvestReport]:
    """Query every source for every keyword, then dedup across sources."""
    started = time.monotonic()
    sources = sources or default_sources()

    async with contextlib.AsyncExitStack() as stack:
        for s in sources:
            if hasattr(s, "__aenter__"):
                await stack.enter_async_context(s)  # type: ignore[arg-type]
        results = await asyncio.gather(
            *(s.search(plan, per_keyword=per_keyword) for s in sources),
            return_exceptions=True,
        )

    raw: list[PaperMeta] = []
    per_source_raw: dict[str, int] = {}
    notes: list[str] = []
    for src, res in zip(sources, results, strict=True):
        if isinstance(res, BaseException):
            per_source_raw[src.name.value] = 0
            notes.append(f"{src.name.value}: failed ({type(res).__name__})")
            log.warning("harvest.source_failed", source=src.name.value, error=str(res))
            continue
        per_source_raw[src.name.value] = len(res)
        raw.extend(res)

    unique = dedup_papers(raw)
    report = HarvestReport(
        query=plan.query,
        keywords=list(plan.keywords),
        per_source_raw=per_source_raw,
        total_raw=len(raw),
        total_unique=len(unique),
        multi_source=sum(1 for p in unique if len(p.found_via) > 1),
        with_pdf_url=sum(1 for p in unique if p.pdf_url),
        with_abstract=sum(1 for p in unique if p.abstract),
        elapsed_s=time.monotonic() - started,
        notes=notes,
    )
    log.info("harvest.done", **{k: v for k, v in report.as_dict().items() if k != "keywords"})
    return unique, report


def run_harvest(
    query: str,
    *,
    per_keyword: int = 25,
    use_llm: bool = True,
    client: LLMClient | None = None,
    sources: list[Source] | None = None,
) -> tuple[list[PaperMeta], HarvestReport]:
    """Sync entry point: Job A (keyword expansion) then the async fan-out."""
    if use_llm:
        plan = expand_query(client or LLMClient(), query)
    else:
        # debug path: skip Job A. QueryPlan needs >=8 keywords, so bypass validation.
        plan = QueryPlan.model_construct(
            query=query, keywords=[Keyword(text=query, tier="exact")], year_from=None,
            domain_hint=None,
        )
    return asyncio.run(harvest(plan, per_keyword=per_keyword, sources=sources))
