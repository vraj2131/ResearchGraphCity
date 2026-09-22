from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import uuid

import hnswlib
import numpy as np
from sqlalchemy import func, select, text

from ..models import CityPaperRecord, PaperEmbeddingRecord, PaperNeighborRecord
from ..repositories.postgres_city import PostgresCityRepository


HNSW_ALGORITHM_VERSION = "hnsw-cosine-v1"


class NeighborBuildCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class NeighborRow:
    source_openalex_id: str
    target_openalex_id: str
    rank: int
    similarity: float


@dataclass(frozen=True)
class NeighborBuildResult:
    candidate_count: int
    cache_hit_sources: int
    computed_sources: int
    scope_key: str


def build_hnsw_neighbors(
    openalex_ids: list[str],
    embeddings: np.ndarray,
    *,
    top_k: int,
    workers: int,
    cancel_check: Callable[[], bool] | None = None,
) -> list[NeighborRow]:
    cancel_check = cancel_check or (lambda: False)
    if cancel_check():
        raise NeighborBuildCancelled("Neighbor construction cancelled")
    if top_k <= 0 or len(openalex_ids) < 2:
        return []
    vectors = np.asarray(embeddings, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != len(openalex_ids):
        raise ValueError("Embedding rows must match paper IDs")
    worker_count = max(1, workers)
    index = hnswlib.Index(space="cosine", dim=vectors.shape[1])
    index.init_index(
        max_elements=len(openalex_ids),
        ef_construction=max(100, top_k * 4),
        M=16,
        random_seed=42,
    )
    labels = np.arange(len(openalex_ids), dtype=np.int32)
    index.add_items(vectors, labels, num_threads=worker_count)
    index.set_ef(max(64, top_k * 3))
    query_k = min(len(openalex_ids), top_k + 1)
    neighbor_labels, distances = index.knn_query(vectors, k=query_k, num_threads=worker_count)
    if cancel_check():
        raise NeighborBuildCancelled("Neighbor construction cancelled")

    rows: list[NeighborRow] = []
    for source_index, (targets, target_distances) in enumerate(zip(neighbor_labels, distances, strict=True)):
        source_id = openalex_ids[source_index]
        rank = 0
        for target_index, distance in zip(targets, target_distances, strict=True):
            target_id = openalex_ids[int(target_index)]
            if source_id == target_id:
                continue
            rank += 1
            rows.append(
                NeighborRow(
                    source_openalex_id=source_id,
                    target_openalex_id=target_id,
                    rank=rank,
                    similarity=max(0.0, min(1.0, 1.0 - float(distance))),
                )
            )
            if rank == top_k:
                break
    return rows


def canonical_pairs(rows: Iterable[NeighborRow]) -> dict[tuple[str, str], float]:
    pairs: dict[tuple[str, str], float] = {}
    for row in rows:
        if row.source_openalex_id == row.target_openalex_id:
            continue
        pair = tuple(sorted((row.source_openalex_id, row.target_openalex_id)))
        pairs[pair] = max(pairs.get(pair, 0.0), row.similarity)
    return dict(sorted(pairs.items()))


def compute_city_neighbors(
    city_id: uuid.UUID,
    repository: PostgresCityRepository,
    model: str,
    *,
    top_k: int,
    workers: int,
    cancel_check: Callable[[], bool] | None = None,
) -> NeighborBuildResult:
    result, _ = get_city_neighbors(
        city_id,
        repository,
        model,
        top_k=top_k,
        workers=workers,
        cancel_check=cancel_check,
    )
    _merge_cached_neighbors(city_id, repository, model, result.scope_key, top_k)
    return result


def get_city_neighbors(
    city_id: uuid.UUID,
    repository: PostgresCityRepository,
    model: str,
    *,
    top_k: int,
    workers: int,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[NeighborBuildResult, list[NeighborRow]]:
    cancel_check = cancel_check or (lambda: False)
    with repository.session_factory() as session:
        embedding_rows = session.execute(
            select(PaperEmbeddingRecord.openalex_id, PaperEmbeddingRecord.embedding)
            .join(CityPaperRecord, CityPaperRecord.openalex_id == PaperEmbeddingRecord.openalex_id)
            .where(CityPaperRecord.city_id == city_id, PaperEmbeddingRecord.model == model)
            .order_by(PaperEmbeddingRecord.openalex_id)
        ).all()
    openalex_ids = [row[0] for row in embedding_rows]
    scope_key = hashlib.sha256("\n".join(openalex_ids).encode("utf-8")).hexdigest()
    expected_per_source = min(top_k, max(0, len(openalex_ids) - 1))
    expected_count = len(openalex_ids) * expected_per_source
    with repository.session_factory() as session:
        cached_sources = int(
            session.scalar(
                select(func.count())
                .select_from(PaperNeighborRecord)
                .where(
                    PaperNeighborRecord.model == model,
                    PaperNeighborRecord.algorithm_version == HNSW_ALGORITHM_VERSION,
                    PaperNeighborRecord.scope_key == scope_key,
                    func.cardinality(PaperNeighborRecord.target_openalex_ids) >= expected_per_source,
                )
            )
            or 0
        )

    cache_hit_sources = len(openalex_ids) if expected_count > 0 and cached_sources == len(openalex_ids) else 0
    computed_sources = 0
    neighbors: list[NeighborRow]
    if expected_count and not cache_hit_sources:
        vectors = np.stack([np.asarray(row[1], dtype=np.float32) for row in embedding_rows])
        neighbors = build_hnsw_neighbors(
            openalex_ids,
            vectors,
            top_k=expected_per_source,
            workers=workers,
            cancel_check=cancel_check,
        )
        _replace_neighbor_cache(repository, model, scope_key, neighbors, workers=workers)
        computed_sources = len(openalex_ids)
    elif expected_count:
        neighbors = _load_cached_neighbors(repository, model, scope_key, expected_per_source)
    else:
        neighbors = []
    if cancel_check():
        raise NeighborBuildCancelled("Neighbor construction cancelled")
    return (
        NeighborBuildResult(
            candidate_count=expected_count,
            cache_hit_sources=cache_hit_sources,
            computed_sources=computed_sources,
            scope_key=scope_key,
        ),
        neighbors,
    )


def _load_cached_neighbors(
    repository: PostgresCityRepository,
    model: str,
    scope_key: str,
    top_k: int,
) -> list[NeighborRow]:
    with repository.session_factory() as session:
        rows = session.execute(
            select(
                PaperNeighborRecord.source_openalex_id,
                PaperNeighborRecord.target_openalex_ids,
                PaperNeighborRecord.similarities,
            )
            .where(
                PaperNeighborRecord.model == model,
                PaperNeighborRecord.algorithm_version == HNSW_ALGORITHM_VERSION,
                PaperNeighborRecord.scope_key == scope_key,
            )
            .order_by(PaperNeighborRecord.source_openalex_id)
        ).all()
    return [
        NeighborRow(source, target, rank, float(similarity))
        for source, targets, similarities in rows
        for rank, (target, similarity) in enumerate(zip(targets, similarities, strict=True), start=1)
        if rank <= top_k
    ]


def _replace_neighbor_cache(
    repository: PostgresCityRepository,
    model: str,
    scope_key: str,
    rows: list[NeighborRow],
    *,
    workers: int = 1,
) -> None:
    engine = repository.session_factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM paper_neighbors "
                "WHERE model = :model AND algorithm_version = :algorithm AND scope_key = :scope_key"
            ),
            {"model": model, "algorithm": HNSW_ALGORITHM_VERSION, "scope_key": scope_key},
        )
    grouped: dict[str, tuple[list[str], list[float]]] = {}
    for row in rows:
        targets, similarities = grouped.setdefault(row.source_openalex_id, ([], []))
        targets.append(row.target_openalex_id)
        similarities.append(row.similarity)
    cache_rows = list(grouped.items())
    worker_count = min(4, max(1, workers), len(cache_rows))
    chunk_size = (len(cache_rows) + worker_count - 1) // worker_count
    chunks = [cache_rows[start : start + chunk_size] for start in range(0, len(cache_rows), chunk_size)]
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="neighbor-cache") as executor:
        futures = [
            executor.submit(_copy_neighbor_cache_chunk, repository, model, scope_key, chunk)
            for chunk in chunks
        ]
        for future in futures:
            future.result()


