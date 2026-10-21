"""Offline snapshots (store/snapshot.py) — a saved run's graph/gaps/report/stats replay from
disk with no Neo4j and no LLM, which is what makes a demo run work with the network unplugged.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from atlas.api import registry
from atlas.api.main import app
from atlas.config import settings
from atlas.contracts import (
    GraphSnapshot,
    PaperRef,
    RankedGap,
    Report,
    ReportSection,
    RunStats,
)
from atlas.store import db, snapshot

client = TestClient(app)
RID = "snap-run-1"


def _stats() -> RunStats:
    return RunStats(
        papers_discovered=9, papers_read=3, full_text_ratio=0.33, claims_extracted=10,
        claims_dropped_ungrounded=1, relations_judged=4, contradictions_found=0,
        bridge_promotions=0, clusters_covered=2, stop_reason="budget", total_usd=0.01,
        wall_clock_seconds=12.0,
    )


def _gap() -> RankedGap:
    return RankedGap(
        gap_id="gap:1", type="unlinked_concepts", statement="A and B never appear together",
        detector_score=0.5,
        bounding_papers=[PaperRef(paper_id="doi:1", title="P1", year=2024, role="evidence")],
        gap_score=0.5, rank=1, found_by=["unlinked_concepts"],
    )


def _report(gaps: list[RankedGap]) -> Report:
    sec = ReportSection(heading="h", body_md="body", citations=[])
    return Report(
        run_id=RID, query="q", agreement=sec, contradictions=sec, gaps=gaps,
        methodology_timeline=sec, stats=_stats(), generated_at=datetime.now(UTC),
    )


@pytest.fixture
def saved_run(fresh_db: None):
    db.create_run(RID, "q", "standard", "cfg")
    db.finish_run(RID, "completed", "budget: 3 papers read")
    gaps = [_gap()]
    snapshot.save_snapshot(
        RID,
        graph=GraphSnapshot(nodes=[{"data": {"id": "doi:1", "label": "P1"}}], edges=[]),
        gaps=gaps, report=_report(gaps), stats=_stats(),
    )
    yield RID
    for f in snapshot.snapshot_dir(RID).glob("*"):
        f.unlink()


@pytest.fixture
def no_neo4j(monkeypatch):
    """Any attempt to reach Neo4j fails the test — proves the snapshot path is offline."""

    class Boom:
        def __init__(self, *a, **k):
            raise AssertionError("touched Neo4j while serving an offline snapshot")

    monkeypatch.setattr(settings, "neo4j_uri", "bolt://unreachable.invalid:7687")
    monkeypatch.setattr("atlas.api.routes.runs.GraphStore", Boom)
    monkeypatch.setattr("atlas.synthesis.report.GraphStore", Boom)


def test_snapshot_roundtrips_every_piece(saved_run):
    assert snapshot.has_snapshot(saved_run)
    assert snapshot.load_graph(saved_run).nodes[0]["data"]["id"] == "doi:1"
    assert snapshot.load_gaps(saved_run)[0].gap_id == "gap:1"
    assert snapshot.load_report(saved_run).query == "q"
    assert snapshot.load_stats(saved_run).papers_read == 3


def test_partial_snapshot_does_not_count(saved_run):
    (snapshot.snapshot_dir(saved_run) / "report.json").unlink()
    assert not snapshot.has_snapshot(saved_run)


def test_routes_serve_snapshot_without_touching_neo4j(saved_run, no_neo4j):
    assert client.get(f"/api/v1/runs/{saved_run}/graph").json()["nodes"][0]["data"]["id"] == "doi:1"
    gaps = client.get(f"/api/v1/runs/{saved_run}/gaps").json()
    assert gaps[0]["bounding_papers"][0]["paper_id"] == "doi:1"
    assert client.get(f"/api/v1/runs/{saved_run}/report").json()["query"] == "q"
    assert "Literature review: q" in client.get(f"/api/v1/runs/{saved_run}/report.md").text
    assert client.get(f"/api/v1/runs/{saved_run}").json()["stats"]["papers_read"] == 3


def test_a_running_run_ignores_the_snapshot(saved_run, no_neo4j):
    handle = registry.register(saved_run)
    try:
        with pytest.raises(AssertionError, match="touched Neo4j"):
            client.get(f"/api/v1/runs/{saved_run}/graph")
    finally:
        handle.done = True
