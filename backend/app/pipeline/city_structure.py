from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import blake2b
from math import ceil, cos, log1p, pi, sin, sqrt
import uuid

import igraph as ig
import networkx as nx
import numpy as np
from sqlalchemy import delete, func, select, text, update

from ..graph_processing import BROAD_LABELS, semantic_domain_for_labels
from ..models import (
    BuildingRecord,
    BuildingRelationshipRecord,
    CityPaperRecord,
    CityRecord,
    CommunityRunRecord,
    DistrictRecord,
    FloorRecord,
    PaperEdgeRecord,
    PaperRecord,
)
from ..repositories.postgres_city import PostgresCityRepository
from .bulk_io import copy_rows
from .communities import detect_paper_communities, group_assignments


def floor_bands(core_numbers: dict[str, int], *, max_floors: int = 5) -> list[tuple[int, int, list[str]]]:
    if not core_numbers:
        return []
    unique_cores = sorted(set(core_numbers.values()))
    floor_count = max(1, min(max_floors, len(unique_cores)))
    chunks = [chunk.tolist() for chunk in np.array_split(np.array(unique_cores, dtype=int), floor_count) if len(chunk)]
    bands = []
    for chunk in chunks:
        values = set(chunk)
        node_ids = sorted(node_id for node_id, core in core_numbers.items() if core in values)
        if node_ids:
            bands.append((min(chunk), max(chunk), node_ids))
    return bands


def assign_unique_primary_labels(candidate_labels: list[list[str]]) -> list[str]:
    used: set[str] = set()
    result: list[str] = []
    broad = {label.casefold() for label in BROAD_LABELS}
    for index, labels in enumerate(candidate_labels, start=1):
        normalized = []
        seen: set[str] = set()
        for label in labels:
            key = label.strip().casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            normalized.append(label.strip())
        specific = [label for label in normalized if label.casefold() not in broad]
        choice = next((label for label in specific if label.casefold() not in used), None)
        choice = choice or next((label for label in normalized if label.casefold() not in used), None)
        choice = choice or (specific[0] if specific else normalized[0] if normalized else f"Research Building {index}")
        used.add(choice.casefold())
        result.append(choice)
    return result


def relationship_kind(score: float, *, bridge_threshold: float = 0.35, street_threshold: float = 0.08) -> str | None:
    if score >= bridge_threshold:
        return "bridge"
    if score >= street_threshold and score > 0:
        return "street"
    return None


def top_specific_labels(values: list[str], limit: int = 8) -> list[str]:
    broad = {label.casefold() for label in BROAD_LABELS}
    counts = Counter(value.strip() for value in values if value.strip())
    specific = [label for label, _ in counts.most_common() if label.casefold() not in broad]
    fallback = [label for label, _ in counts.most_common() if label.casefold() in broad]
    return (specific + fallback)[:limit]


def _community_backbone(edge_rows: list[tuple], *, max_similarity_degree: int = 10) -> list[tuple]:
    """Keep citations and the strongest bounded similarity edges for clustering."""
    citations = [row for row in edge_rows if row[3] == "citation"]
    similarities = sorted(
        (row for row in edge_rows if row[3] == "similarity"),
        key=lambda row: (
            -float(row[2]),
            blake2b(f"{row[0]}\0{row[1]}".encode(), digest_size=8).digest(),
            str(row[0]),
            str(row[1]),
        ),
    )
    degree: Counter[str] = Counter()
    selected: list[tuple] = []
    for row in similarities:
        source, target = str(row[0]), str(row[1])
        if degree[source] >= max_similarity_degree or degree[target] >= max_similarity_degree:
            continue
        selected.append(row)
        degree[source] += 1
        degree[target] += 1
    return [*citations, *selected]


