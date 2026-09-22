from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://research_graph_city:research_graph_city@"
    "127.0.0.1:55432/research_graph_city"
)


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_backend: Literal["json", "postgres"]
    worker_poll_seconds: float
    job_stale_seconds: int
    embedding_model: str
    openalex_timeout_seconds: float = 30.0
    openalex_max_retries: int = 4
    openalex_cache_ttl_seconds: int = 86_400
    graph_workers: int = 8
    openalex_workers: int = 6
    openalex_min_interval_seconds: float = 0.1
    openalex_snapshot_path: str | None = None


def load_project_env(project_root: Path = PROJECT_ROOT) -> bool:
    return load_dotenv(project_root / ".env", override=False)


def load_settings(project_root: Path = PROJECT_ROOT) -> Settings:
    load_project_env(project_root)
    storage_backend = os.getenv("STORAGE_BACKEND", "json").strip().lower()
    if storage_backend not in {"json", "postgres"}:
        raise ValueError("STORAGE_BACKEND must be either 'json' or 'postgres'")

    worker_poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "1.0"))
    job_stale_seconds = int(os.getenv("JOB_STALE_SECONDS", "300"))
    if worker_poll_seconds <= 0:
        raise ValueError("WORKER_POLL_SECONDS must be greater than zero")
    if job_stale_seconds < 60:
        raise ValueError("JOB_STALE_SECONDS must be at least 60")
    openalex_timeout_seconds = float(os.getenv("OPENALEX_TIMEOUT_SECONDS", "30"))
    openalex_max_retries = int(os.getenv("OPENALEX_MAX_RETRIES", "4"))
    openalex_cache_ttl_seconds = int(os.getenv("OPENALEX_CACHE_TTL_SECONDS", "86400"))
    if openalex_timeout_seconds <= 0 or openalex_max_retries < 0 or openalex_cache_ttl_seconds < 0:
        raise ValueError("OpenAlex timeout, retry, and cache settings must be non-negative")
    graph_workers = int(os.getenv("GRAPH_WORKERS", str(min(8, max(1, os.cpu_count() or 4)))))
    openalex_workers = int(os.getenv("OPENALEX_WORKERS", "6"))
    openalex_min_interval_seconds = float(os.getenv("OPENALEX_MIN_INTERVAL_SECONDS", "0.1"))
    if not 1 <= graph_workers <= 32:
        raise ValueError("GRAPH_WORKERS must be between 1 and 32")
    if not 1 <= openalex_workers <= 16:
        raise ValueError("OPENALEX_WORKERS must be between 1 and 16")
    if openalex_min_interval_seconds < 0:
        raise ValueError("OPENALEX_MIN_INTERVAL_SECONDS must be non-negative")
    snapshot_path = os.getenv("OPENALEX_SNAPSHOT_PATH", "").strip() or None

    return Settings(
        database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_backend=cast(Literal["json", "postgres"], storage_backend),
        worker_poll_seconds=worker_poll_seconds,
        job_stale_seconds=job_stale_seconds,
        embedding_model=os.getenv("EMBEDDING_MODEL", "hashing-64-v1"),
        openalex_timeout_seconds=openalex_timeout_seconds,
        openalex_max_retries=openalex_max_retries,
        openalex_cache_ttl_seconds=openalex_cache_ttl_seconds,
        graph_workers=graph_workers,
        openalex_workers=openalex_workers,
        openalex_min_interval_seconds=openalex_min_interval_seconds,
        openalex_snapshot_path=snapshot_path,
    )
