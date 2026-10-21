# ATLAS: Agentic Technology for Literature review using Augmented Synthesis

*Final-year project report — draft.*

> **Status of this draft.** Written in plain markdown so it's easy to keep editing while
> evaluation results are still coming in; convert to whatever format (Word/LaTeX/a
> department template) once that's confirmed. Sections marked **[PENDING]** need data or
> a human judgment step that hasn't happened yet — everything else is real, drawn from
> the actual working system and actual runs against it, not aspirational description.

---

## Abstract

Doing a literature review well means reading widely, noticing when papers disagree, and
following citation trails to work a topic hasn't already been covered — not retrieving
the top-k most similar abstracts and summarizing them. ATLAS is an agent that reads the
scholarly literature the way a researcher does: it reads the most promising paper first,
follows its citations, re-scores what to read next based on everything read so far, and
builds a live knowledge graph as it goes, ending with what the field agrees on, where it
contradicts itself, and which gaps are genuinely unexplored — every claim backed by a
verbatim quote checked character-for-character against its source, never repaired or
invented by an LLM. The system runs the full pipeline — harvest, ingest, foraging loop,
relation judging, gap detection, synthesis — end to end, served through a live web
dashboard, on consumer hardware with no GPU, for free on free-tier LLM quotas (at most about
$0.05 per 15-paper run at paid rates). Evaluated against a one-shot retrieval baseline on
three queries, ATLAS's foraged paper set overlapped the baseline's by only 36–56% and reached
4–60% more of the reference network than the same number of top-ranked papers — the loop
reads meaningfully differently — but at 9–15 papers it was not measurably broader in citation-
cluster coverage, which a larger-scale run still has to show. Hand-verification of a sample of extracted claims found 98% genuinely
verbatim and correctly attributed. The honest limitations are in what ATLAS
infers between papers. The only contradiction it ever reported was a false one (two
independent devices, not a disagreement), and relation labels proved ambiguous even for
people: a human and an AI annotator agreed on only 2 of 12 claim pairs, so the relation
taxonomy itself needs sharpening before judge accuracy can be measured. Its automatically
detected research gaps were mostly artefacts of wording (0–2 of 6–10 rated plausible). ATLAS
is therefore dependable as an evidence finder — every quote real and traceable — and should
be read as a source of leads, not conclusions, where it relates papers to one another.

---

## 1. Introduction

### 1.1 The problem

Doing a literature review well means reading widely, noticing when two papers disagree,
and noticing what nobody has actually tried yet. Large language models are good at
summarizing text they are shown, but a chatbot that retrieves once and answers — the
now-familiar retrieval-augmented-generation (RAG) pattern — never does the second and
third of those things. It answers questions about the papers it happens to be shown; it
does not decide what to read next based on what it just learned, and it has no structural
reason to trust or distrust what it produces beyond "the source text is nearby in
embedding space."

ATLAS is built around a different idea: treat literature discovery as a **closed loop**,
not a single retrieval step. Given a research question, it reads the most promising paper
it can find, follows that paper's citations, re-ranks what to read next based on what it
now knows about the field, and repeats — building a live knowledge graph as it goes. It
stops when the graph stops teaching it anything new. Only then does it report what the
field agrees on, where it contradicts itself, and which combinations of methods, datasets,
and open questions nobody in the corpus has actually addressed.

### 1.2 What makes this different from RAG

The distinction that matters, stated precisely: **a RAG system retrieves once and
answers; ATLAS runs a loop where every paper it reads changes what it reads next.** The
frontier queue — the ranked list of "what to read next" — is rescored after every single
paper, using five components (relevance, citation-graph PageRank, novelty relative to
what's already been read, "contest" — how often a paper's claims get contradicted by the
literature, and recency). A one-shot cosine-similarity retrieval, by construction, cannot
discover a paper that is not textually similar to the query but that turns out to be
structurally important — a paper two citation-hops away that connects two otherwise
disconnected clusters of the field. Section 5 (Evaluation, E1) measures this directly:
the same query given to a naive one-shot baseline and to ATLAS overlaps only partially in
which papers get picked, and the two systems cover a very different amount of the field's
actual community structure.

### 1.3 The non-negotiable design commitment

Every claim ATLAS extracts carries a verbatim quote, checked character-for-character
against the source text before it is trusted (the "grounding gate", `extract/grounding.py`).
A claim whose quote does not genuinely appear in the paper is dropped, never repaired,
never passed on with a caveat. This is stated first because it shapes almost every other
design decision in the system: **nothing downstream — the graph, the contradiction
report, the gap list, the chat interface — is allowed to say anything ATLAS cannot point
to a verbatim source for.** Section 5 (E4) reports how often the gate actually rejects a
claim, and includes a hand-checked sample confirming what survives is genuinely verbatim.

---

## 2. System design

### 2.1 Shape

ATLAS is a single-process orchestrator, not a microservice mesh or a multi-agent swarm —
the "agentic" behaviour comes from the closed feedback loop (the frontier is re-scored
after every paper), not from multiple autonomous agents negotiating with each other. It
runs against three purpose-built stores, each answering one kind of question:

