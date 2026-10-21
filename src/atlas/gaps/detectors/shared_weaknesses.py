"""Detector 6 — shared weaknesses (GAP_DETECTORS.md §6).

A thin reader: the actual clustering (HDBSCAN over limitation-sentence embeddings, kept
only if it spans >= min_papers papers from >= min_author_groups distinct first-author
groups, labeled by an LLM) already happened in extract/concepts.py during Phase 5a
concept extraction and was written to Neo4j via write_weakness_clusters. This detector
just reads the survivors back and scores them.
"""

from __future__ import annotations

import structlog

from atlas.contracts import GapCandidate
from atlas.gaps.common import (
    DetectorConfig,
    PaperAttrs,
    gap_id,
    has_real_evidence,
    pagerank_of,
    paper_ref,
)
from atlas.store.graph import GraphStore

log = structlog.get_logger(__name__)


def _author_group(paper_id: str) -> str:
    from atlas.store.db import get_paper

    paper = get_paper(paper_id)
    if paper is not None and paper.authors:
        name = paper.authors[0].name or ""
        surname = name.strip().split(" ")[-1].lower() if name.strip() else ""
        return surname or "unknown"
    return "unknown"


def detect(
    run_id: str, graph: GraphStore, cfg: DetectorConfig, attrs: PaperAttrs | None = None
) -> list[GapCandidate]:
    attrs = attrs if attrs is not None else graph.paper_attrs(run_id)
    clusters = graph.weakness_clusters(run_id)

    out: list[GapCandidate] = []
    for c in clusters:
        members = c["members"]
        assert isinstance(members, list)
        paper_ids = sorted({str(m["paper_id"]) for m in members})
        if not paper_ids:
            continue
        n_papers = len(paper_ids)
        author_groups = {_author_group(pid) for pid in paper_ids}
        author_diversity = len(author_groups) / n_papers
        mean_pr = sum(pagerank_of(attrs, pid) for pid in paper_ids) / n_papers

        bounding = [paper_ref(attrs, pid, "evidence") for pid in paper_ids]
        if not has_real_evidence(bounding, attrs):
            continue

        score = n_papers * author_diversity * (mean_pr or 0.01)
        label = str(c.get("label") or "shared weakness")
        statement = (
            f"A recurring limitation across {n_papers} papers from "
            f"{len(author_groups)} independent author groups: {label}."
        )
        out.append(
            GapCandidate(
                gap_id=gap_id("shared_weakness", str(c["cluster_id"]), *paper_ids),
                type="shared_weakness",
                statement=statement,
                detector_score=score,
                bounding_papers=bounding,
                entities=[label],
                detail={
                    "cluster_id": c["cluster_id"],
                    "n_papers": n_papers,
                    "author_groups": len(author_groups),
                    "sample_sentences": [str(m["text"]) for m in members[:5]],
                },
            )
        )

    out.sort(key=lambda g: (-g.detector_score, g.gap_id))  # gap_id: deterministic ties
    kept = out[: cfg.max_candidates]
    log.info(
        "gaps.shared_weaknesses", run_id=run_id, clusters=len(clusters),
        candidates=len(out), kept=len(kept),
    )
    return kept
