from __future__ import annotations

from collections import defaultdict
import re
from typing import Any
import uuid

from sqlalchemy import Integer, Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased, sessionmaker

from ..models import (
    AnswerCitationRecord,
    AssistantConversationRecord,
    AssistantMessageRecord,
    BuildingRecord,
    BuildingPaperRecord,
    BuildingRelationshipRecord,
    CityPaperRecord,
    CityRecord,
    CitySeedRecord,
    DistrictRecord,
    FloorRecord,
    FloorPaperRecord,
    DecompositionEdgeRecord,
    PaperEdgeRecord,
    PaperEmbeddingRecord,
    PaperRecord,
)


class PostgresCityRepository:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def list_cities(self) -> list[dict]:
        with self.session_factory() as session:
            cities = session.scalars(select(CityRecord).order_by(CityRecord.created_at)).all()
            return [
                {"city_type": city.external_id, "name": city.name, "status": city.status, "city_id": str(city.id)}
                for city in cities
            ]

    def create_city(self, name: str, seed_inputs: list[str], target_paper_count: int) -> tuple[CityRecord, list[str]]:
        unique_inputs: list[str] = []
        seen: set[str] = set()
        duplicate_count = 0
        for seed_input in seed_inputs:
            normalized = " ".join(seed_input.split()).casefold()
            if normalized in seen:
                duplicate_count += 1
                continue
            seen.add(normalized)
            unique_inputs.append(seed_input.strip())
        if not unique_inputs:
            raise ValueError("At least one unique seed input is required")

        city_uuid = uuid.uuid4()
        with self.session_factory.begin() as session:
            city = CityRecord(
                id=city_uuid,
                external_id=f"seeded-{city_uuid.hex[:12]}",
                name=name,
                kind="seeded",
                status="draft",
                target_paper_count=target_paper_count,
                configuration={"seed_input_count": len(unique_inputs)},
                algorithm_version="platform-v1",
                embedding_model="hashing-64-v1",
            )
            session.add(city)
            session.flush()
            session.add_all(
                [
                    CitySeedRecord(city_id=city.id, position=index, raw_input=value)
                    for index, value in enumerate(unique_inputs, start=1)
                ]
            )
            session.flush()
            session.expunge(city)
        warnings = [f"Removed {duplicate_count} duplicate seed input."] if duplicate_count == 1 else []
        if duplicate_count > 1:
            warnings = [f"Removed {duplicate_count} duplicate seed inputs."]
        return city, warnings

    def get_city_record(self, identifier: str) -> CityRecord:
        with self.session_factory() as session:
            try:
                city_uuid = uuid.UUID(identifier)
            except ValueError:
                city_uuid = None
            query = select(CityRecord).where(
                CityRecord.id == city_uuid if city_uuid else CityRecord.external_id == identifier
            )
            city = session.scalar(query)
            if city is None:
                raise KeyError(identifier)
            session.expunge(city)
            return city

    def get_city_seed_count(self, city_id: uuid.UUID) -> int:
        with self.session_factory() as session:
            return len(session.scalars(select(CitySeedRecord).where(CitySeedRecord.city_id == city_id)).all())

    def set_city_status(self, city_id: uuid.UUID, status: str) -> None:
        with self.session_factory.begin() as session:
            city = session.get(CityRecord, city_id)
            if city is None:
                raise KeyError(str(city_id))
            city.status = status

    def read_collection(self, city_id: str, suffix: str) -> list[dict]:
        if suffix in {"buildings", "bridges", "streets", "communities"}:
            return self.get_scene(city_id)[suffix]
        if suffix == "vertices":
            return self._city_papers(city_id)
        if suffix == "edges":
            return self._city_edges(city_id)
        if suffix == "floors":
            return [floor for building in self.get_scene(city_id)["buildings"] for floor in building["floors"]]
        raise KeyError(suffix)

    def get_scene(self, city_id: str) -> dict[str, list[dict]]:
        with self.session_factory() as session:
            city = self._city(session, city_id)
            buildings = session.scalars(
                select(BuildingRecord).where(BuildingRecord.city_id == city.id).order_by(BuildingRecord.external_id)
            ).all()
            floor_query = select(FloorRecord).where(FloorRecord.city_id == city.id)
            if city.algorithm_version.startswith('graph-cities'):
                ranked = select(
                    FloorRecord.id,
                    func.row_number().over(partition_by=FloorRecord.building_id, order_by=FloorRecord.floor_index).label('position'),
                    func.count().over(partition_by=FloorRecord.building_id).label('total'),
                ).where(FloorRecord.city_id == city.id).subquery()
                step = func.cast(func.greatest(1, func.ceil((ranked.c.total - 1) / 63.0)), Integer)
                floor_query = floor_query.join(ranked, ranked.c.id == FloorRecord.id).where(or_(
                    ranked.c.position == ranked.c.total,
                    (ranked.c.position - 1) % step == 0,
                ))
            floors = session.scalars(floor_query.order_by(FloorRecord.building_id, FloorRecord.floor_index)).all()
            districts = session.scalars(
                select(DistrictRecord).where(DistrictRecord.city_id == city.id).order_by(DistrictRecord.external_id)
            ).all()
            relationships = session.scalars(
                select(BuildingRelationshipRecord)
                .where(BuildingRelationshipRecord.city_id == city.id)
                .order_by(BuildingRelationshipRecord.external_id)
            ).all()

            district_external = {item.id: item.external_id for item in districts}
            building_external = {item.id: item.external_id for item in buildings}
            floors_by_building: dict[uuid.UUID, list[dict]] = defaultdict(list)
            for floor in floors:
                floors_by_building[floor.building_id].append(self._serialize_floor(floor, []))

            building_payload = [
                self._serialize_building(
                    city.external_id,
                    building,
                    [],
                    floors_by_building[building.id],
                    district_external.get(building.district_id),
                )
                for building in buildings
            ]
            bridges = [
                self._serialize_relationship(city.external_id, item, building_external)
                for item in relationships
                if item.relationship_kind == "bridge"
            ]
            streets = [
                self._serialize_relationship(city.external_id, item, building_external)
                for item in relationships
                if item.relationship_kind == "street"
            ]
            communities = [
                {
                    "community_id": district.external_id,
                    "city_type": city.external_id,
                    "name": district.name,
                    "building_ids": [building_external[item.id] for item in buildings if item.district_id == district.id],
                    "top_labels": district.labels,
                    "semantic_domain": district.semantic_domain,
                    "semantic_domain_name": district.semantic_domain_name,
                    "metrics": district.metrics,
                    "summary": None,
                    "color": district.color,
                }
                for district in districts
            ]
            return {"buildings": building_payload, "bridges": bridges, "streets": streets, "communities": communities}

    def get_building(self, city_id: str, building_id: str) -> dict | None:
        return next((item for item in self.get_scene(city_id)["buildings"] if item["building_id"] == building_id), None)

    def get_building_floors(self, city_id: str, building_id: str, limit: int = 100, cursor: int = 0) -> list[dict]:
        with self.session_factory() as session:
            city = self._city(session, city_id)
            building = session.scalar(select(BuildingRecord).where(
                BuildingRecord.city_id == city.id, BuildingRecord.external_id == building_id))
            if building is None:
                raise KeyError(building_id)
            floors = session.scalars(select(FloorRecord).where(
                FloorRecord.city_id == city.id, FloorRecord.building_id == building.id,
                FloorRecord.floor_index > max(0, cursor),
            ).order_by(FloorRecord.floor_index).limit(max(1, min(limit, 500)))).all()
            return [{**self._serialize_floor(floor, []), 'building_id': building.external_id} for floor in floors]

    def get_bridge(self, city_id: str, bridge_id: str) -> dict | None:
        return next((item for item in self.get_scene(city_id)["bridges"] if item["bridge_id"] == bridge_id), None)

    def get_street(self, city_id: str, street_id: str) -> dict | None:
        return next((item for item in self.get_scene(city_id)["streets"] if item["street_id"] == street_id), None)

    def get_building_papers(
        self, city_id: str, building_id: str, floor_id: str | None = None, limit: int = 200, cursor: str | None = None
    ) -> list[dict]:
        with self.session_factory() as session:
            city = self._city(session, city_id)
            building = self._building(session, city.id, building_id)
            query = (
                select(CityPaperRecord, PaperRecord)
                .join(PaperRecord, PaperRecord.openalex_id == CityPaperRecord.openalex_id)
                .where(CityPaperRecord.city_id == city.id)
            )
            if city.algorithm_version.startswith("graph-cities"):
                query = query.where(CityPaperRecord.openalex_id.in_(self._member_ids(city, building.id)))
            else:
                query = query.where(CityPaperRecord.building_id == building.id)
            if floor_id:
                floor = session.scalar(
                    select(FloorRecord).where(FloorRecord.building_id == building.id, FloorRecord.external_id == floor_id)
                )
                if floor is None:
                    raise KeyError(floor_id)
                if city.algorithm_version.startswith("graph-cities"):
                    query = query.where(CityPaperRecord.openalex_id.in_(self._member_ids(city, building.id, floor.id)))
                else:
                    query = query.where(CityPaperRecord.floor_id == floor.id)
            if cursor:
                query = query.where(CityPaperRecord.external_paper_id > cursor)
            rows = session.execute(query.order_by(CityPaperRecord.external_paper_id).limit(self._limit(limit))).all()
            result = [self._serialize_paper(membership, paper) for membership, paper in rows]
            self._attach_locations(session, city, result, building_id)
            return result

    def get_building_edges(
        self, city_id: str, building_id: str, floor_id: str | None = None, limit: int = 200, cursor: str | None = None
    ) -> list[dict]:
        with self.session_factory() as session:
            city = self._city(session, city_id)
            building = self._building(session, city.id, building_id)
            if city.algorithm_version.startswith("graph-cities"):
                owned = select(DecompositionEdgeRecord).where(
                    DecompositionEdgeRecord.city_id == city.id,
                    DecompositionEdgeRecord.building_id == building.id,
                )
                if floor_id:
                    floor = session.scalar(select(FloorRecord).where(FloorRecord.building_id == building.id, FloorRecord.external_id == floor_id))
                    if floor is None:
                        raise KeyError(floor_id)
                    owned = owned.where(DecompositionEdgeRecord.floor_id == floor.id)
                ownership = owned.subquery()
                query = select(PaperEdgeRecord).where(
                    PaperEdgeRecord.city_id == city.id,
                    select(ownership.c.city_id).where(or_(
                        and_(ownership.c.source_openalex_id == PaperEdgeRecord.source_openalex_id,
                             ownership.c.target_openalex_id == PaperEdgeRecord.target_openalex_id),
                        and_(ownership.c.target_openalex_id == PaperEdgeRecord.source_openalex_id,
                             ownership.c.source_openalex_id == PaperEdgeRecord.target_openalex_id),
                    )).exists(),
                )
                # A citation baseline retains citation evidence only; similarity
                # remains a separate overlay, even for the same endpoint pair.
                if city.configuration.get("graph_input", "citation") == "citation":
                    query = query.where(PaperEdgeRecord.edge_type == "citation")
                return self._serialize_edges(session, city.id, query, limit, cursor)
            member_query = select(CityPaperRecord.openalex_id).where(
                CityPaperRecord.city_id == city.id, CityPaperRecord.building_id == building.id
            )
            if floor_id:
                floor = session.scalar(
                    select(FloorRecord).where(FloorRecord.building_id == building.id, FloorRecord.external_id == floor_id)
                )
                if floor is None:
                    raise KeyError(floor_id)
                member_query = member_query.where(CityPaperRecord.floor_id == floor.id)
            query = select(PaperEdgeRecord).where(
                PaperEdgeRecord.city_id == city.id,
                PaperEdgeRecord.source_openalex_id.in_(member_query),
                PaperEdgeRecord.target_openalex_id.in_(member_query),
            )
            return self._serialize_edges(session, city.id, query, limit, cursor)

    def get_bridge_edges(self, city_id: str, bridge_id: str, limit: int = 200, cursor: str | None = None) -> list[dict]:
        with self.session_factory() as session:
            city = self._city(session, city_id)
            relationship = session.scalar(
                select(BuildingRelationshipRecord).where(
                    BuildingRelationshipRecord.city_id == city.id,
                    BuildingRelationshipRecord.external_id == bridge_id,
                    BuildingRelationshipRecord.relationship_kind == "bridge",
                )
            )
            if relationship is None:
                raise KeyError(bridge_id)
            source_ids = self._member_ids(city, relationship.source_building_id)
            target_ids = self._member_ids(city, relationship.target_building_id)
            query = select(PaperEdgeRecord).where(
                PaperEdgeRecord.city_id == city.id,
                or_(
                    and_(
                        PaperEdgeRecord.source_openalex_id.in_(source_ids),
                        PaperEdgeRecord.target_openalex_id.in_(target_ids),
                    ),
                    and_(
                        PaperEdgeRecord.source_openalex_id.in_(target_ids),
                        PaperEdgeRecord.target_openalex_id.in_(source_ids),
                    ),
                ),
            )
            return self._serialize_edges(session, city.id, query, limit, cursor)

    def search_papers(
        self,
        city_id: str,
        query_text: str,
        query_embedding: list[float] | None = None,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        filters = filters or {}
        result_limit = max(1, min(limit, 50))
        candidate_limit = min(max(result_limit * 4, 40), 200)
        with self.session_factory() as session:
            city = self._city(session, city_id)
            fallback_document = func.to_tsvector(
                "english",
                func.concat_ws(" ", PaperRecord.title, PaperRecord.abstract, PaperRecord.venue),
            )
            lexical_tokens = re.findall(r"[A-Za-z0-9]+", query_text)
            ts_query = func.websearch_to_tsquery("english", " OR ".join(lexical_tokens) or query_text)
            lexical_rank = func.coalesce(
                func.ts_rank_cd(PaperRecord.search_vector, ts_query),
                func.ts_rank_cd(fallback_document, ts_query),
            ).label("lexical_rank")
            base = (
                select(CityPaperRecord, PaperRecord, BuildingRecord, DistrictRecord)
                .join(PaperRecord, PaperRecord.openalex_id == CityPaperRecord.openalex_id)
                .outerjoin(BuildingRecord, BuildingRecord.id == CityPaperRecord.building_id)
                .outerjoin(DistrictRecord, DistrictRecord.id == BuildingRecord.district_id)
                .where(CityPaperRecord.city_id == city.id)
            )
            effective_filters = dict(filters)
            if city.algorithm_version.startswith("graph-cities"):
                member_building = aliased(BuildingRecord)
                member_district = aliased(DistrictRecord)
                locations = (select(BuildingPaperRecord.openalex_id)
                    .join(member_building, member_building.id == BuildingPaperRecord.building_id)
                    .outerjoin(member_district, member_district.id == member_building.district_id)
                    .where(BuildingPaperRecord.city_id == city.id,
                           BuildingPaperRecord.openalex_id == CityPaperRecord.openalex_id)
                    .correlate(CityPaperRecord))
                scoped = False
                for key, column in (("building_id", member_building.external_id), ("district_id", member_district.external_id), ("domain", member_building.semantic_domain)):
                    if effective_filters.get(key):
                        locations = locations.where(column == str(effective_filters.pop(key)))
                        scoped = True
                if scoped:
                    base = base.where(locations.exists())
            base = self._apply_paper_filters(base, effective_filters)
            lexical_rows = session.execute(
                base.add_columns(lexical_rank)
                .where(
                    or_(
                        PaperRecord.search_vector.op("@@")(ts_query),
                        and_(PaperRecord.search_vector.is_(None), fallback_document.op("@@")(ts_query)),
                    )
                )
                .order_by(lexical_rank.desc(), PaperRecord.citation_count.desc())
                .limit(candidate_limit)
            ).all()

            candidates: dict[str, dict[str, Any]] = {}
            query_terms = {term.casefold() for term in lexical_tokens}
            for membership, paper, building, district, lexical in lexical_rows:
                item = self._search_result(membership, paper, building, district)
                primary_text = " ".join(
                    [paper.title, paper.venue, *paper.topics, *paper.keywords, *paper.methods, *paper.datasets]
                ).casefold()
                primary_overlap = sum(term in primary_text for term in query_terms) / max(len(query_terms), 1)
                abstract_overlap = sum(term in paper.abstract.casefold() for term in query_terms) / max(len(query_terms), 1)
                rank_score = min(float(lexical or 0.0) / 0.1, 1.0)
                item["lexical_score"] = max(rank_score, primary_overlap, 0.25 * abstract_overlap)
                item["semantic_score"] = 0.0
                candidates[paper.openalex_id] = item

            if query_embedding:
                distance = PaperEmbeddingRecord.embedding.cosine_distance(query_embedding).label("distance")
                semantic_rows = session.execute(
                    base.join(
                        PaperEmbeddingRecord,
                        PaperEmbeddingRecord.openalex_id == PaperRecord.openalex_id,
                    )
                    .add_columns(distance)
                    .where(PaperEmbeddingRecord.model == "hashing-64-v1")
                    .order_by(distance)
                    .limit(candidate_limit)
                ).all()
                for membership, paper, building, district, raw_distance in semantic_rows:
                    item = candidates.setdefault(
                        paper.openalex_id,
                        self._search_result(membership, paper, building, district),
                    )
                    item.setdefault("lexical_score", 0.0)
                    item["semantic_score"] = max(0.0, min(1.0 - float(raw_distance or 0.0), 1.0))

            for item in candidates.values():
                quality = min(1.0, float(item["citation_count"]) / 100.0)
                item["score"] = round(
                    0.60 * item.get("lexical_score", 0.0)
                    + 0.30 * item.get("semantic_score", 0.0)
                    + 0.10 * quality,
                    4,
                )
            result = sorted(
                candidates.values(),
                key=lambda item: (-item["score"], -item["citation_count"], item["openalex_id"]),
            )[:result_limit]
            self._attach_locations(session, city, result, filters.get("building_id"))
            return result

    def get_paper(self, city_id: str, paper_id: str) -> dict | None:
        with self.session_factory() as session:
            city = self._city(session, city_id)
            row = session.execute(
                select(CityPaperRecord, PaperRecord, BuildingRecord, DistrictRecord)
                .join(PaperRecord, PaperRecord.openalex_id == CityPaperRecord.openalex_id)
                .outerjoin(BuildingRecord, BuildingRecord.id == CityPaperRecord.building_id)
                .outerjoin(DistrictRecord, DistrictRecord.id == BuildingRecord.district_id)
                .where(
                    CityPaperRecord.city_id == city.id,
                    or_(
                        CityPaperRecord.external_paper_id == paper_id,
                        CityPaperRecord.openalex_id == paper_id,
                    ),
                )
                .limit(1)
            ).first()
            if row is None:
                return None
            result = self._search_result(*row)
            self._attach_locations(session, city, [result])
            return result

    def relationships_for_buildings(self, city_id: str, building_ids: list[str], limit: int = 12) -> list[dict]:
        if len(building_ids) < 2:
            return []
        with self.session_factory() as session:
            city = self._city(session, city_id)
            buildings = session.scalars(
                select(BuildingRecord).where(
                    BuildingRecord.city_id == city.id,
                    BuildingRecord.external_id.in_(building_ids),
                )
            ).all()
            ids = [item.id for item in buildings]
            external = {item.id: item.external_id for item in buildings}
            relationships = session.scalars(
                select(BuildingRelationshipRecord)
                .where(
                    BuildingRelationshipRecord.city_id == city.id,
                    BuildingRelationshipRecord.source_building_id.in_(ids),
                    BuildingRelationshipRecord.target_building_id.in_(ids),
                    BuildingRelationshipRecord.relationship_type != "graph_city_geometry",
                )
                .order_by(BuildingRelationshipRecord.score.desc())
                .limit(max(1, min(limit, 30)))
            ).all()
            return [
                {
                    "evidence_id": f"relationship:{item.external_id}",
                    "relationship_id": item.external_id,
                    "relationship_kind": item.relationship_kind,
                    "relationship_type": item.relationship_type,
                    "source_building_id": external[item.source_building_id],
                    "target_building_id": external[item.target_building_id],
                    "score": round(item.score, 4),
                    "components": item.components,
                    "evidence": item.evidence[:8],
                }
                for item in relationships
            ]

    def get_timeline(self, city_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            city = self._city(session, city_id)
            rows = session.execute(
                select(
                    PaperRecord.publication_year,
                    func.count().label("paper_count"),
                    func.sum(PaperRecord.citation_count).label("citation_count"),
                    func.sum(func.cast(PaperRecord.open_access, Integer)).label("open_access_count"),
                    func.count(func.distinct(CityPaperRecord.building_id)).label("building_count"),
                )
                .join(CityPaperRecord, CityPaperRecord.openalex_id == PaperRecord.openalex_id)
                .where(CityPaperRecord.city_id == city.id, PaperRecord.publication_year.is_not(None))
                .group_by(PaperRecord.publication_year)
                .order_by(PaperRecord.publication_year)
            ).all()
            years = [
                {
                    "year": int(year),
                    "paper_count": int(paper_count),
                    "citation_count": int(citation_count or 0),
                    "open_access_count": int(open_access_count or 0),
                    "building_count": int(building_count or 0),
                }
                for year, paper_count, citation_count, open_access_count, building_count in rows
            ]
            if city.algorithm_version.startswith("graph-cities"):
                building_counts = dict(session.execute(
                    select(PaperRecord.publication_year, func.count(func.distinct(BuildingPaperRecord.building_id)))
                    .join(BuildingPaperRecord, BuildingPaperRecord.openalex_id == PaperRecord.openalex_id)
                    .where(BuildingPaperRecord.city_id == city.id, PaperRecord.publication_year.is_not(None))
                    .group_by(PaperRecord.publication_year)
                ).all())
                for year in years:
                    year["building_count"] = int(building_counts.get(year["year"], 0))
            return {
                "city_id": city.external_id,
                "year_min": years[0]["year"] if years else None,
                "year_max": years[-1]["year"] if years else None,
                "years": years,
            }

    def compare_cities(self, left_city_id: str, right_city_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            left = self._city(session, left_city_id)
            right = self._city(session, right_city_id)
            left_ids = select(CityPaperRecord.openalex_id).where(CityPaperRecord.city_id == left.id)
            right_ids = select(CityPaperRecord.openalex_id).where(CityPaperRecord.city_id == right.id)
            left_count = int(session.scalar(select(func.count()).select_from(left_ids.subquery())) or 0)
            right_count = int(session.scalar(select(func.count()).select_from(right_ids.subquery())) or 0)
            shared_count = int(
                session.scalar(
                    select(func.count()).select_from(left_ids.where(CityPaperRecord.openalex_id.in_(right_ids)).subquery())
                )
                or 0
            )

            def domains(city_uuid: uuid.UUID) -> dict[str, str]:
                rows = session.execute(
                    select(BuildingRecord.semantic_domain, BuildingRecord.semantic_domain_name)
                    .where(BuildingRecord.city_id == city_uuid)
                    .distinct()
                ).all()
                return {key: name for key, name in rows}

            left_domains = domains(left.id)
            right_domains = domains(right.id)
            shared_domain_keys = sorted(set(left_domains) & set(right_domains))
            return {
                "left_city": {"city_id": left.external_id, "name": left.name, "paper_count": left_count},
                "right_city": {"city_id": right.external_id, "name": right.name, "paper_count": right_count},
                "papers": {
                    "shared": shared_count,
                    "left_only": left_count - shared_count,
                    "right_only": right_count - shared_count,
                },
                "domains": {
                    "shared": [left_domains[key] for key in shared_domain_keys],
                    "left_only": [left_domains[key] for key in sorted(set(left_domains) - set(right_domains))],
                    "right_only": [right_domains[key] for key in sorted(set(right_domains) - set(left_domains))],
                },
            }

    def save_assistant_exchange(
        self,
        city_id: str,
        question: str,
        response: Any,
        evidence_packet: dict[str, Any],
        model: str | None,
    ) -> str:
        evidence_by_id = {
            item["evidence_id"]: item
            for collection in ("papers", "buildings", "districts", "relationships", "timeline")
            for item in evidence_packet.get(collection, [])
            if item.get("evidence_id")
        }
        with self.session_factory.begin() as session:
            city = self._city(session, city_id)
            conversation = AssistantConversationRecord(city_id=city.id)
            session.add(conversation)
            session.flush([conversation])
            session.add(
                AssistantMessageRecord(
                    conversation_id=conversation.id,
                    role="user",
                    content=question,
                    structured_content={"filters": evidence_packet.get("filters_applied", {})},
                )
            )
            assistant_message = AssistantMessageRecord(
                conversation_id=conversation.id,
                role="assistant",
                content=response.answer_markdown,
                structured_content=response.model_dump(mode="json", exclude={"conversation_id"}),
                model=model,
            )
            session.add(assistant_message)
            session.flush([assistant_message])
            for claim_index, claim in enumerate(response.claims):
                for citation_id in claim.citation_ids:
                    entity_type, _, entity_id = citation_id.partition(":")
                    session.add(
                        AnswerCitationRecord(
                            message_id=assistant_message.id,
                            entity_type=entity_type,
                            entity_id=entity_id,
                            claim_index=claim_index,
                            support_score=claim.support_score,
                            evidence=evidence_by_id.get(citation_id, {}),
                        )
                    )
            return str(conversation.id)

    def _city_papers(self, city_id: str) -> list[dict]:
        with self.session_factory() as session:
            city = self._city(session, city_id)
            rows = session.execute(
                select(CityPaperRecord, PaperRecord)
                .join(PaperRecord, PaperRecord.openalex_id == CityPaperRecord.openalex_id)
                .where(CityPaperRecord.city_id == city.id)
                .order_by(CityPaperRecord.external_paper_id)
            ).limit(200).all()
            return [self._serialize_paper(membership, paper) for membership, paper in rows]

    def _city_edges(self, city_id: str) -> list[dict]:
        with self.session_factory() as session:
            city = self._city(session, city_id)
            return self._serialize_edges(session, city.id, select(PaperEdgeRecord).where(PaperEdgeRecord.city_id == city.id), 200, None)

    @staticmethod
    def _member_ids(city, building_id, floor_id=None):
        if city.algorithm_version.startswith("graph-cities"):
            if floor_id is not None:
                return select(FloorPaperRecord.openalex_id).where(
                    FloorPaperRecord.city_id == city.id, FloorPaperRecord.building_id == building_id,
                    FloorPaperRecord.floor_id == floor_id,
                )
            return select(BuildingPaperRecord.openalex_id).where(
                BuildingPaperRecord.city_id == city.id, BuildingPaperRecord.building_id == building_id,
            )
        query = select(CityPaperRecord.openalex_id).where(
            CityPaperRecord.city_id == city.id, CityPaperRecord.building_id == building_id,
        )
        return query.where(CityPaperRecord.floor_id == floor_id) if floor_id is not None else query

    @staticmethod
    def _attach_locations(session, city, results, preferred_building=None):
        if not results or not city.algorithm_version.startswith("graph-cities"):
            return
        ids = [item["openalex_id"] for item in results]
        rows = session.execute(
            select(BuildingPaperRecord, BuildingRecord, DistrictRecord, FloorRecord)
            .join(BuildingRecord, BuildingRecord.id == BuildingPaperRecord.building_id)
            .outerjoin(DistrictRecord, DistrictRecord.id == BuildingRecord.district_id)
            .outerjoin(FloorRecord, FloorRecord.id == BuildingPaperRecord.floor_id)
            .where(BuildingPaperRecord.city_id == city.id, BuildingPaperRecord.openalex_id.in_(ids))
            .order_by(BuildingRecord.external_id)
        ).all()
        floor_rows = session.execute(
            select(FloorPaperRecord.openalex_id, FloorPaperRecord.building_id, FloorRecord)
            .join(FloorRecord, FloorRecord.id == FloorPaperRecord.floor_id)
            .where(FloorPaperRecord.city_id == city.id, FloorPaperRecord.openalex_id.in_(ids))
            .order_by(FloorRecord.floor_index)
        ).all()
        floors = defaultdict(list)
        for paper_id, building_id, floor in floor_rows:
            floors[(paper_id, building_id)].append({"floor_id": floor.external_id, "floor_index": floor.floor_index, "summary": floor.summary})
        locations = defaultdict(list)
        for membership, building, district, primary_floor in rows:
            locations[membership.openalex_id].append({
                "building_id": building.external_id,
                "building_label": building.top_labels[0] if building.top_labels else building.external_id,
                "district_id": district.external_id if district else None,
                "district_name": district.name if district else None,
                "domain_name": building.semantic_domain_name,
                "floor_id": primary_floor.external_id if primary_floor else None,
                "floors": floors[(membership.openalex_id, building.id)],
            })
        for item in results:
            item["locations"] = locations[item["openalex_id"]]
            preferred = preferred_building or item.get("building_id")
            chosen = next((location for location in item["locations"] if location["building_id"] == preferred), None)
            if chosen is None and item["locations"]:
                chosen = item["locations"][0]
            if chosen:
                item.update({key: value for key, value in chosen.items() if key != "floors"})
                item["floor_ids"] = [floor["floor_id"] for floor in chosen["floors"]]

    @staticmethod
    def _apply_paper_filters(query: Select[Any], filters: dict[str, Any]) -> Select[Any]:
        if filters.get("year_min") is not None:
            query = query.where(PaperRecord.publication_year >= int(filters["year_min"]))
        if filters.get("year_max") is not None:
            query = query.where(PaperRecord.publication_year <= int(filters["year_max"]))
        if filters.get("building_id"):
            query = query.where(BuildingRecord.external_id == str(filters["building_id"]))
        if filters.get("district_id"):
            query = query.where(DistrictRecord.external_id == str(filters["district_id"]))
        if filters.get("domain"):
            query = query.where(BuildingRecord.semantic_domain == str(filters["domain"]))
        if filters.get("venue"):
            query = query.where(PaperRecord.venue.ilike(f"%{filters['venue']}%"))
        for key, column in (
            ("author", PaperRecord.authors),
            ("institution", PaperRecord.institutions),
            ("topic", PaperRecord.topics),
            ("method", PaperRecord.methods),
            ("dataset", PaperRecord.datasets),
        ):
            if filters.get(key):
                query = query.where(column.contains([str(filters[key])]))
        for key, column in (
            ("open_access", PaperRecord.open_access),
            ("code_available", PaperRecord.code_available),
            ("data_available", PaperRecord.data_available),
        ):
            if filters.get(key) is not None:
                query = query.where(column == bool(filters[key]))
        return query

    @classmethod
    def _search_result(cls, membership, paper, building, district) -> dict[str, Any]:
        result = cls._serialize_paper(membership, paper)
        result.update(
            {
                "evidence_id": f"paper:{paper.openalex_id}",
                "building_id": building.external_id if building else None,
                "building_label": building.top_labels[0] if building and building.top_labels else None,
                "district_id": district.external_id if district else None,
                "district_name": district.name if district else None,
                "domain_name": building.semantic_domain_name if building else None,
            }
        )
        return result

    def _serialize_edges(
        self, session: Session, city_id: uuid.UUID, query: Select[Any], limit: int, cursor: str | None
    ) -> list[dict]:
        if cursor:
            source_cursor, _, remaining_cursor = cursor.partition(":")
            target_cursor, type_separator, type_cursor = remaining_cursor.partition(":")
            cursor_memberships = session.scalars(
                select(CityPaperRecord).where(
                    CityPaperRecord.city_id == city_id,
                    CityPaperRecord.external_paper_id.in_([source_cursor, target_cursor]),
                )
            ).all()
            canonical_by_external = {item.external_paper_id: item.openalex_id for item in cursor_memberships}
            source_openalex = canonical_by_external.get(source_cursor, source_cursor)
            target_openalex = canonical_by_external.get(target_cursor, target_cursor)
            query = query.where(
                or_(
                    PaperEdgeRecord.source_openalex_id > source_openalex,
                    and_(PaperEdgeRecord.source_openalex_id == source_openalex, PaperEdgeRecord.target_openalex_id > target_openalex),
                    and_(PaperEdgeRecord.source_openalex_id == source_openalex,
                         PaperEdgeRecord.target_openalex_id == target_openalex,
                         PaperEdgeRecord.edge_type > type_cursor) if type_separator else False,
                )
            )
        edges = session.scalars(
            query.order_by(PaperEdgeRecord.source_openalex_id, PaperEdgeRecord.target_openalex_id, PaperEdgeRecord.edge_type).limit(self._limit(limit))
        ).all()
        endpoint_ids = {item for edge in edges for item in (edge.source_openalex_id, edge.target_openalex_id)}
        memberships = session.scalars(
            select(CityPaperRecord).where(
                CityPaperRecord.city_id == city_id,
                CityPaperRecord.openalex_id.in_(endpoint_ids),
            )
        ).all()
        external_by_openalex = {item.openalex_id: item.external_paper_id for item in memberships}
        papers = session.scalars(select(PaperRecord).where(PaperRecord.openalex_id.in_(endpoint_ids))).all()
        paper_by_id = {item.openalex_id: item for item in papers}
        result = []
        for edge in edges:
            source = external_by_openalex.get(edge.source_openalex_id, edge.source_openalex_id)
            target = external_by_openalex.get(edge.target_openalex_id, edge.target_openalex_id)
            item = {
                "source": source,
                "target": target,
                "edge_type": edge.edge_type,
                "edge_weight": edge.weight,
                "components": edge.components,
                "evidence": edge.evidence,
                "directed_citation": edge.directed,
            }
            if edge.source_openalex_id in paper_by_id:
                item["source_paper"] = self._paper_ref(source, paper_by_id[edge.source_openalex_id])
            if edge.target_openalex_id in paper_by_id:
                item["target_paper"] = self._paper_ref(target, paper_by_id[edge.target_openalex_id])
            result.append(item)
        return result

    @staticmethod
    def _serialize_paper(membership: CityPaperRecord, paper: PaperRecord) -> dict:
        return {
            "paper_id": membership.external_paper_id,
            "openalex_id": paper.openalex_id,
            "doi": paper.doi,
            "title": paper.title,
            "abstract": paper.abstract,
            "publication_year": paper.publication_year,
            "authors": paper.authors,
            "author_ids": paper.author_ids,
            "institutions": paper.institutions,
            "institution_ids": paper.institution_ids,
            "venue": paper.venue,
            "publisher": paper.publisher,
            "topics": paper.topics,
            "keywords": paper.keywords,
            "methods": paper.methods,
            "datasets": paper.datasets,
            "citation_count": paper.citation_count,
            "open_access": paper.open_access,
            "code_available": paper.code_available,
            "data_available": paper.data_available,
            "seeded": membership.is_seed,
            "seed_rank": membership.seed_position,
            "seed_relevance": membership.seed_relevance,
            "expansion_depth": membership.expansion_depth,
            "expansion_source": membership.expansion_source,
        }

    @staticmethod
    def _paper_ref(external_id: str, paper: PaperRecord) -> dict:
        return {
            "paper_id": external_id,
            "title": paper.title,
            "publication_year": paper.publication_year,
            "venue": paper.venue,
        }

    @staticmethod
    def _serialize_floor(floor: FloorRecord, vertex_ids: list[str]) -> dict:
        return {
            "floor_id": floor.external_id,
            "building_id": None,
            "floor_index": floor.floor_index,
            "core_range": [floor.core_min, floor.core_max],
            "vertex_ids": sorted(vertex_ids),
            "node_count": floor.node_count,
            "top_labels": floor.top_labels,
            "activation_score": floor.activation_score,
            "summary": floor.summary,
        }

    @staticmethod
    def _serialize_building(
        city_type: str,
        building: BuildingRecord,
        vertex_ids: list[str],
        floors: list[dict],
        community_id: str | None,
    ) -> dict:
        for floor in floors:
            floor["building_id"] = building.external_id
        return {
            "building_id": building.external_id,
            "city_type": city_type,
            "vertex_ids": sorted(vertex_ids),
            "node_count": building.node_count,
            "edge_count": building.edge_count,
            "internal_density": building.internal_density,
            "avg_core": building.avg_core,
            "max_core": building.max_core,
            "height": building.height,
            "footprint": building.footprint,
            "x": building.x,
            "z": building.z,
            "top_labels": building.top_labels,
            "semantic_domain": building.semantic_domain,
            "semantic_domain_name": building.semantic_domain_name,
            "semantic_color": building.semantic_color,
            "profile": building.profile,
            "original_labels": building.original_labels,
            "activation": building.activation,
            "activation_score": building.activation_score,
            "floors": floors,
            "floor_count": building.quality_metrics.get('floor_count', len(floors)),
            "floors_truncated": building.quality_metrics.get('floor_count', len(floors)) > len(floors),
            "summary": building.summary,
            "community_id": community_id,
            "quality_metrics": building.quality_metrics,
        }

    @staticmethod
    def _serialize_relationship(city_type: str, item: BuildingRelationshipRecord, building_external: dict) -> dict:
        common = {
            "city_type": city_type,
            "source_building_id": building_external[item.source_building_id],
            "target_building_id": building_external[item.target_building_id],
            "components": item.components,
            "evidence": item.evidence,
        }
        if item.relationship_kind == "bridge":
            return {
                **common,
                "bridge_id": item.external_id,
                "bridge_strength": item.score,
                "bridge_type": item.relationship_type,
                "summary": item.summary,
                "activation_score": item.activation_score,
            }
        return {
            **common,
            "street_id": item.external_id,
            "street_type": item.relationship_type,
            "distance": item.distance,
            "street_score": item.score,
        }

    @staticmethod
    def _city(session: Session, external_id: str) -> CityRecord:
        city = session.scalar(select(CityRecord).where(CityRecord.external_id == external_id))
        if city is None:
            raise KeyError(external_id)
        return city

    @staticmethod
    def _building(session: Session, city_id: uuid.UUID, external_id: str) -> BuildingRecord:
        building = session.scalar(
            select(BuildingRecord).where(BuildingRecord.city_id == city_id, BuildingRecord.external_id == external_id)
        )
        if building is None:
            raise KeyError(external_id)
        return building

    @staticmethod
    def _limit(limit: int) -> int:
        return max(1, min(limit, 200))