def build_city_structure(
    city_id: uuid.UUID,
    repository: PostgresCityRepository,
    *,
    seed: int = 42,
    max_building_size: int = 5_000,
    min_building_size: int = 3,
) -> dict[str, int]:
    with repository.session_factory() as session:
        rows = session.execute(
            select(CityPaperRecord.openalex_id, PaperRecord)
            .join(PaperRecord, PaperRecord.openalex_id == CityPaperRecord.openalex_id)
            .where(CityPaperRecord.city_id == city_id)
            .order_by(CityPaperRecord.openalex_id)
        ).all()
        edge_rows = session.execute(
            select(
                PaperEdgeRecord.source_openalex_id,
                PaperEdgeRecord.target_openalex_id,
                PaperEdgeRecord.weight,
                PaperEdgeRecord.edge_type,
                PaperEdgeRecord.evidence,
            ).where(PaperEdgeRecord.city_id == city_id)
        ).all()
    paper_by_id = {paper_id: paper for paper_id, paper in rows}
    node_ids = list(paper_by_id)
    weighted_edges = [(source, target, float(weight)) for source, target, weight, _, _ in edge_rows]
    community_edges = [
        (source, target, float(weight))
        for source, target, weight, _, _ in _community_backbone(edge_rows)
    ]
    assignments = detect_paper_communities(
        node_ids,
        community_edges,
        seed=seed,
        max_building_size=max_building_size,
    )
    assignments = _merge_tiny_groups(assignments, weighted_edges, min_building_size)
    groups = group_assignments(assignments)
    prepared = []
    max_nodes = max((len(nodes) for nodes in groups.values()), default=1)
    edge_by_group: dict[int, list[tuple[str, str, float]]] = defaultdict(list)
    for source, target, weight in weighted_edges:
        source_group = assignments.get(source)
        target_group = assignments.get(target)
        if source_group is not None and source_group == target_group:
            edge_by_group[source_group].append((source, target, weight))

    for group_id, members in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        papers = [paper_by_id[node_id] for node_id in members]
        labels = top_specific_labels(
            [label for paper in papers for label in [*paper.topics, *paper.keywords, *paper.methods, *paper.datasets]],
            12,
        )
        core_numbers = _core_numbers(members, edge_by_group[group_id])
        avg_core = sum(core_numbers.values()) / max(1, len(core_numbers))
        domain = semantic_domain_for_labels(labels)
        activation = _activation(papers)
        prepared.append(
            {
                "group_id": group_id,
                "members": members,
                "papers": papers,
                "edges": edge_by_group[group_id],
                "labels": labels,
                "core_numbers": core_numbers,
                "avg_core": avg_core,
                "max_core": max(core_numbers.values(), default=0),
                "domain": domain,
                "activation": activation,
                "footprint": round(6 + 28 * sqrt(len(members) / max_nodes), 4),
                "height": round(18 + 6 * avg_core, 4),
            }
        )
    primary_labels = assign_unique_primary_labels([item["labels"] for item in prepared])
    for item, primary in zip(prepared, primary_labels, strict=True):
        item["labels"] = [primary, *[label for label in item["labels"] if label != primary]][:8]
    _assign_layout(prepared)
    return _persist_structure(city_id, repository, prepared, assignments, edge_rows, seed)


