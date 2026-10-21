"""Stopping criteria (SCORING.md §4)."""

from __future__ import annotations

from atlas.forage.stopping import Stopper


def test_budget_stop_on_paper_count():
    s = Stopper("standard")
    s.max_papers = 5
    assert s.check(papers_read=4, total_usd=0, elapsed_s=0, pending_above=10) is None
    assert "5 papers" in s.check(papers_read=5, total_usd=0, elapsed_s=0, pending_above=10)


def test_frontier_exhausted_stop():
    s = Stopper("standard")
    assert "exhausted" in s.check(papers_read=3, total_usd=0, elapsed_s=0, pending_above=0)


def test_three_consecutive_ingest_failures_stop():
    s = Stopper("standard")
    assert s.record_failure() is None
    assert s.record_failure() is None
    assert "hard_failure" in s.record_failure()
    # a good paper resets the streak
    s.record_paper(new_claims=2)
    assert s.record_failure() is None


def test_saturation_fires_after_patience_below_ratio_and_min_papers():
    s = Stopper("standard")
    s.max_papers = 999  # isolate the saturation criterion from the budget one
    # build a tall EMA, then feed zeros until it saturates
    for _ in range(12):
        s.record_paper(new_claims=20)
    peak = s.max_ema
    reason = None
    for _ in range(10):
        s.record_paper(new_claims=0)
        reason = s.check(papers_read=22, total_usd=0, elapsed_s=0, pending_above=50)
        if reason:
            break
    assert reason is not None and "saturation" in reason
    assert s.ema < 0.15 * peak


def test_no_saturation_before_min_papers():
    s = Stopper("standard")
    for _ in range(5):
        s.record_paper(new_claims=10)
    for _ in range(5):
        s.record_paper(new_claims=0)
    # only 10 papers, min_papers floor not cleared for saturation
    assert s.check(papers_read=9, total_usd=0, elapsed_s=0, pending_above=50) is None
