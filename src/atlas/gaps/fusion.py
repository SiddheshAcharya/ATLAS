"""Fusion (GAP_DETECTORS.md §Fusion) — the 6 detectors' candidate lists become one ranked
gap list.

1. Min-max normalize each detector's scores *within that detector* (raw scores aren't
   comparable across detectors).
2. Deduplicate: merge candidates whose statements are >=dedup_similarity cosine-similar
   or whose bounding-paper sets overlap by >=dedup_jaccard Jaccard. A merged gap keeps
   the union of bounding papers and every detector that found it.
3. Weighted Reciprocal Rank Fusion + corroboration bonus for gaps multiple detectors
   independently found.
4. Citation rule (hard filter, enforced again here even though each detector already
   enforces it at the source): drop anything with zero bounding papers or where every
   bounding paper is metadata_only.
5. Cap at max_gaps for the report; the caller gets the full ranked list too.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import structlog

from atlas.contracts import GapCandidate, GapType, PaperRef, RankedGap
from atlas.gaps.common import DetectorConfig, PaperAttrs, has_real_evidence
from atlas.store.graph import GraphStore

log = structlog.get_logger(__name__)


@dataclass
class _Group:
    statement: str
    bounding: dict[str, PaperRef]  # paper_id -> ref, union across merged candidates
    entities: list[str]
    detail: dict[str, object]
    types: list[GapType]
    best_rank_by_detector: dict[str, int] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)
    representative_gap_id: str = ""


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def fuse(
    candidates_by_detector: dict[str, list[GapCandidate]],
    cfg: DetectorConfig,
    attrs: PaperAttrs,
) -> list[RankedGap]:
    from atlas.ingest.embed import embed_texts

    ranked_items: list[tuple[str, int, GapCandidate]] = []  # (detector, rank, candidate)
    for detector, cands in candidates_by_detector.items():
        # gap_id breaks score ties, so the greedy grouping below sees one fixed order
        ordered = sorted(cands, key=lambda c: (-c.detector_score, c.gap_id))
        for rank, c in enumerate(ordered, start=1):
            ranked_items.append((detector, rank, c))

    if not ranked_items:
        return []

    statements = [c.statement for _, _, c in ranked_items]
    vecs = embed_texts(statements)

    groups: list[_Group] = []
    for (detector, rank, cand), vec in zip(ranked_items, vecs, strict=True):
        cand_paper_ids = {p.paper_id for p in cand.bounding_papers}
        match: _Group | None = None
        for g in groups:
            sim = float(np.dot(g.embedding, vec)) if g.embedding else 0.0
            jac = _jaccard(set(g.bounding), cand_paper_ids)
            if sim >= cfg.dedup_similarity or jac >= cfg.dedup_jaccard:
                match = g
                break

        if match is None:
            match = _Group(
                statement=cand.statement,
                bounding={p.paper_id: p for p in cand.bounding_papers},
                entities=list(cand.entities),
                detail=dict(cand.detail),
                types=[cand.type],
                embedding=vec,
                representative_gap_id=cand.gap_id,
            )
            groups.append(match)
        else:
            for p in cand.bounding_papers:
                match.bounding.setdefault(p.paper_id, p)
            for e in cand.entities:
                if e not in match.entities:
                    match.entities.append(e)
            if cand.type not in match.types:
                match.types.append(cand.type)

        prev = match.best_rank_by_detector.get(detector)
        if prev is None or rank < prev:
            match.best_rank_by_detector[detector] = rank

    scored: list[tuple[float, _Group]] = []
    for g in groups:
        rrf = sum(
            cfg.detector_weights.get(detector, 1.0) / (cfg.rrf_k + rank)
            for detector, rank in g.best_rank_by_detector.items()
        )
        n_detectors = len(g.best_rank_by_detector)
        bonus = 1.0 + cfg.corroboration_bonus * (n_detectors - 1)
        scored.append((rrf * bonus, g))

    scored.sort(key=lambda t: t[0], reverse=True)

    out: list[RankedGap] = []
    dropped = 0
    for rank, (score, g) in enumerate(scored, start=1):
        bounding = list(g.bounding.values())
        if not has_real_evidence(bounding, attrs):
            dropped += 1
            continue
        out.append(
            RankedGap(
                gap_id=g.representative_gap_id,
                type=g.types[0],
                statement=g.statement,
                detector_score=score,
                bounding_papers=bounding,
                entities=g.entities,
                detail=g.detail,
                gap_score=score,
                rank=rank,
                found_by=g.types,
            )
        )

    # re-rank after the citation-rule drop so ranks stay contiguous
    for i, rg in enumerate(out, start=1):
        rg.rank = i

    log.info(
        "gaps.fusion", detectors=len(candidates_by_detector), candidates=len(ranked_items),
        groups=len(groups), dropped_citation_rule=dropped, kept=len(out),
    )
    return out


def run_detectors(
    run_id: str, graph: GraphStore, *, cfg: DetectorConfig | None = None
) -> list[RankedGap]:
    """The Phase 5b pass: run detectors 1, 3, 4, 5, 6 (detector 2 is [S] — skipped per
    ROADMAP), fuse, write (:Gap) nodes + BOUNDED_BY edges, return the full ranked list
    (the caller/report trims to max_gaps for display)."""
    from atlas.gaps.detectors import (
        empty_combinations,
        shared_weaknesses,
        unanswered_calls,
        unlinked_concepts,
        unresolved_conflicts,
    )

    cfg = cfg or DetectorConfig.load()
    attrs = graph.paper_attrs(run_id)

    candidates_by_detector = {
        "unlinked_concepts": unlinked_concepts.detect(run_id, graph, cfg, attrs),
        "empty_combinations": empty_combinations.detect(run_id, graph, cfg, attrs),
        "unanswered_calls": unanswered_calls.detect(run_id, graph, cfg, attrs),
        "unresolved_conflicts": unresolved_conflicts.detect(run_id, graph, cfg, attrs),
        "shared_weaknesses": shared_weaknesses.detect(run_id, graph, cfg, attrs),
    }
    for name, cands in candidates_by_detector.items():
        log.info("gaps.detector_done", run_id=run_id, detector=name, candidates=len(cands))

    ranked = fuse(candidates_by_detector, cfg, attrs)
    graph.write_gaps(run_id, ranked)
    log.info("gaps.run_detectors_done", run_id=run_id, total_gaps=len(ranked))
    return ranked
