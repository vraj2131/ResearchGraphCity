import json
from pathlib import Path

import pytest
import requests

from app.graph_processing import (
    build_bridges,
    build_communities,
    build_floors,
    build_research_edges,
    build_streets,
    generate_research_city,
    jaccard,
    normalize_openalex_work,
    semantic_domain_for_labels,
    research_edge_components,
    research_edge_weight,
    assign_building_layout,
    top_labels,
)
from app.openalex import SELECT_FIELDS, build_city_from_openalex, build_city_from_seed_inputs, fetch_openalex_works, parse_seed_text, resolve_seed_works
from app.sample_data import build_sample_city
from app.schemas import Bridge, Building, ResearchEdge


def make_work(idx: int, **overrides):
    base = {
        "id": f"https://openalex.org/W{idx}",
        "doi": f"https://doi.org/10.1000/{idx}",
        "title": f"Paper {idx}",
        "abstract_inverted_index": {"graph": [0], "city": [1], str(idx): [2]},
        "publication_year": 2024,
        "authorships": [
            {
                "author": {"id": "https://openalex.org/A1", "display_name": "Author One"},
                "institutions": [
                    {"id": "https://openalex.org/I1", "display_name": "Rutgers University"}
                ],
            }
        ],
        "primary_location": {
            "source": {
                "id": "https://openalex.org/S1",
                "display_name": "Graph Journal",
            }
        },
        "topics": [{"display_name": "graph visualization"}],
        "keywords": [{"display_name": "graph city"}],
        "referenced_works": [],
        "cited_by_count": 10,
        "open_access": {"is_oa": True},
    }
    base.update(overrides)
    return base


def test_normalize_openalex_work_handles_missing_optional_fields():
    work = make_work(
        1,
        doi=None,
        abstract_inverted_index=None,
        topics=[],
        authorships=[],
        primary_location=None,
    )

    paper = normalize_openalex_work(work, 1)

    assert paper.paper_id == "R_000001"
    assert paper.doi is None
    assert paper.abstract == ""
    assert paper.topics == []
    assert paper.authors == []
    assert paper.venue == ""
    assert paper.openalex_id == "https://openalex.org/W1"


def test_research_edge_weight_matches_spec_formula():
    components = {
        "citation": 1.0,
        "topic_similarity": 0.8,
        "text_similarity": 0.6,
        "method_dataset_overlap": 0.5,
        "author_institution_overlap": 0.25,
        "venue_similarity": 1.0,
        "time_proximity": 0.9,
    }

    assert research_edge_weight(components) == 0.72


def test_research_edges_keep_direct_citation_even_if_weight_is_low():
    first = normalize_openalex_work(
        make_work(
            1,
            topics=[{"display_name": "a"}],
            abstract_inverted_index={"alpha": [0]},
            referenced_works=["https://openalex.org/W2"],
            cited_by_count=1,
        ),
        1,
    )
    second = normalize_openalex_work(
        make_work(
            2,
            topics=[{"display_name": "z"}],
            abstract_inverted_index={"omega": [0]},
            cited_by_count=1,
            primary_location={"source": {"id": "S2", "display_name": "Other"}},
            authorships=[],
        ),
        2,
    )

    edges = build_research_edges([first, second], top_k=0, threshold=0.99)

    assert len(edges) == 1
    assert edges[0].directed_citation is True
    assert "direct_citation" in edges[0].evidence


def test_generate_research_city_excludes_isolates_and_creates_floors_and_bridges():
    vertices = []
    for idx in range(1, 15):
        topic = "cluster alpha" if idx <= 6 else "cluster beta"
        vertices.append(
            normalize_openalex_work(
                make_work(
                    idx,
                    topics=[{"display_name": topic}],
                    abstract_inverted_index={topic.split()[1]: [0], "graph": [1]},
                    cited_by_count=idx,
                ),
                idx,
            )
        )
    isolated = normalize_openalex_work(
        make_work(
            99,
            id="https://openalex.org/W99",
            topics=[{"display_name": "isolated"}],
            abstract_inverted_index={"isolated": [0]},
        ),
        99,
    )
    vertices.append(isolated)
    edges = build_research_edges(vertices[:-1], top_k=2, threshold=0.45)

    city = generate_research_city(vertices, edges, min_building_nodes=3)

    assert isolated.paper_id in city.outskirts
    assert len(city.buildings) >= 2
    assert all(1 <= len(building.floors) <= 5 for building in city.buildings)
    assert all(bridge.bridge_strength >= 0.35 for bridge in city.bridges)


