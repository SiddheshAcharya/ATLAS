"""The frontier queue — ordering, admission, no-demote (ADR-003)."""

from __future__ import annotations

from atlas.contracts import ScoreBreakdown
from atlas.forage import frontier
from atlas.store.db import Paper, Run, session_scope

RID = "00000000-0000-0000-0000-0000000000ff"


def _b(total: float) -> ScoreBreakdown:
    return ScoreBreakdown(relevance=total, total=total)


def _setup(paper_ids: list[str]) -> None:
    with session_scope() as s:
        s.merge(Run(run_id=RID, query="q", mode="standard", config_hash="x", status="running"))
        for pid in paper_ids:
            s.merge(Paper(paper_id=pid, title=pid))


def test_pop_order_follows_score_desc(fresh_db: None):
    _setup(["p1", "p2", "p3"])
    frontier.seed(RID, [("p1", _b(0.4)), ("p2", _b(0.9)), ("p3", _b(0.6))])
    assert frontier.pop_highest(RID, 0.25).paper_id == "p2"
    assert frontier.pop_highest(RID, 0.25).paper_id == "p3"
    assert frontier.pop_highest(RID, 0.25).paper_id == "p1"
    assert frontier.pop_highest(RID, 0.25) is None


def test_pop_respects_min_score_floor(fresh_db: None):
    _setup(["lo", "hi"])
    frontier.seed(RID, [("lo", _b(0.1)), ("hi", _b(0.8))])
    assert frontier.pop_highest(RID, 0.25).paper_id == "hi"
    assert frontier.pop_highest(RID, 0.25) is None  # "lo" is below the floor
    assert frontier.pending_above(RID, 0.25) == 0


def test_push_parked_vs_pending_and_counts(fresh_db: None):
    _setup(["a", "b"])
    frontier.push(RID, "a", state="pending", breakdown=_b(0.5), discovered_via="citer_of:x")
    frontier.push(RID, "b", state="parked", breakdown=_b(0.3), discovered_via="citer_of:x",
                  parked_reason="below park threshold")
    counts = frontier.state_counts(RID)
    assert counts == {"pending": 1, "parked": 1}


def test_read_paper_is_not_demoted_by_a_later_push(fresh_db: None):
    _setup(["p"])
    frontier.seed(RID, [("p", _b(0.9))])
    frontier.pop_highest(RID, 0.25)
    frontier.mark(RID, "p", "read", read_order=0)
    frontier.push(RID, "p", state="pending", breakdown=_b(0.2), discovered_via="citer_of:y")
    assert frontier.state_counts(RID) == {"read": 1}
    assert frontier.read_paper_ids(RID) == ["p"]
