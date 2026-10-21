"""Phase 5b — the 5 built gap detectors + fusion. Synthetic fixtures, no live network,
matching the FakeGraph pattern from test_graphalg_bridge.py. Detector 2 (predicted_links)
is [S] and stays unbuilt per ROADMAP — nothing here tests it."""

from __future__ import annotations

import pytest

from atlas.contracts import GapCandidate, PaperRef
from atlas.gaps import fusion
from atlas.gaps.common import DetectorConfig, has_real_evidence, minmax_normalize, paper_ref
from atlas.gaps.detectors import (
    empty_combinations,
    shared_weaknesses,
    unanswered_calls,
    unlinked_concepts,
    unresolved_conflicts,
)


def _cfg(**thresholds: float) -> DetectorConfig:
    return DetectorConfig(
        max_candidates=50, dedup_similarity=0.85, dedup_jaccard=0.6, rrf_k=60,
        corroboration_bonus=0.15, pmi_tau=0.0, max_gaps=15,
        detector_weights={
            "unlinked_concepts": 1.0, "empty_combinations": 0.9, "unanswered_calls": 1.1,
            "unresolved_conflicts": 1.2, "shared_weaknesses": 1.0,
        },
        thresholds={
            "min_support": 2, "min_method_papers": 3, "min_dataset_papers": 3,
            "answered_threshold": 0.62, "answered_threshold_nocite": 0.75,
            "call_min_age_years": 2, "weakness_min_cluster_size": 3,
            "weakness_min_papers": 4, "weakness_min_author_groups": 3,
            **thresholds,
        },
    )


def _attrs(**papers: dict[str, object]) -> dict[str, dict[str, object]]:
    out = {}
    for pid, kv in papers.items():
        out[pid] = {"title": pid, "year": 2020, "citation_count": 0, "depth": "full_text",
                    "pagerank": 0.5, "cluster_id": 0, **kv}
    return out


# ── common.py ────────────────────────────────────────────────────────────────


def test_minmax_normalize_handles_flat_and_empty():
    assert minmax_normalize([]) == []
    assert minmax_normalize([3.0, 3.0]) == [1.0, 1.0]
    assert minmax_normalize([0.0, 5.0, 10.0]) == [0.0, 0.5, 1.0]


def test_has_real_evidence_drops_metadata_only_and_empty():
    attrs = _attrs(a={"depth": "metadata_only"}, b={"depth": "full_text"})
    a_ref = paper_ref(attrs, "a", "evidence")
    b_ref = paper_ref(attrs, "b", "evidence")
    assert has_real_evidence([], attrs) is False
    assert has_real_evidence([a_ref], attrs) is False
    assert has_real_evidence([a_ref, b_ref], attrs) is True


# ── detector 5: unresolved conflicts ────────────────────────────────────────


class _FakeGraphConflicts:
    def __init__(self, pairs, resolver=None):
        self._pairs = pairs
        self._resolver = resolver

    def contradiction_pairs(self, run_id):
        return list(self._pairs)

    def has_resolver(self, pa, pb, after_year):
        return self._resolver


def test_unresolved_conflicts_flags_pair_with_no_resolver():
    attrs = _attrs(p1={"year": 2018}, p2={"year": 2019})
    pairs = [{
        "pa": "p1", "ta": "Paper One", "ya": 2018, "claim_a": "X works",
        "pb": "p2", "tb": "Paper Two", "yb": 2019, "claim_b": "X does not work",
        "confidence": 0.9, "rationale": "direct conflict",
    }]
    g = _FakeGraphConflicts(pairs, resolver=None)
    out = unresolved_conflicts.detect("r", g, _cfg(), attrs)
    assert len(out) == 1
    assert out[0].type == "unresolved_conflict"
    assert {p.paper_id for p in out[0].bounding_papers} == {"p1", "p2"}


def test_unresolved_conflicts_drops_when_resolved():
    attrs = _attrs(p1={}, p2={})
    pairs = [{
        "pa": "p1", "ta": "A", "ya": 2018, "claim_a": "x",
        "pb": "p2", "tb": "B", "yb": 2019, "claim_b": "y", "confidence": 0.9,
    }]
    g = _FakeGraphConflicts(pairs, resolver={"paper_id": "p3", "title": "Resolver", "year": 2022})
    assert unresolved_conflicts.detect("r", g, _cfg(), attrs) == []


# ── detector 6: shared weaknesses ───────────────────────────────────────────


class _FakeGraphWeaknesses:
    def __init__(self, clusters):
        self._clusters = clusters

    def weakness_clusters(self, run_id):
        return list(self._clusters)


def test_shared_weaknesses_reads_survivors_and_scores_them(monkeypatch):
    authors = {"p1": "smith", "p2": "jones", "p3": "lee"}
    monkeypatch.setattr(shared_weaknesses, "_author_group", lambda pid: authors[pid])
    attrs = _attrs(p1={}, p2={}, p3={})
    clusters = [{
        "cluster_id": 0, "label": "small samples",
        "members": [
            {"paper_id": "p1", "text": "our sample was small", "year": 2019},
            {"paper_id": "p2", "text": "small participant pool", "year": 2020},
            {"paper_id": "p3", "text": "limited sample size", "year": 2021},
        ],
    }]
    out = shared_weaknesses.detect("r", _FakeGraphWeaknesses(clusters), _cfg(), attrs)
    assert len(out) == 1
    assert out[0].type == "shared_weakness"
    assert out[0].entities == ["small samples"]
    assert len(out[0].bounding_papers) == 3


