# API

FastAPI, all routes under `/api/v1`. Response bodies are the Pydantic models from
`CONTRACTS.md` — never ad-hoc dicts.

## REST

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/runs` | start a run. Body: `{query, mode, config_overrides?}`. Returns `{run_id}` immediately; the loop runs in a background task. |
| `GET` | `/runs` | list runs with status and stats |
| `GET` | `/runs/{run_id}` | run detail: `RunStats`, keywords, stop reason |
| `POST` | `/runs/{run_id}/stop` | graceful stop — finishes the current paper, then runs gaps + synthesis on what exists |
| `GET` | `/runs/{run_id}/papers/{paper_id}/source` | the normalized text ATLAS read for that paper (rebuilt from stored chunks, else the normalized abstract) — claim quote offsets index it; `origin` says which copy |
| `GET` | `/runs/{run_id}/graph` | full graph snapshot as `{nodes[], edges[]}` in Cytoscape element format. Nodes: the run's papers (`read_order` from this run's own READ edge, null if unread). Edges carry `type`: `CITES`, or a claim relation (`SUPPORTS`/`CONTRADICTS`/`EXTENDS`/`REPLICATES`/`DIFF_SCOPE`) rolled up to the paper pair with `count` and max `confidence` |
| `GET` | `/runs/{run_id}/frontier` | frontier table with score breakdowns, sortable. **This is the "why did it read that?" view — build it early, it is the best debugging tool in the project.** |
| `GET` | `/runs/{run_id}/timeline` | one `TimelinePoint` per paper read, in order — new_info/EMA (the stopping criterion's own saturation signal), cumulative claims, cumulative cost. [S] stretch item, backs the dashboard's saturation/cost chart. Built from the `saturation` event each read already emits, not a separate write path. |
| `GET` | `/runs/{run_id}/papers/{paper_id}` | paper detail: metadata, claims with quotes and offsets, relations |
| `GET` | `/runs/{run_id}/gaps` | ranked gaps with bounding papers |
| `GET` | `/runs/{run_id}/report` | the four-section `Report` |
| `GET` | `/runs/{run_id}/report.md` | the report as downloadable Markdown |
| `POST` | `/runs/{run_id}/chat` | grounded Q&A. Body `{message, history[]}`. Returns `{answer, citations[]}`. |
| `GET` | `/runs/{run_id}/events` | **SSE stream** (see below) |
| `GET` | `/health` | per-dependency health: postgres, neo4j, qdrant, grobid, llm |

## SSE event contract

`GET /runs/{run_id}/events?since_seq=<n>` — `since_seq` replays from the `events` table so a
browser refresh mid-run catches up rather than showing a half-built graph.

Every event: `{seq, type, at, payload}`.

| `type` | payload | UI does |
|---|---|---|
| `run_started` | `{query, mode, keywords}` | header + status |
| `harvest_done` | `{n_candidates, per_source}` | toast |
| `paper_selected` | `{paper_id, title, score_breakdown, read_order}` | highlight next node, show score bar |
| `paper_ingested` | `{paper_id, depth, structure, n_sections, n_chunks}` | node turns solid |
| `claims_extracted` | `{paper_id, n_kept, n_dropped}` | claim counter |
| `relation_judged` | `{source, target, type, confidence}` | colour the edge; contradictions in red |
| `bridge_promoted` | `{paper_id, clusters:[a,b]}` | **flash the connector edge** — the demo moment |
| `pagerank_updated` | `{top:[{paper_id, pagerank}]}` | resize nodes |
| `frontier_updated` | `{<state>: count, ...}` | queue widget |
| `saturation` | `{step, new_info, ema, ...}` | saturation sparkline |
| `gap_found` | `{gap_id, type, statement, rank}` | gap panel |
| `report_ready` | `{run_id}` | switch to report tab |
| `error` | `{stage, message, paper_id?}` | non-fatal error toast |
| `run_finished` | `{stats, stop_reason}` | the *loop* is done — gap_found/report_ready may still follow |
| `pipeline_finished` | `{}` | **the stream-closing signal** — emitted once, always last (api/tasks.py) |

`node_added`/`edge_added` (per-element Cytoscape streaming) are not implemented — a [D]
scope cut for Phase 6. The frontend re-fetches `GET /runs/{id}/graph` instead (e.g. on
`paper_ingested`); simpler and lower-risk than patching a live Cytoscape instance
incrementally, at the cost of a full snapshot re-render per refetch.

Emit an event and persist it in the same transaction, so replay and live stream never diverge.

## Grounded chat

The one endpoint where scope creep is most tempting and most damaging. Rules:

1. Retrieval is **hard-filtered** to `run_id` in both Qdrant and Neo4j. Server-side. Not a prompt
   instruction — a query filter.
2. The prompt receives only retrieved chunks with their `paper_id`s, plus relevant graph facts.
3. Every answer sentence carries at least one `paper_id`, returned in `citations[]` and rendered
   as a clickable chip that opens the paper's exact quote span.
4. If retrieval returns nothing above threshold, the answer is *"ATLAS did not read anything that
   addresses this."* Do not fall back to the model's own knowledge. Test this with a deliberately
   out-of-scope question — it belongs in the demo.

## Frontend routes (`web/`)

| Route | Contents |
|---|---|
| `/` | new-run form (query, mode) + run history |
| `/runs/:id` | live view — Cytoscape graph, frontier queue table, live log, saturation chart |
| `/runs/:id/paper/:pid` | paper detail with claims and highlighted quote spans |
| `/runs/:id/report` | four report sections + ranked gaps |
| `/runs/:id/chat` | grounded chat with citation chips |

Graph rendering notes: `fcose` layout, node size ∝ PageRank, node colour = Louvain cluster,
edge colour by relation type (contradictions red, supports green). Above ~800 nodes, stop
re-running layout on every add — batch layout every 25 additions or the browser stutters during
the extra-deep demo.


**Offline snapshots.** For a finished run with a saved snapshot (`atlas snapshot`), `/graph`, `/gaps`, `/report`, `/report.md` and the `stats` in `/runs/{id}` are served from `data/runs/<id>/offline/` instead of Neo4j/the LLM. A run that is still running always reads live.