def _persist_structure(city_id, repository, prepared, assignments, edge_rows, seed) -> dict[str, int]:
    with repository.session_factory.begin() as session:
        session.execute(update(CityPaperRecord).where(CityPaperRecord.city_id == city_id).values(building_id=None, floor_id=None))
        session.execute(delete(CommunityRunRecord).where(CommunityRunRecord.city_id == city_id))
        session.execute(delete(BuildingRelationshipRecord).where(BuildingRelationshipRecord.city_id == city_id))
        session.execute(delete(FloorRecord).where(FloorRecord.city_id == city_id))
        session.execute(delete(BuildingRecord).where(BuildingRecord.city_id == city_id))
        session.execute(delete(DistrictRecord).where(DistrictRecord.city_id == city_id))

        domains = sorted({item["domain"]["id"]: item["domain"] for item in prepared}.values(), key=lambda item: item["id"])
        district_by_domain = {}
        for index, domain in enumerate(domains, start=1):
            angle = 2 * pi * (index - 1) / max(1, len(domains))
            district = DistrictRecord(
                id=uuid.uuid4(),
                city_id=city_id,
                external_id=f"D_{index:04d}",
                name=domain["name"],
                semantic_domain=domain["id"],
                semantic_domain_name=domain["name"],
                color=domain["color"],
                labels=[],
                metrics={},
                x=round(cos(angle) * 420, 4),
                z=round(sin(angle) * 420, 4),
            )
            session.add(district)
            district_by_domain[domain["id"]] = district
        session.flush()

        building_by_group = {}
        buildings = []
        floors = []
        paper_assignments: dict[str, list[uuid.UUID | None]] = {}
        floor_count = 0
        for index, item in enumerate(prepared, start=1):
            district = district_by_domain[item["domain"]["id"]]
            building = BuildingRecord(
                id=uuid.uuid4(),
                city_id=city_id,
                district_id=district.id,
                external_id=f"B_{index:04d}",
                node_count=len(item["members"]),
                edge_count=len(item["edges"]),
                internal_density=(2 * len(item["edges"]) / (len(item["members"]) * (len(item["members"]) - 1))) if len(item["members"]) > 1 else 0.0,
                avg_core=item["avg_core"],
                max_core=item["max_core"],
                height=item["height"],
                footprint=item["footprint"],
                x=item["x"],
                z=item["z"],
                top_labels=item["labels"],
                semantic_domain=item["domain"]["id"],
                semantic_domain_name=item["domain"]["name"],
                semantic_color=item["domain"]["color"],
                profile=_profile(item["papers"]),
                original_labels=_original_labels(item["papers"]),
                activation={"score": item["activation"], "formula_version": "activation-v2"},
                activation_score=item["activation"],
                quality_metrics={"formula_version": "city-structure-v2"},
            )
            buildings.append(building)
            building_by_group[item["group_id"]] = building
            for member in item["members"]:
                paper_assignments[member] = [building.id, None]
            for floor_index, (core_min, core_max, floor_nodes) in enumerate(floor_bands(item["core_numbers"]), start=1):
                floor_node_set = set(floor_nodes)
                floor_papers = [paper for paper in item["papers"] if paper.openalex_id in floor_node_set]
                floor = FloorRecord(
                    id=uuid.uuid4(),
                    city_id=city_id,
                    building_id=building.id,
                    external_id=f"F_{index:04d}_{floor_index:02d}",
                    floor_index=floor_index,
                    core_min=core_min,
                    core_max=core_max,
                    node_count=len(floor_nodes),
                    top_labels=top_specific_labels([label for paper in floor_papers for label in paper.topics], 5),
                    activation_score=_activation(floor_papers),
                    year_min=min((paper.publication_year for paper in floor_papers if paper.publication_year), default=None),
                    year_max=max((paper.publication_year for paper in floor_papers if paper.publication_year), default=None),
                )
                floors.append(floor)
                floor_count += 1
                for node_id in floor_nodes:
                    paper_assignments[node_id][1] = floor.id

        session.add_all(buildings)
        session.flush()
        session.add_all(floors)
        session.flush()
        connection = session.connection()
        connection.execute(
            text(
                "CREATE TEMP TABLE city_assignment_stage ("
                "openalex_id text PRIMARY KEY, building_id uuid, floor_id uuid"
                ") ON COMMIT DROP"
            )
        )
        copy_rows(
            connection,
            "city_assignment_stage",
            ("openalex_id", "building_id", "floor_id"),
            (
                (openalex_id, building_floor[0], building_floor[1])
                for openalex_id, building_floor in paper_assignments.items()
            ),
        )
        connection.execute(
            text(
                """
                UPDATE city_papers AS cp
                SET building_id = stage.building_id, floor_id = stage.floor_id
                FROM city_assignment_stage AS stage
                WHERE cp.city_id = :city_id AND cp.openalex_id = stage.openalex_id
                """
            ),
            {"city_id": city_id},
        )

        relationship_count = _persist_relationships(session, city_id, prepared, assignments, building_by_group, edge_rows)
        for district in district_by_domain.values():
            district_buildings = [item for item in prepared if item["domain"]["id"] == district.semantic_domain]
            district.labels = top_specific_labels([label for item in district_buildings for label in item["labels"]], 8)
            district.metrics = {"building_count": len(district_buildings), "paper_count": sum(len(item["members"]) for item in district_buildings)}
        city = session.get(CityRecord, city_id)
        city.building_count = len(prepared)
        city.district_count = len(district_by_domain)
        city.algorithm_version = "leiden-city-v2"
        city.status = "ready"
        city.completed_at = datetime.now(timezone.utc)
        session.add(
            CommunityRunRecord(
                city_id=city_id,
                algorithm="leiden",
                parameters={"resolution": 1.0, "max_building_size": 5_000, "iterations": 1},
                random_seed=seed,
                metrics={"building_count": len(prepared), "district_count": len(district_by_domain)},
                completed_at=datetime.now(timezone.utc),
            )
        )
    bridge_count, street_count = relationship_count
    return {
        "districts": len(district_by_domain),
        "buildings": len(prepared),
        "floors": floor_count,
        "bridges": bridge_count,
        "streets": street_count,
    }


