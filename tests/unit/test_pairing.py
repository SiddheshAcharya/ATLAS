"""Candidate generation (ADR-008) — kNN over atlas_claims, no cross-paper judging of self."""

from __future__ import annotations

import math

from atlas.contracts import Claim, ClaimScope
from atlas.judge.pairing import candidate_pairs
from atlas.store import vector

DIM = 768
RID = "run-pairing"


def _unit(seed: int) -> list[float]:
    import random

    r = random.Random(seed)
    v = [r.random() for _ in range(DIM)]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _claim(cid: str, pid: str) -> Claim:
    return Claim(claim_id=cid, paper_id=pid, section="results", text=f"t {cid}",
                 quote=f"q {cid}", scope=ClaimScope(what_was_tested="x"))


def test_knn_pairs_exclude_same_paper_and_dedupe():
    client = vector.get_client()
    vector.ensure_collections(client, dim=DIM)

    # two existing claims, one near vector v0 and one far
    near, far = _unit(1), _unit(999)
    existing = [_claim("e-near", "doi:P2"), _claim("e-far", "doi:P3"),
                _claim("e-same", "doi:P1")]
    vector.upsert_claims(existing, [near, [-x for x in near], far], run_id=RID, client=client)

    new = [_claim("n1", "doi:P1")]
    pairs = candidate_pairs(new, [near], RID, per_claim=10, client=client)

    partners = {p.b["claim_id"] for p in pairs}
    assert "e-near" in partners
    assert "e-same" not in partners  # same paper as the new claim
    assert all(p.a.claim_id == "n1" for p in pairs)


def test_max_pairs_caps_the_batch():
    client = vector.get_client()
    vector.ensure_collections(client, dim=DIM)
    v = _unit(7)
    existing = [_claim(f"x{i}", f"doi:Q{i}") for i in range(8)]
    vector.upsert_claims(existing, [v] * 8, run_id="run-cap", client=client)

    new = [_claim(f"m{i}", "doi:NEW") for i in range(4)]
    pairs = candidate_pairs(new, [v] * 4, "run-cap", per_claim=8, max_pairs=5, client=client)
    assert len(pairs) == 5
