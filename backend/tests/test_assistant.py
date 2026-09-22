from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.assistant import build_evidence_packet, build_retrieval_fallback, infer_question_filters, research_query_text, validate_assistant_response
from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.models import AssistantConversationRecord, AssistantMessageRecord, BuildingRecord, CityPaperRecord, DistrictRecord, PaperEmbeddingRecord, PaperRecord
from app.main import create_app
from app.pipeline.embeddings import EMBEDDING_MODEL, hash_documents
from app.repositories.postgres_city import PostgresCityRepository
from app.schemas import AssistantClaim, AssistantResponse


def evidence_packet() -> dict:
    return {
        "papers": [
            {
                "evidence_id": "paper:W1",
                "openalex_id": "W1",
                "paper_id": "P_000001",
                "title": "Graph neural networks for molecules",
                "publication_year": 2024,
                "authors": ["A. Researcher"],
                "venue": "Graph Journal",
                "topics": ["Graph Neural Networks"],
                "methods": ["message passing"],
                "datasets": ["QM9"],
                "citation_count": 12,
                "building_id": "B_0001",
                "building_label": "Molecular Graph Learning",
                "district_id": "D_0001",
                "domain_name": "Artificial Intelligence",
                "score": 0.91,
            }
        ],
        "buildings": [
            {
                "evidence_id": "building:B_0001",
                "building_id": "B_0001",
                "label": "Molecular Graph Learning",
                "domain_name": "Artificial Intelligence",
                "district_id": "D_0001",
            }
        ],
        "districts": [
            {
                "evidence_id": "district:D_0001",
                "district_id": "D_0001",
                "name": "Graph AI",
                "domain_name": "Artificial Intelligence",
            }
        ],
        "relationships": [],
        "filters_applied": {},
        "retrieval_summary": {"candidate_count": 1, "returned_count": 1},
        "retrieval_margin": 0.91,
    }


def test_question_filters_extract_research_constraints_without_overriding_explicit_values():
    filters = infer_question_filters(
        "Show open access papers with code and data between 2020 and 2024",
        {"year_min": 2021},
    )

    assert filters == {
        "year_min": 2021,
        "year_max": 2024,
        "open_access": True,
        "code_available": True,
        "data_available": True,
    }

    assert research_query_text("Which open access graph visualization papers and domains should I inspect?") == "graph visualization"


def test_fallback_keeps_paper_and_domain_evidence_without_llm():
    result = build_retrieval_fallback("Which molecular graph papers should I read?", evidence_packet())

    assert result.model_available is False
    assert "Molecular Graph Learning" in result.answer_markdown
    assert result.papers[0]["title"] == "Graph neural networks for molecules"
    assert result.districts[0]["domain_name"] == "Artificial Intelligence"
    assert result.claims[0].citation_ids == ["paper:W1"]
    assert result.confidence > 0
    assert result.route_steps[0].target_id == "B_0001"


def test_fallback_answers_trend_questions_from_timeline_evidence():
    packet = evidence_packet()
    packet["timeline"] = [
        {"evidence_id": "timeline:2020", "year": 2020, "paper_count": 2, "citation_count": 5},
        {"evidence_id": "timeline:2024", "year": 2024, "paper_count": 7, "citation_count": 12},
    ]

    result = build_retrieval_fallback("How has this topic changed over time?", packet)

    assert "2020 to 2024" in result.answer_markdown
    assert result.claims[0].citation_ids == ["timeline:2024"]


def test_assistant_validation_rejects_unknown_citation_ids():
    response = AssistantResponse(
        answer_markdown="A grounded-looking answer.",
        claims=[AssistantClaim(claim="Unsupported", citation_ids=["paper:W999"], support_score=0.8)],
        papers=[],
        buildings=[],
        districts=[],
        relationships=[],
        route_steps=[],
        filters_applied={},
        retrieval_summary={},
        confidence=0.8,
    )

    with pytest.raises(ValueError, match="unknown evidence ID"):
        validate_assistant_response(response, evidence_packet())


def test_assistant_validation_removes_unknown_route_targets_and_recomputes_confidence():
    packet = evidence_packet()
    response = AssistantResponse(
        answer_markdown="Inspect the molecular graph learning building.",
        claims=[AssistantClaim(claim="Relevant paper", citation_ids=["paper:W1"], support_score=0.9)],
        papers=[],
        buildings=[],
        districts=[],
        relationships=[],
        route_steps=[
            {"label": "Known", "target_type": "building", "target_id": "B_0001", "reason": "Contains the paper"},
            {"label": "Unknown", "target_type": "building", "target_id": "B_9999", "reason": "Invented"},
        ],
        filters_applied={},
        retrieval_summary={},
        confidence=1.0,
    )

    validated = validate_assistant_response(response, packet)

    assert [step.target_id for step in validated.route_steps] == ["B_0001"]
    assert validated.papers[0]["openalex_id"] == "W1"
    assert 0 < validated.confidence < 1


