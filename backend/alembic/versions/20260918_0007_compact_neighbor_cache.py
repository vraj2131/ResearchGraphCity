"""Compact neighbor cache to one array row per source paper.

Revision ID: 20260918_0007
Revises: 20260918_0006
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260918_0007"
down_revision = "20260918_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("paper_neighbors")
    op.create_table(
        "paper_neighbors",
        sa.Column("model", sa.String(length=240), nullable=False),
        sa.Column("algorithm_version", sa.String(length=80), nullable=False),
        sa.Column("scope_key", sa.String(length=64), nullable=False),
        sa.Column("source_openalex_id", sa.Text(), nullable=False),
        sa.Column("target_openalex_ids", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("similarities", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_openalex_id"], ["papers.openalex_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("model", "algorithm_version", "scope_key", "source_openalex_id"),
    )
    op.create_index("ix_paper_neighbors_source_fk", "paper_neighbors", ["source_openalex_id"])


def downgrade() -> None:
    op.drop_table("paper_neighbors")
    op.create_table(
        "paper_neighbors",
        sa.Column("model", sa.String(length=240), nullable=False),
        sa.Column("algorithm_version", sa.String(length=80), nullable=False),
        sa.Column("scope_key", sa.String(length=64), nullable=False),
        sa.Column("source_openalex_id", sa.Text(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("target_openalex_id", sa.Text(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_openalex_id"], ["papers.openalex_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_openalex_id"], ["papers.openalex_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("model", "algorithm_version", "scope_key", "source_openalex_id", "rank"),
        sa.UniqueConstraint(
            "model", "algorithm_version", "scope_key", "source_openalex_id", "target_openalex_id",
            name="uq_paper_neighbors_target",
        ),
    )
    op.create_index("ix_paper_neighbors_source_fk", "paper_neighbors", ["source_openalex_id"])
    op.create_index("ix_paper_neighbors_target_fk", "paper_neighbors", ["target_openalex_id"])
    op.create_index(
        "ix_paper_neighbors_target",
        "paper_neighbors",
        ["model", "algorithm_version", "scope_key", "target_openalex_id"],
    )