def test_jaccard_handles_empty_sets():
    assert jaccard([], []) == 0.0
    assert jaccard(["a"], []) == 0.0
    assert jaccard(["a"], ["a", "b"]) == 0.5


def test_sample_city_has_enough_buildings_and_bridges_for_demo():
    city = build_sample_city()

    assert len(city.buildings) >= 5
    assert len(city.bridges) >= 5


def test_openalex_fetch_errors_do_not_expose_api_key(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "secret-key")

    def fail_request(*args, **kwargs):
        raise requests.ConnectionError("failed url https://api.openalex.org/works?api_key=secret-key")

    monkeypatch.setattr("app.openalex.requests.get", fail_request)

    with pytest.raises(RuntimeError) as exc:
        fetch_openalex_works(["graph visualization"], per_query=1)

    assert "secret-key" not in str(exc.value)
    assert "api_key" not in str(exc.value)
    assert exc.value.__cause__ is None


def test_openalex_fetch_uses_cursor_pagination_and_target_total(monkeypatch):
    calls = []
    responses = [
        openalex_response([make_work(1), make_work(2)], next_cursor="cursor-2"),
        openalex_response([make_work(2), make_work(3)], next_cursor="cursor-3"),
        openalex_response([make_work(4)], next_cursor=None),
    ]

    def fake_get(url, params, timeout):
        calls.append(params.copy())
        return responses.pop(0)

    monkeypatch.setattr("app.openalex.requests.get", fake_get)

    works = fetch_openalex_works(["graph visualization"], per_query=2, target_total=3)

    assert [work["id"] for work in works] == [
        "https://openalex.org/W1",
        "https://openalex.org/W2",
        "https://openalex.org/W3",
    ]
    assert [call["cursor"] for call in calls] == ["*", "cursor-2"]
    assert [call["per_page"] for call in calls] == [2, 1]


def test_openalex_fetch_balances_pages_across_queries(monkeypatch):
    calls = []
    responses = [
        openalex_response([make_work(1)], next_cursor="q1-next"),
        openalex_response([make_work(101)], next_cursor="q2-next"),
        openalex_response([make_work(2)], next_cursor=None),
    ]

    def fake_get(url, params, timeout):
        calls.append(params.copy())
        return responses.pop(0)

    monkeypatch.setattr("app.openalex.requests.get", fake_get)

    works = fetch_openalex_works(["query one", "query two"], per_query=1, target_total=3)

    assert [work["id"] for work in works] == [
        "https://openalex.org/W1",
        "https://openalex.org/W101",
        "https://openalex.org/W2",
    ]
    assert [(call["search"], call["cursor"]) for call in calls] == [
        ("query one", "*"),
        ("query two", "*"),
        ("query one", "q1-next"),
    ]


def test_build_city_from_openalex_forwards_target_total(tmp_path: Path, monkeypatch):
    captured = {}

    def fake_fetch(per_query=100, target_total=None):
        captured["per_query"] = per_query
        captured["target_total"] = target_total
        return []

    monkeypatch.setattr("app.openalex.fetch_openalex_works", fake_fetch)

    city = build_city_from_openalex(tmp_path, per_query=50, target_total=1000)

    assert captured == {"per_query": 50, "target_total": 1000}
    assert city.vertices == []


def test_parse_seed_text_accepts_simple_one_per_line_input():
    seed_text = """
    Visualizing Data using t-SNE

    https://doi.org/10.1000/example
    https://openalex.org/W123
    Visualizing Data using t-SNE
    """

    assert parse_seed_text(seed_text) == [
        "Visualizing Data using t-SNE",
        "https://doi.org/10.1000/example",
        "https://openalex.org/W123",
    ]


def test_build_city_from_seed_inputs_marks_seed_vertices_and_writes_seeded_files(tmp_path: Path, monkeypatch):
    seed_works = [
        make_work(1, title="Seed Graph Visualization", topics=[{"display_name": "Topic Modeling"}]),
        make_work(2, title="Seed Network Science", topics=[{"display_name": "Complex Network Analysis Techniques"}]),
    ]
    related_works = [
        make_work(idx, title=f"Related Graph Paper {idx}", topics=[{"display_name": "Topic Modeling"}])
        for idx in range(3, 18)
    ]

    monkeypatch.setattr("app.openalex.resolve_seed_works", lambda seed_inputs: (seed_works, []))
    monkeypatch.setattr("app.openalex.fetch_openalex_works", lambda queries, per_query=100, target_total=None, continue_on_error=False: related_works[: target_total or len(related_works)])

    city = build_city_from_seed_inputs(["Seed Graph Visualization", "Seed Network Science"], tmp_path, target_total=10)

    assert len(city.vertices) == 10
    assert city.vertices[0].seeded is True
    assert city.vertices[0].seed_rank == 1
    assert city.vertices[1].seeded is True
    assert city.vertices[2].seeded is False
    vertices = json.loads((tmp_path / "seeded_vertices.json").read_text())
    assert vertices[0]["seeded"] is True
    assert (tmp_path / "seeded_buildings.json").exists()
    assert (tmp_path / "seeded_streets.json").exists()