def test_postgres_hybrid_search_returns_city_context_and_applies_filters(monkeypatch):
    import os

    settings = Settings(
        database_url=os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_backend="postgres",
        worker_poll_seconds=1.0,
        job_stale_seconds=300,
        embedding_model=EMBEDDING_MODEL,
    )
    engine = create_engine_from_settings(settings)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    repository = PostgresCityRepository(factory)
    city, _ = repository.create_city("Assistant Search", ["seed"], 1_000)
    try:
        with factory.begin() as session:
            district = DistrictRecord(
                city_id=city.id,
                external_id="D_0001",
                name="Graph AI",
                semantic_domain="graph_ai",
                semantic_domain_name="Artificial Intelligence",
            )
            session.add(district)
            session.flush([district])
            building = BuildingRecord(
                city_id=city.id,
                district_id=district.id,
                external_id="B_0001",
                node_count=2,
                edge_count=1,
                internal_density=1.0,
                avg_core=1.0,
                max_core=1,
                height=10,
                footprint=8,
                x=0,
                z=0,
                top_labels=["Molecular Graph Learning"],
                semantic_domain="graph_ai",
                semantic_domain_name="Artificial Intelligence",
            )
            session.add(building)
            session.flush([building])
            papers = [
                PaperRecord(
                    openalex_id="W1",
                    title="Graph neural networks for molecules",
                    abstract="Message passing predicts molecular properties.",
                    publication_year=2024,
                    citation_count=20,
                    open_access=True,
                    topics=["Graph Neural Networks"],
                ),
                PaperRecord(
                    openalex_id="W2",
                    title="Economic policy under uncertainty",
                    abstract="A macroeconomic policy study.",
                    publication_year=2018,
                    citation_count=100,
                    open_access=False,
                    topics=["Economics"],
                ),
            ]
            session.add_all(papers)
            session.flush()
            vectors = hash_documents([f"{paper.title} {paper.abstract}" for paper in papers])
            for index, paper in enumerate(papers, start=1):
                session.add(
                    CityPaperRecord(
                        city_id=city.id,
                        openalex_id=paper.openalex_id,
                        external_paper_id=f"P_{index:06d}",
                        building_id=building.id,
                    )
                )
                session.add(
                    PaperEmbeddingRecord(
                        openalex_id=paper.openalex_id,
                        model=EMBEDDING_MODEL,
                        dimensions=64,
                        embedding=vectors[index - 1].tolist(),
                    )
                )

        results = repository.search_papers(
            city.external_id,
            "molecular graph neural networks",
            hash_documents(["molecular graph neural networks"])[0].tolist(),
            filters={"open_access": True, "year_min": 2020},
            limit=10,
        )

        assert [item["openalex_id"] for item in results] == ["W1"]
        assert results[0]["building_id"] == "B_0001"
        assert results[0]["district_name"] == "Graph AI"
        assert results[0]["domain_name"] == "Artificial Intelligence"
        assert results[0]["score"] > 0.5

        second_city, _ = repository.create_city("Comparison City", ["seed two"], 1_000)
        with factory.begin() as session:
            second_district = DistrictRecord(
                city_id=second_city.id,
                external_id="D_0002",
                name="Graph Methods",
                semantic_domain="graph_ai",
                semantic_domain_name="Artificial Intelligence",
            )
            session.add(second_district)
            session.flush([second_district])
            second_building = BuildingRecord(
                city_id=second_city.id,
                district_id=second_district.id,
                external_id="B_0002",
                node_count=1,
                edge_count=0,
                internal_density=0,
                avg_core=0,
                max_core=0,
                height=8,
                footprint=6,
                x=0,
                z=0,
                top_labels=["Graph Methods"],
                semantic_domain="graph_ai",
                semantic_domain_name="Artificial Intelligence",
            )
            session.add(second_building)
            session.flush([second_building])
            session.add(
                CityPaperRecord(
                    city_id=second_city.id,
                    openalex_id="W1",
                    external_paper_id="Q_000001",
                    building_id=second_building.id,
                )
            )

        timeline = repository.get_timeline(city.external_id)
        comparison = repository.compare_cities(city.external_id, second_city.external_id)
        trend_packet = build_evidence_packet(repository, city.external_id, "How has molecular graph research changed over time?", {}, 5)
        assert timeline["year_min"] == 2018
        assert timeline["year_max"] == 2024
        assert sum(item["paper_count"] for item in timeline["years"]) == 2
        assert comparison["papers"] == {"shared": 1, "left_only": 1, "right_only": 0}
        assert comparison["domains"]["shared"] == ["Artificial Intelligence"]
        assert [item["evidence_id"] for item in trend_packet["timeline"]] == ["timeline:2018", "timeline:2024"]

        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        client = TestClient(create_app(repository=repository, settings=settings))
        search = client.get(
            f"/api/cities/{city.external_id}/papers/search",
            params={"q": "molecular graph neural networks", "open_access": True, "year_min": 2020},
        )
        detail = client.get(f"/api/cities/{city.external_id}/papers/W1")
        assistant = client.post(
            f"/api/cities/{city.external_id}/assistant/query",
            json={"question": "Which molecular graph papers should I read?"},
        )
        timeline_response = client.get(f"/api/cities/{city.external_id}/timeline")
        comparison_response = client.post(
            "/api/cities/compare",
            json={"left_city_id": city.external_id, "right_city_id": second_city.external_id},
        )
        report = client.post(
            f"/api/cities/{city.external_id}/exports/evidence-report",
            json={"question": "molecular graph neural networks"},
        )

        assert search.status_code == 200
        assert search.json()[0]["openalex_id"] == "W1"
        assert detail.status_code == 200
        assert detail.json()["title"] == "Graph neural networks for molecules"
        assert assistant.status_code == 200
        assert assistant.json()["papers"][0]["building_id"] == "B_0001"
        assert assistant.json()["model_available"] is False
        assert assistant.json()["conversation_id"]
        assert timeline_response.status_code == 200
        assert comparison_response.json()["papers"]["shared"] == 1
        assert report.status_code == 200
        assert "Graph neural networks for molecules" in report.text
        assert report.headers["content-type"].startswith("text/markdown")
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(AssistantConversationRecord)) == 1
            assert session.scalar(select(func.count()).select_from(AssistantMessageRecord)) == 2
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
