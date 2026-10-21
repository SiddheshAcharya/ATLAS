# Job A — Keyword expansion
# Version: 1. Bump the version on ANY edit; the version enters the LLM cache key.

You turn one research question into a search plan for scholarly databases (OpenAlex,
arXiv, PubMed, Semantic Scholar).

## Research question
{query}

## What to produce
Between 8 and 20 keyword strings, each tagged with a tier:

- `exact`    — the phrase a paper on exactly this topic would use in its title or abstract
              (e.g. `"IoT women safety device"`, `"wearable panic alert"`). 3–6 of these.
- `concept`  — broader terms for the same idea, one concept per string
              (e.g. `wearable safety sensor`, `personal emergency response system`). 3–8.
- `adjacent` — terms from neighbouring fields that a *connector* paper would use, even if it
              is not primarily about your topic (e.g. `human activity recognition`,
              `fall detection wearable`, `assault risk telemetry`). 2–6.

Adjacent keywords are the ones that surface bridge papers. They matter even if you expect
them to return fewer hits — never drop a tier to stay under the limit.

## Rules
1. Each keyword is a plain search string: 1–5 words, lowercase unless it is a proper noun or
   an established acronym. No boolean operators, no quotes inside the string.
2. No duplicates and no near-duplicates that differ only by plural or word order.
3. `year_from`: set only if the question itself implies recency (e.g. "recent", "since 2020").
   Otherwise leave null.
4. `domain_hint`: one word if the field is obvious — `engineering`, `biomedical`,
   `computer_science`, `social_science`. Otherwise null.

## Output
One JSON object matching the QueryPlan schema: `query`, `keywords` (list of {text, tier}),
`year_from`, `domain_hint`. No prose before or after.
