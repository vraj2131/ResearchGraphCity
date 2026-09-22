from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.main import create_app
from app.models import CityPaperRecord, CitySeedRecord, PaperEdgeRecord, PaperRecord
from app.openalex_client import ResolvedSeed
from app.pipeline.seed_stage import run_seed_stage
from app.repositories.postgres_city import PostgresCityRepository


def raw_work(work_id: str, title: str, references=None):
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": None,
        "title": title,
        "abstract_inverted_index": {"graph": [0], "research": [1]},
        "publication_year": 2024,
        "authorships": [],
        "primary_location": {"source": {"display_name": "Test Journal"}},
        "topics": [{"display_name": "Graph Learning"}],
        "keywords": [],
        "referenced_works": references or [],
        "cited_by_count": 10,
        "open_access": {"is_oa": True},
    }


class FakeOpenAlexClient:
    def resolve_seed(self, raw_input: str):
        if raw_input == "missing":
            return ResolvedSeed(raw_input=raw_input, match_type="title", work=None)
        if raw_input == "Paper One":
            return ResolvedSeed(raw_input=raw_input, match_type="title", work=raw_work("W1", raw_input, ["https://openalex.org/W2"]))
        return ResolvedSeed(raw_input=raw_input, match_type="doi", work=raw_work("W2", "Paper Two"))


@pytest.fixture()
def seed_context():
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
    city, _ = repository.create_city("Seed preview", ["Paper One", "10.1000/two", "missing"], 1_000)
    yield settings, factory, repository, city
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_seed_stage_persists_provenance_graph_and_warning_idempotently(seed_context):
    _, factory, repository, city = seed_context

    first = run_seed_stage(city.id, repository, FakeOpenAlexClient())
    second = run_seed_stage(city.id, repository, FakeOpenAlexClient())

    assert first.resolved_count == second.resolved_count == 2
    assert first.unresolved_count == second.unresolved_count == 1
    assert first.warnings == ["No OpenAlex match for 'missing'."]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(PaperRecord)) == 2
        assert session.scalar(select(func.count()).select_from(CityPaperRecord)) == 2
        assert session.scalar(select(func.count()).select_from(PaperEdgeRecord)) >= 1
        seeds = session.scalars(select(CitySeedRecord).order_by(CitySeedRecord.position)).all()
        assert [seed.resolution_status for seed in seeds] == ["resolved", "resolved", "unresolved"]
        assert [seed.match_type for seed in seeds] == ["title", "doi", "title"]


def test_seed_graph_endpoint_returns_titles_and_evidence_edges(seed_context):
    settings, _, repository, city = seed_context
    run_seed_stage(city.id, repository, FakeOpenAlexClient())
    client = TestClient(create_app(repository=repository, settings=settings))

    response = client.get(f"/api/cities/{city.external_id}/seed-graph")

    assert response.status_code == 200
    payload = response.json()
    assert {node["title"] for node in payload["nodes"]} == {"Paper One", "Paper Two"}
    assert payload["unresolved"] == ["missing"]
    assert payload["edges"]
    assert payload["edges"][0]["evidence"]