def test_seed_resolution_skips_failed_or_unmatched_seeds(monkeypatch):
    def fake_resolve_seed_work(seed_input):
        if seed_input == "bad network title":
            raise RuntimeError("OpenAlex seed lookup failed for bad network title")
        if seed_input == "unknown title":
            return None
        return make_work(1, title="Resolved Seed Paper")

    monkeypatch.setattr("app.openalex.resolve_seed_work", fake_resolve_seed_work)

    works, warnings = resolve_seed_works(["bad network title", "unknown title", "good title"])

    assert [work["title"] for work in works] == ["Resolved Seed Paper"]
    assert warnings == [
        "Skipped seed 'bad network title': OpenAlex seed lookup failed for bad network title",
        "Skipped seed 'unknown title': no OpenAlex match",
    ]


def test_build_city_from_seed_inputs_continues_with_partial_seed_failures(tmp_path: Path, monkeypatch):
    seed_works = [make_work(1, title="Resolved Climate Seed", topics=[{"display_name": "Climate Change"}])]
    related_works = [
        make_work(idx, title=f"Related Climate Paper {idx}", topics=[{"display_name": "Climate Change"}])
        for idx in range(2, 14)
    ]

    monkeypatch.setattr("app.openalex.resolve_seed_works", lambda seed_inputs: (seed_works, ["Skipped seed 'bad title': no OpenAlex match"]))
    monkeypatch.setattr("app.openalex.fetch_openalex_works", lambda queries, per_query=100, target_total=None, continue_on_error=False: related_works[: target_total or len(related_works)])

    city = build_city_from_seed_inputs(["Resolved Climate Seed", "bad title"], tmp_path, target_total=8)

    assert len(city.vertices) == 8
    assert city.warnings == ["Skipped seed 'bad title': no OpenAlex match"]
    assert city.vertices[0].seeded is True


def test_openalex_selected_fields_do_not_include_invalid_work_fields():
    assert "publisher" not in SELECT_FIELDS.split(",")


def test_top_labels_prioritize_specific_topics_over_broad_domains():
    vertices = [
        normalize_openalex_work(
            make_work(
                idx,
                topics=[{"display_name": "Topic Modeling"}],
                keywords=[
                    {"display_name": "Computer science"},
                    {"display_name": "Artificial intelligence"},
                    {"display_name": "Information retrieval"},
                ],
            ),
            idx,
        )
        for idx in range(1, 4)
    ]

    labels = top_labels(vertices)

    assert labels[0] == "Topic Modeling"
    assert "Computer science" not in labels
    assert "Artificial intelligence" not in labels


def test_floors_split_large_uniform_core_buildings_into_visible_segments():
    vertex_ids = [f"R_{idx:06d}" for idx in range(20)]
    core_numbers = {vertex_id: 8 for vertex_id in vertex_ids}

    floors = build_floors("B_R_0001", vertex_ids, core_numbers, ["Topic Modeling"], 0.5)

    assert len(floors) == 5
    assert sum(floor.node_count for floor in floors) == 20


def test_floors_use_activation_from_assigned_papers():
    old_papers = [
        normalize_openalex_work(make_work(idx, publication_year=2010, cited_by_count=0), idx)
        for idx in range(1, 3)
    ]
    recent_papers = [
        normalize_openalex_work(make_work(idx, publication_year=2026, cited_by_count=200), idx)
        for idx in range(3, 5)
    ]
    vertices = old_papers + recent_papers
    vertex_ids = [vertex.paper_id for vertex in vertices]
    core_numbers = {
        old_papers[0].paper_id: 1,
        old_papers[1].paper_id: 1,
        recent_papers[0].paper_id: 8,
        recent_papers[1].paper_id: 8,
    }
    vertex_by_id = {vertex.paper_id: vertex for vertex in vertices}

    floors = build_floors("B_R_0001", vertex_ids, core_numbers, ["Topic Modeling"], 0.5, vertex_by_id=vertex_by_id)

    assert len(floors) == 2
    assert floors[1].activation_score > floors[0].activation_score
    assert floors[1].activation_score > 0.9


