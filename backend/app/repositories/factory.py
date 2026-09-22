from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..db import create_engine_from_settings, create_session_factory
from .json_city import JsonCityRepository
from .postgres_city import PostgresCityRepository
from .protocols import CityRepository


def get_city_repository(settings: Settings, processed_dir: Path) -> CityRepository:
    if settings.storage_backend == "postgres":
        engine = create_engine_from_settings(settings)
        return PostgresCityRepository(create_session_factory(engine))
    return JsonCityRepository(processed_dir)
