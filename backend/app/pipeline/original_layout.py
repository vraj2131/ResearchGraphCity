"""Graph Cities bucket, spiral, and frustum geometry.

Adapted from the original scripts; see vendor/graph_cities for attribution.
Saved reference-script output tests the numeric formulas independently.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from itertools import combinations
import math

from scipy.spatial import QhullError, Voronoi

from .fixed_points import Decomposition, FixedPointBuilding


def bucket_thresholds(vertex_count: int, largest_edge_count: int) -> list[int]:
    base = math.log(max(vertex_count, 1)) / 2
    # The upstream loop cannot terminate for base <= 1. This extension only
    # affects tiny inputs for which the published formula is undefined.
    if base <= 1:
        base = 2.0
    thresholds = [0]
    exponent = 1
    while thresholds[-1] <= largest_edge_count:
        thresholds.append(math.floor(base ** exponent))
        exponent += 1
    return thresholds


def frustum_height(volume: float, upper: float, lower: float) -> float:
    denominator = math.pi * (upper * upper + upper * lower + lower * lower)
    if denominator == 0:
        if volume == 0:
            return 0.0
        raise ValueError('A positive-volume frustum requires a nonzero radius')
    return 3 * volume / denominator


def spiral_layout(buildings: list[dict], vertex_count: int) -> list[dict]:
    if not buildings:
        return []
    thresholds = bucket_thresholds(vertex_count, max(b['edge_count'] for b in buildings))
    ordered = sorted(buildings, key=lambda b: (
        -bisect_right(thresholds, b['edge_count']), -b['peel']))
    reference_radius = math.log2(max(b['max_wave_vertices'] for b in buildings))
    length = 2 * reference_radius
    theta = 0.0
    result = []
    for index, building in enumerate(ordered):
        orbit = length + length / 4 * theta
        lower = math.log2(building['first_wave_sources'] + 1)
        volume = building['wave_count'] * math.log2(building['edge_count'] + 1)
        radius = math.sqrt(lower * lower + volume * reference_radius ** 2 - reference_radius ** 2) / math.sqrt(volume)
        result.append(dict(
            id=building['id'], x=orbit * math.cos(theta) - length / 2,
            z=orbit * math.sin(theta), rotation_degrees=math.degrees(theta) + 90,
            radius=radius, bucket=bisect_right(thresholds, building['edge_count']),
        ))
        theta += length * 1.7 / orbit
        if index == 0:
            theta = 1.5 * math.pi / 2
    return result


def street_pairs(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Original Voronoi ridge adjacency; degenerate inputs use a stable chain.

    These edges describe geometry, never citation or semantic evidence.
    A deterministic chain also keeps duplicate locations navigable without
    depending on Qhull's random perturbations.
    """
    if len(points) < 4:
        return list(combinations(range(len(points)), 2))
    if len(set(points)) == len(points):
        try:
            return sorted({tuple(sorted(map(int, pair))) for pair in Voronoi(points).ridge_points})
        except QhullError:
            pass
    ordered = sorted(range(len(points)), key=lambda i: (points[i][0], points[i][1], i))
    return sorted(tuple(sorted(pair)) for pair in zip(ordered, ordered[1:]))


def wave_profiles(graph: Decomposition, building: FixedPointBuilding) -> list[dict]:
    """Build original wave frustums, retaining every wave and fragment.

    The original wave-map's t is all wave vertices outside fragment zero,
    including later fragments of this same wave. Edges toward later waves
    remain a separate external-edge count. Shared endpoints appear on both floors.
    """
    levels = graph.vertex_levels[building.peel]
    by_wave = defaultdict(list)
    removed = defaultdict(list)
    for vertex in building.vertices:
        removed[levels[vertex][0]].append(vertex)
    for edge_index in building.edge_indices:
        by_wave[graph.waves[edge_index]].append(edge_index)
    profiles = []
    bottom = 0.0
    for wave, edge_indices in sorted(by_wave.items()):
        vertices = set()
        internal = 0
        for edge_index in edge_indices:
            endpoints = graph.edges[edge_index]
            vertices.update(endpoints)
            later = [v for v in endpoints if levels[v][0] > wave]
            internal += not later
        fragments = defaultdict(list)
        for vertex in removed[wave]:
            fragments[levels[vertex][1]].append(vertex)
        sources = tuple(sorted(fragments[0]))
        targets = vertices.difference(sources)
        lower = math.log2(len(sources) + 1)
        upper = math.log2(len(targets) + 1)
        height = frustum_height(math.log2(len(edge_indices) + 1), upper, lower)
        profiles.append(dict(
            wave=wave, edge_indices=tuple(edge_indices), vertices=tuple(sorted(vertices)),
            removed=tuple(sorted(removed[wave])), sources=sources, targets=tuple(sorted(targets)),
            fragments={fragment: tuple(sorted(members)) for fragment, members in sorted(fragments.items())},
            internal_edges=internal, external_edges=len(edge_indices) - internal,
            lower_radius=lower, upper_radius=upper, bottom=bottom, height=height,
        ))
        bottom += height
    return profiles
