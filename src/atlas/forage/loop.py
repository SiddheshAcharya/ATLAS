"""The foraging loop (ADR-001, ADR-002) — the core of ATLAS.

    seed the frontier (relevance)
    while not stop():
        paper  = frontier.pop_highest()
        doc    = ingest(paper)                    # Phase 2
        claims = extract + grounding gate         # Job B
        graph.write(paper, claims, CITES)         # incremental, paper by paper
        neighbours = openalex references + citers
        frontier.push_scored(neighbours)          # admission bands
        rescore novelty; record new-info for saturation

It is an explicit `while` loop, not a framework — "why did it read that paper sixth?"
must be a readable function.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from uuid import uuid4

import structlog

from atlas.config import settings
from atlas.config_files import config_hash
from atlas.config_files import scoring as scoring_cfg
from atlas.contracts import PaperMeta
from atlas.extract.claims import extract_claims
from atlas.forage import bridge, frontier, graphalg, scoring
from atlas.forage.stopping import Stopper
from atlas.harvest import run_harvest
from atlas.ids import dedup_papers
from atlas.ingest.embed import embed_texts
from atlas.ingest.pipeline import run_ingest
from atlas.judge import pairing
from atlas.judge import relations as judge
from atlas.llm.client import LLMClient
from atlas.sources.openalex import OpenAlexSource
from atlas.store import db, vector
from atlas.store.graph import GraphStore

log = structlog.get_logger(__name__)

_S = scoring_cfg()
SEED_K = int(_S["seed"]["k"])
EXPAND_REFS = int(_S["expansion"]["max_references_per_paper"])
EXPAND_CITERS = int(_S["expansion"]["max_citers_per_paper"])
JUDGE_PAIRS_PER_PAPER = int(_S["judging"]["pairs_per_paper"])
JUDGE_CALLS_PER_RUN = int(_S["judging"]["max_calls_per_run"])


@dataclass
class RunResult:
    run_id: str
    query: str
    mode: str
    papers_read: int
    claims_kept: int
    claims_dropped: int
    relations_judged: int
    bridge_promotions: int
    stop_reason: str
    total_usd: float
    wall_clock_s: float
    saturation: list[float] = field(default_factory=list)
    graph_counts: dict[str, int] = field(default_factory=dict)


def _text_of(p: PaperMeta) -> str:
    return f"{p.title}\n{p.abstract or ''}".strip()


def _expand(paper: PaperMeta) -> tuple[list[PaperMeta], list[PaperMeta]]:
    async def go() -> tuple[list[PaperMeta], list[PaperMeta]]:
        async with OpenAlexSource() as oa:
            refs = await oa.references(paper, limit=EXPAND_REFS)
            citers = await oa.citers(paper, limit=EXPAND_CITERS)
        return refs, citers

    try:
        return asyncio.run(go())
    except Exception as e:  # expansion failure must not stop the loop
        log.warning("loop.expand_failed", paper_id=paper.paper_id, error=str(e))
        return [], []


def _bridge_neighbourhood(paper: PaperMeta) -> list[str]:
    """paper_ids of a parked paper's references + citers (for bridge probing)."""
    refs, citers = _expand(paper)
    return [p.paper_id for p in refs + citers]


