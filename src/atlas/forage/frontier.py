"""The frontier queue — a Postgres table, not a heap (ADR-003).

Ordered pop, partial re-score of many rows, crash recovery, and "why did it read that
paper 12th?" as one SQL query. A paper must exist in `papers` before it is pushed here
(FK). Cross-source dedup already happened upstream; the key is the canonical `paper_id`.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa
import structlog

from atlas.contracts import ScoreBreakdown
from atlas.store.db import Frontier, session_scope

log = structlog.get_logger(__name__)


@dataclass
class Popped:
    paper_id: str
    score: float
    discovered_via: str
    relevance: float = 0.0
    novelty: float = 0.0
    recency: float = 0.0
    pagerank: float = 0.0
    contest: float = 0.0


def _apply_breakdown(row: Frontier, b: ScoreBreakdown) -> None:
    row.relevance = b.relevance
    row.pagerank = b.pagerank
    row.novelty = b.novelty
    row.contest = b.contest
    row.recency = b.recency
    row.score = b.total


def seed(run_id: str, ranked: list[tuple[str, ScoreBreakdown]]) -> int:
    """Insert the seed papers as `pending`. `ranked` is [(paper_id, score_breakdown)]."""
    with session_scope() as s:
        for paper_id, b in ranked:
            row = s.get(Frontier, {"run_id": run_id, "paper_id": paper_id})
            if row is None:
                row = Frontier(run_id=run_id, paper_id=paper_id, state="pending",
                               discovered_via="seed")
                s.add(row)
            _apply_breakdown(row, b)
    return len(ranked)


def push(
    run_id: str,
    paper_id: str,
    *,
    state: str,
    breakdown: ScoreBreakdown,
    discovered_via: str,
    parked_reason: str | None = None,
) -> None:
    """Add or update a discovered paper. Never demotes a paper already read/reading."""
    with session_scope() as s:
        row = s.get(Frontier, {"run_id": run_id, "paper_id": paper_id})
        if row is None:
            row = Frontier(run_id=run_id, paper_id=paper_id, state=state,
                           discovered_via=discovered_via, parked_reason=parked_reason)
            s.add(row)
            _apply_breakdown(row, breakdown)
            return
        if row.state in ("read", "reading", "failed"):
            return
        row.state = state
        row.parked_reason = parked_reason
        _apply_breakdown(row, breakdown)


def pop_highest(run_id: str, min_score: float) -> Popped | None:
    """Take the top `pending` paper at or above `min_score`; mark it `reading`."""
    with session_scope() as s:
        row = s.execute(
            sa.select(Frontier)
            .where(
                Frontier.run_id == run_id,
                Frontier.state == "pending",
                Frontier.score >= min_score,
            )
            .order_by(Frontier.score.desc(), Frontier.paper_id)  # paper_id breaks score ties
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        row.state = "reading"
        row.attempts = (row.attempts or 0) + 1
        return Popped(
            row.paper_id, row.score or 0.0, row.discovered_via or "",
            relevance=row.relevance or 0.0, novelty=row.novelty or 0.0,
            recency=row.recency or 0.0, pagerank=row.pagerank or 0.0,
            contest=row.contest or 0.0,
        )


def mark(run_id: str, paper_id: str, state: str, *, read_order: int | None = None) -> None:
    with session_scope() as s:
        row = s.get(Frontier, {"run_id": run_id, "paper_id": paper_id})
        if row is None:
            return
        row.state = state
        if read_order is not None:
            row.read_order = read_order


def update_scores(run_id: str, updates: dict[str, ScoreBreakdown]) -> None:
    """Bulk re-score pending/parked rows (novelty every iteration, etc.)."""
    if not updates:
        return
    with session_scope() as s:
        rows = s.execute(
            sa.select(Frontier).where(
                Frontier.run_id == run_id,
                Frontier.paper_id.in_(list(updates)),
                Frontier.state.in_(("pending", "parked")),
            )
        ).scalars()
        for row in rows:
            _apply_breakdown(row, updates[row.paper_id])


def pending_above(run_id: str, min_score: float) -> int:
    with session_scope() as s:
        return int(
            s.execute(
                sa.select(sa.func.count())
                .select_from(Frontier)
                .where(
                    Frontier.run_id == run_id,
                    Frontier.state == "pending",
                    Frontier.score >= min_score,
                )
            ).scalar_one()
        )


def state_counts(run_id: str) -> dict[str, int]:
    with session_scope() as s:
        rows = s.execute(
            sa.select(Frontier.state, sa.func.count())
            .where(Frontier.run_id == run_id)
            .group_by(Frontier.state)
        ).all()
    return {state: n for state, n in rows}


def read_paper_ids(run_id: str) -> list[str]:
    with session_scope() as s:
        return list(
            s.execute(
                sa.select(Frontier.paper_id)
                .where(Frontier.run_id == run_id, Frontier.state == "read")
                .order_by(Frontier.read_order)
            ).scalars()
        )


def parked_paper_ids(run_id: str, limit: int = 15) -> list[str]:
    """Parked papers, highest relevance first — bridge-promotion candidates."""
    with session_scope() as s:
        return list(
            s.execute(
                sa.select(Frontier.paper_id)
                .where(Frontier.run_id == run_id, Frontier.state == "parked")
                .order_by(Frontier.relevance.desc().nulls_last(), Frontier.paper_id)
                .limit(limit)
            ).scalars()
        )


def promote_bridge(run_id: str, paper_id: str) -> None:
    """Move a parked paper to pending and tag it as a bridge (SCORING.md §3)."""
    with session_scope() as s:
        row = s.get(Frontier, {"run_id": run_id, "paper_id": paper_id})
        if row is not None and row.state == "parked":
            row.state = "pending"
            row.discovered_via = "bridge"
            row.parked_reason = None


def scored_paper_ids(run_id: str) -> list[str]:
    """Ids of every pending/parked row — the set re-scored each iteration."""
    with session_scope() as s:
        return list(
            s.execute(
                sa.select(Frontier.paper_id)
                .where(
                    Frontier.run_id == run_id,
                    Frontier.state.in_(("pending", "parked")),
                )
                .order_by(Frontier.paper_id)
            ).scalars()
        )


def rows_for(run_id: str) -> list[dict[str, object]]:
    """Every frontier row (all states), highest score first — the "why did it read that
    paper?" view, GET /runs/{id}/frontier (docs/API.md). Unlike `db.run_summary`'s
    `reads`, this includes pending/parked/dropped/failed rows too."""
    from atlas.store.db import Paper

    with session_scope() as s:
        rows = s.execute(
            sa.select(Frontier, Paper.title, Paper.depth)
            .join(Paper, Paper.paper_id == Frontier.paper_id)
            .where(Frontier.run_id == run_id)
            .order_by(Frontier.score.desc().nulls_last(), Frontier.paper_id)
        ).all()
    return [
        {
            "paper_id": f.paper_id, "title": title, "state": f.state, "score": f.score,
            "relevance": f.relevance, "novelty": f.novelty, "recency": f.recency,
            "pagerank": f.pagerank, "contest": f.contest,
            "discovered_via": f.discovered_via, "parked_reason": f.parked_reason,
            "read_order": f.read_order, "depth": depth,
        }
        for f, title, depth in rows
    ]
