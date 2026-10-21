# CONTRACTS

Every cross-stage type lives in `src/atlas/contracts.py`. Nothing crosses a stage boundary as a
dict. If a change here is needed, change it here first, then the code, in the same commit.

```python
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl

# ─── identifiers ────────────────────────────────────────────────────────────
class SourceName(StrEnum):
    OPENALEX = "openalex"; ARXIV = "arxiv"; PUBMED = "pubmed"; S2 = "semantic_scholar"

class Depth(StrEnum):
    FULL_TEXT = "full_text"; ABSTRACT_ONLY = "abstract_only"; METADATA_ONLY = "metadata_only"

# ─── stage 0: query expansion ───────────────────────────────────────────────
class Keyword(BaseModel):
    text: str
    tier: Literal["exact", "concept", "adjacent"]

class QueryPlan(BaseModel):
    query: str
    keywords: list[Keyword] = Field(min_length=8, max_length=20)
    year_from: int | None = None
    domain_hint: str | None = None          # e.g. "engineering" | "biomedical"

# ─── stage 1: harvest ───────────────────────────────────────────────────────
class Author(BaseModel):
    name: str
    author_id: str | None = None
    orcid: str | None = None

class PaperMeta(BaseModel):
    paper_id: str                            # canonical, from ids.canonical_id()
    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    authors: list[Author] = []
    doi: str | None = None
    arxiv_id: str | None = None
    pmid: str | None = None
    openalex_id: str | None = None
    s2_corpus_id: str | None = None
    pdf_url: HttpUrl | None = None
    citation_count: int | None = None
    found_via: list[SourceName] = []
    depth: Depth = Depth.METADATA_ONLY

# ─── stage 2/3: frontier ────────────────────────────────────────────────────
class ScoreBreakdown(BaseModel):
    relevance: float; pagerank: float; novelty: float
    contest: float;   recency: float; bridge_bonus: float = 0.0
    total: float

class FrontierEntry(BaseModel):
    run_id: str
    paper: PaperMeta
    state: Literal["pending","parked","reading","read","dropped","failed"]
    score: ScoreBreakdown | None = None
    discovered_via: str                      # "seed" | "reference_of:<id>" | "citer_of:<id>" | "bridge"
    parked_reason: str | None = None
    read_order: int | None = None

# ─── stage 3a: ingestion ────────────────────────────────────────────────────
class Section(BaseModel):
    name: str                                # normalized: abstract|intro|related|methods|results|
                                             # discussion|limitations|future_work|conclusion|other
    raw_name: str
    text: str                                # NORMALIZED text (see §Normalization)
    char_start: int                          # offsets into the doc's normalized full text
    char_end: int

class ParsedDoc(BaseModel):
    paper_id: str
    depth: Depth
    structure: Literal["grobid","flat","none"]
    full_text: str                           # normalized
    sections: list[Section]
    references: list[PaperMeta] = []         # parsed from the bibliography
    parse_warnings: list[str] = []

class Chunk(BaseModel):
    chunk_id: str
    paper_id: str
    section: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int

# ─── stage 3b: claims ───────────────────────────────────────────────────────
class ClaimScope(BaseModel):
    what_was_tested: str
    population_or_setting: str | None = None
    method: str | None = None
    dataset_or_context: str | None = None
    metric: str | None = None
    conditions: str | None = None

class Claim(BaseModel):
    claim_id: str
    paper_id: str
    text: str                                # the claim, in the model's words
    quote: str                               # VERBATIM from the source
    section: str
    scope: ClaimScope
    polarity: Literal["positive","negative","neutral"] = "neutral"
    confidence: float = Field(ge=0, le=1)
    verified: bool = False
    verify_method: Literal["exact","fuzzy97","failed"] | None = None
    quote_char_start: int | None = None
    quote_char_end: int | None = None

# ─── stage 3c: relations ────────────────────────────────────────────────────
RelationType = Literal["SUPPORTS","CONTRADICTS","EXTENDS","REPLICATES","DIFF_SCOPE","UNRELATED"]

class Relation(BaseModel):
    source_claim_id: str
    target_claim_id: str
    type: RelationType
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(max_length=400)
    judged_by: str                           # model id
    run_id: str

# ─── stage 4: gaps ──────────────────────────────────────────────────────────
GapType = Literal["unlinked_concepts","predicted_link","empty_combination",
                  "unanswered_call","unresolved_conflict","shared_weakness"]

class PaperRef(BaseModel):
    paper_id: str
    title: str
    year: int | None
    role: Literal["a_side","b_side","evidence"] = "evidence"

class GapCandidate(BaseModel):
    gap_id: str
    type: GapType
    statement: str
    detector_score: float
    bounding_papers: list[PaperRef] = Field(min_length=1)   # enforced by the schema itself
    entities: list[str] = []
    detail: dict[str, Any] = {}

class RankedGap(GapCandidate):
    gap_score: float
    rank: int
    found_by: list[GapType]

# ─── stage 5: report ────────────────────────────────────────────────────────
class Citation(BaseModel):
    paper_id: str; title: str; year: int | None

class ReportSection(BaseModel):
    heading: str
    body_md: str
    citations: list[Citation]

class Report(BaseModel):
    run_id: str
    query: str
    agreement: ReportSection
    contradictions: ReportSection
    gaps: list[RankedGap]
    methodology_timeline: ReportSection
    stats: RunStats
    generated_at: datetime

class RunStats(BaseModel):
    papers_discovered: int
    papers_read: int
    full_text_ratio: float
    claims_extracted: int
    claims_dropped_ungrounded: int
    relations_judged: int
    bridge_promotions: int
    stop_reason: str
    total_usd: float
    wall_clock_seconds: float

# ─── stage 6: API (docs/API.md) ─────────────────────────────────────────────
# GraphSnapshot.nodes/edges stay `dict[str, Any]` on purpose — Cytoscape's element
# format is a third-party UI shape, not ATLAS's own cross-stage data.
class RunCreateRequest(BaseModel):
    query: str
    mode: Literal["standard", "deep", "extra_deep"] = "standard"
    max_papers: int | None = None

class RunCreateResponse(BaseModel):
    run_id: str

class RunListItem(BaseModel):
    run_id: str; query: str; mode: str
    status: str | None; stop_reason: str | None; started_at: str | None
    offline: bool = False          # has a saved `atlas snapshot` (replayable, no network)

class RunDetail(BaseModel):
    run_id: str; query: str; mode: str
    status: str | None; stop_reason: str | None; config_hash: str | None
    started_at: str | None; finished_at: str | None
    keywords: list[str]
    stats: RunStats

class GraphSnapshot(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]

class FrontierRow(BaseModel):
    paper_id: str; title: str; state: FrontierState
    score: float | None; relevance: float | None; novelty: float | None
    recency: float | None; pagerank: float | None; contest: float | None
    discovered_via: str | None; parked_reason: str | None
    read_order: int | None; depth: str | None

class PaperDetail(BaseModel):
    paper: PaperMeta
    claims: list[Claim]
    relations: list[Relation]

class PaperSource(BaseModel):      # GET /runs/{id}/papers/{pid}/source
    paper_id: str
    text: str                      # normalized text ATLAS read; Claim.quote_char_* index it
    sections: list[SourceSpan]     # SourceSpan: name, char_start, char_end
    origin: Literal["this_run", "other_run", "abstract"]

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]; content: str

class ChatCitation(BaseModel):
    paper_id: str; title: str; quote: str | None

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage]

class ChatResponse(BaseModel):
    answer: str
    citations: list[ChatCitation]

class Event(BaseModel):                 # one SSE frame / one `events` table row
    seq: int; type: str; at: str | None
    payload: dict[str, Any]

class ServiceHealth(BaseModel):
    name: str; ok: bool | None; detail: str   # ok=None means skipped, optional dep

class HealthStatus(BaseModel):
    services: list[ServiceHealth]
    healthy: bool
```

