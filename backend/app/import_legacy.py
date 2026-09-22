from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import ijson
from sqlalchemy import delete, select

from .models import (
    BuildingRecord,
    BuildingRelationshipRecord,
    CityPaperRecord,
    CityRecord,
    DistrictRecord,
    FloorRecord,
    PaperEdgeRecord,
    PaperEmbeddingRecord,
    PaperRecord,
)
from .repositories.postgres_city import PostgresCityRepository
from .storage import read_json


LEGACY_EMBEDDING_DIMENSIONS = 64


@dataclass(frozen=True)
class ImportCounts:
    paper_count: int
    edge_count: int
    building_count: int
    floor_count: int
    bridge_count: int
    street_count: int
    community_count: int


def iter_json_array(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open("rb") as source:
        yield from ijson.items(source, "item")


def import_legacy_city(
    processed_dir: Path,
    city_prefix: str,
    repository: PostgresCityRepository,
) -> ImportCounts:
    buildings_data = read_json(processed_dir / f"{city_prefix}_buildings.json", [])
    communities_data = read_json(processed_dir / f"{city_prefix}_communities.json", [])
    bridges_data = read_json(processed_dir / f"{city_prefix}_bridges.json", [])
    streets_data = read_json(processed_dir / f"{city_prefix}_streets.json", [])
    vertices_path = processed_dir / f"{city_prefix}_vertices.json"
    edges_path = processed_dir / f"{city_prefix}_edges.json"

    vertex_count = sum(1 for _ in iter_json_array(vertices_path))
    if vertex_count == 0:
        raise ValueError(f"No vertices found for legacy city '{city_prefix}'")

    with repository.session_factory() as session:
        existing = session.scalar(select(CityRecord).where(CityRecord.external_id == city_prefix))
        if existing is not None:
            session.delete(existing)
            session.flush()

        city = CityRecord(
            external_id=city_prefix,
            name="Research Graph City" if city_prefix == "research" else "Seeded Research Graph City",
            kind="research" if city_prefix == "research" else "seeded",
            status="ready",
            target_paper_count=max(10, min(vertex_count, 100_000)),
            paper_count=vertex_count,
            building_count=len(buildings_data),
            district_count=len(communities_data),
            algorithm_version="legacy-v1",
            embedding_model="tfidf-svd-64",
            source_version="legacy-json",
            configuration={"import_source": str(processed_dir), "prefix": city_prefix},
        )
        session.add(city)
        session.flush()

        district_by_external: dict[str, DistrictRecord] = {}
        for item in communities_data:
            district = DistrictRecord(
                city_id=city.id,
                external_id=item["community_id"],
                name=item.get("name") or item["community_id"],
                semantic_domain=item.get("semantic_domain", "general"),
                semantic_domain_name=item.get("semantic_domain_name", "General Research"),
                color=item.get("color", "#94a3b8"),
                labels=item.get("top_labels", []),
                metrics=item.get("metrics", {}),
            )
            session.add(district)
            district_by_external[district.external_id] = district
        session.flush()

        building_by_external: dict[str, BuildingRecord] = {}
        floor_by_external: dict[str, FloorRecord] = {}
        building_for_vertex: dict[str, BuildingRecord] = {}
        floor_for_vertex: dict[str, FloorRecord] = {}
        for item in buildings_data:
            community = district_by_external.get(item.get("community_id", ""))
            building = BuildingRecord(
                city_id=city.id,
                district_id=community.id if community else None,
                external_id=item["building_id"],
                node_count=int(item.get("node_count", 0)),
                edge_count=int(item.get("edge_count", 0)),
                internal_density=float(item.get("internal_density", 0.0)),
                avg_core=float(item.get("avg_core", 0.0)),
                max_core=int(item.get("max_core", 0)),
                height=float(item.get("height", 1.0)),
                footprint=float(item.get("footprint", 1.0)),
                x=float(item.get("x", 0.0)),
                z=float(item.get("z", 0.0)),
                top_labels=item.get("top_labels", []),
                semantic_domain=item.get("semantic_domain", "general"),
                semantic_domain_name=item.get("semantic_domain_name", "General Research"),
                semantic_color=item.get("semantic_color", "#94a3b8"),
                profile=item.get("profile", {}),
                original_labels=item.get("original_labels", {}),
                activation=item.get("activation", {}),
                activation_score=float(item.get("activation_score", 0.0)),
                quality_metrics=item.get("quality_metrics", {}),
                summary=item.get("summary"),
            )
            session.add(building)
            session.flush()
            building_by_external[building.external_id] = building
            for paper_id in item.get("vertex_ids", []):
                building_for_vertex[paper_id] = building
            for floor_item in item.get("floors", []):
                core_range = floor_item.get("core_range") or [0, 0]
                floor = FloorRecord(
                    city_id=city.id,
                    building_id=building.id,
                    external_id=floor_item["floor_id"],
                    floor_index=int(floor_item.get("floor_index", 1)),
                    core_min=int(core_range[0]),
                    core_max=int(core_range[-1]),
                    node_count=int(floor_item.get("node_count", 0)),
                    top_labels=floor_item.get("top_labels", []),
                    activation_score=float(floor_item.get("activation_score", 0.0)),
                    summary=floor_item.get("summary"),
                )
                session.add(floor)
                session.flush()
                floor_by_external[floor.external_id] = floor
                for paper_id in floor_item.get("vertex_ids", []):
                    floor_for_vertex[paper_id] = floor

        vertex_to_openalex: dict[str, str] = {}
        for index, item in enumerate(iter_json_array(vertices_path), start=1):
            external_id = item.get("paper_id") or f"R_{index:06d}"
            openalex_id = item.get("openalex_id") or external_id
            vertex_to_openalex[external_id] = openalex_id
            paper = session.get(PaperRecord, openalex_id)
            if paper is None:
                paper = PaperRecord(openalex_id=openalex_id, title=item.get("title") or "Untitled work")
                session.add(paper)
            _update_paper(paper, item)
            session.flush([paper])
            building = building_for_vertex.get(external_id)
            floor = floor_for_vertex.get(external_id)
            session.add(
                CityPaperRecord(
                    city_id=city.id,
                    openalex_id=openalex_id,
                    external_paper_id=external_id,
                    is_seed=bool(item.get("seeded", False)),
                    seed_position=item.get("seed_rank"),
                    seed_relevance=float(item.get("seed_relevance", 0.0)),
                    expansion_depth=0 if item.get("seeded", False) else 1,
                    expansion_source=item.get("seed_input") or "legacy",
                    building_id=building.id if building else None,
                    floor_id=floor.id if floor else None,
                )
            )
            embedding = item.get("embedding") or []
            if embedding:
                existing_embedding = session.get(PaperEmbeddingRecord, (openalex_id, "tfidf-svd-64"))
                if existing_embedding is None:
                    normalized_embedding = _normalize_legacy_embedding(embedding)
                    session.add(
                        PaperEmbeddingRecord(
                            openalex_id=openalex_id,
                            model="tfidf-svd-64",
                            dimensions=LEGACY_EMBEDDING_DIMENSIONS,
                            embedding=normalized_embedding,
                        )
                    )
            if index % 2_000 == 0:
                session.flush()

        edge_count = 0
        for edge_count, item in enumerate(iter_json_array(edges_path), start=1):
            source = vertex_to_openalex.get(item.get("source", ""))
            target = vertex_to_openalex.get(item.get("target", ""))
            if not source or not target:
                continue
            session.add(
                PaperEdgeRecord(
                    city_id=city.id,
                    source_openalex_id=source,
                    target_openalex_id=target,
                    edge_type=item.get("edge_type", "mixed"),
                    weight=float(item.get("edge_weight", 0.0)),
                    components=_json_compatible(item.get("components", {})),
                    evidence=_json_compatible(item.get("evidence", [])),
                    directed=bool(item.get("directed_citation", False)),
                )
            )
            if edge_count % 2_000 == 0:
                session.flush()

        for kind, relationships in (("bridge", bridges_data), ("street", streets_data)):
            for item in relationships:
                source = building_by_external[item["source_building_id"]]
                target = building_by_external[item["target_building_id"]]
                if kind == "bridge":
                    external_id = item["bridge_id"]
                    score = item.get("bridge_strength", 0.0)
                    relationship_type = item.get("bridge_type", "research")
                    distance = 0.0
                else:
                    external_id = item["street_id"]
                    score = item.get("street_score", 0.0)
                    relationship_type = item.get("street_type", "research_backbone")
                    distance = item.get("distance", 0.0)
                session.add(
                    BuildingRelationshipRecord(
                        city_id=city.id,
                        external_id=external_id,
                        source_building_id=source.id,
                        target_building_id=target.id,
                        relationship_kind=kind,
                        relationship_type=relationship_type,
                        score=float(score),
                        distance=float(distance),
                        components=item.get("components", {}),
                        evidence=item.get("evidence", []),
                        activation_score=float(item.get("activation_score", 0.0)),
                        summary=item.get("summary"),
                    )
                )

        city.edge_count = edge_count
        session.commit()

    return ImportCounts(
        paper_count=vertex_count,
        edge_count=edge_count,
        building_count=len(buildings_data),
        floor_count=len(floor_by_external),
        bridge_count=len(bridges_data),
        street_count=len(streets_data),
        community_count=len(communities_data),
    )


def _normalize_legacy_embedding(embedding: list[float]) -> list[float]:
    """Fit historical JSON vectors to the fixed pgvector column dimension."""
    values = [float(value) for value in embedding[:LEGACY_EMBEDDING_DIMENSIONS]]
    return values + [0.0] * (LEGACY_EMBEDDING_DIMENSIONS - len(values))


def _update_paper(paper: PaperRecord, item: dict) -> None:
    paper.doi = item.get("doi")
    paper.title = item.get("title") or "Untitled work"
    paper.abstract = item.get("abstract", "")
    paper.publication_year = item.get("publication_year")
    paper.venue = item.get("venue", "")
    paper.publisher = item.get("publisher", "")
    paper.citation_count = int(item.get("citation_count", 0))
    paper.open_access = bool(item.get("open_access", False))
    paper.code_available = bool(item.get("code_available", False))
    paper.data_available = bool(item.get("data_available", False))
    paper.authors = item.get("authors", [])
    paper.author_ids = item.get("author_ids", [])
    paper.institutions = item.get("institutions", [])
    paper.institution_ids = item.get("institution_ids", [])
    paper.topics = item.get("topics", [])
    paper.keywords = item.get("keywords", [])
    paper.methods = item.get("methods", [])
    paper.datasets = item.get("datasets", [])
    paper.metadata_json = {"legacy_paper_id": item.get("paper_id")}


def _json_compatible(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    return value
