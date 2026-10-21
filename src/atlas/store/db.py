"""Postgres / SQLite — run state, frontier, caches, cost ledger (ADR-003, ADR-004).

Postgres is the source of truth for paper existence; Neo4j and Qdrant are projections.
Only this module writes here. The ORM types are deliberately portable (``sa.Uuid``,
``sa.JSON``, non-native enums) so the same migration runs on the SQLite dev default and
on the Postgres container without a second migration.
"""

from __future__ import annotations

import datetime as dt
import random
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from atlas.config import settings

FRONTIER_STATES = ("pending", "parked", "reading", "read", "dropped", "failed")
PAPER_DEPTHS = ("full_text", "abstract_only", "metadata_only")

# JSONB on Postgres, plain JSON everywhere else.
JSON_ = sa.JSON().with_variant(JSONB(), "postgresql")
_DEPTH = sa.Enum(*PAPER_DEPTHS, name="paper_depth", native_enum=False)
_FRONTIER_STATE = sa.Enum(*FRONTIER_STATES, name="frontier_state", native_enum=False)

# run_id / claim_id are plain text: the *same* string must key Postgres, Neo4j and the
# data/runs/<id>/ dir. SQLAlchemy's Uuid type stores hyphen-less on SQLite and breaks that.
_uuid = sa.Text
_ts = sa.DateTime(timezone=True)
# SQLite only autoincrements a plain INTEGER PK, not BIGINT.
_bigint_pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    run_id: Mapped[str] = mapped_column(_uuid, primary_key=True)
    query: Mapped[str] = mapped_column(sa.Text)
    mode: Mapped[str] = mapped_column(sa.Text)
    config_hash: Mapped[str] = mapped_column(sa.Text)
    keywords: Mapped[Any | None] = mapped_column(JSON_, nullable=True)
    status: Mapped[str] = mapped_column(sa.Text, default="running")
    stop_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(_ts, server_default=sa.func.now())
    finished_at: Mapped[dt.datetime | None] = mapped_column(_ts, nullable=True)


