"""Persist a self-contained original Graph Cities decomposition.

Semantic domains and evidence bridges are application overlays. They never
change the original edge partition or force papers into a single building.
"""
from collections import defaultdict
from datetime import datetime, timezone
import math
import uuid
from time import monotonic

from psycopg.types.json import Jsonb
from sqlalchemy import delete, select, text, update

from ..models import (BuildingRecord, BuildingRelationshipRecord, CityRecord,
                      CityPaperRecord, CommunityRunRecord, DistrictRecord,
                      FloorRecord, PaperRecord, PaperEdgeRecord, BuildingPaperRecord)
from ..openalex_client import OpenAlexCancelled
from ..graph_processing import semantic_domain_for_labels
from .bulk_io import copy_rows
from .city_structure import (_activation, _profile, _original_labels,
                             top_specific_labels, assign_unique_primary_labels,
                             _persist_relationships)
from .fixed_points import decompose_graph
from .original_layout import spiral_layout, street_pairs, wave_profiles

ALGORITHM = 'graph-cities-v1'


def _cancel_guard(cancel_check):
    last_poll = None
    def check(*, force=False):
        nonlocal last_poll
        now = monotonic()
        if cancel_check and (force or last_poll is None or now - last_poll >= 0.2):
            last_poll = now
            if cancel_check():
                raise OpenAlexCancelled('Graph Cities build cancelled')
        return False
    return check


def build_original_city(city_id, repository, *, cancel_check=None):
    # Long paths may have 50k waves. Check frequently in CPU loops, but avoid
    # turning each fragment into a database round trip to the job repository.
    check = _cancel_guard(cancel_check)

    check()
    with repository.session_factory() as session:
        city = session.get(CityRecord, city_id)
        mode = city.configuration.get('graph_input', 'citation')
        if mode not in {'citation', 'citation-plus-similarity'}:
            raise ValueError(f'Unsupported graph_input: {mode}')
        papers = session.scalars(select(PaperRecord).join(
            CityPaperRecord, CityPaperRecord.openalex_id == PaperRecord.openalex_id
        ).where(CityPaperRecord.city_id == city_id).order_by(PaperRecord.openalex_id)).all()
        edges = session.execute(select(
            PaperEdgeRecord.source_openalex_id, PaperEdgeRecord.target_openalex_id,
            PaperEdgeRecord.weight, PaperEdgeRecord.edge_type, PaperEdgeRecord.evidence,
        ).where(PaperEdgeRecord.city_id == city_id)).all()
    by_id = {p.openalex_id: p for p in papers}
    graph = decompose_graph(list(by_id), ((u, v) for u, v, _, kind, _ in edges
                                         if kind == 'citation' or mode == 'citation-plus-similarity'), check)
    prepared = []
    for index, component in enumerate(graph.buildings):
        check()
        profiles = wave_profiles(graph, component)
        prepared.append(dict(group_id=index, members=component.vertices, peel=component.peel,
                             edge_indices=component.edge_indices, floors=profiles, isolate=False))
    if graph.isolates:
        # An explicitly labeled application representation, not a fixed point.
        prepared.append(dict(group_id=len(prepared), members=graph.isolates, peel=0,
                             edge_indices=(), isolate=True, floors=[dict(
                                 wave=0, vertices=graph.isolates, removed=graph.isolates,
                                 sources=graph.isolates, targets=(), fragments={}, edge_indices=(),
                                 internal_edges=0, external_edges=0, lower_radius=1.0,
                                 upper_radius=1.0, bottom=0.0, height=1.0)]))
    descriptors = []
    memberships = defaultdict(list)
    for item in prepared:
        item['papers'] = [by_id[v] for v in item['members']]
        item['paper_by_id'] = {v: by_id[v] for v in item['members']}
        item['labels'] = top_specific_labels([label for p in item['papers']
                                             for label in [*p.topics, *p.keywords, *p.methods, *p.datasets]], 12)
        if item['isolate']:
            item['labels'] = ['Isolated papers', *item['labels']]
        item['domain'] = semantic_domain_for_labels(item['labels'])
        item['activation'] = _activation(item['papers'])
        for member in item['members']:
            memberships[member].append(item['group_id'])
        if not item['isolate']:
            descriptors.append(dict(id=item['group_id'], peel=item['peel'], node_count=len(item['members']),
                                    edge_count=len(item['edge_indices']), wave_count=len(item['floors']),
                                    max_wave_vertices=max(len(f['removed']) + len(f['targets']) for f in item['floors']),
                                    first_wave_sources=len(item['floors'][0]['sources'])))
    layout = {p['id']: p for p in spiral_layout(descriptors, len(papers))}
    for item, label in zip(prepared, assign_unique_primary_labels([p['labels'] for p in prepared])):
        item['labels'] = [label, *[v for v in item['labels'] if v != label]][:8]
        item['layout'] = layout.get(item['group_id'], dict(
            x=max((p['x'] + p['radius'] for p in layout.values()), default=0) + 4,
            z=0, radius=1, rotation_degrees=0, bucket=None))
    check(force=True)
    return _persist(city_id, repository, graph, prepared, memberships, edges, mode, check)


