# GAP DETECTORS

Six independent detectors run over the finished graph, then fuse into one ranked list. Each
detector is a module in `gaps/detectors/` implementing:

```python
def detect(run_id: str, graph: GraphStore, cfg: DetectorConfig) -> list[GapCandidate]: ...
```

A `GapCandidate` **must** carry `bounding_papers: list[PaperRef]` with at least one entry.
Detectors that cannot name their evidence return nothing. This is enforced again in fusion, but
enforce it here too — failing loudly at the source is easier to debug.

---

## 1. Unlinked concepts (Swanson ABC)

**Idea.** Concept A co-occurs with B; B co-occurs with C; A and C never co-occur. Classic
literature-based discovery — Swanson's fish-oil/Raynaud's finding.

**Method.**
1. Build a concept co-occurrence graph from `(:Paper)-[:MENTIONS]->(:Concept)`.
2. Weight edges by **PMI**, not raw count: `pmi(a,b) = log( p(a,b) / (p(a)·p(b)) )`.
3. Find A–B–C paths where `pmi(A,B) > τ`, `pmi(B,C) > τ`, and A–C co-occurrence count is 0.
4. Require ≥ `min_support: 2` distinct papers on each leg, and A, C in different Louvain
   communities of the concept graph (same-community pairs are usually trivially unlinked).

**Score.** `min(pmi(A,B), pmi(B,C)) · log(1 + support_AB + support_BC)`, normalized.

**Bounding papers.** The A–B papers and the B–C papers.

**Statement template.** *"{A} and {C} are both linked to {B} ({n} and {m} papers respectively) but
no paper in this corpus connects {A} to {C} directly."*

**Guard.** Concept normalization is everything here. Without it "IoT device" and "IoT devices"
become different concepts and the detector produces noise. Normalize by lowercase → lemmatize →
embed → cluster at cosine 0.85 → canonical label = most frequent surface form.

---

## 2. Predicted links

**Idea.** The graph's own structure implies a connection that does not exist yet.

**Method.** Adamic-Adar (and optionally node2vec + logistic regression as a stretch) over the
concept co-occurrence graph. Rank non-existent edges by predicted score. Take the top N where
neither endpoint is a hub (degree > 90th percentile — hubs predict links with everything and the
result is uninformative).

```cypher
CALL gds.alpha.linkprediction.adamicAdar(a, b) YIELD score
```
or compute with NetworkX if GDS's function is awkward — the graph is small.

**Score.** Normalized Adamic-Adar, penalized by endpoint degree.

**Bounding papers.** Papers mentioning each endpoint, top 3 by PageRank.

**Overlap with detector 1** is real and expected. Fusion handles it (see §Deduplication).

---

## 3. Empty combinations

**Idea.** An untried method × dataset pairing.

**Method.**
1. Build the Method × Dataset matrix from `USES_METHOD` and `EVALUATED_ON`.
2. Keep methods with `min_method_papers: 3` and datasets with `min_dataset_papers: 3` — this
   avoids the trivially-empty cells that make the matrix mostly zeros.
3. Empty cells are candidates.
4. Optional strengthening: require the method to have been applied to a dataset *similar* to the
   target (cosine of dataset-description embeddings > 0.5), so the combination is plausible rather
   than nonsensical.

**Score.** `min(method_frequency, dataset_frequency)` normalized × plausibility.

**Bounding papers.** Top papers for the method and top papers for the dataset.

**Statement template.** *"{Method} has been evaluated on {k} datasets and {Dataset} has been used
by {m} papers, but no paper in this corpus evaluates {Method} on {Dataset}."*

**Note for non-benchmark fields.** For a query like IoT women-safety devices, "dataset" is often
"deployment setting" or "sensor configuration". Keep the `Dataset` label but allow the extraction
prompt to fill it with evaluation context. Say so explicitly in the report.

---

## 4. Unanswered calls

**Idea.** A paper's "future work" that nobody followed up on.

**Method.**
1. Extract future-work sentences from GROBID's conclusion/future-work sections (`full_text` papers
   only — ADR-010).
