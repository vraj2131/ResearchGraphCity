from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
import heapq
import uuid

from psycopg.types.json import Jsonb
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from ..models import CityPaperRecord, PaperEdgeRecord, PaperEmbeddingRecord, PaperRecord, PaperReferenceRecord
from ..repositories.postgres_city import PostgresCityRepository
from .bulk_io import copy_rows
from .embeddings import EMBEDDING_MODEL
from .vector_neighbors import NeighborBuildCancelled, canonical_pairs, get_city_neighbors


def bounded_topic_pairs(
    papers: Iterable[dict],
    *,
    top_k: int = 10,
    bucket_cap: int = 500,
) -> list[tuple[str, str]]:
    paper_rows = list(papers)
    topic_buckets: dict[str, list[str]] = defaultdict(list)
    for paper in paper_rows:
        paper_id = str(paper["id"])
        for topic in {str(item).strip().casefold() for item in paper.get("topics", []) if str(item).strip()}:
            topic_buckets[topic].append(paper_id)
    for topic, members in topic_buckets.items():
        topic_buckets[topic] = sorted(set(members))[:bucket_cap]

    candidates_by_paper: dict[str, Counter[str]] = defaultdict(Counter)
    for members in topic_buckets.values():
        for source in members:
            for target in members:
                if source != target:
                    candidates_by_paper[source][target] += 1

    pairs: set[tuple[str, str]] = set()
    for source, candidates in candidates_by_paper.items():
        strongest = sorted(candidates.items(), key=lambda item: (-item[1], item[0]))[:top_k]
        for target, _ in strongest:
            pairs.add(tuple(sorted((source, target))))
    return sorted(pairs)


def bounded_attribute_pairs(
    papers: Iterable[dict],
    *,
    keys: tuple[str, ...] = ("author_ids", "methods", "datasets"),
    top_k: int = 10,
    bucket_cap: int = 100,
) -> list[tuple[str, str]]:
    rows = list(papers)
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for paper in rows:
        paper_id = str(paper["id"])
        for key in keys:
            for value in {str(item).strip().casefold() for item in paper.get(key, []) if str(item).strip()}:
                buckets[(key, value)].append(paper_id)
    overlap: dict[str, Counter[str]] = defaultdict(Counter)
    for members in buckets.values():
        bounded = sorted(set(members))[:bucket_cap]
        for source in bounded:
            for target in bounded:
                if source != target:
                    overlap[source][target] += 1
    pairs: set[tuple[str, str]] = set()
    for source, candidates in overlap.items():
        for target, _ in sorted(candidates.items(), key=lambda item: (-item[1], item[0]))[:top_k]:
            pairs.add(tuple(sorted((source, target))))
    return sorted(pairs)


