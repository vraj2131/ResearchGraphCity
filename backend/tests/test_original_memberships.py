from __future__ import annotations

import itertools
import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy import text

from app.config import Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.repositories.postgres_city import PostgresCityRepository


def test_migration_backfills_legacy_primary_memberships_without_changing_city(original_repository, monkeypatch):
    from alembic import command
    from alembic.config import Config

    repository = original_repository
    monkeypatch.setenv('DATABASE_URL', os.environ['TEST_DATABASE_URL'])
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.stamp(config, 'head')
    command.downgrade(config, '20260919_0008')
    with repository.session_factory.begin() as session:
        session.execute(text("UPDATE cities SET algorithm_version = 'leiden-city-v2'"))
        before = session.execute(text('SELECT city_id, building_id, openalex_id, floor_id FROM city_papers ORDER BY openalex_id')).all()
        city_before = session.execute(text('SELECT id, external_id, status, paper_count, algorithm_version FROM cities')).all()
    command.upgrade(config, 'head')
    with repository.session_factory() as session:
        assert session.execute(text('SELECT city_id, building_id, openalex_id, floor_id FROM building_papers ORDER BY openalex_id')).all() == before
        assert session.execute(text('SELECT city_id, building_id, openalex_id, floor_id FROM floor_papers ORDER BY openalex_id')).all() == before
        assert session.execute(text('SELECT city_id, building_id, openalex_id, floor_id FROM city_papers ORDER BY openalex_id')).all() == before
        assert session.execute(text('SELECT id, external_id, status, paper_count, algorithm_version FROM cities')).all() == city_before
        assert session.execute(text('SELECT COUNT(*) FROM decomposition_edges')).scalar_one() == 0
    assert len(repository.get_building_papers('original', 'high')) == 4
    assert len(repository.get_building_papers('original', 'low')) == 1


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
    timeline = original_repository.get_timeline('original')
    assert sum(year['paper_count'] for year in timeline['years']) == 5
    year = next(y for y in timeline['years'] if y['year'] == 2021)
    assert year['paper_count'] == 1
    assert year['building_count'] == 2


def test_assistant_retains_secondary_locations_but_excludes_geometric_streets(original_repository):
    from sqlalchemy import select
    from app.assistant import build_evidence_packet, build_evidence_report
    from app.models import BuildingRecord, BuildingRelationshipRecord

    repository = original_repository
    city = repository.get_city_record('original')
    with repository.session_factory.begin() as session:
        buildings = session.scalars(select(BuildingRecord).order_by(BuildingRecord.external_id)).all()
        for external_id, kind, score in [('GS_1', 'graph_city_geometry', 0), ('BR_1', 'evidence_bridge', 0.7)]:
            session.add(BuildingRelationshipRecord(city_id=city.id, external_id=external_id,
                        source_building_id=buildings[0].id, target_building_id=buildings[1].id,
                        relationship_kind='street' if score == 0 else 'bridge', relationship_type=kind,
                        score=score, distance=1, components={}, evidence=[]))
    packet = build_evidence_packet(repository, 'original', 'graph', {'year_min': 2021}, limit=1)
    assert len(packet['papers']) == 1
    assert {b['building_id'] for b in packet['buildings']} == {'high', 'low'}
    assert [r['relationship_id'] for r in packet['relationships']] == ['BR_1']
    assert 'GS_1' not in build_evidence_report(packet)
    assert 'BR_1' in build_evidence_report(packet)


def test_scene_bounds_wave_geometry_and_floor_endpoint_pages_all_waves(original_repository):
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.main import create_app
    from app.models import BuildingRecord, FloorRecord

    repository = original_repository
    with repository.session_factory.begin() as session:
        building = session.scalar(select(BuildingRecord).where(BuildingRecord.external_id == 'high'))
        building.quality_metrics = {'algorithm': 'graph-cities-v1', 'floor_count': 151}
        for index in range(2, 152):
            session.add(FloorRecord(city_id=building.city_id, building_id=building.id,
                        external_id=f'high-wave-{index}', floor_index=index, core_min=3, core_max=3, node_count=1))
    scene = repository.get_scene('original')
    high = next(b for b in scene['buildings'] if b['building_id'] == 'high')
    assert len(high['floors']) <= 64
    assert high['floors'][0]['floor_index'] == 1
    assert high['floors'][-1]['floor_index'] == 151
    assert high['floor_count'] == 151
    assert high['floors_truncated'] is True
    client = TestClient(create_app(repository=repository))
    url = '/api/cities/original/building/high/floors'
    first = client.get(url, params={'limit': 100})
    assert first.status_code == 200
    assert [f['floor_index'] for f in first.json()] == list(range(1, 101))
    second = client.get(url, params={'limit': 100, 'cursor': 100})
    assert [f['floor_index'] for f in second.json()] == list(range(101, 152))


def test_edge_cursor_preserves_distinct_types_for_same_endpoints(original_repository):
    from sqlalchemy import select
    from app.models import CityRecord, PaperEdgeRecord
    repository = original_repository
    with repository.session_factory.begin() as session:
        city = session.scalar(select(CityRecord).where(CityRecord.external_id == 'original'))
        city.configuration = {'graph_input': 'citation-plus-similarity'}
        session.add(PaperEdgeRecord(city_id=city.id, source_openalex_id='W0', target_openalex_id='W1',
                                    edge_type='similarity', weight=0.8, directed=False))
    first = repository.get_building_edges('original', 'high', limit=1)
    assert first[0]['edge_type'] == 'citation'
    following = repository.get_building_edges('original', 'high', limit=1, cursor='P0:P1:citation')
    assert (following[0]['source'], following[0]['target'], following[0]['edge_type']) == ('P0', 'P1', 'similarity')
    legacy = repository.get_building_edges('original', 'high', limit=1, cursor='P0:P1')
    assert (legacy[0]['source'], legacy[0]['target']) != ('P0', 'P1')
