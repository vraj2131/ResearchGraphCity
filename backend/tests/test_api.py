from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.json_city import JsonCityRepository
from app.storage import write_json


def json_client(processed_dir: Path) -> TestClient:
    return TestClient(create_app(processed_dir=processed_dir, repository=JsonCityRepository(processed_dir)))


class StubCityRepository:
    def list_cities(self):
        return [{"city_type": "research", "name": "Database Research City"}]

    def read_collection(self, city_id, suffix):
        if suffix == "buildings":
            return [{"building_id": "B_DB_0001"}]
        return []


def test_api_can_read_through_injected_repository(tmp_path: Path):
    client = TestClient(create_app(processed_dir=tmp_path, repository=StubCityRepository()))

    assert client.get("/api/cities").json()[0]["name"] == "Database Research City"
    assert client.get("/api/cities/research/buildings").json() == [{"building_id": "B_DB_0001"}]


def test_api_serves_processed_research_city(tmp_path: Path):
    processed = tmp_path / "processed"
    processed.mkdir()
    write_json(processed / "research_buildings.json", [{"building_id": "B_R_0001"}])
    write_json(processed / "research_bridges.json", [{"bridge_id": "BR_R_0001_0002"}])
    write_json(processed / "research_streets.json", [{"street_id": "ST_R_0001_0002"}])
    write_json(processed / "research_communities.json", [{"community_id": "C_R_0001"}])

    client = json_client(processed)

    assert client.get("/api/cities").json() == [{"city_type": "research", "name": "Research Graph City"}]
    assert client.get("/api/cities/research/buildings").json()[0]["building_id"] == "B_R_0001"
    assert client.get("/api/cities/research/bridges").json()[0]["bridge_id"] == "BR_R_0001_0002"
    assert client.get("/api/cities/research/streets").json()[0]["street_id"] == "ST_R_0001_0002"
    assert client.get("/api/cities/research/communities").json()[0]["community_id"] == "C_R_0001"


