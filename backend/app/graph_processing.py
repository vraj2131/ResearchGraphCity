from __future__ import annotations

import colorsys
from collections import Counter, defaultdict
from itertools import combinations
from math import exp, sqrt
from statistics import mean
from typing import Iterable

import networkx as nx
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .schemas import Bridge, Building, Community, Floor, ResearchCity, ResearchEdge, ResearchVertex, Street


SEED_QUERIES = ["graph visualization", "GraphRAG", "education income mobility"]
PALETTE = [
    "#4f8cff",
    "#ff6b6b",
    "#42b883",
    "#f7b801",
    "#9b5de5",
    "#00bbf9",
    "#f15bb5",
    "#6a994e",
    "#e76f51",
    "#577590",
]
SEMANTIC_DOMAINS = [
    {
        "id": "graph_ai",
        "name": "Graph, AI, and Computation",
        "color": "#6ee7f9",
        "terms": [
            "artificial intelligence",
            "attention",
            "comput",
            "data visualization",
            "domain adaptation",
            "explainable",
            "few-shot",
            "graph",
            "knowledge graph",
            "language model",
            "machine learning",
            "network",
            "neural",
            "topic model",
            "visualization",
        ],
    },
    {
        "id": "health_biomedicine",
        "name": "Health and Biomedicine",
        "color": "#34d399",
        "terms": [
            "bioinformatics",
            "biomed",
            "cancer",
            "clinical",
            "disease",
            "genomic",
            "health",
            "medicine",
            "patient",
            "phylogenetic",
            "protein",
            "single-cell",
            "transcriptomic",
        ],
    },
    {
        "id": "climate_energy",
        "name": "Climate and Energy",
        "color": "#facc15",
        "terms": [
            "carbon",
            "climate",
            "ecolog",
            "emission",
            "energy",
            "environment",
            "food security",
            "global warming",
            "renewable",
            "sustainab",
        ],
    },
    {
        "id": "economics_policy",
        "name": "Economics and Policy",
        "color": "#fb923c",
        "terms": [
            "economic",
            "economics",
            "fiscal",
            "income",
            "innovation",
            "market",
            "mobility",
            "policy",
            "trade",
        ],
    },
    {
        "id": "education_society",
        "name": "Education and Society",
        "color": "#f472b6",
        "terms": [
            "education",
            "equity",
            "inequality",
            "mobility",
            "school",
            "social",
            "sociology",
            "student",
        ],
    },
    {
        "id": "physical_sciences",
        "name": "Physical Sciences",
        "color": "#a78bfa",
        "terms": [
            "astronomy",
            "galax",
            "material",
            "physics",
            "quantum",
            "space",
        ],
    },
]
DEFAULT_SEMANTIC_DOMAIN = {"id": "general", "name": "General Research", "color": "#94a3b8", "terms": []}
BROAD_LABELS = {
    "artificial intelligence",
    "biology",
    "business",
    "chemistry",
    "computer science",
    "data science",
    "disease",
    "economics",
    "engineering",
    "environmental health",
    "field (mathematics)",
    "genetics",
    "health care",
    "internal medicine",
    "mathematics",
    "medicine",
    "political science",
    "psychology",
    "public health",
    "sociology",
    "software",
}


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = {item for item in left if item}
    right_set = {item for item in right if item}
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def normalize_openalex_work(work: dict, index: int) -> ResearchVertex:
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    authors: list[str] = []
    author_ids: list[str] = []
    institutions: list[str] = []
    institution_ids: list[str] = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        if author.get("display_name"):
            authors.append(author["display_name"])
        if author.get("id"):
            author_ids.append(author["id"])
        for institution in authorship.get("institutions") or []:
            if institution.get("display_name"):
                institutions.append(institution["display_name"])
            if institution.get("id"):
                institution_ids.append(institution["id"])
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    topics = [topic.get("display_name", "") for topic in work.get("topics") or []]
    keywords = [kw.get("display_name", "") for kw in work.get("keywords") or []]
    doi = work.get("doi")
    if isinstance(doi, str) and doi.startswith("https://doi.org/"):
        doi = doi.removeprefix("https://doi.org/")
    return ResearchVertex(
        paper_id=f"R_{index:06d}",
        openalex_id=work.get("id", ""),
        doi=doi,
        title=work.get("title") or "Untitled work",
        abstract=abstract,
        publication_year=work.get("publication_year"),
        authors=dedupe(authors),
        author_ids=dedupe(author_ids),
        institutions=dedupe(institutions),
        institution_ids=dedupe(institution_ids),
        venue=source.get("display_name") or "",
        publisher=(work.get("publisher") or ""),
        topics=dedupe([topic for topic in topics if topic]),
        keywords=dedupe([kw for kw in keywords if kw]),
        methods=extract_terms((work.get("title") or "") + " " + abstract, method_terms()),
        datasets=extract_terms((work.get("title") or "") + " " + abstract, dataset_terms()),
        referenced_paper_ids=work.get("referenced_works") or [],
        citation_count=int(work.get("cited_by_count") or 0),
        open_access=bool((work.get("open_access") or {}).get("is_oa", False)),
        data_available=has_any((work.get("title") or "") + " " + abstract, ["dataset", "data availability", "open data"]),
        code_available=has_any((work.get("title") or "") + " " + abstract, ["github", "source code", "code available"]),
    )


