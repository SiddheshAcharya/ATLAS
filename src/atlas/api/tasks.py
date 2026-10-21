"""Background orchestration for `POST /runs` (api/routes/runs.py).

`loop.run()` is a long, sync, blocking function — it runs in a worker thread via
`asyncio.to_thread` so the event loop stays free for other requests, including SSE reads
of this same run's events. After the loop finishes — naturally, by user stop, or by
error — this runs concept extraction (Phase 5a) then detectors + fusion + synthesis
(Phase 5b) on whatever graph exists, matching docs/API.md's description of the stop
endpoint ("finishes the current paper, then runs gaps + synthesis on what exists")
applied to every finish, not just a requested stop. Concept extraction has to happen
here too, not just via the separate `atlas concepts` CLI command — the gap detectors
have nothing to find without it, and the Phase 6 exit criterion is that the whole
pipeline runs from a browser with no manual CLI step in between.

`run_finished` (emitted by loop.run() itself) marks the *loop* being done, not the whole
pipeline — gap_found/report_ready still come after it when Neo4j is configured. The SSE
endpoint (api/sse.py) therefore does not close on `run_finished`; it waits for
`pipeline_finished`, emitted here exactly once, on every exit path (success, loop
failure, synthesis failure, or "skipped, no Neo4j") — see the try/finally below.
"""

from __future__ import annotations

import asyncio

import structlog

from atlas.api.registry import RunHandle
from atlas.config import settings
from atlas.extract.concepts import extract_and_store
from atlas.forage.loop import run as run_loop
from atlas.gaps.common import DetectorConfig
from atlas.gaps.fusion import run_detectors
from atlas.store import db
from atlas.store.graph import GraphStore
from atlas.synthesis.report import build_report

log = structlog.get_logger(__name__)


async def run_full_pipeline(
    run_id: str, query: str, mode: str, max_papers: int | None, handle: RunHandle
) -> None:
    try:
        try:
            await asyncio.to_thread(
                run_loop, query, mode=mode, max_papers=max_papers,
                run_id=run_id, should_stop=handle.stop_event.is_set,
            )
        except Exception as e:
            log.error("api.run_failed", run_id=run_id, error=str(e))
            handle.error = str(e)
            db.emit_event(run_id, "error", {"stage": "loop", "message": str(e)})
            db.finish_run(run_id, "failed", f"error: {e}")
            return

        if not settings.neo4j_configured:
            log.info("api.gaps_skipped", run_id=run_id, reason="neo4j not configured")
            return

        try:
            await asyncio.to_thread(_concepts_gaps_and_report, run_id)
        except Exception as e:
            log.error("api.synthesis_failed", run_id=run_id, error=str(e))
            db.emit_event(run_id, "error", {"stage": "synthesis", "message": str(e)})
    finally:
        handle.done = True
        db.emit_event(run_id, "pipeline_finished", {})


def _concepts_gaps_and_report(run_id: str) -> None:
    concepts_report = extract_and_store(run_id)
    log.info(
        "api.concepts_done", run_id=run_id, concepts=concepts_report.concepts,
        methods=concepts_report.methods, datasets=concepts_report.datasets,
    )

    with GraphStore() as g:
        ranked = run_detectors(run_id, g, cfg=DetectorConfig.load())
    for gap in ranked:
        db.emit_event(
            run_id, "gap_found",
            {
                "gap_id": gap.gap_id, "type": gap.type,
                "statement": gap.statement, "rank": gap.rank,
            },
        )
    build_report(run_id, gaps=ranked)
    db.emit_event(run_id, "report_ready", {"run_id": run_id})
