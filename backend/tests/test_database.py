from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings
from app.models import CityRecord


REQUIRED_TABLES = {
    "cities",
    "city_seeds",
    "papers",
    "paper_embeddings",
    "city_papers",
    "paper_references",
    "paper_edges",
    "districts",
    "buildings",
    "floors",
    "building_relationships",
    "community_runs",
    "city_snapshots",
    "build_jobs",
    "ingestion_cache",
    "assistant_conversations",
    "assistant_messages",
    "answer_citations",
}


def database_settings() -> Settings:
    return Settings(
        database_url=os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_backend="postgres",
        worker_poll_seconds=1.0,
        job_stale_seconds=300,
        embedding_model="tfidf-svd-64",
    )


@pytest.fixture()
def database_engine():
    engine = create_engine_from_settings(database_settings())
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - only used when local PostgreSQL is absent
        pytest.skip(f"PostgreSQL test database unavailable: {exc}")

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_schema_contains_required_platform_tables(database_engine):
    tables = set(inspect(database_engine).get_table_names())
    assert REQUIRED_TABLES <= tables

    with database_engine.connect() as connection:
        assert connection.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")).scalar_one() == "vector"


def test_city_target_accepts_100000(database_engine):
    with Session(database_engine) as session:
        city = CityRecord(
            external_id="scale-test",
            name="Scale test",
            kind="seeded",
            status="draft",
            target_paper_count=100_000,
            configuration={},
        )
        session.add(city)
        session.commit()
        session.refresh(city)

        assert city.target_paper_count == 100_000


def test_alembic_upgrade_creates_required_platform_tables(monkeypatch):
    database_url = os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    settings = database_settings()
    engine = create_engine_from_settings(settings)
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(config, "head")

    assert REQUIRED_TABLES <= set(inspect(engine).get_table_names())

    command.downgrade(config, "base")
    assert not (REQUIRED_TABLES & set(inspect(engine).get_table_names()))
    engine.dispose()
