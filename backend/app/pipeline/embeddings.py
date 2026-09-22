from __future__ import annotations

from collections.abc import Callable
import uuid

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sqlalchemy import and_, select, text

from ..models import CityPaperRecord, PaperEmbeddingRecord, PaperRecord
from ..repositories.postgres_city import PostgresCityRepository
from .bulk_io import copy_rows


EMBEDDING_DIMENSIONS = 64
EMBEDDING_MODEL = "hashing-64-v1"


def hash_documents(documents: list[str]) -> np.ndarray:
    vectorizer = HashingVectorizer(
        n_features=EMBEDDING_DIMENSIONS,
        alternate_sign=False,
        norm="l2",
        stop_words="english",
    )
    return vectorizer.transform(documents).toarray().astype(np.float32, copy=False)


def embed_city_papers(
    city_id: uuid.UUID,
    repository: PostgresCityRepository,
    *,
    model: str = EMBEDDING_MODEL,
    batch_size: int = 20_000,
    cancel_check: Callable[[], bool] | None = None,
) -> int:
    cancel_check = cancel_check or (lambda: False)
    embedded = 0
    query = (
        select(PaperRecord.openalex_id, PaperRecord.title, PaperRecord.abstract, PaperRecord.topics)
        .join(CityPaperRecord, CityPaperRecord.openalex_id == PaperRecord.openalex_id)
        .outerjoin(
            PaperEmbeddingRecord,
            and_(
                PaperEmbeddingRecord.openalex_id == PaperRecord.openalex_id,
                PaperEmbeddingRecord.model == model,
            ),
        )
        .where(
            CityPaperRecord.city_id == city_id,
            PaperEmbeddingRecord.openalex_id.is_(None),
        )
        .order_by(PaperRecord.openalex_id)
        .execution_options(stream_results=True)
    )
    with repository.session_factory() as read_session:
        result = read_session.execute(query).yield_per(batch_size)
        rows = []
        for row in result:
            rows.append(row)
            if len(rows) == batch_size:
                if cancel_check():
                    return embedded
                embedded += _store_embedding_batch(repository, rows, model)
                rows = []
        if rows and not cancel_check():
            embedded += _store_embedding_batch(repository, rows, model)
    return embedded


def _store_embedding_batch(repository, rows, model: str) -> int:
    documents = [f"{title} {abstract} {' '.join(topics)}".strip() for _, title, abstract, topics in rows]
    vectors = hash_documents(documents)
    values = [
        (openalex_id, model, EMBEDDING_DIMENSIONS, vector.tolist())
        for (openalex_id, _, _, _), vector in zip(rows, vectors, strict=True)
    ]
    engine = repository.session_factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TEMP TABLE embedding_stage ("
                "openalex_id text, model varchar(240), dimensions smallint, embedding real[]"
                ") ON COMMIT DROP"
            )
        )
        copy_rows(
            connection,
            "embedding_stage",
            ("openalex_id", "model", "dimensions", "embedding"),
            values,
        )
        connection.execute(
            text(
                """
                INSERT INTO paper_embeddings (openalex_id, model, dimensions, embedding)
                SELECT openalex_id, model, dimensions, embedding::vector(64)
                FROM embedding_stage
                ON CONFLICT (openalex_id, model) DO NOTHING
                """
            )
        )
    return len(values)
