from __future__ import annotations

import os
from threading import Event
from types import SimpleNamespace

from sqlalchemy import select

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.jobs import JobRepository
from app.models import BuildingRecord, CityRecord
from app.openalex_client import ResolvedSeed
from app.pipeline.build import build_city_job
from app.repositories.postgres_city import PostgresCityRepository
from app.worker import run_worker


def work(work_id: str, title: str):
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": None,
        "title": title,
        "abstract_inverted_index": {"graph": [0], "learning": [1]},
        "publication_year": 2025,
        "authorships": [],
        "primary_location": {"source": {"display_name": "Graph Journal"}},
        "topics": [{"display_name": "Graph Learning"}],
        "keywords": [],
        "referenced_works": [],
        "cited_by_count": 10,
        "open_access": {"is_oa": True},
    }


class FakeOpenAlexClient:
    def resolve_seed(self, raw_input):
        return ResolvedSeed(raw_input, "title", work("W0", "Graph Learning Seed"))

    def fetch_works_by_ids(self, ids):
        return iter(())

    def iter_citing_works(self, openalex_id, *, limit):
        return iter(())

    def iter_works(self, filters, *, limit, per_page=100):
        return (work(f"W{index}", f"Graph Learning Candidate {index}") for index in range(1, 15))


def test_worker_runs_real_restart_safe_pipeline_with_fake_openalex():
    database_url = os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    settings = Settings(
        database_url=database_url,
        storage_backend="postgres",
        worker_poll_seconds=0.01,
        job_stale_seconds=300,
        embedding_model="hashing-64-v1",
    )
    engine = create_engine_from_settings(settings)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    repository = PostgresCityRepository(factory)
    jobs = JobRepository(factory)
    city, _ = repository.create_city("Worker city", ["Graph Learning Seed"], 10)
    repository.set_city_status(city.id, "building")
    job = jobs.enqueue(city.id)

    def handler(claimed, worker_jobs):
        build_city_job(claimed, worker_jobs, repository, settings, client=FakeOpenAlexClient())

    try:
        run_worker(settings, once=True, handler=handler, worker_id="pipeline-test")

        completed = jobs.get(job.id)
        ready_city = repository.get_city_record(str(city.id))
        assert completed.status == "succeeded"
        assert completed.stage == "complete"
        assert "Built" in completed.message
        assert ready_city.status == "ready"
        assert ready_city.paper_count == 10
        assert ready_city.algorithm_version == 'graph-cities-v1'
        assert ready_city.configuration['graph_input'] == 'citation'
        with factory() as session:
            buildings = session.scalars(select(BuildingRecord).where(BuildingRecord.city_id == city.id)).all()
            # This fixture has no citations. Similarity links must not silently
            # become the graph used for original fixed-point decomposition.
            assert len(buildings) == 1
            assert buildings[0].node_count == 10
            assert buildings[0].quality_metrics['representation'] == 'isolates'
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_cancelling_a_queued_job_is_terminal_without_worker_claim():
    database_url = os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    settings = Settings(database_url, "postgres", 1.0, 300, "hashing-64-v1")
    engine = create_engine_from_settings(settings)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    repository = PostgresCityRepository(factory)
    jobs = JobRepository(factory)
    city, _ = repository.create_city("Cancelled", ["Paper"], 10)
    job = jobs.enqueue(city.id)
    try:
        cancelled = jobs.request_cancel(job.id)
        assert cancelled.status == "cancelled"
        assert jobs.claim_next("worker") is None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_build_overlaps_embedding_with_collection_batches(monkeypatch):
    database_url = os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    settings = Settings(database_url, "postgres", 1.0, 300, "hashing-64-v1")
    engine = create_engine_from_settings(settings)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    repository = PostgresCityRepository(factory)
    jobs = JobRepository(factory)
    city, _ = repository.create_city("Overlapped build", ["Paper"], 10)
    repository.set_city_status(city.id, "building")
    queued = jobs.enqueue(city.id)
    claimed = jobs.claim_next("overlap-test")
    assert claimed is not None and claimed.id == queued.id
    embedding_started = Event()

    monkeypatch.setattr("app.pipeline.build.run_seed_stage", lambda *args, **kwargs: SimpleNamespace(resolved_count=1))

    def fake_expand(*args, on_batch_committed, **kwargs):
        on_batch_committed(city.id, ["W1"])
        assert embedding_started.wait(1.0)
        return SimpleNamespace(total_paper_count=10, exhausted=False)

    def fake_embed(*args, **kwargs):
        embedding_started.set()
        return 1

    monkeypatch.setattr("app.pipeline.build.expand_city", fake_expand)
    monkeypatch.setattr("app.pipeline.build.embed_city_papers", fake_embed)
    monkeypatch.setattr("app.pipeline.build.build_sparse_edges", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        "app.pipeline.build.build_original_city",
        lambda *args, **kwargs: {"buildings": 1, "bridges": 0, "streets": 0},
    )
    try:
        build_city_job(claimed, jobs, repository, settings, client=FakeOpenAlexClient())
        assert embedding_started.is_set()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
