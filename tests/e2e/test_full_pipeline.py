"""tests/e2e — one real, full run over a fixture-cached corpus, no live network.

Unlike tests/unit (every collaborator faked) and tests/integration (real Neo4j, still
mocks HTTP), this exercises the actual harvest -> ingest -> claims -> judge -> loop
control flow for real, but every external call it makes is a cache hit against
tests/fixtures/e2e/cache.db (see conftest.py for exactly how that fixture was made).
`_block_network` (autouse, conftest.py) turns any real network attempt into a hard
failure, so a pass here is a genuine "the full pipeline works end to end, offline"
result, not just "the mocks were self-consistent".
"""

from __future__ import annotations

from atlas.forage import loop


def test_full_pipeline_runs_entirely_from_cache():
    # Exact numbers from the real seeding run (2026-09-28, run 55078995) — a genuine replay
    # of the same query/config against a warm cache should reproduce them exactly
    # (invariant #4/#5, CLAUDE.md: every LLM/API call is cached and replayable). A mismatch
    # here means either the fixture went stale or reproducibility broke, both worth
    # failing loudly on rather than asserting loosely.
    # Re-seeded because the PyMuPDF page-number fix changed both fixture PDFs' text (so
    # their claims prompts) and the grounding gate's wording guard now drops edited quotes.
    # Was 41 kept / 1 dropped (2026-09-19, run 6bbbef81).
    result = loop.run(
        "small language models for edge devices",
        mode="standard",
        max_papers=3,
        write_graph=False,  # NEO4J_URI is unset (conftest.py) — matches how the fixture was seeded
    )

    assert result.papers_read == 3
    assert result.claims_kept == 43
    assert result.claims_dropped == 4
    assert result.relations_judged == 12
    assert result.bridge_promotions == 0
    assert result.stop_reason == "budget: 3 papers read"
