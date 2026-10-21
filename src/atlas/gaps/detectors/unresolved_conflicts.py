"""Detector 5 — unresolved conflicts (GAP_DETECTORS.md §5).

Two papers disagree (a CONTRADICTS edge between their claims) and no later paper in the
corpus cites both, or resolves the disagreement. The detector most dependent on judge
quality — if Job C over-labels CONTRADICTS, this list fills with false conflicts.
"""

from __future__ import annotations

from datetime import UTC, datetime

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


def detect(
    run_id: str, graph: GraphStore, cfg: DetectorConfig, attrs: PaperAttrs | None = None
) -> list[GapCandidate]:
    attrs = attrs if attrs is not None else graph.paper_attrs(run_id)
    pairs = graph.contradiction_pairs(run_id)
    now_year = datetime.now(UTC).year

    out: list[GapCandidate] = []
    for row in pairs:
        pa, pb = str(row["pa"]), str(row["pb"])
        ya, yb = row.get("ya"), row.get("yb")
        y = max((v for v in (ya, yb) if isinstance(v, int)), default=None)
        confidence_raw = row.get("confidence")
        confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0.0

        resolver = graph.has_resolver(pa, pb, y if y is not None else 0)
        if resolver is not None:
            continue  # resolved — not a gap

        bounding = [paper_ref(attrs, pa, "a_side"), paper_ref(attrs, pb, "b_side")]
        if not has_real_evidence(bounding, attrs):
            continue

        years_open = max(0, now_year - y) if y is not None else 0
        mean_pr = (pagerank_of(attrs, pa) + pagerank_of(attrs, pb)) / 2.0
        score = confidence * (mean_pr or 0.01) * min(1.0, years_open / 10.0 + 0.1)

        ta = str(row.get("ta") or pa)
        tb = str(row.get("tb") or pb)
        statement = (
            f'"{ta}" ({ya if ya is not None else "n.d."}) reports {row.get("claim_a", "")!r}; '
            f'"{tb}" ({yb if yb is not None else "n.d."}) reports {row.get("claim_b", "")!r}. '
            "No subsequent paper in this corpus cites both or resolves the disagreement."
        )
        out.append(
            GapCandidate(
                gap_id=gap_id("unresolved_conflict", pa, pb),
                type="unresolved_conflict",
                statement=statement,
                detector_score=score,
                bounding_papers=bounding,
                entities=[],
                detail={
                    "claim_a": row.get("claim_a"),
                    "claim_b": row.get("claim_b"),
                    "confidence": confidence,
                    "years_open": years_open,
                    "rationale": row.get("rationale"),
                },
            )
        )

    out.sort(key=lambda g: (-g.detector_score, g.gap_id))  # gap_id: deterministic ties
    kept = out[: cfg.max_candidates]
    log.info(
        "gaps.unresolved_conflicts", run_id=run_id, pairs=len(pairs),
        candidates=len(out), kept=len(kept),
    )
    return kept
