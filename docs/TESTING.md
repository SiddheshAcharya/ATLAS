# TESTING & EVALUATION

Two different things, both required. Tests prove the code works. Evaluation proves the *design*
works — that is what earns marks.

---

## Part 1 — Tests

```
tests/
├── unit/           no network, no docker. Runs in <30s. `make test`
├── integration/    testcontainers: postgres, neo4j, qdrant. `make test-int`
├── e2e/            one tiny full run over 5 fixture papers, fully cached LLM responses
└── fixtures/
    ├── api/        REAL captured responses: openalex_*.json, arxiv_*.xml, pubmed_*.xml, s2_*.json
    ├── pdfs/       3 real OA PDFs (clean, two-column, and one nasty scan)
    ├── tei/        GROBID output for each
    └── llm/        recorded LLM responses keyed by prompt hash
```

**Rule: no live network in `tests/unit`.** Mock HTTP with `respx`. Fixtures are real captured
responses — never hand-written JSON that "looks about right", because the bugs you need to catch
live in the shapes real APIs actually return.

### The tests that actually matter

All 11 exist as of Phase 7 (an audit — TESTING.md previously listed these aspirationally,
without checking). Names below are the actual test function, not always identical to the
original name in this table; each was checked to genuinely exercise the described behavior,
not just share a name with it.

| Test | Why | Where |
|---|---|---|
| `test_ids_canonical` — same paper from 4 sources → 1 ID | dedup failure corrupts everything downstream | `test_invariants.py::test_same_paper_from_four_sources_collapses_to_one_id` |
| `test_normalize_idempotent` | offsets break silently if it isn't | `test_invariants.py::test_normalize_is_idempotent` |
| `test_grounding_rejects_paraphrase` | give it a near-miss quote; it must fail. **This is the project's integrity test.** | `test_invariants.py::test_paraphrase_is_rejected` |
| `test_grounding_accepts_ligature_variant` | `ﬁnding` vs `finding` must still verify | `test_invariants.py::test_ligature_variant_still_verifies` |
| `test_offsets_roundtrip` | `text[start:end] == quote` for every verified claim | `test_invariants.py::test_exact_quote_verifies_and_offsets_round_trip` + `test_ingest.py` |
| `test_graph_write_idempotent` | write the same paper twice → node/edge counts unchanged | `tests/integration/test_graph_idempotent.py` (needs real Neo4j — `make test-int`, skipped otherwise) |
| `test_gap_without_citation_dropped` | the hard rule, in code | `test_invariants.py::test_gap_without_bounding_papers_cannot_be_constructed` |
| `test_frontier_ordering` | known scores → known pop order | `test_frontier.py::test_pop_order_follows_score_desc` |
| `test_stopping_saturation` | synthetic new_info series → stops at the expected step | `test_stopping.py::test_saturation_fires_after_patience_below_ratio_and_min_papers` |
| `test_chat_out_of_scope_refuses` | ask something the corpus can't answer; must decline, not invent | `test_api.py::test_chat_refuses_when_corpus_has_content_but_it_is_irrelevant` (the empty-corpus case alone was too weak — the real claim in the store, real embeddings, genuinely-low cosine version) |
| `test_abstract_only_path` | a paper with no PDF completes the loop without raising | `test_loop_smoke.py::test_abstract_only_paper_completes_the_loop_without_raising` (runs the actual loop, not just doc construction) |

Target: cover the invariants, not a coverage percentage. ~60% line coverage concentrated on
`ids`, `normalize`, `grounding`, `scoring`, `fusion` beats 90% spread thin.

### Frontend (added 2026-09-29)
`web/tests/smoke.spec.ts` (Playwright, headless Chromium) walks the demo arc against a real
running server (`atlas serve`, which also serves `web/dist`) and a real finished run
(default the IoT demo run `a0e32253-6a67-46e5-9b4e-6273c0aa1673`, override with
`ATLAS_SMOKE_RUN_ID`): home lists the demo runs; the run view draws the graph with its legend,
unclipped stats and the replayed event log; the report cites by number with a references list
and no raw ids; clicking a claim highlights a span in the source text that reads exactly like
its quote; the chat refuses an off-corpus question. Every test also fails on any page or
console error. Run: `cd web && npm run test:smoke` (5/5, three consecutive runs, 2026-09-29).
`web/scripts/screenshots.mjs <run_id>` saves every route at 1920×1080 and 1366×768 for a
visual check.

