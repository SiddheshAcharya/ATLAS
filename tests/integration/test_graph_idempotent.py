"""Integration — GraphStore write idempotency (docs/TESTING.md: `test_graph_write_idempotent`,
"write the same paper twice -> node/edge counts unchanged").

Needs a real Neo4j. This project has no Docker (docs/DECISIONS.md ADR-011: no GDS/testcontainers
on this laptop) — the lightweight path uses a real AuraDB Free instance instead, so this test
talks to whatever `NEO4J_URI` in the environment points at, and is skipped when that's unset
(e.g. a CI runner or a machine that hasn't configured Neo4j yet) rather than failing.

`make test-int` runs this. It writes and deletes its own throwaway run_id/paper_id/claim_id(s)
so it never touches real project data, and cleans up via `delete_run` even on failure.
"""

from __future__ import annotations

import uuid

import pytest

from atlas.config import settings
from atlas.contracts import Claim, ClaimScope
from atlas.store.graph import GraphStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not settings.neo4j_configured, reason="NEO4J_URI not set"),
]


def _claim(claim_id: str, paper_id: str) -> Claim:
    return Claim(
        claim_id=claim_id, paper_id=paper_id, text="a claim", quote="a claim",
        section="results", scope=ClaimScope(what_was_tested="x"), verified=True,
        verify_method="exact",
    )


def test_writing_the_same_paper_claims_and_citation_twice_does_not_duplicate_anything():
    run_id = f"test-idempotent-{uuid.uuid4()}"
    pid_a = f"test:idempotent-a-{uuid.uuid4()}"
    pid_b = f"test:idempotent-b-{uuid.uuid4()}"
    claim_a1 = _claim(f"c-{uuid.uuid4()}", pid_a)
    claim_a2 = _claim(f"c-{uuid.uuid4()}", pid_a)

    with GraphStore() as g:
        try:
            g.write_run(run_id, "idempotency test", "standard", "cfg")

            def write_everything() -> None:
                g.write_paper(paper_id=pid_a, title="Paper A", run_id=run_id, year=2024)
                g.write_paper(paper_id=pid_b, title="Paper B", run_id=run_id, year=2023)
                g.write_claims([claim_a1, claim_a2], run_id)
                g.write_cites(pid_a, [(pid_b, "Paper B")], run_id)
                g.write_read(run_id, pid_a, 0)

            write_everything()
            first = g.counts(run_id)
            write_everything()  # again, byte-for-byte identical inputs
            second = g.counts(run_id)

            assert first == second
            assert second["papers"] == 2
            assert second["claims"] == 2
            assert second["cites"] == 1
        finally:
            g.delete_run(run_id)


def test_gaps_are_per_run_and_replaced_not_accumulated():
    """Two runs that find the same gap each keep their own copy and rank; re-running a
    run's detectors replaces its gap set. (Before 2026-09-28 a Gap node was keyed by gap_id
    alone: the second run took the node over, and stale passes left duplicate ranks.)"""
    from atlas.contracts import PaperRef, RankedGap

    run_a, run_b = f"test-gaps-a-{uuid.uuid4()}", f"test-gaps-b-{uuid.uuid4()}"
    pid = f"test:gap-paper-{uuid.uuid4()}"
    shared_id = f"gap:test:{uuid.uuid4()}"

    def gap(gap_id: str, rank: int) -> RankedGap:
        return RankedGap(
            gap_id=gap_id, type="unlinked_concepts", statement=f"gap {rank}",
            detector_score=1.0, gap_score=1.0 / rank, rank=rank, found_by=["unlinked_concepts"],
            bounding_papers=[PaperRef(paper_id=pid, title="P", year=2024, role="evidence")],
        )

    with GraphStore() as g:
        try:
            for rid in (run_a, run_b):
                g.write_run(rid, "gap test", "standard", "cfg")
                g.write_paper(paper_id=pid, title="P", run_id=rid, year=2024)
            g.write_gaps(run_a, [gap(shared_id, 1), gap(f"gap:test:{uuid.uuid4()}", 2)])
            g.write_gaps(run_b, [gap(shared_id, 1)])
            assert [r["rank"] for r in g.gaps_for(run_a)] == [1, 2]  # not taken over by run_b
            assert [r["rank"] for r in g.gaps_for(run_b)] == [1]

            g.write_gaps(run_a, [gap(shared_id, 1)])  # a later detector pass for run_a
            assert [r["gap_id"] for r in g.gaps_for(run_a)] == [shared_id]
            assert [r["rank"] for r in g.gaps_for(run_b)] == [1]

            g.write_gaps(run_a, [])  # a pass that finds nothing clears the old set too
            assert g.gaps_for(run_a) == []
        finally:
            for rid in (run_a, run_b):
                g.delete_run(rid)


def test_contradictions_are_counted_only_for_the_run_that_judged_them():
    """Papers are shared across runs. contradiction_pairs(run) once returned CONTRADICTS
    edges judged in *other* runs over the same papers (a0e32253 reported 7 where it judged
    1), feeding detector 5 and the report's contradiction section."""
    from atlas.contracts import Relation

    run_a, run_b = f"test-contra-a-{uuid.uuid4()}", f"test-contra-b-{uuid.uuid4()}"
    p1, p2 = f"test:contra-1-{uuid.uuid4()}", f"test:contra-2-{uuid.uuid4()}"
    with GraphStore() as g:
        try:
            for rid in (run_a, run_b):
                g.write_run(rid, "contradiction test", "standard", "cfg")
                for i, pid in enumerate((p1, p2)):
                    g.write_paper(paper_id=pid, title=pid, run_id=rid, year=2024)
                    g.write_read(rid, pid, i)
            a1, a2 = _claim(f"c-{uuid.uuid4()}", p1), _claim(f"c-{uuid.uuid4()}", p2)
            b1, b2 = _claim(f"c-{uuid.uuid4()}", p1), _claim(f"c-{uuid.uuid4()}", p2)
            g.write_claims([a1, a2], run_a)
            g.write_claims([b1, b2], run_b)
            g.write_relations(
                [Relation(source_claim_id=b1.claim_id, target_claim_id=b2.claim_id,
                          type="CONTRADICTS", confidence=0.9, rationale="x",
                          judged_by="test", run_id=run_b)],
                run_b,
            )
            assert g.contradiction_pairs(run_a) == []
            assert len(g.contradiction_pairs(run_b)) == 1
        finally:
            for rid in (run_a, run_b):
                g.delete_run(rid)
