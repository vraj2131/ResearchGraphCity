"""Add overlapping Graph Cities memberships and explicit edge ownership.

Revision ID: 20260924_0009
Revises: 20260919_0008
"""
from alembic import op

revision = "20260924_0009"
down_revision = "20260919_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_buildings_city_id", "buildings", ["city_id", "id"])
    op.create_unique_constraint("uq_floors_city_building_id", "floors", ["city_id", "building_id", "id"])
    op.execute("""
CREATE TABLE building_papers (
	city_id UUID NOT NULL, 
	building_id UUID NOT NULL, 
	openalex_id TEXT NOT NULL, 
	floor_id UUID, 
	PRIMARY KEY (city_id, building_id, openalex_id), 
	FOREIGN KEY(city_id, openalex_id) REFERENCES city_papers (city_id, openalex_id) ON DELETE CASCADE, 
	FOREIGN KEY(city_id, building_id) REFERENCES buildings (city_id, id) ON DELETE CASCADE, 
	FOREIGN KEY(city_id, building_id, floor_id) REFERENCES floors (city_id, building_id, id) ON DELETE CASCADE
)
    """)
    op.execute("""
CREATE INDEX ix_building_papers_paper ON building_papers (city_id, openalex_id)
    """)
    op.execute("""
CREATE TABLE floor_papers (
	city_id UUID NOT NULL, 
	floor_id UUID NOT NULL, 
	openalex_id TEXT NOT NULL, 
	building_id UUID NOT NULL, 
	PRIMARY KEY (city_id, floor_id, openalex_id), 
	FOREIGN KEY(city_id, building_id, openalex_id) REFERENCES building_papers (city_id, building_id, openalex_id) ON DELETE CASCADE, 
	FOREIGN KEY(city_id, building_id, floor_id) REFERENCES floors (city_id, building_id, id) ON DELETE CASCADE
)
    """)
    op.execute("""
CREATE INDEX ix_floor_papers_membership ON floor_papers (city_id, building_id, openalex_id)
    """)
    op.execute("""
CREATE TABLE decomposition_edges (
	city_id UUID NOT NULL, 
	source_openalex_id TEXT NOT NULL, 
	target_openalex_id TEXT NOT NULL, 
	building_id UUID NOT NULL, 
	floor_id UUID NOT NULL, 
	peel INTEGER NOT NULL, 
	wave INTEGER NOT NULL, 
	fragment INTEGER NOT NULL, 
	wave_component INTEGER NOT NULL, 
	PRIMARY KEY (city_id, source_openalex_id, target_openalex_id), 
	FOREIGN KEY(city_id, building_id, source_openalex_id) REFERENCES building_papers (city_id, building_id, openalex_id) ON DELETE CASCADE, 
	FOREIGN KEY(city_id, building_id, target_openalex_id) REFERENCES building_papers (city_id, building_id, openalex_id) ON DELETE CASCADE, 
	FOREIGN KEY(city_id, building_id, floor_id) REFERENCES floors (city_id, building_id, id) ON DELETE CASCADE
)
    """)
    op.execute("""
CREATE INDEX ix_decomposition_edges_building ON decomposition_edges (city_id, building_id, floor_id)
    """)
    op.execute("""
        INSERT INTO building_papers (city_id, building_id, openalex_id, floor_id)
        SELECT city_id, building_id, openalex_id, floor_id FROM city_papers
        WHERE building_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO floor_papers (city_id, building_id, openalex_id, floor_id)
        SELECT city_id, building_id, openalex_id, floor_id FROM city_papers
        WHERE building_id IS NOT NULL AND floor_id IS NOT NULL
    """)


def downgrade():
    op.drop_table("decomposition_edges")
    op.drop_table("floor_papers")
    op.drop_table("building_papers")
    op.drop_constraint("uq_floors_city_building_id", "floors", type_="unique")
    op.drop_constraint("uq_buildings_city_id", "buildings", type_="unique")