- **Postgres** (SQLite in this project's lightweight deployment) — "what happened in this
  run": the frontier queue, run state, LLM/API cost ledger, event log for the live UI.
- **Neo4j** — "what connects to what": papers, claims, concepts, contradictions, gaps.
- **Qdrant** — "what text is similar": abstract, chunk, and claim embeddings.

```
Query → keyword expansion (LLM) → harvest (4 scholarly APIs, ~500 candidates, deduplicated)
      → seed by cosine similarity → foraging loop (read, extract, judge, expand, rescore)
      → gap detection (6 independent detectors, fused into one ranked list)
      → synthesis (one LLM pass over a deterministic graph summary → 4-section report)
      → served live over SSE to a React dashboard, plus a retrieval-grounded chat
```

### 2.2 The foraging loop

```
while not stop():
    paper  = frontier.pop_highest()
    doc    = ingest(paper)                    # PDF → GROBID/PyMuPDF → sections → chunks
    claims = extract_claims(doc)              # verbatim quote + scope, per section
    claims = grounding_gate(claims)            # character-exact check; failures dropped
    edges  = judge(claims)                     # vs. kNN-neighbouring existing claims
    graph.write(paper, claims, edges)          # incremental — the live graph is not batched
    neighbours = expand(paper)                 # references + citers
    frontier.push_scored(neighbours)           # three-band admission: drop / park / queue
    frontier.rescore_if_dirty()                # PageRank periodically, novelty every step
```

Three-band admission on cosine similarity to the query keeps the frontier from either
drowning in irrelevant candidates or discarding a paper too early: below 0.20 is dropped
outright, 0.20–0.35 is *parked* (not read now, not thrown away), above 0.35 is scored and
queued normally. The most structurally interesting mechanism is **bridge promotion**: a
parked paper is promoted back onto the frontier if its citations reach into two or more
distinct Louvain communities of the citation graph that ATLAS is actively building — a
paper connecting two otherwise-separate clusters gets a second look precisely because it
is structurally a connector, something similarity ranking alone cannot detect. (Section 5,
E3, reports how often this actually fired on real runs — honestly, not often at this
scale; see the limitations discussion.)

### 2.3 Gap discovery

Six independent detectors run over the finished graph (one, "predicted links" via
Adamic-Adar link prediction, was descoped as a stretch item — see §6.3): unlinked
concepts (Swanson ABC literature-based discovery), empty method×dataset combinations,
unanswered "future work" calls, unresolved contradictions, and shared weaknesses recurring
across independent research groups. Every candidate a detector produces must name the
papers that bound it — a gap with no citable evidence is not constructed, enforced at the
type level (`GapCandidate.bounding_papers` requires at least one entry) and again after
fusion. The five detectors' outputs are merged by embedding-similarity/bounding-paper
overlap, ranked by weighted reciprocal rank fusion with a corroboration bonus for gaps
multiple detectors independently found, and capped to the top 15 for the report.

### 2.4 Synthesis

A single LLM call receives a **deterministically serialized** summary of the graph — never
raw text — covering agreement clusters, contradiction pairs with both verbatim quotes, the
ranked gap list, and a method/dataset adoption timeline. It writes three prose sections
(what the field agrees on, where it disagrees, methodology over time); the fourth section,
the ranked gap list, is never rewritten by the model — it stays exactly the structured,
citation-backed record the detectors produced, so the model cannot accidentally invent or
drop evidence for a gap.

### 2.5 Serving

A FastAPI backend streams every graph mutation live over Server-Sent Events during a run,
and a React/Cytoscape dashboard renders the graph as it is built, a sortable "why did it
read that?" frontier table, the four-section report, and a chat interface. Chat retrieval
is hard-filtered to the current run's data server-side — not by prompt instruction — and
if nothing in the corpus is relevant enough, the system says so plainly rather than
falling back on the model's own general knowledge. This refusal behaviour is treated as a
first-class feature, not an edge case: §5 reports it working correctly on a real deliberate
out-of-scope question.

---

## 3. Implementation notes

*(Brief by design — the interesting engineering decisions, not a line-by-line account.)*

### 3.1 A lightweight deployment path

The reference architecture assumes Docker (Postgres, Neo4j, Qdrant, GROBID as containers).
Development happened on a laptop that could not run that stack (Intel i3, 2 cores, 8GB
RAM). Every store has a Docker-free equivalent that needed no code changes at the call
site: SQLite for Postgres, an embedded on-disk Qdrant, a free-tier Neo4j AuraDB cloud
instance instead of a local container, and PyMuPDF as a fallback PDF parser when GROBID
is unavailable (at the cost of losing GROBID's section/reference structure — flat text
only). Graph algorithms (PageRank, Louvain community detection) that would normally run
via Neo4j's Graph Data Science library instead run in `networkx`, pulled from and written
back to the same graph, seeded for reproducibility.

### 3.2 LLM strategy on a zero budget

All LLM calls route through a provider-agnostic client (LiteLLM + `instructor` for
structured output) so the underlying model is a config change, not a code change. The
working default is Groq's free tier (paced client-side to stay under its
tokens-per-minute cap) with Gemini as a secondary profile for the one job (synthesis) that
sends an entire graph summary in a single prompt too large for Groq's per-request budget.
Every LLM call is cached by `(prompt, model, params)`, so a repeated run — or, as it turned
out, a repeated evaluation query against the same graph state — costs nothing on a cache
hit. This is not a performance nicety: it is also what makes the reproducibility guarantee
(§5, E8) practically free to demonstrate.

### 3.3 Honesty as an engineering property, not a promise

A handful of invariants recur throughout the codebase specifically because they are the
project's actual thesis, and violating one silently is treated as the worst possible
failure mode:

1. No unverified quote survives (the grounding gate, §1.3).
2. No gap without bounding citations (enforced in the type system, not just business
   logic).
3. Nothing in a report ATLAS did not actually read (deterministic synthesis input, no
   parametric fallback in chat).
4. Every LLM call is cached and replayable — a rerun of the same graph state must produce
   the same result (§5, E8).

### 3.4 Data ethics and licensing

