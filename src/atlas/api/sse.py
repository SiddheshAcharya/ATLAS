"""SSE event stream — `GET /runs/{run_id}/events?since_seq=<n>` (docs/API.md).

Replays persisted events (the `events` table) from `since_seq` first, so a browser
refresh mid-run catches up instead of showing a half-built graph, then polls for new
ones. Single-process, no pub/sub (ARCHITECTURE.md): the run's own loop (or the API's
background task wrapping it, api/tasks.py) writes events via `db.emit_event()` as it
goes, and this just re-reads the same table — replay and live stream can never diverge
because they're the same read.

Closes the stream on `pipeline_finished`, not `run_finished` — the loop finishing
(`run_finished`) is not the end of the story when Neo4j is configured: gap_found and
report_ready still follow, from the same background task's gaps+synthesis phase. A
client that stopped listening at `run_finished` would silently miss those. `tasks.py`
guarantees exactly one `pipeline_finished` on every exit path.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from atlas.store import db

log = structlog.get_logger(__name__)
router = APIRouter(tags=["events"])

_POLL_INTERVAL_S = 1.0


async def _event_stream(
    request: Request, run_id: str, since_seq: int
) -> AsyncIterator[dict[str, Any]]:
    last_seq = since_seq
    while True:
        if await request.is_disconnected():
            log.info("sse.client_disconnected", run_id=run_id)
            return

        events = await asyncio.to_thread(db.events_since, run_id, last_seq)
        for ev in events:
            last_seq = ev["seq"]
            yield {"event": ev["type"], "id": str(ev["seq"]), "data": json.dumps(ev["payload"])}
            if ev["type"] == "pipeline_finished":
                return

        await asyncio.sleep(_POLL_INTERVAL_S)


@router.get("/runs/{run_id}/events")
async def stream_events(
    request: Request, run_id: str, since_seq: int = -1
) -> EventSourceResponse:
    return EventSourceResponse(_event_stream(request, run_id, since_seq))
