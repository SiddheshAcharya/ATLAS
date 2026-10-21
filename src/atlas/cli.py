"""``atlas`` — the command-line entrypoint (Typer).

Every pipeline stage is meant to be runnable standalone from here so a 40-minute crawl
never has to be re-run just to debug one step. Phase 0 ships ``version``, ``health`` and
``init-stores``; stage commands (``harvest``, ``ingest``, ``forage`` …) land with their
phases.
"""

from __future__ import annotations

from atlas.console_encoding import fix_windows_console_encoding

fix_windows_console_encoding()

import typer  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from atlas import __version__  # noqa: E402
from atlas.config import settings  # noqa: E402

app = typer.Typer(no_args_is_help=True, add_completion=False, help="ATLAS literature review")
console = Console()

@app.command()
def version() -> None:
    """Print the ATLAS version."""
    console.print(f"atlas {__version__}")


@app.command()
def health(
    live_llm: bool = typer.Option(False, "--live-llm", help="actually call the LLM"),
) -> None:
    """Check every dependency: db, neo4j, qdrant, grobid, llm."""
    settings.ensure_dirs()
    from atlas.health import check_all

    rows = check_all(live_llm=live_llm)

    table = Table(title="atlas health", show_lines=False)
    table.add_column("service")
    table.add_column("status")
    table.add_column("detail", overflow="fold")

    required_ok = True
    for name, ok, detail in rows:
        if ok is None:
            status = "[yellow]SKIP[/yellow]"
        elif ok:
            status = "[green]OK[/green]"
        else:
            status = "[red]FAIL[/red]"
            if name in ("postgres/sqlite",):
                required_ok = False
        table.add_row(name, status, detail)

    console.print(table)
    if not required_ok:
        console.print("[red]required service down[/red]")
        raise typer.Exit(1)


@app.command(name="init-stores")
def init_stores() -> None:
    """Run DB migrations, create Qdrant collections, apply Neo4j schema."""
    settings.ensure_dirs()

    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    console.print("[green]db[/green] migrated to head")

    from atlas.store import vector

    created = vector.ensure_collections()
    console.print(f"[green]qdrant[/green] collections ok (created: {created or 'none'})")

    if settings.neo4j_configured:
        from atlas.store.graph import GraphStore

        with GraphStore() as g:
            g.apply_schema()
        console.print("[green]neo4j[/green] schema applied")
    else:
        console.print("[yellow]neo4j[/yellow] skipped (NEO4J_URI unset)")


@app.command()
def harvest(
    query: str = typer.Argument(..., help="the research question"),
    per_keyword: int = typer.Option(25, "--per-keyword", help="results per keyword per source"),
    no_llm: bool = typer.Option(False, "--no-llm", help="skip keyword expansion (debug)"),
    store: bool = typer.Option(True, "--store/--no-store", help="write papers to the DB"),
    as_json: bool = typer.Option(False, "--json", help="print the report as JSON"),
) -> None:
    """Phase 1 — expand the query, hit the four scholarly APIs, dedup, report."""
    settings.ensure_dirs()
    from atlas.harvest import run_harvest

    papers, report = run_harvest(query, per_keyword=per_keyword, use_llm=not no_llm)

    if store:
        from atlas.store.db import upsert_papers

        n = upsert_papers(papers)
        kind = "sqlite" if settings.is_sqlite else "postgres"
        report.notes.append(f"stored {n} papers to {kind}")

    if as_json:
        console.print_json(data={"report": report.as_dict(), "n_papers": len(papers)})
        return

    if not no_llm:
        kw = Table(title="query plan", show_lines=False)
        kw.add_column("tier")
        kw.add_column("keywords", overflow="fold")
        for tier in ("exact", "concept", "adjacent"):
            terms = [k.text for k in report.keywords if k.tier == tier]
            if terms:
                kw.add_row(tier, ", ".join(terms))
        console.print(kw)

    src = Table(title="per source (before dedup)")
    src.add_column("source")
    src.add_column("papers", justify="right")
    for name, count in report.per_source_raw.items():
        src.add_row(name, str(count))
    src.add_row("[dim]total raw[/dim]", f"[dim]{report.total_raw}[/dim]")
    console.print(src)

    summary = Table(title="harvest", show_header=False)
    summary.add_column("k")
    summary.add_column("v", justify="right")
    summary.add_row("unique papers", str(report.total_unique))
    summary.add_row("found by >1 source", str(report.multi_source))
    summary.add_row("with a direct PDF url", str(report.with_pdf_url))
    summary.add_row("with an abstract", str(report.with_abstract))
    summary.add_row("elapsed", f"{report.elapsed_s:.0f}s")
    console.print(summary)
    for note in report.notes:
        console.print(f"[dim]· {note}[/dim]")