ATLAS only ever fetches PDFs through legitimate open-access routes: a source-provided
`pdf_url`, arXiv, Unpaywall, and Europe PMC, tried in that order (`ingest/pdf_fetch.py`).
There is no scraping of paywalled publisher sites and no use of shadow-library mirrors —
if none of those four routes returns a PDF, the paper is read in abstract-only mode
instead (the normal, first-class path for the 40-60% of papers with no accessible full
text, not an error). Every fetched PDF's originating source is recorded (`via` field), and
every `Paper` carries a `license` field populated from OpenAlex/arXiv metadata where
available. That field is stored and queryable today but **not yet surfaced in the
dashboard UI** — a small, honest gap rather than a claim of a feature that doesn't exist.
Scholarly API terms of use and `robots.txt` are respected throughout (polite pools with a
contact email, backoff on `Retry-After`). No paper text or LLM output is redistributed
beyond quoting the verbatim spans the grounding gate has already verified against the
source.

---

## 4. Evaluation

*Methodology, tooling, and results per `docs/TESTING.md`'s evaluation plan. Three queries
frozen in `evaluation/queries.yaml`: an applied engineering query ("IoT devices for women
safety" — sparse literature, mixed venue quality), a well-studied CS topic ("federated
learning for medical imaging"), and a biomedical query ("gut microbiome and depression",
to exercise PubMed specifically). Results below are reported per-query where a query is
named; **[PENDING]** marks anything not yet run or not yet possible to report.*

### 4.1 E1 — Does the loop beat one-shot retrieval? *(the central claim)*

**Method.** Baseline: harvest the same candidate pool the run saw, embed, take the top 25 by
cosine similarity to the query — no expansion, no re-ranking, no claim extraction. Compare
against ATLAS's actual read set from a real standard-mode run over the same query. Breadth is
measured identically for both sets: every paper's reference list is fetched from OpenAlex, one
citation graph is built over all of them, Louvain (seed 42) clusters it once, and each set is
scored by how many clusters its papers fall into and how many distinct references it reaches.
A size-matched baseline (its top 15 or 14) removes set size as an explanation
(`evaluation/e1_baseline.py`, results in `evaluation/e1_*.json`).

**Results (2026-09-29, re-run on the repaired vector store — see below):**

| Run (query, papers read) | Overlap with baseline top-25 | Clusters: ATLAS / baseline same size | References reached: ATLAS / baseline same size |
|---|---|---|---|
| `8d78fb54` (IoT safety, 15) | 53% (8/15) | 8 / 9 | 115 / 92 |
| `a0e32253` (IoT safety, 15) | 40% (6/15) | 9 / 9 | 147 / 92 |
| `42ddbe56` (federated learning, 14) | 36% (5/14) | 10 / 8 | 355 / 332 |
| `b0e7e2c2` (federated learning, 13, with GROBID) | 38.5% (5/13) | 11 / 9 | 452 / 332 |
| `4c1f35f3` (gut microbiome & depression, 9, with GROBID; stopped at the Groq daily cap) | 56% (5/9) | 7 / 8 | 381 / 365 |

