from __future__ import annotations

from dataclasses import dataclass
import uuid

from sqlalchemy import delete, select

from ..graph_processing import build_research_edges
from ..models import CityPaperRecord, CityRecord, CitySeedRecord, PaperEdgeRecord, PaperReferenceRecord
from ..openalex_client import OpenAlexClient, OpenAlexError
from ..repositories.postgres_city import PostgresCityRepository
from .persistence import upsert_openalex_work


@dataclass(frozen=True)
class SeedStageResult:
    resolved_count: int
    unresolved_count: int
    warnings: list[str]


def run_seed_stage(
    city_id: uuid.UUID,
    repository: PostgresCityRepository,
    client: OpenAlexClient,
) -> SeedStageResult:
    warnings: list[str] = []
    vertices = []
    resolved_openalex_ids: set[str] = set()
    with repository.session_factory.begin() as session:
        city = session.get(CityRecord, city_id)
        if city is None:
            raise KeyError(str(city_id))
        seeds = session.scalars(
            select(CitySeedRecord).where(CitySeedRecord.city_id == city_id).order_by(CitySeedRecord.position)
        ).all()
        for seed in seeds:
            try:
                resolved = client.resolve_seed(seed.raw_input)
            except OpenAlexError as exc:
                seed.resolution_status = "error"
                seed.match_type = "unresolved"
                warnings.append(f"OpenAlex lookup failed for '{seed.raw_input}': {exc}")
                continue
            seed.match_type = resolved.match_type
            if resolved.work is None:
                seed.resolution_status = "unresolved"
                warnings.append(f"No OpenAlex match for '{seed.raw_input}'.")
                continue
            paper, vertex = upsert_openalex_work(session, resolved.work, seed.position)
            session.flush([paper])
            if paper.openalex_id in resolved_openalex_ids:
                seed.resolution_status = "duplicate"
                seed.resolved_openalex_id = paper.openalex_id
                warnings.append(f"Seed '{seed.raw_input}' resolves to a paper already selected.")
                continue
            resolved_openalex_ids.add(paper.openalex_id)
            seed.resolution_status = "resolved"
            seed.resolved_openalex_id = paper.openalex_id
            seed.match_score = 1.0 if resolved.match_type in {"openalex_id", "doi"} else None
            vertex.paper_id = paper.openalex_id
            vertex.seeded = True
            vertex.seed_input = seed.raw_input
            vertex.seed_rank = seed.position
            vertex.seed_relevance = 1.0
            vertices.append(vertex)

            membership = session.get(CityPaperRecord, (city_id, paper.openalex_id))
            if membership is None:
                membership = CityPaperRecord(
                    city_id=city_id,
                    openalex_id=paper.openalex_id,
                    external_paper_id=f"S_{seed.position:04d}",
                )
                session.add(membership)
            membership.is_seed = True
            membership.seed_position = seed.position
            membership.seed_relevance = 1.0
            membership.expansion_depth = 0
            membership.expansion_source = resolved.match_type
            for referenced_id in vertex.referenced_paper_ids:
                reference = session.get(PaperReferenceRecord, (paper.openalex_id, referenced_id))
                if reference is None:
                    session.add(PaperReferenceRecord(source_openalex_id=paper.openalex_id, target_openalex_id=referenced_id))

        if not vertices:
            city.status = "failed"
            city.configuration = {**city.configuration, "seed_warnings": warnings}
            raise ValueError("None of the seed papers could be resolved through OpenAlex")

        session.execute(delete(PaperEdgeRecord).where(PaperEdgeRecord.city_id == city_id, PaperEdgeRecord.edge_type == "seed_preview"))
        for edge in build_research_edges(vertices, top_k=min(4, max(0, len(vertices) - 1)), threshold=0.45):
            session.add(
                PaperEdgeRecord(
                    city_id=city_id,
                    source_openalex_id=edge.source,
                    target_openalex_id=edge.target,
                    edge_type="seed_preview",
                    weight=edge.edge_weight,
                    components=edge.components,
                    evidence=edge.evidence,
                    directed=edge.directed_citation,
                )
            )
        city.paper_count = len(resolved_openalex_ids)
        city.configuration = {
            **city.configuration,
            "seed_warnings": warnings,
            "seed_preview_ready": True,
            "resolved_seed_count": len(resolved_openalex_ids),
        }

    unresolved_count = len([warning for warning in warnings if warning.startswith(("No OpenAlex", "OpenAlex lookup"))])
    return SeedStageResult(len(resolved_openalex_ids), unresolved_count, warnings)
