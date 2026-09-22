from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.main import create_app
from app.models import BuildingRecord, CityPaperRecord, DistrictRecord, FloorRecord, PaperRecord
from app.repositories.postgres_city import PostgresCityRepository


def test_scene_is_aggregate_only_and_detail_page_is_hard_capped():
    settings = Settings(
        database_url=os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_backend="postgres",
        worker_poll_seconds=1.0,
        job_stale_seconds=300,
        embedding_model="hashing-64-v1",
    )
    engine = create_engine_from_settings(settings)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    repository = PostgresCityRepository(factory)
    city, _ = repository.create_city("Scale API", ["seed"], 1_000)
    try:
        with factory.begin() as session:
            district = DistrictRecord(city_id=city.id, external_id="D_0001", name="Graph AI")
            session.add(district)
            session.flush([district])
            building = BuildingRecord(
                city_id=city.id,
                district_id=district.id,
                external_id="B_0001",
                node_count=500,
                edge_count=1_000,
                internal_density=0.01,
                avg_core=4,
                max_core=8,
                height=42,
                footprint=30,
                x=0,
                z=0,
                top_labels=["Graph Learning"],
            )
            session.add(building)
            session.flush([building])
            floor = FloorRecord(
                city_id=city.id,
                building_id=building.id,
                external_id="F_0001_01",
                floor_index=1,
                core_min=1,
                core_max=8,
                node_count=500,
            )
            session.add(floor)
            session.flush([floor])
            for index in range(500):
                paper = PaperRecord(openalex_id=f"W{index:05d}", title=f"Paper {index}")
                session.add(paper)
                session.flush([paper])
                session.add(
                    CityPaperRecord(
                        city_id=city.id,
                        openalex_id=paper.openalex_id,
                        external_paper_id=f"P_{index:06d}",
                        building_id=building.id,
                        floor_id=floor.id,
                    )
                )
        client = TestClient(create_app(repository=repository, settings=settings))

        scene = client.get(f"/api/cities/{city.external_id}/scene")
        papers = client.get(f"/api/cities/{city.external_id}/building/B_0001/papers?limit=999")

        assert scene.status_code == 200
        payload = scene.json()
        assert payload["buildings"][0]["node_count"] == 500
        assert payload["buildings"][0]["vertex_ids"] == []
        assert payload["buildings"][0]["floors"][0]["vertex_ids"] == []
        assert len(scene.content) < 25_000
        assert papers.status_code == 200
        assert len(papers.json()) == 200
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
