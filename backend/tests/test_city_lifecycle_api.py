from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.jobs import JobRepository
from app.main import create_app
from app.repositories.postgres_city import PostgresCityRepository


@pytest.fixture()
def lifecycle_context():
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
    city_repository = PostgresCityRepository(factory)
    job_repository = JobRepository(factory)
    client = TestClient(
        create_app(
            repository=city_repository,
            job_repository=job_repository,
            settings=settings,
        )
    )
    yield client, city_repository, job_repository
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_create_accepts_thirty_seeds_and_100000(lifecycle_context):
    client, _, _ = lifecycle_context

    response = client.post(
        "/api/cities",
        json={
            "name": "Large city",
            "seed_inputs": [f"paper {index}" for index in range(30)],
            "target_paper_count": 100_000,
        },
    )

    assert response.status_code == 201
    assert response.json()["target_paper_count"] == 100_000
    assert response.json()["seed_count"] == 30
    assert response.json()["status"] == "draft"
    assert response.json()["provenance"]["algorithm_version"] == "platform-v1"
    assert response.json()["provenance"]["embedding_model"] == "hashing-64-v1"


def test_create_rejects_more_than_thirty_seeds(lifecycle_context):
    client, _, _ = lifecycle_context

    response = client.post(
        "/api/cities",
        json={
            "name": "Too many seeds",
            "seed_inputs": [f"paper {index}" for index in range(31)],
            "target_paper_count": 100_000,
        },
    )

    assert response.status_code == 422


def test_create_reports_duplicate_seed_warning(lifecycle_context):
    client, _, _ = lifecycle_context

    response = client.post(
        "/api/cities",
        json={
            "name": "Duplicates",
            "seed_inputs": ["Paper One", " paper one ", "Paper Two"],
            "target_paper_count": 1_000,
        },
    )

    assert response.status_code == 201
    assert response.json()["seed_count"] == 2
    assert response.json()["warnings"] == ["Removed 1 duplicate seed input."]


def test_build_is_queued_and_can_be_cancelled(lifecycle_context, monkeypatch):
    client, _, job_repository = lifecycle_context
    monkeypatch.setattr("app.main.build_city_from_seed_inputs", lambda *args, **kwargs: pytest.fail("build ran in API request"))
    created = client.post(
        "/api/cities",
        json={"name": "Queued city", "seed_inputs": ["Paper One"], "target_paper_count": 100_000},
    ).json()

    queued = client.post(f"/api/cities/{created['city_id']}/build")

    assert queued.status_code == 202
    job_id = queued.json()["job_id"]
    assert job_repository.get(job_id).status == "queued"
    assert client.get(f"/api/jobs/{job_id}").json()["stage"] == "resolve"
    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.status_code == 202
    assert cancelled.json()["cancel_requested"] is True


def test_new_city_external_id_can_be_used_by_scene_endpoints(lifecycle_context):
    client, _, _ = lifecycle_context
    created = client.post(
        "/api/cities",
        json={"name": "Dynamic city", "seed_inputs": ["Paper One"], "target_paper_count": 1_000},
    ).json()

    response = client.get(f"/api/cities/{created['city_type']}/buildings")

    assert response.status_code == 200
    assert response.json() == []