def reconstruct_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions:
            words.append((position, word))
    return " ".join(word for _, word in sorted(words))


def build_research_edges(
    vertices: list[ResearchVertex],
    top_k: int = 8,
    threshold: float = 0.45,
) -> list[ResearchEdge]:
    vertices = with_tfidf_embeddings(vertices)
    text_similarity = build_similarity_lookup(vertices)
    nearest_pairs = top_nearest_pairs(vertices, text_similarity, top_k)
    edges: list[ResearchEdge] = []
    for left, right in combinations(vertices, 2):
        components = research_edge_components(left, right, text_similarity)
        weight = research_edge_weight(components)
        cited = is_direct_citation(left, right)
        is_nearest = tuple(sorted((left.paper_id, right.paper_id))) in nearest_pairs
        if weight >= threshold or cited or is_nearest:
            evidence = edge_evidence(left, right, components, cited, is_nearest)
            edges.append(
                ResearchEdge(
                    source=left.paper_id,
                    target=right.paper_id,
                    edge_weight=weight,
                    components=components,
                    evidence=evidence,
                    directed_citation=cited,
                )
            )
    return edges


def research_edge_components(
    left: ResearchVertex,
    right: ResearchVertex,
    text_similarity_lookup: dict[tuple[str, str], float] | None = None,
) -> dict[str, float]:
    pair = tuple(sorted((left.paper_id, right.paper_id)))
    references_left = set(left.referenced_paper_ids)
    references_right = set(right.referenced_paper_ids)
    direct_citation = is_direct_citation(left, right)
    citation = 1.0 if direct_citation else jaccard(references_left, references_right)
    text_similarity = 0.0
    if text_similarity_lookup is not None:
        text_similarity = text_similarity_lookup.get(pair, 0.0)
    elif left.embedding and right.embedding:
        text_similarity = cosine(left.embedding, right.embedding)
    return {
        "topic_similarity": round(jaccard(left.topics, right.topics), 4),
        "text_similarity": round(text_similarity, 4),
        "citation": round(citation, 4),
        "method_dataset_overlap": round(0.5 * jaccard(left.methods, right.methods) + 0.5 * jaccard(left.datasets, right.datasets), 4),
        "author_institution_overlap": round(0.5 * jaccard(left.author_ids, right.author_ids) + 0.5 * jaccard(left.institution_ids, right.institution_ids), 4),
        "venue_similarity": 1.0 if left.venue and left.venue == right.venue else 0.0,
        "time_proximity": round(time_proximity(left.publication_year, right.publication_year), 4),
    }


def research_edge_weight(components: dict[str, float]) -> float:
    weight = (
        0.25 * components["topic_similarity"]
        + 0.25 * components["text_similarity"]
        + 0.20 * components["citation"]
        + 0.10 * components["method_dataset_overlap"]
        + 0.10 * components["author_institution_overlap"]
        + 0.05 * components["venue_similarity"]
        + 0.05 * components["time_proximity"]
    )
    return round(weight, 4)