---

## Normalization (`ingest/normalize.py`)

Applied **once**, immediately after text extraction. Everything downstream — chunks, offsets,
claims, the grounding gate — operates on normalized text. The original is kept only for display.

1. Unicode NFKC (collapses ligatures: ﬁ → fi).
2. Join hyphenated line breaks: `r"(\w)-\n(\w)" → r"\1\2"`.
3. Newlines within a paragraph → space; blank lines preserved as paragraph separators.
4. Unify quotes (' ' " " → ' ") and dashes (– — → -).
5. Collapse runs of whitespace to a single space.
6. Strip page headers/footers repeated on ≥ 3 pages.

Normalization must be **idempotent** — `normalize(normalize(x)) == normalize(x)`. Test it.

---

## The grounding gate (`extract/grounding.py`)

```python
def verify(claim: Claim, section_text: str) -> Claim:
    """Returns the claim with verified/verify_method/offsets set.
    Never mutates the quote. Never asks the LLM to fix anything."""
```

Order of attempts:
1. **Exact substring** of `normalize(quote)` in `normalize(section_text)` → `verify_method="exact"`,
   record offsets.
2. **`rapidfuzz.fuzz.partial_ratio` ≥ 97** → `verify_method="fuzzy97"`, map the matched span back
   to offsets via `rapidfuzz.fuzz.partial_ratio_alignment`. Log every fuzzy pass with the diff.
3. Otherwise `verified=False`, `verify_method="failed"`. **The claim is dropped** — not written to
   Neo4j, not embedded, not passed to the judge. Increment
   `RunStats.claims_dropped_ungrounded`.

**Numeric guard.** On the fuzzy path only, every numeric token in the quote must also appear in
the matched source span. Fuzzy matching is for PDF noise, not for digits — a single altered digit
scores ~99 on `partial_ratio` and is precisely the fabrication the gate exists to catch.

**Wording guard.** Also on the fuzzy path: after lowercasing and removing whitespace, quote marks
and hyphens between two letters from both sides (and full stops/commas at the quote's two ends),
the quote must be an *exact* substring of the source near the aligned span. So the fuzzy path
forgives PDF formatting noise ("keycharacteristics", "fixedrank"), a capitalised mid-sentence
start, and an added full stop, but never a changed or inserted letter, digit or symbol
("increased"→"decreased", `p > 0.05`→`p < 0.05`, `-0.3`→`0.3`, "is too high"→"is set too
high", all ≥ 97 on `partial_ratio`). Offsets come from that exact match.

Also reject a quote that is shorter than 15 characters or longer than 400 — the first is not
evidence, the second is the model copying a paragraph to game the check.

---

## LLM job schemas (`llm/schemas.py`)

All jobs use `instructor` for structured output, `temperature=0`, and a prompt file version that
enters the cache key.

| Job | Prompt file | Input | Output model |
|---|---|---|---|
| A. keywords | `prompts/keywords.v1.md` | user query | `QueryPlan` |
| B. claims | `prompts/claims.v1.md` | one section's text + paper metadata | `list[Claim]` (pre-verification) |
| C. judge | `prompts/judge.v1.md` | claim pair + both scopes + both papers' year/venue | `Relation` |
| D. synthesis | `prompts/synthesis.v1.md` | serialized graph summary + ranked gaps | `Report` |

**Job B rules baked into the prompt.** Extract only claims the paper *asserts about its own or
prior findings*. The `quote` field must be copied character-for-character from the provided text —
no ellipses, no reformatting, no correcting typos. If no defensible claim exists in a section,
return an empty list; an empty list is a valid and common answer for Related Work.

**Job C rules.** `DIFF_SCOPE` is the answer whenever two claims look contradictory but were
measured on different populations, metrics, or conditions — this label exists precisely to prevent
inflating the contradiction count, which detector 5 depends on. `UNRELATED` must be freely
available as an output; a judge that never says "unrelated" is a judge that is guessing.
