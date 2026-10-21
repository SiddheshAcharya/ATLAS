# Job C — Relation judging
# Version: 2. Bump on ANY edit.
# v2 (2026-09-28): E5 found the v1 judge reading shared topic vocabulary between two
# independent systems as SUPPORTS / EXTENDS / CONTRADICTS. v2 makes "are these about the
# same thing?" the first decision and gives worked examples. The examples are deliberately
# from an unrelated domain (farm sensing) so they cannot leak into the E5 evaluation pairs.

Decide the relationship between two claims from two different papers.

## Claim A — {paper_a_title} ({paper_a_year})
Statement: {claim_a_text}
Quote: "{claim_a_quote}"
Scope: {claim_a_scope}

## Claim B — {paper_b_title} ({paper_b_year})
Statement: {claim_b_text}
Quote: "{claim_b_quote}"
Scope: {claim_b_scope}

## Step 1 — what is each claim about?
Name the object of each claim in a few words. The object is one of:
- **a specific system, device, model or study that its own paper built or ran** ("our wristband",
  "the proposed network", "this trial"), or
- **a finding or statement about the world or the field** ("most devices use GPS", "violence is
  underreported", "method X beats method Y on dataset Z").

Two papers that each describe **their own** system are about **different objects**, even when the
systems do the same job with similar parts. A description of one system's design is not evidence
about another system's design.

## Step 2 — choose the label
- `SUPPORTS` — both claims are about **the same finding or question**, under comparable scope, and B
  gives independent evidence that A's claim is true. Agreeing on a topic, a motivation or a
  component list is not support.
- `CONTRADICTS` — both claims are about **the same finding or question**, the scopes are genuinely
  comparable, and B asserts something that cannot be true if A is true.
- `EXTENDS` — B takes **A's own specific result or method** further (a new setting, scale or
  population for that same result or method). Two independent systems that share techniques or
  components do not extend each other.
- `REPLICATES` — B is a direct reproduction of A's setup and reports the same outcome.
- `DIFF_SCOPE` — the claims address a related question but concern **different objects**
  (different systems, populations, datasets, metrics or conditions), so neither is evidence for
  or against the other. This includes claims that look contradictory only because their scopes
  differ.
- `UNRELATED` — the claims address different questions.

## Worked examples (a different field, on purpose)
1. A: "Our soil probe uses a capacitive moisture sensor and a LoRa radio." B: "The proposed
   irrigation node is built on an ESP32 with a resistive moisture sensor." → `DIFF_SCOPE`. Two
   different devices; different parts are not a disagreement, and similar parts are not support.
2. A: "Our probe measures volumetric water content." B: "The node monitors soil moisture and
   temperature and alerts the farmer by SMS." → `DIFF_SCOPE`, not `EXTENDS`. B did not build on
   A's probe; both simply work on soil monitoring.
3. A: "Capacitive sensors drift less than resistive sensors over a season." B: "In our 12-month
   field test, capacitive sensors drifted 3% and resistive sensors 11%." → `SUPPORTS`. Same
   finding, comparable scope, independent evidence.
4. A: "Capacitive sensors drift less than resistive sensors over a season." B: "In sandy soil,
   resistive sensors drifted less than capacitive ones." → `DIFF_SCOPE` (soil type differs),
   unless A's scope already covers sandy soil, in which case `CONTRADICTS`.
5. A: "Crop losses from drought are rising in the region." B: "Our node sends an alert when
   moisture falls below a threshold." → `DIFF_SCOPE`. A states the problem; B describes one
   system aimed at it. Sharing a motivation is not support.
6. A: "Our probe measures volumetric water content." B: "Farmers rarely read equipment manuals."
   → `UNRELATED`.

## Critical guidance
A false `CONTRADICTS` corrupts the final report: downstream analysis treats it as an unresolved
disagreement in the field. Before `CONTRADICTS`, check that both claims are about the same object
and that every scope field is comparable. If not, the answer is `DIFF_SCOPE`.

`DIFF_SCOPE` and `UNRELATED` are good answers and often the right ones. Do not manufacture a
relationship.

Your rationale must name the object of each claim. For `CONTRADICTS`, state exactly what is
incompatible. For `DIFF_SCOPE`, name what differs (the object, or which scope dimension).

## Output
One JSON object matching the Relation schema: type, confidence (0-1), rationale (max 400 chars).
