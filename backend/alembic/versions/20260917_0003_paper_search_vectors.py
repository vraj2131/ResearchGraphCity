"""Maintain indexed paper full-text search vectors.

Revision ID: 20260917_0003
Revises: 20260917_0002
"""

from alembic import op


revision = "20260917_0003"
down_revision = "20260917_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE cities SET embedding_model = 'hashing-64-v1' "
        "WHERE algorithm_version = 'platform-v1' AND embedding_model = 'tfidf-svd-64'"
    )
    op.execute(
        "UPDATE papers SET search_vector = to_tsvector('pg_catalog.english', "
        "concat_ws(' ', title, abstract, venue, publisher))"
    )
    op.execute(
        "CREATE TRIGGER papers_search_vector_update BEFORE INSERT OR UPDATE OF title, abstract, venue, publisher "
        "ON papers FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger("
        "search_vector, 'pg_catalog.english', title, abstract, venue, publisher)"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS papers_search_vector_update ON papers")
