from __future__ import annotations

from collections import Counter
import os

import numpy as np
from sqlalchemy import select

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.models import CityPaperRecord, PaperEdgeRecord, PaperRecord, PaperReferenceRecord
from app.pipeline.edges import bounded_topic_pairs, build_sparse_edges
from app.pipeline.embeddings import hash_documents
from app.repositories.postgres_city import PostgresCityRepository


def test_hash_embeddings_are_deterministic_normalized_and_fixed_size():
    documents = ["graph neural networks for molecules", "economic mobility and education"]

    first = hash_documents(documents)
    second = hash_documents(documents)

    assert first.shape == (2, 64)
    assert np.allclose(first, second)
    assert np.allclose(np.linalg.norm(first, axis=1), [1.0, 1.0])


def test_topic_candidates_are_frequency_capped_and_linear():
    papers = [
        {"id": f"W{index:05d}", "topics": ["Graph Learning", f"Specific {index % 20}"]}
        for index in range(1_000)
    ]

    pairs = bounded_topic_pairs(papers, top_k=10, bucket_cap=200)

    assert len(pairs) <= len(papers) * 10
    assert all(source < target for source, target in pairs)
    assert len(set(pairs)) == len(pairs)


def test_topic_candidates_do_not_compare_unrelated_topic_buckets():
    papers = [
        {"id": "W1", "topics": ["Graph Learning"]},
        {"id": "W2", "topics": ["Graph Learning"]},
        {"id": "W3", "topics": ["Public Health"]},
    ]

    assert bounded_topic_pairs(papers, top_k=10) == [("W1", "W2")]


def test_sparse_builder_caps_similarity_degree_but_retains_citations():
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
    city, _ = repository.create_city("Sparse edges", ["seed"], 50)
    try:
        with factory.begin() as session:
            for index in range(50):
                paper_id = f"W{index:03d}"
                paper = PaperRecord(openalex_id=paper_id, title=f"Paper {index}", topics=["Graph Learning"])
                session.add(paper)
                session.flush([paper])
                session.add(
                    CityPaperRecord(
                        city_id=city.id,
                        openalex_id=paper_id,
                        external_paper_id=f"P_{index:06d}",
                        is_seed=index == 0,
                    )
                )
            session.add(PaperReferenceRecord(source_openalex_id="W000", target_openalex_id="W049"))

        counts = build_sparse_edges(
            city.id,
            repository,
            semantic_k=0,
            topic_k=15,
            attribute_k=0,
            max_similarity_degree=8,
        )

        with factory() as session:
            edges = session.scalars(select(PaperEdgeRecord).where(PaperEdgeRecord.city_id == city.id)).all()
        degree = Counter()
        for edge in edges:
            if edge.edge_type == "similarity":
                degree[edge.source_openalex_id] += 1
                degree[edge.target_openalex_id] += 1
        assert max(degree.values(), default=0) <= 8
        assert counts["citation"] == 1
        assert any(edge.edge_type == "citation" and {edge.source_openalex_id, edge.target_openalex_id} == {"W000", "W049"} for edge in edges)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
