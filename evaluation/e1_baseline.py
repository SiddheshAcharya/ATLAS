"""E1 — does the loop beat one-shot retrieval? (docs/TESTING.md Part 2, "the central claim")

Baseline: harvest ~500 candidates for the query, embed everything, rank by cosine to the
query vector, take the top 25. No expansion, no re-ranking, no claim extraction, no
judging — "the naive system" (TESTING.md's own words). Compared against an ATLAS
standard-mode run already completed over the *same* query.

Usage (from the repo root, with the venv active):
    PYTHONPATH=src python evaluation/e1_baseline.py --run-id <atlas_run_id>

Requires: the run named by --run-id used `evaluation/queries.yaml`'s query verbatim (the
script re-harvests that same query fresh — API results drift over time, so a baseline
run today is not byte-identical to what the ATLAS run saw weeks ago; that drift is
itself worth a sentence in the report, not something to hide).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from atlas.config import settings
from atlas.forage import frontier, scoring
from atlas.harvest import run_harvest
from atlas.ingest.embed import embed_query, embed_texts
from atlas.store import db, vector
from atlas.store.graph import GraphStore

TOP_K = 25
# paper abstracts are looser semantically than concept phrases (extract/concepts.py uses 0.85)
DIVERSITY_FLOOR = 0.55


def _text_of(p: Any) -> str:
    return f"{p.title}\n{p.abstract or ''}".strip()


def run_baseline(query: str, *, per_keyword: int = 25, top_k: int = TOP_K) -> dict[str, Any]:
    papers, hreport = run_harvest(query, per_keyword=per_keyword, use_llm=True)
    by_id = {p.paper_id: p for p in papers}
    qvec = embed_query(query)

    cached = vector.get_abstract_vectors(list(by_id))
    missing = [pid for pid in by_id if pid not in cached and by_id[pid].abstract]
    if missing:
        fresh = embed_texts([_text_of(by_id[pid]) for pid in missing])
        cached.update(dict(zip(missing, fresh, strict=True)))
        vector.upsert_abstracts_bulk(
            [(pid, cached[pid], by_id[pid].title, by_id[pid].year, None) for pid in missing]
        )

    scorable = {pid: v for pid, v in cached.items() if by_id[pid].abstract}
    ranked = scoring.relevance_scores(qvec, scorable)
    top = sorted(ranked, key=lambda pid: ranked[pid], reverse=True)[:top_k]
    return {
        "query": query,
        "n_candidates": hreport.total_unique,
        "per_source": hreport.per_source_raw,
        "top_papers": top,
        "vecs": {pid: cached[pid] for pid in top},
        "by_id": {pid: by_id[pid] for pid in top},
    }


def _diversity_clusters(paper_ids: list[str], vecs: dict[str, list[float]], *, floor: float) -> int:
    """Count of cosine-agglomerative clusters at `floor` — a citation-graph-free stand-in
    for "breadth" that can be computed identically for the baseline (which never builds a
    graph at all) and the ATLAS set."""
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    ids = [pid for pid in paper_ids if pid in vecs]
    if len(ids) < 2:
        return len(ids)
    x = np.array([vecs[pid] for pid in ids])
    labels = AgglomerativeClustering(
        n_clusters=None, distance_threshold=1 - floor, metric="cosine", linkage="average"
    ).fit_predict(x)
    return len(set(labels))


def citation_breadth(sets: dict[str, list[Any]], *, ref_limit: int = 60) -> dict[str, Any]:
    """Breadth measured the same way for every set (2026-09-29).

    The old headline compared ATLAS's *citation* clusters (from Paper.cluster_id, which the
    latest run to touch a paper overwrites — ADR-017) against the baseline's *embedding*
    clusters: two different metrics. Here every paper in every set gets its OpenAlex
    reference list (cached, no LLM), one citation graph is built over all of them, Louvain
    (seed 42, sorted insertion) clusters it once, and each set is scored on that one graph.
    """
    import asyncio

    import networkx as nx

    from atlas.sources.openalex import OpenAlexSource

    papers = {p.paper_id: p for group in sets.values() for p in group if p is not None}

    async def fetch_all() -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        async with OpenAlexSource() as oa:
            for pid in sorted(papers):
                refs = await oa.references(papers[pid], limit=ref_limit)
                out[pid] = sorted({r.paper_id for r in refs})
        return out

    refs = asyncio.run(fetch_all())
    g = nx.Graph()
    g.add_nodes_from(sorted(papers))
    for pid in sorted(refs):
        for r in refs[pid]:
            if r != pid:
                g.add_edge(pid, r)
    communities = nx.community.louvain_communities(g, seed=42)
    community_of = {n: i for i, comm in enumerate(communities) for n in comm}

    out: dict[str, Any] = {"graph_nodes": g.number_of_nodes(), "graph_edges": g.number_of_edges()}
    for name, group in sets.items():
        ids = [p.paper_id for p in group if p is not None]
        linked = [pid for pid in ids if refs.get(pid)]
        reach = {r for pid in ids for r in refs.get(pid, [])}
        out[name] = {
            "papers": len(ids),
            "papers_with_references": len(linked),
            "clusters_covered": len({community_of[pid] for pid in linked}),
            "distinct_references_reached": len(reach),
        }
    out["note"] = (
        "clusters_covered counts only papers with at least one OpenAlex reference (a paper "
        "with none would be its own singleton cluster and inflate breadth); compare "
        "papers_with_references too. Same graph, same clustering for both sets."
    )
    return out


def compare(run_id: str, baseline: dict[str, Any]) -> dict[str, Any]:
    atlas_ids = frontier.read_paper_ids(run_id)
    baseline_ids = baseline["top_papers"]

    overlap = set(atlas_ids) & set(baseline_ids)

    atlas_papers = {pid: db.get_paper(pid) for pid in atlas_ids}
    atlas_cc = [
        p.citation_count for p in atlas_papers.values() if p and p.citation_count is not None
    ]
    baseline_cc = [
        baseline["by_id"][pid].citation_count
        for pid in baseline_ids
        if baseline["by_id"][pid].citation_count is not None
    ]

    atlas_vecs = vector.get_abstract_vectors(atlas_ids)
    result: dict[str, Any] = {
        "run_id": run_id,
        "query": baseline["query"],
        "atlas_papers_read": len(atlas_ids),
        "baseline_top_k": len(baseline_ids),
        "overlap_count": len(overlap),
        "overlap_ratio": round(len(overlap) / max(1, min(len(atlas_ids), len(baseline_ids))), 3),
        "mean_citation_count": {
            "atlas": round(sum(atlas_cc) / len(atlas_cc), 1) if atlas_cc else None,
            "baseline": round(sum(baseline_cc) / len(baseline_cc), 1) if baseline_cc else None,
        },
        f"diversity_clusters_at_floor_{DIVERSITY_FLOOR:.2f}": {
            "atlas": _diversity_clusters(atlas_ids, atlas_vecs, floor=DIVERSITY_FLOOR),
            "baseline": _diversity_clusters(baseline_ids, baseline["vecs"], floor=DIVERSITY_FLOOR),
            "caveat": (
                "This embedding-cosine metric answers a different question from "
                "atlas_only.distinct_louvain_clusters_covered below, and the two can "
                "legitimately disagree (e.g. both near 1). Every candidate here was "
                "retrieved *because* it matched the query topically, so abstract "
                "embeddings for both sets tend to clump into one semantic cluster "
                "regardless of which 25 (or 15) got picked — that's expected, not a bug. "
                "Louvain over the citation graph clusters by *citation structure* "
                "instead, which has nothing to do with abstract-text similarity and is "
                "the metric that actually speaks to breadth the loop can find and "
                "one-shot cosine ranking cannot."
            ),
        },
    }

    if settings.neo4j_configured:
        with GraphStore() as g:
            attrs = g.paper_attrs(run_id)
            contradiction_pairs = g.contradiction_pairs(run_id)
            gaps = g.gaps_for(run_id)
        pageranks = [
            attrs[pid]["pagerank"] for pid in atlas_ids if attrs.get(pid, {}).get("pagerank")
        ]
        # distinct_louvain_clusters_covered (from Paper.cluster_id) was removed 2026-09-29:
        # cluster_id lives on shared Paper nodes and reflects whichever run touched them
        # last (ADR-017). citation_breadth below is the like-for-like replacement.
        result["atlas_only"] = {
            "mean_pagerank": round(sum(pageranks) / len(pageranks), 4) if pageranks else None,
            "contradictions_found": len(contradiction_pairs),
            "gaps_found": len(gaps),
        }
    else:
        result["atlas_only"] = "neo4j not configured — graph-derived metrics unavailable"

    result["citation_breadth"] = citation_breadth(
        {
            "atlas": [atlas_papers.get(pid) for pid in atlas_ids],
            "baseline": [baseline["by_id"][pid] for pid in baseline_ids],
            # same size as ATLAS's read set, so set size can't explain a difference
            f"baseline_top_{len(atlas_ids)}": [
                baseline["by_id"][pid] for pid in baseline_ids[: len(atlas_ids)]
            ],
        }
    )
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--run-id", required=True, help="an already-completed ATLAS run over the same query"
    )
    ap.add_argument("--query", help="override: query text (default: read from the run itself)")
    ap.add_argument("--out", help="path to save the JSON result (default: print only)")
    args = ap.parse_args()

    settings.ensure_dirs()
    query = args.query
    if not query:
        summary = db.run_summary(args.run_id)
        if summary is None:
            raise SystemExit(f"no run {args.run_id!r} — pass --query explicitly")
        query = summary["query"]

    baseline = run_baseline(query)
    result = compare(args.run_id, baseline)
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
