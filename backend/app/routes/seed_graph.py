from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select

from ..models import CityPaperRecord, CitySeedRecord, PaperEdgeRecord, PaperRecord
from ..repositories.postgres_city import PostgresCityRepository


def create_seed_graph_router(repository: PostgresCityRepository) -> APIRouter:
    router = APIRouter()

    @router.get("/api/cities/{city_id}/seed-graph")
    def seed_graph(city_id: str):
        try:
            city = repository.get_city_record(city_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="City not found") from exc
        with repository.session_factory() as session:
            memberships = session.execute(
                select(CityPaperRecord, PaperRecord)
                .join(PaperRecord, PaperRecord.openalex_id == CityPaperRecord.openalex_id)
                .where(CityPaperRecord.city_id == city.id, CityPaperRecord.is_seed.is_(True))
                .order_by(CityPaperRecord.seed_position)
            ).all()
            seed_ids = {membership.openalex_id for membership, _ in memberships}
            edges = session.scalars(
                select(PaperEdgeRecord).where(
                    PaperEdgeRecord.city_id == city.id,
                    PaperEdgeRecord.edge_type == "seed_preview",
                    or_(PaperEdgeRecord.source_openalex_id.in_(seed_ids), PaperEdgeRecord.target_openalex_id.in_(seed_ids)),
                )
            ).all()
            unresolved = session.scalars(
                select(CitySeedRecord.raw_input)
                .where(CitySeedRecord.city_id == city.id, CitySeedRecord.resolution_status.in_(("unresolved", "error")))
                .order_by(CitySeedRecord.position)
            ).all()
            return {
                "city_id": str(city.id),
                "status": city.status,
                "nodes": [
                    {
                        "paper_id": paper.openalex_id,
                        "title": paper.title,
                        "publication_year": paper.publication_year,
                        "venue": paper.venue,
                        "topics": paper.topics,
                        "seed_position": membership.seed_position,
                    }
                    for membership, paper in memberships
                ],
                "edges": [
                    {
                        "source": edge.source_openalex_id,
                        "target": edge.target_openalex_id,
                        "weight": edge.weight,
                        "directed": edge.directed,
                        "components": edge.components,
                        "evidence": edge.evidence,
                    }
                    for edge in edges
                ],
                "unresolved": list(unresolved),
                "warnings": city.configuration.get("seed_warnings", []),
            }

    return router