def generate_research_city(
    vertices: list[ResearchVertex],
    edges: list[ResearchEdge],
    min_building_nodes: int = 8,
) -> ResearchCity:
    graph = nx.Graph()
    for vertex in vertices:
        graph.add_node(vertex.paper_id)
    for edge in edges:
        graph.add_edge(edge.source, edge.target, weight=edge.edge_weight)
    non_isolates = [node for node, degree in graph.degree() if degree > 0]
    outskirts = [node for node, degree in graph.degree() if degree == 0]
    active_graph = graph.subgraph(non_isolates).copy()
    if active_graph.number_of_nodes() == 0:
        return ResearchCity(vertices=vertices, edges=edges, buildings=[], floors=[], bridges=[], streets=[], communities=[], outskirts=outskirts)
    core_numbers = nx.core_number(active_graph) if active_graph.number_of_edges() else {node: 0 for node in active_graph.nodes}
    partition = community_partition(active_graph)
    vertex_by_id = {vertex.paper_id: vertex for vertex in vertices}
    raw_buildings: list[dict] = []
    bushes: list[str] = []
    for community_id, node_ids in sorted(partition.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(node_ids) < min_building_nodes:
            bushes.extend(node_ids)
            continue
        subgraph = active_graph.subgraph(node_ids).copy()
        internal_edges = subgraph.number_of_edges()
        density = nx.density(subgraph) if len(node_ids) > 1 else 0.0
        avg_core = mean(core_numbers[node] for node in node_ids)
        max_core = max(core_numbers[node] for node in node_ids)
        raw_buildings.append(
            {
                "community_seed": community_id,
                "vertex_ids": sorted(node_ids),
                "node_count": len(node_ids),
                "edge_count": internal_edges,
                "internal_density": density,
                "avg_core": avg_core,
                "max_core": max_core,
                "top_labels": top_labels(vertex_by_id[node] for node in node_ids),
                "profile": building_profile(vertex_by_id[node] for node in node_ids),
                "original_labels": original_labels(vertex_by_id[node] for node in node_ids),
                "activation_score": activation_score(vertex_by_id[node] for node in node_ids),
            }
        )
    outskirts.extend(bushes)
    raw_buildings = ensure_minimum_buildings(raw_buildings, active_graph, vertex_by_id, core_numbers, min_building_nodes)
    positioned = assign_building_layout(raw_buildings)
    buildings = [
        build_building(idx + 1, raw, core_numbers, vertex_by_id)
        for idx, raw in enumerate(positioned)
    ]
    floors = [floor for building in buildings for floor in building.floors]
    bridges = build_bridges(buildings, edges)
    streets = build_streets(buildings, edges, bridges)
    communities = build_communities(buildings, bridges)
    community_by_building = {
        building_id: community.community_id
        for community in communities
        for building_id in community.building_ids
    }
    for building in buildings:
        building.community_id = community_by_building.get(building.building_id)
    return ResearchCity(
        vertices=vertices,
        edges=edges,
        buildings=buildings,
        floors=floors,
        bridges=bridges,
        streets=streets,
        communities=communities,
        outskirts=sorted(set(outskirts)),
    )


def build_streets(buildings: list[Building], edges: list[ResearchEdge] | None = None, bridges: list[Bridge] | None = None) -> list[Street]:
    if len(buildings) < 2:
        return []
    edges = edges or []
    bridges = bridges or []
    bridge_pairs = {
        tuple(sorted((bridge.source_building_id, bridge.target_building_id)))
        for bridge in bridges
    }
    building_lookup = {building.building_id: building for building in buildings}
    building_by_vertex = {
        vertex_id: building.building_id
        for building in buildings
        for vertex_id in building.vertex_ids
    }
    cross_edges: dict[tuple[str, str], list[ResearchEdge]] = defaultdict(list)
    for edge in edges:
        source_building = building_by_vertex.get(edge.source)
        target_building = building_by_vertex.get(edge.target)
        if not source_building or not target_building or source_building == target_building:
            continue
        key = tuple(sorted((source_building, target_building)))
        if key not in bridge_pairs:
            cross_edges[key].append(edge)

    candidates: dict[tuple[str, str], tuple[float, dict[str, float], list[str], bool]] = {}
    for left, right in combinations(buildings, 2):
        key = tuple(sorted((left.building_id, right.building_id)))
        if key in bridge_pairs:
            continue
        connecting_edges = cross_edges.get(key, [])
        components = research_street_components(left, right, connecting_edges)
        score = research_street_score(components)
        has_research_signal = score > 0
        candidates[key] = (score, components, street_evidence(left, right, connecting_edges, has_research_signal), has_research_signal)

    selected: dict[tuple[str, str], str] = {}
    research_graph = nx.Graph()
    for building in buildings:
        research_graph.add_node(building.building_id)
    for (source_id, target_id), (score, _, _, has_research_signal) in candidates.items():
        if has_research_signal:
            research_graph.add_edge(source_id, target_id, weight=score)
    for source, target in nx.maximum_spanning_edges(research_graph, data=False):
        selected[tuple(sorted((source, target)))] = "research_backbone"
    for building in buildings:
        research_neighbors = [
            (score, pair)
            for pair, (score, _, _, has_research_signal) in candidates.items()
            if has_research_signal and building.building_id in pair
        ]
        if research_neighbors:
            _, pair = max(research_neighbors, key=lambda item: (item[0], item[1]))
            selected.setdefault(pair, "research_neighbor")
    streets: list[Street] = []
    for (source_id, target_id), street_type in sorted(selected.items()):
        source = building_lookup[source_id]
        target = building_lookup[target_id]
        score, components, evidence, _ = candidates[(source_id, target_id)]
        final_evidence = [street_type]
        final_evidence.extend(evidence)
        streets.append(
            Street(
                street_id=f"ST_R_{source_id[-4:]}_{target_id[-4:]}",
                source_building_id=source_id,
                target_building_id=target_id,
                street_type=street_type,
                distance=round(building_distance(source, target), 4),
                street_score=score,
                components=components,
                evidence=final_evidence,
            )
        )
    return streets


def research_street_components(left: Building, right: Building, connecting_edges: list[ResearchEdge]) -> dict[str, float]:
    denom = sqrt(max(1, left.node_count) * max(1, right.node_count))
    normalized_cross_edge_count = min(1.0, len(connecting_edges) / denom)
    shared_label_similarity = jaccard(left.top_labels, right.top_labels)
    semantic_similarity = 0.5 * shared_label_similarity + 0.5 * profile_text_similarity(left, right)
    return {
        "normalized_cross_edge_count": round(normalized_cross_edge_count, 4),
        "profile_similarity": round(profile_similarity_research(left, right), 4),
        "shared_label_similarity": round(shared_label_similarity, 4),
        "semantic_similarity": round(semantic_similarity, 4),
    }


def research_street_score(components: dict[str, float]) -> float:
    return round(
        0.45 * components["normalized_cross_edge_count"]
        + 0.25 * components["profile_similarity"]
        + 0.20 * components["shared_label_similarity"]
        + 0.10 * components["semantic_similarity"],
        4,
    )


def street_evidence(left: Building, right: Building, connecting_edges: list[ResearchEdge], has_research_signal: bool) -> list[str]:
    if not has_research_signal:
        return []
    evidence = [f"cross_edges: {len(connecting_edges)}"] if connecting_edges else []
    shared = set(left.top_labels) & set(right.top_labels)
    evidence.extend(f"shared_label: {label}" for label in sorted(shared)[:3])
    if profile_similarity_research(left, right) > 0:
        evidence.append("profile_overlap")
    if profile_text_similarity(left, right) > 0:
        evidence.append("semantic_profile_overlap")
    return evidence


def building_distance(left: Building, right: Building) -> float:
    dx = right.x - left.x
    dz = right.z - left.z
    return sqrt(dx * dx + dz * dz)


def build_bridges(buildings: list[Building], edges: list[ResearchEdge]) -> list[Bridge]:
    building_by_vertex = {
        vertex_id: building.building_id
        for building in buildings
        for vertex_id in building.vertex_ids
    }
    cross_edges: dict[tuple[str, str], list[ResearchEdge]] = defaultdict(list)
    for edge in edges:
        source_building = building_by_vertex.get(edge.source)
        target_building = building_by_vertex.get(edge.target)
        if not source_building or not target_building or source_building == target_building:
            continue
        cross_edges[tuple(sorted((source_building, target_building)))].append(edge)
    building_lookup = {building.building_id: building for building in buildings}
    bridges: list[Bridge] = []
    for left, right in combinations(buildings, 2):
        key = tuple(sorted((left.building_id, right.building_id)))
        connecting_edges = cross_edges.get(key, [])
        profile_similarity = profile_similarity_research(left, right)
        semantic_similarity = 0.5 * jaccard(left.top_labels, right.top_labels) + 0.5 * profile_text_similarity(left, right)
        cross_edge_strength = 0.0
        if connecting_edges:
            denom = sqrt(max(1, left.node_count) * max(1, right.node_count))
            cross_edge_strength = min(1.0, len(connecting_edges) / denom)
        activation_similarity = 1 - abs(left.activation_score - right.activation_score)
        components = {
            "profile_similarity": round(profile_similarity, 4),
            "semantic_similarity": round(semantic_similarity, 4),
            "cross_edge_strength": round(cross_edge_strength, 4),
            "vertex_overlap": 0.0,
            "activation_similarity": round(activation_similarity, 4),
            "llm_confidence": 0.5,
        }
        strength = round(
            0.25 * components["profile_similarity"]
            + 0.25 * components["semantic_similarity"]
            + 0.25 * components["cross_edge_strength"]
            + 0.10 * components["vertex_overlap"]
            + 0.10 * components["activation_similarity"]
            + 0.05 * components["llm_confidence"],
            4,
        )
        if strength < 0.35:
            continue
        evidence = [f"cross_edges: {len(connecting_edges)}"] if connecting_edges else []
        shared = set(left.top_labels) & set(right.top_labels)
        evidence.extend(f"shared_label: {label}" for label in sorted(shared)[:3])
        bridges.append(
            Bridge(
                bridge_id=f"BR_R_{left.building_id[-4:]}_{right.building_id[-4:]}",
                source_building_id=left.building_id,
                target_building_id=right.building_id,
                bridge_strength=strength,
                bridge_type="semantic_structural" if semantic_similarity >= 0.5 else "structural",
                components=components,
                evidence=evidence,
                activation_score=round((left.activation_score + right.activation_score) / 2, 4),
            )
        )
    return bridges


def build_communities(buildings: list[Building], bridges: list[Bridge]) -> list[Community]:
    building_lookup = {building.building_id: building for building in buildings}
    for building in buildings:
        domain = semantic_domain_for_building(building)
        building.semantic_domain = domain["id"]
        building.semantic_domain_name = domain["name"]
        building.semantic_color = domain["color"]

    groups: list[set[str]] = []
    buildings_by_domain: dict[str, list[Building]] = defaultdict(list)
    for building in buildings:
        buildings_by_domain[building.semantic_domain].append(building)

    for domain_id, domain_buildings in sorted(buildings_by_domain.items()):
        domain_graph = nx.Graph()
        domain_ids = {building.building_id for building in domain_buildings}
        for building in domain_buildings:
            domain_graph.add_node(building.building_id)
        for bridge in bridges:
            if bridge.bridge_strength < 0.5:
                continue
            if bridge.source_building_id in domain_ids and bridge.target_building_id in domain_ids:
                domain_graph.add_edge(bridge.source_building_id, bridge.target_building_id, weight=bridge.bridge_strength)
        if domain_graph.number_of_edges() > 0 and len(domain_buildings) > 2:
            groups.extend(set(group) for group in nx.community.greedy_modularity_communities(domain_graph, weight="weight"))
        else:
            groups.append(set(domain_ids))

    communities: list[Community] = []
    domain_counts: dict[str, int] = defaultdict(int)
    for idx, group in enumerate(groups, start=1):
        group_buildings = [building_lookup[building_id] for building_id in sorted(group)]
        labels = top_list([label for building in group_buildings for label in building.top_labels], 4)
        domain = semantic_domain_for_building(group_buildings[0]) if group_buildings else DEFAULT_SEMANTIC_DOMAIN
        domain_variant_index = domain_counts[domain["id"]]
        domain_counts[domain["id"]] += 1
        color = semantic_color_variant(domain["color"], domain_variant_index)
        for building in group_buildings:
            building.semantic_color = color
        communities.append(
            Community(
                community_id=f"C_R_{idx:04d}",
                name=", ".join(labels[:2]) if labels else domain["name"],
                building_ids=[building.building_id for building in group_buildings],
                top_labels=labels,
                semantic_domain=domain["id"],
                semantic_domain_name=domain["name"],
                metrics={
                    "intra_cluster_similarity": average_bridge_strength(group, bridges),
                    "inter_cluster_separation": 1.0,
                    "attribute_coherence": 1.0 if len(labels) > 0 else 0.0,
                    "label_coherence": label_coherence(group_buildings),
                    "cluster_stability": 1.0,
                },
                color=color,
            )
        )
    return communities


def write_processed_city(city: ResearchCity, processed_dir, prefix: str = "research") -> None:
    from .storage import write_json

    write_json(processed_dir / f"{prefix}_vertices.json", [item.model_dump(mode="json") for item in city.vertices])
    write_json(processed_dir / f"{prefix}_edges.json", [item.model_dump(mode="json") for item in city.edges])
    write_json(processed_dir / f"{prefix}_buildings.json", [item.model_dump(mode="json") for item in city.buildings])
    write_json(processed_dir / f"{prefix}_floors.json", [item.model_dump(mode="json") for item in city.floors])
    write_json(processed_dir / f"{prefix}_bridges.json", [item.model_dump(mode="json") for item in city.bridges])
    write_json(processed_dir / f"{prefix}_streets.json", [item.model_dump(mode="json") for item in city.streets])
    write_json(processed_dir / f"{prefix}_communities.json", [item.model_dump(mode="json") for item in city.communities])


def with_tfidf_embeddings(vertices: list[ResearchVertex]) -> list[ResearchVertex]:
    documents = [(vertex.title + " " + vertex.abstract).strip() or vertex.title for vertex in vertices]
    if not documents:
        return vertices
    matrix = TfidfVectorizer(max_features=64, stop_words="english").fit_transform(documents).toarray()
    for vertex, row in zip(vertices, matrix):
        vertex.embedding = [round(float(value), 6) for value in row]
    return vertices


def build_similarity_lookup(vertices: list[ResearchVertex]) -> dict[tuple[str, str], float]:
    if not vertices or not vertices[0].embedding:
        return {}
    matrix = np.array([vertex.embedding for vertex in vertices])
    similarities = cosine_similarity(matrix)
    lookup: dict[tuple[str, str], float] = {}
    for left_idx, right_idx in combinations(range(len(vertices)), 2):
        pair = tuple(sorted((vertices[left_idx].paper_id, vertices[right_idx].paper_id)))
        lookup[pair] = float(similarities[left_idx][right_idx])
    return lookup


def top_nearest_pairs(vertices: list[ResearchVertex], lookup: dict[tuple[str, str], float], top_k: int) -> set[tuple[str, str]]:
    if top_k <= 0:
        return set()
    pairs: set[tuple[str, str]] = set()
    for vertex in vertices:
        scores = []
        for other in vertices:
            if vertex.paper_id == other.paper_id:
                continue
            pair = tuple(sorted((vertex.paper_id, other.paper_id)))
            scores.append((lookup.get(pair, 0.0), pair))
        scores.sort(reverse=True)
        pairs.update(pair for _, pair in scores[:top_k])
    return pairs


def community_partition(graph: nx.Graph) -> dict[int, set[str]]:
    try:
        communities = nx.community.louvain_communities(graph, weight="weight", seed=42)
    except Exception:
        communities = nx.community.greedy_modularity_communities(graph, weight="weight")
    return {idx: set(group) for idx, group in enumerate(communities)}


def ensure_minimum_buildings(raw_buildings, graph, vertex_by_id, core_numbers, min_building_nodes):
    if len(raw_buildings) >= 2:
        return raw_buildings
    components = sorted(nx.connected_components(graph), key=len, reverse=True)
    rebuilt = []
    for component in components:
        nodes = sorted(component)
        if len(nodes) < min_building_nodes:
            continue
        midpoint = max(min_building_nodes, len(nodes) // 2)
        for chunk in (nodes[:midpoint], nodes[midpoint:]):
            if len(chunk) < min_building_nodes:
                continue
            subgraph = graph.subgraph(chunk)
            rebuilt.append(
                {
                    "community_seed": len(rebuilt),
                    "vertex_ids": chunk,
                    "node_count": len(chunk),
                    "edge_count": subgraph.number_of_edges(),
                    "internal_density": nx.density(subgraph) if len(chunk) > 1 else 0.0,
                    "avg_core": mean(core_numbers[node] for node in chunk),
                    "max_core": max(core_numbers[node] for node in chunk),
                    "top_labels": top_labels(vertex_by_id[node] for node in chunk),
                    "profile": building_profile(vertex_by_id[node] for node in chunk),
                    "original_labels": original_labels(vertex_by_id[node] for node in chunk),
                    "activation_score": activation_score(vertex_by_id[node] for node in chunk),
                }
            )
    return rebuilt or raw_buildings


def assign_building_layout(raw_buildings: list[dict]) -> list[dict]:
    count = len(raw_buildings)
    if count == 0:
        return []
    graph = nx.Graph()
    for idx in range(count):
        graph.add_node(idx)
    positions = nx.spring_layout(graph, seed=42) if count > 1 else {0: np.array([0.0, 0.0])}
    max_nodes = max(raw["node_count"] for raw in raw_buildings)
    min_nodes = min(raw["node_count"] for raw in raw_buildings)
    for idx, raw in enumerate(raw_buildings):
        node_norm = normalize(raw["node_count"], min_nodes, max_nodes)
        raw["height"] = round(24 + 86 * node_norm, 4)
        raw["footprint"] = round(6 + 28 * sqrt(raw["node_count"] / max_nodes), 4)
        pos = positions[idx]
        raw["x"] = round(float(pos[0]) * 500, 4)
        raw["z"] = round(float(pos[1]) * 500, 4)
    return adjust_collisions(raw_buildings)


def adjust_collisions(buildings: list[dict]) -> list[dict]:
    for _ in range(50):
        for left, right in combinations(buildings, 2):
            dx = right["x"] - left["x"]
            dz = right["z"] - left["z"]
            distance = sqrt(dx * dx + dz * dz) or 0.001
            minimum = 0.65 * (left["footprint"] + right["footprint"])
            if distance >= minimum:
                continue
            push = (minimum - distance) / 2
            ux, uz = dx / distance, dz / distance
            left["x"] -= ux * push
            left["z"] -= uz * push
            right["x"] += ux * push
            right["z"] += uz * push
    for building in buildings:
        building["x"] = round(building["x"], 4)
        building["z"] = round(building["z"], 4)
    return buildings


def build_building(index: int, raw: dict, core_numbers: dict[str, int], vertex_by_id: dict[str, ResearchVertex] | None = None) -> Building:
    building_id = f"B_R_{index:04d}"
    floors = build_floors(building_id, raw["vertex_ids"], core_numbers, raw["top_labels"], raw["activation_score"], vertex_by_id=vertex_by_id)
    domain = semantic_domain_for_labels(raw["top_labels"] + list(raw.get("profile", {}).get("topics", [])) + list(raw.get("profile", {}).get("keywords", [])))
    return Building(
        building_id=building_id,
        vertex_ids=raw["vertex_ids"],
        node_count=raw["node_count"],
        edge_count=raw["edge_count"],
        internal_density=round(raw["internal_density"], 4),
        avg_core=round(raw["avg_core"], 4),
        max_core=raw["max_core"],
        height=raw["height"],
        footprint=raw["footprint"],
        x=raw["x"],
        z=raw["z"],
        top_labels=raw["top_labels"],
        semantic_domain=domain["id"],
        semantic_domain_name=domain["name"],
        semantic_color=domain["color"],
        profile=raw["profile"],
        original_labels=raw.get("original_labels", {}),
        activation={"score": raw["activation_score"], "recency": raw["activation_score"], "persistence": 1.0},
        activation_score=raw["activation_score"],
        floors=floors,
    )


def build_floors(
    building_id: str,
    vertex_ids: list[str],
    core_numbers: dict[str, int],
    labels: list[str],
    activation: float,
    vertex_by_id: dict[str, ResearchVertex] | None = None,
) -> list[Floor]:
    values = sorted({core_numbers[vertex_id] for vertex_id in vertex_ids})
    if not values:
        values = [0]
    if len(values) == 1 and len(vertex_ids) > 5:
        floors = []
        chunks = np.array_split(sorted(vertex_ids), min(5, len(vertex_ids)))
        for idx, chunk in enumerate(chunks, start=1):
            floor_vertices = [str(vertex_id) for vertex_id in chunk]
            floors.append(
                Floor(
                    floor_id=f"F_{building_id}_{idx:02d}",
                    building_id=building_id,
                    floor_index=idx,
                    core_range=(values[0], values[0]),
                    vertex_ids=floor_vertices,
                    node_count=len(floor_vertices),
                    top_labels=labels[:3],
                    activation_score=floor_activation_score(floor_vertices, vertex_by_id, activation),
                )
            )
        return floors
    bins = np.array_split(values, min(5, len(values)))
    floors: list[Floor] = []
    for idx, band in enumerate(bins, start=1):
        low, high = int(min(band)), int(max(band))
        floor_vertices = [vertex_id for vertex_id in vertex_ids if low <= core_numbers[vertex_id] <= high]
        floors.append(
            Floor(
                floor_id=f"F_{building_id}_{idx:02d}",
                building_id=building_id,
                floor_index=idx,
                core_range=(low, high),
                vertex_ids=floor_vertices,
                node_count=len(floor_vertices),
                top_labels=labels[:3],
                activation_score=floor_activation_score(floor_vertices, vertex_by_id, activation),
            )
        )
    return floors


def floor_activation_score(vertex_ids: list[str], vertex_by_id: dict[str, ResearchVertex] | None, fallback: float) -> float:
    if not vertex_by_id:
        return fallback
    vertices = [vertex_by_id[vertex_id] for vertex_id in vertex_ids if vertex_id in vertex_by_id]
    if not vertices:
        return fallback
    return activation_score(vertices)


def profile_similarity_research(left: Building, right: Building) -> float:
    lp, rp = left.profile, right.profile
    return round(
        0.30 * jaccard(lp.get("topics", []), rp.get("topics", []))
        + 0.20 * jaccard(lp.get("methods", []), rp.get("methods", []))
        + 0.15 * jaccard(lp.get("datasets", []), rp.get("datasets", []))
        + 0.15 * 0.0
        + 0.10 * jaccard(lp.get("venues", []), rp.get("venues", []))
        + 0.10 * jaccard(lp.get("institutions", []), rp.get("institutions", [])),
        4,
    )


def profile_text_similarity(left: Building, right: Building) -> float:
    return jaccard(left.profile.get("topics", []) + left.profile.get("keywords", []), right.profile.get("topics", []) + right.profile.get("keywords", []))


def semantic_domain_for_building(building: Building) -> dict[str, str]:
    labels = list(building.top_labels)
    labels.extend(str(label) for label in building.profile.get("topics", []) if label)
    labels.extend(str(label) for label in building.profile.get("keywords", []) if label)
    labels.extend(str(label) for label in building.profile.get("methods", []) if label)
    labels.extend(str(label) for label in building.profile.get("datasets", []) if label)
    return semantic_domain_for_labels(labels)


def semantic_domain_for_labels(labels: Iterable[str]) -> dict[str, str]:
    text = " ".join(label.lower() for label in labels if label)
    if not text:
        return {key: str(value) for key, value in DEFAULT_SEMANTIC_DOMAIN.items() if key != "terms"}
    best = DEFAULT_SEMANTIC_DOMAIN
    best_score = 0
    for domain in SEMANTIC_DOMAINS:
        score = sum(1 for term in domain["terms"] if term in text)
        if score > best_score:
            best = domain
            best_score = score
    return {key: str(value) for key, value in best.items() if key != "terms"}


def semantic_color_variant(base_color: str, index: int) -> str:
    if index <= 0:
        return base_color
    red, green, blue = hex_to_rgb(base_color)
    hue, lightness, saturation = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)
    lightness_offsets = [0.0, -0.13, 0.11, -0.22, 0.18, -0.06, 0.06]
    saturation_offsets = [0.0, 0.05, -0.10, 0.08, -0.16, 0.12, -0.05]
    lightness = min(0.86, max(0.32, lightness + lightness_offsets[index % len(lightness_offsets)]))
    saturation = min(0.92, max(0.38, saturation + saturation_offsets[index % len(saturation_offsets)]))
    red_float, green_float, blue_float = colorsys.hls_to_rgb(hue, lightness, saturation)
    return rgb_to_hex(red_float, green_float, blue_float)


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    clean = color.strip().lstrip("#")
    if len(clean) != 6:
        return (148, 163, 184)
    return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))