**What this shows, and what it does not.** The loop reads a substantially different set of
papers from one-shot retrieval — 36–56% overlap, at or just below the 40–60% range the design
predicted (TESTING.md's sanity check: "if it's 95%, the loop isn't doing anything"). Its read
set also reaches further into the reference network than the same number of top-cosine papers
(+7% to +60% distinct references). But at this scale (14–15 papers) it is **not measurably
broader in citation structure**: cluster coverage is within ±2 of the size-matched baseline in
every run (−1, 0, +2, +2). The loop changes *what* gets read; that it finds breadth one-shot
retrieval cannot has not been demonstrated at 15 papers. This is consistent with E3 (bridge
promotion, the mechanism designed to reach new clusters, never fired at this scale) and is the
first thing a larger (deep-mode) evaluation should test.

**Correction to an earlier draft.** An earlier version of this section reported "14 distinct
Louvain clusters for ATLAS against roughly 1 for the baseline". That compared two different
metrics: the 14 came from citation-graph clusters stored on shared Paper nodes (which later runs
overwrite — `docs/DECISIONS.md` ADR-017), the ~1 from *embedding* clusters, on which ATLAS also
scored 1. The earlier run was also computed on a vector store where every paper ATLAS had read
carried a different kind of embedding from the rest of the pool (ADR-015). Both are fixed; the
table above replaces that figure.

Contradictions and gaps are properties of ATLAS alone (the baseline extracts no claims): the IoT
runs surfaced 1 and 0 contradictions (the 1 is the false positive discussed in §4.5) and 7 and 6
gaps; the federated-learning run surfaced none of either.

**[PENDING]** the `biomedical` query needs an ATLAS run to compare against.

### 4.2 E2 — Ablation of the scoring components

**Method.** Run standard mode with each scoring weight zeroed in turn (pagerank, novelty,
contest, recency), plus a relevance-only config equivalent to the E1 baseline's own
ranking mechanism. Report papers read, Louvain clusters covered, contradictions, and
relations judged for each. `evaluation/e2_e3_ablation.py` is the harness: each config
transiently edits `config/scoring.yaml` and invokes a real `atlas run` subprocess so
every config gets a genuinely fresh process.

**Result (iot_safety query, 15-paper cap for tractability — a full 25-paper × 6-config
sweep would run many hours on this hardware; every config saw the same cap):**

| Config | Papers read | Clusters covered | Contradictions | Relations judged | Wall clock |
|---|---|---|---|---|---|
| full | 15 | 13 | 1 | 132 | 834s |
| −pagerank | 15 | 12 | 1 | 120 | 904s |
| −novelty | 15 | 13 | 1 | 156 | 872s |
| −contest | 15 | 13 | 1 | 120 | 299s |
| −recency | 15 | 10 | 0 | 84 | 1067s |
| relevance only | 15 | 10 | 0 | 84 | 1482s |

Cluster coverage is fairly stable when a *single* component (pagerank, novelty, or
contest) is removed — 12-13, against 13 for the full config — but drops noticeably (10)
once recency drops out, and drops by the same amount again for `relevance_only` (which
zeroes recency *and* pagerank, novelty, and contest together). Removing recency alone
costs as much cluster coverage as removing everything else besides relevance — on this
query, recency is doing more work than pagerank/novelty/contest combined, which is
plausible for a fast-moving, recently-active topic (most of this corpus is 2023-2026
work) but is exactly the kind of query-dependent result a single-query ablation cannot
generalize from; **[PENDING]** the same sweep against the other two frozen queries, whose
literatures move at different speeds, would test whether this holds or is an
`iot_safety`-specific artefact.

**A striking coincidence, checked rather than assumed:** `-recency` and `relevance_only`
produced *identical* aggregate numbers (10 clusters, 0 contradictions, 84 relations) from
different run_ids. Checking directly (`frontier.read_paper_ids` for both runs) confirms
they read a genuinely different set of 15 papers in a different order — the matching
totals are a real coincidence at the aggregate-metric level, not the same underlying
run. Worth stating plainly: aggregate counts alone can converge across meaningfully
different configurations, so a table like this one should be read alongside which
specific papers were read, not as a complete picture on its own.

The `-contest` run finishing in roughly a third of the wall-clock time of comparable
configs (299s vs 834-1482s) is worth flagging rather than reporting flatly as noise —
plausibly an interaction with the saturation-stopping calculation (`contest` is one of
`new_info_weights`' inputs), not a free efficiency win; **[PENDING]** a closer look at
that run's saturation trace before drawing a conclusion.

### 4.3 E3 — Bridge promotion value

**Method.** Same harness, `bridge.enabled: true` vs `false`, iot_safety query, 15 papers.

**Result:** `bridge_on` and `bridge_off` read the **exact same 15 papers in the exact
same order** (`frontier.read_paper_ids` returns identical lists for both run_ids), and
directly querying each run's event log confirms **zero `bridge_promoted` events in
either run**. Disabling bridge promotion entirely changed nothing about this run, because
the mechanism never actually fired with it enabled — a clean, direct confirmation of what
had already been suspected from development history (two rounds of `min_cluster_size`
tuning, from 3 down to 2, backed by real cluster-size data — see `docs/DECISIONS.md`),
now backed by a controlled on/off comparison rather than inference.

This is reported as a genuine, informative negative result, not a failed experiment: at
this corpus scale (10-15 papers, standard mode), the Louvain communities in the citation
graph never grow large enough (`min_cluster_size: 2` reads) for a parked paper's
cross-cluster citations to qualify for promotion. **[PENDING]** the same on/off comparison
at deep or extra-deep scale (75-200 papers), where clusters have room to actually
accumulate the reads bridge promotion requires, is the natural next test of whether the
mechanism works at all or needs further redesign — this project's development notes
already flag that possibility rather than assuming it will simply resolve at scale.

### 4.4 E4 — Grounding gate effectiveness

**Drop rate (free — already computed per run).** Real example: the `fine_tuning` run
dropped 3 of 97 extracted claims (3.1%) to the grounding gate. Rates observed across
completed runs so far sit in the low single digits to low teens, consistent with
TESTING.md's own expectation of 10-25% (most runs at the low end, likely because the
underlying corpus is abstract-heavy and abstracts contain fewer of the long, complex
sentences that are hardest to quote exactly).

**Hand-check.** `evaluation/e4_grounding_sample.py` samples 50 verified + 20 dropped
claims into a markdown checklist. **Result: 49/50 (98%) verified as genuinely verbatim and
correctly attributed** — above the ≥95% target. Every distinct source paper behind the 50
sampled claims was independently re-fetched (the OpenAlex/Crossref API for 11 papers,
arXiv's HTML full text for 3, and the actual PDF for 3 more whose quoted text lived
outside the abstract) and each quote checked as an exact substring of the real source
text, rather than judged by eye.

The one real failure is informative, though not in the way it first appeared. Claim #18's
quote reads "...last few **5** layers..." where the published paper says "...last few
layers...". Checking the actual PDF showed the "5" is the paper's page number: page 4 ends
mid-sentence at "the last few", and page 5 opens with its running header, then "5", then
"layers of FMs". The PDF parser (PyMuPDF) removed the repeated header but not the page
number, so the sentence ATLAS read genuinely contained a "5". The LLM quoted that text
faithfully and the gate correctly matched it: the error lies upstream, in PDF extraction.
It is now fixed: bare page numbers are stripped from the top and bottom of every page,
with a regression test built from this exact sentence.

The investigation still exposed a real weakness in the gate's *fuzzy* fallback (tagged
`fuzzy97`, ~97% string similarity), which exists to tolerate PDF noise. Re-running every
stored fuzzy match against its source text showed that 97% similarity also admits small
*wording* edits, and found one live case: a quote reading "if μ is **set** too high" where
the paper says "if μ is too high". The fuzzy path now additionally requires the quote to
match the source exactly once formatting noise alone is removed (whitespace, hyphenation,
quote marks, letter case, numbered reference markers such as "[7]"). Any changed or inserted
word, digit or symbol is rejected. On the 22 stored fuzzy matches whose source text was
available, 20 still pass and 2 are dropped: the μ quote, and a quote made unmatchable by
another mid-sentence page number, which the parser fix resolves. The exact-match path, the
gate's primary mechanism, had zero failures in the sample. A few
other claims initially looked like near-misses (e.g. "fixedrank" in the stored quote vs.
"fixed-rank" in the canonically published version) but checked out as genuine once
compared against the text ATLAS itself actually parsed from the PDF — PyMuPDF sometimes
drops a hyphen when unwrapping a line break, which is an extraction artifact, not
fabrication.

*(Note: the `dropped_claims` table this needed did not exist before this evaluation phase
— the gate previously only counted rejections, never retained what was rejected. It now
populates from every run going forward; the runs this sample was drawn from predate it,
so the dropped-claims half of this check has nothing to sample yet.)*

