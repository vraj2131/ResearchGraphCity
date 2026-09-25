from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = json.loads((Path(__file__).parent / "fixtures/graph_cities/original.json").read_text())


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
def test_decomposition_matches_original_executables(case):
    from app.pipeline.fixed_points import decompose_graph

    nodes = [str(i) for i in range(case["vertex_count"])]
    result = decompose_graph(nodes, [(str(u), str(v)) for u, v in case["edges"]])
    actual = {
        (int(u), int(v)): (result.layers[i], result.waves[i], result.fragments[i])
        for i, (u, v) in enumerate(result.edges)
    }
    expected = {(u, v): (peel, wave, fragment) for u, v, peel, wave, _, fragment in case["labels"]}
    assert actual == expected
    # Compare wave connected components as partitions, independent of IDs.
    expected_groups = {}
    actual_groups = {}
    for u, v, peel, wave, component, fragment in case["labels"]:
        expected_groups.setdefault((peel, wave, component), set()).add((u, v))
    for i, (u, v) in enumerate(result.edges):
        key = (result.layers[i], result.waves[i], result.wave_components[i])
        actual_groups.setdefault(key, set()).add((int(u), int(v)))
    assert {frozenset(group) for group in actual_groups.values()} == {frozenset(group) for group in expected_groups.values()}
    assert sorted(i for building in result.buildings for i in building.edge_indices) == list(range(len(result.edges)))


def test_fixed_point_memberships_overlap_without_splitting_edge_ownership():
    from app.pipeline.fixed_points import decompose_graph

    result = decompose_graph(["a", "b", "c", "d"], [("a", "b"), ("b", "c"), ("a", "c"), ("c", "d")])
    assert {(b.peel, frozenset(b.vertices)) for b in result.buildings} == {
        (2, frozenset(["a", "b", "c"])), (1, frozenset(["c", "d"]))}
    assert sum("c" in b.vertices for b in result.buildings) == 2


def test_sanitizes_duplicate_reverse_and_self_edges_and_preserves_isolates():
    from app.pipeline.fixed_points import decompose_graph

    result = decompose_graph(["a", "b", "isolated"], [("a", "b"), ("b", "a"), ("a", "a"), ("a", "b")])
    assert result.edges == (("a", "b"),)
    assert result.isolates == ("isolated",)
    assert decompose_graph([], []).buildings == ()
    assert decompose_graph(["alone"], []).isolates == ("alone",)


def test_rejects_unknown_vertices_and_checks_cancellation():
    from app.pipeline.fixed_points import decompose_graph
    from app.openalex_client import OpenAlexCancelled

    with pytest.raises(ValueError, match="Unknown"):
        decompose_graph(["a"], [("a", "missing")])
    with pytest.raises(OpenAlexCancelled):
        decompose_graph(["a", "b"], [("a", "b")], cancel_check=lambda: True)


def test_vertex_wave_and_fragment_locations_preserve_wave_source_geometry():
    from app.pipeline.fixed_points import decompose_graph

    case = next(case for case in FIXTURE["cases"] if case["name"] == "triangles_pendant")
    result = decompose_graph([str(i) for i in range(7)], [(str(u), str(v)) for u, v in case["edges"]])
    assert result.vertex_levels[2] == {
        "0": (1, 0), "1": (1, 0), "2": (1, 1), "3": (1, 1), "4": (1, 0), "5": (1, 0),
    }
    assert result.vertex_levels[1] == {"5": (1, 0), "6": (1, 0)}
