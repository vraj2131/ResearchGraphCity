"""Scope reusable neighbors by corpus membership.

Revision ID: 20260918_0005
Revises: 20260918_0004
"""

from alembic import op
import sqlalchemy as sa


revision = "20260918_0005"
down_revision = "20260918_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_neighbors",
        sa.Column("scope_key", sa.String(length=64), server_default="legacy", nullable=False),
    )
    op.drop_constraint("uq_paper_neighbors_target", "paper_neighbors", type_="unique")
    op.drop_constraint("paper_neighbors_pkey", "paper_neighbors", type_="primary")
    op.create_primary_key(
        "paper_neighbors_pkey",
        "paper_neighbors",
        ["model", "algorithm_version", "scope_key", "source_openalex_id", "rank"],
    )
    op.create_unique_constraint(
        "uq_paper_neighbors_target",
        "paper_neighbors",
        ["model", "algorithm_version", "scope_key", "source_openalex_id", "target_openalex_id"],
    )
    op.drop_index("ix_paper_neighbors_target", table_name="paper_neighbors")
    op.create_index(
        "ix_paper_neighbors_target",
        "paper_neighbors",
        ["model", "algorithm_version", "scope_key", "target_openalex_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_paper_neighbors_target", "paper_neighbors", type_="unique")
    op.drop_constraint("paper_neighbors_pkey", "paper_neighbors", type_="primary")
    op.create_primary_key(
        "paper_neighbors_pkey",
        "paper_neighbors",
        ["model", "algorithm_version", "source_openalex_id", "rank"],
    )
    op.create_unique_constraint(
        "uq_paper_neighbors_target",
        "paper_neighbors",
        ["model", "algorithm_version", "source_openalex_id", "target_openalex_id"],
    )
    op.drop_index("ix_paper_neighbors_target", table_name="paper_neighbors")
    op.create_index(
        "ix_paper_neighbors_target",
        "paper_neighbors",
        ["model", "algorithm_version", "target_openalex_id"],
    )
    op.drop_column("paper_neighbors", "scope_key")