### 4.5 E5 — Judge quality

**Method.** Hand-labelled claim pairs against the model's own `SUPPORTS` / `CONTRADICTS`
/ `EXTENDS` / `REPLICATES` / `DIFF_SCOPE` / `UNRELATED` verdict, confusion matrix,
per-label precision/recall. `atlas judge-eval` now pools multiple runs and
stratified-samples per label, since any single small run rarely has 12 pairs of a rare
label like `CONTRADICTS`.

**Real label availability, pooling 3 completed runs (49 of 272 judged pairs sampled):**

| Label | Available in the pool |
|---|---|
| SUPPORTS | 12 (capped) |
| EXTENDS | 12 (capped) |
| DIFF_SCOPE | 12 (capped) |
| UNRELATED | 12 (capped) |
| CONTRADICTS | 1 |
| REPLICATES | 0 |

This asymmetry is itself worth reporting plainly rather than padding: contradictions and
replications are genuinely rare relative to unrelated/supporting pairs in this corpus,
exactly as `judge.v1.md`'s own prompt anticipates ("most pairs are unrelated").

**Hand-labelled, 49 pairs, `atlas judge-eval --score`: 57.1% overall accuracy.** The
per-label breakdown is the actually informative part:

| gold label | precision | recall | support |
|---|---|---|---|
| SUPPORTS | 0.667 | 0.889 | 9 |
| EXTENDS | 0.167 | 1.0 | 2 |
| REPLICATES | 0.0 | 0.0 | 1 |
| DIFF_SCOPE | 0.917 | 0.379 | 29 |
| UNRELATED | 0.583 | 0.875 | 8 |

`DIFF_SCOPE` has the highest precision of any label — when the judge does say two claims
are out of scope of each other, it's almost always right — but by far the worst recall
(0.379): it systematically *misses* true `DIFF_SCOPE` pairs, mislabelling them as
`EXTENDS` (9 cases), `SUPPORTS` (3), `UNRELATED` (5), or `CONTRADICTS` (1). That last one
is exactly the confusion this section set out to get an honest read on: the judge's only
`CONTRADICTS` verdict in the entire 49-pair sample was, on inspection, two unrelated,
independently-designed devices from two different papers (different microcontrollers,
no actual disagreement) — not a real contradiction. The underlying cause is specific to
this corpus's shape: it's a large set of independently-invented IoT safety devices that
share surface vocabulary (GPS, GSM, sensors, "women's safety") without building on each
other, and the judge is biased toward reading shared vocabulary as evidence of a
relationship (support, extension, even contradiction) rather than correctly recognizing
"these are just two different things." Detector 5 (unresolved conflicts) inherits this
weakness directly — see §4.6, Gap 1.

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

### 4.6 E6 — Gap plausibility (expert assessment, the R3 tripwire)

**Method.** Top 10 gaps from a completed run, rated by a domain-familiar person as
plausible / trivial / wrong, blinded to which of the 5 detectors produced each one.
`evaluation/e6_gap_review.py` generates the blinded sheet and a separate answer key for
scoring afterward.

**Result: 2/10 plausible, 4/10 trivial, 4/10 wrong**, rated against the `iot_safety`
run's top 10 gaps (mostly `unlinked_concepts`, one `unresolved_conflict`). Full reasoning
per gap in `evaluation/e6_sheet.md`; the headline findings:

- **Gap 1 (wrong)** is the `unresolved_conflict` gap, and it fails for exactly the reason
  §4.5 surfaced independently: the two "conflicting" claims are just two unrelated,
  independently-designed devices, not a real disagreement. Detector 5's output quality is
  capped by the relation judge's weak `DIFF_SCOPE` recall.
- **Two "wrong" gaps claim the corpus never connects `machine learning` to `personal
  security` / `incidents`**, but it does — SheGUARD (already in both gaps' own evidence
  lists) combines exactly these. The concept-linking step missed it, most likely a
  vocabulary mismatch (e.g. "protection" vs. "personal security"), not an actual absence
  of evidence.
- **Two "plausible" gaps turned out to be the same underlying gap** (whether any paper
  measures detection accuracy against real safety-risk/incident scenarios, rather than
  just claiming detection qualitatively) reached from two different concept pairs — a
  near-duplicate that fusion's dedup step (Jaccard/embedding similarity on the gap
  statement) didn't catch because the two statements' concept nodes differ even though
  the substance is the same.
- **Net result: only 20% of this run's top-10 gaps hold up as genuinely novel on this
  corpus.** Consistent with development notes elsewhere in this report (§5): this
  corpus is abstract-only-heavy, and detectors 3/4/6 already produce zero gaps for lack
  of full-text structure (ADR-013). The two detectors that *do* produce output here
  (`unlinked_concepts`, `unresolved_conflict`) are working with thinner, noisier
  material than they would against full-text papers, and it shows in gap quality, not
  just gap quantity.

