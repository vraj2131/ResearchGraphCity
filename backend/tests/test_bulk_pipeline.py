from __future__ import annotations

import os

from sqlalchemy import text

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.models import CityPaperRecord, PaperEmbeddingRecord, PaperRecord
from app.pipeline.bulk_io import copy_rows, upsert_paper_rows
from app.pipeline.embeddings import embed_city_papers, hash_documents
from app.repositories.postgres_city import PostgresCityRepository


def test_copy_rows_streams_typed_arrays_into_postgres():
    settings = Settings(
        database_url=os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_backend="postgres",
        worker_poll_seconds=1.0,
        job_stale_seconds=300,
        embedding_model="hashing-64-v1",
    )
    engine = create_engine_from_settings(settings)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TEMP TABLE copy_probe (paper_id text, values real[]) ON COMMIT DROP"))
            copied = copy_rows(
                connection,
                "copy_probe",
                ("paper_id", "values"),
                [("W1", [1.0, 2.0]), ("W2", [3.0, 4.0])],
            )
            rows = connection.execute(text("SELECT paper_id, values FROM copy_probe ORDER BY paper_id")).all()

        assert copied == 2
        assert rows == [("W1", [1.0, 2.0]), ("W2", [3.0, 4.0])]
    finally:
        engine.dispose()


def test_upsert_paper_rows_bulk_updates_existing_metadata():
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
    row = {
        "openalex_id": "W1",
        "doi": None,
        "title": "Initial title",
        "abstract": "Evidence",
        "publication_year": 2024,
        "venue": "Journal",
        "publisher": "Publisher",
        "citation_count": 4,
        "open_access": True,
        "code_available": False,
        "data_available": False,
        "authors": ["Researcher"],
        "author_ids": ["A1"],
        "institutions": ["University"],
        "institution_ids": ["I1"],
        "topics": ["Graphs"],
        "keywords": ["network"],
        "methods": [],
        "datasets": [],
        "metadata": {"source": "test"},
    }
    try:
        with engine.begin() as connection:
            assert upsert_paper_rows(connection, [row]) == 1
        with engine.begin() as connection:
            assert upsert_paper_rows(connection, [{**row, "title": "Updated title"}]) == 1
        with engine.connect() as connection:
            stored = connection.execute(text("SELECT title, topics FROM papers WHERE openalex_id = 'W1'")).one()
        assert stored == ("Updated title", ["Graphs"])
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_upsert_paper_rows_materializes_database_defaults_for_sparse_rows():
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
    try:
        with engine.begin() as connection:
            upsert_paper_rows(connection, [{"openalex_id": "W-minimal", "title": "Minimal"}])
        with engine.connect() as connection:
            stored = connection.execute(
                text(
                    "SELECT abstract, venue, publisher, citation_count, open_access, topics, metadata "
                    "FROM papers WHERE openalex_id = 'W-minimal'"
                )
            ).one()
        assert stored == ("", "", "", 0, False, [], {})
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_bulk_embedding_is_idempotent_and_preserves_hash_vectors():
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
    city, _ = repository.create_city("Bulk embeddings", ["seed"], 10)
    try:
        with factory.begin() as session:
            papers = [PaperRecord(openalex_id=f"W{index}", title=f"Graph paper {index}") for index in range(10)]
            session.add_all(papers)
            session.flush()
            session.add_all(
                CityPaperRecord(city_id=city.id, openalex_id=paper.openalex_id, external_paper_id=f"P_{index:06d}")
                for index, paper in enumerate(papers)
            )

        assert embed_city_papers(city.id, repository, batch_size=10) == 10
        assert embed_city_papers(city.id, repository, batch_size=10) == 0
        with factory() as session:
            stored = session.get(PaperEmbeddingRecord, ("W0", "hashing-64-v1"))
        assert stored is not None
        assert __import__("numpy").allclose(stored.embedding, hash_documents(["Graph paper 0"])[0])
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