@app.command()
def ingest(
    paper_id: str = typer.Option(None, "--paper-id", help="a paper_id already in the DB"),
    pdf: str = typer.Option(None, "--pdf", help="ingest a local PDF file directly"),
    no_grobid: bool = typer.Option(False, "--no-grobid", help="skip GROBID, use PyMuPDF"),
    no_store: bool = typer.Option(False, "--no-store", help="parse only, don't write Qdrant/DB"),
) -> None:
    """Phase 2 — resolve a PDF, parse it, chunk + embed + store, verify offsets."""
    settings.ensure_dirs()
    from pathlib import Path

    from atlas.contracts import PaperMeta
    from atlas.ingest.pipeline import run_ingest
    from atlas.store.db import get_paper

    if pdf:
        paper = PaperMeta(paper_id=f"local:{Path(pdf).stem}", title=Path(pdf).stem)
        pdf_path: str | None = pdf
    elif paper_id:
        paper = get_paper(paper_id)
        pdf_path = None
        if paper is None:
            console.print(f"[red]no paper[/red] with id {paper_id!r} (run `atlas harvest` first)")
            raise typer.Exit(1)
    else:
        console.print("[red]pass --paper-id or --pdf[/red]")
        raise typer.Exit(1)

    doc, report = run_ingest(
        paper, prefer_grobid=not no_grobid, store=not no_store, pdf_path=pdf_path
    )

    t = Table(title="ingest", show_header=False)
    t.add_column("k")
    t.add_column("v", overflow="fold")
    for k, v in report.as_dict().items():
        t.add_row(k, str(v))
    console.print(t)

    if doc.sections:
        s = doc.sections[0]
        roundtrip = doc.full_text[s.char_start : s.char_end] == s.text
        console.print(
            f"[dim]section[0] {s.name!r} [{s.char_start}:{s.char_end}] "
            f"roundtrip={'ok' if roundtrip else 'BROKEN'}[/dim]"
        )
    for w in report.warnings:
        console.print(f"[yellow]· {w}[/yellow]")


@app.command(name="resolve-check")
def resolve_check(
    limit: int = typer.Option(40, "--limit", help="papers to test (use 200 for the R1 tripwire)"),
    no_download: bool = typer.Option(False, "--no-download", help="only pick a URL, don't fetch"),
) -> None:
    """R1 tripwire — what fraction of harvested papers yield an open-access PDF."""
    settings.ensure_dirs()
    import asyncio
    import collections

    import httpx

    from atlas.ingest.pdf_fetch import resolve_pdf
    from atlas.store.db import list_papers

    papers = list_papers(limit=limit)
    if not papers:
        console.print("[red]no papers in the DB[/red] — run `atlas harvest` first")
        raise typer.Exit(1)

    async def _run() -> collections.Counter[str]:
        tally: collections.Counter[str] = collections.Counter()
        async with httpx.AsyncClient(
            headers={"User-Agent": f"ATLAS/0.1 (mailto:{settings.contact_email})"}
        ) as client:
            for p in papers:
                res = await resolve_pdf(p, client=client, download=not no_download)
                tally[res.via if res.ok or no_download else "none"] += 1
        return tally

    tally = asyncio.run(_run())
    got = sum(v for k, v in tally.items() if k != "none")
    rate = got / len(papers)

    tbl = Table(title=f"resolve-check ({len(papers)} papers)")
    tbl.add_column("via")
    tbl.add_column("n", justify="right")
    for via, n in tally.most_common():
        tbl.add_row(via, str(n))
    console.print(tbl)
    colour = "green" if rate >= 0.35 else "red"
    console.print(
        f"[{colour}]full-text reachable: {got}/{len(papers)} = {rate:.0%}[/{colour}]"
        "  (R1 target >= 35%)"
    )


