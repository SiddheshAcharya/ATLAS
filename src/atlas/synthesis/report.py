"""Job D — one-pass synthesis (docs/GAP_DETECTORS.md Output, ROADMAP Phase 5).

Everything the LLM sees is built deterministically in Python first: agreement clusters
(connected components over SUPPORTS/EXTENDS/REPLICATES claim edges), contradiction pairs
(with both verbatim quotes and resolver status), the ranked gap list (already computed by
gaps/fusion.py — never rewritten here, so its citation guarantees can't be broken), and a
method/dataset timeline table. One LLM call turns the first three into readable prose;
the citations on each ReportSection are built from the same deterministic data, not
parsed out of the LLM's prose, so invariant 3 ("every sentence carries a paper_id") holds
structurally rather than by trusting the model.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel

from atlas.contracts import Citation, PaperRef, RankedGap, Report, ReportSection, RunStats
from atlas.gaps.common import DetectorConfig
from atlas.gaps.fusion import run_detectors
from atlas.llm.client import LLMClient
from atlas.llm.schemas import render_prompt
from atlas.store import db
from atlas.store.graph import GraphStore

log = structlog.get_logger(__name__)


class _SynthesisOutput(BaseModel):
    agreement_body_md: str
    contradictions_body_md: str
    methodology_timeline_body_md: str


# ── deterministic graph summary ──────────────────────────────────────────────


def _agreement_clusters(run_id: str, graph: GraphStore) -> list[dict[str, Any]]:
    pairs = graph.agreement_pairs(run_id)
    if not pairs:
        return []
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for row in pairs:
        union(str(row["pa"]), str(row["pb"]))

    by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        by_root[find(str(row["pa"]))].append(row)

    clusters: list[dict[str, Any]] = []
    for rows in by_root.values():
        papers = sorted({str(r["pa"]) for r in rows} | {str(r["pb"]) for r in rows})
        clusters.append({"papers": papers, "pairs": rows})
    clusters.sort(key=lambda c: len(c["papers"]), reverse=True)
    return clusters


def _contradictions(run_id: str, graph: GraphStore) -> list[dict[str, Any]]:
    pairs = graph.contradiction_pairs(run_id)
    out = []
    for row in pairs:
        year = max(
            (v for v in (row.get("ya"), row.get("yb")) if isinstance(v, int)), default=None
        )
        resolver = graph.has_resolver(
            str(row["pa"]), str(row["pb"]), year if year is not None else 0
        )
        out.append({**row, "resolved": resolver is not None, "resolver": resolver})
    return out


def _methodology_timeline(
    run_id: str, graph: GraphStore, attrs: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    methods, datasets, _tried = graph.method_dataset_usage(run_id)
    rows: list[dict[str, Any]] = []
    for kind, entities in (("method", methods), ("dataset", datasets)):
        for _id, (label, papers) in entities.items():
            raw_years = [attrs.get(p, {}).get("year") for p in papers]
            years: list[int] = [y for y in raw_years if isinstance(y, int)]
            rows.append(
                {
                    "kind": kind, "label": label, "paper_ids": papers,
                    "papers": len(papers),
                    "first_year": min(years) if years else None,
                    "last_year": max(years) if years else None,
                }
            )
    rows.sort(key=lambda r: (r["first_year"] is None, r["first_year"] or 0))
    return rows


# ── prompt-facing text rendering ─────────────────────────────────────────────


def _fmt_pair(row: dict[str, Any]) -> str:
    ya = row.get("ya", "n.d.")
    yb = row.get("yb", "n.d.")
    return (
        f'- [{row["pa"]}] "{row.get("ta", row["pa"])}" ({ya}): {row.get("claim_a", "")!r}\n'
        f'  [{row["pb"]}] "{row.get("tb", row["pb"])}" ({yb}): {row.get("claim_b", "")!r}'
    )


def _render_agreement(clusters: list[dict[str, Any]]) -> str:
    if not clusters:
        return "(none found — no SUPPORTS/EXTENDS/REPLICATES relations survived judging.)"
    lines = []
    for i, c in enumerate(clusters, 1):
        lines.append(f"### Cluster {i} — {len(c['papers'])} papers: {', '.join(c['papers'])}")
        for row in c["pairs"][:6]:
            lines.append(_fmt_pair(row))
    return "\n".join(lines)


def _render_contradictions(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(none found — no CONTRADICTS relations survived judging.)"
    lines = []
    for row in rows:
        lines.append(_fmt_pair(row))
        lines.append(f"  resolved: {row['resolved']}")
    return "\n".join(lines)


def _render_timeline(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "(no methods/datasets extracted — likely an abstract-only-heavy corpus; "
            "concept extraction only scopes methods/datasets to real GROBID sections.)"
        )
    lines = []
    for r in rows:
        span = f"{r['first_year']}-{r['last_year']}" if r["first_year"] else "n.d."
        lines.append(
            f"- [{r['kind']}] \"{r['label']}\" — {r['papers']} paper(s), {span}, "
            f"papers: {', '.join(r['paper_ids'])}"
        )
    return "\n".join(lines)


def _citations(paper_ids: set[str], attrs: dict[str, dict[str, Any]]) -> list[Citation]:
    return [
        Citation(
            paper_id=pid,
            title=str(attrs.get(pid, {}).get("title") or pid),
            year=attrs.get(pid, {}).get("year"),
        )
        for pid in sorted(paper_ids)
    ]


# ── orchestration ─────────────────────────────────────────────────────────────


def build_report(
    run_id: str,
    *,
    graph: GraphStore | None = None,
    client: LLMClient | None = None,
    gaps: list[RankedGap] | None = None,
) -> Report:
    own_graph = graph is None
    graph = graph or GraphStore()
    client = client or LLMClient(run_id=run_id)
    started = time.monotonic()
    try:
        summary = db.run_summary(run_id)
        if summary is None:
            raise ValueError(f"no run {run_id!r}")

        attrs = graph.paper_attrs(run_id)
        clusters = _agreement_clusters(run_id, graph)
        contradictions = _contradictions(run_id, graph)
        timeline = _methodology_timeline(run_id, graph, attrs)
        ranked_gaps = (
            gaps if gaps is not None else run_detectors(run_id, graph, cfg=DetectorConfig.load())
        )

        prompt = render_prompt(
            "synthesis.v1.md",
            query=summary["query"],
            agreement_summary=_render_agreement(clusters),
            contradiction_summary=_render_contradictions(contradictions),
            timeline_summary=_render_timeline(timeline),
        )
        result = client.complete(
            "synthesis", messages=[{"role": "user", "content": prompt}],
            response_model=_SynthesisOutput,
        )
        synth: _SynthesisOutput = result.value

        agreement_papers = {pid for c in clusters for pid in c["papers"]}
        contradiction_papers = {str(r["pa"]) for r in contradictions} | {
            str(r["pb"]) for r in contradictions
        }
        timeline_papers = {pid for r in timeline for pid in r["paper_ids"]}

        max_gaps = DetectorConfig.load().max_gaps
        report = Report(
            run_id=run_id,
            query=summary["query"],
            agreement=ReportSection(
                heading="What the field agrees on",
                body_md=synth.agreement_body_md,
                citations=_citations(agreement_papers, attrs),
            ),
            contradictions=ReportSection(
                heading="Where the field disagrees",
                body_md=synth.contradictions_body_md,
                citations=_citations(contradiction_papers, attrs),
            ),
            gaps=ranked_gaps[:max_gaps],
            methodology_timeline=ReportSection(
                heading="Methods and datasets over time",
                body_md=synth.methodology_timeline_body_md,
                citations=_citations(timeline_papers, attrs),
            ),
            stats=run_stats(
                run_id, graph=graph, summary=summary, wall_clock_seconds=time.monotonic() - started
            ),
            generated_at=datetime.now(UTC),
        )
        log.info(
            "synthesis.report_built", run_id=run_id, agreement_clusters=len(clusters),
            contradictions=len(contradictions), gaps=len(report.gaps),
        )
        return report
    finally:
        if own_graph:
            graph.close()


def run_stats(
    run_id: str,
    *,
    graph: GraphStore | None = None,
    summary: dict[str, Any] | None = None,
    wall_clock_seconds: float = 0.0,
) -> RunStats:
    """Shared by build_report() and GET /runs/{id} (api/routes/runs.py) — one place that
    knows how to turn Postgres + (if available) Neo4j into a RunStats snapshot, so the
    two never compute it differently. `graph` is optional: a mid-run poll from the API
    shouldn't pay for a Neo4j round trip it doesn't need (clusters_covered is 0 without one)."""
    summary = summary if summary is not None else db.run_summary(run_id)
    if summary is None:
        raise ValueError(f"no run {run_id!r}")
    states: dict[str, int] = summary["frontier_states"]
    reads = summary["reads"]
    papers_discovered = sum(states.values())
    papers_read = states.get("read", len(reads))
    full_text = sum(1 for r in reads if r["depth"] == "full_text")
    rel_by_type: dict[str, int] = summary["relations_by_type"] or {}

    dropped = 0
    bridge_promotions = 0
    try:
        import sqlalchemy as sa

        from atlas.store.db import Event, Frontier, session_scope

        with session_scope() as s:
            payloads: list[Any] = list(
                s.execute(
                    sa.select(Event.payload).where(
                        Event.run_id == run_id, Event.type == "saturation"
                    )
                ).scalars().all()
            )
            bridge_promotions = s.execute(
                sa.select(sa.func.count()).select_from(Frontier).where(
                    Frontier.run_id == run_id, Frontier.discovered_via == "bridge"
                )
            ).scalar_one()
        dropped = sum(int((p or {}).get("claims_dropped") or 0) for p in payloads)
    except Exception as e:  # stats are best-effort, never block the report
        log.warning("synthesis.stats_query_failed", error=str(e))

    cluster_ids: set[object] = set()
    if graph is not None:
        attrs = graph.paper_attrs(run_id)
        cluster_ids = {
            a.get("cluster_id") for a in attrs.values() if a.get("cluster_id") is not None
        }

    return RunStats(
        papers_discovered=papers_discovered,
        papers_read=papers_read,
        full_text_ratio=round(full_text / papers_read, 3) if papers_read else 0.0,
        claims_extracted=sum(r["claims"] for r in reads) + dropped,
        claims_dropped_ungrounded=dropped,
        relations_judged=sum(rel_by_type.values()),
        contradictions_found=rel_by_type.get("CONTRADICTS", 0),
        bridge_promotions=bridge_promotions,
        clusters_covered=len(cluster_ids),
        stop_reason=summary["stop_reason"] or "",
        total_usd=db.run_cost(run_id),  # fresh, not the pre-synthesis-call snapshot
        wall_clock_seconds=round(wall_clock_seconds, 1),
    )


def _ranked_gap_from_row(row: dict[str, Any]) -> RankedGap:
    """Caller must have already dropped rows with no bounding papers — GapCandidate's
    own min_length=1 validation (the citation-rule guard, contracts.py) will raise if one
    slips through anyway, which is correct: fabricating a fake bounding paper to satisfy
    the constraint would violate invariant 2, not honor it."""
    bounding_raw = row["bounding_papers"]
    assert isinstance(bounding_raw, list)
    bounding = [PaperRef(**b) for b in bounding_raw]

    gap_score_raw = row.get("gap_score")
    gap_score = float(gap_score_raw) if isinstance(gap_score_raw, (int, float)) else 0.0

    rank_raw = row.get("rank")
    rank = int(rank_raw) if isinstance(rank_raw, (int, float)) else 0

    found_by_raw = row.get("found_by")
    found_by = list(found_by_raw) if isinstance(found_by_raw, list) else []

    return RankedGap(
        gap_id=str(row["gap_id"]),
        type=str(row["type"]),
        statement=str(row["statement"]),
        detector_score=gap_score,  # not persisted separately from gap_score — see gaps_for()
        bounding_papers=bounding,
        gap_score=gap_score,
        rank=rank,
        found_by=found_by,
    )


def ranked_gaps_with_evidence(run_id: str) -> list[RankedGap]:
    """Persisted gaps for a run (Neo4j), dropping any with no bounding papers."""
    with GraphStore() as g:
        rows = g.gaps_for(run_id)
    return [_ranked_gap_from_row(r) for r in rows if r.get("bounding_papers")]


# ── markdown export ───────────────────────────────────────────────────────────


def _bounding_line(p: PaperRef) -> str:
    year = f" ({p.year})" if p.year else ""
    return f"- [{p.role}] {p.title}{year} — `{p.paper_id}`"


def render_markdown(report: Report) -> str:
    lines = [f"# Literature review: {report.query}", "", f"_run `{report.run_id}`_", ""]

    for section in (report.agreement, report.contradictions, report.methodology_timeline):
        lines.append(f"## {section.heading}")
        lines.append("")
        lines.append(section.body_md)
        if section.citations:
            lines.append("")
            src = "; ".join(f"[{c.paper_id}] {c.title}" for c in section.citations)
            lines.append(f"**Sources:** {src}")
        lines.append("")

    lines.append("## Gaps")
    lines.append("")
    if not report.gaps:
        lines.append("(no gaps survived the citation-rule filter for this run.)")
    for g in report.gaps:
        lines.append(f"### {g.rank}. {g.type} — score {g.gap_score:.3f}")
        lines.append("")
        lines.append(g.statement)
        lines.append("")
        for p in g.bounding_papers[:8]:
            lines.append(_bounding_line(p))
        if len(g.bounding_papers) > 8:
            lines.append(f"- _(+{len(g.bounding_papers) - 8} more — see the graph)_")
        if len(g.found_by) > 1:
            found_by = ", ".join(g.found_by)
            lines.append(f"\n_corroborated by {len(g.found_by)} detectors: {found_by}_")
        lines.append("")

    s = report.stats
    kept = s.claims_extracted - s.claims_dropped_ungrounded
    lines.append("## Run stats")
    lines.append("")
    lines.append(f"- papers discovered / read: {s.papers_discovered} / {s.papers_read}")
    lines.append(f"- full-text ratio: {s.full_text_ratio:.0%}")
    lines.append(
        f"- claims extracted (kept / dropped ungrounded): {kept} / {s.claims_dropped_ungrounded}"
    )
    lines.append(
        f"- relations judged: {s.relations_judged} (contradictions: {s.contradictions_found})"
    )
    lines.append(f"- bridge promotions: {s.bridge_promotions}")
    lines.append(f"- clusters covered: {s.clusters_covered}")
    lines.append(f"- stop reason: {s.stop_reason}")
    lines.append(f"- cost: ${s.total_usd:.4f}, wall clock: {s.wall_clock_seconds:.0f}s")
    lines.append("")
    return "\n".join(lines)
