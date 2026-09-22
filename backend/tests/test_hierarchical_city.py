from __future__ import annotations

from collections import Counter
import os

import networkx as nx
from sqlalchemy import func, select

from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import Base, create_engine_from_settings, create_session_factory
from app.models import BuildingRecord, BuildingRelationshipRecord, CityPaperRecord, DistrictRecord, FloorRecord, PaperEdgeRecord, PaperRecord
from app.pipeline.city_structure import _community_backbone, assign_unique_primary_labels, floor_bands, relationship_kind
from app.pipeline.city_structure import build_city_structure
from app.pipeline.communities import detect_paper_communities
from app.repositories.postgres_city import PostgresCityRepository


def test_leiden_detects_two_dense_groups_connected_by_a_weak_edge():
    left = [f"L{index}" for index in range(8)]
    right = [f"R{index}" for index in range(8)]
    edges = []
    for group in (left, right):
        edges.extend((group[index], group[(index + 1) % len(group)], 1.0) for index in range(len(group)))
        edges.extend((group[index], group[(index + 2) % len(group)], 0.8) for index in range(len(group)))
    edges.append((left[0], right[0], 0.01))

    assignments = detect_paper_communities(left + right, edges, seed=42, iterations=2)

    assert len({assignments[node] for node in left}) == 1
    assert len({assignments[node] for node in right}) == 1
    assert assignments[left[0]] != assignments[right[0]]


def test_oversized_dense_community_does_not_fragment_into_many_buildings():
    nodes = [f"W{index:03d}" for index in range(100)]
    edges = [
        (source, target, 1.0)
        for index, source in enumerate(nodes)
        for target in nodes[index + 1 :]
    ]

    assignments = detect_paper_communities(nodes, edges, seed=42, max_building_size=50)
    sizes = Counter(assignments.values())

    assert len(sizes) <= 4
    assert max(sizes.values()) <= 50


def test_floor_bands_create_between_one_and_five_nonempty_core_ranges():
    bands = floor_bands({f"W{index}": index for index in range(20)}, max_floors=5)

    assert 1 <= len(bands) <= 5
    assert sum(len(node_ids) for _, _, node_ids in bands) == 20
    assert all(node_ids for _, _, node_ids in bands)


def test_building_primary_labels_are_specific_and_unique_when_possible():
    candidates = [
        ["Computer Science", "Graph Neural Networks", "Representation Learning"],
        ["Computer Science", "Graph Neural Networks", "Molecular Graphs"],
        ["Computer Science", "Graph Neural Networks", "Citation Networks"],
    ]

    labels = assign_unique_primary_labels(candidates)

    assert labels == ["Graph Neural Networks", "Molecular Graphs", "Citation Networks"]


def test_relationship_classification_never_presents_zero_score_as_research():
    assert relationship_kind(0.52, bridge_threshold=0.35, street_threshold=0.08) == "bridge"
    assert relationship_kind(0.2, bridge_threshold=0.35, street_threshold=0.08) == "street"
    assert relationship_kind(0.0, bridge_threshold=0.35, street_threshold=0.08) is None


def test_community_backbone_caps_similarity_degree_but_keeps_citations():
    edges = [
        ("W0", f"W{index}", 1.0 - index * 0.1, "similarity", [])
        for index in range(1, 6)
    ]
    edges.append(("W0", "W6", 0.01, "citation", ["citation"]))

    backbone = _community_backbone(edges, max_similarity_degree=2)

    similarity = [edge for edge in backbone if edge[3] == "similarity"]
    assert len(similarity) == 2
    assert any(edge[3] == "citation" and {edge[0], edge[1]} == {"W0", "W6"} for edge in backbone)


def test_community_backbone_distributes_equal_weight_edges_across_nodes():
    nodes = [f"W{index:02d}" for index in range(20)]
    edges = [
        (source, target, 0.5, "similarity", [])
        for index, source in enumerate(nodes)
        for target in nodes[index + 1 :]
    ]

    backbone = _community_backbone(edges, max_similarity_degree=4)
    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from((edge[0], edge[1]) for edge in backbone)

    assert nx.is_connected(graph)
    assert max(dict(graph.degree()).values()) <= 4


def test_city_structure_persists_hierarchy_and_evidence_relationships():
    settings = Settings(
        database_url=os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_backend="postgres",
        worker_poll_seconds=1.0,
        job_stale_seconds=300,
        embedding_model="hashing-64-v1",
    )
    engine = create_engine_from_settings(settings)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    repository = PostgresCityRepository(factory)
    city, _ = repository.create_city("Hierarchy", ["seed"], 12)
    try:
        with factory.begin() as session:
            for index in range(12):
                paper_id = f"W{index:03d}"
                topic = "Graph Learning" if index < 6 else "Public Health"
                paper = PaperRecord(openalex_id=paper_id, title=f"{topic} {index}", topics=[topic], publication_year=2024)
                session.add(paper)
                session.flush([paper])
                session.add(CityPaperRecord(city_id=city.id, openalex_id=paper_id, external_paper_id=f"P_{index:04d}"))
            for start in (0, 6):
                for offset in range(6):
                    source = f"W{start + offset:03d}"
                    target = f"W{start + ((offset + 1) % 6):03d}"
                    session.add(PaperEdgeRecord(city_id=city.id, source_openalex_id=min(source, target), target_openalex_id=max(source, target), edge_type="similarity", weight=0.9, components={}, evidence=["internal"], directed=False))
            session.add(PaperEdgeRecord(city_id=city.id, source_openalex_id="W000", target_openalex_id="W006", edge_type="citation", weight=1.0, components={"citation": 1.0}, evidence=["cross citation"], directed=True))

        counts = build_city_structure(city.id, repository, min_building_size=3)
        rebuilt_counts = build_city_structure(city.id, repository, min_building_size=3)

        with factory() as session:
            assert counts["buildings"] == 2
            assert rebuilt_counts == counts
            assert session.scalar(select(func.count()).select_from(DistrictRecord)) == 2
            buildings = session.scalars(select(BuildingRecord).order_by(BuildingRecord.external_id)).all()
            assert len({building.top_labels[0] for building in buildings}) == 2
            floors = session.scalars(select(FloorRecord)).all()
            assert all(1 <= floor.floor_index <= 5 for floor in floors)
            relationships = session.scalars(select(BuildingRelationshipRecord)).all()
            assert relationships
            assert all(item.score > 0 and any("paper_edge" in value for value in item.evidence) for item in relationships)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