@app.command()
def run(
    query: str = typer.Argument(..., help="the research question"),
    mode: str = typer.Option("standard", "--mode", help="standard | deep | extra_deep"),
    max_papers: int = typer.Option(None, "--max-papers", help="cap below the mode budget"),
    no_neo4j: bool = typer.Option(False, "--no-neo4j", help="skip graph writes"),
) -> None:
    """Phase 3 — the foraging loop: read, extract claims, follow citations, build the graph."""
    settings.ensure_dirs()
    import json

    from atlas.forage.loop import run as run_loop

    result = run_loop(query, mode=mode, max_papers=max_papers, write_graph=not no_neo4j)

    out_dir = settings.data_dir / "runs" / result.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "saturation.json").write_text(
        json.dumps({"run_id": result.run_id, "series": result.saturation}, indent=1)
    )

    t = Table(title=f"run {result.run_id[:8]}", show_header=False)
    t.add_column("k")
    t.add_column("v", overflow="fold")
    t.add_row("query", result.query)
    t.add_row("mode", result.mode)
    t.add_row("papers read", str(result.papers_read))
    t.add_row("claims kept", str(result.claims_kept))
    t.add_row("claims dropped (ungrounded)", str(result.claims_dropped))
    t.add_row("relations judged", str(result.relations_judged))
    t.add_row("bridge promotions", str(result.bridge_promotions))
    t.add_row("stop reason", result.stop_reason)
    t.add_row("graph (neo4j)", str(result.graph_counts or "not written"))
    t.add_row("cost", f"${result.total_usd:.4f}")
    t.add_row("wall clock", f"{result.wall_clock_s:.0f}s")
    console.print(t)

    if result.saturation:
        ramp = " .:-=+*#%@"  # ASCII — the Windows console can't do unicode blocks
        hi = max(result.saturation) or 1.0
        spark = "".join(ramp[min(9, int(v / hi * 9))] for v in result.saturation)
        console.print(f"saturation EMA: |{spark}|")
        console.print(f"saved: {out_dir / 'saturation.json'}")


