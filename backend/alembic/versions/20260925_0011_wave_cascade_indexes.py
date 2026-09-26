"""Index floor and membership foreign keys for large wave decompositions."""
from alembic import op

revision = '20260925_0011'
down_revision = '20260925_0010'
branch_labels = None
depends_on = None

INDEXES = [
    ('ix_city_papers_floor_fk', 'city_papers', ['floor_id']),
    ('ix_city_papers_building_fk', 'city_papers', ['building_id']),
    ('ix_building_papers_floor_fk', 'building_papers', ['city_id', 'building_id', 'floor_id']),
    ('ix_decomposition_edges_target_fk', 'decomposition_edges', ['city_id', 'building_id', 'target_openalex_id']),
]


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
