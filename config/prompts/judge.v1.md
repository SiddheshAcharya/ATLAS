# Job C — Relation judging
# Version: 1. Bump on ANY edit.

Decide the relationship between two claims from two different papers.

## Claim A — {paper_a_title} ({paper_a_year})
Statement: {claim_a_text}
Quote: "{claim_a_quote}"
Scope: {claim_a_scope}

## Claim B — {paper_b_title} ({paper_b_year})
Statement: {claim_b_text}
Quote: "{claim_b_quote}"
Scope: {claim_b_scope}

## Labels
- `SUPPORTS` — B provides evidence consistent with A, in a comparable scope.
- `CONTRADICTS` — B asserts something that cannot be true if A is true, **and the scopes are
  genuinely comparable**.
- `EXTENDS` — B builds on A: same direction, new setting, method, or scale.
- `REPLICATES` — B is a direct reproduction attempt of A's setup.
- `DIFF_SCOPE` — the claims appear to conflict but were measured on different populations,
  metrics, datasets, or conditions, so they are not actually in conflict.
- `UNRELATED` — no meaningful relationship.

## Critical guidance
`DIFF_SCOPE` exists to stop false contradictions. Before you answer `CONTRADICTS`, check every
scope field. If they differ in population, metric, dataset, or conditions, the answer is
`DIFF_SCOPE`, not `CONTRADICTS`. Downstream analysis treats contradictions as unresolved
disagreements in the field, so a false positive here corrupts the final report.

`UNRELATED` is a good answer. Most pairs are unrelated. Do not manufacture a relationship.

When you answer `CONTRADICTS`, your rationale must state exactly what is incompatible.
When you answer `DIFF_SCOPE`, your rationale must name which scope dimension differs.

## Output
One JSON object matching the Relation schema: type, confidence (0-1), rationale (max 400 chars).
