"""All cross-stage types. Nothing crosses a stage boundary as a dict.

Change this file first, then `docs/CONTRACTS.md`, then the code — in the same commit.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ─────────────────────────────── enums ────────────────────────────────────────


class SourceName(StrEnum):
    OPENALEX = "openalex"
    ARXIV = "arxiv"
    PUBMED = "pubmed"
    S2 = "semantic_scholar"


class Depth(StrEnum):
    """How much of the paper ATLAS actually has. Abstract-only is first class (ADR-010)."""

    FULL_TEXT = "full_text"
    ABSTRACT_ONLY = "abstract_only"
    METADATA_ONLY = "metadata_only"


FrontierState = Literal["pending", "parked", "reading", "read", "dropped", "failed"]
RelationType = Literal[
    "SUPPORTS", "CONTRADICTS", "EXTENDS", "REPLICATES", "DIFF_SCOPE", "UNRELATED"
]
GapType = Literal[
    "unlinked_concepts",
    "predicted_link",
    "empty_combination",
    "unanswered_call",
    "unresolved_conflict",
    "shared_weakness",
]
SectionName = Literal[
    "abstract", "intro", "related", "methods", "results",
    "discussion", "limitations", "future_work", "conclusion", "other",
]

# ──────────────────────── stage 0: query expansion ────────────────────────────


class Keyword(BaseModel):
    text: str
    tier: Literal["exact", "concept", "adjacent"]


class QueryPlan(BaseModel):
    """Tier-3 (adjacent) keywords surface bridge papers. Never drop them for low hit counts."""

    query: str
    keywords: list[Keyword] = Field(min_length=8, max_length=20)
    year_from: int | None = None
    domain_hint: str | None = None


# ─────────────────────────── stage 1: harvest ─────────────────────────────────


class Author(BaseModel):
    name: str
    author_id: str | None = None
    orcid: str | None = None


class PaperMeta(BaseModel):
    paper_id: str  # canonical; produced only by ids.canonical_id()
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
    pdf_url: str | None = None
    license: str | None = None
    citation_count: int | None = None
    found_via: list[SourceName] = []
    depth: Depth = Depth.METADATA_ONLY


# ────────────────────────── stage 2/3: frontier ───────────────────────────────


class ScoreBreakdown(BaseModel):
    relevance: float = 0.0
    pagerank: float = 0.0
    novelty: float = 0.0
    contest: float = 0.0
    recency: float = 0.0
    bridge_bonus: float = 0.0
    total: float = 0.0


class FrontierEntry(BaseModel):
    run_id: str
    paper: PaperMeta
    state: FrontierState = "pending"
    score: ScoreBreakdown | None = None
    discovered_via: str  # "seed" | "reference_of:<id>" | "citer_of:<id>" | "bridge"
    parked_reason: str | None = None
    read_order: int | None = None


# ───────────────────────── stage 3a: ingestion ────────────────────────────────


class Section(BaseModel):
    """`text` is NORMALIZED. char offsets index the doc's normalized full_text."""

    name: SectionName
    raw_name: str
    text: str
    char_start: int
    char_end: int


class ParsedDoc(BaseModel):
    paper_id: str
    depth: Depth
    structure: Literal["grobid", "flat", "none"]
    full_text: str
    sections: list[Section] = []
    references: list[PaperMeta] = []
    parse_warnings: list[str] = []


class Chunk(BaseModel):
    chunk_id: str
    paper_id: str
    section: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int


# ─────────────────────────── stage 3b: claims ─────────────────────────────────


class ClaimScope(BaseModel):
    """Fill only what the text supports. Never infer — the judge relies on these to
    distinguish a real contradiction from DIFF_SCOPE."""

    what_was_tested: str
    population_or_setting: str | None = None
    method: str | None = None
    dataset_or_context: str | None = None
    metric: str | None = None
    conditions: str | None = None


class Claim(BaseModel):
    claim_id: str
    paper_id: str
    text: str  # paraphrase
    quote: str  # VERBATIM — verified by extract.grounding, dropped if it fails
    section: str
    scope: ClaimScope
    polarity: Literal["positive", "negative", "neutral"] = "neutral"
    confidence: float = Field(default=0.5, ge=0, le=1)
    verified: bool = False
    verify_method: Literal["exact", "fuzzy97", "failed"] | None = None
    quote_char_start: int | None = None
    quote_char_end: int | None = None


# ────────────────────────── stage 3c: relations ───────────────────────────────


class Relation(BaseModel):
    source_claim_id: str
    target_claim_id: str
    type: RelationType
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(max_length=400)
    judged_by: str
    run_id: str


# ──────────────────────────── stage 4: gaps ───────────────────────────────────


