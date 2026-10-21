# ROADMAP

Labels: **[C]** core (must ship) · **[D]** differentiator (what makes this a project, not a
tutorial) · **[S]** stretch (cut without guilt).

**Build order rule:** get a thin end-to-end pipeline working before improving any single stage.
Phase 3 must be reachable by week 6.

---

## Phase 0 — Foundations (week 1)
- [x] **[C]** Repo, `pyproject.toml`, ruff + mypy + pytest wired
- [~] **[C]** `docker-compose.yml` up: postgres, neo4j (APOC+GDS), qdrant, grobid
      — compose file ready; dev machine can't run Docker, so a **lightweight path** is
      wired in (SQLite / embedded Qdrant / hosted GROBID / optional AuraDB Neo4j).
      Full stack pending the stronger PC.
      **2026-09-28:** Postgres verified — migrations 0001–0003 apply, the unit suite passes
      against it (`ATLAS_TEST_POSTGRES_DSN`), and a real 3-paper crawl completed on Postgres
      + GROBID + AuraDB (run `a5071aac-8ab4-485c-8995-b0051c7c4166`). GROBID runs on a Hugging
      Face Space rather than local Docker (5.9 GB machine; see DECISIONS.md ADR-005 addendum).
      Neo4j stays on AuraDB; Qdrant embedded.
- [x] **[C]** `config.py` (pydantic-settings), `.env` loading, `atlas health` checks all services
      (`/health` HTTP route is Phase 6)
- [x] **[C]** `contracts.py` — the full model set from `CONTRACTS.md`
- [x] **[C]** `ids.py` canonical ID + unit tests (multi-source *list* dedup is Phase 1)
- [x] **[C]** Alembic migrations for the schema in `DATA_MODEL.md`
- [x] **[C]** `llm/client.py` — LiteLLM + instructor + response cache + cost logging

**Exit:** `make test` green (23 unit tests). `atlas health`: db + neo4j (AuraDB Free) +
qdrant + llm OK; grobid SKIP (public demo asleep → PyMuPDF fallback; real GROBID on the
full stack). Phase 4 graph algorithms will run in `networkx`, not Neo4j GDS.

## Phase 1 — Harvest (week 2)
- [x] **[C]** `sources/base.py` protocol; `openalex.py` (incl. inverted-index abstract reconstruction)
- [x] **[C]** `arxiv.py`, `pubmed.py`, `semantic_scholar.py`
- [x] **[C]** Disk/DB cache on every request; polite rate limiting per source
- [x] **[C]** Dedup across sources → `PaperMeta` list (`ids.dedup_papers`)
- [x] **[C]** Job A: keyword expansion → `QueryPlan`
- [x] **[C]** `atlas harvest "<query>"` prints N unique papers with per-source breakdown

**Exit:** met — `atlas harvest "IoT devices for women safety"` → **468 unique** papers
(openalex 360, pubmed 121, arxiv 55, s2 20-then-429), deduped, cached to disk + SQLite.
Cross-source overlap is low here (~16%) because the four keyword searches surface mostly
disjoint literature; genuine dupes still collapse by canonical id. **R1 tripwire** (PDF
resolver over 200 papers) belongs to Phase 2 — early signal: ~46% have a direct `pdf_url`.
S2 is effectively unusable without an API key (shared-pool 429s); it degrades gracefully.

## Phase 2 — Ingest one paper properly (week 3)
- [x] **[C]** PDF resolution chain (source → arXiv → Unpaywall → Europe PMC → abstract-only)
- [x] **[C]** GROBID client + TEI parsing → `ParsedDoc` (coded + unit-tested on a TEI fixture;
      no live GROBID yet — the HF demo is dead, needs the docker container)
- [x] **[C]** PyMuPDF fallback; `structure` flag — this is the *active* path without Docker
- [x] **[C]** `normalize.py` with idempotence test (already in the scaffold)
- [x] **[C]** Chunk → embed (local bge-base) → Qdrant with char offsets in the payload
- [x] **[C]** `atlas ingest --paper-id <id>` end to end

