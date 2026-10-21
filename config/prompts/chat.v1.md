# Job F — Grounded chat
# Version: 1. Bump on ANY edit; the version enters the LLM cache key.

Answer the question below using ONLY the claim snippets provided. Every one of these snippets
was verbatim-verified against its source paper before ATLAS accepted it (the grounding gate) —
you are not being shown raw, unchecked text.

## Conversation so far
{history}

## Question
{question}

## Claim snippets from papers ATLAS actually read in this run
{snippets}

## Rules
1. Use only the snippets above. Do not add anything from your own training knowledge, even if
   you are confident it is true — this run's graph is the only source of truth here.
2. Every claim in your answer must be traceable to at least one snippet. List the `paper_id`s you
   actually drew on in `cited_paper_ids` — every id there must be one that appears above.
3. If the snippets do not actually address the question, say so plainly instead of stretching a
   tangential snippet to fit. A short "the papers I read don't address this" is a correct and
   good answer, not a failure.
4. Do not restate the snippets verbatim — synthesize an answer in your own words, still
   attributable to them.

## Output
One JSON object matching the schema: `answer` (string), `cited_paper_ids` (list of strings).
