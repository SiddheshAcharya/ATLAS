"""add relations table — SQL mirror of the Claim-Claim edges (Job C, R2 eval)

Revision ID: 0002_relations
Revises: 0001_initial
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_relations"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "relations",
        sa.Column("id", _BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text()),
        sa.Column("source_claim_id", sa.Text()),
        sa.Column("target_claim_id", sa.Text()),
        sa.Column("type", sa.Text()),
        sa.Column("confidence", sa.Float()),
        sa.Column("rationale", sa.Text()),
        sa.Column("judged_by", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_relations_run_type", "relations", ["run_id", "type"])
    op.create_index(
        "ix_relations_pair", "relations", ["source_claim_id", "target_claim_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_relations_pair", "relations")
    op.drop_index("ix_relations_run_type", "relations")
    op.drop_table("relations")
