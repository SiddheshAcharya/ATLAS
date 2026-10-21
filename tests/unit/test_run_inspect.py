"""`atlas show` backends — list_runs / run_summary."""

from __future__ import annotations

from atlas.store import db
from atlas.store.db import ClaimRow, Frontier, Paper, Run, session_scope

RID = "run-abc-123"


def _seed_a_run() -> None:
    with session_scope() as s:
        # Parents are flushed before children: with no relationship() mappings SQLAlchemy
        # doesn't order INSERTs by foreign key, and Postgres (unlike SQLite) enforces them.
        s.add(Run(run_id=RID, query="q", mode="standard", config_hash="h", status="completed",
                  stop_reason="budget: 2 papers read"))
        for pid in ["doi:1", "doi:2", "doi:parked"]:
            s.add(Paper(paper_id=pid, title="Parked" if pid == "doi:parked" else f"Paper {pid}"))
        s.flush()
        for i, pid in enumerate(["doi:1", "doi:2"]):
            s.add(Frontier(run_id=RID, paper_id=pid, state="read", score=0.9 - i * 0.1,
                           relevance=0.8, novelty=1.0 - i * 0.2, recency=0.7,
                           discovered_via="seed" if i == 0 else "citer_of:doi:1", read_order=i))
        s.add(Frontier(run_id=RID, paper_id="doi:parked", state="parked", score=0.3))
        s.add(ClaimRow(claim_id="c1", run_id=RID, paper_id="doi:1", text="t", quote="q",
                       section="results", verified=True))


def test_run_summary_shapes(fresh_db: None):
    _seed_a_run()
    out = db.run_summary(RID)
    assert out is not None
    assert out["query"] == "q" and out["stop_reason"] == "budget: 2 papers read"
    assert out["frontier_states"] == {"read": 2, "parked": 1}
    assert [r["order"] for r in out["reads"]] == [0, 1]
    assert out["reads"][0]["via"] == "seed"
    assert out["reads"][0]["claims"] == 1
    assert out["reads"][1]["claims"] == 0


def test_run_summary_missing_run(fresh_db: None):
    assert db.run_summary("nope") is None


def test_list_runs_newest_first(fresh_db: None):
    _seed_a_run()
    runs = db.list_runs()
    assert runs and runs[0]["run_id"] == RID


def test_run_timeline_from_saturation_events(fresh_db: None):
    db.emit_event(RID, "saturation", {
        "step": 0, "new_info": 3.0, "ema": 3.0, "paper_id": "doi:1", "title": "Paper doi:1",
        "claims_kept": 2, "claims_dropped": 0, "total_usd": 0.001,
    })
    db.emit_event(RID, "saturation", {
        "step": 1, "new_info": 1.0, "ema": 2.0, "paper_id": "doi:2", "title": "Paper doi:2",
        "claims_kept": 1, "claims_dropped": 1, "total_usd": 0.0025,
    })
    # a non-saturation event in between must not appear as a timeline point
    db.emit_event(RID, "paper_ingested", {"paper_id": "doi:2"})

    points = db.run_timeline(RID)
    assert [p["read_order"] for p in points] == [0, 1]
    assert [p["cumulative_claims"] for p in points] == [2, 3]
    assert points[0]["cumulative_usd"] == 0.001
    assert points[1]["cumulative_usd"] == 0.0025
    assert points[1]["ema"] == 2.0


def test_run_timeline_missing_cost_is_zero_not_wrong(fresh_db: None):
    db.emit_event(RID, "saturation", {
        "step": 0, "new_info": 1.0, "ema": 1.0, "paper_id": "doi:1", "title": "Paper doi:1",
        "claims_kept": 1, "claims_dropped": 0,
    })
    points = db.run_timeline(RID)
    assert points[0]["cumulative_usd"] == 0.0