class PaperRef(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    role: Literal["a_side", "b_side", "evidence"] = "evidence"


class GapCandidate(BaseModel):
    """min_length=1 on bounding_papers enforces the citation rule in the type system:
    a gap ATLAS cannot show evidence for cannot be constructed."""

    gap_id: str
    type: GapType
    statement: str
    detector_score: float
    bounding_papers: list[PaperRef] = Field(min_length=1)
    entities: list[str] = []
    detail: dict[str, Any] = {}


class RankedGap(GapCandidate):
    gap_score: float
    rank: int
    found_by: list[GapType] = []


# ─────────────────────────── stage 5: report ──────────────────────────────────


class Citation(BaseModel):
    paper_id: str
    title: str
    year: int | None = None


class ReportSection(BaseModel):
    heading: str
    body_md: str
    citations: list[Citation] = []


class RunStats(BaseModel):
    papers_discovered: int = 0
    papers_read: int = 0
    full_text_ratio: float = 0.0
    claims_extracted: int = 0
    claims_dropped_ungrounded: int = 0
    relations_judged: int = 0
    contradictions_found: int = 0
    bridge_promotions: int = 0
    clusters_covered: int = 0
    stop_reason: str = ""
    total_usd: float = 0.0
    wall_clock_seconds: float = 0.0


class Report(BaseModel):
    run_id: str
    query: str
    agreement: ReportSection
    contradictions: ReportSection
    gaps: list[RankedGap] = []
    methodology_timeline: ReportSection
    stats: RunStats
    generated_at: datetime


# ─────────────────────────────── stage 6: API ──────────────────────────────────
# Request/response shapes for `api/routes/*.py` (docs/API.md). `GraphSnapshot`'s
# nodes/edges are intentionally `dict[str, Any]`, not modeled — Cytoscape's element
# format (`{data: {...}, position?: {...}}`) is a third-party UI library's shape, not
# ATLAS's own cross-stage data; the fields inside `data` are ATLAS PaperMeta/Concept
# values, everything else is Cytoscape bookkeeping.


class RunCreateRequest(BaseModel):
    query: str
    mode: Literal["standard", "deep", "extra_deep"] = "standard"
    max_papers: int | None = None


class RunCreateResponse(BaseModel):
    run_id: str


class RunListItem(BaseModel):
    run_id: str
    query: str
    mode: str
    status: str | None = None
    stop_reason: str | None = None
    started_at: str | None = None
    offline: bool = False  # has a saved `atlas snapshot` — replayable with no network


class RunDetail(BaseModel):
    run_id: str
    query: str
    mode: str
    status: str | None = None
    stop_reason: str | None = None
    config_hash: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    keywords: list[str] = []
    stats: RunStats


class GraphSnapshot(BaseModel):
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []


class FrontierRow(BaseModel):
    paper_id: str
    title: str
    state: FrontierState
    score: float | None = None
    relevance: float | None = None
    novelty: float | None = None
    recency: float | None = None
    pagerank: float | None = None
    contest: float | None = None
    discovered_via: str | None = None
    parked_reason: str | None = None
    read_order: int | None = None
    depth: str | None = None


class TimelinePoint(BaseModel):
    """One point per paper read, in read order — the dashboard's saturation/cost
    chart ([S] stretch item). Built from the real `saturation` event each read
    already emits (see db.run_timeline())."""

    read_order: int
    paper_id: str
    title: str
    score: float | None = None
    new_info: float | None = None
    ema: float | None = None
    cumulative_claims: int
    cumulative_usd: float


class PaperDetail(BaseModel):
    paper: PaperMeta
    claims: list[Claim] = []
    relations: list[Relation] = []


class SourceSpan(BaseModel):
    name: str
    char_start: int
    char_end: int


class PaperSource(BaseModel):
    """The normalized text ATLAS read for one paper in one run, rebuilt from its stored
    chunks. Claim `quote_char_start/end` index this text, so the UI can highlight each
    verbatim quote where it sits in the source (the grounding gate, made visible)."""

    paper_id: str
    text: str
    sections: list[SourceSpan] = []
    # where the text came from: "this_run" chunks; "other_run" chunks (chunk points are
    # keyed per paper, so a later run that re-reads a paper re-labels them); or "abstract"
    origin: Literal["this_run", "other_run", "abstract"] = "this_run"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatCitation(BaseModel):
    paper_id: str
    title: str
    quote: str | None = None


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    answer: str
    citations: list[ChatCitation] = []


class Event(BaseModel):
    seq: int
    type: str
    at: str | None = None
    payload: dict[str, Any] = {}


class ServiceHealth(BaseModel):
    name: str
    ok: bool | None  # None = skipped (optional dependency not configured)
    detail: str


class HealthStatus(BaseModel):
    services: list[ServiceHealth]
    healthy: bool  # every required service (currently: postgres/sqlite) is ok
