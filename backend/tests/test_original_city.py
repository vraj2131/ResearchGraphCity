import pytest
from sqlalchemy import select, func

from app.models import (CityRecord, CityPaperRecord, PaperRecord, PaperEdgeRecord,
                        BuildingRecord, FloorRecord, BuildingPaperRecord, DecompositionEdgeRecord)
from app.openalex_client import OpenAlexCancelled
from test_original_memberships import original_repository


def test_original_city_persists_fixed_points_shared_memberships_and_isolates(original_repository):
    from app.pipeline.original_city import build_original_city
    repository = original_repository
    city = repository.get_city_record('original')
    with repository.session_factory.begin() as session:
        session.add(PaperRecord(openalex_id='W5', title='Isolated paper', citation_count=0))
        session.flush()
        session.add(CityPaperRecord(city_id=city.id, openalex_id='W5', external_paper_id='P5'))
        session.flush()
        session.add(PaperEdgeRecord(city_id=city.id, source_openalex_id='W4', target_openalex_id='W5', edge_type='similarity', weight=0.9, directed=False))
    counts = build_original_city(city.id, repository)
    assert counts['buildings'] == 3
    assert counts['floors'] == 3
    with repository.session_factory() as session:
        assert session.get(CityRecord, city.id).algorithm_version == 'graph-cities-v1'
        buildings = session.scalars(select(BuildingRecord).order_by(BuildingRecord.external_id)).all()
        assert sorted((b.max_core, b.node_count, b.edge_count) for b in buildings) == [(0, 1, 0), (1, 3, 2), (3, 4, 6)]
        assert session.scalar(select(func.count()).select_from(DecompositionEdgeRecord)) == 8
        assert session.scalar(select(func.count()).select_from(BuildingPaperRecord)) == 8
        assert all(b.district_id is not None for b in buildings)
        assert all(b.quality_metrics['algorithm'] == 'graph-cities-v1' for b in buildings)
        floors = session.scalars(select(FloorRecord)).all()
        assert all(f.summary['geometry']['height'] > 0 for f in floors)
        before = [(b.id, b.external_id, b.x, b.z) for b in buildings]
    assert len(repository.get_paper('original', 'P1')['locations']) == 2
    assert build_original_city(city.id, repository) == counts
    with repository.session_factory() as session:
        buildings = session.scalars(select(BuildingRecord).order_by(BuildingRecord.external_id)).all()
        assert [(b.id, b.external_id, b.x, b.z) for b in buildings] == before


def test_cancellation_during_persistence_rolls_back_existing_city(original_repository, monkeypatch):
    import app.pipeline.original_city as pipeline
    repository = original_repository
    city = repository.get_city_record('original')
    original_copy = pipeline.copy_rows
    def interrupted(*args, **kwargs):
        original_copy(*args, **kwargs)
        raise OpenAlexCancelled('cancelled during persistence')
    monkeypatch.setattr(pipeline, 'copy_rows', interrupted)
    with pytest.raises(OpenAlexCancelled):
        pipeline.build_original_city(city.id, repository)
    assert len(repository.get_building_papers('original', 'high')) == 4
    assert len(repository.get_building_papers('original', 'low')) == 3


def test_cancelled_before_work_and_invalid_input_mode_leave_city_untouched(original_repository):
    from app.pipeline.original_city import build_original_city
    repository = original_repository
    city = repository.get_city_record('original')
    with pytest.raises(OpenAlexCancelled):
        build_original_city(city.id, repository, cancel_check=lambda: True)
    with repository.session_factory.begin() as session:
        session.get(CityRecord, city.id).configuration = {'graph_input': 'unknown'}
    with pytest.raises(ValueError, match='graph_input'):
        build_original_city(city.id, repository)
    assert len(repository.get_building_papers('original', 'high')) == 4


def test_floor_index_accepts_original_wave_counts_over_smallint(original_repository):
    with original_repository.session_factory.begin() as session:
        floor = session.scalar(select(FloorRecord).limit(1))
        floor.floor_index = 50_000
    with original_repository.session_factory() as session:
        assert session.scalar(select(func.max(FloorRecord.floor_index))) == 50_000


def test_cancellation_polling_is_bounded_and_commit_check_is_fresh(monkeypatch):
    import app.pipeline.original_city as pipeline
    now = [0.0]
    cancelled = [False]
    calls = []
    monkeypatch.setattr(pipeline, 'monotonic', lambda: now[0], raising=False)
    def poll():
        calls.append(now[0])
        return cancelled[0]
    check = pipeline._cancel_guard(poll)
    for _ in range(1000):
        check()
    assert len(calls) == 1
    now[0] = 0.3
    check()
    assert len(calls) == 2
    cancelled[0] = True
    with pytest.raises(OpenAlexCancelled):
        check(force=True)
