# DECISIONS (ADRs)

Format: Context → Decision → Consequences. Append new ADRs; never delete one. If a decision is
reversed, write a new ADR that supersedes it and mark the old one.

---

## ADR-001 — ATLAS is a foraging loop, not a RAG pipeline
**Status:** accepted

**Context.** The obvious build is: search papers, embed, retrieve top-k, ask an LLM to summarize.
That is a weekend project and a hundred people have submitted it.

**Decision.** The value is the *loop*: read a paper → follow its citation neighbourhood → re-score
everything → decide what to read next. Retrieval is a component, not the architecture.

**Consequences.** Iteration count and stopping criteria become first-class concerns. Every
component must support incremental updates. Evaluation must show the loop beat one-shot retrieval
(see `TESTING.md` §Evaluation) — that comparison is the project's central claim and must be
measured, not asserted.

---

## ADR-002 — Plain Python orchestration; LangChain only as a utility library
**Status:** accepted

**Context.** The diagram says "Converting Json in Document format using LangChain". LangChain is
the default reflex for LLM projects. Its agent abstractions hide control flow.

**Decision.** No LangChain framework, no AgentExecutor, no LangGraph in the core loop. Use exactly
one LangChain package: `langchain-text-splitters`. LLM access goes through LiteLLM behind our own
thin client. Orchestration is an explicit `while` loop in `forage/loop.py`.

**Rationale.** The loop *is* the contribution. When an examiner asks "why did it read that paper
sixth?", the answer must be a readable function, not a framework's internal scheduler. Debugging a
framework's state machine costs more weeks than writing 200 lines of loop.

**Consequences.** We hand-write retries, budget tracking, and step logging. That is ~1 day of work
and it produces exactly the artefacts the report needs. LangGraph may be revisited if the loop ever
needs true branching/parallel exploration — a stretch item, not now.

---

## ADR-003 — Postgres holds the frontier queue
**Status:** accepted

**Decision.** The frontier is a Postgres table with score columns and a state enum, not a Redis
sorted set or an in-memory heap.

**Rationale.** Requirements are: ordered pop, partial re-score of many rows, crash recovery, and
full post-hoc inspection of the read order. Only a database gives all four. The queue is at most a
few thousand rows — performance is a non-issue.

**Consequences.** One extra service in compose (needed anyway for cache and cost ledger). The
"why this order?" question becomes a single SQL query, which is a report figure.

---

## ADR-004 — Three specialised stores, not one general one
**Status:** accepted

**Decision.** Qdrant for vectors, Neo4j for the graph, Postgres for run state.

**Rationale.** Every merge attempt (pgvector-only, or Neo4j vector index for everything) trades a
day of setup convenience for a month of fighting the store that is doing the job it is worst at.
The gap detectors need real graph algorithms (PageRank, Louvain, Adamic-Adar); Neo4j GDS provides
them and NetworkX cannot stream to a live UI.

**Consequences.** Three connection managers, three docker services, and a genuine consistency
concern: **Postgres is the source of truth for `paper_id` existence.** Neo4j and Qdrant are
projections. Writes go Postgres → Neo4j → Qdrant, and a repair command (`atlas repair --run-id`)
rebuilds the projections from Postgres.

---

## ADR-005 — GROBID for structure, PyMuPDF as fallback
**Status:** accepted

**Decision.** PDFs go through GROBID to TEI XML; sections are preserved. If GROBID fails or times
out (60 s), fall back to PyMuPDF flat text and mark the doc `structure: none`.

**Rationale.** Two detectors (unanswered calls, shared weaknesses) read specifically from
"future work" and "limitations" sections. Claim extraction quality roughly doubles when the prompt
knows whether it is reading Methods or Results. Flat text cannot supply this.

**Consequences.** A ~1.5 GB Docker image and 5–20 s per PDF. Cache TEI output on disk keyed by
PDF hash — never re-parse.

