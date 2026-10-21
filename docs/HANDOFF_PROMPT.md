# HANDOFF PROMPT — finish ATLAS end to end (paste this to Claude Code as your first message)

> Repo: https://github.com/Suhani-99/ATLAS  ·  Owner: Suhani (final-year B.Tech student, non-technical — explain everything in plain language)
> Written 2026-09-19 by the Claude Code instance that built phases 0–7 with Suhani. Everything below was verified against the repo and real runs on that date; where something is a guess or unverified it says so.

---

## 0. Your role and the goal

You are Claude Code, working with a friend of Suhani who has a **stronger machine with Docker and plenty of disk**. Suhani built **ATLAS** with a previous Claude Code session on a weak laptop (Intel i3, 7.7 GB RAM, no GPU, no Docker, C: drive ~99 % full), so several things were deliberately built in a "lightweight" way or left undone. **Your job: finish the project end to end and get it to a state where it can be shown live, with real output, to a board of faculty members.**

"Done" means all of section 9's checklist is ticked, with real evidence (numbers, screenshots, a rehearsed offline demo) — not "the code exists".

**How to work**
1. Read, in this order: `CLAUDE.md` → `docs/ARCHITECTURE.md` → `docs/ROADMAP.md` → `docs/TESTING.md` → `docs/RISKS.md` → `docs/DECISIONS.md` (ADR-005, 007, 010, 013, 014 especially) → `report/report.md`. `CLAUDE.md`'s seven **non-negotiable invariants** are the project's thesis; never break one silently. If a task seems to require it, stop and ask.
2. **Report honestly.** Never hide a failure, weak result, or limitation. Several real weaknesses are already documented (section 3) — keep documenting, don't paper over. Never invent identifiers (DOIs, paper IDs, run IDs, counts). **Look up full run IDs; never reconstruct one from memory** (the previous session made exactly that mistake once).
3. **Verify with real runs**, not just unit tests. Type-checks and passing tests are not proof a feature works. For UI work, actually open it in a browser (the previous session had no browser tool and could not — that is a debt you can pay).
4. Follow ROADMAP labels: **[C]** core (must ship), **[D]** differentiator, **[S]** stretch (skip without guilt, ask before starting one).
5. Suhani is non-technical. Give short plain-language updates; explain *why*, not jargon. Ask before big architecture changes or anything costing real money.
6. **Git:** small logical commits with detailed messages. **No attribution / co-author lines** in commit or PR messages (Suhani's explicit instruction). Never commit `.env`, keys, or Suhani's real email. Run `git status` before any destructive git command. Push only when asked or when the checklist says so.
7. Update `docs/ROADMAP.md`, `docs/TESTING.md`, and `report/report.md` as results land — they are the report's source of truth.

---

## 1. What ATLAS is (30-second version)

Given a research question, ATLAS runs a **closed foraging loop** over scholarly literature: harvest ~500 candidates from OpenAlex / arXiv / PubMed / Semantic Scholar → embed + rank → read the best paper (PDF → parse → chunk → embed → extract **verbatim claims**, each checked by a **grounding gate**) → follow its citations, re-score the frontier, repeat → judge claim-pair relations (supports / contradicts / extends / replicates / diff-scope) → build a Neo4j graph incrementally → run 5 **gap detectors** → fuse into ranked gaps (every gap must cite bounding papers) → one-pass grounded synthesis (agreement / contradictions / gaps / methods timeline) → FastAPI + React dashboard with live SSE graph, report, paper pages with highlighted quotes, and grounded chat that **refuses** off-corpus questions.

Stack: Python (repo requires >=3.11; all development ran on 3.14.2 — use 3.11+ and tell Suhani if anything breaks on your version), FastAPI, SQLAlchemy/Alembic, Neo4j, Qdrant, sentence-transformers (`BAAI/bge-base-en-v1.5`, local), LiteLLM (Groq + Gemini), PyMuPDF (GROBID optional), React 19 + Vite + Tailwind v4 + Cytoscape (fcose). Repo map and commands: `CLAUDE.md`.

---

## 2. Verified state of the repo (2026-09-19)

| Area | State |
|---|---|
| Phases 0–6 (pipeline, API, dashboard) | **Built and live-verified.** |
| Unit tests | **136 pass** (`PYTHONPATH=src pytest -q tests/unit`). |
| Offline e2e test | **Passes** (`make test-offline` / `pytest tests/e2e`, ~2.5 min, zero network). Must be run as its own pytest invocation, never combined with `tests/unit` (conftests set incompatible env at import time). |
| Integration test | `tests/integration/test_graph_idempotent.py` needs a real Neo4j; passed against AuraDB. |
| Evaluation E1, E7, E8 | Done. |
| E2/E3 ablation + bridge | Done for **1 of 3** queries (`iot_safety`). Query 2 (`federated_learning_medical`): only 2 of 8 configs produced data (disk filled mid-sweep). Query 3 (`biomedical`): not started. |
| E4 / E5 / E6 | Done as a **first pass by Claude, not a human** (see §3) — Suhani has not verified them yet. |
| Report | `report/report.md` drafted end to end (plain markdown). Needs 2 more queries' data and final format. |
| Demo runs | Three finished runs + offline snapshots exist **only on Suhani's laptop** (see §4). |
| Slides | Not started. |
| Docker / GROBID / local Postgres+Neo4j | **Never run.** `docker-compose.yml` exists but is untested by us. |

### Real results so far (use these as the baseline you must beat or honestly reproduce)
- **E1 (central claim), `iot_safety`, 15 papers:** 40 % overlap with the one-shot cosine baseline; ATLAS covered **14 distinct Louvain clusters vs ~1**.
- **E2 ablation (`iot_safety`):** full 13 clusters; −pagerank 12; −novelty 13; −contest 13; −recency 10; relevance-only 10. Recency carries most of the non-relevance signal.
- **E3 bridge promotion:** `bridge_on` and `bridge_off` read the identical 15 papers; **zero `bridge_promoted` events on any real run ever.** Needs a deep-scale run to test properly.
- **E4 grounding:** 49/50 (98 %) verified verbatim by re-fetching every source. One real failure: a fabricated digit slipped through the gate's **fuzzy97** path.
- **E5 judge:** 49 hand-labelled pairs, **57.1 % accuracy**; `DIFF_SCOPE` recall **0.379** (precision 0.917). The judge reads shared vocabulary between unrelated independent devices as SUPPORTS/EXTENDS/even CONTRADICTS.
- **E6 gaps (R3 tripwire), top 10 of the `iot_safety` run:** 2 plausible, 4 trivial, 4 wrong.
- **E7:** mean **$0.0018 per standard run**, LLM cache hit rate 53 %, full-text ratio only 9.2 % (that is what the missing GROBID/full-text costs us).
- **R6 dashboard stress test:** headless fcose layout 0.5 s @100 nodes, 11.8 s @500, **32.6 s @1000** (`web/scripts/stress_test_layout.cjs`). A refresh throttle was added (>100 nodes → once per 4 s) but each single re-layout is still slow.

---

## 3. Known weaknesses you should expect and ideally fix (all documented in `docs/TESTING.md`, `docs/RISKS.md`, `report/report.md` §4–5)

1. **Judge is weak at `DIFF_SCOPE`.** Every completed IoT run's one "CONTRADICTS" is the same **false positive**: "NodeMCU as main processor" vs "Raspberry Pi Pico + ESP32-CAM" — two independent devices, not a disagreement. Consequence: detector 5 (unresolved conflicts) inherits it; **there is currently no genuinely good contradiction example anywhere** for the demo. Suhani agreed to show it with an honest caveat only as a fallback — a real one is far better. Try sharpening `config/prompts/judge.v1.md` (bump the version → cache key changes) with explicit negative examples, then re-measure with `atlas judge-eval --score`.
2. **Grounding gate fuzzy path too loose** (`src/atlas/extract/grounding.py`): a single inserted character passes at ~97 % similarity. Fix (e.g. reject fuzzy matches that add/alter digits or whole tokens; keep ligature/hyphen tolerance) **and add a regression test** using the real bad claim described in `evaluation/e4_sheet.md` (#18). The exact-match path is untouched and must stay exact.
3. **Concept extraction vocabulary mismatch** ("protection" ≠ "personal security") makes `unlinked_concepts` claim links that exist; two E6 gaps were wrong for this reason. Also fusion dedup missed two near-duplicate gaps.
4. **Only 3 of 5 gap detectors have full-text material to work with** on this machine because PyMuPDF gives flat text with no sections. Detectors 3/4/6 (empty combinations, unanswered calls, shared weaknesses) found **zero** on every real run. GROBID is the intended fix — verifying that is your task B.
5. **Bridge promotion never fired.** Unknown whether it works at scale or needs redesign. Task D.
6. **`parse_tei` (GROBID TEI parsing) is unit-tested on one fixture but has never run live.** Expect surprises.
7. **Postgres has never been used.** All development ran on SQLite (`sqlite+pysqlite`). Alembic migrations 0001–0003 exist; a SQLAlchemy `Uuid` column bug already bit us once on SQLite (run_ids are now plain text). Treat Postgres compatibility as **unverified**: run migrations, the unit suite, and a real run against it.
8. **Frontend is demo-grade, not production-grade** (see task E).

---

## 4. CRITICAL: what is NOT in the git repo

`data/` and `*.db` are gitignored. Therefore **your clone has none of Suhani's results.** Missing from the clone:
- `data/atlas.db` (SQLite: runs, papers, claims, relations, LLM cache, API cache, costs, events) ~76 MB
- `data/qdrant/` (embedded vectors), `data/pdfs/`, `data/runs/<id>/` (including `offline/` snapshots and reports), ~275 MB total
- the three demo runs: `a0e32253-6a67-46e5-9b4e-6273c0aa1673` (IoT safety, 15 papers, has gaps; the run E4/E5/E6 were judged against), `917e7b11-4148-4fdf-9512-2b3361d59ae0` (same query, backup), `42ddbe56-585a-4b2c-8edc-b3f7ba4b4684` (federated learning for medical imaging, 14 papers)
- the Neo4j graph for those runs lives in **Suhani's Neo4j AuraDB Free instance** (cloud), not local.

**Options (ask Suhani which; my recommendation is A then B):**
- **A. Get her `data/` folder** (zip it, ~275 MB; it contains the LLM/API caches so re-running the same queries is nearly free and reproducible) plus AuraDB credentials from her `.env`. Run on SQLite exactly as she did to reproduce the demo state first. Confirms nothing regressed.
- **B. Bring up the full stack** (§5) and generate *fresh* runs there — with real GROBID they will be richer (sections, references, all 5 detectors). Do not try to auto-migrate her SQLite data into Postgres; re-running is cleaner. Cache misses mean real API calls: see the rate-limit warning in §7.

---

## 5. Task A — Environment bring-up (do this first)

**Disk:** ensure **≥ 40 GB free** before anything long-running. (On Suhani's laptop the disk filled to 4.3 GB free partway through an 8-config sweep and silently killed 6 of 8 configs — check free space at the start of any sweep, and after.)

```bash
git clone https://github.com/Suhani-99/ATLAS.git && cd ATLAS
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"                                     # check pyproject.toml for the exact extras
python -m spacy download en_core_web_sm                     # needed by concept extraction
cp .env.example .env                                        # then fill it in — see below
```

**Secrets.** Suhani will hand you API keys **personally**. Put them only in `.env` (gitignored). Needed: `GROQ_API_KEY`, `GEMINI_API_KEY` (+ optional `GEMINI_API_KEY_2` for quota rotation), `SEMANTIC_SCHOLAR_API_KEY` (S2 is nearly unusable without one), optional `NCBI_API_KEY`, `ATLAS_CONTACT_EMAIL` (polite-pool identity for OpenAlex/PubMed/Unpaywall; **use a real address of yours or Suhani's here, in `.env` only**). Never paste keys into chat, commits, issues, or fixtures. (Keys Suhani pasted in an earlier chat should be rotated — remind her.) Neo4j: either her AuraDB creds, or the local container below.

**Full stack (the thing her laptop couldn't do):**
```bash
make up            # docker compose: postgres, neo4j (APOC+GDS), qdrant, grobid — read docker-compose.yml first
make health        # = atlas health ; every service should be OK, grobid included
```
Then in `.env` switch to the compose values (they are listed, commented, in `.env.example`):
`POSTGRES_DSN=postgresql+psycopg://atlas:atlas@localhost:5432/atlas`, `NEO4J_URI=bolt://localhost:7687` (+ `NEO4J_USER/PASSWORD/DATABASE` per compose), `QDRANT_URL=http://localhost:6333`, `GROBID_URL=http://localhost:8070`.
```bash
atlas init-stores                     # alembic upgrade head + Qdrant collections + Neo4j schema
PYTHONPATH=src pytest -q tests/unit                       # expect 136 pass
PYTHONPATH=src pytest -q tests/e2e                        # expect pass (run separately!)
pytest -q -m integration tests/integration                # real Neo4j idempotency test
```
Note `tests/unit/conftest.py` forces SQLite + in-memory Qdrant + no Neo4j, so unit tests do **not** prove Postgres works. You must additionally run a real `atlas run` on Postgres (task B) and fix whatever breaks (raw SQL in `store/db.py` uses `sa.text` in several places — check dialect assumptions; `frontier.updated_at`, JSON columns, UUID handling are the likely spots).

**Ports:** the dashboard defaults to 5173 (Vite) and the API to 8000. `web/vite.config.ts` accepts `ATLAS_WEB_PORT` and `ATLAS_API_URL` if those are busy (Suhani's other project collided with them).

**Embedding model:** first run downloads ~440 MB to the HF cache. If the network is flaky during the demo, set `HF_HUB_OFFLINE=1` after the first download.

---

## 6. Task B — Verify GROBID and the full-text path

1. `atlas ingest --paper-id arxiv:1905.12285` → expect `structure=tei` (not `flat`), sections + references populated, `offsets_ok=True`. Fix `ingest/grobid.py::parse_tei` against real output; keep the PyMuPDF fallback working (GROBID down must still degrade gracefully — the e2e test depends on that).
2. Run `atlas resolve-check --limit 200` (R1 tripwire: target ≥ 35 % full-text reachable; the earlier 60-paper sample gave 75 % but was arXiv-heavy).
3. Run a standard-mode crawl on `iot_safety`, then `atlas concepts --run-id <id>`, `atlas gaps --run-id <id>`, `atlas report --run-id <id>`. **Detectors 3/4/6 should now produce candidates.** If they still find nothing with real sections, debug them (unit tests use synthetic fixtures; live behaviour is unproven). Record the before/after gap counts and full-text ratio — this is a headline improvement for the report (E7's 9.2 % full-text ratio is the "before").
4. Update `docs/DECISIONS.md` ADR-013 with what changed.

---

## 7. Task C — Fix the known weaknesses (§3 items 1–3, 7)

Do these before the big evaluation sweeps so the sweeps measure the improved system; keep the "before" numbers in the report as an honest before/after.

- **Rate limits are the real bottleneck.** Groq free tier caps ~8k tokens/min (claims/judge calls wait ~55 s each); one 3-paper crawl took anywhere from 15 minutes to 5 hours depending on quota. `gemini-2.5-pro` was retired mid-project (synthesis uses `gemini-2.5-flash`). With paid keys or the `cloud`/`hybrid` profile in `config/models.yaml` you can go much faster — **ask Suhani before spending money**; every LLM call is cached and keyed on `(prompt, model, params, prompt_version)`, so changing a prompt version re-spends.
- Optional but valuable: run a **local LLM via Ollama** (`ATLAS_LLM_PROFILE=local`, `OLLAMA_BASE_URL`) so the *chat* also works with the network unplugged. Not required.

---

## 8. Task D — Finish the evaluation (this is the report's results chapter)

Follow `docs/TESTING.md` Part 2 exactly. Queries are frozen in `evaluation/queries.yaml`: (1) `iot_safety` "IoT devices for women safety", (2) `federated_learning_medical` "federated learning for medical imaging", (3) `biomedical` "gut microbiome and depression".

| Item | What to do | Tool |
|---|---|---|
| E1 | For queries 2 and 3 (and re-do 1 on the full stack) | `python evaluation/e1_baseline.py --run-id <id>` |
| E2/E3 | Query 2: re-run the 5 missing configs (`--resume evaluation/e2_e3_federated_learning_medical.json --only -novelty,-contest,-recency,relevance_only` plus `e3:bridge_on`). Query 3: full 8 configs. **Also re-run E2/E3 for query 1 if the scoring/judge changed.** | `python evaluation/e2_e3_ablation.py --query "<q>" --max-papers 15 --out evaluation/e2_e3_<label>.json` |
| Bridge at scale | A **deep-mode** (75 papers) or extra-deep (200) run to finally observe whether bridge promotion fires; run bridge on/off there. If it never fires, diagnose (needs ≥2 Louvain clusters with ≥`min_cluster_size` reads; `config/scoring.yaml` `bridge:`) and say so honestly. A real bridge promotion is the planned demo centrepiece. | `atlas run "<q>" --mode deep` |
| E4 | Sample 50 verified + **20 dropped** claims (the `dropped_claims` table now populates; the earlier sample had none). The exact-substring verification method is in `evaluation/e4_sheet.md`'s header. | `python evaluation/e4_grounding_sample.py --out evaluation/e4_sheet.md` |
| E5 | Get to **≥ 60 pairs, 12 per label**. CONTRADICTS and REPLICATES are rare — pool many runs (`--run-id id1,id2,...`). Report honestly if they stay rare. **The existing `gold` labels were written by Claude, not a human — get Suhani or a domain-familiar person to label/verify.** | `atlas judge-eval --run-id ... --export ...` then `--score` |
| E6 | Top-10 gaps per query, rated plausible/trivial/wrong **blind** by a human (the sheet hides the detector; `e6_key.json` holds the answers). Again: current ratings are Claude's. | `python evaluation/e6_gap_review.py --run-id <id> --out ... --key-out ...` |
| E7 | Cost/time per mode incl. deep and extra-deep. | `python evaluation/e7_cost.py` |
| E8 | Same query twice with a warm cache → identical graph. Re-verify on the new stack (Postgres/Neo4j). | re-run `atlas run` |

**Sweep safety rules (learned the hard way):** the ablation script edits `config/scoring.yaml` per config and restores it in a `finally`; if the process is killed the file stays corrupted. It now refuses to start if `git diff config/scoring.yaml` is dirty. Check `git status` first, keep disk free, run each config in a fresh subprocess (the config loader is `@lru_cache`d), default `--timeout-s 3300` (standard mode's own budget is 2700 s). Failures write `evaluation/_failure_<config>.log`. Delete zombie "running" rows with `atlas clear-run --run-id <id> --yes` (only when nothing is actually running; embedded Qdrant is single-process, so stop the sweep first).

After each result: update the tables in `docs/TESTING.md` and `report/report.md` §4, and re-check that the Abstract/Conclusion still match the numbers.

---

## 9. Task E — Frontend to board-demo quality

Current state (honest): ~1,100 lines; 5 routes (`/` home, `/runs/:id` graph/frontier/timeline + live log, `/runs/:id/paper/:pid`, `/runs/:id/report`, `/runs/:id/chat`); works; used in a real browser by Suhani twice. **Not reviewed visually by the previous session.** Known gaps:
- Graph edges are all one grey colour (CITES only). `docs/API.md` intends **contradictions red / supports green** — requires the graph snapshot to include claim-relation edges, not just paper citations (`store/graph.py::graph_snapshot`) — extend the API/contract and the snapshot too (`store/snapshot.py`).
- No visual moment for `bridge_promoted` ("flash the connector edge — the demo moment").
- Per-refresh full re-layout is slow above a few hundred nodes; implement incremental layout (position only new nodes) or cap/cluster-collapse, keeping the ≤100-node live behaviour (invariant #6: the graph builds live, never batched to the end).
- No loading/empty/error states worth the name, no error boundary, no responsive/projector layout, almost no accessibility, 960 kB unsplit bundle, **zero frontend tests**.
- The dashboard should be servable as a single process for the demo (build `web/`, serve `dist/` from the API) so there is one command to start it.

Do it with a real browser (screenshots at 1920×1080 and a smaller laptop size; walk every route on all three demo runs), then add a small Playwright/Vitest smoke suite. Keep `tsc`, oxlint and `vite build` clean.

---

## 10. Task F — Demo preparation (offline!)

`docs/TESTING.md` "Demo-day preparation": three saved runs, cached end to end, **replayable with the network unplugged — test it literally by disconnecting wifi.**

- Cloud Neo4j was the only cloud dependency for *viewing* a run. **`atlas snapshot --run-id <id>`** (built, tested) saves graph/gaps/report/stats to `data/runs/<id>/offline/`, and the API serves those for any finished run instead of Neo4j/the LLM. A running run always reads live. Re-run it for every demo run **after** any change to gaps/reports/graph, and once more after the frontend/graph-edge work above (snapshots must include the new edge types).
- Simulated-offline check already passed (Neo4j pointed at an unreachable host, every outgoing request forced to fail, all pages < 0.1 s). **The literal wifi-off rehearsal has NOT been done.** Do it, on the demo machine, with the real browser.
- Still needs internet unless you set up a local LLM: a *new* in-scope chat question. The **refusal** of an out-of-scope question works offline (decided by local embeddings). Pre-ask the demo questions online so the LLM cache replays them.
- **Pick runs that show every beat:** (1) live graph build — start a fresh small run for real; (2) a **bridge promotion** if task D finds one, else say plainly it did not fire at this scale; (3) open a claim → highlighted verbatim quote in the source; (4) contradiction report with two quotes side by side — use a *genuine* one after task C, not the NodeMCU false positive; (5) ranked gaps with bounding papers — choose ones you can defend (in the old IoT run the two "plausible" gaps were the ones about accuracy of risk/incident detection); (6) **chat refuses an out-of-corpus question — never skip this**, it is the trust argument for the whole system. Pre-compute the extra-deep run; **never crawl 200 papers live.**
- The demo script skeleton is `report/report.md` Appendix A — update it with the real run IDs and timings. Rehearse it twice with a stopwatch.
- The e2e fixture (`tests/fixtures/e2e/`) was seeded with the placeholder email `atlas-e2e-fixture@example.edu` on purpose. If you re-seed it, keep a placeholder — never bake a real address into committed cache keys.

---

## 11. Task G — Report and slides

- `report/report.md` is complete in structure. Fold in queries 2–3 results, the new-stack before/after numbers, and the fixes from §3. Ask Suhani for the **department's required format/template** (Word/LaTeX/PDF) and convert last. Keep the honest-limitations tone; examiners notice a missing ethics paragraph (already written, §3.4) and reward measured weaknesses.
- **Slides (10–15, ~10–15 min talk):** title → the problem with one-shot retrieval/RAG → the idea (foraging loop) → pipeline diagram → the invariants (verbatim quotes, no gap without citations, refusal) → live demo/screenshots → E1 headline (14 vs ~1 clusters, 40 % overlap) → grounding 98 % → cost ($/run) → honest limitations & what the evaluation found (judge DIFF_SCOPE, gap quality) → what was fixed since → future work → Q&A backup slides (ablation table, R6 stress test, architecture).
- **Prepare answers to likely questions, honestly:** "How is this different from RAG?", "How do you know quotes aren't hallucinated?", "What if the judge is wrong?" (we measured it: 57 %, DIFF_SCOPE weak — and what we did about it), "Why did bridge promotion never fire?", "Cost?", "Why only N papers?", "Is a full-text/GROBID run better?" (task B numbers).

---

## 12. Optional [S] items (ask Suhani first)
Langfuse tracing (env vars in `.env.example`, needs a Langfuse instance/account — could now be a compose service), predicted-links detector 2, GraphML export.

---

## 13. Definition of done (tick every box with evidence)

- [ ] Full stack up; `atlas health` all OK incl. GROBID; unit (136+), e2e and integration tests green on the new stack
- [ ] Real run on Postgres + local Neo4j + GROBID succeeds; detectors 3/4/6 verified live; before/after numbers recorded
- [ ] Judge `DIFF_SCOPE` weakness addressed and re-measured; grounding fuzzy-path fix + regression test; near-duplicate gap dedup
- [ ] E1–E8 complete for **all three queries**; bridge promotion tested at deep scale with an honest result either way
- [ ] E5/E6 verified by a **human**, not just Claude
- [ ] Frontend polished, tested in a real browser at projector resolution, edge colours by relation type, single-command startup
- [ ] Three demo runs re-snapshotted; **literal wifi-off rehearsal passed** twice; at least one genuine contradiction and a defensible gap ready
- [ ] `report/report.md` numbers match `docs/TESTING.md`; converted to the required format
- [ ] Slides + Q&A notes done; ROADMAP/TESTING updated; everything committed (no secrets) and pushed

---

## 14. Gotchas cheat-sheet
- `atlas` CLI: `run`, `show [run_id]`, `concepts`, `gaps`, `report`, `snapshot`, `judge-eval`, `clear-run`, `harvest`, `ingest`, `resolve-check`, `health`, `init-stores`. `make test`, `make test-int`, `make test-offline`, `make lint`.
- Windows console cp1252 vs UTF-8 has bitten this project at ~5 entry points (`atlas/console_encoding.py` fixes CLI + API). If you hit `charmap codec can't encode`, that is the class of bug.
- Paper IDs like `doi:10.1109/x.y` contain `/`; the paper route uses `{paper_id:path}` for that reason.
- `EventSource` treats a server event named `error` specially — the frontend guards it (`web/src/lib/useEvents.ts`).
- Groq gpt-oss models: JSON via `MD_JSON` mode; "IncompleteOutputException" on very long claim outputs is logged and skipped, not fatal.
- Run the API and dashboard with `ATLAS_WEB_PORT` / `ATLAS_API_URL` if 5173/8000 are taken.
- When unsure whether something is a bug or a documented limitation, check `docs/RISKS.md`, `docs/DECISIONS.md`, and the "Discussion and limitations" section of the report before "fixing" it.