def build_sparse_edges(
    city_id: uuid.UUID,
    repository: PostgresCityRepository,
    *,
    model: str = EMBEDDING_MODEL,
    semantic_k: int = 20,
    topic_k: int = 10,
    attribute_k: int = 10,
    max_similarity_degree: int = 40,
    workers: int = 8,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, int]:
    cancel_check = cancel_check or (lambda: False)
    with repository.session_factory.begin() as session:
        session.execute(
            delete(PaperEdgeRecord).where(
                PaperEdgeRecord.city_id == city_id,
                PaperEdgeRecord.edge_type.in_(("citation", "similarity")),
            )
        )
    with repository.session_factory() as session:
        rows = session.execute(
            select(
                PaperRecord.openalex_id,
                PaperRecord.topics,
                PaperRecord.author_ids,
                PaperRecord.methods,
                PaperRecord.datasets,
            )
            .join(CityPaperRecord, CityPaperRecord.openalex_id == PaperRecord.openalex_id)
            .where(CityPaperRecord.city_id == city_id)
            .order_by(PaperRecord.openalex_id)
        ).all()
        papers = [
            {"id": row[0], "topics": row[1], "author_ids": row[2], "methods": row[3], "datasets": row[4]}
            for row in rows
        ]
    city_ids = {paper["id"] for paper in papers}
    citation_rows = _collect_citation_rows(city_id, repository, city_ids, cancel_check)

    pair_components: dict[tuple[str, str], dict] = {}
    topic_lookup = {
        paper["id"]: {str(item).casefold() for item in paper.get("topics", []) if str(item).strip()}
        for paper in papers
    }
    for pair in bounded_topic_pairs(papers, top_k=topic_k):
        left = topic_lookup.get(pair[0], set())
        right = topic_lookup.get(pair[1], set())
        pair_components.setdefault(pair, {})["topic_similarity"] = len(left & right) / len(left | right) if left and right else 0.0
    for pair in bounded_attribute_pairs(papers, top_k=attribute_k):
        pair_components.setdefault(pair, {})["attribute_overlap"] = 1.0
    semantic_count = 0
    cache_hit_sources = 0
    computed_sources = 0
    if semantic_k > 0:
        try:
            neighbor_result, neighbor_rows = get_city_neighbors(
                city_id,
                repository,
                model,
                top_k=semantic_k,
                workers=workers,
                cancel_check=cancel_check,
            )
            semantic_count = neighbor_result.candidate_count
            cache_hit_sources = neighbor_result.cache_hit_sources
            computed_sources = neighbor_result.computed_sources
            for pair, similarity in canonical_pairs(neighbor_rows).items():
                components = pair_components.setdefault(pair, {})
                components["semantic_similarity"] = max(
                    float(components.get("semantic_similarity", 0.0)),
                    similarity,
                )
        except NeighborBuildCancelled:
            semantic_count = 0
    similarity_rows = _bounded_similarity_rows(pair_components, max_similarity_degree)
    _copy_city_edges(city_id, repository, citation_rows, similarity_rows, workers=workers)
    return {
        "citation": len(citation_rows),
        "similarity": len(similarity_rows),
        "semantic_candidates": semantic_count,
        "neighbor_cache_hit_sources": cache_hit_sources,
        "neighbor_computed_sources": computed_sources,
    }


def _collect_citation_rows(city_id, repository, city_ids: set[str], cancel_check) -> list[tuple]:
    by_pair: dict[tuple[str, str], list[str]] = {}
    with repository.session_factory() as session:
        references = session.execute(
            select(PaperReferenceRecord.source_openalex_id, PaperReferenceRecord.target_openalex_id)
            .join(CityPaperRecord, CityPaperRecord.openalex_id == PaperReferenceRecord.source_openalex_id)
            .where(CityPaperRecord.city_id == city_id)
        ).yield_per(10_000)
        for source, target in references:
            if target not in city_ids or source == target:
                continue
            pair = tuple(sorted((source, target)))
            by_pair.setdefault(pair, []).append(f"citation_direction: {source} -> {target}")
            if cancel_check():
                break
    return [
        (source, target, "citation", 1.0, {"citation": 1.0}, evidence, True)
        for (source, target), evidence in sorted(by_pair.items())
    ]


def _bounded_similarity_rows(
    pair_components: dict[tuple[str, str], dict],
    max_degree: int,
) -> list[tuple]:
    weighted: dict[tuple[str, str], tuple[float, dict]] = {}
    for pair, components in pair_components.items():
        semantic = float(components.get("semantic_similarity", 0.0))
        topic = float(components.get("topic_similarity", 0.0))
        attributes = float(components.get("attribute_overlap", 0.0))
        weight = max(0.55 * semantic, 0.30 * topic + 0.15 * attributes)
        if weight > 0:
            weighted[pair] = (round(weight, 6), components)
    if max_degree <= 0:
        return []

    strongest: dict[str, list[tuple[float, tuple[str, str]]]] = defaultdict(list)
    for pair, (weight, _) in weighted.items():
        for node_id in pair:
            heap = strongest[node_id]
            heapq.heappush(heap, (weight, pair))
            if len(heap) > max_degree:
                heapq.heappop(heap)
    accepted = {node_id: {pair for _, pair in heap} for node_id, heap in strongest.items()}
    rows = []
    for pair, (weight, components) in sorted(weighted.items()):
        if pair not in accepted.get(pair[0], set()) or pair not in accepted.get(pair[1], set()):
            continue
        evidence = [f"{name}: {float(value):.4f}" for name, value in components.items() if float(value) > 0]
        rows.append((pair[0], pair[1], "similarity", weight, components, evidence, False))
    return rows