def test_building_height_varies_with_node_count():
    buildings = assign_building_layout(
        [
            {"node_count": 10, "avg_core": 8, "vertex_ids": [], "edge_count": 0, "internal_density": 0, "max_core": 8, "top_labels": [], "profile": {}, "activation_score": 0},
            {"node_count": 50, "avg_core": 8, "vertex_ids": [], "edge_count": 0, "internal_density": 0, "max_core": 8, "top_labels": [], "profile": {}, "activation_score": 0},
        ]
    )

    assert buildings[1]["height"] > buildings[0]["height"]
    assert buildings[1]["footprint"] > buildings[0]["footprint"]


def test_bridge_strength_normalizes_cross_edges_by_building_size():
    left = make_building("B_R_0001", [f"L{i}" for i in range(10)])
    right = make_building("B_R_0002", [f"R{i}" for i in range(10)])
    edges = [
        ResearchEdge(
            source=f"L{idx % 10}",
            target=f"R{idx % 10}",
            edge_weight=0.5,
            components={},
        )
        for idx in range(12)
    ]

    bridges = build_bridges([left, right], edges)

    assert len(bridges) == 1
    assert bridges[0].bridge_strength >= 0.35
    assert bridges[0].components["cross_edge_strength"] == 1.0


def test_dense_cross_edges_can_create_structural_bridge_without_shared_labels():
    left = make_building("B_R_0001", [f"L{i}" for i in range(10)])
    right = make_building("B_R_0002", [f"R{i}" for i in range(10)])
    left.top_labels = ["Topic Modeling"]
    left.profile = {"topics": ["Topic Modeling"], "keywords": [], "methods": [], "datasets": [], "venues": [], "institutions": []}
    right.top_labels = ["Health disparities"]
    right.profile = {"topics": ["Health disparities"], "keywords": [], "methods": [], "datasets": [], "venues": [], "institutions": []}
    edges = [
        ResearchEdge(source=f"L{idx % 10}", target=f"R{idx % 10}", edge_weight=0.5, components={})
        for idx in range(12)
    ]

    bridges = build_bridges([left, right], edges)

    assert len(bridges) == 1
    assert bridges[0].bridge_type == "structural"


def test_streets_do_not_create_layout_fallbacks_without_research_signal():
    buildings = [
        make_positioned_building("B_R_0001", 0, 0),
        make_positioned_building("B_R_0002", 10, 0),
        make_positioned_building("B_R_0003", 25, 0),
        make_positioned_building("B_R_0004", 80, 0),
    ]
    for idx, building in enumerate(buildings):
        building.top_labels = [f"unique label {idx}"]
        building.profile = {"topics": [f"topic {idx}"], "keywords": [], "methods": [], "datasets": [], "venues": [], "institutions": []}

    streets = build_streets(buildings, [], [])

    assert streets == []


def test_research_streets_score_research_relationships_and_skip_bridges():
    first = make_positioned_building("B_R_0001", 0, 0)
    first.vertex_ids = ["A1", "A2", "A3", "A4"]
    first.top_labels = ["topic modeling", "graph neural networks"]
    first.profile = {"topics": ["topic modeling"], "keywords": ["graph"], "methods": [], "datasets": [], "venues": ["Graph Journal"], "institutions": []}
    second = make_positioned_building("B_R_0002", 20, 0)
    second.vertex_ids = ["B1", "B2", "B3", "B4"]
    second.top_labels = ["topic modeling", "language models"]
    second.profile = {"topics": ["topic modeling"], "keywords": ["language models"], "methods": [], "datasets": [], "venues": ["Graph Journal"], "institutions": []}
    third = make_positioned_building("B_R_0003", 80, 0)
    third.vertex_ids = ["C1", "C2", "C3", "C4"]
    third.top_labels = ["education mobility"]
    third.profile = {"topics": ["education mobility"], "keywords": [], "methods": [], "datasets": [], "venues": [], "institutions": []}
    edges = [
        ResearchEdge(source="A1", target="B1", edge_weight=0.8, components={}),
        ResearchEdge(source="B2", target="C1", edge_weight=0.5, components={}),
    ]
    bridges = [
        Bridge(
            bridge_id="BR_R_0001_0002",
            source_building_id="B_R_0001",
            target_building_id="B_R_0002",
            bridge_strength=0.7,
            bridge_type="semantic_structural",
            components={},
        )
    ]

    streets = build_streets([first, second, third], edges, bridges)

    assert all({street.source_building_id, street.target_building_id} != {"B_R_0001", "B_R_0002"} for street in streets)
    assert streets
    assert all(street.street_type in {"research_backbone", "research_neighbor"} for street in streets)
    assert all(street.street_score > 0 for street in streets)
    assert streets[0].components["normalized_cross_edge_count"] > 0
    assert "cross_edges: 1" in streets[0].evidence


