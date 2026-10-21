"""Frontier scoring (SCORING.md §1).

    score = w_rel·Relevance + w_pr·PageRank + w_nov·Novelty + w_con·Contest + w_rec·Recency

Every component is in [0, 1] and every weight comes from `config/scoring.yaml` (the
ablation study zeroes them from there). This phase computes **Relevance, Recency and
Novelty**; PageRank and Contest need GDS / the judge and stay 0 until Phase 4 — the
weighted sum and the ablation hooks are already in place.
"""

from __future__ import annotations

import math
import statistics

from atlas.config_files import scoring
from atlas.contracts import ScoreBreakdown

Vector = list[float]


def cosine(a: Vector, b: Vector) -> float:
    """Dot product — inputs are unit-normalised (bge `normalize_embeddings=True`)."""
    return sum(x * y for x, y in zip(a, b, strict=True))


def relevance_scores(query_vec: Vector, paper_vecs: dict[str, Vector]) -> dict[str, float]:
    """Cosine to the query, then min-max normalised **across this set** (SCORING.md)."""
    if not paper_vecs:
        return {}
    raw = {pid: cosine(query_vec, v) for pid, v in paper_vecs.items()}
    lo, hi = min(raw.values()), max(raw.values())
    span = (hi - lo) or 1.0
    return {pid: (r - lo) / span for pid, r in raw.items()}


def raw_relevance(query_vec: Vector, paper_vec: Vector) -> float:
    """Un-normalised cosine — used for the admission bands, which are absolute."""
    return cosine(query_vec, paper_vec)


def recency_score(year: int | None, frontier_years: list[int], *, now_year: int) -> float:
    half_life = float(scoring()["recency"]["half_life_years"])
    if year is None:
        year = int(statistics.median(frontier_years)) if frontier_years else now_year
    age = max(0, now_year - year)
    return math.exp(-math.log(2) * age / half_life)


def novelty_score(paper_vec: Vector, read_vecs: list[Vector]) -> float:
    """1 - max cosine to any already-read paper. 1.0 when nothing has been read."""
    if not read_vecs:
        return 1.0
    return 1.0 - max(cosine(paper_vec, r) for r in read_vecs)


def combine(
    *,
    relevance: float = 0.0,
    pagerank: float = 0.0,
    novelty: float = 0.0,
    contest: float = 0.0,
    recency: float = 0.0,
    bridge_bonus: float = 0.0,
) -> ScoreBreakdown:
    w = scoring()["weights"]
    total = (
        w["relevance"] * relevance
        + w["pagerank"] * pagerank
        + w["novelty"] * novelty
        + w["contest"] * contest
        + w["recency"] * recency
        + bridge_bonus
    )
    return ScoreBreakdown(
        relevance=relevance,
        pagerank=pagerank,
        novelty=novelty,
        contest=contest,
        recency=recency,
        bridge_bonus=bridge_bonus,
        total=total,
    )


def admission_band(raw_sim: float) -> str:
    """SCORING.md §2 — 'drop' | 'park' | 'queue' from raw cosine to the query."""
    bands = scoring()["bands"]
    if raw_sim < float(bands["drop_below"]):
        return "drop"
    if raw_sim < float(bands["park_below"]):
        return "park"
    return "queue"
