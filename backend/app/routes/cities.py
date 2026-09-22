from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from ..jobs import JobRepository
from ..repositories.postgres_city import PostgresCityRepository
from ..schemas import BuildJobResponse, CityLifecycleResponse, CreateCityRequest
from .jobs import serialize_job


def create_cities_router(repository: PostgresCityRepository, jobs: JobRepository) -> APIRouter:
    router = APIRouter()

    @router.post("/api/cities", response_model=CityLifecycleResponse, status_code=status.HTTP_201_CREATED)
    def create_city(request: CreateCityRequest):
        try:
            city, warnings = repository.create_city(
                request.name,
                request.seed_inputs,
                request.target_paper_count,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return CityLifecycleResponse(
            city_id=str(city.id),
            city_type=city.external_id,
            name=city.name,
            status=city.status,
            target_paper_count=city.target_paper_count,
            seed_count=repository.get_city_seed_count(city.id),
            warnings=warnings,
            provenance={
                "algorithm_version": city.algorithm_version,
                "embedding_model": city.embedding_model,
                "source_version": city.source_version,
                "configuration": city.configuration,
            },
        )

    @router.get("/api/cities/{city_id}", response_model=CityLifecycleResponse)
    def get_city(city_id: str):
        try:
            city = repository.get_city_record(city_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="City not found") from exc
        return CityLifecycleResponse(
            city_id=str(city.id),
            city_type=city.external_id,
            name=city.name,
            status=city.status,
            target_paper_count=city.target_paper_count,
            seed_count=repository.get_city_seed_count(city.id),
            warnings=[],
            provenance={
                "algorithm_version": city.algorithm_version,
                "embedding_model": city.embedding_model,
                "source_version": city.source_version,
                "configuration": city.configuration,
            },
        )

    @router.post("/api/cities/{city_id}/build", response_model=BuildJobResponse, status_code=status.HTTP_202_ACCEPTED)
    def queue_city_build(city_id: str):
        try:
            city = repository.get_city_record(city_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="City not found") from exc
        if city.status == "building":
            raise HTTPException(status_code=409, detail="City already has a build in progress")
        job = jobs.enqueue(city.id)
        repository.set_city_status(city.id, "building")
        return serialize_job(job)

    return router