def rgb_to_hex(red: float, green: float, blue: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        round(min(1.0, max(0.0, red)) * 255),
        round(min(1.0, max(0.0, green)) * 255),
        round(min(1.0, max(0.0, blue)) * 255),
    )


def top_labels(vertices: Iterable[ResearchVertex]) -> list[str]:
    vertex_list = list(vertices)
    labels = []
    labels.extend(label for vertex in vertex_list for label in vertex.topics)
    topic_labels = top_specific_list(labels, 5)
    if len(topic_labels) >= 5:
        return topic_labels
    labels = topic_labels.copy()
    fallback = []
    for vertex in vertex_list:
        fallback.extend(vertex.keywords)
        fallback.extend(vertex.methods)
        fallback.extend(vertex.datasets)
    for label in top_specific_list(fallback, 5):
        if label not in labels:
            labels.append(label)
        if len(labels) == 5:
            break
    return labels


def building_profile(vertices: Iterable[ResearchVertex]) -> dict[str, list[str]]:
    vertex_list = list(vertices)
    return {
        "topics": top_list([label for vertex in vertex_list for label in vertex.topics], 8),
        "keywords": top_list([label for vertex in vertex_list for label in vertex.keywords], 8),
        "methods": top_list([label for vertex in vertex_list for label in vertex.methods], 8),
        "datasets": top_list([label for vertex in vertex_list for label in vertex.datasets], 8),
        "venues": top_list([vertex.venue for vertex in vertex_list if vertex.venue], 5),
        "institutions": top_list([label for vertex in vertex_list for label in vertex.institutions], 5),
    }


