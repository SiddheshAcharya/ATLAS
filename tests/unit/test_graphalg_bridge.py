"""[D] items — PageRank/Louvain in networkx, Contest inputs, bridge promotion."""

from __future__ import annotations

from atlas.contracts import PaperMeta
from atlas.forage import bridge, graphalg
from atlas.judge.eval import score
from atlas.judge.relations import contradiction_count, judge_pairs
from tests.unit.test_judge import FakeClient, _pair, _v


class FakeGraph:
    def __init__(self, nodes, edges, *, read_clusters=None, neigh_clusters=None):
        self._nodes = nodes
        self._edges = edges
        self._read_clusters = read_clusters or {}
        self._neigh_clusters = neigh_clusters or {}
        self.written: dict = {}

    def run_paper_ids(self, run_id):
        return list(self._nodes)

    def citation_edges(self, run_id):
        return list(self._edges)

    def write_pagerank_clusters(self, run_id, pr, cl):
        self.written = {"pr": pr, "cl": cl}

    def cluster_read_counts(self, run_id):
        return dict(self._read_clusters)

    def clusters_of(self, ids):
        return {i: self._neigh_clusters[i] for i in ids if i in self._neigh_clusters}


def test_graphalg_normalises_pagerank_and_finds_clusters():
    # two triangles joined by one edge -> ~2 communities
    edges = [("a", "b"), ("b", "c"), ("c", "a"), ("d", "e"), ("e", "f"), ("f", "d"), ("c", "d")]
    g = FakeGraph(["a", "b", "c", "d", "e", "f"], edges)
    pr, clusters = graphalg.recompute(g, "r")
    assert abs(max(pr.values()) - 1.0) < 1e-9  # normalised to the run max
    assert set(clusters.values()) and len(set(clusters.values())) >= 2
    assert g.written["pr"] == pr


def test_graphalg_no_edges_returns_empty():
    pr, clusters = graphalg.recompute(FakeGraph(["a", "b"], []), "r")
    assert pr == {} and clusters == {}


def test_bridge_promotes_a_paper_linking_two_active_clusters():
    parked = PaperMeta(paper_id="doi:bridge", title="Connector")
    g = FakeGraph(
        [], [],
        read_clusters={0: 4, 1: 3, 2: 1},  # clusters 0 and 1 are "active" (>=3 read)
        neigh_clusters={"n1": 0, "n2": 0, "n3": 1},  # links: 2 into cl0, 1 into cl1
    )
    promos = bridge.sweep(
        g, "r", [parked], lambda p: ["n1", "n2", "n3"], promoted_so_far=0
    )
    assert len(promos) == 1
    assert sorted(promos[0].clusters) == [0, 1]
    assert promos[0].links == 3


def test_bridge_does_not_promote_when_only_one_cluster_touched():
    parked = PaperMeta(paper_id="doi:x", title="x")
    g = FakeGraph([], [], read_clusters={0: 4, 1: 3}, neigh_clusters={"n1": 0, "n2": 0})
    assert bridge.sweep(g, "r", [parked], lambda p: ["n1", "n2"], promoted_so_far=0) == []


def test_r2_scoring_reads_gold_labels(tmp_path):
    rels = judge_pairs(
        [_pair("a1", "b1"), _pair("a2", "b2"), _pair("a3", "b3")],
        FakeClient([_v("CONTRADICTS"), _v("SUPPORTS"), _v("SUPPORTS")]),
        "r",
    )
    assert contradiction_count(rels, 0.7) == 1

    import json

    p = tmp_path / "labelled.jsonl"
    p.write_text(
        "\n".join(
            json.dumps(d)
            for d in [
                {"type": "CONTRADICTS", "gold": "CONTRADICTS"},
                {"type": "SUPPORTS", "gold": "SUPPORTS"},
                {"type": "SUPPORTS", "gold": "DIFF_SCOPE"},
            ]
        )
    )
    out = score(p)
    assert out["n"] == 3
    assert out["per_label"]["SUPPORTS"]["precision"] == 0.5
    assert out["per_label"]["CONTRADICTS"]["precision"] == 1.0