**Addendum (2026-09-28) — first live GROBID, and where it runs.** GROBID had never run before
this date. The compose file's image tag (`lfoppiano/grobid:0.8.1-crf`) did not exist on Docker
Hub; it is now `grobid/grobid:0.9.1-crf`. On the 5.9 GB-RAM machine the Docker VM gets ~2.9 GB,
and GROBID was OOM-killed by the VM kernel every time, at 2.1–2.3 GB resident, even with a 512 MB
heap, lazy model loading and concurrency 2 (`config/grobid.yaml`): the CRF models live in native
memory outside the heap, and the segmentation model alone expands to several hundred MB. Public
GROBID demo Spaces were all paused ("flagged as abusive"), and free Hugging Face accounts no longer
get CPU quota. So GROBID runs on a Hugging Face Docker Space under a PRO account
(`deploy/hf-grobid/`, 2 vCPU / 16 GB), and `GROBID_URL` points there. Only open-access PDFs are
sent, and the TEI cache means each PDF is sent once. The compose service is kept for machines with
≥ 8 GB RAM.

First live `parse_tei` (`atlas ingest --paper-id arxiv:1905.12285`): `structure=grobid`, 9
sections (abstract, related, methods, results, discussion, …), 10 references, `offsets_ok=True`,
27 s, versus 1 flat section and 0 references from PyMuPDF. The unit-test TEI fixture carries no
GROBID version stamp and was evidently hand-built, so this is the first check against real output.

---

## ADR-006 — Canonical paper ID with a fixed precedence
**Status:** accepted

**Decision.** `doi:<lowercased, prefix-stripped>` → `arxiv:<id>` → `pmid:<id>` →
`openalex:<W…>` → `s2:<corpusId>` → `sha1:<normalized_title|year|first_author_surname>`.
Implemented once in `ids.py`; nothing else constructs an ID.

**Rationale.** Four sources return the same paper with different identifiers. Without a single
canonical rule the frontier reads duplicates, PageRank is wrong, and citation counts are inflated —
and every one of those errors is visible in the final report.

**Consequences.** The sha1 fallback can wrongly merge two papers with identical
title+year+first author. Rare; log every sha1-fallback assignment for audit.

---

## ADR-007 — The grounding gate is a hard filter, not a score
**Status:** accepted

**Context.** LLMs paraphrase quotes while claiming they are verbatim. This is the single most
dangerous failure mode for a literature-review tool: a fabricated quote attributed to a real paper.

**Decision.** Every extracted claim carries a quote. The quote is normalized (NFKC, de-hyphenate
line breaks, collapse whitespace, unify quote/dash characters) and must appear as an **exact
substring** of the identically-normalized source section. Failing that, `rapidfuzz.partial_ratio`
≥ 97 with the matched span mapped back to original character offsets. Below that, **the claim is
discarded**. No repair, no re-ask, no "confidence: low" passthrough.

**Numeric guard (added after the first test run).** The fuzzy path alone is a fabrication hole:
changing "1.8 seconds" to "0.8 seconds" in a 56-character quote still scores ~99 on
`partial_ratio` and would pass. So every numeric token in the quote must appear verbatim in the
matched source span, even when the surrounding text matched fuzzily. Numbers are where fabrication
does the most damage in a literature review; they do not get the benefit of fuzzy matching.

**Wording guard (added 2026-09-28, after E4).** The numeric guard left the same hole open for
words: "increased" → "decreased" in a 140-character quote scores ~98.6 and passed, as did a
flipped `>`/`<` (99.3) or a dropped minus sign (98.8). The fuzzy path now also requires the quote
to match the source exactly once only formatting noise is removed from both sides: whitespace,
quote marks, hyphens between letters (incl. U+2010/U+2011), letter case, and full stops/commas at
the quote's ends. The fuzzy path keeps its purpose — forgiving PDF extraction noise — and loses
the ability to forgive any change in wording.

