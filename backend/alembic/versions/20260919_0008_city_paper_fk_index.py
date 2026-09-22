"""Index city-paper metadata foreign key.

Revision ID: 20260919_0008
Revises: 20260918_0007
"""

from alembic import op


revision = "20260919_0008"
down_revision = "20260918_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_city_papers_openalex_id", "city_papers", ["openalex_id"])


def downgrade() -> None:
    op.drop_index("ix_city_papers_openalex_id", table_name="city_papers")