def _persist(city_id, repository, graph, prepared, memberships, edges, mode, check):
    def checked(rows):
        for index, row in enumerate(rows):
            if index % 4096 == 0:
                check()
            yield row

    with repository.session_factory.begin() as session:
        # Serialize rebuilds of the same city; commit all structure at once.
        city = session.scalar(select(CityRecord).where(CityRecord.id == city_id).with_for_update())
        check(force=True)
        session.execute(update(CityPaperRecord).where(CityPaperRecord.city_id == city_id).values(building_id=None, floor_id=None))
        for model in (CommunityRunRecord, BuildingRelationshipRecord, BuildingPaperRecord, FloorRecord, BuildingRecord, DistrictRecord):
            session.execute(delete(model).where(model.city_id == city_id))
        districts = {}
        for item in prepared:
            domain = item['domain']
            if domain['id'] not in districts:
                district = DistrictRecord(id=uuid.uuid5(city_id, f'district:{domain["id"]}'), city_id=city_id,
                                          external_id=f'D_{len(districts)+1:04d}', name=domain['name'],
                                          semantic_domain=domain['id'], semantic_domain_name=domain['name'],
                                          color=domain['color'], labels=[], metrics={}, x=0, z=0)
                districts[domain['id']] = district
                session.add(district)
        session.flush()
        building_by_group = {}
        floors = []
        building_members = []
        floor_members = []
        owned_edges = []
        primary = {}
        for index, item in enumerate(prepared, 1):
            check()
            external_id = f'B_{index:04d}'
            building_id = uuid.uuid5(city_id, external_id)
            layout = item['layout']
            size = len(item['members'])
            edge_count = len(item['edge_indices'])
            # Original per-wave radii, rather than a fabricated rectangular
            # footprint. The enclosing footprint supports existing camera APIs.
            radius = max(max(f['lower_radius'], f['upper_radius']) for f in item['floors'])
            building = BuildingRecord(
                id=building_id, city_id=city_id, district_id=districts[item['domain']['id']].id,
                external_id=external_id, node_count=size, edge_count=edge_count,
                internal_density=2*edge_count/(size*(size-1)) if size > 1 else 0,
                avg_core=float(item['peel']), max_core=item['peel'],
                height=sum(f['height'] for f in item['floors']), footprint=2*radius,
                x=layout['x'], z=layout['z'], top_labels=item['labels'],
                semantic_domain=item['domain']['id'], semantic_domain_name=item['domain']['name'],
                semantic_color=item['domain']['color'], profile=_profile(item['papers']),
                original_labels=_original_labels(item['papers']),
                activation={'score': item['activation'], 'formula_version': 'activation-v2'},
                activation_score=item['activation'], quality_metrics={
                    'algorithm': ALGORITHM, 'graph_input': mode, 'representation': 'isolates' if item['isolate'] else 'fixed_point',
                    'peel': item['peel'], 'wave_count': 0 if item['isolate'] else len(item['floors']),
                    'floor_count': len(item['floors']), 'bucket': layout['bucket'],
                    'rotation_degrees': layout['rotation_degrees'], 'spiral_radius': layout['radius'],
                })
            session.add(building)
            building_by_group[item['group_id']] = building
            location = {}
            for floor_index, profile in enumerate(item['floors'], 1):
                if floor_index % 256 == 1:
                    check()
                floor_id = uuid.uuid5(building_id, f'wave:{profile["wave"]}')
                floor_papers = [item['paper_by_id'][v] for v in profile['vertices']]
                years = [p.publication_year for p in floor_papers if p.publication_year is not None]
                geometry = {key: profile[key] for key in ('lower_radius', 'upper_radius', 'bottom', 'height')}
                summary = dict(algorithm=ALGORITHM, wave=profile['wave'], geometry=geometry,
                               source_count=len(profile['sources']), target_count=len(profile['targets']),
                               removed_count=len(profile['removed']), internal_edges=profile['internal_edges'],
                               external_edges=profile['external_edges'],
                               fragments={str(k): len(v) for k, v in profile['fragments'].items()})
                floors.append((floor_id, city_id, building_id, f'F_{index:04d}_{floor_index:05d}', floor_index,
                               item['peel'], item['peel'], len(profile['vertices']),
                               Jsonb(top_specific_labels([label for p in floor_papers for label in p.topics], 5)),
                               _activation(floor_papers), min(years, default=None), max(years, default=None), Jsonb(summary)))
                floor_members.extend((city_id, floor_id, v, building_id) for v in profile['vertices'])
                for vertex in profile['removed']:
                    location[vertex] = floor_id
                for edge_index in profile['edge_indices']:
                    u, v = graph.edges[edge_index]
                    owned_edges.append((city_id, u, v, building_id, floor_id, item['peel'],
                                        graph.waves[edge_index], graph.fragments[edge_index], graph.wave_components[edge_index]))
            for vertex in item['members']:
                building_members.append((city_id, building_id, vertex, location[vertex]))
                primary.setdefault(vertex, (building_id, location[vertex]))
        session.flush()
        connection = session.connection()
        copy_rows(connection, 'floors', ('id', 'city_id', 'building_id', 'external_id', 'floor_index', 'core_min', 'core_max',
                                        'node_count', 'top_labels', 'activation_score', 'year_min', 'year_max', 'summary'), checked(floors))
        copy_rows(connection, 'building_papers', ('city_id', 'building_id', 'openalex_id', 'floor_id'), checked(building_members))
        copy_rows(connection, 'floor_papers', ('city_id', 'floor_id', 'openalex_id', 'building_id'), checked(floor_members))
        copy_rows(connection, 'decomposition_edges', ('city_id', 'source_openalex_id', 'target_openalex_id', 'building_id',
                  'floor_id', 'peel', 'wave', 'fragment', 'wave_component'), checked(owned_edges))
        connection.execute(text('CREATE TEMP TABLE original_locations (openalex_id text PRIMARY KEY, building_id uuid, floor_id uuid) ON COMMIT DROP'))
        copy_rows(connection, 'original_locations', ('openalex_id', 'building_id', 'floor_id'), checked((v, *ids) for v, ids in primary.items()))
        connection.execute(text('UPDATE city_papers p SET building_id=l.building_id, floor_id=l.floor_id FROM original_locations l '
                                'WHERE p.city_id=:city AND p.openalex_id=l.openalex_id'), {'city': city_id})
        # Fresh bulk-loaded wave tables can have no planner statistics until
        # autovacuum runs. Publish usable query plans with the completed city.
        connection.execute(text('ANALYZE city_papers, floors, building_papers, floor_papers, decomposition_edges'))
        bridges, streets = _persist_relationships(session, city_id, prepared, {}, building_by_group, edges, memberships=memberships)
        fixed = [building_by_group[i['group_id']] for i in prepared if not i['isolate']]
        for sequence, (left, right) in enumerate(street_pairs([(b.x, b.z) for b in fixed]), 1):
            a, b = fixed[left], fixed[right]
            session.add(BuildingRelationshipRecord(city_id=city_id, external_id=f'GS_{sequence:05d}',
                        source_building_id=a.id, target_building_id=b.id, relationship_kind='street',
                        relationship_type='graph_city_geometry', score=0, distance=math.hypot(a.x-b.x, a.z-b.z),
                        components={'visual_only': True, 'algorithm': ALGORITHM}, evidence=[], activation_score=0))
            streets += 1
        for domain, district in districts.items():
            items = [p for p in prepared if p['domain']['id'] == domain]
            district.labels = top_specific_labels([v for p in items for v in p['labels']], 8)
            district.metrics = {'building_count': len(items), 'paper_count': len({v for p in items for v in p['members']}), 'application_overlay': True}
            district.x = sum(p['layout']['x'] for p in items)/len(items)
            district.z = sum(p['layout']['z'] for p in items)/len(items)
        counts = dict(buildings=len(prepared), floors=len(floors), districts=len(districts), bridges=bridges, streets=streets)
        city.algorithm_version = ALGORITHM
        city.configuration = {**city.configuration, 'graph_input': mode}
        city.building_count = counts['buildings']
        city.district_count = counts['districts']
        city.status = 'ready'
        city.completed_at = datetime.now(timezone.utc)
        session.add(CommunityRunRecord(city_id=city_id, algorithm=ALGORITHM, random_seed=0,
                                      parameters={'graph_input': mode}, metrics=counts, completed_at=city.completed_at))
        check(force=True)
    return counts