*Measured on real data, not just unit tests.* Every stored `fuzzy97` claim (34 of 1,020 verified)
was re-checked against its paper's text rebuilt from the stored chunks; 22 had chunk text
available. A first version of the guard (case-sensitive, no edge-punctuation or Unicode-hyphen
tolerance) would have wrongly dropped 20 of those 22 — capitalised starts, an added full stop,
U+2010 hyphens — so it was relaxed to the rule above. Final: 20 pass, 2 dropped, both for real
reasons: (1) doi:10.1109/jbhi.2025.3631706 — the quote reads "if μ is **set** too high", the
source "if μ is too high": an inserted word the old gate passed at ~99, now a regression test;
(2) doi:10.48550/arxiv.2508.20414 — the quote is right but ATLAS's parsed text reads "FL methods
**3** in medical image analysis": a page number, see next paragraph (a fresh parse fixes it).
Re-seeding the e2e fixture then caught two more live edits the old gate would have kept, both in
doi:10.48550/arxiv.2503.01933: "attains **an** summarization score" (source: "a") and "Quantized
versions (int8, int5, int4) minimize…" (source: "…(int8, int5, int4) **that** minimize…", which
turns a noun phrase into a free-standing claim). It also showed one tolerance was missing: a quote
that omits a numbered reference marker ("Direct Preference Optimization (DPO)" for "…Optimization[7]
(DPO)") is formatting, not wording, so `[7]`-style markers are ignored too. An *invented* marker
still fails the numeric guard.

E4's one failure (claim #18, a "5" inside "the last few 5 layers") turned out **not** to be an LLM
fabrication the gate missed: the "5" is in ATLAS's own parsed text (the stored chunks read "…the
last few" ⏎⏎ "5 layers of FMs…"), where a sentence ran across a PDF page break and PyMuPDF kept the
page number. The gate correctly matched the quote to what ATLAS read; what ATLAS read was wrong.
`strip_repeated_headers` never caught page numbers (unique per page, and ≤ 3 characters). Fixed at
the source: `normalize.strip_page_numbers` removes a bare page number from the top/bottom line of
each page in the PyMuPDF path. Both fixes have regression tests in `tests/unit/test_invariants.py`.
Because this changes the parsed text of affected PDFs, their claim-extraction prompts change too:
re-parsed papers miss the LLM cache once.

**Consequences.** Recall drops — expect 10–25% of extracted claims dropped early, less once prompts
mature. That is the correct trade. The drop rate is logged per run and reported: *"ATLAS discarded
N claims that failed verbatim verification"* is a strength in the report, not a weakness. Store
`quote_char_start` / `quote_char_end` so the UI can highlight the exact source span.

---

## ADR-008 — Candidate generation before claim-pair judging
**Status:** accepted

**Context.** 200 papers × ~8 claims = 1600 claims → 1.28M pairs. Unaffordable and unnecessary.

**Decision.** Embed every claim. For each new claim, retrieve the top-k (k=10) most similar
existing claims above a similarity floor (0.55), plus any claim from a paper in a direct citation
relationship. Only those pairs go to the LLM judge.

**Consequences.** Judging cost becomes linear in claims. We will miss some genuinely contradictory
claim pairs that are lexically distant — an acknowledged limitation, and one worth stating
explicitly in the report's own limitations section.

---

## ADR-009 — React dashboard, not Streamlit
**Status:** accepted

**Decision.** React + Vite + Cytoscape.js.

**Rationale.** The live incremental graph build is the demo. Streamlit's rerun model fights
incremental updates and SSE. Cytoscape's `cy.add()` on an SSE event is the whole feature in ~30
lines. If the frontend slips badly, the fallback is a static graph export (PNG/GraphML) plus the
Markdown reports — not a Streamlit rewrite.

---

## ADR-010 — Abstract-only papers are first-class
**Status:** accepted

**Context.** 40–60% of papers will have no legally accessible PDF. Treating that as failure would
gut coverage.

**Decision.** `Paper.depth ∈ {full_text, abstract_only, metadata_only}`. Abstract-only papers are
read, claim-extracted from the abstract, judged, and graphed — with claims tagged
`source_section: abstract` and given a lower confidence weight in scoring and synthesis. They still
contribute to the citation graph and to PageRank in full.

**Consequences.** Every downstream component must check `depth`. Detectors 4 (unanswered calls) and
6 (shared weaknesses) require `full_text` and simply skip abstract-only papers. Report the
full-text ratio per run — an examiner will ask, and having the number ready is the difference
between a limitation and an oversight.

---

## ADR-011 — Graph algorithms in `networkx`, not Neo4j GDS
**Status:** accepted (supersedes the GDS assumption in `TECH_STACK.md` and `SCORING.md`)

**Context.** The design assumed Neo4j GDS for PageRank / Louvain / Adamic-Adar. GDS is a plugin
that only runs on a self-hosted Neo4j (the `docker-compose.yml` stack) or the paid AuraDS tier.
The primary dev machine cannot run Docker, and the free AuraDB tier has no GDS.

**Decision.** Pull the run's `CITES` subgraph out of Neo4j and run PageRank + Louvain in
`networkx` in `forage/graphalg.py`, on the recompute cadence in `SCORING.md`. Results
(`pagerank`, `cluster_id`) are written back onto the `Paper` nodes so the scorer, the bridge
sweep, and the UI read them the same way they would have from GDS. Louvain is seeded (`seed=42`)
for reproducibility (R9).

**Consequences.** The citation subgraph is a few hundred to a few thousand nodes — `networkx` is
comfortably fast enough at that size, on the recompute cadence (not every iteration). If a run
ever grows past ~50k nodes, revisit: either the Docker Neo4j + GDS, or `python-igraph`. The gap
detectors that were speced against GDS (Adamic-Adar for detector 2) use `networkx` equivalents.

---

## ADR-012 — Free-tier LLMs; a client-side rate-limit pacer; `groq` is the default profile
**Status:** accepted

**Context.** No Anthropic budget. Groq's free tier is 8k tokens/minute org-wide; Gemini's free
tier is 20 requests/day. Relation judging (Job C) is hundreds of calls per run and was losing
most of them to 429s.

**Decision.** `config/models.yaml` gains a `rate_limits` block per provider; `llm/client.py` runs a
trailing-60s token/request pacer that sleeps before a call so the budget is never exceeded — Job C
now *completes* on Groq, just slower. One `Retry-After` backoff on a residual 429. `hybrid`
(Gemini for long-context jobs) stays available but is not the default because 20/day is unusable
for a real run; `local` (Ollama `qwen2.5`) is the offline/unlimited fallback.

**Consequences.** A standard run's judging is paced, not fast — acceptable on a laptop, and the
per-run judge-call cap in `scoring.yaml` bounds it. The real fix for speed is paid Gemini or the
strong PC; the pacer makes the free path actually finish.

**Addendum (2026-09-28) — truncated answers are cached and retried once.** `gpt-oss-120b`
spends completion tokens reasoning, so a long claims window can exhaust `max_tokens: 4000`
before the JSON answer ends (instructor's `IncompleteOutputException`). The window was then
skipped. Re-seeding the e2e fixture showed the cost: 3 of 8 claims windows lost, the run's
claims falling from 41 to 26. Worse for invariant 4: a failed call was never cached, so a
replay re-asked the provider and could get a different graph. Now `LLMClient` stores a
`{"__truncated__": true}` marker under the failed call's key and retries once with double
`max_tokens` (its own cache key). A replay hits the marker, takes the same retry path, and
reaches the same result with zero provider calls. Keys for first attempts are unchanged, so
every previously cached answer still hits. Not applied when a caller set `max_tokens` itself.
Tests: `tests/unit/test_llm_client.py`.

## ADR-013 — 5 of 6 gap detectors, Louvain-per-detector, and a Python-side citation guard

**Status:** accepted

**Context.** GAP_DETECTORS.md specifies 6 detectors + fusion. Detector 2 (predicted links,
Adamic-Adar over the concept graph) is explicitly `[S]` on the roadmap and was cut for scope —
nothing in `gaps/detectors/predicted_links.py` beyond the stub. Detector 1 (Swanson ABC) needs
Louvain communities over the *concept* co-occurrence graph, which is a different graph from the
*paper* citation graph `forage/graphalg.py` already clusters — so `unlinked_concepts.py` runs its
own `networkx.community.louvain_communities` call (seeded 42, matching ADR-011) rather than
reusing `graphalg.recompute`.

**Decision.** Every detector's `detect()` takes an optional pre-fetched `attrs` (paper metadata —
title/year/depth/pagerank) so `gaps/fusion.run_detectors` fetches it once via
`GraphStore.paper_attrs()` and passes it to all 5, instead of 5 redundant Neo4j round trips.
Detector 6 (shared weaknesses) is a thin reader — the actual HDBSCAN clustering already happened
in `extract/concepts.py` during Phase 5a and was written to Neo4j; the detector just scores the
survivors. The citation-rule guard (`gaps/common.has_real_evidence`) is enforced twice by design —
once inside each detector (fail loudly at the source, per GAP_DETECTORS.md's own instruction) and
again in `fusion.fuse` after dedup/merge (a merge could in theory combine two candidates into a
metadata_only-only group). Detector 4 (unanswered calls) reads real claim quotes from `atlas_claims`
via `vector.search_claims`, tracking "does the later paper cite the calling paper" from
`graph.citation_edges()` — a real bug here (the citer-lookup dict was keyed backwards) was caught
by the unit test before it ever reached a live run.

**Consequences — what actually fired on the real 15-paper "IoT devices for women safety" run**
(`a0e32253-6a67-46e5-9b4e-6273c0aa1673`, `atlas gaps` then `atlas report`): detector 1 (unlinked
concepts) found 48 candidates against 108 real concepts; detector 5 (unresolved conflicts) found
the corpus's one real `CONTRADICTS` edge and correctly flagged it unresolved; detectors 3, 4, 6
(empty combinations, unanswered calls, shared weaknesses) found **zero** — expected, documented in
ADR from Phase 5a: this corpus is abstract-only-heavy (full-text ratio 7%), so methods, datasets,
future-work sentences, and limitation sentences — all scoped to real GROBID sections — are mostly
absent. Fusion merged 49 raw candidates into 7 groups with zero corroboration overlap (no gap was
independently found by two detectors on this small a corpus) and dropped 0 to the citation rule.
Job D synthesis (`gemini-2.5-flash` — `gemini-2.5-pro` was retired mid-project, see
`config/models.yaml`) produced a grounded 3-section report citing 12 of the 15 read papers; the
full markdown is at `data/runs/<run_id>/report.md`. This is an honest result, not a strong one:
the gap list is real and citation-backed, but detector diversity needs either a bigger/more
full-text-heavy corpus or a stronger PDF pipeline (GROBID instead of PyMuPDF flat text) to show
its full range.

**Addendum (2026-09-28) — the gap list was not reproducible.** Running the detectors twice on
one finished run (`8d78fb54-ddb2-4121-bc2e-b0685a89b59e`: once in `atlas gaps`, again inside
`atlas report`) gave 8 fused gaps, then 6. Neo4j returns rows in no fixed order and Python
randomises set iteration per process; row and set order steered Louvain, the A/C orientation of
each Swanson triple (so its statement and `gap_id`), and score ties at the `max_candidates` cut
and in fusion's greedy grouping. Checked directly: the original code, run in three processes
with different `PYTHONHASHSEED`s, produced three different gap lists (6, 6, 7 gaps). Now every
detector sorts its inputs and breaks score ties by `gap_id`, and fusion does the same; the fixed
code produces byte-identical output across processes. Regression test:
`tests/unit/test_gaps.py::test_unlinked_concepts_is_independent_of_row_order` (fails on the old
code). Consequence: E6's gap ratings were made on one of several possible gap lists for that
run.

**Addendum (2026-09-29) — detectors 3/4/6 with real GROBID sections.** First multi-paper
full-text run (`b0e7e2c2`, federated learning, 4 of 13 papers parsed by GROBID): detectors 1, 3,
4, 5, 6 all returned 0. Concept extraction found 48 concepts, 4 methods, 4 datasets and 2 "call"
sentences, but none met the ≥2-paper support thresholds, and no limitation sentences clustered.
So the full-text detectors are not broken — they are starved: they need several full-text papers
that share methods/datasets, which 13-15-paper runs over open-access PDFs do not supply. The
remedy is scale (deep mode) or a corpus with more open full text, not threshold tuning — lowering
the ≥2-paper support to 1 would turn every method mention into a "gap". See TESTING.md "GROBID
before/after".

## ADR-014 — FastAPI backend: thread-backed background runs, poll-based SSE, no per-element graph streaming

**Status:** accepted

**Context.** Phase 6 needs `POST /runs` to return immediately while the (long, sync,
partly-nested-asyncio) foraging loop keeps running, a live event stream a browser can
consume, and a grounded chat endpoint. ARCHITECTURE.md already rules out a queue-worker
fleet ("one process, not a queue-worker fleet") — everything here has to fit the
single-process model.

**Decisions.**
1. **Background runs = `asyncio.create_task` + `asyncio.to_thread`, not Celery/RQ.**
   `loop.run()` calls `asyncio.run()` internally (`_expand`'s reference/citer fetch), so
   it cannot run on the request-handling event loop's own thread — `asyncio.to_thread`
   gives it a fresh thread with no running loop. `loop.run()` gained optional `run_id`
   (so the API can generate and return the id before the loop starts) and `should_stop`
   (a `threading.Event.is_set` passed from `api/registry.py`, checked once per outer
   loop iteration — cooperative, not preemptive: `POST /stop` finishes the current
   paper, exactly as API.md specifies).
2. **SSE is polling the `events` Postgres table, not a pub/sub broker.** `db.emit_event`
   now auto-assigns a per-run `seq` (previously the caller passed one, and the one real
   caller — `loop.py` — used the read-order counter, which does not work once multiple
   event *types* per paper exist). `GET /runs/{id}/events?since_seq=` replays from
   Postgres, then polls every 1s for more — replay and live-tail are the same code path,
   so they cannot diverge. This trades a little latency (up to 1s) for zero new
   infrastructure.
3. **`run_finished` is not the stream-closing signal — `pipeline_finished` is.** Caught by
   the live end-to-end test (below), not by unit tests: `loop.run()` emits
   `run_finished` at the *loop's* end, but when Neo4j is configured the API's background
   task (`api/tasks.py`) keeps going — concept extraction, gap detection, synthesis —
   emitting `gap_found`/`report_ready` afterward. An SSE client that closed on
   `run_finished` would silently never see those. Fixed by having `tasks.py` emit
   `pipeline_finished` exactly once, in a `try/finally`, on every exit path (success,
   loop failure, synthesis failure, or "skipped, no Neo4j"); the SSE endpoint now closes
   on that instead.
4. **The API auto-chains concept extraction, not just gaps + synthesis.** Also caught
   live, not in unit tests: the gap detectors need Concept/Method/Dataset nodes that only
   `extract.concepts.extract_and_store()` (Phase 5a) produces, and nothing was calling it
   automatically. Without this, every run started through the browser would silently
   produce zero gaps, because the CLI's separate `atlas concepts` step was never invoked.
   `api/tasks.py`'s background task now runs concepts → gaps → synthesis in that order.
5. **`node_added`/`edge_added` (per-element Cytoscape streaming) are cut.** The frontend
   re-fetches `GET /runs/{id}/graph` (a full snapshot) on relevant events instead of the
   backend patching a live graph incrementally. Simpler, lower-risk, and the API.md table
   already anticipated batched-relayout at scale ("batch layout every 25 additions") —
   full-snapshot refetch is a coarser version of the same tradeoff. Documented as a
   deliberate [D]-scope cut in `docs/API.md`, not an oversight.
6. **Chat's honesty guarantee is structural, not prompted.** Retrieval
   (`vector.search_claims`) hard-filters by `run_id` server-side; if nothing clears the
   similarity floor, the canned refusal is returned *without calling the LLM at all* — so
   there is no path for the model's parametric knowledge to leak in. `cited_paper_ids`
   the model returns are filtered against the actual retrieved set before becoming
   `citations[]`, the same "don't trust the LLM with the citation list" pattern
   `synthesis/report.py` already uses.

**Consequences — what the live end-to-end test found.** A real `POST /runs` (3-paper
"wearable fall detection" query) was watched over real SSE from start to finish: correct
`run_started` → `harvest_done` → (`paper_selected` → `paper_ingested` →
`claims_extracted` → `relation_judged`× → `saturation` → `frontier_updated`) × 3 →
`run_finished` → `report_ready` → `pipeline_finished`, ~500s wall clock (matches the
documented ~7-minute one-time abstract-embedding cost on this laptop), $0.00 (Groq free
tier). Two real bugs surfaced only by this live run, not by any unit test: point 3 and 4
above. A third, `vector.search_claims`/`get_chunks_by_paper` crashing with "Collection
atlas_claims not found" when called before any claim had ever been written (missing
`ensure_collections()` — every other vector.py function already had it) — caught by the
new API unit test suite (`tests/unit/test_api.py`), not live. All three are fixed.

**Addendum — two more bugs, this time only visible in the actual browser.** `atlas.api`
and `atlas.cli` are separate process entrypoints; the Windows-console UTF-8 fix
(`console_encoding.py`, originally added to `cli.py` in Phase 3/4) was never applied to
the API server. A real full-text paper's PDF text containing a non-breaking hyphen
(`‑`) crashed the foraging loop mid-run the first time a run was started through
the dashboard — `api/tasks.py`'s error handling caught it cleanly (an `error` event +
`pipeline_finished`, not a raw 500), but the run itself still failed. Fixed by calling
`fix_windows_console_encoding()` at the top of `api/main.py` too — it runs before any
logging happens and covers the `asyncio.to_thread` worker threads the loop runs on,
since `sys.stdout`/`sys.stderr` are process-wide. Separately, the frontend's event log
was showing fake `#NaN error (undefined): undefined` entries: `"error"` is a reserved
`EventSource` event name — a native connection failure (or the stream's own ordinary
close) *also* dispatches a plain `Event` named `"error"`, indistinguishable by name from
the server's real business `"error"` event (a `MessageEvent` with real payload). Fixed
in `web/src/lib/useEvents.ts` by guarding on `ev instanceof MessageEvent` before treating
an `"error"`-named event as server data. Both were found by actually running the app in
a browser — twice, once by re-running a known query and once independently by the user
running a different one — not by any of the 124 unit tests or the TypeScript/lint
checks, all of which stayed green throughout. This is the concrete case for the "start
the dev server and use the feature in a browser" rule: neither bug was reachable from
inside the process boundary the tests exercise.

## ADR-015 — Abstract vectors are write-once, in one representation

**Status:** accepted (2026-09-28)

**Context.** `atlas_abstracts` holds one vector per paper, shared across runs. Seeding wrote it
as a *document* embedding of `title + "\n" + abstract` (`embed_texts`); ingest then overwrote it
for every paper it read with a *query* embedding (bge's query instruction prefix) of the abstract
alone (`embed_query`). So a paper's seed relevance depended on whether some earlier run had read
it. Found while re-seeding the e2e fixture: the same query on the same cache read
`doi:10.48550/arxiv.2503.01933` first on one run and `doi:10.26615/978-954-452-098-4-093` first on
the next, because the latter's cosine to the query had moved from 0.8332 to 0.8609 between them.
Two readers were affected: seed ranking (invariant 4, and so E8) and `evaluation/e1_baseline.py`,
whose "one-shot cosine" baseline ranked the papers ATLAS had read with query-style vectors and
everything else with document-style ones.

**Decision.** Ingest writes the abstract vector only when the paper has none, with the same
representation seeding uses. `atlas repair-abstract-vectors` re-embeds the points ingest had
overwritten (they are the ones carrying a `depth` payload). Run on Suhani's store 2026-09-28:
58 of 2,560 points repaired (backup taken first). Regression test:
`tests/unit/test_ingest.py::test_ingest_never_overwrites_a_cached_abstract_vector`.

**Consequences.** E1's published numbers (40 % overlap, 14 vs ~1 clusters) were computed on the
mixed vectors and must be re-run before they are reported; E8's "identical graph on a warm cache"
held for back-to-back runs but not across a store that earlier runs had modified. The e2e fixture
was seeded before this fix and still carries three overwritten vectors; that is harmless for a
replay test (it replays recorded state) but should be cleaned at the next re-seed.

## ADR-016 — Neo4j writes survive a dropped connection

**Status:** accepted (2026-09-28)

**Context.** The first crawl on the Postgres stack died after one paper with
`SessionExpired` / `SSLEOFError`: harvest plus abstract embedding had left the driver's pool idle
for ~7 minutes, AuraDB had closed the idle connection, and `GraphStore._run_write` used
`session.run`, which never retries. One transient drop ended the whole run.

**Decision.** The driver pings any pooled connection idle for more than 30 s before reuse
(`liveness_check_timeout=30`) and recycles connections after 5 minutes
(`max_connection_lifetime=300`). Writes go through `session.execute_write`, which the driver
retries on transient errors. Retrying is safe because every write is an idempotent MERGE / `ON
CREATE SET` (the `run_ids` appends are guarded by a membership check). Reads still use
`session.run` and rely on the liveness check. Verified against AuraDB:
`tests/integration/test_graph_idempotent.py` passes.

## ADR-017 — Per-run facts must not live on shared nodes

**Status:** accepted (2026-09-28)

**Context.** Papers are shared across runs by design (ADR-006: one canonical node per paper).
Several *per-run* facts were nonetheless stored on those shared nodes or points, so the last run
to touch a paper silently rewrote what every earlier run showed. Found by looking at the
dashboard for the first time in a real browser:

| Fact | Where it lived | Symptom | Status |
|---|---|---|---|
| read order | `Paper.read_order` | run `a0e32253` (15 papers read) showed 27 "read" papers | **fixed**: graph snapshot reads the run's own `READ` edge |
| gaps | `Gap {gap_id}` unique per gap | a second run that found the same gap took the node over; stale detector passes accumulated; `a0e32253`'s saved gap list has ranks 3,3,5,5,6,6,7 | **fixed**: `Gap {gap_key: run_id:gap_id}`, a run's gap set is replaced on every pass (constraint swapped in AuraDB 2026-09-28; integration test) |
| abstract vector | `atlas_abstracts` point per paper | seed ranking depended on earlier runs (ADR-015) | **fixed** (ADR-015) |
| chunk `run_id` | `atlas_chunks` points keyed per paper | a later run re-labels the chunks; earlier runs lose their text | **mitigated**: the source view falls back to another run's copy and says so |
| depth | `papers.depth` / `Paper.depth` | a paper read abstract-only in one run and not at all in another shows the last value (seen: a paper with 6 abstract claims labelled "metadata only") | open — cosmetic; per-run depth is in the frontier/ingest events |
| PageRank, cluster | `Paper.pagerank`, `Paper.cluster_id` | colours/sizes of an old run reflect the latest recompute on those papers | open — E1/E2 cluster counts are computed at run end from the run's own graph, but re-snapshotting an old run after newer runs can show other clusters |

**Consequence.** Snapshots taken before these fixes (the three demo runs, 2026-09-19) have the
old gap list; their `graph.json` was refreshed with `atlas snapshot --graph-only` (gaps, report
and stats deliberately left as they were, so they still match what E6 rated).
