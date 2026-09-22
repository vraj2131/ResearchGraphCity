from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

import pytest
from sqlalchemy.orm import Session

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.jobs import JobRepository
from app.models import BuildJobRecord, CityRecord
from app.worker import run_worker


@pytest.fixture()
def job_context():
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
            external_id="job-city",
            name="Job city",
            kind="seeded",
            status="draft",
            target_paper_count=100_000,
            configuration={},
        )
        session.add(city)
        session.commit()
        city_id = city.id
    yield JobRepository(factory), factory, city_id
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_two_workers_cannot_claim_same_job(job_context):
    repository, _, city_id = job_context
    queued = repository.enqueue(city_id)

    first = repository.claim_next("worker-a")
    second = repository.claim_next("worker-b")

    assert first is not None
    assert first.id == queued.id
    assert first.status == "running"
    assert first.locked_by == "worker-a"
    assert second is None


def test_cancel_is_cooperative(job_context):
    repository, _, city_id = job_context
    job = repository.enqueue(city_id)

    repository.request_cancel(job.id)

    assert repository.should_cancel(job.id) is True


def test_progress_is_monotonic_within_stage(job_context):
    repository, _, city_id = job_context
    job = repository.enqueue(city_id)
    repository.claim_next("worker-a")

    repository.update_progress(job.id, stage="collect", current=50, total=100, message="Collected 50")
    repository.update_progress(job.id, stage="collect", current=40, total=100, message="Older update")

    stored = repository.get(job.id)
    assert stored.progress_current == 50
    assert stored.message == "Collected 50"


def test_stale_running_job_is_requeued(job_context):
    repository, factory, city_id = job_context
    job = repository.enqueue(city_id)
    repository.claim_next("dead-worker")
    with factory.begin() as session:
        stored = session.get(BuildJobRecord, job.id)
        stored.heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=10)

    assert repository.requeue_stale(stale_after_seconds=300) == 1
    assert repository.get(job.id).status == "queued"


def test_failure_sanitizes_secret_like_fields(job_context):
    repository, _, city_id = job_context
    job = repository.enqueue(city_id)
    repository.claim_next("worker-a")

    repository.fail(job.id, RuntimeError("request failed api_key=secret-value"))

    stored = repository.get(job.id)
    assert stored.status == "failed"
    assert "secret-value" not in stored.error["message"]


def test_worker_smoke_completes_a_queued_fake_source_build(job_context):
    repository, _, city_id = job_context
    job = repository.enqueue(city_id)
    settings = Settings(
        database_url=os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_backend="postgres",
        worker_poll_seconds=1.0,
        job_stale_seconds=300,
        embedding_model="tfidf-svd-64",
    )

    def fake_source_handler(claimed, jobs):
        jobs.update_progress(claimed.id, stage="persist", current=10, total=10, message="Stored 10 fake papers")

    run_worker(settings, once=True, handler=fake_source_handler, worker_id="smoke-worker")

    completed = repository.get(job.id)
    assert completed.status == "succeeded"
    assert completed.progress_current == 10
    assert completed.stage == "complete"
    assert completed.message == "Stored 10 fake papers"
