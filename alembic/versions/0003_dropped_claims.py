"""add dropped_claims table — grounding-gate rejects, kept for evaluation only (TESTING.md
E4: "hand-check 20 dropped claims"). Never written to Neo4j/Qdrant; see DroppedClaim's
docstring in store/db.py for the invariant.

Revision ID: 0003_dropped_claims
Revises: 0002_relations
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_dropped_claims"
down_revision: str | None = "0002_relations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "dropped_claims",
        sa.Column("id", _BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text()),
        sa.Column("paper_id", sa.Text()),
        sa.Column("section", sa.Text()),
        sa.Column("attempted_text", sa.Text()),
        sa.Column("attempted_quote", sa.Text()),
        sa.Column("verify_method", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dropped_claims_run", "dropped_claims", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_dropped_claims_run", "dropped_claims")
    op.drop_table("dropped_claims")