2. Embed each call.
3. Search `atlas_claims` for claims from papers published **after** the calling paper.
4. A call is **answered** if any later claim has cosine ≥ `answered_threshold: 0.62` **and** its
   paper cites the calling paper, or cosine ≥ 0.75 regardless of citation.
5. Everything else is unanswered. Require `min_age_years: 2` — nobody has answered a call from
   six months ago, and reporting that as a gap is noise.

**Score.** `citation_count(calling_paper)_normalized × age_factor × (1 − best_match_similarity)`.
A widely-cited paper's unanswered call is a stronger gap than an obscure one's.

**Bounding papers.** The calling paper (role `a_side`), plus the nearest non-answering later
papers (role `evidence`).

---

## 5. Unresolved conflicts

**Idea.** Two papers disagree and nothing since has settled it.

**Method.**
1. Take every `CONTRADICTS` edge between claims of papers P₁ and P₂.
2. Let `y = max(year(P₁), year(P₂))`.
3. Search for a resolver: a paper with year > y that cites **both** P₁ and P₂, or that makes a
   claim `SUPPORTS`-linked to one side with `DIFF_SCOPE` to the other.
4. No resolver → unresolved. Mark the `CONTRADICTS` edge `resolved: false`.

**Score.** `contradiction_confidence × mean_pagerank(P₁,P₂) × years_open_normalized`.

**Bounding papers.** P₁ (`a_side`), P₂ (`b_side`), any partial resolvers (`evidence`).

**Statement template.** *"{P₁} ({y₁}) reports {claim₁}; {P₂} ({y₂}) reports {claim₂}. No
subsequent paper in this corpus cites both or resolves the disagreement."*

This is the detector most dependent on judge quality. If Job C over-labels `CONTRADICTS`, this
list fills with false conflicts — measure judge precision on a hand-labelled set (see
`TESTING.md`) before trusting it.

---

## 6. Shared weaknesses

**Idea.** The same limitation recurring across many papers is a field-level gap.

**Method.**
1. Extract limitation sentences from limitations/discussion sections (`full_text` only).
2. Embed, cluster with HDBSCAN (`min_cluster_size: 3`).
3. Keep clusters spanning ≥ `min_papers: 4` papers from ≥ `min_author_groups: 3` distinct
   first-author groups — otherwise it is one lab repeating itself, not a field-level weakness.
4. Label each cluster with an LLM given the cluster's member sentences (one call per cluster).

**Score.** `n_papers_normalized × author_diversity × mean_pagerank`.

**Bounding papers.** Every paper in the cluster (cap the displayed list at 8, keep all in data).

---

## Fusion (`gaps/fusion.py`)

1. **Normalize** each detector's scores to `[0,1]` with min-max *within that detector*. Raw scores
   are not comparable across detectors.
2. **Deduplicate.** Two candidates merge if their statement embeddings are ≥ 0.85 similar or their
   bounding-paper sets overlap by Jaccard ≥ 0.6. A merged gap keeps the union of bounding papers
   and records which detectors found it.
3. **Fuse** with weighted Reciprocal Rank Fusion:
   ```
   GapScore(g) = Σ_d  w_d / (k + rank_d(g))        # k = 60
   ```
   Then apply a **corroboration bonus**: `× (1 + 0.15·(n_detectors − 1))`. A gap found by three
   detectors is much more likely real than one found by one.

   ```yaml
   detector_weights:
     unlinked_concepts:   1.0
     predicted_links:     0.7    # structural, weakest standalone evidence
     empty_combinations:  0.9
     unanswered_calls:    1.1    # explicit textual evidence
     unresolved_conflicts: 1.2   # strongest — the field itself flagged the tension
     shared_weaknesses:   1.0
   ```
4. **Citation rule (hard filter, from the design).** Drop any gap with zero bounding papers, or
   whose bounding papers are all `metadata_only`. A gap ATLAS cannot show you the evidence for is
   not shown. Log the drop count.
5. **Cap** at `max_gaps: 15` for the report; keep the full list in the graph and the API.

## Output

Each surviving gap becomes a `(:Gap)` node with `BOUNDED_BY` edges, and enters synthesis as a
structured record — never as free text. The synthesis LLM rewrites the statement for readability
but **cannot** add or remove bounding papers.