def _copy_city_edges(
    city_id,
    repository,
    citation_rows: list[tuple],
    similarity_rows: list[tuple],
    *,
    workers: int,
) -> None:
    rows = citation_rows + similarity_rows
    if not rows:
        return
    worker_count = min(8, max(1, workers), len(rows))
    chunk_size = (len(rows) + worker_count - 1) // worker_count
    chunks = [rows[start : start + chunk_size] for start in range(0, len(rows), chunk_size)]
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="edge-copy") as executor:
        futures = [executor.submit(_copy_edge_chunk, city_id, repository, chunk) for chunk in chunks]
        for future in futures:
            future.result()


def _copy_edge_chunk(city_id, repository, rows: list[tuple]) -> None:
    engine = repository.session_factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL synchronous_commit = off"))
        copy_rows(
            connection,
            "paper_edges",
            (
                "city_id",
                "source_openalex_id",
                "target_openalex_id",
                "edge_type",
                "weight",
                "components",
                "evidence",
                "directed",
            ),
            (
                (city_id, source, target, edge_type, weight, Jsonb(components), Jsonb(evidence), directed)
                for source, target, edge_type, weight, components, evidence, directed in rows
            ),
        )


def _insert_citations(city_id, repository, city_ids: set[str], cancel_check) -> int:
    inserted = 0
    with repository.session_factory() as session:
        references = session.execute(
            select(PaperReferenceRecord.source_openalex_id, PaperReferenceRecord.target_openalex_id)
            .join(CityPaperRecord, CityPaperRecord.openalex_id == PaperReferenceRecord.source_openalex_id)
            .where(CityPaperRecord.city_id == city_id)
        ).yield_per(2_000)
        batch = []
        for source, target in references:
            if target not in city_ids or source == target:
                continue
            pair = tuple(sorted((source, target)))
            batch.append(
                {
                    "city_id": city_id,
                    "source_openalex_id": pair[0],
                    "target_openalex_id": pair[1],
                    "edge_type": "citation",
                    "weight": 1.0,
                    "components": {"citation": 1.0},
                    "evidence": [f"citation_direction: {source} -> {target}"],
                    "directed": True,
                }
            )
            if len(batch) >= 1_000:
                inserted += _insert_edge_batch(repository, batch)
                batch = []
                if cancel_check():
                    return inserted
        if batch:
            inserted += _insert_edge_batch(repository, batch)
    return inserted


