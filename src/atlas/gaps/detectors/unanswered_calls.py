"""Detector 4 — unanswered calls (GAP_DETECTORS.md §4).

A paper's future-work sentence that nobody followed up on: embed the call, search
atlas_claims for later claims, and call it "answered" if a later claim is similar enough
(>= answered_threshold and its paper cites the calling paper, or >= answered_threshold_nocite
regardless of citation). Everything else, past the min-age floor, is a gap.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from atlas.contracts import GapCandidate
from atlas.gaps.common import DetectorConfig, PaperAttrs, gap_id, has_real_evidence, paper_ref
from atlas.store.graph import GraphStore

log = structlog.get_logger(__name__)

_EVIDENCE_K = 3


def _as_int(v: object) -> int:
    return int(v) if isinstance(v, (int, float)) else 0


def detect(
    run_id: str, graph: GraphStore, cfg: DetectorConfig, attrs: PaperAttrs | None = None
) -> list[GapCandidate]:
    from atlas.ingest.embed import embed_texts
    from atlas.store import vector

    attrs = attrs if attrs is not None else graph.paper_attrs(run_id)
    calls = graph.calls_for(run_id)
    if not calls:
        return []

    citers: dict[str, set[str]] = {}
    for a, b in graph.citation_edges(run_id):  # a CITES b
        citers.setdefault(b, set()).add(a)

    now_year = datetime.now(UTC).year
    min_age = int(cfg.thresholds.get("call_min_age_years", 2))
    answered_t = float(cfg.thresholds.get("answered_threshold", 0.62))
    answered_nocite_t = float(cfg.thresholds.get("answered_threshold_nocite", 0.75))

    max_cc = max((_as_int(c.get("cc")) for c in calls), default=0) or 1

    vecs = embed_texts([str(c["text"]) for c in calls])
    client = vector.get_client()

    out: list[GapCandidate] = []
    for call, vec in zip(calls, vecs, strict=True):
        calling_paper = str(call["pid"])
        call_year = call.get("year")
        if not isinstance(call_year, int):
            continue
        age_years = now_year - call_year
        if age_years < min_age:
            continue

        candidates = vector.search_claims(
            vec, run_id=run_id, k=10, floor=0.0, exclude_paper_id=calling_paper, client=client
        )
        later = [
            c for c in candidates
            if isinstance(c.get("year"), int) and c["year"] > call_year
        ]

        answered = False
        for c in later:
            sim = float(c.get("similarity") or 0.0)
            cites_back = str(c["paper_id"]) in citers.get(calling_paper, set())
            if (sim >= answered_t and cites_back) or sim >= answered_nocite_t:
                answered = True
                break
        if answered:
            continue

        best_sim = max((float(c.get("similarity") or 0.0) for c in later), default=0.0)
        evidence_papers = sorted(
            {str(c["paper_id"]) for c in later}, key=lambda pid: pid
        )[:_EVIDENCE_K]

        bounding = [paper_ref(attrs, calling_paper, "a_side")] + [
            paper_ref(attrs, pid, "evidence") for pid in evidence_papers
        ]
        if not has_real_evidence(bounding, attrs):
            continue

        cc_norm = _as_int(call.get("cc")) / max_cc
        age_factor = min(1.0, age_years / 10.0)
        score = cc_norm * age_factor * (1.0 - best_sim)

        title = str(attrs.get(calling_paper, {}).get("title") or calling_paper)
        statement = (
            f'"{title}" ({call_year}) calls for {str(call["text"]).strip()!r}. '
            "No later paper in this corpus appears to answer it."
        )
        out.append(
            GapCandidate(
                gap_id=gap_id("unanswered_call", calling_paper, str(call["cid"])),
                type="unanswered_call",
                statement=statement,
                detector_score=score,
                bounding_papers=bounding,
                entities=[str(call["label"])],
                detail={
                    "call_text": call["text"], "call_year": call_year,
                    "age_years": age_years, "best_later_similarity": best_sim,
                },
            )
        )

    out.sort(key=lambda g: (-g.detector_score, g.gap_id))  # gap_id: deterministic ties
    kept = out[: cfg.max_candidates]
    log.info(
        "gaps.unanswered_calls", run_id=run_id, calls=len(calls),
        candidates=len(out), kept=len(kept),
    )
    return kept