def test_api_builds_and_serves_seeded_city(tmp_path: Path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()

    def fake_build_city_from_seed_inputs(seed_inputs, processed_dir, target_total=1000, per_query=100):
        assert seed_inputs == ["Visualizing Data using t-SNE", "Fast unfolding of communities in large networks"]
        assert target_total == 1000
        write_json(processed_dir / "seeded_vertices.json", [{"paper_id": "R_000001", "title": seed_inputs[0], "seeded": True}])
        write_json(processed_dir / "seeded_edges.json", [])
        write_json(processed_dir / "seeded_buildings.json", [{"building_id": "B_R_0001", "vertex_ids": ["R_000001"]}])
        write_json(processed_dir / "seeded_floors.json", [])
        write_json(processed_dir / "seeded_bridges.json", [])
        write_json(processed_dir / "seeded_streets.json", [{"street_id": "ST_R_0001_0002", "street_score": 0.4}])
        write_json(processed_dir / "seeded_communities.json", [{"community_id": "C_R_0001"}])
        return SimpleNamespace(vertices=[1], edges=[], buildings=[1], floors=[], bridges=[], streets=[1], communities=[1])

    monkeypatch.setattr("app.main.build_city_from_seed_inputs", fake_build_city_from_seed_inputs)
    client = json_client(processed)

    response = client.post(
        "/api/cities/seeded/build",
        json={"seed_text": "Visualizing Data using t-SNE\nFast unfolding of communities in large networks"},
    )

    assert response.status_code == 200
    assert response.json()["counts"] == {"vertices": 1, "edges": 0, "buildings": 1, "floors": 0, "bridges": 0, "streets": 1, "communities": 1}
    assert response.json()["warnings"] == []
    assert client.get("/api/cities/seeded/buildings").json()[0]["building_id"] == "B_R_0001"
    assert client.get("/api/cities/seeded/streets").json()[0]["street_score"] == 0.4


def test_api_returns_seeded_city_warnings(tmp_path: Path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()

    def fake_build_city_from_seed_inputs(seed_inputs, processed_dir, target_total=1000, per_query=100):
        write_json(processed_dir / "seeded_vertices.json", [{"paper_id": "R_000001", "title": seed_inputs[0], "seeded": True}])
        write_json(processed_dir / "seeded_edges.json", [])
        write_json(processed_dir / "seeded_buildings.json", [{"building_id": "B_R_0001", "vertex_ids": ["R_000001"]}])
        write_json(processed_dir / "seeded_floors.json", [])
        write_json(processed_dir / "seeded_bridges.json", [])
        write_json(processed_dir / "seeded_streets.json", [])
        write_json(processed_dir / "seeded_communities.json", [])
        return SimpleNamespace(vertices=[1], edges=[], buildings=[1], floors=[], bridges=[], streets=[], communities=[], warnings=["Skipped seed 'bad title': no OpenAlex match"])

    monkeypatch.setattr("app.main.build_city_from_seed_inputs", fake_build_city_from_seed_inputs)
    client = json_client(processed)

    response = client.post("/api/cities/seeded/build", json={"seed_text": "good title\nbad title"})

    assert response.status_code == 200
    assert response.json()["warnings"] == ["Skipped seed 'bad title': no OpenAlex match"]


def test_api_reports_openalex_seed_build_failure_gracefully(tmp_path: Path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()

    def fail_build_city_from_seed_inputs(seed_inputs, processed_dir, target_total=1000, per_query=100):
        raise RuntimeError("OpenAlex seed lookup failed for Visualizing Data using t-SNE")

    monkeypatch.setattr("app.main.build_city_from_seed_inputs", fail_build_city_from_seed_inputs)
    client = json_client(processed)

    response = client.post("/api/cities/seeded/build", json={"seed_text": "Visualizing Data using t-SNE"})

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "OpenAlex is unavailable for seeded city generation. "
        "Check backend internet/DNS access and OPENALEX_API_KEY, then try again. "
        "OpenAlex seed lookup failed for Visualizing Data using t-SNE"
    )


def test_api_serves_building_papers_and_internal_edges(tmp_path: Path):
    processed = tmp_path / "processed"
    processed.mkdir()
    write_json(
        processed / "research_buildings.json",
        [
            {
                "building_id": "B_R_0001",
                "vertex_ids": ["R_000001", "R_000002"],
                "floors": [{"floor_id": "F_B_R_0001_01", "vertex_ids": ["R_000001"]}],
            }
        ],
    )
    write_json(
        processed / "research_vertices.json",
        [
            {"paper_id": "R_000001", "title": "Paper One", "topics": ["Topic Modeling"]},
            {"paper_id": "R_000002", "title": "Paper Two", "topics": ["GraphRAG"]},
            {"paper_id": "R_000003", "title": "Outside Paper", "topics": ["Other"]},
        ],
    )
    write_json(
        processed / "research_edges.json",
        [
            {"source": "R_000001", "target": "R_000002", "edge_weight": 0.8, "evidence": ["shared_topic: Topic Modeling"]},
            {"source": "R_000001", "target": "R_000003", "edge_weight": 0.9, "evidence": ["outside"]},
        ],
    )

    client = json_client(processed)

    papers = client.get("/api/cities/research/building/B_R_0001/papers").json()
    edges = client.get("/api/cities/research/building/B_R_0001/edges").json()
    floor_papers = client.get("/api/cities/research/building/B_R_0001/papers?floor_id=F_B_R_0001_01").json()
    floor_edges = client.get("/api/cities/research/building/B_R_0001/edges?floor_id=F_B_R_0001_01").json()

    assert [paper["paper_id"] for paper in papers] == ["R_000001", "R_000002"]
    assert len(edges) == 1
    assert edges[0]["source"] == "R_000001"
    assert edges[0]["source_paper"]["title"] == "Paper One"
    assert edges[0]["target_paper"]["title"] == "Paper Two"
    assert [paper["paper_id"] for paper in floor_papers] == ["R_000001"]
    assert floor_edges == []
    assert client.get("/api/cities/research/building/B_R_0001/edges?cursor=R_000001:R_000002").json() == []
    later = client.get("/api/cities/research/building/B_R_0001/papers?limit=1&cursor=R_000001").json()
    assert [paper["paper_id"] for paper in later] == ["R_000002"]
    assert client.get("/api/cities/research/building/B_R_0001/papers?cursor=R_000002").json() == []


def test_api_serves_bridge_cross_edges(tmp_path: Path):
    processed = tmp_path / "processed"
    processed.mkdir()
    write_json(
        processed / "research_buildings.json",
        [
            {"building_id": "B_R_0001", "vertex_ids": ["R_000001", "R_000002"]},
            {"building_id": "B_R_0002", "vertex_ids": ["R_000101", "R_000102"]},
        ],
    )
    write_json(
        processed / "research_bridges.json",
        [
            {
                "bridge_id": "BR_R_0001_0002",
                "source_building_id": "B_R_0001",
                "target_building_id": "B_R_0002",
            }
        ],
    )
    write_json(
        processed / "research_vertices.json",
        [
            {"paper_id": "R_000001", "title": "Source Building Paper", "publication_year": 2025, "venue": "Graph Journal"},
            {"paper_id": "R_000101", "title": "Target Building Paper", "publication_year": 2024, "venue": "AI Journal"},
        ],
    )
    write_json(
        processed / "research_edges.json",
        [
            {"source": "R_000001", "target": "R_000101", "edge_weight": 0.74, "evidence": ["shared_topic: graph visualization"]},
            {"source": "R_000001", "target": "R_000002", "edge_weight": 0.92, "evidence": ["internal"]},
            {"source": "R_000102", "target": "R_999999", "edge_weight": 0.4, "evidence": ["outside"]},
        ],
    )

    client = json_client(processed)

    response = client.get("/api/cities/research/bridge/BR_R_0001_0002/edges")

    assert response.status_code == 200
    assert response.json() == [
        {
            "source": "R_000001",
            "target": "R_000101",
            "edge_weight": 0.74,
            "evidence": ["shared_topic: graph visualization"],
            "source_paper": {"paper_id": "R_000001", "title": "Source Building Paper", "publication_year": 2025, "venue": "Graph Journal"},
            "target_paper": {"paper_id": "R_000101", "title": "Target Building Paper", "publication_year": 2024, "venue": "AI Journal"},
        }
    ]


def test_llm_summary_returns_unavailable_without_groq_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    client = json_client(tmp_path)

    response = client.post(
        "/api/llm/building-summary",
        json={
            "building_id": "B_R_0001",
            "city_type": "research",
            "node_count": 10,
            "edge_count": 20,
            "internal_density": 0.4,
            "avg_core": 2.3,
            "top_labels": ["graph visualization"],
            "dominant_attributes": {"topics": ["graph visualization"]},
            "activation_score": 0.5,
            "strongest_bridges": [],
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["short_name"] == "Summary unavailable"
    assert body["confidence"] == 0.0


def test_city_navigation_uses_compact_seeded_city_index(tmp_path: Path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()
    write_json(
        processed / "seeded_buildings.json",
        [
            {
                "building_id": "B_R_0001",
                "node_count": 25,
                "edge_count": 40,
                "internal_density": 0.2,
                "avg_core": 3.4,
                "activation_score": 0.8,
                "top_labels": ["Climate Change"],
                "semantic_domain_name": "Climate and Energy",
                "community_id": "C_R_0001",
            }
        ],
    )
    write_json(
        processed / "seeded_bridges.json",
        [
            {
                "bridge_id": "BR_R_0001_0002",
                "source_building_id": "B_R_0001",
                "target_building_id": "B_R_0002",
                "bridge_strength": 0.6,
                "bridge_type": "semantic_structural",
                "evidence": ["shared_label: climate"],
            }
        ],
    )
    write_json(processed / "seeded_streets.json", [])
    write_json(processed / "seeded_communities.json", [{"community_id": "C_R_0001", "name": "Climate", "color": "#facc15"}])

    captured = {}

    def fake_navigation(self, question, city_index):
        captured["question"] = question
        captured["city_index"] = city_index
        return SimpleNamespace(
            answer="Go to B_R_0001.",
            route_steps=[{"label": "Climate", "target_type": "building", "target_id": "B_R_0001", "reason": "Matches climate"}],
            focus_building_ids=["B_R_0001"],
            focus_bridge_ids=[],
            confidence=0.9,
            model_available=True,
        )

    monkeypatch.setattr("app.main.GroqSummaryProvider.generate_city_navigation", fake_navigation)
    client = json_client(processed)

    response = client.post("/api/llm/city-navigation", json={"city_type": "seeded", "question": "Where is climate work?"})

    assert response.status_code == 200
    assert response.json()["focus_building_ids"] == ["B_R_0001"]
    assert captured["question"] == "Where is climate work?"
    assert captured["city_index"]["buildings"][0]["id"] == "B_R_0001"
    assert "vertex_ids" not in captured["city_index"]["buildings"][0]


def test_city_navigation_returns_graceful_unavailable_when_llm_fails(tmp_path: Path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()
    write_json(
        processed / "seeded_buildings.json",
        [
            {
                "building_id": "B_R_0001",
                "node_count": 25,
                "top_labels": ["Graph Learning"],
            }
        ],
    )
    write_json(processed / "seeded_bridges.json", [])
    write_json(processed / "seeded_streets.json", [])
    write_json(processed / "seeded_communities.json", [])

    def fail_navigation(self, question, city_index):
        raise RuntimeError("upstream timeout")

    monkeypatch.setattr("app.main.GroqSummaryProvider.generate_city_navigation", fail_navigation)
    client = json_client(processed)

    response = client.post("/api/llm/city-navigation", json={"city_type": "seeded", "question": "Where should I go?"})

    assert response.status_code == 200
    assert response.json()["model_available"] is False
    assert response.json()["confidence"] == 0.0
    assert "City navigation LLM request failed" in response.json()["answer"]
