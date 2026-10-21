"""PageRank + Louvain over the run's citation graph — in networkx, not Neo4j GDS.

GDS isn't on the AuraDB Free tier and the laptop has no Docker, so the graph algorithms
run in Python (SCORING.md — recompute every K papers, not every iteration). Results are
written back onto the Paper nodes (`pagerank`, `cluster_id`) for the scorer and the UI.
Seeded so a warm re-run reproduces the same clusters (R9).
"""

from __future__ import annotations

import networkx as nx
import structlog

from atlas.store.graph import GraphStore

log = structlog.get_logger(__name__)
_SEED = 42


def recompute(
    graph: GraphStore, run_id: str, *, damping: float = 0.85
) -> tuple[dict[str, float], dict[str, int]]:
    """Returns (pagerank_by_paper normalised to the run max, cluster_id_by_paper)."""
    nodes = graph.run_paper_ids(run_id)
    edges = graph.citation_edges(run_id)
    g = nx.DiGraph()
    g.add_nodes_from(nodes)
    g.add_edges_from(edges)

    if g.number_of_edges() == 0:
        log.info("graphalg.skip", run_id=run_id, reason="no citation edges yet")
        return {}, {}

    pr = nx.pagerank(g, alpha=damping)
    hi = max(pr.values()) or 1.0
    pr = {k: v / hi for k, v in pr.items()}

    communities = nx.community.louvain_communities(g.to_undirected(), seed=_SEED)
    cluster_of = {pid: i for i, comm in enumerate(communities) for pid in comm}

    graph.write_pagerank_clusters(run_id, pr, cluster_of)
    log.info(
        "graphalg.done",
        run_id=run_id,
        papers=len(nodes),
        edges=g.number_of_edges(),
        clusters=len(communities),
    )
    return pr, cluster_of
