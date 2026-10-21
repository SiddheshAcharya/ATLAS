"""Shared helpers for the 6 gap detectors (docs/GAP_DETECTORS.md).

Config loading, PaperRef construction, and the citation-rule guard every detector must
satisfy: a GapCandidate that cannot name real (non-metadata_only) evidence is not
constructed. Fusion enforces this again — failing loudly at the source is easier to debug.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from atlas.config_files import scoring
from atlas.contracts import PaperRef

PaperAttrs = dict[str, dict[str, Any]]


@dataclass(frozen=True)
class DetectorConfig:
    max_candidates: int
    dedup_similarity: float
    dedup_jaccard: float
    rrf_k: int
    corroboration_bonus: float
    pmi_tau: float
    max_gaps: int
    detector_weights: dict[str, float]
    thresholds: dict[str, float]

    @classmethod
    def load(cls) -> DetectorConfig:
        g = scoring()["gaps"]
        return cls(
            max_candidates=int(g.get("max_candidates_per_detector", 50)),
            dedup_similarity=float(g["dedup_similarity"]),
            dedup_jaccard=float(g["dedup_jaccard"]),
            rrf_k=int(g["rrf_k"]),
            corroboration_bonus=float(g["corroboration_bonus"]),
            pmi_tau=float(g.get("pmi_tau", 0.0)),
            max_gaps=int(g["max_gaps"]),
            detector_weights=dict(g["detector_weights"]),
            thresholds=dict(g["thresholds"]),
        )


def gap_id(gap_type: str, *parts: str) -> str:
    """Stable id independent of paper_id shape (DOIs/slashes/etc. are fine as inputs)."""
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"gap:{gap_type}:{h}"


def slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return s or "x"


def paper_ref(attrs: PaperAttrs, paper_id: str, role: str) -> PaperRef:
    a = attrs.get(paper_id, {})
    return PaperRef(
        paper_id=paper_id,
        title=str(a.get("title") or paper_id),
        year=a.get("year"),
        role=role,
    )


def is_metadata_only(attrs: PaperAttrs, paper_id: str) -> bool:
    return attrs.get(paper_id, {}).get("depth") == "metadata_only"


def has_real_evidence(bounding: list[PaperRef], attrs: PaperAttrs) -> bool:
    """Citation rule (GAP_DETECTORS.md preamble + fusion §4): False means drop — either no
    bounding papers, or every one of them is metadata_only (no text ATLAS can show)."""
    if not bounding:
        return False
    return not all(is_metadata_only(attrs, p.paper_id) for p in bounding)


def pagerank_of(attrs: PaperAttrs, paper_id: str) -> float:
    v = attrs.get(paper_id, {}).get("pagerank")
    return float(v) if isinstance(v, (int, float)) else 0.0


def minmax_normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]