@app.command()
def show(
    run_id: str = typer.Argument(None, help="a run_id; omit to list recent runs"),
    claims: bool = typer.Option(False, "--claims", help="also print every claim with its quote"),
) -> None:
    """Inspect a foraging run — read order, scores, claims, graph counts."""
    settings.ensure_dirs()
    import json

    from atlas.store import db

    if not run_id:
        t = Table(title="recent runs")
        for col in ("run_id", "query", "mode", "status", "stop_reason", "started"):
            t.add_column(col, overflow="fold")
        for r in db.list_runs():
            t.add_row(
                r["run_id"][:8], r["query"], r["mode"], r["status"] or "",
                (r["stop_reason"] or "")[:30], (r["started_at"] or "")[:19],
            )
        console.print(t)
        return

    summary = db.run_summary(run_id)
    if summary is None:
        console.print(f"[red]no run[/red] {run_id!r}")
        raise typer.Exit(1)

    meta = Table(show_header=False, title=f"run {summary['run_id'][:8]}")
    meta.add_column("k")
    meta.add_column("v", overflow="fold")
    for k in ("query", "mode", "status", "stop_reason", "config_hash", "started_at", "finished_at"):
        meta.add_row(k, str(summary[k]))
    meta.add_row("frontier", str(summary["frontier_states"]))
    meta.add_row("relations", str(summary["relations_by_type"] or "none"))
    meta.add_row("llm", f"{summary['llm_calls']} calls, ${summary['total_usd']:.4f}")
    console.print(meta)

    def _f(v: object) -> str:
        return f"{v:.2f}" if isinstance(v, (int, float)) else "-"

    reads = Table(title="read order")
    for col in ("#", "score", "rel", "nov", "rec", "pr", "con", "depth", "clm", "via", "title"):
        reads.add_column(col, overflow="fold")
    for r in summary["reads"]:
        reads.add_row(
            str(r["order"]),
            _f(r["score"]),
            _f(r["relevance"]),
            _f(r["novelty"]),
            _f(r["recency"]),
            _f(r["pagerank"]),
            _f(r["contest"]),
            r["depth"] or "-",
            str(r["claims"]),
            (r["via"] or "")[:20],
            (r["title"] or "")[:50],
        )
    console.print(reads)

    sat = settings.data_dir / "runs" / summary["run_id"] / "saturation.json"
    if sat.exists():
        series = json.loads(sat.read_text()).get("series", [])
        if series:
            ramp = " .:-=+*#%@"
            hi = max(series) or 1.0
            spark = "".join(ramp[min(9, int(v / hi * 9))] for v in series)
            console.print(f"saturation EMA: |{spark}|")

    if settings.neo4j_configured:
        from atlas.store.graph import GraphStore

        with GraphStore() as g:
            try:
                console.print(f"neo4j graph: {g.counts(summary['run_id'])}")
            except Exception as e:
                console.print(f"[yellow]neo4j counts failed:[/yellow] {e}")

    if claims:
        from atlas.store.db import ClaimRow, session_scope

        with session_scope() as s:
            import sqlalchemy as sa

            rows = s.execute(
                sa.select(ClaimRow.paper_id, ClaimRow.section, ClaimRow.text, ClaimRow.quote)
                .where(ClaimRow.run_id == summary["run_id"])
            ).all()
        for pid, section, text, quote in rows:
            console.print(f"\n[dim]{pid} · {section}[/dim]\n  {text}\n  [green]“{quote}”[/green]")


@app.command()
def snapshot(
    run_id: str = typer.Option(
        ..., "--run-id", help="run(s) to save for offline replay (comma-separated)"
    ),
    graph_only: bool = typer.Option(
        False, "--graph-only",
        help="refresh only graph.json of an existing snapshot; keep its gaps/report/stats",
    ),
) -> None:
    """Save a local copy of a finished run's graph/gaps/report/stats so the dashboard can
    replay it with the network unplugged. Run this while online, before the demo."""
    settings.ensure_dirs()
    from atlas.store import db
    from atlas.store import snapshot as snap

    known = {r["run_id"]: r for r in db.list_runs(limit=500)}
    for raw in run_id.split(","):
        prefix = raw.strip()
        matches = [rid for rid in known if rid.startswith(prefix)]
        if len(matches) != 1:
            console.print(f"[red]{prefix!r} matches {len(matches)} runs — need exactly one[/red]")
            raise typer.Exit(1)
        rid = matches[0]
        out = snap.refresh_graph(rid) if graph_only else snap.build_and_save(rid)
        console.print(f"[green]saved[/green] {rid[:8]} -> {out}")


