# Job E — Label a recurring-weakness cluster
# Version: 1. Bump the version on ANY edit; the version enters the LLM cache key.

The sentences below are limitation statements from different papers. They were grouped
together because they describe essentially the same recurring weakness.

## Sentences
{sentences}

## Task
Write a short label (3–8 words) naming this shared weakness, suitable as a graph node
label — e.g. "small, non-diverse participant samples" or "no outdoor GPS accuracy testing".
Describe the weakness itself, not the papers. No trailing punctuation.

## Output
One JSON object matching the schema: `label` (string).