def original_labels(vertices: Iterable[ResearchVertex]) -> dict[str, list[str]]:
    vertex_list = list(vertices)
    return {
        "topics": top_list([label for vertex in vertex_list for label in vertex.topics], 30),
        "keywords": top_list([label for vertex in vertex_list for label in vertex.keywords], 30),
        "methods": top_list([label for vertex in vertex_list for label in vertex.methods], 20),
        "datasets": top_list([label for vertex in vertex_list for label in vertex.datasets], 20),
    }


def activation_score(vertices: Iterable[ResearchVertex]) -> float:
    years = [vertex.publication_year for vertex in vertices if vertex.publication_year]
    citations = [vertex.citation_count for vertex in vertices]
    recency = 0.5
    if years:
        latest = max(years)
        recency = exp(-max(0, 2026 - latest) / 5)
    citation_signal = min(1.0, (mean(citations) if citations else 0.0) / 100)
    return round(0.55 * recency + 0.45 * citation_signal, 4)


def average_bridge_strength(group: set[str], bridges: list[Bridge]) -> float:
    strengths = [
        bridge.bridge_strength
        for bridge in bridges
        if bridge.source_building_id in group and bridge.target_building_id in group
    ]
    return round(mean(strengths), 4) if strengths else 1.0


def label_coherence(buildings: list[Building]) -> float:
    if len(buildings) < 2:
        return 1.0
    scores = [jaccard(left.top_labels, right.top_labels) for left, right in combinations(buildings, 2)]
    return round(mean(scores), 4) if scores else 1.0