**Exit:** met — `atlas ingest --paper-id arxiv:1905.12285` → PDF resolved, PyMuPDF parse,
13.9k normalized chars → **19 chunks in Qdrant**, `offsets_ok=True` (full_text[start:end]
== chunk.text for every chunk). GROBID sections/references land when the container runs.
**R1 tripwire:** `atlas resolve-check --limit 60` → **45/60 = 75%** full-text reachable
(target ≥ 35%). Sample skews arXiv-heavy; a 200-paper run would be more representative.

## Phase 3 — The loop, thin (weeks 4–6) ← **the make-or-break milestone**
- [x] **[C]** Frontier table + seed ranking (relevance only) — `forage/frontier.py`, Postgres queue
- [~] **[D]** Full 5-component scoring — Relevance (min-max across the live frontier, per
      SCORING.md §1) + Recency + Novelty are live; PageRank + Contest weighted but 0 until
      GDS / the judge (Phase 4).
- [x] **[C]** Job B: claim extraction per section — `extract/claims.py` (`claims.v1.md`)
- [x] **[C]** **Grounding gate** — reused from Phase 0; drop-on-fail, counted, never repaired
- [x] **[C]** Citation expansion (references + citers) via OpenAlex, three-band admission
- [x] **[C]** Neo4j writes: Paper, Claim, CITES, MAKES_CLAIM — incremental MERGE, idempotent
- [x] **[C]** Stopping criteria — budget (papers/USD/minutes) + EMA saturation + exhausted + 3-fail
- [x] **[C]** `atlas run "<query>" --mode standard` produces a graph

**Exit:** met (mechanism) — `atlas run "IoT devices for women safety" --max-papers 15` read 15
papers autonomously, wrote **130 Paper / 46 Claim / 211 CITES** into Neo4j AuraDB
incrementally, 0 ungrounded claims dropped, saturation EMA saved to
`data/runs/<id>/saturation.json`, $0.11 (Gemini), 10 min. A full 25-paper `--mode standard`
run is the same command without the cap. Bridge promotion + PageRank/Louvain are Phase 4.
Known: seeds skew to abstract-only regional venues (this applied literature genuinely is
that shape); better seed quality needs the [D] scoring polish + a full-text preference.
LLM split: keywords→Groq, claims→Gemini (`hybrid` profile; Groq's 8k-tok/min cap is too
small for full-text claim extraction).

## Phase 4 — Relations and the graph's meaning (week 7)
- [x] **[C]** `judge/pairing.py` — kNN candidate generation (ADR-008); one pair/call
      (batching deferred — free Groq is the bottleneck, not call overhead)
- [x] **[C]** Job C: 5-way relation judging — per-call failure logged + skipped
- [x] **[C]** Relation edges (SUPPORTS/CONTRADICTS/EXTENDS/REPLICATES/DIFF_SCOPE) with
      confidence + rationale; UNRELATED writes no edge
- [x] **[D]** Contest score computed from CONTRADICTS ratio, fed into `_rescore_frontier`
- [x] **[D]** PageRank + Louvain — **networkx, not GDS** (no Docker); on the recompute
      cadence + a final pass
- [~] **[D]** Bridge promotion — built + unit-tested; hasn't fired on a real run yet
      (needs ≥2 Louvain clusters with ≥3 read papers each — a bigger, more diverse crawl)
- [x] **[C]** R2 tooling: `atlas judge-eval --export` / `--score` (per-label precision/recall)

**Exit:** relation edges exist and read sensibly (SUPPORTS/EXTENDS/DIFF_SCOPE with
rationales; no CONTRADICTS yet — the narrow-topic seeds all agree). Bridge promotion
awaits a real `--mode standard` run on the stronger PC. Judge coverage is throttled by
Groq's 8k-tok/min free tier (`groq` profile for claims+judge on this abstract-heavy
corpus; `hybrid` when Gemini quota is available).

## Phase 5 — Gaps and synthesis (weeks 8–9)
- [x] **[C]** Concept/method/dataset extraction + normalization (**R4 tripwire**)
- [x] **[D]** Detectors 1, 5, 6 (Swanson ABC, unresolved conflicts, shared weaknesses)
- [x] **[D]** Detectors 3, 4 (empty combinations, unanswered calls)
- [~] **[S]** Detector 2 (predicted links) — skipped, cut without guilt per [S]
- [x] **[C]** Fusion, dedup, corroboration bonus, **citation rule filter**
- [x] **[C]** Job D: one-pass synthesis → 4-section `Report`
- [x] **[C]** Markdown export

