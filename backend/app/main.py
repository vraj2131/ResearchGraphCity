from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .assistant import answer_research_question, build_evidence_packet, build_evidence_report
from .config import Settings, load_settings
from .jobs import JobRepository
from .llm import GroqSummaryProvider, unavailable_navigation
from .openalex import build_city_from_seed_inputs, parse_seed_text
from .repositories.factory import get_city_repository
from .repositories.postgres_city import PostgresCityRepository
from .repositories.protocols import CityRepository
from .routes.cities import create_cities_router
from .routes.jobs import create_jobs_router, serialize_job
from .routes.seed_graph import create_seed_graph_router
from .pipeline.embeddings import hash_documents
from .schemas import AssistantQueryRequest, BridgeSummaryPacket, BuildingSummaryPacket, CityCompareRequest, CityNavigationRequest, SeededCityRequest


DEFAULT_PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
CITY_NAMES = {
    "research": "Research Graph City",
    "seeded": "Seeded Research Graph City",
}
DEFAULT_SETTINGS = load_settings()


def create_app(
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    repository: CityRepository | None = None,
    job_repository: JobRepository | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    app = FastAPI(title="Research Graph City API")
    resolved_settings = settings or DEFAULT_SETTINGS
    city_repository = repository or get_city_repository(resolved_settings, processed_dir)
    active_jobs = job_repository
    if isinstance(city_repository, PostgresCityRepository):
        active_jobs = active_jobs or JobRepository(city_repository.session_factory)
        app.include_router(create_cities_router(city_repository, active_jobs))
        app.include_router(create_jobs_router(active_jobs))
        app.include_router(create_seed_graph_router(city_repository))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def file(name: str) -> Path:
        return processed_dir / name

    def city_prefix(city_id: str) -> str:
        if isinstance(city_repository, PostgresCityRepository):
            try:
                return city_repository.get_city_record(city_id).external_id
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=404, detail="City not found") from exc
        if city_id not in CITY_NAMES:
            raise HTTPException(status_code=404, detail="City not found")
        return city_id

    def city_file(city_id: str, suffix: str) -> Path:
        return file(f"{city_prefix(city_id)}_{suffix}.json")

    def read_city_json(city_id: str, suffix: str, default):
        try:
            return city_repository.read_collection(city_prefix(city_id), suffix)
        except KeyError:
            return default

    def city_counts(city) -> dict[str, int]:
        return {
            "vertices": len(city.vertices),
            "edges": len(city.edges),
            "buildings": len(city.buildings),
            "floors": len(city.floors),
            "bridges": len(city.bridges),
            "streets": len(city.streets),
            "communities": len(city.communities),
        }

    def city_navigation_index(city_id: str) -> dict:
        buildings = sorted(read_city_json(city_id, "buildings", []), key=lambda item: item.get("node_count", 0), reverse=True)
        bridges = sorted(read_city_json(city_id, "bridges", []), key=lambda item: item.get("bridge_strength", 0), reverse=True)
        streets = sorted(read_city_json(city_id, "streets", []), key=lambda item: item.get("street_score", 0), reverse=True)
        communities = read_city_json(city_id, "communities", [])
        return {
            "city_type": city_id,
            "buildings": [
                {
                    "id": item.get("building_id"),
                    "labels": item.get("top_labels", [])[:5],
                    "semantic_domain": item.get("semantic_domain"),
                    "semantic_domain_name": item.get("semantic_domain_name"),
                    "community_id": item.get("community_id"),
                    "node_count": item.get("node_count"),
                    "edge_count": item.get("edge_count"),
                    "density": item.get("internal_density"),
                    "avg_core": item.get("avg_core"),
                    "activation": item.get("activation_score"),
                }
                for item in buildings[:40]
            ],
            "bridges": [
                {
                    "id": item.get("bridge_id"),
                    "source": item.get("source_building_id"),
                    "target": item.get("target_building_id"),
                    "strength": item.get("bridge_strength"),
                    "type": item.get("bridge_type"),
                    "evidence": item.get("evidence", [])[:6],
                }
                for item in bridges[:40]
            ],
            "streets": [
                {
                    "id": item.get("street_id"),
                    "source": item.get("source_building_id"),
                    "target": item.get("target_building_id"),
                    "score": item.get("street_score"),
                    "type": item.get("street_type"),
                    "evidence": item.get("evidence", [])[:4],
                }
                for item in streets[:30]
            ],
            "communities": [
                {
                    "id": item.get("community_id"),
                    "name": item.get("name"),
                    "semantic_domain": item.get("semantic_domain"),
                    "semantic_domain_name": item.get("semantic_domain_name"),
                    "building_ids": item.get("building_ids", []),
                    "labels": item.get("top_labels", [])[:5],
                }
                for item in communities
            ],
        }

    @app.get("/api/cities")
    def cities():
        return city_repository.list_cities()

    @app.post("/api/cities/seeded/build")
    def build_seeded_city(request: SeededCityRequest):
        seed_inputs = parse_seed_text(request.seed_text)
        if not seed_inputs:
            raise HTTPException(status_code=400, detail="Add at least one paper title, DOI, or OpenAlex work URL.")
        if isinstance(city_repository, PostgresCityRepository) and active_jobs is not None:
            city, warnings = city_repository.create_city("Seeded Research Graph City", seed_inputs, request.target_total)
            job = active_jobs.enqueue(city.id)
            city_repository.set_city_status(city.id, "building")
            response = serialize_job(job).model_dump(mode="json")
            response.update({"city_type": city.external_id, "warnings": warnings})
            return response
        if request.target_total > 1000:
            raise HTTPException(status_code=409, detail="PostgreSQL storage is required for builds above 1,000 papers.")
        try:
            city = build_city_from_seed_inputs(
                seed_inputs,
                processed_dir,
                target_total=request.target_total,
                per_query=request.per_query,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "OpenAlex is unavailable for seeded city generation. "
                    "Check backend internet/DNS access and OPENALEX_API_KEY, then try again. "
                    f"{exc}"
                ),
            ) from exc
        return {"city_type": "seeded", "counts": city_counts(city), "warnings": getattr(city, "warnings", [])}

    @app.get("/api/cities/research/buildings")
    def buildings():
        return read_city_json("research", "buildings", [])

    @app.get("/api/cities/research/bridges")
    def bridges():
        return read_city_json("research", "bridges", [])

    @app.get("/api/cities/research/streets")
    def streets():
        return read_city_json("research", "streets", [])

    @app.get("/api/cities/research/communities")
    def communities():
        return read_city_json("research", "communities", [])

    @app.get("/api/cities/{city_id}/buildings")
    def city_buildings(city_id: str):
        return read_city_json(city_id, "buildings", [])

    @app.get("/api/cities/{city_id}/bridges")
    def city_bridges(city_id: str):
        return read_city_json(city_id, "bridges", [])

    @app.get("/api/cities/{city_id}/streets")
    def city_streets(city_id: str):
        return read_city_json(city_id, "streets", [])

    @app.get("/api/cities/{city_id}/communities")
    def city_communities(city_id: str):
        return read_city_json(city_id, "communities", [])

    @app.get("/api/cities/{city_id}/scene")
    def city_scene(city_id: str):
        try:
            return city_repository.get_scene(city_prefix(city_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="City not found") from exc

    @app.get("/api/cities/{city_id}/papers/search")
    def search_city_papers(
        city_id: str,
        q: str,
        year_min: int | None = None,
        year_max: int | None = None,
        domain: str | None = None,
        district_id: str | None = None,
        building_id: str | None = None,
        author: str | None = None,
        institution: str | None = None,
        venue: str | None = None,
        topic: str | None = None,
        open_access: bool | None = None,
        code_available: bool | None = None,
        data_available: bool | None = None,
        limit: int = 20,
    ):
        if not isinstance(city_repository, PostgresCityRepository):
            raise HTTPException(status_code=409, detail="PostgreSQL storage is required for scalable paper search.")
        if not q.strip():
            raise HTTPException(status_code=400, detail="Search text is required.")
        filters = {
            key: value
            for key, value in {
                "year_min": year_min,
                "year_max": year_max,
                "domain": domain,
                "district_id": district_id,
                "building_id": building_id,
                "author": author,
                "institution": institution,
                "venue": venue,
                "topic": topic,
                "open_access": open_access,
                "code_available": code_available,
                "data_available": data_available,
            }.items()
            if value is not None
        }
        try:
            return city_repository.search_papers(
                city_prefix(city_id),
                q.strip(),
                hash_documents([q.strip()])[0].tolist(),
                filters=filters,
                limit=limit,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="City not found") from exc

    @app.get("/api/cities/{city_id}/papers/{paper_id:path}")
    def city_paper(city_id: str, paper_id: str):
        if not isinstance(city_repository, PostgresCityRepository):
            raise HTTPException(status_code=409, detail="PostgreSQL storage is required for paper details.")
        try:
            paper = city_repository.get_paper(city_prefix(city_id), paper_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="City not found") from exc
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found")
        return paper

    @app.post("/api/cities/{city_id}/assistant/query")
    def research_assistant(city_id: str, request: AssistantQueryRequest):
        if not isinstance(city_repository, PostgresCityRepository):
            raise HTTPException(status_code=409, detail="PostgreSQL storage is required for evidence-grounded answers.")
        try:
            return answer_research_question(
                city_repository,
                GroqSummaryProvider(),
                city_prefix(city_id),
                request.question.strip(),
                request.filters,
                request.limit,
            ).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="City not found") from exc

    @app.get("/api/cities/{city_id}/timeline")
    def city_timeline(city_id: str):
        if not isinstance(city_repository, PostgresCityRepository):
            raise HTTPException(status_code=409, detail="PostgreSQL storage is required for timeline analysis.")
        try:
            return city_repository.get_timeline(city_prefix(city_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="City not found") from exc

    @app.post("/api/cities/compare")
    def compare_cities(request: CityCompareRequest):
        if not isinstance(city_repository, PostgresCityRepository):
            raise HTTPException(status_code=409, detail="PostgreSQL storage is required for city comparison.")
        try:
            return city_repository.compare_cities(
                city_prefix(request.left_city_id),
                city_prefix(request.right_city_id),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="City not found") from exc

    @app.post("/api/cities/{city_id}/exports/evidence-report", response_class=PlainTextResponse)
    def export_evidence_report(city_id: str, request: AssistantQueryRequest):
        if not isinstance(city_repository, PostgresCityRepository):
            raise HTTPException(status_code=409, detail="PostgreSQL storage is required for evidence export.")
        try:
            packet = build_evidence_packet(
                city_repository,
                city_prefix(city_id),
                request.question.strip(),
                request.filters,
                request.limit,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="City not found") from exc
        return PlainTextResponse(
            build_evidence_report(packet),
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="research-evidence-report.md"'},
        )

    @app.get("/api/cities/research/building/{building_id}")
    def building(building_id: str):
        for item in read_city_json("research", "buildings", []):
            if item.get("building_id") == building_id:
                return item
        raise HTTPException(status_code=404, detail="Building not found")

    @app.get("/api/cities/{city_id}/building/{building_id}")
    def city_building(city_id: str, building_id: str):
        for item in read_city_json(city_id, "buildings", []):
            if item.get("building_id") == building_id:
                return item
        raise HTTPException(status_code=404, detail="Building not found")

    def building_vertex_ids(city_id: str, building_id: str, floor_id: str | None = None) -> set[str]:
        for item in read_city_json(city_id, "buildings", []):
            if item.get("building_id") != building_id:
                continue
            if not floor_id:
                return set(item.get("vertex_ids", []))
            for floor in item.get("floors", []):
                if floor.get("floor_id") == floor_id:
                    return set(floor.get("vertex_ids", []))
            raise HTTPException(status_code=404, detail="Floor not found")
        raise HTTPException(status_code=404, detail="Building not found")

    def paper_refs(city_id: str) -> dict[str, dict]:
        refs = {}
        for item in read_city_json(city_id, "vertices", []):
            paper_id = item.get("paper_id")
            if not paper_id:
                continue
            refs[paper_id] = {
                key: item[key]
                for key in ("paper_id", "title", "publication_year", "venue")
                if key in item and item[key] is not None
            }
        return refs

    def enrich_edges(city_id: str, edges: list[dict]) -> list[dict]:
        refs = paper_refs(city_id)
        enriched = []
        for item in edges:
            edge = dict(item)
            source_paper = refs.get(edge.get("source"))
            target_paper = refs.get(edge.get("target"))
            if source_paper:
                edge["source_paper"] = source_paper
            if target_paper:
                edge["target_paper"] = target_paper
            enriched.append(edge)
        return enriched

    @app.get("/api/cities/research/building/{building_id}/papers")
    def building_papers(building_id: str, floor_id: str | None = None):
        return city_building_papers("research", building_id, floor_id)

    @app.get("/api/cities/research/building/{building_id}/edges")
    def building_edges(building_id: str, floor_id: str | None = None):
        return city_building_edges("research", building_id, floor_id)

    @app.get("/api/cities/{city_id}/building/{building_id}/papers")
    def city_building_papers(city_id: str, building_id: str, floor_id: str | None = None, limit: int = 200, cursor: str | None = None):
        if isinstance(city_repository, PostgresCityRepository):
            try:
                return city_repository.get_building_papers(city_prefix(city_id), building_id, floor_id, limit, cursor)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Building or floor not found") from exc
        vertex_ids = building_vertex_ids(city_id, building_id, floor_id)
        return [item for item in read_city_json(city_id, "vertices", []) if item.get("paper_id") in vertex_ids][: max(1, min(limit, 200))]

    @app.get("/api/cities/{city_id}/building/{building_id}/edges")
    def city_building_edges(city_id: str, building_id: str, floor_id: str | None = None, limit: int = 200, cursor: str | None = None):
        if isinstance(city_repository, PostgresCityRepository):
            try:
                return city_repository.get_building_edges(city_prefix(city_id), building_id, floor_id, limit, cursor)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Building or floor not found") from exc
        vertex_ids = building_vertex_ids(city_id, building_id, floor_id)
        return enrich_edges(city_id, [
            item
            for item in read_city_json(city_id, "edges", [])
            if item.get("source") in vertex_ids and item.get("target") in vertex_ids
        ])[: max(1, min(limit, 200))]

    @app.get("/api/cities/research/bridge/{bridge_id}")
    def bridge(bridge_id: str):
        for item in read_city_json("research", "bridges", []):
            if item.get("bridge_id") == bridge_id:
                return item
        raise HTTPException(status_code=404, detail="Bridge not found")

    @app.get("/api/cities/{city_id}/bridge/{bridge_id}")
    def city_bridge(city_id: str, bridge_id: str):
        for item in read_city_json(city_id, "bridges", []):
            if item.get("bridge_id") == bridge_id:
                return item
        raise HTTPException(status_code=404, detail="Bridge not found")

    @app.get("/api/cities/research/bridge/{bridge_id}/edges")
    def bridge_edges(bridge_id: str):
        return city_bridge_edges("research", bridge_id)

    @app.get("/api/cities/{city_id}/bridge/{bridge_id}/edges")
    def city_bridge_edges(city_id: str, bridge_id: str, limit: int = 200, cursor: str | None = None):
        if isinstance(city_repository, PostgresCityRepository):
            try:
                return city_repository.get_bridge_edges(city_prefix(city_id), bridge_id, limit, cursor)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Bridge not found") from exc
        bridge_item = None
        for item in read_city_json(city_id, "bridges", []):
            if item.get("bridge_id") == bridge_id:
                bridge_item = item
                break
        if not bridge_item:
            raise HTTPException(status_code=404, detail="Bridge not found")

        source_ids = building_vertex_ids(city_id, bridge_item.get("source_building_id", ""))
        target_ids = building_vertex_ids(city_id, bridge_item.get("target_building_id", ""))

        return enrich_edges(city_id, [
            item
            for item in read_city_json(city_id, "edges", [])
            if (
                (item.get("source") in source_ids and item.get("target") in target_ids)
                or (item.get("source") in target_ids and item.get("target") in source_ids)
            )
        ])[: max(1, min(limit, 200))]

    @app.post("/api/llm/building-summary")
    def building_summary(packet: BuildingSummaryPacket):
        return GroqSummaryProvider().generate_building_summary(packet).model_dump(mode="json")

    @app.post("/api/llm/bridge-summary")
    def bridge_summary(packet: BridgeSummaryPacket):
        return GroqSummaryProvider().generate_bridge_summary(packet).model_dump(mode="json")

    @app.post("/api/llm/city-navigation")
    def city_navigation(packet: CityNavigationRequest):
        if not packet.question.strip():
            raise HTTPException(status_code=400, detail="Navigation question is required.")
        index = city_navigation_index(packet.city_type)
        if not index["buildings"]:
            raise HTTPException(status_code=404, detail=f"No {packet.city_type} city has been built yet.")
        try:
            result = GroqSummaryProvider().generate_city_navigation(packet.question.strip(), index)
        except Exception as exc:
            return unavailable_navigation(f"City navigation LLM request failed. Check GROQ_API_KEY and network access.").model_dump(mode="json")
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json")
        return vars(result)

    return app


app = create_app()
