"""In-memory registry of currently-running foraging loops.

Single-process architecture (ARCHITECTURE.md — "one process, not a queue-worker
fleet"): there is no external queue or lock service, just a module-level dict mapping
run_id to a control handle. `loop.run()` executes in a worker thread (via
`asyncio.to_thread`, see `api/tasks.py`) so a `threading.Event`, not `asyncio.Event`, is
the right cross-thread stop signal — the API request handling POST /stop runs on the
event loop thread, the loop itself runs on a worker thread.

This registry does not survive a server restart — an in-flight run's `should_stop` is
unreachable after a restart, which just means `/stop` on it 404s; the run itself is
unaffected (Postgres/Neo4j/Qdrant are the durable state, per ARCHITECTURE.md).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class RunHandle:
    stop_event: threading.Event = field(default_factory=threading.Event)
    error: str | None = None
    done: bool = False


_runs: dict[str, RunHandle] = {}


def register(run_id: str) -> RunHandle:
    handle = RunHandle()
    _runs[run_id] = handle
    return handle


def get(run_id: str) -> RunHandle | None:
    return _runs.get(run_id)


def request_stop(run_id: str) -> bool:
    """True if a live handle was found and signalled; False if this run isn't (or is no
    longer) tracked in this process — the caller should treat that as "already finished",
    not as an error, since run state itself lives in the DB, not here."""
    handle = _runs.get(run_id)
    if handle is None:
        return False
    handle.stop_event.set()
    return True