**Exit:** a full report for the sample query — done live against run
`a0e32253-6a67-46e5-9b4e-6273c0aa1673` (`atlas gaps` then `atlas report`), see
`docs/DECISIONS.md` ADR-013. **R3 tripwire (expert gap review) is a manual step for the
user, still pending — not automatable.**

## Phase 6 — The dashboard (weeks 10–11)
- [x] **[C]** FastAPI routes + background run task — all of docs/API.md's REST surface,
      live-verified against a real run through the API (not just unit tests)
- [x] **[D]** SSE events + replay from the `events` table — live-verified; see ADR-014
      for the `pipeline_finished` vs `run_finished` fix this surfaced
- [x] **[D]** Cytoscape live graph, node size by PageRank, colour by cluster —
      `web/src/components/GraphView.tsx`, fcose layout
- [x] **[C]** Frontier table view with score breakdowns (**best debugging tool — build it
      first**) — `web/src/components/FrontierTable.tsx`, sortable by any score component
- [x] **[C]** Report view + paper detail with highlighted quote spans —
      `web/src/pages/{ReportView,PaperDetailPage}.tsx`
- [x] **[D]** Grounded chat with citation chips and out-of-scope refusal —
      `web/src/pages/ChatView.tsx`
- [x] **[S]** Saturation + cost charts — `web/src/components/SaturationChart.tsx`
      (dependency-free inline SVG), backed by a new `GET /runs/{id}/timeline` endpoint
      built from the real `saturation` event each read already emits (new_info/EMA,
      cumulative claims, cumulative cost), not synthetic data. Verified via `tsc`, lint,
      and a production build only — no live browser available this session (built-in
      browser can't reach localhost, no Chrome extension loaded), said explicitly rather
      than claimed as visually confirmed
- [x] **[S]** Graph export to PNG — `cy.png()` wired to an "Export PNG" button in
      `RunView.tsx`/`GraphView.tsx` (GraphML export not done, PNG covers the actual use
      case — a demo screenshot/report figure)
- [x] **[C]** `tests/e2e/` offline pipeline test — real full pipeline (no faked
      collaborators, unlike `tests/unit`), replaying a genuine tiny 3-paper crawl entirely
      from a warm cache with live network hard-blocked. **Passes: 144s, 0 network calls.**
      Getting here surfaced and fixed two real bugs: (1) `ingest/pdf_fetch.py`'s Unpaywall
      lookup was never actually cached (invariant 5 gap — fixed, now matches every other
      external call's caching convention); (2) the fixture's own build accidentally baked
      the user's real contact email into cached request URLs on the first two attempts —
      caught before committing, re-seeded with a placeholder instead

**Exit criterion met: the whole thing runs from a browser.** Built with Vite + React +
TypeScript + Tailwind v4 + Cytoscape (fcose layout) + react-router-dom, talking to the
FastAPI backend via relative `/api/v1` paths (Vite dev-proxies to the backend; a real
deploy would sit behind the same origin). Live-tested twice against real runs through
the actual browser — once by re-running a known query, once independently by the user
running a different one ("fine tuning in ai models", 6 papers, up to 163 chunks of real
full text) — not just `tsc`/lint/unit tests. Two real bugs surfaced only by that live
browser test, both fixed; see ADR-014's addendum.

Stretch items (saturation/cost charts, graph export) are cut without guilt, per their [S]
label — nothing about the exit criterion depends on them.

## Phase 7 — Evaluation and writing (weeks 12–14)
- [~] **[C]** Ablation study: zero each scoring component, compare (see `TESTING.md`) —
      done for 1 of 3 queries (`iot_safety`, 15-paper cap): removing recency alone costs
      as much cluster coverage as removing pagerank+novelty+contest+recency together.
      2 of 3 queries still need the sweep (`evaluation/e2_e3_ablation.py`, ~2-4 hrs/query)
- [~] **[C]** Baseline comparison: one-shot RAG vs. ATLAS on the same query —
      `evaluation/e1_baseline.py` built and run once (`iot_safety` query): 40% overlap,
      14 Louvain clusters covered vs. ~1 for the baseline. 2 of 3 queries still need a run
- [x] **[C]** Judge precision/recall table — 49 pairs hand-labelled, 57.1% accuracy. The
      real finding: `DIFF_SCOPE` recall is weak (0.379) — the judge systematically
      mislabels "two unrelated independent devices" as EXTENDS/SUPPORTS/CONTRADICTS
      rather than DIFF_SCOPE. See `evaluation/e5_sample.jsonl`, TESTING.md E5
- [x] **[C]** Expert gap assessment (R3 tripwire) — 10/10 gaps rated: 2 plausible, 4
      trivial, 4 wrong. Two "wrong" gaps claim missing links the corpus actually has
      (concept-extraction vocabulary mismatch); the one conflict-type gap traces directly
      to the judge's DIFF_SCOPE weakness above. See `evaluation/e6_sheet.md`, TESTING.md E6
- [x] **[C]** Reproducibility check (R9 tripwire) — done in Phase 4/5, see DECISIONS.md
- [x] **[C]** Three saved demo runs, cached, offline-playable — `a0e32253` (IoT safety,
      the most-vetted run: E4/E5/E6 were all done against it), `917e7b11` (same query,
      second crawl, backup — largely the same paper pool, not an independent data point),
      `42ddbe56` (federated learning for medical imaging, different domain, no gaps —
      only 2 of 14 papers had enough full text). Made offline-capable by `atlas snapshot
      --run-id ...` (`store/snapshot.py`): saves the graph/gaps/report/stats — the only
      parts that came from cloud Neo4j — to `data/runs/<id>/offline/`, and the API serves
      those for any finished run. Verified with Neo4j pointed at an unreachable host and
      every outgoing web call forced to fail: all pages load in <0.1s, chat refusal works.
      NOT verified by literally switching wifi off — do that once yourself before the demo.
      Still needs internet: a real answer to a *new* in-scope chat question (LLM call);
      already-asked questions replay from the LLM cache
- [~] **[C]** Report + slides + demo script — `report/report.md` now has every section
      filled with real content (Abstract, Introduction, Design, Implementation,
      Evaluation E1-E8, Discussion, Conclusion, Appendix A demo script, Appendix B
      reproducibility). Still open: 2 of 3 queries' E2/E3 data, the 3 cached demo runs
      Appendix A depends on, and slides (not started)
- [ ] **[S]** Langfuse traces as a live demo artefact — **blocked on an external
      account**, not effort: needs a Langfuse Cloud sign-up (or self-hosting, which is a
      Docker service this machine doesn't run) and API keys, which only the user can
      create. Everything else in this phase's [S] items was completed without asking;
      this one genuinely needs a decision only the user can make

**E3 (bridge promotion value) done for 1 of 3 queries alongside E2** (same sweep, same
harness): `bridge.enabled: true` vs `false` read the *identical* 15 papers in the
identical order, and each run's event log confirmed zero `bridge_promoted` events either
way — a direct, controlled confirmation that the mechanism has not yet fired at this
corpus scale, not just an inference from tuning history.

Also done this phase, not in TESTING.md's E-numbered list but load-bearing for it: an
audit of "the tests that actually matter" found all 11 already existed, 2 too weak to
trust (`test_chat_out_of_scope_refuses`, `test_abstract_only_path` — both strengthened)
and 1 missing entirely (`test_graph_write_idempotent` — added as a real-Neo4j
integration test, `tests/integration/`, since this project has no Docker/testcontainers).
`evaluation/e4_grounding_sample.py` (E4) needed a new `dropped_claims` table — the
grounding gate only ever counted rejects, never retained the attempted quote — added via
migration 0003, populating from every run going forward. **E4 hand-check done: 49/50
(98%) of sampled verified claims independently confirmed genuinely verbatim** (re-fetched
every source paper and checked exact substring match, not just eyeballed) — above the
95% target. The one failure is real and informative: a fabricated digit slipped through
the grounding gate's fuzzy-match path (`fuzzy97`). See TESTING.md E4.

---

## Explicitly out of scope
Multi-user auth · deployment beyond `docker compose up` · fine-tuning · a mobile app ·
supporting every scholarly API in existence · real-time collaborative editing · anything invented
after this file was written and not discussed with the team.

## Two-person split suggestion
One owns **loop + stores** (phases 2, 3, 4), the other owns **harvest + gaps + UI** (phases 1, 5,
6). Both must be able to run the whole pipeline. Integrate weekly, not at the end.