def _persist_relationships(session, city_id, prepared, assignments, building_by_group, edge_rows, *, memberships=None):
    cross: dict[tuple[int, int], list] = defaultdict(list)
    for source, target, weight, edge_type, evidence in edge_rows:
        left_ids = memberships.get(source, []) if memberships is not None else [assignments.get(source)]
        right_ids = memberships.get(target, []) if memberships is not None else [assignments.get(target)]
        pairs = {tuple(sorted((left, right))) for left in left_ids for right in right_ids
                 if left is not None and right is not None and left != right}
        for pair in pairs:
            cross[pair].append((source, target, float(weight), edge_type, evidence))
    item_by_group = {item["group_id"]: item for item in prepared}
    candidates = []
    for (left_id, right_id), connecting in cross.items():
        left = item_by_group[left_id]
        right = item_by_group[right_id]
        denom = sqrt(max(1, len(left["members"])) * max(1, len(right["members"])))
        cross_strength = min(1.0, sum(edge[2] for edge in connecting) / denom)
        left_labels = {label.casefold() for label in left["labels"]}
        right_labels = {label.casefold() for label in right["labels"]}
        label_similarity = len(left_labels & right_labels) / len(left_labels | right_labels) if left_labels and right_labels else 0.0
        profile_similarity = _profile_similarity(_profile(left["papers"]), _profile(right["papers"]))
        activation_similarity = 1 - abs(left["activation"] - right["activation"])
        score = round(0.45 * cross_strength + 0.25 * label_similarity + 0.20 * profile_similarity + 0.10 * activation_similarity, 6)
        kind = relationship_kind(score)
        if kind is None:
            continue
        components = {
            "cross_edge_strength": round(cross_strength, 6),
            "semantic_similarity": round(label_similarity, 6),
            "profile_similarity": round(profile_similarity, 6),
            "activation_similarity": round(activation_similarity, 6),
            "cross_edge_count": len(connecting),
        }
        evidence = [f"cross_edges: {len(connecting)}", f"cross_edge_weight_sum: {sum(edge[2] for edge in connecting):.4f}"]
        evidence.extend(f"shared_label: {label}" for label in sorted(left_labels & right_labels)[:3])
        evidence.extend(f"paper_edge: {source} -> {target}" for source, target, *_ in sorted(connecting, key=lambda edge: -edge[2])[:3])
        candidates.append((left_id, right_id, kind, score, components, evidence))

    bridge_candidates = [item for item in candidates if item[2] == "bridge"]
    street_candidates = _research_backbone([item for item in candidates if item[2] == "street"], building_by_group)
    counts = Counter()
    for sequence, (left_id, right_id, kind, score, components, evidence) in enumerate(bridge_candidates + street_candidates, start=1):
        left = building_by_group[left_id]
        right = building_by_group[right_id]
        dx = right.x - left.x
        dz = right.z - left.z
        session.add(
            BuildingRelationshipRecord(
                city_id=city_id,
                external_id=f"{'BR' if kind == 'bridge' else 'ST'}_{sequence:05d}",
                source_building_id=left.id,
                target_building_id=right.id,
                relationship_kind=kind,
                relationship_type="evidence_bridge" if kind == "bridge" else "research_backbone",
                score=score,
                distance=sqrt(dx * dx + dz * dz),
                components=components,
                evidence=evidence,
                activation_score=(left.activation_score + right.activation_score) / 2,
            )
        )
        counts[kind] += 1
    return counts["bridge"], counts["street"]


def _research_backbone(candidates, building_by_group):
    graph = nx.Graph()
    graph.add_nodes_from(building_by_group)
    by_pair = {}
    for item in candidates:
        left, right, _, score, *_ = item
        graph.add_edge(left, right, weight=score)
        by_pair[tuple(sorted((left, right)))] = item
    selected = []
    for component in nx.connected_components(graph):
        subgraph = graph.subgraph(component)
        for left, right in nx.maximum_spanning_edges(subgraph, data=False):
            selected.append(by_pair[tuple(sorted((left, right)))])
    return selected


