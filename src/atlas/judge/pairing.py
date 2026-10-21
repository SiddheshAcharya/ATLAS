"""Candidate generation for relation judging (ADR-008).

Never judge all pairs — 200 papers x 8 claims = 1.28M pairs. For each *new* claim, take
the k nearest existing claims (cosine ≥ floor) from `atlas_claims`, excluding its own
paper. Only those pairs go to Job C.

(A refinement from ADR-008 — also pairing claims from papers in a direct CITES relation —
needs the graph and lands with the [D] items; the kNN path is the core.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from atlas.config_files import scoring
from atlas.contracts import Claim
from atlas.store import vector

log = structlog.get_logger(__name__)


@dataclass
class Pair:
    a: Claim  # the newly extracted claim
    b: dict[str, Any]  # a candidate claim's payload (claim_id, paper_id, text, quote, scope, year)
    similarity: float


def candidate_pairs(
    new_claims: list[Claim],
    new_vecs: list[list[float]],
    run_id: str,
    *,
    per_claim: int | None = None,
    max_pairs: int | None = None,
    client: Any = None,
) -> list[Pair]:
    cfg = scoring()["judging"]
    k = per_claim or int(cfg["knn_k"])
    floor = float(cfg["similarity_floor"])

    client = client or vector.get_client()
    seen: set[frozenset[str]] = set()
    pairs: list[Pair] = []
    for claim, vec in zip(new_claims, new_vecs, strict=True):
        cands = vector.search_claims(
            vec, run_id=run_id, k=k, floor=floor,
            exclude_paper_id=claim.paper_id, client=client,
        )
        for cand in cands:
            cid = str(cand.get("claim_id") or "")
            if not cid or cid == claim.claim_id:
                continue
            key = frozenset((claim.claim_id, cid))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(Pair(a=claim, b=cand, similarity=float(cand["similarity"])))
            if max_pairs and len(pairs) >= max_pairs:
                log.info("pairing.capped", run_id=run_id, max_pairs=max_pairs)
                return pairs
    log.info("pairing.candidates", run_id=run_id, new_claims=len(new_claims), pairs=len(pairs))
    return pairs