def test_semantic_domain_classifies_building_labels_for_color_scheme():
    graph_domain = semantic_domain_for_labels(["Topic Modeling", "Advanced Graph Neural Networks"])
    climate_domain = semantic_domain_for_labels(["Climate Change", "Renewable Energy Sources"])
    health_domain = semantic_domain_for_labels(["Health disparities and outcomes"])

    assert graph_domain["id"] == "graph_ai"
    assert climate_domain["id"] == "climate_energy"
    assert health_domain["id"] == "health_biomedicine"
    assert graph_domain["color"].startswith("#")


def test_communities_do_not_merge_different_semantic_domains_on_strong_bridges():
    graph_building = make_positioned_building("B_R_0001", 0, 0)
    graph_building.top_labels = ["Topic Modeling", "Advanced Graph Neural Networks"]
    graph_building.profile = {"topics": graph_building.top_labels, "keywords": [], "methods": [], "datasets": [], "venues": [], "institutions": []}
    health_building = make_positioned_building("B_R_0002", 20, 0)
    health_building.top_labels = ["Health disparities and outcomes"]
    health_building.profile = {"topics": health_building.top_labels, "keywords": [], "methods": [], "datasets": [], "venues": [], "institutions": []}
    bridge = Bridge(
        bridge_id="BR_R_0001_0002",
        source_building_id="B_R_0001",
        target_building_id="B_R_0002",
        bridge_strength=0.95,
        bridge_type="semantic_structural",
        components={},
    )

    communities = build_communities([graph_building, health_building], [bridge])

    assert len(communities) == 2
    assert {community.semantic_domain for community in communities} == {"graph_ai", "health_biomedicine"}
    assert all(community.color for community in communities)


def test_same_semantic_domain_communities_get_distinct_color_variants():
    buildings = []
    for index, label in enumerate(
        [
            "Topic Modeling",
            "Graph Neural Networks",
            "Knowledge Graph Retrieval",
            "Network Visualization",
        ],
        start=1,
    ):
        building = make_positioned_building(f"B_R_{index:04d}", index * 20, 0)
        building.top_labels = [label, "Graph Methods"]
        building.profile = {"topics": building.top_labels, "keywords": ["graph"], "methods": [], "datasets": [], "venues": [], "institutions": []}
        buildings.append(building)
    bridges = [
        Bridge(
            bridge_id="BR_R_0001_0002",
            source_building_id="B_R_0001",
            target_building_id="B_R_0002",
            bridge_strength=0.95,
            bridge_type="semantic_structural",
            components={},
        ),
        Bridge(
            bridge_id="BR_R_0003_0004",
            source_building_id="B_R_0003",
            target_building_id="B_R_0004",
            bridge_strength=0.95,
            bridge_type="semantic_structural",
            components={},
        ),
    ]

    communities = build_communities(buildings, bridges)

    assert len(communities) == 2
    assert {community.semantic_domain for community in communities} == {"graph_ai"}
    assert len({community.color for community in communities}) == 2
    assert len({building.semantic_color for building in buildings}) == 2


def make_building(building_id: str, vertex_ids: list[str]) -> Building:
    return Building(
        building_id=building_id,
        vertex_ids=vertex_ids,
        node_count=len(vertex_ids),
        edge_count=100,
        internal_density=0.5,
        avg_core=5,
        max_core=8,
        height=40,
        footprint=20,
        x=0,
        z=0,
        top_labels=["research graph city"],
        profile={"topics": ["research graph city"], "keywords": ["city map"], "methods": [], "datasets": [], "venues": [], "institutions": []},
        activation={"score": 0.5},
        activation_score=0.5,
    )


def make_positioned_building(building_id: str, x: float, z: float) -> Building:
    building = make_building(building_id, [f"{building_id}_V1", f"{building_id}_V2"])
    building.x = x
    building.z = z
    return building


class OpenAlexResponse:
    def __init__(self, results: list[dict], next_cursor: str | None):
        self.results = results
        self.next_cursor = next_cursor

    def raise_for_status(self):
        return None

    def json(self):
        return {"results": self.results, "meta": {"next_cursor": self.next_cursor}}


def openalex_response(results: list[dict], next_cursor: str | None) -> OpenAlexResponse:
    return OpenAlexResponse(results, next_cursor)
