from __future__ import annotations

import argparse
from collections.abc import Callable
import os
import socket
import time

from .config import Settings, load_settings
from .db import create_engine_from_settings, create_session_factory
from .jobs import JobRepository
from .models import BuildJobRecord
from .pipeline.build import create_build_handler
from .repositories.postgres_city import PostgresCityRepository
from .openalex_client import OpenAlexCancelled


BuildHandler = Callable[[BuildJobRecord, JobRepository], None]


def run_worker(
    settings: Settings,
    *,
    once: bool = False,
    handler: BuildHandler | None = None,
    worker_id: str | None = None,
) -> None:
    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(engine)
    repository = JobRepository(session_factory)
    active_handler = handler or create_build_handler(settings, PostgresCityRepository(session_factory))
    identity = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    repository.requeue_stale(settings.job_stale_seconds)

    while True:
        job = repository.claim_next(identity)
        if job is None:
            if once:
                return
            time.sleep(settings.worker_poll_seconds)
            continue
        try:
            if repository.should_cancel(job.id):
                repository.finish(job.id)
            else:
                active_handler(job, repository)
                repository.finish(job.id, message=repository.get(job.id).message)
        except OpenAlexCancelled:
            repository.finish(job.id)
        except Exception as exc:
            repository.fail(job.id, exc)
        if once:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Research Graph City PostgreSQL build worker.")
    parser.add_argument("--once", action="store_true", help="Claim at most one queued job and exit.")
    args = parser.parse_args()
    run_worker(load_settings(), once=args.once)


if __name__ == "__main__":
    main()