class Paper(Base):
    __tablename__ = "papers"
    paper_id: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    title: Mapped[str] = mapped_column(sa.Text)
    year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(sa.Text, nullable=True, index=True)
    arxiv_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    pmid: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    openalex_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    s2_corpus_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    authors: Mapped[Any | None] = mapped_column(JSON_, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    depth: Mapped[str | None] = mapped_column(_DEPTH, default="metadata_only")
    raw: Mapped[Any | None] = mapped_column(JSON_, nullable=True)
    created_at: Mapped[dt.datetime | None] = mapped_column(_ts, server_default=sa.func.now())


class Frontier(Base):
    __tablename__ = "frontier"
    run_id: Mapped[str] = mapped_column(_uuid, sa.ForeignKey("runs.run_id"), primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        sa.Text, sa.ForeignKey("papers.paper_id"), primary_key=True
    )
    state: Mapped[str] = mapped_column(_FRONTIER_STATE, default="pending")
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    relevance: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    pagerank: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    novelty: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    contest: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    recency: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    discovered_via: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    parked_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    read_order: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(sa.Integer, default=0)
    updated_at: Mapped[dt.datetime | None] = mapped_column(_ts, server_default=sa.func.now())
    __table_args__ = (sa.Index("ix_frontier_run_state_score", "run_id", "state", "score"),)


class ClaimRow(Base):
    __tablename__ = "claims"
    claim_id: Mapped[str] = mapped_column(_uuid, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(_uuid, nullable=True)
    paper_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    quote: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    quote_start: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    quote_end: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    scope: Mapped[Any | None] = mapped_column(JSON_, nullable=True)
    verified: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    verify_method: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[dt.datetime | None] = mapped_column(_ts, server_default=sa.func.now())


class DroppedClaim(Base):
    """Claims the grounding gate rejected (ADR-007) — kept ONLY here, for evaluation
    (TESTING.md E4: "hand-check 20 dropped claims to show the gate isn't discarding good
    ones indiscriminately"). Never written to Neo4j or Qdrant, never re-enters the
    pipeline — that invariant is enforced by every other module simply never reading
    this table; extract/claims.py and forage/loop.py only write to it."""

    __tablename__ = "dropped_claims"
    id: Mapped[int] = mapped_column(_bigint_pk, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(_uuid, nullable=True)
    paper_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    section: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    attempted_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    attempted_quote: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    verify_method: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[dt.datetime | None] = mapped_column(_ts, server_default=sa.func.now())


class ApiCache(Base):
    __tablename__ = "api_cache"
    cache_key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    source: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    response: Mapped[Any | None] = mapped_column(JSON_, nullable=True)
    status_code: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    fetched_at: Mapped[dt.datetime | None] = mapped_column(_ts, server_default=sa.func.now())
    expires_at: Mapped[dt.datetime | None] = mapped_column(_ts, nullable=True)


class LlmCache(Base):
    __tablename__ = "llm_cache"
    cache_key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    model: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    job: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    response: Mapped[Any | None] = mapped_column(JSON_, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    created_at: Mapped[dt.datetime | None] = mapped_column(_ts, server_default=sa.func.now())


class Cost(Base):
    __tablename__ = "costs"
    id: Mapped[int] = mapped_column(_bigint_pk, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(_uuid, nullable=True)
    job: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    model: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    usd: Mapped[float | None] = mapped_column(sa.Numeric(10, 6), nullable=True)
    cache_hit: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    at: Mapped[dt.datetime | None] = mapped_column(_ts, server_default=sa.func.now())


class RelationRow(Base):
    __tablename__ = "relations"
    id: Mapped[int] = mapped_column(_bigint_pk, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(_uuid, nullable=True)
    source_claim_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    target_claim_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    judged_by: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[dt.datetime | None] = mapped_column(_ts, server_default=sa.func.now())
    __table_args__ = (
        sa.Index("ix_relations_run_type", "run_id", "type"),
        sa.Index("ix_relations_pair", "source_claim_id", "target_claim_id"),
    )


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(_bigint_pk, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(_uuid, nullable=True)
    seq: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    payload: Mapped[Any | None] = mapped_column(JSON_, nullable=True)
    at: Mapped[dt.datetime | None] = mapped_column(_ts, server_default=sa.func.now())
    __table_args__ = (sa.Index("ix_events_run_seq", "run_id", "seq"),)


# ── engine / session plumbing ────────────────────────────────────────────────

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _Session
    if _engine is None:
        connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
        _engine = sa.create_engine(
            settings.postgres_dsn,
            future=True,
            pool_pre_ping=not settings.is_sqlite,
            connect_args=connect_args,
        )
        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    get_engine()
    assert _Session is not None
    return _Session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session. Commits on success, rolls back on error."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    """Create every table directly (test/bootstrap shortcut; prod uses Alembic)."""
    Base.metadata.create_all(get_engine())


def get_paper(paper_id: str) -> Any:
    """Load one `PaperMeta` from `papers`, or None."""
    from atlas.contracts import Author, PaperMeta

    with session_scope() as s:
        row = s.get(Paper, paper_id)
        if row is None:
            return None
        return PaperMeta(
            paper_id=row.paper_id,
            title=row.title,
            abstract=row.abstract,
            year=row.year,
            venue=row.venue,
            authors=[Author(**a) for a in (row.authors or [])],
            doi=row.doi,
            arxiv_id=row.arxiv_id,
            pmid=row.pmid,
            openalex_id=row.openalex_id,
            s2_corpus_id=row.s2_corpus_id,
            pdf_url=row.pdf_url,
            depth=row.depth or "metadata_only",
        )


def list_papers(limit: int = 200, offset: int = 0) -> list[Any]:
    """Load up to `limit` papers as `PaperMeta`, oldest first (deterministic)."""
    from atlas.contracts import Author, PaperMeta

    with session_scope() as s:
        stmt = (
            sa.select(Paper)
            .order_by(Paper.created_at, Paper.paper_id)
            .limit(limit)
            .offset(offset)
        )
        rows = (
            s.execute(stmt)
            .scalars()
            .all()
        )
        return [
            PaperMeta(
                paper_id=r.paper_id,
                title=r.title,
                abstract=r.abstract,
                year=r.year,
                venue=r.venue,
                authors=[Author(**a) for a in (r.authors or [])],
                doi=r.doi,
                arxiv_id=r.arxiv_id,
                pmid=r.pmid,
                openalex_id=r.openalex_id,
                s2_corpus_id=r.s2_corpus_id,
                pdf_url=r.pdf_url,
                depth=r.depth or "metadata_only",
            )
            for r in rows
        ]


def set_paper_depth(paper_id: str, depth: str) -> None:
    with session_scope() as s:
        row = s.get(Paper, paper_id)
        if row is not None:
            row.depth = depth


# ── run lifecycle + per-run mirrors (Phase 3) ──────────────────────────────


def create_run(run_id: str, query: str, mode: str, config_hash: str, keywords: Any = None) -> None:
    with session_scope() as s:
        s.merge(
            Run(
                run_id=run_id,
                query=query,
                mode=mode,
                config_hash=config_hash,
                keywords=keywords,
                status="running",
            )
        )


def finish_run(run_id: str, status: str, stop_reason: str) -> None:
    with session_scope() as s:
        row = s.get(Run, run_id)
        if row is not None:
            row.status = status
            row.stop_reason = stop_reason
            row.finished_at = sa.func.now()


def insert_claims(claims: list[Any], run_id: str) -> int:
    """Mirror verified claims into the `claims` table for cheap SQL analysis."""
    if not claims:
        return 0
    with session_scope() as s:
        for c in claims:
            s.merge(
                ClaimRow(
                    claim_id=c.claim_id,
                    run_id=run_id,
                    paper_id=c.paper_id,
                    text=c.text,
                    quote=c.quote,
                    quote_start=c.quote_char_start,
                    quote_end=c.quote_char_end,
                    section=c.section,
                    scope=c.scope.model_dump() if hasattr(c.scope, "model_dump") else c.scope,
                    verified=c.verified,
                    verify_method=c.verify_method,
                )
            )
    return len(claims)


def insert_dropped_claims(claims: list[Any], run_id: str) -> int:
    """Persist grounding-gate rejects for evaluation only (TESTING.md E4) — see
    `DroppedClaim`'s docstring for the invariant this must not violate."""
    if not claims:
        return 0
    with session_scope() as s:
        for c in claims:
            s.add(
                DroppedClaim(
                    run_id=run_id, paper_id=c.paper_id, section=c.section,
                    attempted_text=c.text, attempted_quote=c.quote,
                    verify_method=c.verify_method,
                )
            )
    return len(claims)


def sample_dropped_claims(n: int, *, seed: int = 42) -> list[dict[str, Any]]:
    """Random sample across every run for E4's "hand-check 20 dropped claims"."""
    with session_scope() as s:
        rows = s.execute(sa.select(DroppedClaim)).scalars().all()
    rng = random.Random(seed)
    picked = rng.sample(rows, min(n, len(rows)))
    return [
        {
            "run_id": r.run_id, "paper_id": r.paper_id, "section": r.section,
            "attempted_text": r.attempted_text, "attempted_quote": r.attempted_quote,
            "verify_method": r.verify_method,
        }
        for r in picked
    ]


def insert_relations(relations: list[Any], run_id: str) -> int:
    """Mirror judged Claim-Claim edges into `relations` (Job C, R2 eval)."""
    if not relations:
        return 0
    with session_scope() as s:
        for r in relations:
            s.add(
                RelationRow(
                    run_id=run_id,
                    source_claim_id=r.source_claim_id,
                    target_claim_id=r.target_claim_id,
                    type=r.type,
                    confidence=r.confidence,
                    rationale=r.rationale,
                    judged_by=r.judged_by,
                )
            )
    return len(relations)


def paper_claims_and_relations(run_id: str, paper_id: str) -> tuple[list[Any], list[Any]]:
    """(claims, relations) for GET /runs/{id}/papers/{pid} (api/routes/runs.py).

    `claims` table is a partial mirror (see insert_claims) — it has quotes/offsets/scope
    but not polarity/confidence (those never left the in-memory Claim during the run), so
    reconstructed Claim objects default them. That's fine for this endpoint's purpose
    (showing quotes with highlighted spans), not a data-loss bug."""
    from atlas.contracts import Claim, ClaimScope, Relation

    with session_scope() as s:
        claim_rows = s.execute(
            sa.select(ClaimRow).where(ClaimRow.run_id == run_id, ClaimRow.paper_id == paper_id)
        ).scalars().all()
        claim_ids = {r.claim_id for r in claim_rows}
        relation_rows = (
            s.execute(
                sa.select(RelationRow).where(
                    RelationRow.run_id == run_id,
                    sa.or_(
                        RelationRow.source_claim_id.in_(claim_ids),
                        RelationRow.target_claim_id.in_(claim_ids),
                    ),
                )
            ).scalars().all()
            if claim_ids
            else []
        )

    claims = [
        Claim(
            claim_id=r.claim_id,
            paper_id=r.paper_id or "",
            text=r.text or "",
            quote=r.quote or "",
            section=r.section or "other",
            scope=ClaimScope(**(r.scope or {"what_was_tested": ""})),
            verified=bool(r.verified),
            verify_method=r.verify_method,
            quote_char_start=r.quote_start,
            quote_char_end=r.quote_end,
        )
        for r in claim_rows
    ]
    relations = [
        Relation(
            source_claim_id=r.source_claim_id or "",
            target_claim_id=r.target_claim_id or "",
            type=r.type,
            confidence=r.confidence or 0.0,
            rationale=r.rationale or "",
            judged_by=r.judged_by or "",
            run_id=run_id,
        )
        for r in relation_rows
    ]
    return claims, relations


def delete_run(run_id: str) -> dict[str, int]:
    """Remove a run's Postgres rows (frontier / claims / relations / costs / events / runs).
    Shared `papers` rows are kept."""
    removed: dict[str, int] = {}
    with session_scope() as s:
        for name, model in (
            ("frontier", Frontier), ("claims", ClaimRow), ("relations", RelationRow),
            ("costs", Cost), ("events", Event), ("runs", Run),
        ):
            col = model.run_id
            res = s.execute(sa.delete(model).where(col == run_id))
            removed[name] = int(getattr(res, "rowcount", 0) or 0)
    return removed


def judged_pairs(run_id: str) -> list[dict[str, Any]]:
    """Every judged Claim-Claim pair for a run, with both claims' text/quote (R2 export)."""
    with session_scope() as s:
        rows = s.execute(
            sa.text(
                "SELECT r.type, r.confidence, r.rationale, r.judged_by, "
                "  r.source_claim_id AS a_claim_id, r.target_claim_id AS b_claim_id, "
                "  a.text AS a_text, a.quote AS a_quote, a.section AS a_section, "
                "  b.text AS b_text, b.quote AS b_quote, b.section AS b_section "
                "FROM relations r "
                "LEFT JOIN claims a ON a.claim_id = r.source_claim_id "
                "LEFT JOIN claims b ON b.claim_id = r.target_claim_id "
                "WHERE r.run_id = :r"
            ),
            {"r": run_id},
        ).mappings().all()
    return [dict(row) for row in rows]


def run_cost(run_id: str) -> float:
    with session_scope() as s:
        total = s.execute(
            sa.select(sa.func.coalesce(sa.func.sum(Cost.usd), 0)).where(Cost.run_id == run_id)
        ).scalar_one()
    return float(total or 0.0)


def run_cost_breakdown(run_id: str) -> dict[str, Any]:
    """Token/call/cache-hit-rate summary for one run — evaluation/e7_cost.py (TESTING.md
    E7: "wall-clock, USD, tokens, API calls, cache hit rate, full-text ratio... a
    cost-per-paper figure")."""
    with session_scope() as s:
        rows = s.execute(sa.select(Cost).where(Cost.run_id == run_id)).scalars().all()
    n_calls = len(rows)
    cache_hits = sum(1 for r in rows if r.cache_hit)
    return {
        "n_calls": n_calls,
        "cache_hits": cache_hits,
        "cache_hit_rate": round(cache_hits / n_calls, 3) if n_calls else 0.0,
        "prompt_tokens": sum(r.prompt_tokens or 0 for r in rows),
        "output_tokens": sum(r.output_tokens or 0 for r in rows),
        "usd": round(sum(float(r.usd or 0) for r in rows), 6),
    }


def emit_event(run_id: str, event_type: str, payload: dict[str, Any]) -> int:
    """Persist one event, auto-assigning the next per-run seq. A run's own loop iteration
    is strictly sequential (single thread per run_id even under the API's background-task
    model — ARCHITECTURE.md "one process, not a queue-worker fleet"), so a plain
    max-then-insert is race-free without extra locking. Returns the assigned seq so the
    caller (or a test) can correlate it if needed."""
    with session_scope() as s:
        raw_nxt = s.execute(
            sa.select(sa.func.coalesce(sa.func.max(Event.seq), -1) + 1).where(
                Event.run_id == run_id
            )
        ).scalar_one()
        nxt = int(raw_nxt) if raw_nxt is not None else 0
        s.add(Event(run_id=run_id, seq=nxt, type=event_type, payload=payload))
    return nxt


def events_since(run_id: str, since_seq: int = -1) -> list[dict[str, Any]]:
    """Events for a run with seq > since_seq, ordered — replay for GET /runs/{id}/events."""
    with session_scope() as s:
        rows = s.execute(
            sa.select(Event.seq, Event.type, Event.at, Event.payload)
            .where(Event.run_id == run_id, Event.seq > since_seq)
            .order_by(Event.seq)
        ).all()
    return [
        {"seq": seq, "type": etype, "at": str(at) if at else None, "payload": payload}
        for seq, etype, at, payload in rows
    ]


def run_keywords(run_id: str) -> list[str]:
    """Keywords from the run's `run_started` event — Run.keywords itself is never
    populated (create_run() is called before Job A's output exists), so this is the
    only place they're recoverable from. Used by GET /runs/{id} (RunDetail.keywords)."""
    with session_scope() as s:
        payload = s.execute(
            sa.select(Event.payload)
            .where(Event.run_id == run_id, Event.type == "run_started")
            .order_by(Event.seq)
            .limit(1)
        ).scalar_one_or_none()
    if not payload:
        return []
    return list(payload.get("keywords") or [])


# ── inspection (`atlas show`) ──────────────────────────────────────────────


def list_runs(limit: int = 15) -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            sa.select(
                Run.run_id, Run.query, Run.mode, Run.status, Run.stop_reason, Run.started_at
            ).order_by(Run.started_at.desc()).limit(limit)
        ).all()
    return [
        {
            "run_id": r[0], "query": r[1], "mode": r[2], "status": r[3],
            "stop_reason": r[4], "started_at": str(r[5]) if r[5] else None,
        }
        for r in rows
    ]


def run_summary(run_id: str) -> dict[str, Any] | None:
    with session_scope() as s:
        run = s.get(Run, run_id)
        if run is None:
            return None
        reads = s.execute(
            sa.text(
                "SELECT f.read_order, f.score, f.relevance, f.novelty, f.recency, "
                "       f.discovered_via, p.paper_id, p.title, p.depth, "
                "       f.pagerank, f.contest "
                "FROM frontier f JOIN papers p ON p.paper_id = f.paper_id "
                "WHERE f.run_id = :r AND f.state = 'read' ORDER BY f.read_order"
            ),
            {"r": run_id},
        ).all()
        claims_by_paper: dict[str, int] = {
            row[0]: row[1]
            for row in s.execute(
                sa.text("SELECT paper_id, count(*) FROM claims WHERE run_id=:r GROUP BY paper_id"),
                {"r": run_id},
            ).all()
        }
        states: dict[str, int] = {
            row[0]: row[1]
            for row in s.execute(
                sa.text("SELECT state, count(*) FROM frontier WHERE run_id=:r GROUP BY state"),
                {"r": run_id},
            ).all()
        }
        cost = s.execute(
            sa.text(
                "SELECT coalesce(sum(usd),0), count(*) FROM costs WHERE run_id=:r"
            ),
            {"r": run_id},
        ).one()
        rel_by_type: dict[str, int] = {
            row[0]: row[1]
            for row in s.execute(
                sa.text("SELECT type, count(*) FROM relations WHERE run_id=:r GROUP BY type"),
                {"r": run_id},
            ).all()
        }
    return {
        "run_id": run.run_id,
        "query": run.query,
        "mode": run.mode,
        "status": run.status,
        "stop_reason": run.stop_reason,
        "config_hash": run.config_hash,
        "started_at": str(run.started_at) if run.started_at else None,
        "finished_at": str(run.finished_at) if run.finished_at else None,
        "reads": [
            {
                "order": r[0], "score": r[1], "relevance": r[2], "novelty": r[3],
                "recency": r[4], "via": r[5], "paper_id": r[6], "title": r[7],
                "depth": r[8], "pagerank": r[9], "contest": r[10],
                "claims": claims_by_paper.get(r[6], 0),
            }
            for r in reads
        ],
        "frontier_states": states,
        "relations_by_type": rel_by_type,
        "total_usd": float(cost[0] or 0.0),
        "llm_calls": int(cost[1] or 0),
    }


def run_timeline(run_id: str) -> list[dict[str, Any]]:
    """Per-read-step saturation/cost series for the dashboard's timeline chart
    ([S] stretch item, docs/ROADMAP.md Phase 6) — one point per `saturation` event
    (`forage/loop.py`, emitted once per paper read, carrying the exact new_info/EMA
    signal the stopping criterion itself uses, plus running totals recorded at
    that moment). Reuses the real event log rather than reconstructing an
    approximation from other tables.

    Runs recorded before `total_usd` was added to the event payload will have
    `cumulative_usd: 0.0` for every point — cost data genuinely isn't available
    for those, not silently wrong."""
    events = [e for e in events_since(run_id) if e["type"] == "saturation"]
    claims_running = 0
    points: list[dict[str, Any]] = []
    for e in events:
        p = e["payload"]
        claims_running += int(p.get("claims_kept") or 0)
        points.append(
            {
                "read_order": int(p.get("step", 0)),
                "paper_id": str(p.get("paper_id", "")),
                "title": str(p.get("title", "")),
                "score": None,
                "new_info": p.get("new_info"),
                "ema": p.get("ema"),
                "cumulative_claims": claims_running,
                "cumulative_usd": round(float(p.get("total_usd") or 0.0), 6),
            }
        )
    return points


def upsert_papers(papers: list[Any]) -> int:
    """Insert-or-update `PaperMeta` records into `papers` (the existence source of truth).

    Keyed on the canonical `paper_id`; safe to call repeatedly (incremental writes).
    Returns the number of rows written.
    """
    if not papers:
        return 0
    with session_scope() as s:
        for p in papers:
            s.merge(
                Paper(
                    paper_id=p.paper_id,
                    title=p.title,
                    year=p.year,
                    venue=p.venue,
                    doi=p.doi,
                    arxiv_id=p.arxiv_id,
                    pmid=p.pmid,
                    openalex_id=p.openalex_id,
                    s2_corpus_id=p.s2_corpus_id,
                    abstract=p.abstract,
                    authors=[a.model_dump() for a in p.authors],
                    pdf_url=p.pdf_url,
                    depth=p.depth.value if hasattr(p.depth, "value") else p.depth,
                )
            )
    return len(papers)


def ping() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


def reset_engine() -> None:
    """Drop cached engine/sessionmaker — used by tests that swap the DSN."""
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None