def _merge_tiny_groups(assignments, edges, min_size):
    groups = group_assignments(assignments)
    sizes = {group_id: len(nodes) for group_id, nodes in groups.items()}
    cross = defaultdict(float)
    for source, target, weight in edges:
        left = assignments.get(source)
        right = assignments.get(target)
        if left is not None and right is not None and left != right:
            cross[(left, right)] += weight
            cross[(right, left)] += weight
    updated = dict(assignments)
    for group_id, members in groups.items():
        if len(members) >= min_size:
            continue
        neighbors = [(score, target) for (source, target), score in cross.items() if source == group_id and sizes.get(target, 0) >= min_size]
        if not neighbors:
            for member in members:
                updated.pop(member, None)
            continue
        target = max(neighbors)[1]
        for member in members:
            updated[member] = target
    remap = {old: new for new, old in enumerate(sorted(set(updated.values())))}
    return {node: remap[group] for node, group in updated.items()}


def _core_numbers(nodes, edges):
    index = {node: position for position, node in enumerate(nodes)}
    graph_edges = [(index[source], index[target]) for source, target, _ in edges if source in index and target in index]
    graph = ig.Graph(n=len(nodes), edges=graph_edges, directed=False)
    cores = graph.coreness() if graph.vcount() else []
    return {node: int(cores[position]) for node, position in index.items()}


def _assign_layout(prepared):
    by_domain = defaultdict(list)
    for item in prepared:
        by_domain[item["domain"]["id"]].append(item)
    domains = sorted(by_domain)
    for domain_index, domain_id in enumerate(domains):
        district_angle = 2 * pi * domain_index / max(1, len(domains))
        center_x = cos(district_angle) * 420
        center_z = sin(district_angle) * 420
        items = sorted(by_domain[domain_id], key=lambda item: (-len(item["members"]), item["group_id"]))
        for index, item in enumerate(items):
            angle = 2 * pi * index / max(1, len(items))
            radius = 55 + 24 * sqrt(len(items))
            item["x"] = round(center_x + cos(angle) * radius, 4)
            item["z"] = round(center_z + sin(angle) * radius, 4)


def _activation(papers):
    if not papers:
        return 0.0
    current_year = datetime.now(timezone.utc).year
    recency = sum(max(0.0, 1 - max(0, current_year - (paper.publication_year or current_year - 20)) / 20) for paper in papers) / len(papers)
    citation = sum(min(1.0, log1p(max(0, paper.citation_count)) / 10) for paper in papers) / len(papers)
    return round(0.6 * recency + 0.4 * citation, 6)


def _profile(papers):
    return {
        "topics": top_specific_labels([value for paper in papers for value in paper.topics], 12),
        "methods": top_specific_labels([value for paper in papers for value in paper.methods], 8),
        "datasets": top_specific_labels([value for paper in papers for value in paper.datasets], 8),
        "venues": top_specific_labels([paper.venue for paper in papers if paper.venue], 8),
        "institutions": top_specific_labels([value for paper in papers for value in paper.institutions], 8),
    }


def _original_labels(papers):
    return {
        "topics": top_specific_labels([value for paper in papers for value in paper.topics], 100),
        "keywords": top_specific_labels([value for paper in papers for value in paper.keywords], 100),
        "methods": top_specific_labels([value for paper in papers for value in paper.methods], 100),
        "datasets": top_specific_labels([value for paper in papers for value in paper.datasets], 100),
        "venues": top_specific_labels([paper.venue for paper in papers if paper.venue], 100),
        "institutions": top_specific_labels([value for paper in papers for value in paper.institutions], 100),
    }


def _profile_similarity(left, right):
    scores = []
    for key in ("topics", "methods", "datasets", "venues", "institutions"):
        left_values = {value.casefold() for value in left[key]}
        right_values = {value.casefold() for value in right[key]}
        scores.append(len(left_values & right_values) / len(left_values | right_values) if left_values and right_values else 0.0)
    return sum(scores) / len(scores)


def _chunks(values, size):
    for start in range(0, len(values), size):
        yield values[start : start + size]
