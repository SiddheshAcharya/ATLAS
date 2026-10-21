"""Detector 1 — unlinked concepts / Swanson ABC (GAP_DETECTORS.md §1).

Concept A co-occurs with B; B co-occurs with C; A and C never co-occur in this corpus.
Classic literature-based discovery (Swanson's fish-oil/Raynaud's finding). Depends
entirely on concept normalization already having happened (extract/concepts.py,
Phase 5a, R4) — without it "IoT device" and "IoT devices" look unlinked for a silly
reason.
"""

from __future__ import annotations

import itertools
import math
from collections import Counter, defaultdict

import networkx as nx
import structlog

from atlas.contracts import GapCandidate
from atlas.gaps.common import DetectorConfig, PaperAttrs, gap_id, has_real_evidence, paper_ref
from atlas.store.graph import GraphStore

log = structlog.get_logger(__name__)

_SEED = 42
_EVIDENCE_CAP = 6


def detect(
    run_id: str, graph: GraphStore, cfg: DetectorConfig, attrs: PaperAttrs | None = None
) -> list[GapCandidate]:
    attrs = attrs if attrs is not None else graph.paper_attrs(run_id)
    # Canonical order everywhere below: Neo4j returns rows in no fixed order, and graph
    # insertion order steers Louvain, node iteration, the A/C orientation of each triple (so
    # its statement text and gap_id), and score ties at the max_candidates cut. Unsorted,
    # the same finished graph gave 8 fused gaps on one pass and 6 on the next.
    mentions = sorted(graph.concept_mentions(run_id))
    if not mentions:
        return []

    label_of: dict[str, str] = {}
    concepts_by_paper: dict[str, set[str]] = defaultdict(set)
    for pid, cid, label in mentions:
        concepts_by_paper[pid].add(cid)
        label_of[cid] = label

    n_papers = len(concepts_by_paper)
    if n_papers < 2:
        return []

    doc_freq: Counter[str] = Counter()
    for concepts in concepts_by_paper.values():
        doc_freq.update(concepts)

    pair_papers: dict[frozenset[str], set[str]] = defaultdict(set)
    for pid, concepts in concepts_by_paper.items():
        for a, b in itertools.combinations(sorted(concepts), 2):
            pair_papers[frozenset((a, b))].add(pid)

    min_support = int(cfg.thresholds.get("min_support", 2))

    def pmi(a: str, b: str, support: int) -> float:
        p_a = doc_freq[a] / n_papers
        p_b = doc_freq[b] / n_papers
        p_ab = support / n_papers
        if p_ab <= 0 or p_a <= 0 or p_b <= 0:
            return float("-inf")
        return math.log(p_ab / (p_a * p_b))

    g = nx.Graph()
    g.add_nodes_from(sorted(doc_freq))
    edge_pmi: dict[frozenset[str], float] = {}
    edge_support: dict[frozenset[str], int] = {}
    for pair, papers in sorted(pair_papers.items(), key=lambda kv: sorted(kv[0])):
        support = len(papers)
        if support < min_support:
            continue
        a, b = sorted(pair)
        score = pmi(a, b, support)
        if score <= cfg.pmi_tau:
            continue
        g.add_edge(a, b, weight=score)
        edge_pmi[pair] = score
        edge_support[pair] = support

    if g.number_of_edges() == 0:
        log.info("gaps.unlinked_concepts", run_id=run_id, reason="no co-occurrence edges above tau")
        return []

    communities = nx.community.louvain_communities(g, seed=_SEED, weight="weight")
    community_of = {cid: i for i, comm in enumerate(communities) for cid in comm}

    seen: set[tuple[str, frozenset[str]]] = set()
    out: list[GapCandidate] = []
    for b in sorted(g.nodes):
        neighbors = sorted(g.neighbors(b))
        for a, c in itertools.combinations(neighbors, 2):
            if a == c:
                continue
            triple_key = frozenset((a, c))
            if triple_key in pair_papers:
                continue  # A and C DO co-occur directly — not a gap
            if community_of.get(a) == community_of.get(c):
                continue  # same community — usually trivially unlinked
            dedup_key = (b, triple_key)  # anchor on B so A-B-C and C-B-A collapse to one
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            pmi_ab = edge_pmi[frozenset((a, b))]
            pmi_bc = edge_pmi[frozenset((b, c))]
            support_ab = edge_support[frozenset((a, b))]
            support_bc = edge_support[frozenset((b, c))]

            ab_papers = pair_papers[frozenset((a, b))]
            bc_papers = pair_papers[frozenset((b, c))]
            bounding = [
                paper_ref(attrs, pid, "evidence")
                for pid in sorted(ab_papers | bc_papers)[:_EVIDENCE_CAP]
            ]
            if not has_real_evidence(bounding, attrs):
                continue

            score = min(pmi_ab, pmi_bc) * math.log(1 + support_ab + support_bc)
            label_a, label_b, label_c = label_of[a], label_of[b], label_of[c]
            statement = (
                f'"{label_a}" and "{label_c}" are both linked to "{label_b}" '
                f"({support_ab} and {support_bc} papers respectively) but no paper in this "
                f'corpus connects "{label_a}" to "{label_c}" directly.'
            )
            out.append(
                GapCandidate(
                    gap_id=gap_id("unlinked_concepts", a, b, c),
                    type="unlinked_concepts",
                    statement=statement,
                    detector_score=score,
                    bounding_papers=bounding,
                    entities=[label_a, label_b, label_c],
                    detail={
                        "concept_a": label_a, "concept_b": label_b, "concept_c": label_c,
                        "pmi_ab": pmi_ab, "pmi_bc": pmi_bc,
                        "support_ab": support_ab, "support_bc": support_bc,
                    },
                )
            )

    out.sort(key=lambda gp: (-gp.detector_score, gp.gap_id))
    kept = out[: cfg.max_candidates]
    log.info(
        "gaps.unlinked_concepts", run_id=run_id, concepts=len(doc_freq), edges=g.number_of_edges(),
        communities=len(communities), candidates=len(out), kept=len(kept),
    )
    return kept
