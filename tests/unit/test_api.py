"""Phase 6a — the FastAPI layer. No live Neo4j/Qdrant server, no real crawl: conftest.py
forces NEO4J_URI="" and an in-memory Qdrant for every unit test, so routes that need the
graph are exercised on their 409 path here; the live end-to-end check (a real run through
a real browser) happens separately, not in this file.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from atlas.api import registry
from atlas.api.main import app
from atlas.api.routes import runs as runs_route
from atlas.contracts import Author, Claim, ClaimScope, PaperMeta
from atlas.store import db

client = TestClient(app)


def _seed_paper(paper_id: str, *, title: str = "A Paper", author: str = "Smith") -> None:
    db.upsert_papers(
        [PaperMeta(paper_id=paper_id, title=title, year=2022, authors=[Author(name=author)])]
    )


# ── health ───────────────────────────────────────────────────────────────────


def test_health_reports_services():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    names = {s["name"] for s in body["services"]}
    assert {"postgres/sqlite", "neo4j", "qdrant", "grobid", "llm"} <= names


# ── run lifecycle ────────────────────────────────────────────────────────────


def test_list_runs_empty(fresh_db: None):
    r = client.get("/api/v1/runs")
    assert r.status_code == 200
    assert r.json() == []


def test_get_run_404_when_missing(fresh_db: None):
    r = client.get("/api/v1/runs/does-not-exist")
    assert r.status_code == 404


def test_stop_untracked_run_404(fresh_db: None):
    r = client.post("/api/v1/runs/does-not-exist/stop")
    assert r.status_code == 404


def test_create_run_spawns_a_tracked_background_task(fresh_db: None, monkeypatch):
    started = {}

    async def fake_pipeline(run_id, query, mode, max_papers, handle):
        started["run_id"] = run_id
        started["query"] = query
        handle.done = True

    monkeypatch.setattr(runs_route.tasks, "run_full_pipeline", fake_pipeline)

    r = client.post("/api/v1/runs", json={"query": "IoT safety", "mode": "standard"})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    assert run_id
    # registry.register() runs synchronously before asyncio.create_task(), so this is
    # guaranteed true by the time the response comes back — no race.
    assert registry.get(run_id) is not None

    # The background task itself runs concurrently on the TestClient's event loop and
    # is not guaranteed to have executed yet — poll briefly rather than assert immediately.
    for _ in range(50):
        if started:
            break
        time.sleep(0.02)
    assert started.get("run_id") == run_id
    assert started.get("query") == "IoT safety"


def test_stop_signals_a_tracked_run():
    handle = registry.register("run-to-stop")
    assert not handle.stop_event.is_set()
    r = client.post("/api/v1/runs/run-to-stop/stop")
    assert r.status_code == 200
    assert handle.stop_event.is_set()


# ── neo4j-backed routes without neo4j (the conftest default) ───────────────


def test_graph_409_without_neo4j(fresh_db: None):
    assert client.get("/api/v1/runs/r1/graph").status_code == 409


def test_gaps_409_without_neo4j(fresh_db: None):
    assert client.get("/api/v1/runs/r1/gaps").status_code == 409


def test_report_409_without_neo4j(fresh_db: None):
    assert client.get("/api/v1/runs/r1/report").status_code == 409


# ── frontier ─────────────────────────────────────────────────────────────────


def test_frontier_returns_seeded_rows(fresh_db: None):
    from atlas.contracts import ScoreBreakdown
    from atlas.forage import frontier as frontier_mod

    db.create_run("r1", "query", "standard", "cfg")
    _seed_paper("doi:p1")
    frontier_mod.seed("r1", [("doi:p1", ScoreBreakdown(relevance=0.8, total=0.8))])

    r = client.get("/api/v1/runs/r1/frontier")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["paper_id"] == "doi:p1"
    assert rows[0]["state"] == "pending"


# ── timeline ─────────────────────────────────────────────────────────────────


def test_timeline_returns_saturation_events(fresh_db: None):
    db.create_run("r1", "query", "standard", "cfg")
    db.emit_event(
        "r1", "saturation",
        {"step": 0, "new_info": 2.0, "ema": 2.0, "paper_id": "doi:p1", "title": "P1",
         "claims_kept": 3, "claims_dropped": 0, "total_usd": 0.002},
    )

    r = client.get("/api/v1/runs/r1/timeline")
    assert r.status_code == 200
    points = r.json()
    assert len(points) == 1
    assert points[0]["read_order"] == 0
    assert points[0]["cumulative_claims"] == 3
    assert points[0]["cumulative_usd"] == 0.002


def test_timeline_empty_before_any_paper_read(fresh_db: None):
    db.create_run("r1", "query", "standard", "cfg")
    assert client.get("/api/v1/runs/r1/timeline").json() == []


# ── paper detail ─────────────────────────────────────────────────────────────


def test_paper_detail_works_for_doi_ids_containing_slashes(fresh_db: None):
    from urllib.parse import quote

    db.create_run("r1", "query", "standard", "cfg")
    _seed_paper("doi:10.1109/access.2023.3252903")
    r = client.get(f"/api/v1/runs/r1/papers/{quote('doi:10.1109/access.2023.3252903', safe='')}")
    assert r.status_code == 200
    assert r.json()["paper"]["paper_id"] == "doi:10.1109/access.2023.3252903"



def test_paper_detail_404_for_unknown_paper(fresh_db: None):
    r = client.get("/api/v1/runs/r1/papers/doi:nope")
    assert r.status_code == 404


def test_paper_detail_returns_claims_and_relations(fresh_db: None):
    _seed_paper("doi:p1", title="Paper One")
    claim = Claim(
        claim_id="c1", paper_id="doi:p1", text="text", quote="quote", section="results",
        scope=ClaimScope(what_was_tested="x"), verified=True, verify_method="exact",
        quote_char_start=0, quote_char_end=5,
    )
    db.insert_claims([claim], "r1")
    r = client.get("/api/v1/runs/r1/papers/doi:p1")
    assert r.status_code == 200
    body = r.json()
    assert body["paper"]["paper_id"] == "doi:p1"
    assert len(body["claims"]) == 1
    assert body["claims"][0]["quote"] == "quote"
    assert body["relations"] == []


# ── chat ─────────────────────────────────────────────────────────────────────


def test_chat_refuses_when_nothing_is_retrieved(fresh_db: None):
    r = client.post("/api/v1/runs/r-empty/chat", json={"message": "what did the papers find?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "ATLAS did not read anything that addresses this."
    assert body["citations"] == []


def test_chat_refuses_when_corpus_has_content_but_it_is_irrelevant(fresh_db: None):
    """The harder out-of-scope case TESTING.md actually describes: the run has real
    claims, but none of them are close enough to this question — the similarity floor,
    not an empty corpus, is what triggers the refusal. Uses the real embedding model (no
    mocking) so the cosine gap is genuine, not asserted by construction."""
    from atlas.contracts import Claim, ClaimScope
    from atlas.ingest.embed import embed_texts
    from atlas.store import vector

    run_id = "r-irrelevant"
    claim = Claim(
        claim_id="c1", paper_id="doi:p1", text="Chlorophyll absorbs light for photosynthesis.",
        quote="Chlorophyll absorbs light for photosynthesis.", section="results",
        scope=ClaimScope(what_was_tested="photosynthesis rate"), verified=True,
        verify_method="exact",
    )
    vec = embed_texts([claim.text])
    vector.upsert_claims([claim], vec, run_id=run_id, year_by_paper={"doi:p1": 2020})

    r = client.post(
        f"/api/v1/runs/{run_id}/chat", json={"message": "what is the capital of France?"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "ATLAS did not read anything that addresses this."
    assert body["citations"] == []


# ── events (store layer directly — the HTTP SSE stream is a live-only check) ─


def test_emit_event_assigns_increasing_per_run_seq(fresh_db: None):
    s1 = db.emit_event("r1", "run_started", {"query": "q"})
    s2 = db.emit_event("r1", "harvest_done", {"n_candidates": 5})
    s_other = db.emit_event("r2", "run_started", {"query": "other"})
    assert (s1, s2) == (0, 1)
    assert s_other == 0  # separate run, separate sequence

    replay = db.events_since("r1", -1)
    assert [e["seq"] for e in replay] == [0, 1]
    assert [e["type"] for e in replay] == ["run_started", "harvest_done"]

    tail = db.events_since("r1", 0)
    assert [e["seq"] for e in tail] == [1]


def test_built_dashboard_is_served_with_spa_fallback(tmp_path):
    """`atlas serve`: one process serves the API and the built dashboard. Real files are
    served, client-side routes get index.html, and unknown /api paths stay 404s."""
    from fastapi import FastAPI

    from atlas.api.main import mount_web

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    web = FastAPI()

    @web.get("/api/v1/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    assert mount_web(web, tmp_path)
    c = TestClient(web)
    assert c.get("/api/v1/ping").json() == {"ok": True}
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert "id=root" in c.get("/runs/abc/report").text
    assert c.get("/api/v1/nope").status_code == 404
    assert "id=root" in c.get("/../../etc/passwd").text  # no escape from dist
    assert not mount_web(FastAPI(), tmp_path / "missing")


def test_paper_source_rebuilds_text_at_quote_offsets(monkeypatch):
    """GET .../papers/{id}/source: chunks placed at their full_text offsets, so a claim's
    quote_char_start/end index straight into it. The route must win over the greedy
    `{paper_id:path}` detail route even for a DOI with slashes."""
    from atlas.store import vector

    chunks = [
        {"chunk_index": 0, "section": "abstract", "char_start": 0, "char_end": 22,
         "text": "Wearables detect falls"},
        {"chunk_index": 1, "section": "results", "char_start": 24, "char_end": 48,
         "text": "Latency was 1.8 seconds."},
    ]
    monkeypatch.setattr(vector, "get_chunks_by_paper", lambda pid, run_id=None: chunks)
    r = client.get("/api/v1/runs/r1/papers/doi:10.1/a.b/c/source")
    assert r.status_code == 200
    body = r.json()
    assert body["paper_id"] == "doi:10.1/a.b/c"
    assert body["text"][24:48] == "Latency was 1.8 seconds."
    assert body["text"][22:24] == "\n\n"
    assert [s["name"] for s in body["sections"]] == ["abstract", "results"]

    monkeypatch.setattr(vector, "get_chunks_by_paper", lambda pid, run_id=None: [])
    assert client.get("/api/v1/runs/r1/papers/doi:10.1/x/source").status_code == 404