# ── detector 3: empty combinations ──────────────────────────────────────────


class _FakeGraphMD:
    def __init__(self, methods, datasets, tried):
        self._methods, self._datasets, self._tried = methods, datasets, tried

    def method_dataset_usage(self, run_id):
        return self._methods, self._datasets, self._tried


def test_empty_combinations_flags_untried_pair_above_paper_floor():
    methods = {"m:svm": ("SVM", ["p1", "p2", "p3"])}
    datasets = {"d:x": ("Dataset X", ["p4", "p5", "p6"]), "d:y": ("Dataset Y", ["p1", "p7", "p8"])}
    tried = {("m:svm", "d:y")}  # SVM x Dataset Y tried; SVM x Dataset X is not
    attrs = _attrs(**{p: {} for p in ("p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8")})
    out = empty_combinations.detect("r", _FakeGraphMD(methods, datasets, tried), _cfg(), attrs)
    assert len(out) == 1
    assert out[0].detail["dataset"] == "Dataset X"


def test_empty_combinations_respects_paper_count_floor():
    methods = {"m:svm": ("SVM", ["p1", "p2"])}  # below min_method_papers=3
    datasets = {"d:x": ("Dataset X", ["p3", "p4", "p5"])}
    attrs = _attrs(**{p: {} for p in ("p1", "p2", "p3", "p4", "p5")})
    out = empty_combinations.detect("r", _FakeGraphMD(methods, datasets, set()), _cfg(), attrs)
    assert out == []


# ── detector 4: unanswered calls ────────────────────────────────────────────


class _FakeGraphCalls:
    def __init__(self, calls, citation_edges):
        self._calls, self._edges = calls, citation_edges

    def calls_for(self, run_id):
        return list(self._calls)

    def citation_edges(self, run_id):
        return list(self._edges)


def _patch_calls_deps(monkeypatch, *, search_result):
    """detect() does `from atlas.ingest.embed import embed_texts` and `from atlas.store
    import vector` INSIDE the function body, so patching must target the source modules
    (picked up fresh on each call), not the detector module's own namespace."""
    import atlas.ingest.embed as embed_mod
    import atlas.store.vector as vector_mod

    monkeypatch.setattr(embed_mod, "embed_texts", lambda texts, **k: [[1.0, 0.0] for _ in texts])
    monkeypatch.setattr(vector_mod, "get_client", lambda: object())
    monkeypatch.setattr(vector_mod, "search_claims", lambda *a, **k: search_result)


def test_unanswered_call_survives_when_no_later_claim_is_close(monkeypatch):
    _patch_calls_deps(monkeypatch, search_result=[])
    calls = [{
        "pid": "old_paper", "year": 2018, "cc": 50,
        "cid": "concept:x", "label": "x", "text": "future work should explore X",
    }]
    g = _FakeGraphCalls(calls, citation_edges=[])
    attrs = _attrs(old_paper={"year": 2018, "citation_count": 50})
    out = unanswered_calls.detect("r", g, _cfg(), attrs)
    assert len(out) == 1
    assert out[0].type == "unanswered_call"


def test_unanswered_call_is_dropped_when_a_citing_later_paper_matches(monkeypatch):
    _patch_calls_deps(
        monkeypatch, search_result=[{"paper_id": "new_paper", "year": 2022, "similarity": 0.7}]
    )
    calls = [{
        "pid": "old_paper", "year": 2018, "cc": 50,
        "cid": "concept:x", "label": "x", "text": "future work should explore X",
    }]
    g = _FakeGraphCalls(calls, citation_edges=[("new_paper", "old_paper")])
    attrs = _attrs(old_paper={"year": 2018}, new_paper={"year": 2022})
    out = unanswered_calls.detect("r", g, _cfg(), attrs)
    assert out == []


def test_unanswered_call_respects_min_age(monkeypatch):
    from datetime import UTC, datetime

    _patch_calls_deps(monkeypatch, search_result=[])
    this_year = datetime.now(UTC).year
    calls = [{
        "pid": "recent_paper", "year": this_year, "cc": 5,
        "cid": "concept:x", "label": "x", "text": "future work",
    }]
    g = _FakeGraphCalls(calls, citation_edges=[])
    attrs = _attrs(recent_paper={"year": this_year})
    assert unanswered_calls.detect("r", g, _cfg(), attrs) == []


# ── detector 1: unlinked concepts (Swanson ABC) ─────────────────────────────


class _FakeGraphConcepts:
    def __init__(self, mentions):
        self._mentions = mentions

    def concept_mentions(self, run_id):
        return list(self._mentions)


