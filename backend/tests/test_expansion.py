from __future__ import annotations

import os
from threading import Event, Lock

from sqlalchemy import func, select

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.models import CityPaperRecord
from app.openalex_client import ResolvedSeed
from app.pipeline.expansion import (
    ExpansionCandidate,
    balanced_candidates,
    candidate_relevance,
    expand_city,
    parallel_round_robin,
    stream_balanced_candidates,
)
from app.pipeline.seed_stage import run_seed_stage
from app.repositories.postgres_city import PostgresCityRepository


def candidate(work_id: str, seed: str, domain: str, score: float) -> ExpansionCandidate:
    return ExpansionCandidate(
        work={"id": f"https://openalex.org/{work_id}", "title": work_id},
        seed_openalex_id=seed,
        source="semantic_search",
        domain=domain,
        components={"semantic_to_seed": score, "citation_proximity": 0.0, "topic_overlap": 0.0, "source_quality": 0.0, "recency": 0.0},
        relevance=score * 0.4,
        depth=1,
    )


def test_candidate_relevance_uses_versioned_formula():
    components = {
        "semantic_to_seed": 0.8,
        "citation_proximity": 1.0,
        "topic_overlap": 0.5,
        "source_quality": 0.4,
        "recency": 0.6,
    }

    assert candidate_relevance(components) == 0.74


def test_balancing_uses_seed_and_domain_soft_quotas_before_redistribution():
    candidates = [candidate(f"A{i}", "seed-a", "graph", 0.9 - i * 0.01) for i in range(8)]
    candidates += [candidate(f"B{i}", "seed-b", "health", 0.7 - i * 0.01) for i in range(4)]

    selected = balanced_candidates(candidates, target=8, seed_count=2, seed_quota_factor=1.0, domain_quota_fraction=0.5)

    assert len(selected) == 8
    assert len([item for item in selected[:6] if item.seed_openalex_id == "seed-a"]) <= 4
    assert len([item for item in selected[:6] if item.domain == "graph"]) <= 4


def test_balancing_deduplicates_and_rejects_candidates_without_evidence():
    duplicate = candidate("W1", "seed-a", "graph", 0.8)
    no_evidence = candidate("W2", "seed-b", "health", 0.0)

    selected = balanced_candidates([duplicate, duplicate, no_evidence], target=10, seed_count=2)

    assert [item.work["id"] for item in selected] == ["https://openalex.org/W1"]


def test_balancing_redistributes_unused_quota_to_reach_target():
    candidates = [candidate(f"W{i}", "only-seed", "only-domain", 0.9 - i * 0.01) for i in range(10)]

    selected = balanced_candidates(candidates, target=7, seed_count=3, seed_quota_factor=0.5, domain_quota_fraction=0.2)

    assert len(selected) == 7


def test_streaming_selector_stops_consuming_when_target_is_met():
    consumed = []

    def source():
        for index in range(1000):
            consumed.append(index)
            yield candidate(f"W{index}", f"seed-{index % 2}", f"domain-{index % 3}", 0.8)

    selected = list(stream_balanced_candidates(source(), target=10, seed_count=2))

    assert len(selected) == 10
    assert len(consumed) == 10


def test_parallel_round_robin_fetches_streams_concurrently_but_yields_deterministically():
    gate = Event()
    lock = Lock()
    started = 0

    def source(label):
        nonlocal started
        with lock:
            started += 1
            if started == 2:
                gate.set()
        assert gate.wait(1.0)
        yield f"{label}-1"
        yield f"{label}-2"

    values = list(parallel_round_robin([source("a"), source("b")], max_workers=2))

    assert values == ["a-1", "b-1", "a-2", "b-2"]


def test_expand_city_persists_batches_and_is_restart_safe():
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
    city, _ = repository.create_city("Expansion", ["Graph Seed"], 10)

    class Client:
        def resolve_seed(self, raw_input):
            return ResolvedSeed(raw_input, "title", raw_work("W0", "Graph Seed"))

        def fetch_works_by_ids(self, ids):
            return iter(())

        def iter_citing_works(self, openalex_id, *, limit):
            return iter(())

        def iter_works(self, filters, *, limit, per_page=100):
            return (raw_work(f"W{index}", f"Graph Candidate {index}") for index in range(1, 20))

    try:
        run_seed_stage(city.id, repository, Client())
        committed_batches = []
        first = expand_city(
            city.id,
            repository,
            Client(),
            batch_size=3,
            on_batch_committed=lambda _city_id, paper_ids: committed_batches.append(paper_ids),
        )
        second = expand_city(city.id, repository, Client(), batch_size=3)

        assert first.total_paper_count == 10
        assert first.accepted_count == 9
        assert [len(batch) for batch in committed_batches] == [3, 3, 3]
        assert second.accepted_count == 0
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(CityPaperRecord)) == 10
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def raw_work(work_id: str, title: str):
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": None,
        "title": title,
        "abstract_inverted_index": {"graph": [0], "candidate": [1]},
        "publication_year": 2025,
        "authorships": [],
        "primary_location": {"source": {"display_name": "Graph Journal"}},
        "topics": [{"display_name": "Graph Learning"}],
        "keywords": [],
        "referenced_works": [],
        "cited_by_count": 5,
        "open_access": {"is_oa": True},
    }
