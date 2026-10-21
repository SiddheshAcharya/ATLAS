"""Frontier scoring components (SCORING.md §1-2)."""

from __future__ import annotations

import math

from atlas.forage import scoring


def test_cosine_of_unit_vectors():
    assert scoring.cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert scoring.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_relevance_is_min_max_normalised_across_the_set():
    q = [1.0, 0.0]
    vecs = {"a": [1.0, 0.0], "b": [0.0, 1.0], "c": [0.7071, 0.7071]}
    r = scoring.relevance_scores(q, vecs)
    assert r["a"] == 1.0 and r["b"] == 0.0
    assert 0.0 < r["c"] < 1.0


def test_novelty_falls_as_read_set_covers_the_paper():
    v = [1.0, 0.0]
    assert scoring.novelty_score(v, []) == 1.0
    assert scoring.novelty_score(v, [[0.0, 1.0]]) == 1.0  # orthogonal read paper
    assert scoring.novelty_score(v, [[1.0, 0.0]]) == 0.0  # identical read paper


def test_recency_decays_by_half_life():
    hl = scoring.scoring()["recency"]["half_life_years"]
    now = 2026
    assert scoring.recency_score(now, [], now_year=now) == 1.0
    one_hl = scoring.recency_score(int(now - hl), [], now_year=now)
    assert math.isclose(one_hl, 0.5, rel_tol=1e-6)


def test_missing_year_uses_frontier_median():
    now = 2026
    s = scoring.recency_score(None, [2020, 2020, 2020], now_year=now)
    assert math.isclose(s, scoring.recency_score(2020, [], now_year=now))


def test_admission_bands_match_config_thresholds():
    b = scoring.scoring()["bands"]
    assert scoring.admission_band(b["drop_below"] - 0.01) == "drop"
    assert scoring.admission_band(b["park_below"] - 0.01) == "park"
    assert scoring.admission_band(b["park_below"] + 0.01) == "queue"


def test_combine_uses_config_weights_and_sums_components():
    w = scoring.scoring()["weights"]
    b = scoring.combine(relevance=1.0, recency=1.0, novelty=1.0)
    assert math.isclose(b.total, w["relevance"] + w["recency"] + w["novelty"])
    assert b.relevance == 1.0 and b.pagerank == 0.0
