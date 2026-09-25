"""Iterative fixed-point edge peeling and wave/fragment decomposition.

The implementation is local to this application. Equivalence is checked against
saved output from the original Graph Cities preproc/buffkcore/ewave_next tools.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import heapq
from typing import Callable, Iterable, Sequence

import igraph as ig

from ..openalex_client import OpenAlexCancelled


@dataclass(frozen=True)
class FixedPointBuilding:
    peel: int
    vertices: tuple[str, ...]
    edge_indices: tuple[int, ...]


@dataclass(frozen=True)
class Decomposition:
    edges: tuple[tuple[str, str], ...]
    layers: tuple[int, ...]
    waves: tuple[int, ...]
    fragments: tuple[int, ...]
    wave_components: tuple[int, ...]
    buildings: tuple[FixedPointBuilding, ...]
    isolates: tuple[str, ...]
    vertex_levels: dict[int, dict[str, tuple[int, int]]]


def decompose_graph(
    node_ids: Sequence[str],
    edges: Iterable[tuple[str, str]],
    cancel_check: Callable[[], bool] | None = None,
) -> Decomposition:
    def check():
        if cancel_check and cancel_check():
            raise OpenAlexCancelled("Graph Cities decomposition cancelled")

    check()
    nodes = tuple(dict.fromkeys(node_ids))
    index = {node: i for i, node in enumerate(nodes)}
    normalized = set()
    for offset, (source, target) in enumerate(edges):
        if offset % 4096 == 0:
            check()
        if source not in index or target not in index:
            raise ValueError("Unknown vertex in graph edge")
        u, v = index[source], index[target]
        if u != v:
            normalized.add((min(u, v), max(u, v)))
    pairs = sorted(normalized)
    layers = [0] * len(pairs)
    remaining = list(range(len(pairs)))
    # Recompute core numbers after removing the maximum-core edge set, rather
    # than assigning each edge the minimum core number of its original ends.
    while remaining:
        check()
        graph = ig.Graph(n=len(nodes), edges=[pairs[i] for i in remaining], directed=False)
        cores = graph.coreness()
        peel = max(cores)
        next_remaining = []
        for i in remaining:
            u, v = pairs[i]
            if cores[u] == peel and cores[v] == peel:
                layers[i] = peel
            else:
                next_remaining.append(i)
        if len(next_remaining) == len(remaining):
            raise RuntimeError("Fixed-point decomposition made no progress")
        remaining = next_remaining

    by_layer = defaultdict(list)
    for i, peel in enumerate(layers):
        by_layer[peel].append(i)
    waves = [0] * len(pairs)
    fragments = [0] * len(pairs)
    wave_components = [0] * len(pairs)
    buildings = []
    vertex_levels = {}
    for peel, edge_ids in sorted(by_layer.items(), reverse=True):
        check()
        adj = defaultdict(dict)
        for i in edge_ids:
            u, v = pairs[i]
            adj[u][v] = i
            adj[v][u] = i
        for members, owned_edges in _components(adj):
            buildings.append(FixedPointBuilding(peel, tuple(nodes[v] for v in sorted(members)), tuple(sorted(owned_edges))))
        vertex_levels[peel] = {nodes[v]: level for v, level in _waves(adj, waves, fragments, check).items()}
        by_wave = defaultdict(dict)
        for i in edge_ids:
            u, v = pairs[i]
            wave_adj = by_wave[waves[i]]
            wave_adj.setdefault(u, {})[v] = i
            wave_adj.setdefault(v, {})[u] = i
        for wave_adj in by_wave.values():
            for component, (_, owned_edges) in enumerate(_components(wave_adj)):
                for i in owned_edges:
                    wave_components[i] = component
    used = {v for edge in pairs for v in edge}
    return Decomposition(
        tuple((nodes[u], nodes[v]) for u, v in pairs), tuple(layers), tuple(waves),
        tuple(fragments), tuple(wave_components), tuple(buildings),
        tuple(node for i, node in enumerate(nodes) if i not in used),
        vertex_levels,
    )


def _components(adj):
    unseen = set(adj)
    for root in sorted(adj):
        if root not in unseen:
            continue
        unseen.remove(root)
        stack = [root]
        vertices = {root}
        edges = set()
        while stack:
            vertex = stack.pop()
            for neighbor, edge in adj[vertex].items():
                edges.add(edge)
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    vertices.add(neighbor)
                    stack.append(neighbor)
        yield vertices, edges


def _waves(adj, waves, fragments, check):
    levels = {}
    remaining = set(adj)
    degrees = {vertex: len(neighbors) for vertex, neighbors in adj.items()}
    buckets = defaultdict(set)
    for vertex, degree in degrees.items():
        buckets[degree].add(vertex)
    heap = list(buckets)
    heapq.heapify(heap)
    wave = 0
    while remaining:
        check()
        while heap and not buckets[heap[0]]:
            heapq.heappop(heap)
        threshold = heap[0]
        wave += 1
        frontier = set(buckets[threshold])
        fragment = 0
        while frontier:
            check()
            remaining.difference_update(frontier)
            for vertex in frontier:
                levels[vertex] = (wave, fragment)
                buckets[degrees[vertex]].discard(vertex)
            touched = set()
            for vertex in sorted(frontier):
                for neighbor, edge in adj[vertex].items():
                    if not waves[edge]:
                        waves[edge] = wave
                        fragments[edge] = fragment
                    if neighbor in remaining:
                        buckets[degrees[neighbor]].discard(neighbor)
                        degrees[neighbor] -= 1
                        if not buckets[degrees[neighbor]]:
                            heapq.heappush(heap, degrees[neighbor])
                        buckets[degrees[neighbor]].add(neighbor)
                        touched.add(neighbor)
            frontier = {v for v in touched if degrees[v] < threshold}
            fragment += 1
    return levels