def run(
    query: str,
    *,
    mode: str = "standard",
    max_papers: int | None = None,
    use_llm_keywords: bool = True,
    per_keyword: int = 20,
    write_graph: bool = True,
    run_id: str | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> RunResult:
    """`run_id`/`should_stop` are for the API's background task (api/tasks.py): the caller
    generates the id up front (to return it from POST /runs immediately) and can request a
    graceful stop — finishes the current paper, then breaks the loop, same as any other
    stop reason. `atlas run` (cli.py) leaves both at their defaults."""
    run_id = run_id or str(uuid4())
    cfg_hash = config_hash(mode)
    stopper = Stopper(mode)
    if max_papers is not None:
        stopper.max_papers = min(stopper.max_papers, max_papers)

    db.create_run(run_id, query, mode, cfg_hash)
    graph = (
        GraphStore()
        if write_graph and settings.neo4j_configured
        else None
    )
    if graph is not None:
        graph.write_run(run_id, query, mode, cfg_hash)

    log.info("loop.start", run_id=run_id, query=query, mode=mode, max_papers=stopper.max_papers)

    # ── harvest + seed ────────────────────────────────────────────────────
    papers, hreport = run_harvest(query, per_keyword=per_keyword, use_llm=use_llm_keywords)
    db.emit_event(
        run_id, "run_started",
        {"query": query, "mode": mode, "keywords": [k.text for k in hreport.keywords]},
    )
    db.emit_event(
        run_id, "harvest_done",
        {"n_candidates": hreport.total_unique, "per_source": hreport.per_source_raw},
    )
    db.upsert_papers(papers)
    by_id = {p.paper_id: p for p in papers}

    client = LLMClient(run_id=run_id)
    from atlas.ingest.embed import embed_query

    qvec = embed_query(query)
    # reuse abstract vectors cached in atlas_abstracts; only embed the new ones
    vecs: dict[str, list[float]] = vector.get_abstract_vectors(list(by_id))
    missing = [pid for pid in by_id if pid not in vecs]
    if missing:
        log.info("loop.embedding_abstracts", cached=len(vecs), new=len(missing))
        fresh = embed_texts([_text_of(by_id[pid]) for pid in missing])
        vecs.update(zip(missing, fresh, strict=True))
        vector.upsert_abstracts_bulk(
            [(pid, vecs[pid], by_id[pid].title, by_id[pid].year, None) for pid in missing]
        )
    now_year = date.today().year
    years = [p.year for p in papers if p.year]

    # seed only from papers that actually carry an abstract — a title-only vector inflates
    # cosine and floods the seeds with keyword-stuffed, no-full-text venues. Abstract-less
    # papers can still enter later via citation expansion.
    raw_rel = {
        pid: scoring.raw_relevance(qvec, v)
        for pid, v in vecs.items()
        if by_id[pid].abstract
    }
    top = sorted(raw_rel, key=lambda k: raw_rel[k], reverse=True)[:SEED_K]
    rel_norm = scoring.relevance_scores(qvec, {pid: vecs[pid] for pid in top})
    seeds = [
        (
            pid,
            scoring.combine(
                relevance=rel_norm[pid],
                recency=scoring.recency_score(by_id[pid].year, years, now_year=now_year),
                novelty=1.0,
            ),
        )
        for pid in top
    ]
    frontier.seed(run_id, seeds)
    log.info("loop.seeded", n=len(seeds))

    # ── the loop ─────────────────────────────────────────────────────────
    started = time.monotonic()
    read_vecs: list[list[float]] = []
    order = 0
    claims_kept = 0
    claims_dropped = 0
    relations_judged = 0
    judge_calls_left = JUDGE_CALLS_PER_RUN
    judge_pairs_per_paper = JUDGE_PAIRS_PER_PAPER
    contest_min_conf = float(scoring_cfg()["contest"]["min_confidence"])
    pr_every_n = int(scoring_cfg()["pagerank"]["every_n_papers"])
    pr_damping = float(scoring_cfg()["pagerank"]["damping"])
    bridge_bonus = float(scoring_cfg()["bridge"]["bonus"])
    pagerank_by_paper: dict[str, float] = {}
    contest_by_paper: dict[str, float] = {}
    bridge_ids: set[str] = set()
    total_usd = 0.0
    stop_reason = "completed"

    while True:
        elapsed = time.monotonic() - started
        pending = frontier.pending_above(run_id, stopper.read_below_score)
        reason = stopper.check(
            papers_read=order, total_usd=total_usd, elapsed_s=elapsed, pending_above=pending
        )
        if reason:
            stop_reason = reason
            break
        if should_stop is not None and should_stop():
            stop_reason = "stopped by user"
            break

        popped = frontier.pop_highest(run_id, stopper.read_below_score)
        if popped is None:
            stop_reason = "frontier exhausted"
            break
        paper = db.get_paper(popped.paper_id)
        if paper is None:
            frontier.mark(run_id, popped.paper_id, "failed")
            continue

        log.info("loop.read", order=order, paper_id=paper.paper_id, score=round(popped.score, 3))
        db.emit_event(
            run_id, "paper_selected",
            {
                "paper_id": paper.paper_id, "title": paper.title, "read_order": order,
                "score_breakdown": {
                    "total": popped.score, "relevance": popped.relevance,
                    "novelty": popped.novelty, "recency": popped.recency,
                    "pagerank": popped.pagerank, "contest": popped.contest,
                },
            },
        )
        try:
            doc, ingest_report = run_ingest(paper, run_id=run_id)
        except Exception as e:
            log.warning("loop.ingest_failed", paper_id=paper.paper_id, error=str(e))
            db.emit_event(
                run_id, "error", {"stage": "ingest", "message": str(e), "paper_id": paper.paper_id}
            )
            frontier.mark(run_id, popped.paper_id, "failed")
            fr = stopper.record_failure()
            if fr:
                stop_reason = fr
                break
            continue

        db.emit_event(
            run_id, "paper_ingested",
            {
                "paper_id": paper.paper_id, "depth": ingest_report.depth,
                "structure": ingest_report.structure, "n_sections": ingest_report.n_sections,
                "n_chunks": ingest_report.n_chunks,
            },
        )

        harvest = extract_claims(doc, paper, client=client)
        claims_kept += len(harvest.kept)
        claims_dropped += harvest.n_dropped
        db.insert_claims(harvest.kept, run_id)
        db.insert_dropped_claims(harvest.dropped, run_id)  # evaluation only — TESTING.md E4
        db.emit_event(
            run_id, "claims_extracted",
            {
                "paper_id": paper.paper_id, "n_kept": len(harvest.kept),
                "n_dropped": harvest.n_dropped,
            },
        )

        if graph is not None:
            graph.write_paper(
                paper_id=paper.paper_id,
                title=paper.title,
                run_id=run_id,
                year=paper.year,
                venue=paper.venue,
                doi=paper.doi,
                pdf_url=str(paper.pdf_url) if paper.pdf_url else None,
                abstract=paper.abstract,
                citation_count=paper.citation_count,
                depth=doc.depth.value,
                relevance=popped.score,
                read_order=order,
                first_seen_via=popped.discovered_via,
            )
            graph.write_claims(harvest.kept, run_id)

        # ── relation judging (Job C) — kNN candidates, then judge ───────────
        n_contradictions = 0
        if harvest.kept:
            cvecs = embed_texts([c.text for c in harvest.kept])
            year_by_paper = {p.paper_id: p.year for p in by_id.values()}
            vector.upsert_claims(
                harvest.kept, cvecs, run_id=run_id, year_by_paper=year_by_paper
            )
            pairs = pairing.candidate_pairs(
                harvest.kept, cvecs, run_id, max_pairs=judge_pairs_per_paper
            )
            relations = judge.judge_pairs(
                pairs, client, run_id, papers=by_id, max_calls=judge_calls_left
            )
            judge_calls_left -= len(relations)
            db.insert_relations(relations, run_id)
            if graph is not None:
                graph.write_relations(relations, run_id)
            relations_judged += len(relations)
            n_contradictions = judge.contradiction_count(relations, contest_min_conf)
            for r in relations:
                db.emit_event(
                    run_id, "relation_judged",
                    {
                        "source": r.source_claim_id, "target": r.target_claim_id,
                        "type": r.type, "confidence": r.confidence,
                    },
                )

        # ── citation expansion + admission ──────────────────────────────
        refs, citers = _expand(paper)
        neighbours = dedup_papers(refs + citers)
        if neighbours:
            db.upsert_papers(neighbours)
            n_vecs = embed_texts([_text_of(n) for n in neighbours])
            ref_ids = {r.paper_id for r in refs}
            for n, nv in zip(neighbours, n_vecs, strict=True):
                vecs.setdefault(n.paper_id, nv)
                by_id.setdefault(n.paper_id, n)
                sim = scoring.raw_relevance(qvec, nv)
                band = scoring.admission_band(sim)
                if band == "drop":
                    continue
                breakdown = scoring.combine(
                    relevance=max(0.0, sim),
                    recency=scoring.recency_score(n.year, years, now_year=now_year),
                    novelty=scoring.novelty_score(nv, read_vecs),
                )
                kind = "reference_of" if n.paper_id in ref_ids else "citer_of"
                via = f"{kind}:{paper.paper_id}"
                frontier.push(
                    run_id,
                    n.paper_id,
                    state="parked" if band == "park" else "pending",
                    breakdown=breakdown,
                    discovered_via=via,
                    parked_reason="below park threshold" if band == "park" else None,
                )

        if graph is not None:
            graph.write_cites(paper.paper_id, [(r.paper_id, r.title) for r in refs], run_id)
            for c in citers:
                graph.write_cites(c.paper_id, [(paper.paper_id, paper.title)], run_id)
            graph.write_read(run_id, paper.paper_id, order)

        # ── bookkeeping ────────────────────────────────────────────────
        frontier.mark(run_id, popped.paper_id, "read", read_order=order)
        read_vecs.append(vecs.get(paper.paper_id, embed_texts([_text_of(paper)])[0]))
        order += 1

        # ── PageRank / Louvain / Contest / bridge — on the recompute cadence ──
        if graph is not None and (
            order % pr_every_n == 0 or order == stopper._min_papers
        ):
            pagerank_by_paper, _clusters = graphalg.recompute(
                graph, run_id, damping=pr_damping
            )
            if pagerank_by_paper:
                top5 = sorted(pagerank_by_paper.items(), key=lambda kv: kv[1], reverse=True)[:5]
                db.emit_event(
                    run_id, "pagerank_updated",
                    {"top": [{"paper_id": pid, "pagerank": pr} for pid, pr in top5]},
                )
            contest_by_paper = {
                pid: contra / max(1, total)
                for pid, (contra, total) in graph.contest_inputs(run_id).items()
            }
            parked = [
                by_id[pid]
                for pid in frontier.parked_paper_ids(run_id, limit=15)
                if pid in by_id
            ]
            for promo in bridge.sweep(
                graph, run_id, parked, _bridge_neighbourhood,
                promoted_so_far=len(bridge_ids),
            ):
                frontier.promote_bridge(run_id, promo.paper_id)
                bridge_ids.add(promo.paper_id)
                db.emit_event(
                    run_id, "bridge_promoted",
                    {"paper_id": promo.paper_id, "clusters": list(promo.clusters)},
                )

        _rescore_frontier(
            run_id, by_id, vecs, read_vecs, qvec, years, now_year,
            pagerank_by_paper, contest_by_paper, bridge_ids, bridge_bonus,
        )

        new_info = stopper.record_paper(
            new_claims=len(harvest.kept), new_contradictions=n_contradictions
        )
        total_usd = db.run_cost(run_id)
        db.emit_event(
            run_id, "saturation",
            {
                "step": order - 1, "new_info": new_info, "ema": stopper.ema,
                "paper_id": paper.paper_id, "title": paper.title,
                "claims_kept": len(harvest.kept), "claims_dropped": harvest.n_dropped,
                "neighbours": len(neighbours), "total_usd": round(total_usd, 6),
            },
        )
        db.emit_event(run_id, "frontier_updated", frontier.state_counts(run_id))

    # ── finalize: one last PageRank/Louvain + bridge sweep ─────────────────
    wall = time.monotonic() - started
    counts: dict[str, int] = {}
    if graph is not None:
        graphalg.recompute(graph, run_id, damping=pr_damping)
        parked = [
            by_id[pid]
            for pid in frontier.parked_paper_ids(run_id, limit=15)
            if pid in by_id
        ]
        for promo in bridge.sweep(
            graph, run_id, parked, _bridge_neighbourhood, promoted_so_far=len(bridge_ids)
        ):
            frontier.promote_bridge(run_id, promo.paper_id)
            bridge_ids.add(promo.paper_id)
            db.emit_event(
                run_id, "bridge_promoted",
                {"paper_id": promo.paper_id, "clusters": list(promo.clusters)},
            )
        graph.finish_run(run_id, "completed", stop_reason)
        try:
            counts = graph.counts(run_id)
        except Exception as e:
            log.warning("loop.graph_counts_failed", error=str(e))
        graph.close()

    db.finish_run(run_id, "completed", stop_reason)
    log.info(
        "loop.done",
        run_id=run_id,
        papers_read=order,
        claims_kept=claims_kept,
        claims_dropped=claims_dropped,
        relations_judged=relations_judged,
        bridge_promotions=len(bridge_ids),
        stop_reason=stop_reason,
        wall_s=round(wall, 1),
    )
    db.emit_event(
        run_id, "run_finished",
        {
            "stop_reason": stop_reason,
            "stats": {
                "papers_read": order, "claims_kept": claims_kept,
                "claims_dropped": claims_dropped, "relations_judged": relations_judged,
                "bridge_promotions": len(bridge_ids), "total_usd": total_usd,
                "wall_clock_seconds": round(wall, 1),
            },
        },
    )
    return RunResult(
        run_id=run_id,
        query=query,
        mode=mode,
        papers_read=order,
        claims_kept=claims_kept,
        claims_dropped=claims_dropped,
        relations_judged=relations_judged,
        bridge_promotions=len(bridge_ids),
        stop_reason=stop_reason,
        total_usd=total_usd,
        wall_clock_s=wall,
        saturation=stopper.series,
        graph_counts=counts,
    )


def _rescore_frontier(
    run_id: str,
    by_id: dict[str, PaperMeta],
    vecs: dict[str, list[float]],
    read_vecs: list[list[float]],
    qvec: list[float],
    years: list[int],
    now_year: int,
    pagerank_by_paper: dict[str, float],
    contest_by_paper: dict[str, float],
    bridge_ids: set[str],
    bridge_bonus: float,
) -> None:
    """Re-score every pending/parked paper with the full 5 components. Relevance is
    min-max normalised across the current frontier (SCORING.md §1); novelty & contest
    change every iteration; PageRank refreshes on the recompute cadence; a bridge-promoted
    paper carries an additive bonus."""
    pids = [pid for pid in frontier.scored_paper_ids(run_id) if pid in vecs]
    if not pids:
        return
    rel_norm = scoring.relevance_scores(qvec, {pid: vecs[pid] for pid in pids})
    updates = {
        pid: scoring.combine(
            relevance=rel_norm[pid],
            recency=scoring.recency_score(
                by_id[pid].year if pid in by_id else None, years, now_year=now_year
            ),
            novelty=scoring.novelty_score(vecs[pid], read_vecs),
            pagerank=pagerank_by_paper.get(pid, 0.0),
            contest=contest_by_paper.get(pid, 0.0),
            bridge_bonus=bridge_bonus if pid in bridge_ids else 0.0,
        )
        for pid in pids
    }
    frontier.update_scores(run_id, updates)
