from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..jobs import JobRepository
from ..models import BuildJobRecord
from ..schemas import BuildJobResponse


def serialize_job(job: BuildJobRecord) -> BuildJobResponse:
    return BuildJobResponse(
        job_id=str(job.id),
        city_id=str(job.city_id),
        status=job.status,
        stage=job.stage,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        message=job.message,
        cancel_requested=job.cancel_requested_at is not None,
        error=job.error,
    )


def create_jobs_router(repository: JobRepository) -> APIRouter:
    router = APIRouter()

    @router.get("/api/jobs/{job_id}", response_model=BuildJobResponse)
    def get_job(job_id: str):
        try:
            return serialize_job(repository.get(job_id))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Build job not found") from exc

    @router.post("/api/jobs/{job_id}/cancel", response_model=BuildJobResponse, status_code=status.HTTP_202_ACCEPTED)
    def cancel_job(job_id: str):
        try:
            return serialize_job(repository.request_cancel(job_id))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Build job not found") from exc

    return router