def top_list(values: Iterable[str], limit: int) -> list[str]:
    counter = Counter(value for value in values if value)
    return [value for value, _ in counter.most_common(limit)]


def top_specific_list(values: Iterable[str], limit: int) -> list[str]:
    return top_list((value for value in values if not is_broad_label(value)), limit)


def is_broad_label(value: str) -> bool:
    return value.strip().lower() in BROAD_LABELS


def dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def extract_terms(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term in lowered]


def has_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def method_terms() -> list[str]:
    return ["community detection", "graph embedding", "tf-idf", "causal inference", "regression", "knowledge graph", "graph neural network", "visual analytics"]


def dataset_terms() -> list[str]:
    return ["openalex", "census", "semantic scholar", "crossref", "college scorecard", "citation graph"]


def is_direct_citation(left: ResearchVertex, right: ResearchVertex) -> bool:
    return right.openalex_id in left.referenced_paper_ids or left.openalex_id in right.referenced_paper_ids


def edge_evidence(left, right, components, cited, nearest) -> list[str]:
    evidence = []
    if cited:
        evidence.append("direct_citation")
    shared_topics = set(left.topics) & set(right.topics)
    evidence.extend(f"shared_topic: {topic}" for topic in sorted(shared_topics)[:2])
    if nearest:
        evidence.append("top_semantic_neighbor")
    if components["venue_similarity"]:
        evidence.append(f"shared_venue: {left.venue}")
    return evidence


def time_proximity(left_year: int | None, right_year: int | None) -> float:
    if not left_year or not right_year:
        return 0.0
    return max(0.0, 1 - abs(left_year - right_year) / 10)


def normalize(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return 0.5
    return (value - minimum) / (maximum - minimum)


def cosine(left: list[float], right: list[float]) -> float:
    left_arr = np.array(left)
    right_arr = np.array(right)
    denom = np.linalg.norm(left_arr) * np.linalg.norm(right_arr)
    if denom == 0:
        return 0.0
    return float(np.dot(left_arr, right_arr) / denom)
