# SCORING, THE PARKED POOL, AND STOPPING

Everything here is configured in `config/scoring.yaml` and implemented in `forage/scoring.py`,
`forage/frontier.py`, `forage/stopping.py`. Weights are **not** hardcoded — the ablation study in
`TESTING.md` §Evaluation depends on being able to zero any component from config.

---

## 1. Frontier score

```
score(p) = w_rel·Relevance(p)
         + w_pr ·PageRank(p)
         + w_nov·Novelty(p)
         + w_con·Contest(p)
         + w_rec·Recency(p)
```

Every component is normalized to `[0, 1]`. Defaults:

```yaml
weights:
  relevance: 0.35
  pagerank:  0.20
  novelty:   0.15
  contest:   0.15
  recency:   0.15    # sums to 1.0
```

### Relevance
`cosine(embed(query), embed(title + "\n" + abstract))`, min-max normalized **across the current
frontier**, not globally — absolute cosine values compress into a narrow band and destroy
ranking resolution. Recompute only when a paper's abstract first arrives.

### PageRank
`gds.pageRank` over the run's `CITES` subgraph, normalized by the run's max. Unread papers with no
edges yet score 0 — correct, since we know nothing about their standing.

**Recompute cadence:** every `pagerank_every_n: 10` papers, or immediately when the frontier has
fewer than 5 candidates above the read threshold. Set a `graph_dirty` flag on every citation write
and check it in the loop; do not project the graph every iteration.

### Novelty
`1 − max cosine(p, r)` over all already-read papers `r`. Pushes the loop away from a cluster it
has already saturated. This is what stops ATLAS reading fifteen near-identical GSM-panic-button
papers.

Cheap implementation: one Qdrant query against `atlas_abstracts` filtered to `state='read'`, take
the top hit's score.

### Contest
How much live disagreement the paper touches.

- **Read papers:** `contradiction_edges(p) / max(1, total_judged_edges(p))`.
- **Unread papers:** inherit — the mean Contest of read papers within one `CITES` hop. No
  neighbours yet → 0.

Rationale: a paper sitting on top of an unresolved conflict is worth reading next, because
resolving conflicts is directly what detector 5 needs.

### Recency
`exp(−ln2 · age_years / half_life)`, `half_life: 4.0` by default. Configurable per domain — set
it to 8 for a slow-moving field, 2 for something like LLM security. Papers with no year get the
median year of the frontier and a `year_imputed` flag.

---

## 2. Admission bands (from the design diagram, preserved exactly)

Applied to a newly discovered paper's cosine similarity to the query:

| Band | Action |
|---|---|
| `sim < 0.20` | **Dropped.** Not stored, not tracked. |
| `0.20 ≤ sim < 0.35` | **Parked pool.** `state='parked'`. Kept, not read. |
| `sim ≥ 0.35` | Scored with the full formula, queued as `pending`. |

Thresholds are `drop_below: 0.20`, `park_below: 0.35` in config. Tune them once on a pilot query
and record the tuning in the report — arbitrary-looking constants get challenged in vivas.

---

## 3. Bridge promotion (the connector-paper mechanism)

A parked paper is promoted to `pending` when **both** hold:

1. Its references/citers touch **≥ 2 distinct Louvain clusters** that the run is actively
   building, where "actively building" means a cluster containing ≥ `min_cluster_size: 3` read
   papers.
2. It has `min_bridge_links: 2` or more such links per side (≥1 into each of two clusters, ≥2
   total).

On promotion: set `discovered_via='bridge'`, apply `bridge_bonus: 0.15` additive on the final
score, and emit a `bridge_promoted` SSE event so the UI can flash the edge. **Log every promotion
with the two cluster IDs** — this is the demo moment and the figure for the report.

Evaluate promotions after each PageRank/Louvain recompute, not every iteration.

Cap: `max_bridge_promotions_per_run: 15`, so a noisy parked pool cannot hijack the reading budget.

---

## 4. Stopping criteria

The loop stops when **any** fires. `stop_reason` is recorded on the run and shown in the report.

### a. Budget reached
```yaml
modes:
  standard:   {papers: 25,  max_usd: 3.0,  max_minutes: 25}
  deep:       {papers: 75,  max_usd: 10.0, max_minutes: 75}
  extra_deep: {papers: 200, max_usd: 30.0, max_minutes: 240}
```

### b. New-information saturation
Per paper, compute:

```
new_info(t) = new_claims(t) + 2·new_contradictions(t) + 3·new_concepts(t)
ema(t)      = α·new_info(t) + (1−α)·ema(t−1)          # α = 0.3
```

Stop when `ema(t) < saturation_ratio · max(ema)` for `saturation_patience: 3` consecutive papers,
with `saturation_ratio: 0.15`, and only after a floor of `min_papers: 10`.

The weights (1 / 2 / 3) encode that a new *concept* is worth more than a new *claim*, and a new
contradiction sits between them. Plot `ema(t)` per run — the saturation curve is one of the best
figures the project can produce and directly evidences that the loop terminates sensibly rather
than arbitrarily.

### c. Frontier exhausted
No `pending` paper above `read_below_score: 0.25`. Before stopping, sweep the parked pool once for
bridge candidates.

### d. Hard failure
Three consecutive papers fail ingestion → pause and surface an error. Usually a dead GROBID
container or an exhausted API key, not a data problem.

---

## 5. Re-ranking cadence summary

| Component | Recomputed |
|---|---|
| Relevance | once, on discovery |
| Recency | once, on discovery |
| Novelty | every iteration (cheap — one filtered Qdrant query) |
| Contest | every iteration for 1-hop neighbours of the paper just read |
| PageRank + Louvain | every `pagerank_every_n` papers, or when `graph_dirty` and frontier is thin |
| Bridge sweep | after every PageRank/Louvain recompute |

---

## 6. `config/scoring.yaml` (starting values)

```yaml
weights:      {relevance: 0.35, pagerank: 0.20, novelty: 0.15, contest: 0.15, recency: 0.15}
bands:        {drop_below: 0.20, park_below: 0.35}
recency:      {half_life_years: 4.0}
pagerank:     {every_n_papers: 10, damping: 0.85}
bridge:       {min_clusters: 2, min_cluster_size: 3, min_bridge_links: 2,
               bonus: 0.15, max_promotions_per_run: 15}
stopping:     {min_papers: 10, alpha: 0.3, saturation_ratio: 0.15,
               saturation_patience: 3, read_below_score: 0.25}
expansion:    {max_references_per_paper: 60, max_citers_per_paper: 60,
               citer_sort: cited_by_count_desc}
modes:
  standard:   {papers: 25,  max_usd: 3.0,  max_minutes: 25}
  deep:       {papers: 75,  max_usd: 10.0, max_minutes: 75}
  extra_deep: {papers: 200, max_usd: 30.0, max_minutes: 240}
```

Every value in this file is an experiment knob. The evaluation chapter is essentially a table of
what happens when you change them.
