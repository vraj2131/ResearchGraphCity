from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import os

from ..config import Settings
from ..jobs import JobRepository
from ..models import BuildJobRecord
from ..openalex_client import OpenAlexCancelled, OpenAlexClient, PostgresOpenAlexCache, RequestRateLimiter
from ..openalex_snapshot import OpenAlexSnapshot
from ..repositories.postgres_city import PostgresCityRepository
from .city_structure import build_city_structure
from .edges import build_sparse_edges
from .embeddings import EMBEDDING_MODEL, embed_city_papers
from .expansion import expand_city
from .seed_stage import run_seed_stage


def build_city_job(
    job: BuildJobRecord,
    jobs: JobRepository,
    repository: PostgresCityRepository,
    settings: Settings,
    *,
    client: OpenAlexClient | None = None,
) -> None:
    city = repository.get_city_record(str(job.city_id))
    target = city.target_paper_count

    def cancelled() -> bool:
        return jobs.should_cancel(job.id)

    if client is not None:
        active_client = client
    elif settings.openalex_snapshot_path:
        active_client = OpenAlexSnapshot(settings.openalex_snapshot_path)
    else:
        active_client = OpenAlexClient(
            api_key=os.getenv("OPENALEX_API_KEY"),
            cache=PostgresOpenAlexCache(repository.session_factory, settings.openalex_cache_ttl_seconds),
            timeout_seconds=settings.openalex_timeout_seconds,
            max_retries=settings.openalex_max_retries,
            cancel_check=cancelled,
            rate_limiter=RequestRateLimiter(settings.openalex_min_interval_seconds),
        )
    try:
        jobs.update_progress(job.id, stage="resolve", current=0, total=target, message="Resolving seed papers")
        seeds = run_seed_stage(job.city_id, repository, active_client)
        if cancelled():
            raise OpenAlexCancelled("Build cancelled after seed resolution")
        jobs.update_progress(
            job.id,
            stage="collect",
            current=seeds.resolved_count,
            total=target,
            message=f"Resolved {seeds.resolved_count} seeds; collecting related papers",
        )
        pending_embedding: Future | None = None
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="city-embed") as embedding_executor:
            def schedule_embedding(batch_city_id, _openalex_ids) -> None:
                nonlocal pending_embedding
                if pending_embedding is not None and pending_embedding.done():
                    pending_embedding.result()
                    pending_embedding = None
                if pending_embedding is None:
                    pending_embedding = embedding_executor.submit(
                        embed_city_papers,
                        batch_city_id,
                        repository,
                        model=EMBEDDING_MODEL,
                        cancel_check=cancelled,
                    )

            expansion = expand_city(
                job.city_id,
                repository,
                active_client,
                cancel_check=cancelled,
                workers=settings.openalex_workers,
                on_batch_committed=schedule_embedding,
            )
            if pending_embedding is not None:
                pending_embedding.result()
        if cancelled():
            raise OpenAlexCancelled("Build cancelled during expansion")
        jobs.update_progress(
            job.id,
            stage="embed",
            current=expansion.total_paper_count,
            total=target,
            message=f"Embedding {expansion.total_paper_count} papers",
        )
        embed_city_papers(
            job.city_id,
            repository,
            model=EMBEDDING_MODEL,
            cancel_check=cancelled,
        )
        if cancelled():
            raise OpenAlexCancelled("Build cancelled during embedding")
        jobs.update_progress(
            job.id,
            stage="edges",
            current=expansion.total_paper_count,
            total=target,
            message="Constructing bounded citation and similarity edges",
        )
        build_sparse_edges(
            job.city_id,
            repository,
            model=EMBEDDING_MODEL,
            workers=settings.graph_workers,
            cancel_check=cancelled,
        )
        if cancelled():
            raise OpenAlexCancelled("Build cancelled during edge construction")
        jobs.update_progress(
            job.id,
            stage="city",
            current=expansion.total_paper_count,
            total=target,
            message="Detecting communities and constructing the graph city",
        )
        counts = build_city_structure(job.city_id, repository)
        warning = " Source corpus exhausted before target." if expansion.exhausted else ""
        jobs.update_progress(
            job.id,
            stage="finalize",
            current=expansion.total_paper_count,
            total=target,
            message=(
                f"Built {counts['buildings']} buildings, {counts['bridges']} bridges, "
                f"and {counts['streets']} streets.{warning}"
            ),
        )
    except OpenAlexCancelled:
        repository.set_city_status(job.city_id, "cancelled")
        if not jobs.should_cancel(job.id):
            jobs.request_cancel(job.id)
        raise
    except Exception:
        repository.set_city_status(job.city_id, "failed")
        raise


def create_build_handler(settings: Settings, repository: PostgresCityRepository):
    def handler(job: BuildJobRecord, jobs: JobRepository) -> None:
        build_city_job(job, jobs, repository, settings)

    return handler
