from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.import_legacy import import_legacy_city
from app.repositories.postgres_city import PostgresCityRepository
from app.storage import write_json


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
    repository = PostgresCityRepository(create_session_factory(engine))
    yield repository
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def processed_fixture(tmp_path: Path) -> Path:
    write_json(
        tmp_path / "research_vertices.json",
        [
            {
                "paper_id": "R_000001",
                "openalex_id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1/example",
                "title": "Paper One",
                "abstract": "Graph visualization paper.",
                "topics": ["Graph Visualization"],
                "keywords": ["Graph"],
                "embedding": [0.1, 0.2],
            }
        ],
    )
    write_json(
        tmp_path / "research_edges.json",
        [
            {
                "source": "R_000001",
                "target": "R_000001",
                "edge_type": "citation",
                "edge_weight": 1.0,
                "components": {"citation": 1.0},
                "evidence": ["citation"],
                "directed_citation": True,
            }
        ],
    )
    write_json(
        tmp_path / "research_buildings.json",
        [
            {
                "building_id": "B_R_0001",
                "city_type": "research",
                "vertex_ids": ["R_000001"],
                "node_count": 1,
                "edge_count": 1,
                "internal_density": 0.0,
                "avg_core": 0.0,
                "max_core": 0,
                "height": 10.0,
                "footprint": 8.0,
                "x": 1.0,
                "z": 2.0,
                "top_labels": ["Graph Visualization"],
                "semantic_domain": "graph_ai",
                "semantic_domain_name": "Graph, AI, and Computation",
                "semantic_color": "#6ee7f9",
                "profile": {},
                "original_labels": {"topics": ["Graph Visualization"]},
                "activation": {"score": 0.2},
                "activation_score": 0.2,
                "floors": [
                    {
                        "floor_id": "F_B_R_0001_01",
                        "floor_index": 1,
                        "core_range": [0, 0],
                        "vertex_ids": ["R_000001"],
                        "node_count": 1,
                        "top_labels": ["Graph Visualization"],
                        "activation_score": 0.2,
                    }
                ],
                "community_id": "C_R_0001",
            }
        ],
    )
    write_json(tmp_path / "research_floors.json", [])
    write_json(tmp_path / "research_bridges.json", [])
    write_json(tmp_path / "research_streets.json", [])
    write_json(
        tmp_path / "research_communities.json",
        [
            {
                "community_id": "C_R_0001",
                "name": "Graph Research",
                "building_ids": ["B_R_0001"],
                "top_labels": ["Graph Visualization"],
                "semantic_domain": "graph_ai",
                "semantic_domain_name": "Graph, AI, and Computation",
                "metrics": {"cluster_stability": 1.0},
                "color": "#6ee7f9",
            }
        ],
    )
    return tmp_path


def test_import_is_idempotent(postgres_repository, processed_fixture):
    first = import_legacy_city(processed_fixture, "research", postgres_repository)
    second = import_legacy_city(processed_fixture, "research", postgres_repository)

    assert first == second
    assert first.paper_count == 1
    assert first.edge_count == 1
    assert first.building_count == 1
    assert postgres_repository.list_cities()[0]["city_type"] == "research"


def test_import_preserves_external_ids_and_scene_contract(postgres_repository, processed_fixture):
    import_legacy_city(processed_fixture, "research", postgres_repository)

    scene = postgres_repository.get_scene("research")
    papers = postgres_repository.get_building_papers("research", "B_R_0001")
    edges = postgres_repository.get_building_edges("research", "B_R_0001")

    # Aggregate scene payloads stay bounded; paper membership is fetched on demand.
    assert scene["buildings"][0]["vertex_ids"] == []
    assert scene["buildings"][0]["community_id"] == "C_R_0001"
    assert scene["communities"][0]["semantic_domain_name"] == "Graph, AI, and Computation"
    assert papers[0]["paper_id"] == "R_000001"
    assert papers[0]["openalex_id"] == "https://openalex.org/W1"
    assert edges[0]["source"] == "R_000001"
