"""Add reusable paper-neighbor cache.

Revision ID: 20260918_0004
Revises: 20260917_0003
"""

from alembic import op
import sqlalchemy as sa


revision = "20260918_0004"
down_revision = "20260917_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_neighbors",
        sa.Column("model", sa.String(length=240), nullable=False),
        sa.Column("algorithm_version", sa.String(length=80), nullable=False),
        sa.Column("source_openalex_id", sa.Text(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("target_openalex_id", sa.Text(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_openalex_id"], ["papers.openalex_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_openalex_id"], ["papers.openalex_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("model", "algorithm_version", "source_openalex_id", "rank"),
        sa.UniqueConstraint(
            "model",
            "algorithm_version",
            "source_openalex_id",
            "target_openalex_id",
            name="uq_paper_neighbors_target",
        ),
    )
    op.create_index(
        "ix_paper_neighbors_target",
        "paper_neighbors",
        ["model", "algorithm_version", "target_openalex_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_paper_neighbors_target", table_name="paper_neighbors")
    op.drop_table("paper_neighbors")
