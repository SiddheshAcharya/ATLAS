"""E8 — reproducibility: are two runs of the same query + config identical? (docs/TESTING.md E8)

Compares what a run *produced*, not ids: claim_ids are fresh per run, so claims are compared as
(paper_id, verbatim quote) and relations as (paper A, quote A, paper B, quote B, type). A warm
cache should make a replay identical (invariant 4).

Usage:
    PYTHONPATH=src python evaluation/e8_compare.py --run-a <id> --run-b <id> [--out result.json]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from atlas.store.db import session_scope


def _run_facts(run_id: str) -> dict[str, Any]:
    with session_scope() as s:
        order = [
            r[0] for r in s.execute(sa.text(
                "SELECT paper_id FROM frontier WHERE run_id=:r AND read_order IS NOT NULL "
                "ORDER BY read_order"), {"r": run_id})
        ]
        claims = Counter(
            (r[0], r[1]) for r in s.execute(sa.text(
                "SELECT paper_id, quote FROM claims WHERE run_id=:r AND verified"), {"r": run_id})
        )
        relations = Counter(
            (r[0], r[1], r[2], r[3], r[4]) for r in s.execute(sa.text(
                "SELECT a.paper_id, a.quote, b.paper_id, b.quote, rel.type FROM relations rel "
                "JOIN claims a ON a.claim_id = rel.source_claim_id "
                "JOIN claims b ON b.claim_id = rel.target_claim_id WHERE rel.run_id=:r"),
                {"r": run_id})
        )
        stop = s.execute(sa.text("SELECT stop_reason FROM runs WHERE run_id=:r"),
                         {"r": run_id}).scalar()
    return {"order": order, "claims": claims, "relations": relations, "stop_reason": stop}


def compare(run_a: str, run_b: str) -> dict[str, Any]:
    a, b = _run_facts(run_a), _run_facts(run_b)
    return {
        "run_a": run_a,
        "run_b": run_b,
        "same_read_order": a["order"] == b["order"],
        "papers_read": [len(a["order"]), len(b["order"])],
        "same_claims": a["claims"] == b["claims"],
        "claims": [sum(a["claims"].values()), sum(b["claims"].values())],
        "claims_only_in_a": sum((a["claims"] - b["claims"]).values()),
        "claims_only_in_b": sum((b["claims"] - a["claims"]).values()),
        "same_relations": a["relations"] == b["relations"],
        "relations": [sum(a["relations"].values()), sum(b["relations"].values())],
        "relations_only_in_a": sum((a["relations"] - b["relations"]).values()),
        "relations_only_in_b": sum((b["relations"] - a["relations"]).values()),
        "stop_reason": [a["stop_reason"], b["stop_reason"]],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-a", required=True)
    ap.add_argument("--run-b", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    result = compare(args.run_a, args.run_b)
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