Writing these surfaced real bugs, all fixed: the demo runs had dropped off the home page (run
list capped at 15); two overlapping requests collided on embedded Qdrant's file lock (HTTP
500), fixed by one shared, locked client per process (also ~30× faster per request); old runs'
event logs were empty (legacy `paper_read` event name never subscribed to); the page height was
a guessed `calc(100vh-6.5rem)` that clipped the stats bar; the graph labelled every node; the
report footer printed the full-text ratio as 0%.

### CI
GitHub Actions: ruff → mypy → unit tests on every push. Integration on PRs to `main`.

---

## Part 2 — Evaluation (this is the report's results chapter)

Pick **three queries** in different shapes and freeze them in `evaluation/queries.yaml`:
1. Your engineering query (IoT women safety) — sparse, applied, mixed venue quality
2. A well-studied CS topic (e.g. federated learning for medical imaging) — dense, citation-rich
3. A biomedical query — exercises PubMed and full-text availability

### E1 — Does the loop beat one-shot retrieval? *(the central claim)*

> **[RE-RUN 2026-09-29 — supersedes the text below]** On the repaired store (ADR-015), with
> breadth measured the same way for both sets (one OpenAlex citation graph over both, Louvain
> seed 42, a size-matched baseline):
>
> | Run | Overlap | Clusters ATLAS / baseline same size | References reached ATLAS / baseline |
> |---|---|---|---|
> | `8d78fb54` IoT, 15 | 53% | 8 / 9 | 115 / 92 |
> | `a0e32253` IoT, 15 | 40% | 9 / 9 | 147 / 92 |
> | `42ddbe56` federated learning, 14 | 36% | 10 / 8 | 355 / 332 |
> | `b0e7e2c2` federated learning, 13 (GROBID, 2026-09-29) | 38.5% | 11 / 9 | 452 / 332 |
> | `4c1f35f3` gut microbiome & depression, 9 (GROBID, 2026-09-30) | 56% (5/9) | 7 / 8 | 381 / 365 |
>
> The loop reads a different set (36–56% overlap) and reaches further into the reference network
> (4–60% more references), but is **not** measurably broader in cluster coverage at 9–15 papers. The "14 clusters vs ~1"
> below compared citation clusters (from shared Paper nodes, ADR-017) with embedding clusters —
> two different metrics — and is withdrawn. `biomedical` still needs a run.
Baseline: harvest 500 papers, embed, take top 25 by cosine, summarize. That is the naive system.
ATLAS: same query, standard mode, 25 papers.

Compare:
- overlap of the two 25-paper sets (expect 40–60%; if it's 95%, the loop isn't doing anything)
- mean citation count and mean PageRank of the papers read
- number of distinct Louvain clusters covered ← **the key metric: does foraging find breadth that
  cosine ranking misses?**
- contradictions surfaced
- gaps found

**Tooling: `evaluation/e1_baseline.py --run-id <id>`.** Already run once against the
`iot_safety` query (`a0e32253-...`, 15 papers): overlap 40% (right at the low end of the
predicted 40–60% band), 14 distinct Louvain clusters covered by ATLAS vs. essentially
none for the baseline (the script's own embedding-diversity metric collapses to ~1 for
*both* sets — that's expected, not a bug, see the script's in-output caveat: everything
retrieved is topically similar by construction, so abstract-embedding "diversity" answers
a different question than citation-graph breadth). Real, striking evidence for the
central claim on one query; the other two queries in `queries.yaml` still need a run. *(Superseded: all three
queries now have like-for-like runs — see the corrected table above.)*

### E2 — Ablation of the scoring components
Run standard mode with each weight zeroed in turn. Report changes in cluster coverage, novelty of
read papers, and gap count. Requires that weights come from config — which is why they do.

