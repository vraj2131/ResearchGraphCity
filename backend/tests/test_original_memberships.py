from __future__ import annotations

import itertools
import os

import pytest
from sqlalchemy.engine import make_url

from app.config import Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.repositories.postgres_city import PostgresCityRepository


@pytest.fixture()
def original_repository():
    from app.models import (
        BuildingRecord, BuildingPaperRecord, CityRecord, CityPaperRecord,
        FloorRecord, FloorPaperRecord, PaperRecord, PaperEdgeRecord, DecompositionEdgeRecord,
    )

    url = os.environ["TEST_DATABASE_URL"]
    assert make_url(url).database.endswith("_test"), "Refuse to reset a non-test database"
    settings = Settings(url, "postgres", 1.0, 300, "hashing-64-v1")
    engine = create_engine_from_settings(settings)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory.begin() as session:
        city = CityRecord(external_id="original", name="Original", kind="seeded", status="ready",
                          target_paper_count=10, paper_count=5, algorithm_version="graph-cities-v1")
        session.add(city)
        session.flush()
        buildings = []
        floors = []
        for name, peel, count, edge_count in [("high", 3, 4, 6), ("low", 1, 3, 2)]:
            building = BuildingRecord(city_id=city.id, external_id=name, node_count=count, edge_count=edge_count,
                                      internal_density=0.5, avg_core=peel, max_core=peel, height=20, footprint=10,
                                      x=0, z=0, top_labels=["Graph networks"], quality_metrics={"algorithm": "graph-cities-v1"})
            session.add(building)
            session.flush()
            floor = FloorRecord(city_id=city.id, building_id=building.id, external_id=f"floor-{name}",
                                floor_index=1, core_min=peel, core_max=peel, node_count=count)
            session.add(floor)
            session.flush()
            buildings.append(building)
            floors.append(floor)
        for i in range(5):
            paper = PaperRecord(openalex_id=f"W{i}", title=f"Graph paper {i}", publication_year=2021 if i == 1 else 2020, citation_count=1)
            session.add(paper)
        session.flush()
        for i in range(5):
            primary = 0 if i < 4 else 1
            session.add(CityPaperRecord(city_id=city.id, openalex_id=f"W{i}", external_paper_id=f"P{i}",
                                        building_id=buildings[primary].id, floor_id=floors[primary].id))
        session.flush()
        for group, members in enumerate([(0, 1, 2, 3), (1, 2, 4)]):
            for i in members:
                session.add(BuildingPaperRecord(city_id=city.id, building_id=buildings[group].id,
                                                openalex_id=f"W{i}", floor_id=floors[group].id))
        session.flush()
        for group, members in enumerate([(0, 1, 2, 3), (1, 2, 4)]):
            for i in members:
                session.add(FloorPaperRecord(city_id=city.id, building_id=buildings[group].id,
                                            floor_id=floors[group].id, openalex_id=f"W{i}"))
        for group, edges in enumerate([list(itertools.combinations(range(4), 2)), [(1, 4), (2, 4)]]):
            for u, v in edges:
                session.add(PaperEdgeRecord(city_id=city.id, source_openalex_id=f"W{u}", target_openalex_id=f"W{v}",
                                            edge_type="citation", weight=1.0, directed=True))
                session.add(DecompositionEdgeRecord(city_id=city.id, source_openalex_id=f"W{u}", target_openalex_id=f"W{v}",
                                                    building_id=buildings[group].id, floor_id=floors[group].id,
                                                    peel=3 if group == 0 else 1, wave=1, fragment=0, wave_component=0))
    yield PostgresCityRepository(factory)
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_shared_paper_is_retrievable_from_each_building_and_floor(original_repository):
    repository = original_repository
    low = repository.get_building_papers("original", "low")
    assert {p["paper_id"] for p in low} == {"P1", "P2", "P4"}
    assert {p["paper_id"] for p in repository.get_building_papers("original", "low", "floor-low")} == {"P1", "P2", "P4"}
    assert {p["paper_id"] for p in repository.get_building_papers("original", "high")} == {"P0", "P1", "P2", "P3"}
    shared = next(p for p in low if p["paper_id"] == "P1")
    assert {location["building_id"] for location in shared["locations"]} == {"high", "low"}
    assert shared["building_id"] == "low"
    assert [p["paper_id"] for p in repository.get_building_papers("original", "low", limit=1, cursor="P1")] == ["P2"]


def test_internal_edges_use_decomposition_ownership(original_repository):
    edges = original_repository.get_building_edges("original", "low")
    assert len(edges) == 2  # The high-layer edge P1-P2 must not leak in.
    assert len(original_repository.get_building_edges("original", "low", "floor-low")) == 2
    assert len(original_repository.get_building_edges("original", "high")) == 6


def test_search_matches_secondary_building_without_duplicate_global_results(original_repository):
    result = original_repository.search_papers("original", "graph", filters={"building_id": "low"})
    assert {p["paper_id"] for p in result} == {"P1", "P2", "P4"}
    assert all(p["building_id"] == "low" for p in result)
    assert len(original_repository.search_papers("original", "graph")) == 5
    timeline = original_repository.get_timeline("original")
    assert sum(year["paper_count"] for year in timeline["years"]) == 5
    shared_year = next(year for year in timeline["years"] if year["year"] == 2021)
    assert shared_year["paper_count"] == 1
    assert shared_year["building_count"] == 2
