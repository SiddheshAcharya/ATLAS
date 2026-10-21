"""Offline snapshots — a local, on-disk copy of everything a finished run's dashboard
pages read from Neo4j (graph, gaps, report, stats), so a saved demo run can be replayed
with the network unplugged (docs/TESTING.md, "Demo-day preparation").

Everything else the dashboard shows (papers, claims, quotes, relations, frontier,
timeline) already comes from the local SQLite store. Neo4j AuraDB is the only cloud
dependency for *viewing* a run, so this is the whole gap.

Written by `atlas snapshot --run-id <id>` while online; read by api/routes/runs.py, which
prefers a snapshot for any run that is not currently running.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter

from atlas.config import settings
from atlas.contracts import GraphSnapshot, RankedGap, Report, RunStats

M = TypeVar("M", bound=BaseModel)

_FILES = ("graph.json", "gaps.json", "report.json", "stats.json")
_GAPS = TypeAdapter(list[RankedGap])


def snapshot_dir(run_id: str) -> Path:
    return settings.data_dir / "runs" / run_id / "offline"


def has_snapshot(run_id: str) -> bool:
    d = snapshot_dir(run_id)
    return all((d / f).is_file() for f in _FILES)


def save_snapshot(
    run_id: str,
    *,
    graph: GraphSnapshot,
    gaps: list[RankedGap],
    report: Report,
    stats: RunStats,
) -> Path:
    d = snapshot_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "graph.json").write_text(graph.model_dump_json(), encoding="utf-8")
    (d / "gaps.json").write_bytes(_GAPS.dump_json(gaps))
    (d / "report.json").write_text(report.model_dump_json(), encoding="utf-8")
    (d / "stats.json").write_text(stats.model_dump_json(), encoding="utf-8")
    return d


def load_graph(run_id: str) -> GraphSnapshot:
    return GraphSnapshot.model_validate_json(
        (snapshot_dir(run_id) / "graph.json").read_text(encoding="utf-8")
    )


def load_gaps(run_id: str) -> list[RankedGap]:
    return _GAPS.validate_json((snapshot_dir(run_id) / "gaps.json").read_bytes())


def load_report(run_id: str) -> Report:
    return Report.model_validate_json(
        (snapshot_dir(run_id) / "report.json").read_text(encoding="utf-8")
    )


def load_stats(run_id: str) -> RunStats:
    return RunStats.model_validate_json(
        (snapshot_dir(run_id) / "stats.json").read_text(encoding="utf-8")
    )


def build_and_save(run_id: str) -> Path:
    """Needs the live network (Neo4j for the graph/gaps; the LLM for the report, which
    is normally already an LLM-cache hit). Run once per demo run, before the demo."""
    from atlas.store import db
    from atlas.store.graph import GraphStore
    from atlas.synthesis.report import build_report, ranked_gaps_with_evidence, run_stats

    summary = db.run_summary(run_id)
    if summary is None:
        raise ValueError(f"no run {run_id!r}")

    with GraphStore() as g:
        nodes, edges = g.graph_snapshot(run_id)
    graph = GraphSnapshot(nodes=nodes, edges=edges)

    gaps = ranked_gaps_with_evidence(run_id)
    report = build_report(run_id, gaps=gaps)

    with GraphStore() as g:
        stats = run_stats(run_id, graph=g, summary=summary, wall_clock_seconds=_wall_clock(summary))

    return save_snapshot(run_id, graph=graph, gaps=gaps, report=report, stats=stats)


def refresh_graph(run_id: str) -> Path:
    """Re-save only graph.json of an existing snapshot (after a change to how the graph is
    drawn), leaving gaps/report/stats exactly as they were — so the report and the gap
    list people rated (E6) don't silently change underneath the demo."""
    from atlas.store.graph import GraphStore

    d = snapshot_dir(run_id)
    if not has_snapshot(run_id):
        raise ValueError(f"no existing snapshot for {run_id!r} — run a full snapshot first")
    with GraphStore() as g:
        nodes, edges = g.graph_snapshot(run_id)
    graph = GraphSnapshot(nodes=nodes, edges=edges)
    (d / "graph.json").write_text(graph.model_dump_json(), encoding="utf-8")
    return d


def _wall_clock(summary: dict[str, object]) -> float:
    from datetime import datetime

    started, finished = summary.get("started_at"), summary.get("finished_at")
    if not isinstance(started, str) or not isinstance(finished, str):
        return 0.0
    try:
        return (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
    except ValueError:
        return 0.0
