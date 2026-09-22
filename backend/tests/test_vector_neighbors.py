from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import delete, func, select

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.models import CityPaperRecord, PaperEdgeRecord, PaperEmbeddingRecord, PaperNeighborRecord, PaperRecord
from app.pipeline.vector_neighbors import (
    NeighborBuildCancelled,
    build_hnsw_neighbors,
    canonical_pairs,
    compute_city_neighbors,
)
from app.repositories.postgres_city import PostgresCityRepository


def test_hnsw_neighbors_return_requested_count_without_self_edges():
    ids = [f"W{index}" for index in range(6)]
    vectors = np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.98, 0.20, 0.0],
            [0.80, 0.60, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.8, 0.6],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )

    rows = build_hnsw_neighbors(ids, vectors, top_k=2, workers=2)

    by_source = {source: [] for source in ids}
    for row in rows:
        by_source[row.source_openalex_id].append(row)
        assert row.source_openalex_id != row.target_openalex_id
        assert 0.0 <= row.similarity <= 1.0
    assert all(len(neighbors) == 2 for neighbors in by_source.values())
    assert [row.rank for row in by_source["W0"]] == [1, 2]
    assert by_source["W0"][0].target_openalex_id == "W1"


def test_canonical_pairs_deduplicate_reciprocal_neighbors_at_max_similarity():
    ids = ["W0", "W1", "W2"]
    vectors = np.asarray([[1.0, 0.0], [0.99, 0.1], [0.0, 1.0]], dtype=np.float32)

    pairs = canonical_pairs(build_hnsw_neighbors(ids, vectors, top_k=1, workers=1))

    assert list(pairs).count(("W0", "W1")) == 1
    assert pairs[("W0", "W1")] > 0.9


def test_hnsw_neighbors_honor_cancellation_before_index_build():
    with pytest.raises(NeighborBuildCancelled):
        build_hnsw_neighbors(
            ["W0", "W1"],
            np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            top_k=1,
            workers=1,
            cancel_check=lambda: True,
        )


def test_compute_city_neighbors_reuses_scope_cache():
    settings = Settings(
        database_url=__import__("os").getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL),
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
    city, _ = repository.create_city("Neighbor cache", ["seed"], 10)
    try:
        with factory.begin() as session:
            for index in range(6):
                paper_id = f"W{index}"
                vector = np.zeros(64, dtype=np.float32)
                vector[index] = 1.0
                vector[(index + 1) % 6] = 0.5
                session.add(PaperRecord(openalex_id=paper_id, title=f"Paper {index}"))
            session.flush()
            for index in range(6):
                paper_id = f"W{index}"
                vector = np.zeros(64, dtype=np.float32)
                vector[index] = 1.0
                vector[(index + 1) % 6] = 0.5
                session.add(
                    CityPaperRecord(city_id=city.id, openalex_id=paper_id, external_paper_id=f"P_{index:06d}")
                )
                session.add(
                    PaperEmbeddingRecord(
                        openalex_id=paper_id,
                        model="hashing-64-v1",
                        dimensions=64,
                        embedding=vector.tolist(),
                    )
                )

        first = compute_city_neighbors(city.id, repository, "hashing-64-v1", top_k=2, workers=2)
        with factory.begin() as session:
            session.execute(
                delete(PaperEdgeRecord).where(
                    PaperEdgeRecord.city_id == city.id,
                    PaperEdgeRecord.edge_type == "similarity",
                )
            )
        second = compute_city_neighbors(city.id, repository, "hashing-64-v1", top_k=2, workers=2)

        assert first.computed_sources == 6
        assert first.cache_hit_sources == 0
        assert second.computed_sources == 0
        assert second.cache_hit_sources == 6
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(PaperNeighborRecord)) == 6
            assert session.scalar(
                select(func.count()).select_from(PaperEdgeRecord).where(PaperEdgeRecord.city_id == city.id)
            ) > 0
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