@app.command(name="clear-run")
def clear_run(
    run_id: str = typer.Option(..., "--run-id", help="the run to delete"),
    yes: bool = typer.Option(False, "--yes", help="skip the confirmation prompt"),
) -> None:
    """Delete a run everywhere — Postgres rows, Qdrant points, Neo4j Claims/Run + orphan
    Papers. Shared Paper rows and abstract vectors are kept."""
    from atlas.store import db, vector

    if not yes:
        typer.confirm(f"delete run {run_id!r} from all stores?", abort=True)

    pg = db.delete_run(run_id)
    console.print(f"postgres: {pg}")
    try:
        qd = vector.delete_run_points(run_id)
        console.print(f"qdrant: {qd}")
    except Exception as e:
        console.print(f"[yellow]qdrant skipped:[/yellow] {e}")
    if settings.neo4j_configured:
        from atlas.store.graph import GraphStore

        with GraphStore() as g:
            console.print(f"neo4j: {g.delete_run(run_id)}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """API + the built dashboard in one process — the demo-day entry point. Build the
    dashboard once first (`cd web && npm run build`), then open http://HOST:PORT/."""
    import uvicorn

    from atlas.api.main import WEB_DIST

    if (WEB_DIST / "index.html").is_file():
        console.print(f"dashboard: http://{host}:{port}/  (from {WEB_DIST})")
    else:
        console.print(
            f"[yellow]no built dashboard at {WEB_DIST} — API only. "
            "Run `cd web && npm run build` first.[/yellow]"
        )
    uvicorn.run("atlas.api.main:app", host=host, port=port)


@app.command(name="repair-abstract-vectors")
def repair_abstract_vectors(
    yes: bool = typer.Option(False, "--yes", help="skip the confirmation prompt"),
) -> None:
    """Re-embed abstract vectors that ingest overwrote before 2026-09-28.

    Ingest used to replace a read paper's seed vector (title+abstract, document-style) with
    a query-style, abstract-only one, so seed ranking and the E1 baseline depended on what
    earlier runs had read. Those points are the ones carrying a `depth` payload; this puts
    them back in the representation the loop seeds with. Stop any running crawl first
    (embedded Qdrant is single-process)."""
    from atlas.ingest.embed import embed_texts
    from atlas.store import db, vector

    client = vector.get_client()
    try:
        vector.ensure_collections(client)
        pids: list[str] = []
        offset = None
        while True:
            got, offset = client.scroll(
                "atlas_abstracts", limit=2000, offset=offset, with_payload=True
            )
            pids += [p.payload["paper_id"] for p in got if p.payload.get("depth")]
            if offset is None:
                break
        papers = [p for p in (db.get_paper(pid) for pid in pids) if p is not None]
        console.print(f"{len(pids)} overwritten abstract vectors; {len(papers)} have metadata")
        if not papers:
            return
        if not yes:
            typer.confirm("re-embed them now?", abort=True)
        vecs = embed_texts([f"{p.title}\n{p.abstract or ''}".strip() for p in papers])
        n = vector.upsert_abstracts_bulk(
            [(p.paper_id, v, p.title, p.year, None) for p, v in zip(papers, vecs, strict=True)],
            client=client,
        )
        console.print(f"[green]re-embedded[/green] {n}")
    finally:
        client.close()


@app.command()
def concepts(
    run_id: str = typer.Option(..., "--run-id", help="a completed run"),
    top: int = typer.Option(100, "--top", help="how many concepts to print (the R4 check)"),
) -> None:
    """Phase 5 — extract concepts/methods/datasets/limitations/future-work, write to Neo4j."""
    settings.ensure_dirs()
    from atlas.extract.concepts import extract_and_store

    report = extract_and_store(run_id)

    t = Table(title=f"concepts — run {run_id[:8]}", show_header=False)
    t.add_column("k")
    t.add_column("v")
    for k in ("papers_processed", "concepts", "methods", "datasets", "weakness_clusters", "calls"):
        t.add_row(k, str(getattr(report, k)))
    console.print(t)

    if not report.top_concepts:
        console.print("[yellow]no concepts extracted[/yellow] — are there read papers with chunks?")
        return
    ct = Table(title=f"R4 — top {min(top, len(report.top_concepts))} concepts by frequency")
    ct.add_column("#")
    ct.add_column("label")
    ct.add_column("papers", justify="right")
    for i, (label, n) in enumerate(report.top_concepts[:top], 1):
        ct.add_row(str(i), label, str(n))
    console.print(ct)
    console.print(
        "[dim]R4 tripwire: read this list — obvious near-duplicates (e.g. "
        "\"iot device\" vs \"iot devices\" as separate rows) mean normalization needs work.[/dim]"
    )


@app.command(name="judge-eval")
def judge_eval(
    run_id: str = typer.Option(
        None, "--run-id", help="export judged pairs (comma-separated for multiple runs)"
    ),
    export: str = typer.Option(None, "--export", help="JSONL path to write"),
    score: str = typer.Option(None, "--score", help="JSONL path to score (needs `gold` labels)"),
    rejudge: str = typer.Option(
        None, "--rejudge",
        help="labelled JSONL to re-judge with the current judge prompt (writes --out)",
    ),
    out: str = typer.Option(None, "--out", help="output JSONL for --rejudge"),
    per_label: int = typer.Option(
        12, "--per-label", help="stratified sample cap per relation type (TESTING.md E5: 12)"
    ),
    no_sample: bool = typer.Option(
        False, "--no-sample", help="export every judged pair, skip the per-label cap"
    ),
) -> None:
    """R2 tripwire — export judged pairs for hand-labelling, then score precision/recall.

    A single small run rarely has 12 CONTRADICTS/REPLICATES pairs (they're naturally
    rare) — pass multiple run ids to pool from, e.g. --run-id id1,id2,id3."""
    from pathlib import Path

    from atlas.judge import eval as je

    if rejudge:
        import json

        from atlas.llm.client import LLMClient

        if not out:
            console.print("[red]--rejudge needs --out[/red]")
            raise typer.Exit(1)
        rows = [
            json.loads(line)
            for line in Path(rejudge).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        client = LLMClient(run_id=None)
        new_rows, missing = je.rejudge(rows, client)
        Path(out).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in new_rows), encoding="utf-8"
        )
        console.print(
            f"re-judged {len(rows) - missing} of {len(rows)} pairs with "
            f"{client.routing.prompt_file('judge')} -> {out}"
            + (f" ([yellow]{missing} pairs' claims not found[/yellow])" if missing else "")
        )
        console.print_json(data=je.score(Path(out)))
        return
    if score:
        result = je.score(Path(score))
        console.print_json(data=result)
        return
    if not run_id or not export:
        console.print("[red]pass --run-id and --export, or --score <file>[/red]")
        raise typer.Exit(1)

    from atlas.store.db import judged_pairs

    rows = [row for rid in run_id.split(",") for row in judged_pairs(rid.strip())]
    n = je.export_pairs(rows, Path(export), per_label=None if no_sample else per_label)
    console.print(f"wrote {n} of {len(rows)} judged pairs to {export}")
    console.print("[dim]fill the `gold` field for each, then --score it[/dim]")