**Second E6 sample, 2026-09-29 (AI-rated; no human rating — by decision of the project team).** Run `8d78fb54` (IoT, 15 papers)
produced 6 gaps, all from detector 1 (unlinked concepts). Rated from the blinded sheet by the AI
assistant: **0 plausible, 1 trivial, 5 wrong** (`evaluation/e6_ai_ratings_8d78fb54.json`) — each
"unlinked" pair is linked in the corpus under different wording ("continuous monitoring" ↔ "panic
button", "attack" ↔ "gsm"), or is a near-synonym pair. Same failure as the first sample
(vocabulary mismatch in concept extraction), more pronounced on this run.

### 4.7 E7 — Cost and time

**Method.** Aggregated across every completed run already in the local store — free,
no new crawling needed.

**Result, standard mode, n=8 runs:**

| Metric | Mean |
|---|---|
| Papers read | 6.8 |
| Wall clock | 1093s (~18 min) |
| Cost | $0.0018/run |
| Cost per paper | $0.00032 |
| Prompt tokens | 63,834 |
| Output tokens | 49,972 |
| LLM cache hit rate | 53% |
| Full-text ratio | 9.2% |

**Update, 2026-09-29 (n=27 standard runs):** mean 9.5 papers, ~29 min wall clock, 80K prompt
+ 64K output tokens per run, 71.5% cache-hit rate, 4.7% full-text ratio.

**Correction on cost.** The "$0.0018/run" above is not a real cost: the cost library has no
price for Groq's `gpt-oss` models, so only the Gemini synthesis calls were priced. Re-pricing
the measured tokens at Groq's paid rate for its larger model ($0.15 / $0.60 per million
input/output tokens) gives an upper bound of **about $0.05 per 15-paper run** — still very
cheap, and a genuinely useful figure: very few student projects report cost per run at all.
On the free tier the binding constraint is not money but throughput (8K tokens/minute and 200K
tokens/day per model), which is why a fresh run takes one to four hours and why the caching
architecture (§3.2) matters: a warm-cache replay of a 15-paper run took 6.7 minutes and zero
LLM calls (§4.8).

### 4.8 E8 — Reproducibility

**Done.** The same query run twice with a warm cache produced an identical graph — the
R9 tripwire, verified during Phase 4/5 of development (after fixing a real bug where
SQLAlchemy's `Uuid` column type silently stored hyphen-less UUIDs on SQLite, breaking
cross-store joins on `run_id` between Postgres, Neo4j, and the filesystem; switched to a
plain text column, see `docs/DECISIONS.md`). ~~Reported here as a settled property of the
system, not something still to verify.~~

**Re-verified, 2026-09-29.** Re-verified 2026-09-29 on the repaired store with all of that day's fixes
(`evaluation/e8_compare.py`, result in `evaluation/e8_iot_safety_2026-09-29.json`): run
`8d78fb54` and its warm-cache replay `782c319e` (same query, same config) read the same 15
papers in the same order and produced identical claims (65, compared as paper + verbatim
quote) and identical relations (132, compared as both claims + type), with 0 new LLM calls
(146 cache hits) in 6.7 min against ~50 min for the original. Gap lists are separately shown
identical across processes (ADR-013 addendum). Caveat, honestly: Suhani's two earlier IoT runs
(`a0e32253`, `917e7b11`) are *not* identical to each other (73 vs 86 claims, different read
order) — they were made under different cache/config states, so the original E8 claim had not
actually been demonstrated on them.

Two further reproducibility gaps had been found and fixed first.
(1) Reading a paper overwrote its shared abstract embedding with a different kind of vector, so
a warm-cache rerun could seed in a different order once earlier runs had touched the store (seen
directly: the same query read a different first paper). (2) An LLM answer cut off by its token
limit was never cached, so a replay asked the provider again and could get a different answer.
Back-to-back reruns, the case originally tested, were unaffected by either, which is why the
first check passed.

---

## 5. Discussion and limitations

*[PENDING expansion once E2-E6 land, but the honest shape of this section is already
clear from development so far:]*

- **Corpus depth is the binding constraint on gap-detector diversity, not detector
  design.** Three of the five built gap detectors (empty combinations, unanswered calls,
  shared weaknesses) need real structured sections — methods, datasets, future-work,
  limitations — that only come from GROBID's PDF parsing, not the PyMuPDF flat-text
  fallback this project's Docker-free deployment defaults to. On a real 15-paper run they
  found nothing, not because they are broken (each is unit-tested against synthetic
  fixtures matching the exact scenario they should catch) but because this corpus is
  abstract-only-heavy. This is a real, disclosed limitation of the lightweight deployment
  path, not of the detector logic.
- **Bridge promotion has not fired on any real run yet.** Coded, unit-tested, tuned twice
  against real cluster-size data, and directly confirmed by E3 (§4.3): a controlled
  bridge-on/bridge-off comparison at this project's run scale (10-15 papers) read the
  identical set of papers in the identical order and logged zero promotion events either
  way. Larger runs (deep/extra-deep mode, more papers, more time for clusters to
  accumulate reads) are the likeliest way to actually observe it firing; that is future
  work, not a claim to walk back.
- **External citation counts are frequently unavailable**, particularly for very recent
  (2025/2026) conference papers not yet indexed by OpenAlex and for arXiv/PubMed sources
  that do not report citation counts at all. This affects one comparison metric in E1,
  not the system's core operation (PageRank is computed from the citation graph ATLAS
  itself builds, independent of external citation-count metadata).
- **The three-query evaluation plan is only fully run for one of three queries so far**
  (`iot_safety`). The other two (`federated_learning_medical`, `biomedical`) exercise a
  denser, more citation-rich literature and PubMed specifically, and may show different
  behaviour — reporting only one query's results as if representative would overstate the
  evidence. `federated_learning_medical`'s E2/E3 sweep was attempted and mostly lost to an
  unrelated problem: the laptop's disk hit 4.3GB free partway through, and every config
  after that point either crashed mid-run or wrote nothing before dying (2 of 8 configs
  produced real data: `-pagerank` and `bridge_off`; see TESTING.md E2/E3). Not a design
  flaw in the evaluation harness — it's now hardened to log full diagnostics on failure
  instead of masking them behind a console-encoding crash — just unfinished work.
- **The relation judge is meaningfully weaker at `DIFF_SCOPE` than at any other label**
  (§4.5): 0.38 recall against a hand-labelled sample, systematically misreading "two
  unrelated, independently-invented devices that share surface vocabulary" as
  EXTENDS/SUPPORTS/even CONTRADICTS. This is not a corner case — on this corpus, most
  cross-paper claim pairs genuinely *are* `DIFF_SCOPE` (independent papers, not a single
  research lineage), so this is the single largest source of downstream noise in both
  the contradiction report and detector 5 (unresolved conflicts). It is a prompt/model
  problem, not an architectural one — `judge.v1.md` could plausibly be sharpened with
  explicit negative examples of "different specific systems, same buzzwords" and this
  would be the first thing to try.
