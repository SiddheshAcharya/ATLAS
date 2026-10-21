# Job B — Claim extraction
# Version: 1. Bump the version on ANY edit; the version enters the LLM cache key.

You are extracting verifiable claims from one section of a research paper.

## Paper
Title: {title}
Year: {year}
Venue: {venue}

## Section: {section_name}
```
{section_text}
```

## What counts as a claim
A statement the paper asserts about its own findings, or about prior work's findings, that could
in principle be checked. Not background definitions. Not motivation. Not future work (that is
extracted separately).

## Rules — these are hard requirements
1. `quote` MUST be copied character-for-character from the section text above. No ellipses, no
   reformatting, no fixing typos or spacing, no joining two separate sentences. An automated
   verifier compares your quote against the source and DISCARDS any claim that does not match
   exactly. Paraphrasing here destroys the claim.
2. Quotes must be between 15 and 400 characters. Pick the single sentence that carries the claim.
3. `text` is the claim restated in your own words — this is where you paraphrase, never in `quote`.
4. `scope` records what the claim is actually about: what was tested, on what population or in what
   setting, using what method, on what data or context, measured by what metric, under what
   conditions. Fill only the fields the text supports; leave the rest null. Do not infer.
5. If the section contains no defensible claim, return an empty list. This is a normal and correct
   answer, especially for Related Work and Introduction sections.
6. Extract at most 6 claims from this section. Prefer the strongest and most specific.

## Output
A JSON list matching the Claim schema. No prose before or after.
