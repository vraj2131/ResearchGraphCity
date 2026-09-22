from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from .models import BuildJobRecord, CityRecord


SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|authorization|token|secret)(\s*[=:]\s*)[^\s,;]+")


class JobRepository:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def enqueue(self, city_id: uuid.UUID, stage: str = "resolve") -> BuildJobRecord:
        with self.session_factory.begin() as session:
            job = BuildJobRecord(
                city_id=city_id,
                status="queued",
                stage=stage,
                progress_current=0,
                progress_total=0,
                message="Queued",
            )
            session.add(job)
            session.flush()
            return job

    def get(self, job_id: uuid.UUID) -> BuildJobRecord:
        with self.session_factory() as session:
            job = session.get(BuildJobRecord, job_id)
            if job is None:
                raise KeyError(str(job_id))
            session.expunge(job)
            return job

    def claim_next(self, worker_id: str) -> BuildJobRecord | None:
        now = datetime.now(timezone.utc)
        with self.session_factory.begin() as session:
            job = session.scalar(
                select(BuildJobRecord)
                .where(BuildJobRecord.status == "queued", BuildJobRecord.cancel_requested_at.is_(None))
                .order_by(BuildJobRecord.created_at, BuildJobRecord.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.status = "running"
            job.locked_by = worker_id
            job.locked_at = now
            job.heartbeat_at = now
            job.started_at = job.started_at or now
            job.attempts += 1
            job.message = f"Running {job.stage}"
            session.flush()
            session.expunge(job)
            return job

    def heartbeat(self, job_id: uuid.UUID, worker_id: str) -> None:
        with self.session_factory.begin() as session:
            job = self._locked_job(session, job_id)
            if job.status != "running" or job.locked_by != worker_id:
                raise ValueError("Only the worker holding a running job can heartbeat it")
            job.heartbeat_at = datetime.now(timezone.utc)

    def update_progress(
        self,
        job_id: uuid.UUID,
        *,
        stage: str,
        current: int,
        total: int,
        message: str,
    ) -> BuildJobRecord:
        if current < 0 or total < 0 or (total and current > total):
            raise ValueError("Invalid job progress")
        with self.session_factory.begin() as session:
            job = self._locked_job(session, job_id)
            if job.status != "running":
                raise ValueError("Progress can only be updated for a running job")
            if stage != job.stage or current >= job.progress_current:
                job.stage = stage
                job.progress_current = current
                job.progress_total = total
                job.message = message
                job.heartbeat_at = datetime.now(timezone.utc)
            session.flush()
            session.expunge(job)
            return job

    def request_cancel(self, job_id: uuid.UUID) -> BuildJobRecord:
        with self.session_factory.begin() as session:
            job = self._locked_job(session, job_id)
            if job.status in {"succeeded", "failed", "cancelled"}:
                return job
            job.cancel_requested_at = datetime.now(timezone.utc)
            if job.status == "queued":
                job.status = "cancelled"
                job.stage = "cancelled"
                job.finished_at = job.cancel_requested_at
                job.message = "Build cancelled"
                city = session.get(CityRecord, job.city_id)
                if city is not None:
                    city.status = "cancelled"
            else:
                job.message = "Cancellation requested"
            session.flush()
            session.expunge(job)
            return job

    def should_cancel(self, job_id: uuid.UUID) -> bool:
        with self.session_factory() as session:
            job = session.get(BuildJobRecord, job_id)
            if job is None:
                raise KeyError(str(job_id))
            return job.cancel_requested_at is not None

    def finish(self, job_id: uuid.UUID, message: str = "Build completed") -> BuildJobRecord:
        now = datetime.now(timezone.utc)
        with self.session_factory.begin() as session:
            job = self._locked_job(session, job_id)
            job.status = "cancelled" if job.cancel_requested_at else "succeeded"
            job.stage = "cancelled" if job.cancel_requested_at else "complete"
            job.message = "Build cancelled" if job.cancel_requested_at else message
            job.finished_at = now
            job.heartbeat_at = now
            job.locked_by = None
            job.locked_at = None
            session.flush()
            session.expunge(job)
            return job

    def fail(self, job_id: uuid.UUID, error: Exception) -> BuildJobRecord:
        now = datetime.now(timezone.utc)
        with self.session_factory.begin() as session:
            job = self._locked_job(session, job_id)
            job.status = "failed"
            job.message = "Build failed"
            job.error = {"type": type(error).__name__, "message": sanitize_error(str(error))}
            job.finished_at = now
            job.heartbeat_at = now
            job.locked_by = None
            job.locked_at = None
            session.flush()
            session.expunge(job)
            return job

    def requeue_stale(self, stale_after_seconds: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
        with self.session_factory.begin() as session:
            result = session.execute(
                update(BuildJobRecord)
                .where(
                    BuildJobRecord.status == "running",
                    BuildJobRecord.heartbeat_at < cutoff,
                    BuildJobRecord.cancel_requested_at.is_(None),
                )
                .values(
                    status="queued",
                    locked_by=None,
                    locked_at=None,
                    message="Requeued after stale worker heartbeat",
                )
            )
            return int(result.rowcount or 0)

    @staticmethod
    def _locked_job(session: Session, job_id: uuid.UUID) -> BuildJobRecord:
        job = session.scalar(select(BuildJobRecord).where(BuildJobRecord.id == job_id).with_for_update())
        if job is None:
            raise KeyError(str(job_id))
        return job


def sanitize_error(message: str) -> str:
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", message)[:2_000]
