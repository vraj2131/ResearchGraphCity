from __future__ import annotations

from collections import defaultdict

import igraph as ig
import leidenalg


def detect_paper_communities(
    node_ids: list[str],
    edges: list[tuple[str, str, float]],
    *,
    seed: int = 42,
    resolution: float = 1.0,
    max_building_size: int = 5_000,
    iterations: int = 1,
) -> dict[str, int]:
    if not node_ids:
        return {}
    index = {node_id: position for position, node_id in enumerate(node_ids)}
    graph_edges = [(index[source], index[target]) for source, target, _ in edges if source in index and target in index and source != target]
    weights = [weight for source, target, weight in edges if source in index and target in index and source != target]
    graph = ig.Graph(n=len(node_ids), edges=graph_edges, directed=False)
    graph.es["weight"] = weights
    if graph.ecount() == 0:
        return {node_id: position for position, node_id in enumerate(node_ids)}
    partition = leidenalg.find_partition(
        graph,
        leidenalg.RBConfigurationVertexPartition,
        weights=weights,
        resolution_parameter=resolution,
        seed=seed,
        n_iterations=iterations,
    )
    groups = [list(group) for group in partition]
    final_groups: list[list[int]] = []
    for group in groups:
        if len(group) <= max_building_size:
            final_groups.append(group)
            continue
        subgraph = graph.induced_subgraph(group)
        subpartition = leidenalg.find_partition(
            subgraph,
            leidenalg.RBConfigurationVertexPartition,
            weights=subgraph.es["weight"] if "weight" in subgraph.es.attributes() else None,
            resolution_parameter=resolution * 1.5,
            seed=seed,
            n_iterations=iterations,
        )
        split_groups = [[group[sub_index] for sub_index in child] for child in subpartition]
        target_group_count = (len(group) + max_building_size - 1) // max_building_size
        over_fragmented = len(split_groups) > target_group_count * 2
        still_oversized = any(len(child) > max_building_size for child in split_groups)
        if len(split_groups) == 1 or over_fragmented or still_oversized:
            ordered = sorted(group)
            split_groups = [ordered[start : start + max_building_size] for start in range(0, len(ordered), max_building_size)]
        final_groups.extend(split_groups)
    ordered_groups = sorted(final_groups, key=lambda group: (-len(group), min(group)))
    return {
        node_ids[node_index]: community_index
        for community_index, group in enumerate(ordered_groups)
        for node_index in group
    }


def group_assignments(assignments: dict[str, int]) -> dict[int, list[str]]:
    groups: dict[int, list[str]] = defaultdict(list)
    for node_id, community_id in assignments.items():
        groups[community_id].append(node_id)
    return {community_id: sorted(nodes) for community_id, nodes in groups.items()}
