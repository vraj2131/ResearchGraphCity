import json
import math
from pathlib import Path

import pytest

from app.pipeline.original_layout import bucket_thresholds, frustum_height, spiral_layout, street_pairs
from app.pipeline.fixed_points import decompose_graph


REFERENCE = json.loads((Path(__file__).parent / 'fixtures/graph_cities/geometry.json').read_text())


def test_geometry_matches_original_scripts():
    assert bucket_thresholds(100, 32) == REFERENCE['thresholds']
    actual = spiral_layout(REFERENCE['inputs'], 100)
    assert [item['id'] for item in actual] == [item['id'] for item in REFERENCE['spiral']]
    for item, expected in zip(actual, REFERENCE['spiral']):
        for key in ('x', 'z', 'rotation_degrees', 'radius'):
            assert item[key] == pytest.approx(expected[key], abs=1e-12)
    for sample in REFERENCE['frustums']:
        assert frustum_height(sample['volume'], sample['upper'], sample['lower']) == pytest.approx(sample['height'])


@pytest.mark.parametrize('vertices', range(8))
def test_small_graph_bucket_fallback_terminates(vertices):
    thresholds = bucket_thresholds(vertices, 10)
    assert thresholds[0] == 0
    assert thresholds[-1] > 10
    assert thresholds == sorted(set(thresholds))


def test_empty_layout_and_small_streets():
    assert spiral_layout([], 0) == []
    assert street_pairs([]) == []
    assert street_pairs([(0, 0)]) == []
    assert street_pairs([(0, 0), (1, 0), (0, 1)]) == [(0, 1), (0, 2), (1, 2)]


def test_streets_are_delaunay_and_collinear_fallback_is_connected():
    points = [(0, 0), (4, 0), (4, 3), (0, 2)]
    assert set(street_pairs(points)) == {(0, 1), (1, 2), (2, 3), (0, 3), (1, 3)}
    assert street_pairs([(3, 0), (0, 0), (1, 0), (2, 0)]) == [(0, 3), (1, 2), (2, 3)]
    assert street_pairs([(0, 0)] * 4) == [(0, 1), (1, 2), (2, 3)]


def test_single_edge_geometry_is_finite():
    item = dict(id='edge', peel=1, node_count=2, edge_count=1,
                max_wave_vertices=2, first_wave_sources=2, wave_count=1)
    layout = spiral_layout([item], 2)
    assert layout[0]['radius'] > 0
    assert all(math.isfinite(layout[0][k]) for k in ('x', 'z', 'radius'))


def test_wave_profiles_keep_shared_endpoints_and_original_volume():
    from app.pipeline.original_layout import wave_profiles
    graph = decompose_graph(['a', 'b', 'c', 'd', 'e'], [('a', 'b'), ('b', 'c'), ('c', 'd'), ('d', 'e')])
    floors = wave_profiles(graph, graph.buildings[0])
    assert [f['wave'] for f in floors] == [1, 2]
    assert floors[0]['sources'] == ('a', 'e')
    assert floors[0]['vertices'] == ('a', 'b', 'd', 'e')
    assert floors[0]['targets'] == ('b', 'd')
    assert floors[0]['internal_edges'] == 0
    assert floors[0]['external_edges'] == 2
    assert floors[1]['vertices'] == ('b', 'c', 'd')
    assert floors[1]['sources'] == ('b', 'd')
    assert floors[1]['removed'] == ('b', 'c', 'd')
    assert floors[1]['targets'] == ('c',)  # Upstream t = wave vertices minus fragment-0 sources.
    assert floors[1]['fragments'] == {0: ('b', 'd'), 1: ('c',)}
    assert floors[1]['internal_edges'] == 2
    assert floors[1]['external_edges'] == 0
    assert floors[1]['bottom'] == pytest.approx(floors[0]['height'])
    for floor in floors:
        a, b = floor['lower_radius'], floor['upper_radius']
        assert math.pi * floor['height'] * (a*a + a*b + b*b) / 3 == pytest.approx(math.log2(3))


@pytest.mark.parametrize('case', json.loads((Path(__file__).parent / 'fixtures/graph_cities/original.json').read_text())['cases'], ids=lambda case: case['name'])
def test_wave_map_statistics_match_original_formula_on_executable_output(case):
    from app.pipeline.original_layout import wave_profiles
    graph = decompose_graph([str(i) for i in range(case['vertex_count'])], [(str(u),str(v)) for u,v in case['edges']])
    for expected in case['wave_profiles']:
        building = next(b for b in graph.buildings if b.peel == expected['peel'] and set(b.vertices) == {str(v) for v in expected['vertices']})
        profiles = wave_profiles(graph, building)
        assert len(profiles) == len(expected['waves'])
        for profile in profiles:
            reference = expected['waves'][str(profile['wave'])]
            assert len(profile['sources']) == reference['s']
            assert len(profile['removed']) == reference['ss']
            assert len(profile['targets']) == reference['t']
            assert profile['internal_edges'] == reference['ie']
            assert profile['external_edges'] == reference['ee']
