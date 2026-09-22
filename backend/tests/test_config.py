import os

from app.config import load_project_env, load_settings
from app.models import CityPaperRecord, PaperNeighborRecord


def test_load_project_env_reads_root_dotenv_without_overriding_existing_values(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("OPENALEX_API_KEY=from-file\nGROQ_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "from-process")
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)

    load_project_env(tmp_path)

    assert load_project_env(tmp_path) is True
    assert os.environ["OPENALEX_API_KEY"] == "from-file"
    assert os.environ["GROQ_API_KEY"] == "from-process"


def test_database_settings_have_safe_local_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("WORKER_POLL_SECONDS", raising=False)
    monkeypatch.delenv("JOB_STALE_SECONDS", raising=False)

    settings = load_settings(tmp_path)

    assert settings.storage_backend == "json"
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.worker_poll_seconds == 1.0
    assert settings.job_stale_seconds >= 60


def test_database_settings_reject_unknown_storage_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")

    try:
        load_settings(tmp_path)
    except ValueError as exc:
        assert "STORAGE_BACKEND" in str(exc)
    else:
        raise AssertionError("load_settings accepted an unsupported storage backend")


def test_fast_build_settings_have_bounded_defaults(tmp_path, monkeypatch):
    for name in (
        "GRAPH_WORKERS",
        "OPENALEX_WORKERS",
        "OPENALEX_MIN_INTERVAL_SECONDS",
        "OPENALEX_SNAPSHOT_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_settings(tmp_path)

    assert 1 <= settings.graph_workers <= 32
    assert 1 <= settings.openalex_workers <= 16
    assert settings.openalex_min_interval_seconds >= 0
    assert settings.openalex_snapshot_path is None


def test_fast_build_settings_reject_invalid_worker_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPH_WORKERS", "0")

    try:
        load_settings(tmp_path)
    except ValueError as exc:
        assert "GRAPH_WORKERS" in str(exc)
    else:
        raise AssertionError("load_settings accepted zero graph workers")


def test_neighbor_cache_primary_key_versions_algorithm_and_rank():
    columns = [column.name for column in PaperNeighborRecord.__table__.primary_key.columns]

    assert columns == ["model", "algorithm_version", "scope_key", "source_openalex_id"]
    assert PaperNeighborRecord.__table__.c.target_openalex_ids.type.item_type.python_type is str
    assert PaperNeighborRecord.__table__.c.similarities.type.item_type.python_type is float


def test_neighbor_cache_indexes_both_paper_foreign_keys():
    indexes = {index.name: [column.name for column in index.columns] for index in PaperNeighborRecord.__table__.indexes}

    assert indexes["ix_paper_neighbors_source_fk"] == ["source_openalex_id"]


def test_city_membership_indexes_paper_foreign_key_for_bulk_cleanup():
    indexes = {index.name: [column.name for column in index.columns] for index in CityPaperRecord.__table__.indexes}

    assert indexes["ix_city_papers_openalex_id"] == ["openalex_id"]