| Config | Papers read | Clusters covered | Contradictions | Relations judged |
|---|---|---|---|---|
| full | 15 | 13 | 1 | 132 |
| −pagerank | 15 | 12 | 1 | 120 |
| −novelty | 15 | 13 | 1 | 156 |
| −contest | 15 | 13 | 1 | 120 |
| −recency | 15 | 10 | 0 | 84 |
| relevance only (= baseline) | 15 | 10 | 0 | 84 |

**Status: done for 1 of 3 queries** (`iot_safety`, 15-paper cap — see `report/report.md`
§4.2 for the full write-up and harness: `evaluation/e2_e3_ablation.py`). Headline finding:
removing recency alone costs as much cluster coverage as removing pagerank+novelty+
contest+recency together — on this query, recency is carrying most of the non-relevance
signal. `-recency` and `relevance_only` landed on identical aggregate numbers from
genuinely different paper sets (checked directly, not assumed) — a real coincidence worth
noting, not a bug.

**Query 2 (`federated_learning_medical`) sweep attempted, mostly failed — not a config
bug.** The laptop's C: drive was at 4.3GB free (99% full, from something unrelated to
this project) partway through the 8-config sweep; every config from that point on either
crashed after partial work or wrote zero data before dying. Only `-pagerank` and
`bridge_off` (E3, below) produced real results:

| Config | Papers read | Clusters covered | Contradictions | Relations judged |
|---|---|---|---|---|
| full | — | — | — | — (timed out at 3300s, unrelated to the disk issue) |
| −pagerank | 13 | 12 | 0 | 71 |
| −novelty | — | — | — | crashed after 2 papers (disk) |
| −contest | — | — | — | crashed after 1 paper (disk) |
| −recency | — | — | — | crashed instantly, 0 data written (disk) |
| relevance only | — | — | — | crashed instantly, 0 data written (disk) |

