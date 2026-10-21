"""`/runs*` routes (docs/API.md) — start/list/inspect/stop a run, and read its graph,
frontier, papers, gaps, and report. Response bodies are always the Pydantic models from
`contracts.py`, never ad-hoc dicts, per API.md's own rule.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Response

from atlas.api import registry, tasks
from atlas.config import settings
from atlas.contracts import (
    FrontierRow,
    GraphSnapshot,
    PaperDetail,
    PaperSource,
    RankedGap,
    Report,
    RunCreateRequest,
    RunCreateResponse,
    RunDetail,
    RunListItem,
    SourceSpan,
    TimelinePoint,
)
from atlas.forage import frontier as frontier_mod
from atlas.store import db, snapshot, vector
from atlas.store.graph import GraphStore
from atlas.synthesis.report import (
    build_report,
    ranked_gaps_with_evidence,
    render_markdown,
    run_stats,
)

log = structlog.get_logger(__name__)
router = APIRouter(tags=["runs"])


def _serve_snapshot(run_id: str) -> bool:
    """A finished run with a saved offline snapshot is read from disk, not Neo4j — this
    is what lets a demo run replay with the network unplugged (store/snapshot.py). A run
    that is still going always reads live, so its graph keeps updating."""
    if not snapshot.has_snapshot(run_id):
        return False
    handle = registry.get(run_id)
    return handle is None or handle.done

# Strong references to in-flight background tasks — asyncio.create_task()'s result must
# be kept alive or the task can be garbage-collected mid-run (asyncio docs warning).
_background_tasks: set[asyncio.Task[None]] = set()


@router.post("/runs", response_model=RunCreateResponse)
async def create_run(body: RunCreateRequest) -> RunCreateResponse:
    run_id = str(uuid4())
    handle = registry.register(run_id)
    task = asyncio.create_task(
        tasks.run_full_pipeline(run_id, body.query, body.mode, body.max_papers, handle)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return RunCreateResponse(run_id=run_id)


@router.get("/runs", response_model=list[RunListItem])
def list_runs() -> list[RunListItem]:
    # every run, not the store default of 15: the demo runs are older than the latest
    # crawls and had silently dropped off the home page
    return [
        RunListItem(**row, offline=snapshot.has_snapshot(row["run_id"]))
        for row in db.list_runs(limit=500)
    ]


def _wall_clock_seconds(summary: dict[str, object]) -> float:
    started, finished = summary.get("started_at"), summary.get("finished_at")
    if not isinstance(started, str) or not isinstance(finished, str):
        return 0.0
    try:
        from datetime import datetime

        return (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
    except ValueError:
        return 0.0


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str) -> RunDetail:
    summary = db.run_summary(run_id)
    if summary is None:
        raise HTTPException(404, f"no run {run_id!r}")

    if _serve_snapshot(run_id):
        stats = snapshot.load_stats(run_id)
    else:
        graph = GraphStore() if settings.neo4j_configured else None
        try:
            stats = run_stats(
                run_id, graph=graph, summary=summary,
                wall_clock_seconds=_wall_clock_seconds(summary),
            )
        finally:
            if graph is not None:
                graph.close()

    return RunDetail(
        run_id=summary["run_id"], query=summary["query"], mode=summary["mode"],
        status=summary["status"], stop_reason=summary["stop_reason"],
        config_hash=summary["config_hash"], started_at=summary["started_at"],
        finished_at=summary["finished_at"], keywords=db.run_keywords(run_id), stats=stats,
    )


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str) -> dict[str, bool]:
    """Graceful stop — the loop finishes its current paper, then the background task
    still runs gaps + synthesis on what exists (api/tasks.py), same as a natural finish."""
    stopped = registry.request_stop(run_id)
    if not stopped:
        raise HTTPException(404, f"run {run_id!r} is not tracked in this process")
    return {"stopping": True}


@router.get("/runs/{run_id}/graph", response_model=GraphSnapshot)
def get_graph(run_id: str) -> GraphSnapshot:
    if _serve_snapshot(run_id):
        return snapshot.load_graph(run_id)
    if not settings.neo4j_configured:
        raise HTTPException(409, "neo4j not configured — no graph for this run")
    with GraphStore() as g:
        nodes, edges = g.graph_snapshot(run_id)
    return GraphSnapshot(nodes=nodes, edges=edges)


@router.get("/runs/{run_id}/frontier", response_model=list[FrontierRow])
def get_frontier(run_id: str) -> list[FrontierRow]:
    return [FrontierRow(**row) for row in frontier_mod.rows_for(run_id)]


@router.get("/runs/{run_id}/timeline", response_model=list[TimelinePoint])
def get_timeline(run_id: str) -> list[TimelinePoint]:
    return [TimelinePoint(**row) for row in db.run_timeline(run_id)]


# Registered before the plain paper route: `{paper_id:path}` is greedy and would otherwise
# swallow the trailing "/source".
@router.get("/runs/{run_id}/papers/{paper_id:path}/source", response_model=PaperSource)
def get_paper_source(run_id: str, paper_id: str) -> PaperSource:
    origin = "this_run"
    rows = vector.get_chunks_by_paper(paper_id, run_id=run_id)
    if not rows:
        # chunk points are keyed per paper: a later run that re-read it re-labelled them
        origin, rows = "other_run", vector.get_chunks_by_paper(paper_id)
    if not rows:
        paper = db.get_paper(paper_id)
        if paper is None or not paper.abstract:
            raise HTTPException(404, f"no stored text for {paper_id!r}")
        from atlas.ingest.grobid import abstract_only_doc

        doc = abstract_only_doc(paper)  # the same normalized text abstract-only claims index
        return PaperSource(
            paper_id=paper_id, text=doc.full_text, origin="abstract",
            sections=[SourceSpan(name=s.name, char_start=s.char_start, char_end=s.char_end)
                      for s in doc.sections],
        )
    # Chunks carry full_text offsets; place each at its offset. Characters between chunks
    # (dropped separators) become newlines, so offsets stay exact.
    buf = ["\n"] * max(int(r["char_end"]) for r in rows)
    sections: list[SourceSpan] = []
    for r in rows:
        start = int(r["char_start"])
        buf[start : start + len(r["text"])] = list(r["text"])
        name = str(r.get("section") or "other")
        if sections and sections[-1].name == name:
            sections[-1].char_end = max(sections[-1].char_end, int(r["char_end"]))
        else:
            sections.append(SourceSpan(name=name, char_start=start, char_end=int(r["char_end"])))
    return PaperSource(paper_id=paper_id, text="".join(buf), sections=sections, origin=origin)


# `:path` — DOI ids contain "/" and the browser's %2F is decoded before routing, so a plain
# `{paper_id}` 404s every DOI paper (found live: most IoT-corpus papers are DOIs).
@router.get("/runs/{run_id}/papers/{paper_id:path}", response_model=PaperDetail)
def get_paper_detail(run_id: str, paper_id: str) -> PaperDetail:
    paper = db.get_paper(paper_id)
    if paper is None:
        raise HTTPException(404, f"no paper {paper_id!r}")
    claims, relations = db.paper_claims_and_relations(run_id, paper_id)
    return PaperDetail(paper=paper, claims=claims, relations=relations)


@router.get("/runs/{run_id}/gaps", response_model=list[RankedGap])
def get_gaps(run_id: str) -> list[RankedGap]:
    if _serve_snapshot(run_id):
        return snapshot.load_gaps(run_id)
    if not settings.neo4j_configured:
        raise HTTPException(409, "neo4j not configured — no gaps for this run")
    return ranked_gaps_with_evidence(run_id)


def _build_report(run_id: str) -> Report:
    if _serve_snapshot(run_id):
        return snapshot.load_report(run_id)
    if not settings.neo4j_configured:
        raise HTTPException(409, "neo4j not configured — no report for this run")
    ranked = ranked_gaps_with_evidence(run_id)
    try:
        return build_report(run_id, gaps=ranked)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/runs/{run_id}/report", response_model=Report)
def get_report(run_id: str) -> Report:
    return _build_report(run_id)


@router.get("/runs/{run_id}/report.md")
def get_report_markdown(run_id: str) -> Response:
    report = _build_report(run_id)
    return Response(content=render_markdown(report), media_type="text/markdown")
