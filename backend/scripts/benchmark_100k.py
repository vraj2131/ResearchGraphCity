from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import resource
import sys
from time import perf_counter

from sqlalchemy import delete, func, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_settings
from app.assistant import build_evidence_packet
from app.db import create_engine_from_settings, create_session_factory
from app.models import CityPaperRecord, CityRecord, PaperEdgeRecord, PaperRecord, PaperReferenceRecord
from app.pipeline.city_structure import build_city_structure
from app.pipeline.original_city import build_original_city
from app.pipeline.bulk_io import copy_rows, upsert_paper_rows
from app.pipeline.edges import build_sparse_edges
from app.pipeline.embeddings import embed_city_papers, hash_documents
from app.repositories.postgres_city import PostgresCityRepository


TOPICS = [
    "Graph Learning",
    "Public Health",
    "Climate Energy",
    "Economic Mobility",
    "Genomics",
    "Materials Science",
    "Education Policy",
    "Knowledge Retrieval",
    "Network Visualization",
    "Clinical Informatics",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the PostgreSQL graph-city pipeline with synthetic papers.")
    parser.add_argument("--papers", type=int, default=100_000)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--semantic-k", type=int, default=20)
    parser.add_argument("--measure-warm-cache", action="store_true")
    parser.add_argument("--algorithm", choices=['original', 'leiden'], default='original')
    args = parser.parse_args()
    if args.papers < 10 or args.papers > 100_000:
        raise SystemExit("--papers must be between 10 and 100000")

    settings = load_settings()
    engine = create_engine_from_settings(settings)
    factory = create_session_factory(engine)
    repository = PostgresCityRepository(factory)
    city, _ = repository.create_city(f"Synthetic {args.papers:,}", ["synthetic seed"], args.papers)
    prefix = f"synthetic://{city.id}/"
    timings = {}
    try:
        started = perf_counter()
        persist_synthetic(factory, city.id, prefix, args.papers)
        timings["persist_seconds"] = perf_counter() - started

        started = perf_counter()
        embedded = embed_city_papers(city.id, repository)
        timings["embed_seconds"] = perf_counter() - started

        started = perf_counter()
        edge_counts = build_sparse_edges(
            city.id,
            repository,
            semantic_k=args.semantic_k,
            topic_k=10,
            attribute_k=10,
            max_similarity_degree=40,
            workers=settings.graph_workers,
        )
        timings["edges_seconds"] = perf_counter() - started

        warm_cache = None
        if args.measure_warm_cache:
            started = perf_counter()
            warm_counts = build_sparse_edges(
                city.id,
                repository,
                semantic_k=args.semantic_k,
                topic_k=10,
                attribute_k=10,
                max_similarity_degree=40,
                workers=settings.graph_workers,
            )
            warm_cache = {
                "seconds": round(perf_counter() - started, 3),
                "hit_sources": warm_counts["neighbor_cache_hit_sources"],
                "computed_sources": warm_counts["neighbor_computed_sources"],
            }

        started = perf_counter()
        structure_builder = build_original_city if args.algorithm == 'original' else build_city_structure
        structure_counts = structure_builder(city.id, repository)
        timings["city_seconds"] = perf_counter() - started

        scene = repository.get_scene(repository.get_city_record(str(city.id)).external_id)
        city_external_id = repository.get_city_record(str(city.id)).external_id
        query_embedding = hash_documents(["graph learning network visualization"])[0].tolist()
        search_latencies = benchmark_calls(
            lambda: repository.search_papers(
                city_external_id,
                "graph learning network visualization",
                query_embedding,
                limit=20,
            )
        )
        largest_building = max(scene["buildings"], key=lambda item: item["node_count"])
        pagination_latencies = benchmark_calls(
            lambda: repository.get_building_papers(city_external_id, largest_building["building_id"], limit=200)
        )
        retrieval_latencies = benchmark_calls(
            lambda: build_evidence_packet(
                repository,
                city_external_id,
                "Which graph learning papers, domains, and trends should I inspect?",
                {},
                12,
            ),
            iterations=12,
        )
        scene_json = json.dumps(scene, separators=(",", ":")).encode("utf-8")
        with factory() as session:
            edge_total = session.scalar(
                select(func.count()).select_from(PaperEdgeRecord).where(PaperEdgeRecord.city_id == city.id)
            )
            database_bytes = session.scalar(text("SELECT pg_database_size(current_database())"))
            max_similarity_degree = session.scalar(
                text(
                    """
                    SELECT COALESCE(MAX(degree), 0)
                    FROM (
                        SELECT endpoint, COUNT(*) AS degree
                        FROM (
                            SELECT source_openalex_id AS endpoint
                            FROM paper_edges WHERE city_id = :city_id AND edge_type = 'similarity'
                            UNION ALL
                            SELECT target_openalex_id AS endpoint
                            FROM paper_edges WHERE city_id = :city_id AND edge_type = 'similarity'
                        ) endpoints
                        GROUP BY endpoint
                    ) degrees
                    """
                ),
                {"city_id": city.id},
            )
        raw_peak_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        peak_rss_bytes = raw_peak_rss if sys.platform == "darwin" else raw_peak_rss * 1_024
        report = {
            "algorithm": repository.get_city_record(str(city.id)).algorithm_version,
            "papers": args.papers,
            "collection_mode": "synthetic_local",
            "collection_seconds": None,
            "embedded": embedded,
            "edges": int(edge_total or 0),
            "edge_components": edge_counts,
            "max_similarity_degree": int(max_similarity_degree or 0),
            "structure": structure_counts,
            "scene_bytes": len(scene_json),
            "scene_gzip_bytes": len(gzip.compress(scene_json)),
            "database_bytes": int(database_bytes or 0),
            "peak_rss_bytes": peak_rss_bytes,
            "timings": {name: round(value, 3) for name, value in timings.items()},
            "total_seconds": round(sum(timings.values()), 3),
            "warm_cache": warm_cache,
            "latency_ms": {
                "paper_search_p95": percentile_95(search_latencies),
                "building_papers_p95": percentile_95(pagination_latencies),
                "assistant_retrieval_p95": percentile_95(retrieval_latencies),
            },
        }
        print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    finally:
        if not args.keep:
            cleanup(factory, city.id, prefix)
        engine.dispose()


def benchmark_calls(function, *, iterations: int = 25) -> list[float]:
    function()  # Warm indexes and connection pools before recording acceptance latency.
    latencies = []
    for _ in range(iterations):
        started = perf_counter()
        function()
        latencies.append((perf_counter() - started) * 1_000)
    return latencies


def percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1))
    return round(ordered[index], 3)


