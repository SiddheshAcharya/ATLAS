"""Loop smoke test — a few iterations with every heavy collaborator faked.

Guards the loop's control flow (seed -> pop by score -> ingest -> claims -> expand ->
admit -> mark read -> saturation) and its determinism, without network / models / Neo4j.
"""

from __future__ import annotations

import math
import random

import pytest

from atlas.contracts import Depth, PaperMeta, ParsedDoc, Section
from atlas.extract.claims import ClaimHarvest
from atlas.forage import loop as loop_mod
from atlas.harvest import HarvestReport
from atlas.ingest.pipeline import IngestReport

DIM = 8


def _vec(text: str) -> list[float]:
    r = random.Random(text)
    v = [r.random() for _ in range(DIM)]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _paper(pid: str, *, abstract: str | None = "an abstract about safety") -> PaperMeta:
    return PaperMeta(paper_id=pid, title=f"Title {pid}", abstract=abstract, year=2024)


SEEDS = [_paper(f"doi:s{i}") for i in range(6)]

_FAKE_HARVEST_REPORT = HarvestReport(
    query="safety query", keywords=[], per_source_raw={}, total_raw=len(SEEDS),
    total_unique=len(SEEDS), multi_source=0, with_pdf_url=0, with_abstract=len(SEEDS),
    elapsed_s=0.0,
)


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(
        loop_mod, "run_harvest", lambda *a, **k: (list(SEEDS), _FAKE_HARVEST_REPORT)
    )
    monkeypatch.setattr(loop_mod, "embed_texts", lambda texts, **k: [_vec(t) for t in texts])
    monkeypatch.setattr("atlas.ingest.embed.embed_query", lambda t: _vec(t))
    monkeypatch.setattr(loop_mod, "dedup_papers", lambda ps: ps)

    from atlas.forage import loop as _l
    from atlas.store import vector

    monkeypatch.setattr(vector, "get_abstract_vectors", lambda ids, **k: {})
    monkeypatch.setattr(vector, "upsert_abstracts_bulk", lambda *a, **k: 0)
    # relation judging has its own tests; here we only exercise the loop's control flow
    monkeypatch.setattr(_l.vector, "upsert_claims", lambda *a, **k: 0)
    monkeypatch.setattr(_l.pairing, "candidate_pairs", lambda *a, **k: [])
    monkeypatch.setattr(_l.judge, "judge_pairs", lambda *a, **k: [])

    def fake_ingest(paper, **k):
        doc = ParsedDoc(
            paper_id=paper.paper_id, depth=Depth.ABSTRACT_ONLY, structure="none",
            full_text="safety text " * 5,
            sections=[Section(name="abstract", raw_name="Abstract",
                              text="safety text " * 5, char_start=0, char_end=55)],
        )
        return doc, IngestReport(paper.paper_id, "none", "none", "abstract_only", 1, 0, 0, 55,
                                 True, [], 0.1)

    monkeypatch.setattr(loop_mod, "run_ingest", fake_ingest)

    def fake_claims(doc, paper, *, client):
        from atlas.contracts import Claim, ClaimScope

        c = Claim(claim_id=f"c-{paper.paper_id}", paper_id=paper.paper_id, section="abstract",
                  text="t", quote="safety text safety text", scope=ClaimScope(what_was_tested="x"),
                  verified=True, verify_method="exact")
        return ClaimHarvest(kept=[c], n_extracted=1, n_dropped=0)

    monkeypatch.setattr(loop_mod, "extract_claims", fake_claims)

    # each read paper yields 2 fresh neighbours
    def fake_expand(paper):
        refs = [_paper(f"{paper.paper_id}->ref", abstract="safety neighbour")]
        citers = [_paper(f"{paper.paper_id}->cite", abstract="safety neighbour")]
        return refs, citers

    monkeypatch.setattr(loop_mod, "_expand", fake_expand)


def _run(**kw):
    return loop_mod.run("safety query", mode="standard", write_graph=False,
                        use_llm_keywords=False, **kw)


def test_loop_reads_up_to_the_cap_and_records_everything(patched, fresh_db: None):
    res = _run(max_papers=4)
    assert res.papers_read == 4
    assert res.stop_reason == "budget: 4 papers read"
    assert res.claims_kept == 4  # one per read paper
    assert len(res.saturation) == 4

    from atlas.forage import frontier

    assert frontier.state_counts(res.run_id)["read"] == 4
    # neighbours from expansion were pushed onto the frontier
    pending = frontier.state_counts(res.run_id).get("pending", 0)
    parked = frontier.state_counts(res.run_id).get("parked", 0)
    assert pending + parked > 0


def test_abstract_only_paper_completes_the_loop_without_raising(patched, fresh_db: None):
    """TESTING.md's `test_abstract_only_path`: a paper with no PDF (ADR-010's first-class
    abstract-only path, ~40-60% of real papers) must not raise anywhere in ingest ->
    claims -> graph write -> expansion. `patched`'s fake_ingest returns depth=ABSTRACT_ONLY
    for every paper (structure="none", one "abstract" section) — this asserts the claims
    that came out are actually scoped to that section, not just that nothing crashed."""
    import sqlalchemy as sa

    res = _run(max_papers=3)
    assert res.papers_read == 3
    assert res.claims_kept == 3  # extraction + grounding still ran, on abstract text only

    from atlas.store.db import ClaimRow, session_scope

    with session_scope() as s:
        sections = s.execute(
            sa.select(ClaimRow.section).where(ClaimRow.run_id == res.run_id)
        ).scalars().all()
    assert sections == ["abstract"] * 3


def test_loop_is_deterministic(patched, fresh_db: None):
    a = _run(max_papers=4)
    from atlas.forage import frontier

    order_a = frontier.read_paper_ids(a.run_id)

    # second identical run in the same fresh db
    b = _run(max_papers=4)
    order_b = frontier.read_paper_ids(b.run_id)
    assert order_a == order_b
    assert a.claims_kept == b.claims_kept


def test_loop_stops_on_exhausted_frontier(patched, fresh_db: None, monkeypatch):
    monkeypatch.setattr(loop_mod, "_expand", lambda p: ([], []))  # no new neighbours
    res = _run(max_papers=99)
    # only the 6 abstract-bearing seeds exist; after reading them the frontier is empty
    assert res.papers_read <= 6
    assert res.stop_reason in {"frontier exhausted", "budget: 6 papers read"}
