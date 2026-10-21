"""Detector 3 — empty combinations (GAP_DETECTORS.md §3).

An untried method x dataset pairing. Keeps methods/datasets with enough papers behind
them (min_method_papers/min_dataset_papers) to avoid a matrix that is trivially mostly
zeros, then flags empty cells.

The optional strengthening (require the target dataset to be embedding-similar to a
dataset the method HAS been tried on) is not implemented — [D] item, cut for scope; noted
so it isn't mistaken for an oversight. Every empty cell that survives the paper-count
floor is reported as-is (plausibility fixed at 1.0).

Note for non-benchmark fields (IoT/women-safety): "dataset" here is often "deployment
setting" or "sensor configuration" per the extraction prompt — say so in the report.
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

_TOP_K_BOUNDING = 5


def _top_papers(paper_ids: list[str], attrs: PaperAttrs, k: int) -> list[str]:
    return sorted(paper_ids, key=lambda pid: (-pagerank_of(attrs, pid), pid))[:k]


def detect(
    run_id: str, graph: GraphStore, cfg: DetectorConfig, attrs: PaperAttrs | None = None
) -> list[GapCandidate]:
    attrs = attrs if attrs is not None else graph.paper_attrs(run_id)
    methods, datasets, tried = graph.method_dataset_usage(run_id)

    min_m = int(cfg.thresholds.get("min_method_papers", 3))
    min_d = int(cfg.thresholds.get("min_dataset_papers", 3))
    methods = {mid: v for mid, v in methods.items() if len(v[1]) >= min_m}
    datasets = {did: v for did, v in datasets.items() if len(v[1]) >= min_d}

    max_freq = max(
        [len(v[1]) for v in methods.values()] + [len(v[1]) for v in datasets.values()] + [1]
    )

    out: list[GapCandidate] = []
    for mid, (m_label, m_papers) in methods.items():
        for did, (d_label, d_papers) in datasets.items():
            if (mid, did) in tried:
                continue
            m_top = _top_papers(m_papers, attrs, _TOP_K_BOUNDING)
            d_top = _top_papers(d_papers, attrs, _TOP_K_BOUNDING)
            bounding = [paper_ref(attrs, p, "evidence") for p in dict.fromkeys(m_top + d_top)]
            if not has_real_evidence(bounding, attrs):
                continue

            score = min(len(m_papers), len(d_papers)) / max_freq
            statement = (
                f'"{m_label}" has been evaluated on {len(d_papers)} dataset(s)/setting(s) '
                f'and "{d_label}" has been used by {len(m_papers)} paper(s) via other methods, '
                f'but no paper in this corpus evaluates "{m_label}" on "{d_label}".'
            )
            out.append(
                GapCandidate(
                    gap_id=gap_id("empty_combination", mid, did),
                    type="empty_combination",
                    statement=statement,
                    detector_score=score,
                    bounding_papers=bounding,
                    entities=[m_label, d_label],
                    detail={
                        "method": m_label, "dataset": d_label,
                        "method_papers": len(m_papers), "dataset_papers": len(d_papers),
                    },
                )
            )

    out.sort(key=lambda g: (-g.detector_score, g.gap_id))  # gap_id: deterministic ties
    kept = out[: cfg.max_candidates]
    log.info(
        "gaps.empty_combinations", run_id=run_id, methods=len(methods), datasets=len(datasets),
        candidates=len(out), kept=len(kept),
    )
    return kept