def _mentions_for_two_triangles_bridged_by_b():
    """Two dense triangles (A,P1,P2) and (C,Q1,Q2), connected only through B — the same
    'two triangles joined by one edge' shape test_graphalg_bridge.py already relies on
    louvain splitting into ~2 communities."""
    labels = {"A": "concept a", "B": "concept b", "C": "concept c",
              "P1": "p1", "P2": "p2", "Q1": "q1", "Q2": "q2"}
    pairs = [
        ("A", "P1"), ("A", "P1"), ("A", "P2"), ("A", "P2"), ("P1", "P2"), ("P1", "P2"),
        ("C", "Q1"), ("C", "Q1"), ("C", "Q2"), ("C", "Q2"), ("Q1", "Q2"), ("Q1", "Q2"),
        ("A", "B"), ("A", "B"), ("B", "C"), ("B", "C"),
    ]
    mentions = []
    for i, (x, y) in enumerate(pairs):
        pid = f"paper{i}"
        mentions.append((pid, x, labels[x]))
        mentions.append((pid, y, labels[y]))
    return mentions


def test_unlinked_concepts_finds_swanson_triple_with_zero_direct_cooccurrence():
    mentions = _mentions_for_two_triangles_bridged_by_b()
    out = unlinked_concepts.detect("r", _FakeGraphConcepts(mentions), _cfg(), _attrs())
    triples = {(c.detail["concept_a"], c.detail["concept_b"], c.detail["concept_c"]) for c in out}
    assert ("concept a", "concept b", "concept c") in triples or (
        "concept c", "concept b", "concept a"
    ) in triples


def test_unlinked_concepts_is_independent_of_row_order():
    """Neo4j returns mentions in no fixed order. Before sorting, row order steered Louvain,
    the A/C orientation of each triple (so its statement and gap_id) and score ties, and the
    same finished run gave 8 fused gaps on one pass and 6 on the next (invariant 4)."""
    import random

    mentions = _mentions_for_two_triangles_bridged_by_b()

    def run(rows):
        out = unlinked_concepts.detect("r", _FakeGraphConcepts(rows), _cfg(), _attrs())
        return [(c.gap_id, c.statement, round(c.detector_score, 9)) for c in out]

    expected = run(mentions)
    assert expected
    for seed in range(5):
        shuffled = list(mentions)
        random.Random(seed).shuffle(shuffled)
        assert run(shuffled) == expected


def test_unlinked_concepts_empty_on_too_few_papers():
    assert unlinked_concepts.detect("r", _FakeGraphConcepts([]), _cfg(), _attrs()) == []


# ── fusion ───────────────────────────────────────────────────────────────────


def _gap(gap_id, gtype, score, papers, statement="stmt"):
    return GapCandidate(
        gap_id=gap_id, type=gtype, statement=statement, detector_score=score,
        bounding_papers=[PaperRef(paper_id=p, title=p, role="evidence") for p in papers],
    )


def _fake_embed_by_statement(texts, **_k):
    """Unit-ish vectors so identical statements cosine to 1.0 and different ones to 0.0 —
    isolates the dedup-by-embedding path from the dedup-by-bounding-paper-Jaccard path."""
    return [[1.0, 0.0] if t == "same statement" else [0.0, 1.0] for t in texts]


def test_fusion_corroboration_bonus_ranks_multi_detector_gap_first(monkeypatch):
    import atlas.ingest.embed as embed_mod

    monkeypatch.setattr(embed_mod, "embed_texts", _fake_embed_by_statement)

    shared = _gap("g1", "unresolved_conflict", 0.9, ["p1", "p2"], statement="same statement")
    shared_again = _gap(
        "g1b", "shared_weakness", 0.5, ["p1", "p2"], statement="same statement"
    )
    solo = _gap("g2", "empty_combination", 0.95, ["p3", "p4"], statement="unrelated statement")

    attrs = _attrs(p1={}, p2={}, p3={}, p4={})
    candidates_by_detector = {
        "unresolved_conflicts": [shared],
        "shared_weaknesses": [shared_again],
        "empty_combinations": [solo],
    }
    ranked = fusion.fuse(candidates_by_detector, _cfg(), attrs)
    assert ranked[0].rank == 1
    assert len(ranked[0].found_by) == 2
    assert set(p.paper_id for p in ranked[0].bounding_papers) == {"p1", "p2"}


def test_fusion_drops_gaps_with_no_real_evidence(monkeypatch):
    import atlas.ingest.embed as embed_mod

    monkeypatch.setattr(embed_mod, "embed_texts", lambda texts, **k: [[1.0, 0.0] for _ in texts])
    meta_only = _gap("g1", "unresolved_conflict", 0.9, ["p1"])
    attrs = _attrs(p1={"depth": "metadata_only"})
    ranked = fusion.fuse({"unresolved_conflicts": [meta_only]}, _cfg(), attrs)
    assert ranked == []


def test_gap_candidate_requires_at_least_one_bounding_paper():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GapCandidate(
            gap_id="x", type="unresolved_conflict", statement="s", detector_score=1.0,
            bounding_papers=[],
        )
