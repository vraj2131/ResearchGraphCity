from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.models import BuildingRecord, CityPaperRecord, CityRecord, FloorRecord, PaperRecord
from app.repositories.json_city import JsonCityRepository
from app.repositories.postgres_city import PostgresCityRepository
from app.storage import write_json


@pytest.fixture()
def json_repository(tmp_path: Path):
    write_json(
        tmp_path / "research_buildings.json",
        [{"building_id": "B_R_0001", "vertex_ids": ["R_000001"], "floors": []}],
    )
    write_json(tmp_path / "research_bridges.json", [])
    write_json(tmp_path / "research_streets.json", [])
    write_json(tmp_path / "research_communities.json", [])
    write_json(tmp_path / "research_vertices.json", [{"paper_id": "R_000001", "title": "Paper One"}])
    write_json(tmp_path / "research_edges.json", [])
    return JsonCityRepository(tmp_path)


@pytest.fixture()
def postgres_repository():
    settings = Settings(
        database_url=os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_backend="postgres",
        worker_poll_seconds=1.0,
        job_stale_seconds=300,
        embedding_model="tfidf-svd-64",
    )
    engine = create_engine_from_settings(settings)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)

    with Session(engine) as session:
        city = CityRecord(
            external_id="research",
            name="Research Graph City",
            kind="research",
            status="ready",
            target_paper_count=1_000,
            paper_count=1,
            building_count=1,
            configuration={},
        )
        session.add(city)
        session.flush()
        building = BuildingRecord(
            city_id=city.id,
            external_id="B_R_0001",
            node_count=1,
            edge_count=0,
            internal_density=0.0,
            avg_core=0.0,
            max_core=0,
            height=10.0,
            footprint=8.0,
            x=0.0,
            z=0.0,
            top_labels=["Graph Visualization"],
            semantic_domain="graph_ai",
            semantic_domain_name="Graph, AI, and Computation",
            semantic_color="#6ee7f9",
            profile={},
            original_labels={"topics": ["Graph Visualization"]},
            activation={},
            activation_score=0.2,
            quality_metrics={},
        )
        session.add(building)
        session.flush()
        floor = FloorRecord(
            city_id=city.id,
            building_id=building.id,
            external_id="F_B_R_0001_01",
            floor_index=1,
            core_min=0,
            core_max=0,
            node_count=1,
            top_labels=["Graph Visualization"],
        )
        paper = PaperRecord(openalex_id="https://openalex.org/W1", title="Paper One")
        session.add_all([floor, paper])
        session.flush()
        session.add(
            CityPaperRecord(
                city_id=city.id,
                openalex_id=paper.openalex_id,
                external_paper_id="R_000001",
                building_id=building.id,
                floor_id=floor.id,
                expansion_source="legacy",
            )
        )
        session.commit()

    yield PostgresCityRepository(factory)
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.mark.parametrize("repository_fixture", ["json_repository", "postgres_repository"])
def test_repository_scene_contract(request, repository_fixture):
    repository = request.getfixturevalue(repository_fixture)

    scene = repository.get_scene("research")

    assert scene["buildings"][0]["building_id"] == "B_R_0001"
    expected_vertex_ids = ["R_000001"] if repository_fixture == "json_repository" else []
    assert scene["buildings"][0]["vertex_ids"] == expected_vertex_ids
    assert scene["buildings"][0]["floors"][0]["floor_id"] == "F_B_R_0001_01" if repository_fixture == "postgres_repository" else True


@pytest.mark.parametrize("repository_fixture", ["json_repository", "postgres_repository"])
def test_repository_returns_building_papers(request, repository_fixture):
    repository = request.getfixturevalue(repository_fixture)

    papers = repository.get_building_papers("research", "B_R_0001")

    assert papers[0]["paper_id"] == "R_000001"
    assert papers[0]["title"] == "Paper One"