- **Gap quality on a shallow corpus is honestly mixed, not uniformly good.** The R3
  expert-assessment tripwire (§4.6) found only 2 of 10 top-ranked gaps on the
  `iot_safety` run genuinely plausible; 4 were wrong because concept extraction missed a
  link the corpus's own evidence already makes (a vocabulary-mismatch problem — e.g.
  "protection" not recognized as the same idea as "personal security" — not a logic bug
  in the detectors or fusion), and 4 were trivial restatements of the corpus's own core
  thesis. This is the honest state of gap quality on a narrow, abstract-only-heavy corpus
  with generic vocabulary; it should not be assumed to generalize to a denser corpus with
  full-text access, where concept extraction has more distinguishing material to work
  with.
- **The dashboard's graph view genuinely does stutter at scale, and the fix that was
  supposed to prevent it (docs/RISKS.md's R6 risk) had never actually been implemented.**
  A headless stress test of the exact layout call the UI uses (`web/scripts/
  stress_test_layout.cjs`) measured 0.5s at 100 synthetic nodes, 11.8s at 500, and 32.6s
  at 1000 — worse-than-linear scaling, confirming the predicted "fine at 50, unusable at
  800" failure mode rather than leaving it as an assumption. The documented mitigation
  ("batch layout every 25 additions") wasn't in the code; every relevant event triggered a
  full graph refetch and full re-layout with no throttling at all. Now fixed with a
  size-aware throttle in `RunView.tsx`: typical runs (6-15 papers) are unaffected and still
  update live, per-event, per CLAUDE.md's own invariant against batching away the live
  build; only once a run's graph passes 100 nodes does refreshing throttle to once every 4
  seconds (always refreshing immediately at run completion, so the final view is never
  stale). This narrows *how often* an expensive re-layout runs; it doesn't make any single
  re-layout faster — a true incremental layout that only positions newly-added nodes is
  the deeper fix and remains future work.
- **The grounding gate's fuzzy-match path was looser than its exact-match path** (§4.4),
  and ATLAS was only as faithful as its PDF text. The single E4 failure traced to a page
  number left mid-sentence by the PDF parser (now stripped). Re-checking every stored fuzzy
  match found the fuzzy path also admitted small wording edits, with one live case (an
  inserted "set"). Both are fixed and covered by regression tests. What remains is the
  underlying dependence on PDF extraction quality: any parser artefact that survives
  normalisation is, by construction, "verbatim" to the gate.

---

## 6. Conclusion and future work

ATLAS set out to test one specific claim: that a literature-review agent which re-scores
what to read next after every paper — following citations, weighing novelty and
contest, occasionally promoting a paper cosine similarity alone would have parked —
covers more of a field's structure than a one-shot retrieve-and-summarize baseline. E1
(§4.1) supports half of that claim: across three queries the loop read a substantially
different set of papers (36–56% overlap with the baseline) and reached 4–60% more of the
reference network than the same number of top-ranked papers — it is genuinely reading
differently, not re-deriving the same ranking. It does not yet support the other half: at 15
papers, citation-cluster coverage was no broader than the baseline's, and bridge promotion
(E3), the mechanism meant to reach new clusters, never fired. Whether breadth appears at larger
scale is the most important open question this project leaves. E7 adds a second,
less commonly reported finding: a run costs nothing on free-tier quotas and at most about
$0.05 at paid rates, and a warm-cache replay reproduces a run exactly with zero LLM calls,
because caching is architectural (§3.2, ADR-004/007) rather than an afterthought.

**What shipped, against the roadmap's own [C]/[D]/[S] labels.** Every [C] (core) item
through Phase 6 is done and live-verified, not just unit-tested: the full harvest →
ingest → forage → judge → gap → synthesis pipeline, the FastAPI backend and React
dashboard, and the grounding gate that is this project's actual thesis (§1.3, §3.3) —
verified end to end via a real browser session, not assumed from passing tests. Within
Phase 7 (evaluation), E1, E7, and E8 are complete; E2 and E3 are complete for one of
three planned queries and partially complete for a second (§5); E4, E5, and E6 — the
three evaluation steps requiring human judgment rather than automation — now have real
first-pass results (§4.4-4.6), produced directly against the actual data rather than
left as placeholder tooling, though they still need a domain-familiar second read before
being treated as final.

**What was cut, deliberately, per the roadmap's own [S] (stretch) label:** the
predicted-links gap detector, saturation/cost charts in the dashboard, graph image
export, and Langfuse tracing. None of these are load-bearing for the central claim above;
cutting them kept the [C] and [D] work — the actual pipeline, the grounding invariant,
the live dashboard, the honest evaluation — on schedule for a fixed-deadline project.

**What's genuinely still open, not cut:** the second and third evaluation queries' full
E2/E3 sweeps (blocked on disk space on the development machine, not a design problem);
the three cached, offline-playable demo runs; and turning the demo script below into a
rehearsed run. None of these change what the system does — they change how convincingly
it can be shown to work under exam conditions.

**Future work**, in rough order of how directly it follows from what this evaluation
already found, rather than as a wishlist: (1) sharpen `judge.v1.md` with explicit
negative examples targeting the DIFF_SCOPE-vs-everything-else confusion §4.5 and §5
identify as the single largest source of downstream noise; (2) run a deep- or
extra-deep-mode crawl (75-200 papers) specifically to test whether bridge promotion
fires at all once Louvain clusters have room to accumulate the reads it requires (§4.3);
(3) re-run this evaluation against a corpus with real full-text access (Docker + GROBID,
on stronger hardware) to see whether the three currently-silent gap detectors and the
concept-vocabulary-mismatch problem in §4.6 are corpus-depth artifacts, as hypothesized,
or something that needs fixing in the extraction logic itself.

---

## Appendix A — Demo script

**Status: a script, not yet a rehearsed run.** The three offline-playable cached demo
runs this depends on (docs/TESTING.md's "unplug the wifi and it still works" test) are
not built yet — this section lays out the arc to record once they are, using details
from real runs already on hand (`iot_safety`, `a0e32253-...` and later re-runs) rather
than invented numbers.

1. **Type the query, watch the graph build live.** `"IoT devices for women safety"` in
   the new-run form (`/`). The dashboard opens on `/runs/:id` and the graph fills in
   paper-by-paper over SSE — this is real incremental writing (§2.2, invariant #6), not a
   progress bar: every node appearing on screen is a row Postgres/Neo4j already committed.
   Narrate: "it just read this paper, extracted its claims, and is already deciding what
   to read next based on what it just learned."
2. **Try to catch a bridge promotion.** Point out in the frontier panel that some
   papers are scored highly by citation-graph position even though they'd rank low on
   cosine similarity alone. Be upfront if none fires during the demo: E3 (§4.3) found
   this genuinely doesn't happen yet at 10-15 paper scale — say so rather than papering
   over it ("we found this ourselves and traced exactly why — the Louvain clusters don't
   grow large enough yet at this scale; it's a known, understood limitation, not a bug we
   missed"). Honesty about a known gap is more convincing than a demo that quietly avoids
   the topic.
3. **Open a claim, show the highlighted verbatim quote in the source PDF** (`/runs/:id/paper/:pid`).
   This is the single most important beat: point at a sentence, then point at the exact
   same sentence highlighted in the PDF viewer. That correspondence — not a description of
   it — is what "no unverified quote survives" (§1.3) actually means.
4. **Show the contradiction report**, two papers' quotes side by side
   (`/runs/:id/report`). If the live run doesn't have one, fall back to a cached run that
   does — a real `CONTRADICTS` relation with both quotes exists in development history
   (§3.3) and should be one of the three cached runs specifically because it has one.
5. **Show the ranked gaps with bounding papers.** Be ready for the honest version of this
   beat too: §4.6 found only 2 of 10 top gaps on this exact corpus hold up as genuinely
   novel on inspection. Picking one of those two for the demo, and being able to explain
   in one sentence *why* it's a real gap (not just that the system says so), is stronger
   than picking the top-ranked one blind.
6. **Ask the chat something outside the corpus. It refuses.** Per docs/TESTING.md: "that
   refusal is the trust argument for the whole system — do not skip it." A concrete
   example already verified in testing (`tests/unit/test_api.py`): a real claim exists in
   the store, but a question with genuinely low cosine similarity to it still gets
   refused rather than answered from the model's own parametric knowledge.

**Remaining before this is demo-ready:** pick and cache 3 runs (one that clearly shows a
contradiction, one representative "typical" run, ideally one deep/extra-deep run if
bridge promotion is re-tested at scale per §6's future work), verify each replays fully
with the network disconnected, and rehearse the actual timing.

## Appendix B — Reproducibility instructions

All commands below assume the lightweight no-Docker setup (README "Quick start") and are
run from the repo root with `PYTHONPATH=src` set (or the Windows equivalent,
`$env:PYTHONPATH="src"` in PowerShell) and the project's virtualenv active.

**Set up once:**
```bash
cp .env.example .env      # fill in an LLM API key + contact email
atlas init-stores          # migrations + Qdrant collections + Neo4j schema
```

**Run a query and inspect it:**
```bash
atlas run "IoT devices for women safety" --mode standard --max-papers 15
atlas show                 # lists recent runs and their run_ids
atlas show <run_id> --claims
```

**E1 — baseline comparison** (needs one completed run_id):
```bash
python evaluation/e1_baseline.py --run-id <run_id>
```

**E2/E3 — ablation + bridge sweep** (long-running — hours; writes a JSON results file,
checkpointing after every config so it survives a crash; `--resume`/`--only` continue a
partial sweep without re-running finished configs):
```bash
python evaluation/e2_e3_ablation.py --query "<query text>" --max-papers 15 \
    --out evaluation/e2_e3_<label>.json
```

**E4 — grounding hand-check sheet:**
```bash
python evaluation/e4_grounding_sample.py --out evaluation/e4_sheet.md
```
Fill in each `- [ ]` checkbox by hand against the actual source paper, then count.

**E5 — judge precision/recall** (pool multiple runs so rare labels like CONTRADICTS have
a chance of appearing):
```bash
atlas judge-eval --run-id <id1>,<id2>,<id3> --export evaluation/e5_sample.jsonl
# fill the "gold" field on each line, then:
atlas judge-eval --score evaluation/e5_sample.jsonl
```

**E6 — gap plausibility (R3 tripwire):**
```bash
python evaluation/e6_gap_review.py --run-id <run_id> \
    --out evaluation/e6_sheet.md --key-out evaluation/e6_key.json
```
Rate each gap in `e6_sheet.md` without looking at `e6_key.json` (it identifies which
detector produced each gap, deliberately withheld from the sheet itself to avoid biasing
the rating), then cross-reference afterward.

**E7 — cost and time** (free — aggregates every completed run already in the local
store, no new crawling):
```bash
python evaluation/e7_cost.py
```

**E8 — reproducibility check:**
```bash
atlas run "<same query>" --mode standard --max-papers <same N>   # run twice
# compare the two runs' graph state — see docs/DECISIONS.md for the exact check used
```

**Tests:**
```bash
pytest -q tests/unit                 # no network, no Docker, <30s
pytest -q -m integration tests/integration   # needs a real NEO4J_URI in .env
```