def persist_synthetic(factory, city_id, prefix: str, count: int, batch_size: int = 25_000) -> None:
    for start in range(0, count, batch_size):
        stop = min(count, start + batch_size)
        papers = []
        memberships = []
        references = []
        for index in range(start, stop):
            openalex_id = f"{prefix}W{index:06d}"
            topic = TOPICS[index % len(TOPICS)]
            papers.append(
                {
                    "openalex_id": openalex_id,
                    "title": f"{topic} synthetic study {index}",
                    "abstract": f"Evidence methods and results for {topic} cluster {index % 100}.",
                    "publication_year": 2005 + index % 21,
                    "venue": f"Synthetic Journal {index % 50}",
                    "citation_count": index % 200,
                    "topics": [topic, f"Subtopic {index % 100}"],
                    "keywords": [f"keyword-{index % 200}"],
                    "author_ids": [f"A{index % 5_000}"],
                    "institutions": [f"Institution {index % 500}"],
                    "institution_ids": [f"I{index % 500}"],
                    "methods": [f"method-{index % 50}"],
                    "datasets": [f"dataset-{index % 100}"],
                    "metadata": {"source": "synthetic-benchmark"},
                }
            )
            memberships.append(
                {
                    "city_id": city_id,
                    "openalex_id": openalex_id,
                    "external_paper_id": f"P_{index:06d}",
                    "is_seed": index < 20,
                    "seed_position": index + 1 if index < 20 else None,
                    "seed_relevance": 1.0 if index < 20 else 0.5,
                    "expansion_depth": 0 if index < 20 else 1,
                    "expansion_source": "synthetic",
                }
            )
            if index > 0:
                references.append(
                    {"source_openalex_id": openalex_id, "target_openalex_id": f"{prefix}W{index - 1:06d}"}
                )
        with factory.begin() as session:
            connection = session.connection()
            upsert_paper_rows(connection, papers)
            connection.execute(
                text(
                    "CREATE TEMP TABLE membership_stage ("
                    "city_id uuid, openalex_id text, external_paper_id varchar(120), is_seed boolean, "
                    "seed_position smallint, seed_relevance double precision, expansion_depth smallint, "
                    "expansion_source varchar(80)) ON COMMIT DROP"
                )
            )
            membership_columns = (
                "city_id", "openalex_id", "external_paper_id", "is_seed", "seed_position",
                "seed_relevance", "expansion_depth", "expansion_source",
            )
            copy_rows(
                connection,
                "membership_stage",
                membership_columns,
                (tuple(item[column] for column in membership_columns) for item in memberships),
            )
            connection.execute(
                text(
                    """
                    INSERT INTO city_papers (
                        city_id, openalex_id, external_paper_id, is_seed, seed_position,
                        seed_relevance, expansion_depth, expansion_source
                    )
                    SELECT city_id, openalex_id, external_paper_id, is_seed, seed_position,
                           seed_relevance, expansion_depth, expansion_source
                    FROM membership_stage
                    ON CONFLICT (city_id, openalex_id) DO NOTHING
                    """
                )
            )
            if references:
                connection.execute(
                    text(
                        "CREATE TEMP TABLE reference_stage ("
                        "source_openalex_id text, target_openalex_id text) ON COMMIT DROP"
                    )
                )
                copy_rows(
                    connection,
                    "reference_stage",
                    ("source_openalex_id", "target_openalex_id"),
                    ((item["source_openalex_id"], item["target_openalex_id"]) for item in references),
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO paper_references (source_openalex_id, target_openalex_id)
                        SELECT source_openalex_id, target_openalex_id FROM reference_stage
                        ON CONFLICT (source_openalex_id, target_openalex_id) DO NOTHING
                        """
                    )
                )
    with factory.begin() as session:
        city = session.get(CityRecord, city_id)
        city.paper_count = count


def cleanup(factory, city_id, prefix: str) -> None:
    with factory.begin() as session:
        session.execute(delete(CityRecord).where(CityRecord.id == city_id))
        session.execute(delete(PaperRecord).where(PaperRecord.openalex_id.startswith(prefix)))


if __name__ == "__main__":
    main()