The sweep script's own failure-reporting had a bug too (a Windows console-encoding crash
that swallowed the real error behind a `charmap` codec message) — fixed, failures now
write a full log to `evaluation/_failure_<config>.log` instead. **[PENDING]**: re-run the
5 missing query-2 configs once there's real disk headroom (`--resume
evaluation/e2_e3_federated_learning_medical.json --only -novelty,-contest,-recency,
relevance_only`), plus the full sweep for query 3.

### E3 — Bridge promotion value
Run with `bridge.enabled: false` vs `true`. Report how many promotions fired, and whether the
promoted papers connected clusters that otherwise stayed disconnected. If a bridge paper turns
out to be genuinely important, that single example is worth a slide.

**Done for 1 of 3 queries** (`iot_safety`). Result: `bridge_on` and `bridge_off` read the
*identical* 15 papers in the identical order, and each run's event log confirms zero
`bridge_promoted` events either way — a controlled, direct confirmation (not just
inference from tuning history) that the mechanism never fired at this corpus scale
(10-15 papers, `min_cluster_size: 2`). Reported as a genuine negative result: the
mechanism needs more papers/time for Louvain clusters to accumulate enough reads to
qualify a promotion, not a bug in the promotion logic itself.

Query 2's `bridge_off` run also completed (14 papers, 13 clusters, 0 contradictions,
88 relations judged) — but its `bridge_on` counterpart crashed instantly (the disk-space
incident above), so there's no on/off comparison for this query yet, just the one side.
**[PENDING]** the same on/off comparison at deep/extra-deep scale, `bridge_on` for query 2,
and both for query 3.

### E4 — Grounding gate effectiveness
Report the drop rate per run. Then hand-check 50 *verified* claims: how many are truly verbatim
and correctly attributed? Target ≥ 95%. Also hand-check 20 *dropped* claims to show the gate isn't
discarding good ones indiscriminately.

**Tooling: `evaluation/e4_grounding_sample.py --out sheet.md`.** Drop rate itself was
already free (`RunStats.claims_dropped_ungrounded`, e.g. 3 of 97 on the `fine_tuning`
run). Hand-checking dropped claims needed a new `dropped_claims` Postgres table (nothing
previously retained *what* the gate rejected, only a count) — added in migration 0003,
wired into `forage/loop.py`; only populates from runs recorded *after* this was added
(the `iot_safety` runs sampled here predate it, so the dropped-claims half is still
empty — nothing to hand-check yet).

**Verified-claims half: done, 49/50 (98%).** Every distinct source paper behind the 50
sampled claims was independently re-fetched (OpenAlex/Crossref for 11 papers, arXiv HTML
full text for 3, and the actual PDF via PyMuPDF for 3 more where the quoted text wasn't
in the abstract) and each quote checked as an exact substring of the real source, not
just eyeballed. One real failure: claim #18 has a fabricated "5" inserted into an
otherwise-correct quote ("...last few **5** layers..." vs. the source's "...last few
layers...") — it slipped through because that claim matched via the grounding gate's
*fuzzy* path (`fuzzy97`, ~97% string similarity), which is loose enough to tolerate a
single inserted character. Everything else, including a few claims that looked like
near-misses at first (PDF-extraction hyphenation artifacts like "fixedrank" for
"fixed-rank"), checked out as genuinely verbatim once compared against what ATLAS itself
actually parsed. Full writeup and checked sheet: `evaluation/e4_sheet.md`.

**Correction (2026-09-28): claim #18 was a parser bug, not an LLM fabrication.** Re-checked
against the arXiv PDF: page 4 ends "…the last few" and page 5 opens with its running header, then
"5", then "layers of FMs…". PyMuPDF kept the page number; the LLM quoted ATLAS's parsed text
faithfully, and the gate matched it. So the 49/50 stands, but the failure belongs to the PDF parser
(fixed: `normalize.strip_page_numbers`). Separately, re-checking every stored `fuzzy97` claim found
the fuzzy path *did* have a real hole (edited words passed at ≥ 97) and one real case: an inserted
"set" in doi:10.1109/jbhi.2025.3631706. Fixed with the wording guard (DECISIONS.md ADR-007).

### E5 — Judge quality
60 hand-labelled claim pairs (12 per relation type). Confusion matrix, per-label precision/recall.
Be honest about `CONTRADICTS` vs `DIFF_SCOPE` confusion — it is the interesting result.

**Tooling: `atlas judge-eval --run-id id1,id2,id3 --export sheet.jsonl` (now pools
multiple runs and stratified-samples per label — a single small run rarely has 12
CONTRADICTS pairs, they're naturally rare).** Pooling the 3 real runs on hand gave 12/12
each for SUPPORTS/EXTENDS/DIFF_SCOPE/UNRELATED but only 1 CONTRADICTS and 0 REPLICATES —
worth noting honestly in the report rather than padding.

**Hand-labelling done, 49 pairs, `atlas judge-eval --score evaluation/e5_sample.jsonl`:
57.1% accuracy overall.** The confusion matrix is the actually interesting result, and
matches exactly what the docs above ask to be honest about:

| gold label | precision | recall | support |
|---|---|---|---|
| SUPPORTS | 0.667 | 0.889 | 9 |
| EXTENDS | 0.167 | 1.0 | 2 |
| REPLICATES | 0.0 | 0.0 | 1 |
| DIFF_SCOPE | 0.917 | 0.379 | 29 |
| UNRELATED | 0.583 | 0.875 | 8 |

DIFF_SCOPE has the highest precision of any label (0.917 — when the judge does say
DIFF_SCOPE, it's almost always right) but by far the lowest recall (0.379) — it *misses*
most true DIFF_SCOPE pairs, mislabelling them as EXTENDS (9 cases), SUPPORTS (3),
UNRELATED (5), or CONTRADICTS (1). That last one is the CONTRADICTS/DIFF_SCOPE confusion
this doc specifically asks to report honestly: the judge's only CONTRADICTS call in the
whole sample was actually two unrelated, independently-designed devices (different
microcontrollers, different papers) — not a real disagreement. The underlying pattern:
this corpus is a lot of independently-invented IoT safety devices that share surface
vocabulary (GPS, GSM, sensors, "women's safety") without actually building on each
other, and the judge is biased toward reading that shared vocabulary as
support/extension/unrelatedness rather than correctly recognizing "these are just two
different things." Full labelled data: `evaluation/e5_sample.jsonl`.

**Second E5 sample, 2026-09-29 (AI-annotated, human check pending).** 50 pairs pooled from runs
`a0e32253`, `917e7b11`, `42ddbe56`, `8d78fb54`, stratified 12 per *model* label (only 2 CONTRADICTS
and 0 REPLICATES exist across all four runs), written blinded by `evaluation/e5_blind_sheet.py`.
Annotated by the AI assistant (Claude) from the blinded sheet without seeing the model's labels
(`evaluation/e5_ai_labels.csv`, one-line reason per pair) — an independent second model, **not a
human**. Judge v1 against these labels: **accuracy 36% (18/50)**; DIFF_SCOPE precision 0.83 but
recall 0.27 (of 37 pairs annotated DIFF_SCOPE the judge said EXTENDS 10, UNRELATED 8, SUPPORTS 7,
CONTRADICTS 2); SUPPORTS recall 0.8; **CONTRADICTS precision 0/2** (both are the NodeMCU pair).
Because the sample is stratified by model label it over-represents rare labels: per-label
precision/recall are the meaningful figures, not the overall accuracy. A human annotator is
labelling a random 15 of these pairs (`evaluation/e5_human_check_15.csv`) to measure
AI–human agreement.

**Human check and inter-annotator agreement, 2026-09-29.** A human annotator from the project
team labelled a random 15 of those 50 pairs (seeded sample; `evaluation/e5_human_check_15.csv`),
blind to both the AI labels and the model's; 3 of the 15 were marked as undecided between labels
(e.g. "EXTENDS/SUPPORTS/REPLICATES"). On the 12 single-label pairs (`evaluation/e5_agreement_2026-09-29.json`):

| Compared | Agreement | Cohen's κ |
|---|---|---|
| human vs AI annotator | 2/12 (17%) | −0.17 |
| human vs ATLAS judge (v1) | 2/12 (17%) | −0.05 |
| AI annotator vs ATLAS judge | 5/12 (42%) | 0.22 |

Agreement is at or below chance. The disagreement is systematic, not noise: the human read
"consistent claims on the same topic" as SUPPORTS/EXTENDS/REPLICATES, the AI annotator read
"different device or study" as DIFF_SCOPE. **Conclusion: the relation taxonomy — above all the
DIFF_SCOPE vs SUPPORTS/EXTENDS boundary — is not reliably applied even by annotators on this
kind of corpus, so the judge "accuracy" figures (57% against the first AI-written labels, 36%
against the second) measure agreement with one annotator's reading, not correctness.** What
survives every annotation so far is narrower: the corpus's only CONTRADICTS verdict (the NodeMCU
pair) was judged a false contradiction by every annotator who labelled it (the pair was not in
the human's random 15). Next step, beyond this project's timeline: a sharper taxonomy with
written guidelines and worked examples, two or more human annotators, then re-measure the judge.

### E6 — Gap plausibility (expert assessment)
Top 10 gaps per query, rated by a domain-familiar person as plausible / trivial / wrong. Report
the counts. Blind them to which detector produced each gap.

**Tooling: `evaluation/e6_gap_review.py --run-id <id> --out sheet.md --key-out key.json`**
— writes a blinded reviewer sheet (statement + bounding papers, no detector `type`/
`found_by`) plus a separate answer key for scoring afterward.

**Rated, 10/10 gaps, `iot_safety` run: 2 plausible, 4 trivial, 4 wrong.** This is the R3
tripwire. Full reasoning per gap in `evaluation/e6_sheet.md`; headline findings:

- The one gap built on a real CONTRADICTS-type judge call turned out to be wrong for the
  exact reason E5 surfaced independently: two unrelated devices misread as a conflict.
- 2 of the "wrong" gaps (unlinked `machine learning`↔`personal security` and `machine
  learning`↔`incidents`) claim the corpus never connects these ideas, but it does —
  SheGUARD (already in the gap's own evidence list) combines exactly these. Concept
  extraction missed the link because of vocabulary mismatch (e.g. "protection" vs.
  "personal security"), not because the evidence is actually absent.
- 2 of the "plausible" gaps (accuracy of risk/incident detection) are genuinely the same
  underlying gap phrased two ways from two different concept pairs — fusion's dedup
  didn't catch the near-duplicate.
- Net effect: only 20% of this run's top-10 gaps hold up as genuinely novel findings on
  this particular corpus — consistent with the corpus being abstract-only-heavy (the
  concept/gap machinery has thinner material to work with than it would on full text).

**Second E6 sample, 2026-09-29 (AI-rated; no human rating — by decision of the project team).** Run `8d78fb54` (IoT, 15 papers)
produced 6 gaps, all from detector 1 (unlinked concepts). Rated from the blinded sheet by the AI
assistant: **0 plausible, 1 trivial, 5 wrong** (`evaluation/e6_ai_ratings_8d78fb54.json`) — each
"unlinked" pair is linked in the corpus under different wording ("continuous monitoring" ↔ "panic
button", "attack" ↔ "gsm"), or is a near-synonym pair. Same failure as the first sample
(vocabulary mismatch in concept extraction), more pronounced on this run.

### E7 — Cost and time
Per mode: wall-clock, USD, tokens, API calls, cache hit rate, full-text ratio. A cost-per-paper
figure is a genuinely useful contribution — very few student projects report it.

**Tooling: `evaluation/e7_cost.py`.** Already run — aggregates every completed run in
the local store for free (no new crawling needed). Real numbers so far, standard mode,
n=8 runs: mean 6.8 papers read, mean $0.0018/run (practically free on the Groq/Gemini
free tiers), mean cache-hit rate 53%, mean full-text ratio 9.2%.

**Re-run 2026-09-29, n=27 standard runs** (`evaluation/e7_cost_2026-09-29.json`): mean 9.5
papers read, ~29 min wall clock (includes cached replays), 80K prompt + 64K output tokens,
71.5% cache-hit rate, full-text ratio 4.7%. **The dollar figure is not a real cost**: LiteLLM
has no price for Groq's `gpt-oss` models, so only the Gemini synthesis calls are priced
(mean "$0.0014"). Re-pricing the tokens at Groq's paid `gpt-oss-120b` rate ($0.15 / $0.60 per M
in/out) gives an upper bound of **~$0.05 per run** (the judge's 20b model is cheaper). On the
free tier the real constraint is time, not money: 8K tokens/min and 200K tokens/day per model.

### GROBID before/after (Task B, 2026-09-29)

Same query (`federated learning for medical imaging`), standard mode, before = PyMuPDF flat text
(run `42ddbe56`, 2026-09-18), after = live GROBID on a Hugging Face Space (run `b0e7e2c2`):

| | before (PyMuPDF) | after (GROBID) |
|---|---|---|
| papers read | 14 | 13 (stopped on saturation) |
| full-text ratio | 14.3% | 23.1% (4 papers parsed by GROBID; 7 of 13 were metadata-only — no PDF, no abstract) |
| claims extracted / dropped by the gate | 98 / 1 | 198 / 3 |
| relations judged | 88 | 28 — ~50 claims calls and most judge calls hit the Groq free-tier daily cap (200K tokens/model) |
| gaps (all five detectors) | 0 | 0 |

`iot_safety` with GROBID (run `8d78fb54`): 0 of 15 papers had an open PDF, so GROBID never ran —
the bottleneck on that query is PDF availability, not parsing. Detectors 3/4/6 still found nothing
on either query: with 4 full-text papers, no method or dataset appeared in the ≥2 papers the
detectors require. Honest reading: GROBID doubles the claims a full-text paper yields and gives
real sections, but 15-paper runs on open-access PDFs are too small and too text-poor to exercise
the full-text gap detectors. Operational note: concept extraction for this run took ~7 h instead
of minutes because the 5.9 GB laptop was swapping (VS Code open alongside); it completed correctly.

**Third query with GROBID — `gut microbiome and depression`, run `4c1f35f3` (2026-09-29/30).**
9 papers read (5 seeds, 4 via citations), then stopped **manually** at a paper boundary: from ~23:46 the
claims model (`gpt-oss-120b`) hit the Groq free-tier daily cap (200K TPD), so later papers would have
been read with no claim extraction. The un-started 10th paper was returned to the frontier and the run
recorded as `completed` with that stop reason. 3 of 9 papers full text via GROBID (33%, the highest of
any run), yielding 30, 65 and 13 claims (the 13 cut short by the cap) against 0–6 per abstract-only
paper; 136 claims kept, 5 dropped by the gate; 84 of 9,180 possible pairs judged (99.1% never judged —
the 12-pairs-per-paper cap was reached for every paper, as in every run); relations 26 SUPPORTS /
16 EXTENDS / 20 DIFF_SCOPE / 21 UNRELATED / 1 CONTRADICTS; 3 gaps survived fusion (8 unlinked-concept
+ 1 unresolved-conflict candidates, none dropped by the citation rule; **not yet rated**). The one
CONTRADICTS — "gut dysbiosis has been repeatedly observed to be associated with obesity, type 2
diabetes, and depression" vs "clinical studies on the gut microbiome–depression association have
produced mixed results" (conf 0.9) — is on the same topic, unlike the IoT false positive: a plausible
tension, but both statements can hold at once, so it needs a human verdict. E1: overlap 5/9 (56%),
clusters 7 vs 8 (baseline cut to 9), references 381 vs 365 (`evaluation/e1_gut_microbiome_4c1f35f3.json`).
Snapshot saved for the offline demo.

### E8 — Reproducibility

> **[RE-VERIFIED — 2026-09-29]** Two reproducibility gaps were found and fixed (ADR-015: shared
> abstract vectors overwritten by ingest; ADR-012 addendum: truncated answers never cached; plus
> the gap-list ordering bug, ADR-013 addendum). Re-verified 2026-09-29 on the repaired store with all of that day's fixes
> (`evaluation/e8_compare.py`, result in `evaluation/e8_iot_safety_2026-09-29.json`): run
> `8d78fb54` and its warm-cache replay `782c319e` (same query, same config) read the same 15
> papers in the same order and produced identical claims (65, compared as paper + verbatim
> quote) and identical relations (132, compared as both claims + type), with 0 new LLM calls
> (146 cache hits) in 6.7 min against ~50 min for the original. Gap lists are separately shown
> identical across processes (ADR-013 addendum). Caveat, honestly: Suhani's two earlier IoT runs
> (`a0e32253`, `917e7b11`) are *not* identical to each other (73 vs 86 claims, different read
> order) — they were made under different cache/config states, so the original E8 claim had not
> actually been demonstrated on them.
Same query twice with a warm cache → identical graph hash. Report it as a property of the system.

**Done** (the R9 tripwire, Phase 4/5) — same query run twice with a warm cache produced
an identical graph, after fixing the SQLAlchemy `Uuid`-on-SQLite bug that first broke it
(docs/DECISIONS.md). Write this up as-is; no further action needed.

---

## Demo-day preparation

Three saved runs, cached end to end, replayable **with the network unplugged** (`atlas snapshot --run-id <id>` while online saves the Neo4j-backed pages to disk; see ROADMAP Phase 7). Test that
literally: disconnect wifi and run the demo. Have the extra-deep run pre-computed; do not attempt
a 200-paper crawl live.

Demo arc that works:
1. Type the query. Watch the graph build live, paper by paper.
2. Pause on a **bridge promotion** — "it just decided to read a paper that cosine similarity had
   parked, because that paper's citations connect two clusters."
3. Open a claim and show the highlighted verbatim quote in the source PDF.
4. Show the contradiction report — two papers, both quotes, side by side.
5. Show the ranked gaps, each with its bounding papers.
6. Ask the chat something outside the corpus. It refuses. **That refusal is the trust argument for
   the whole system** — do not skip it.