def _upsert_similarity_pairs(city_id, repository, pair_components: dict[tuple[str, str], dict]) -> None:
    rows = []
    for (source, target), components in pair_components.items():
        semantic = components.get("semantic_similarity", 0.0)
        topic = components.get("topic_similarity", 0.0)
        attributes = components.get("attribute_overlap", 0.0)
        weight = round(0.55 * semantic + 0.30 * topic + 0.15 * attributes, 6)
        if weight <= 0:
            continue
        rows.append((source, target, semantic, topic, attributes, weight))
    if not rows:
        return
    engine = repository.session_factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TEMP TABLE pair_component_stage ("
                "source_id text, target_id text, semantic double precision, "
                "topic double precision, attributes double precision, weight double precision"
                ") ON COMMIT DROP"
            )
        )
        driver_connection = connection.connection.driver_connection
        with driver_connection.cursor() as cursor:
            with cursor.copy(
                "COPY pair_component_stage (source_id, target_id, semantic, topic, attributes, weight) FROM STDIN"
            ) as copy:
                for row in rows:
                    copy.write_row(row)
        connection.execute(
            text(
                """
                INSERT INTO paper_edges (
                    city_id, source_openalex_id, target_openalex_id, edge_type,
                    weight, components, evidence, directed
                )
                SELECT
                    :city_id, source_id, target_id, 'similarity', weight,
                    (CASE WHEN semantic > 0 THEN jsonb_build_object('semantic_similarity', semantic) ELSE '{}'::jsonb END) ||
                    (CASE WHEN topic > 0 THEN jsonb_build_object('topic_similarity', topic) ELSE '{}'::jsonb END) ||
                    (CASE WHEN attributes > 0 THEN jsonb_build_object('attribute_overlap', attributes) ELSE '{}'::jsonb END),
                    (CASE WHEN semantic > 0 THEN jsonb_build_array('semantic_similarity: ' || ROUND(semantic::numeric, 4)::text) ELSE '[]'::jsonb END) ||
                    (CASE WHEN topic > 0 THEN jsonb_build_array('topic_similarity: ' || ROUND(topic::numeric, 4)::text) ELSE '[]'::jsonb END) ||
                    (CASE WHEN attributes > 0 THEN jsonb_build_array('attribute_overlap: ' || ROUND(attributes::numeric, 4)::text) ELSE '[]'::jsonb END),
                    false
                FROM pair_component_stage
                ON CONFLICT ON CONSTRAINT uq_paper_edges_pair_type DO UPDATE SET
                    weight = GREATEST(paper_edges.weight, EXCLUDED.weight),
                    components = paper_edges.components || EXCLUDED.components,
                    evidence = EXCLUDED.evidence
                """
            ),
            {"city_id": city_id},
        )


def _insert_edge_batch(repository, values: list[dict]) -> int:
    with repository.session_factory.begin() as session:
        statement = insert(PaperEdgeRecord).values(values).on_conflict_do_nothing(
            constraint="uq_paper_edges_pair_type"
        ).returning(PaperEdgeRecord.id)
        return len(session.scalars(statement).all())


def _upsert_similarity_batch(repository, values: list[dict]) -> None:
    with repository.session_factory.begin() as session:
        statement = insert(PaperEdgeRecord).values(values)
        excluded = statement.excluded
        session.execute(
            statement.on_conflict_do_update(
                constraint="uq_paper_edges_pair_type",
                set_={
                    "weight": func.greatest(PaperEdgeRecord.weight, excluded.weight),
                    "components": PaperEdgeRecord.components.op("||")(excluded.components),
                    "evidence": excluded.evidence,
                },
            )
        )


def _prune_similarity_degree(city_id, repository, max_degree: int) -> None:
    if max_degree <= 0:
        with repository.session_factory.begin() as session:
            session.execute(delete(PaperEdgeRecord).where(PaperEdgeRecord.city_id == city_id, PaperEdgeRecord.edge_type == "similarity"))
        return
    query = text(
        """
        WITH endpoints AS (
          SELECT id AS edge_id, source_openalex_id AS node_id, weight
          FROM paper_edges WHERE city_id = :city_id AND edge_type = 'similarity'
          UNION ALL
          SELECT id AS edge_id, target_openalex_id AS node_id, weight
          FROM paper_edges WHERE city_id = :city_id AND edge_type = 'similarity'
        ), ranked AS (
          SELECT edge_id, row_number() OVER (PARTITION BY node_id ORDER BY weight DESC, edge_id) AS rank
          FROM endpoints
        ), rejected AS (
          SELECT DISTINCT edge_id FROM ranked WHERE rank > :max_degree
        )
        DELETE FROM paper_edges WHERE id IN (SELECT edge_id FROM rejected)
        """
    )
    with repository.session_factory.begin() as session:
        session.execute(query, {"city_id": city_id, "max_degree": max_degree})
