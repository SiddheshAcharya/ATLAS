# ARCHITECTURE

## System shape

ATLAS is a **single-process orchestrator** driving a set of stateless stages against three stores.
It is not a microservice mesh and it is not a multi-agent swarm. The "agentic" property comes from
the closed feedback loop — the frontier queue is re-scored after every paper — not from
autonomous agents negotiating with each other.

```
┌─────────┐   ┌──────────────────────────────────────────┐   ┌─────────────┐
│ Sources │──▶│              Orchestrator                │◀─▶│  Postgres   │  run state, frontier,
│ 4 APIs  │   │  (asyncio, one run = one state machine)  │   │             │  cache, costs
└─────────┘   └──────────────┬───────────────────────────┘   └─────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   ┌─────────┐         ┌──────────┐         ┌──────────┐
   │ GROBID  │         │  Qdrant  │         │  Neo4j   │  papers, claims, concepts,
   │ (PDF→   │         │ (vectors)│         │  (graph) │  relations, gaps
   │  TEI)   │         └──────────┘         └──────────┘
   └─────────┘                                   │
                                                 ▼
                                     FastAPI + SSE ──▶ React dashboard
```

## Stage-by-stage

### 0. Query expansion
**In:** user query string. **Out:** 10–15 keyword strings + optional filters (year range, domain).
One LLM call, structured output. Keywords are stored on the run so the report can show what was
actually searched — a reviewer will ask.

*Design note:* generate keywords in three tiers — exact-phrase (`"IoT women safety device"`),
concept-broad (`wearable panic alert`), and adjacent-field (`personal safety telemetry`). Tier
matters: tier-3 keywords are the ones that surface bridge papers, and they must not be dropped
just because they return fewer hits.

### 1. Harvest
**In:** keywords. **Out:** ~300–800 deduplicated `PaperMeta` records.

Four sources, queried in parallel, each behind the `Source` protocol in `sources/base.py`:

| Source | Role | Notes |
|---|---|---|
| **OpenAlex** | primary metadata + citation graph | no key, 100k/day, 10 rps, `mailto` for polite pool. Abstracts arrive as an inverted index — reconstruct. |
| **arXiv** | preprints + guaranteed PDFs | Atom XML, be polite (~1 req / 3 s). Best full-text yield of the four. |
| **PubMed E-utilities** | biomedical coverage | only matters if the query is biomedical; keep it, it costs nothing to include and the diagram promises it. |
| **Semantic Scholar** | enrichment: TLDRs, influential-citation flags, `openAccessPdf` | tight limits (shared 100 req/5 min unauthenticated; an API key starts at ~1 rps). **Do not** use as the primary citation-graph walker. |

The diagram says "500 papers combined". Realistically expect heavy overlap. Dedup by canonical ID
(`ids.py`) *before* counting, or the frontier will read the same paper four times.

### 2. Seed ranking
Embed `title + "\n" + abstract` for every candidate. Embed the user query. Cosine rank. Take top
K (default 20) into the frontier as seeds. This first pass uses **relevance only** — the other
scoring components (PageRank, novelty, contest) are meaningless before the graph exists.

### 3. The foraging loop  ← *the core of the project*

```
while not stop():
    paper = frontier.pop_highest()
    doc   = ingest(paper)              # PDF → GROBID → sections → chunks → Qdrant
    claims = extract_claims(doc)       # verbatim quote + scope, per section
    claims = grounding_gate(claims)    # character-exact verification; drops failures
    edges  = judge(claims)             # vs. kNN-neighbouring existing claims
    graph.write(paper, claims, edges)  # incremental, streamed to UI
    neighbours = expand(paper)         # references + citers from OpenAlex
    frontier.push_scored(neighbours)   # cosine gates into read / parked / dropped
    frontier.rescore_if_dirty()        # PageRank every K papers, novelty always
```

Each sub-step is documented where it belongs: scoring and stopping in `SCORING.md`, claim
extraction and the grounding gate in `CONTRACTS.md` §Claim, the store writes in `DATA_MODEL.md`.

**Three-band admission** (from the diagram, kept exactly):
- `sim < 0.20` — dropped, not tracked.
- `0.20 ≤ sim < 0.35` — **parked pool**. Not read now, not thrown away.
- `sim ≥ 0.35` — scored and queued normally.

**Bridge promotion:** a parked paper is promoted to the frontier when its citations reach into
≥2 distinct clusters that ATLAS is actively building. Clusters come from Louvain community
detection on the citation graph, recomputed with PageRank. This is the single most novel
mechanism in the design and it deserves its own slide in the viva — it is how ATLAS finds
connector papers that pure similarity ranking structurally cannot.

**Failure paths that must not stop the loop:** no PDF (→ abstract-only depth), GROBID timeout
(→ PyMuPDF fallback), source 429 (→ backoff and requeue), LLM schema violation (→ one retry, then
mark paper `partial` and continue).

### 4. Gap discovery
Six independent detectors over the finished graph, fused into one ranked list. Full specification
in `GAP_DETECTORS.md`. The hard rule from the diagram — *a gap with no citation is not shown* —
is enforced in fusion, after ranking, as a filter.

### 5. Synthesis
One pass. The LLM receives a **serialized graph summary** (not raw chunks): agreement clusters,
contradiction edges with both quotes, the ranked gap list with bounding papers, and a
method/dataset timeline table. It writes four sections:
1. Agreement Summary — with citations
2. Contradiction Report — which papers conflict and why
3. Ranked Gap List — each gap citing its bounding papers
4. Methodology Timeline — how methods and datasets shifted over time

*Design note:* build the serialization deterministically in Python. If the graph summary exceeds
the context window, drop by rank (lowest-PageRank papers first) and record what was dropped in
the report's appendix. Never silently truncate.

### 6. Serving
FastAPI + SSE streams graph mutations to a React dashboard during the run. After the run, the
dashboard shows the graph, the four reports, and a chat interface. **Chat is retrieval-restricted
to this run's Qdrant collection and Neo4j subgraph** — that restriction is the honesty guarantee
and must be enforced server-side, not by prompt instruction.

## Why this shape

- **One process, not a queue-worker fleet.** The loop is inherently sequential — paper N+1 is
  chosen because of what paper N contained. Parallelism belongs *inside* a step (fetch 40
  references concurrently), not across loop iterations. A Celery/Redis fan-out would add
  operational surface for no throughput gain.
- **Postgres as the frontier**, not Redis. The frontier needs `ORDER BY score`, partial updates,
  crash recovery, and post-hoc inspection ("why did it read that paper 12th?"). That is a table.
- **Three stores, each doing one thing.** Qdrant answers "what text is similar", Neo4j answers
  "what connects to what", Postgres answers "what happened in this run". Trying to make one store
  do all three is the classic version of this project that collapses in week 9.
- **LangGraph is optional, not load-bearing.** See ADR-002.

## Data flow contract in one line

`str → [PaperMeta] → ScoredPaper → ParsedDoc → [Chunk] → [Claim] → [Relation] → Graph → [Gap] → Report`

Each arrow is a typed function in `contracts.py`. If you cannot express your change as one of
these arrows, it probably belongs in a different stage.
