"""Bridge promotion — the connector-paper mechanism (SCORING.md §3).

A *parked* paper is promoted to the frontier when its citation neighbourhood reaches
into >= 2 distinct Louvain clusters that the run is actively building (a cluster with
>= min_cluster_size read papers), with >= min_bridge_links such links total. This is how
ATLAS finds papers that pure cosine ranking structurally misses.

Evaluated after each PageRank/Louvain recompute, not every iteration. Capped per run.
`neighbourhood_fn(paper) -> list[paper_id]` is injected (OpenAlex in the loop, a stub in
tests).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

import structlog

from atlas.config_files import scoring
from atlas.contracts import PaperMeta
from atlas.store.graph import GraphStore

log = structlog.get_logger(__name__)


@dataclass
class Promotion:
    paper_id: str
    clusters: list[int]
    links: int


def sweep(
    graph: GraphStore,
    run_id: str,
    parked: list[PaperMeta],
    neighbourhood_fn: Callable[[PaperMeta], list[str]],
    *,
    promoted_so_far: int,
    max_probe: int = 12,
) -> list[Promotion]:
    cfg = scoring()["bridge"]
    if not cfg.get("enabled", True) or not parked:
        return []

    min_clusters = int(cfg["min_clusters"])
    min_cluster_size = int(cfg["min_cluster_size"])
    min_links = int(cfg["min_bridge_links"])
    budget = int(cfg["max_promotions_per_run"]) - promoted_so_far
    if budget <= 0:
        return []

    active = {
        cl for cl, n in graph.cluster_read_counts(run_id).items() if n >= min_cluster_size
    }
    if len(active) < min_clusters:
        return []

    out: list[Promotion] = []
    for paper in parked[:max_probe]:
        if len(out) >= budget:
            break
        neigh_clusters = graph.clusters_of(neighbourhood_fn(paper))
        by_cluster = Counter(cl for cl in neigh_clusters.values() if cl in active)
        touched = [cl for cl, c in by_cluster.items() if c >= 1]
        total = sum(by_cluster[cl] for cl in touched)
        if len(touched) >= min_clusters and total >= min_links:
            promo = Promotion(paper.paper_id, sorted(touched)[:2], total)
            out.append(promo)
            log.info(
                "bridge.promoted",
                run_id=run_id,
                paper_id=paper.paper_id,
                clusters=promo.clusters,
                links=total,
            )
    return out
