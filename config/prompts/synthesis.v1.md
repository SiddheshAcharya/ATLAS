# Job D — Synthesis (one pass over the finished graph)

# Version: 1. Bump on ANY edit; the version enters the LLM cache key.

You are writing three sections of a literature-review report for the research question below.
Everything you are given was already read, extracted, and verified by ATLAS — every claim quote
was checked verbatim against the source paper before it reached you. You must not add any fact,
paper, method, or number that is not present in the material below. This is the project's core
integrity rule: nothing in the report that ATLAS did not actually read.

## Research question
{query}

## Agreement clusters
Groups of papers whose claims were judged SUPPORTS / EXTENDS / REPLICATES each other.
{agreement_summary}

## Contradictions
Pairs of papers whose claims were judged CONTRADICTS. `resolved: true` means a later paper in
this corpus cites both and may have settled it — say so if relevant.
{contradiction_summary}

## Method / dataset timeline
Chronological usage of methods and datasets/settings across the corpus.
{timeline_summary}

## Task
Write three short markdown sections:

1. **agreement_body_md** — what the field agrees on. Group related findings; for every claim you
   mention, cite the paper by its id in square brackets, e.g. `[paper_id]`. If there are no
   agreement clusters, say so plainly instead of inventing one.
2. **contradictions_body_md** — where the field disagrees, and whether it's been resolved. Cite
   both papers' ids for every contradiction you describe. If there are none, say so.
3. **methodology_timeline_body_md** — how methods/datasets were adopted over time, in prose (not
   just repeating the table). Cite paper ids for specific claims about who used what and when. If
   the corpus has no extracted methods/datasets (common for abstract-only papers, per ATLAS's
   design), say that plainly rather than guessing.

Each section: 2–5 sentences per point, no filler, no "as is well known" — only what is in the
material above. Every paper_id you cite must be one that actually appears above.

## Output
One JSON object matching the schema: `agreement_body_md`, `contradictions_body_md`,
`methodology_timeline_body_md` (all strings, markdown).
