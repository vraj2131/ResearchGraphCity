"""Index paper-neighbor foreign keys for bounded deletion.

Revision ID: 20260918_0006
Revises: 20260918_0005
"""

from alembic import op


revision = "20260918_0006"
down_revision = "20260918_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_paper_neighbors_source_fk", "paper_neighbors", ["source_openalex_id"])
    op.create_index("ix_paper_neighbors_target_fk", "paper_neighbors", ["target_openalex_id"])


def downgrade() -> None:
    op.drop_index("ix_paper_neighbors_target_fk", table_name="paper_neighbors")
    op.drop_index("ix_paper_neighbors_source_fk", table_name="paper_neighbors")