def _copy_neighbor_cache_chunk(repository, model: str, scope_key: str, rows: list[tuple]) -> None:
    engine = repository.session_factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL synchronous_commit = off"))
        driver_connection = connection.connection.driver_connection
        with driver_connection.cursor() as cursor:
            with cursor.copy(
                "COPY paper_neighbors ("
                "model, algorithm_version, scope_key, source_openalex_id, "
                "target_openalex_ids, similarities) FROM STDIN"
            ) as copy:
                for source_id, (targets, similarities) in rows:
                    copy.write_row(
                        (model, HNSW_ALGORITHM_VERSION, scope_key, source_id, targets, similarities)
                    )


def _merge_cached_neighbors(
    city_id: uuid.UUID,
    repository: PostgresCityRepository,
    model: str,
    scope_key: str,
    top_k: int,
) -> None:
    statement = text(
        """
        WITH deduplicated AS (
          SELECT
            LEAST(neighbors.source_openalex_id, neighbors.target_openalex_id) AS source_id,
            GREATEST(neighbors.source_openalex_id, neighbors.target_openalex_id) AS target_id,
            MAX(neighbors.similarity) AS similarity
          FROM (
            SELECT pn.source_openalex_id,
                   pn.target_openalex_ids[position] AS target_openalex_id,
                   pn.similarities[position] AS similarity
            FROM paper_neighbors pn
            CROSS JOIN LATERAL generate_subscripts(pn.target_openalex_ids, 1) AS position
            WHERE pn.model = :model
              AND pn.algorithm_version = :algorithm
              AND pn.scope_key = :scope_key
              AND position <= :top_k
          ) neighbors
          GROUP BY 1, 2
        )
        INSERT INTO paper_edges (
          city_id, source_openalex_id, target_openalex_id, edge_type,
          weight, components, evidence, directed
        )
        SELECT
          :city_id, source_id, target_id, 'similarity',
          0.55 * similarity,
          jsonb_build_object('semantic_similarity', ROUND(similarity::numeric, 6)),
          jsonb_build_array('semantic_similarity: ' || ROUND(similarity::numeric, 4)::text),
          false
        FROM deduplicated
        ON CONFLICT ON CONSTRAINT uq_paper_edges_pair_type DO UPDATE SET
          weight = GREATEST(paper_edges.weight, EXCLUDED.weight),
          components = paper_edges.components || EXCLUDED.components,
          evidence = paper_edges.evidence || EXCLUDED.evidence
        """
    )
    with repository.session_factory.begin() as session:
        session.execute(
            statement,
            {
                "city_id": city_id,
                "model": model,
                "algorithm": HNSW_ALGORITHM_VERSION,
                "scope_key": scope_key,
                "top_k": top_k,
            },
        )
