"""Fix embedding dimensions and add approximate-neighbor indexes.

Revision ID: 20260917_0002
Revises: 20260917_0001
"""

from alembic import op


revision = "20260917_0002"
down_revision = "20260917_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("paper_embeddings", "buildings", "districts"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN embedding TYPE vector(64) USING embedding::vector(64)")
    op.execute(
        "CREATE INDEX ix_paper_embeddings_hnsw ON paper_embeddings "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX ix_buildings_embedding_hnsw ON buildings "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.drop_index("ix_buildings_embedding_hnsw", table_name="buildings")
    op.drop_index("ix_paper_embeddings_hnsw", table_name="paper_embeddings")
    for table in ("paper_embeddings", "buildings", "districts"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN embedding TYPE vector USING embedding::vector")