@app.command()
def gaps(
    run_id: str = typer.Option(..., "--run-id", help="a run with concepts already extracted"),
) -> None:
    """Phase 5b — run the 5 gap detectors + fusion, write (:Gap) nodes to Neo4j."""
    settings.ensure_dirs()
    from atlas.gaps.fusion import run_detectors
    from atlas.store.graph import GraphStore

    with GraphStore() as g:
        ranked = run_detectors(run_id, g)

    if not ranked:
        console.print("[yellow]no gaps survived detection + the citation-rule filter[/yellow]")
        return

    t = Table(title=f"gaps — run {run_id[:8]} ({len(ranked)} total)")
    for col in ("#", "type", "score", "detectors", "statement"):
        t.add_column(col, overflow="fold")
    for gap in ranked:
        t.add_row(
            str(gap.rank), gap.type, f"{gap.gap_score:.3f}",
            str(len(gap.found_by)), gap.statement[:120],
        )
    console.print(t)


@app.command()
def report(
    run_id: str = typer.Option(..., "--run-id", help="a run with gaps already computed"),
    out: str = typer.Option(None, "--out", help="markdown path (default data/runs/<id>/report.md)"),
) -> None:
    """Job D — one-pass synthesis into the 4-section report, exported as markdown."""
    settings.ensure_dirs()
    from pathlib import Path

    from atlas.synthesis.report import build_report, render_markdown

    rep = build_report(run_id)
    md = render_markdown(rep)

    out_path = Path(out) if out else settings.data_dir / "runs" / run_id / "report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    t = Table(title=f"report — run {run_id[:8]}", show_header=False)
    t.add_column("k")
    t.add_column("v", overflow="fold")
    t.add_row("agreement clusters", str(len(rep.agreement.citations)) + " papers cited")
    t.add_row("contradictions", str(len(rep.contradictions.citations)) + " papers cited")
    t.add_row("gaps", str(len(rep.gaps)))
    t.add_row("saved", str(out_path))
    console.print(t)


if __name__ == "__main__":  # pragma: no cover
    app()
