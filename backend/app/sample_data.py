from __future__ import annotations

from pathlib import Path

from .graph_processing import build_research_edges, generate_research_city, normalize_openalex_work, write_processed_city
from .schemas import ResearchCity


SHARED_TOPICS = ["research graph city", "openalex literature map"]


def sample_work(idx: int, topic: str, year: int = 2024) -> dict:
    abstract_terms = (
        f"{topic} research graph city openalex literature map graph analysis "
        "community detection visual analytics citation graph"
    )
    return {
        "id": f"https://openalex.org/W900{idx}",
        "doi": f"https://doi.org/10.5555/{idx}",
        "title": f"{topic.title()} Study {idx}",
        "abstract_inverted_index": {word: [pos] for pos, word in enumerate(abstract_terms.split())},
        "publication_year": year,
        "authorships": [
            {
                "author": {"id": f"https://openalex.org/A{idx}", "display_name": f"Author {idx}"},
                "institutions": [{"id": f"https://openalex.org/I{idx // 8}", "display_name": f"Institution {idx // 8}"}],
            }
        ],
        "primary_location": {"source": {"id": f"S{idx // 8}", "display_name": f"Venue {idx // 8}"}},
        "topics": [{"display_name": label} for label in [topic, *SHARED_TOPICS]],
        "keywords": [{"display_name": topic.split()[0]}, {"display_name": "city map"}],
        "referenced_works": [],
        "cited_by_count": 10 + idx,
        "open_access": {"is_oa": True},
    }


def build_sample_city() -> ResearchCity:
    topics = [
        "graph visualization",
        "visual analytics",
        "graphrag",
        "knowledge graph retrieval",
        "education income mobility",
        "causal mobility analysis",
    ]
    works = [
        sample_work(cluster_idx * 8 + item_idx + 1, topic, 2025 - (item_idx % 5))
        for cluster_idx, topic in enumerate(topics)
        for item_idx in range(8)
    ]
    vertices = [normalize_openalex_work(work, idx + 1) for idx, work in enumerate(works)]
    edges = build_research_edges(vertices, top_k=0, threshold=0.55)
    return generate_research_city(vertices, edges, min_building_nodes=5)


def write_sample_city(processed_dir: Path) -> None:
    city = build_sample_city()
    write_processed_city(city, processed_dir)
