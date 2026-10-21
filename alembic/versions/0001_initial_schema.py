"""initial schema — runs, papers, frontier, claims, caches, costs, events

Mirrors docs/DATA_MODEL.md §2. Portable types (Text ids / JSON / non-native enums) so
the same migration runs on the SQLite dev default and the Postgres container. Ids are
Text, not UUID, so the identical string keys Postgres, Neo4j and the data/runs/<id>/ dir.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_ = sa.JSON().with_variant(JSONB(), "postgresql")
# SQLite only autoincrements a plain INTEGER PK, not BIGINT.
_BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
_DEPTH = sa.Enum(
    "full_text", "abstract_only", "metadata_only", name="paper_depth", native_enum=False
)
_FRONTIER_STATE = sa.Enum(
    "pending", "parked", "reading", "read", "dropped", "failed",
    name="frontier_state", native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("run_id", sa.Text(), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("keywords", JSON_),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("stop_reason", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "papers",
        sa.Column("paper_id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer()),
        sa.Column("venue", sa.Text()),
        sa.Column("doi", sa.Text()),
        sa.Column("arxiv_id", sa.Text()),
        sa.Column("pmid", sa.Text()),
        sa.Column("openalex_id", sa.Text()),
        sa.Column("s2_corpus_id", sa.Text()),
        sa.Column("abstract", sa.Text()),
        sa.Column("authors", JSON_),
        sa.Column("pdf_url", sa.Text()),
        sa.Column("depth", _DEPTH, server_default="metadata_only"),
        sa.Column("raw", JSON_),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_papers_doi", "papers", ["doi"])

    op.create_table(
        "frontier",
        sa.Column("run_id", sa.Text(), sa.ForeignKey("runs.run_id"), primary_key=True),
        sa.Column(
            "paper_id", sa.Text(), sa.ForeignKey("papers.paper_id"), primary_key=True
        ),
        sa.Column("state", _FRONTIER_STATE, nullable=False, server_default="pending"),
        sa.Column("score", sa.Float()),
        sa.Column("relevance", sa.Float()),
        sa.Column("pagerank", sa.Float()),
        sa.Column("novelty", sa.Float()),
        sa.Column("contest", sa.Float()),
        sa.Column("recency", sa.Float()),
        sa.Column("discovered_via", sa.Text()),
        sa.Column("parked_reason", sa.Text()),
        sa.Column("read_order", sa.Integer()),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_frontier_run_state_score", "frontier", ["run_id", "state", "score"]
    )

    op.create_table(
        "claims",
        sa.Column("claim_id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text()),
        sa.Column("paper_id", sa.Text()),
        sa.Column("text", sa.Text()),
        sa.Column("quote", sa.Text()),
        sa.Column("quote_start", sa.Integer()),
        sa.Column("quote_end", sa.Integer()),
        sa.Column("section", sa.Text()),
        sa.Column("scope", JSON_),
        sa.Column("verified", sa.Boolean()),
        sa.Column("verify_method", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "api_cache",
        sa.Column("cache_key", sa.Text(), primary_key=True),
        sa.Column("source", sa.Text()),
        sa.Column("response", JSON_),
        sa.Column("status_code", sa.Integer()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "llm_cache",
        sa.Column("cache_key", sa.Text(), primary_key=True),
        sa.Column("model", sa.Text()),
        sa.Column("job", sa.Text()),
        sa.Column("response", JSON_),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "costs",
        sa.Column("id", _BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text()),
        sa.Column("job", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("usd", sa.Numeric(10, 6)),
        sa.Column("cache_hit", sa.Boolean()),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "events",
        sa.Column("id", _BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text()),
        sa.Column("seq", sa.BigInteger()),
        sa.Column("type", sa.Text()),
        sa.Column("payload", JSON_),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_events_run_seq", "events", ["run_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_events_run_seq", "events")
    op.drop_table("events")
    op.drop_table("costs")
    op.drop_table("llm_cache")
    op.drop_table("api_cache")
    op.drop_table("claims")
    op.drop_index("ix_frontier_run_state_score", "frontier")
    op.drop_table("frontier")
    op.drop_index("ix_papers_doi", "papers")
    op.drop_table("papers")
    op.drop_table("runs")
