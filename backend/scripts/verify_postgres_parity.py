from __future__ import annotations

from pathlib import Path
import sys

import ijson
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_settings
from app.db import create_engine_from_settings, create_session_factory
from app.models import (
    BuildingRecord,
    BuildingRelationshipRecord,
    CityPaperRecord,
    CityRecord,
    DistrictRecord,
    FloorRecord,
    PaperEdgeRecord,
)
from app.storage import read_json


PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"


def json_array_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as source:
        return sum(1 for _ in ijson.items(source, "item"))


def first_json_id(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    with path.open("rb") as source:
        item = next(ijson.items(source, "item"), None)
    return str(item.get(key)) if item and item.get(key) is not None else None


def verify_city(prefix: str, session_factory) -> list[str]:
    expected = {
        "papers": json_array_count(PROCESSED_DIR / f"{prefix}_vertices.json"),
        "edges": json_array_count(PROCESSED_DIR / f"{prefix}_edges.json"),
        "buildings": len(read_json(PROCESSED_DIR / f"{prefix}_buildings.json", [])),
        "floors": len(read_json(PROCESSED_DIR / f"{prefix}_floors.json", [])),
        "bridges": len(read_json(PROCESSED_DIR / f"{prefix}_bridges.json", [])),
        "streets": len(read_json(PROCESSED_DIR / f"{prefix}_streets.json", [])),
        "communities": len(read_json(PROCESSED_DIR / f"{prefix}_communities.json", [])),
    }
    errors: list[str] = []
    with session_factory() as session:
        city = session.scalar(select(CityRecord).where(CityRecord.external_id == prefix))
        if city is None:
            return [f"{prefix}: city is missing from PostgreSQL"]
        actual = {
            "papers": session.scalar(select(func.count()).select_from(CityPaperRecord).where(CityPaperRecord.city_id == city.id)),
            "edges": session.scalar(select(func.count()).select_from(PaperEdgeRecord).where(PaperEdgeRecord.city_id == city.id)),
            "buildings": session.scalar(select(func.count()).select_from(BuildingRecord).where(BuildingRecord.city_id == city.id)),
            "floors": session.scalar(select(func.count()).select_from(FloorRecord).where(FloorRecord.city_id == city.id)),
            "bridges": session.scalar(
                select(func.count()).select_from(BuildingRelationshipRecord).where(
                    BuildingRelationshipRecord.city_id == city.id,
                    BuildingRelationshipRecord.relationship_kind == "bridge",
                )
            ),
            "streets": session.scalar(
                select(func.count()).select_from(BuildingRelationshipRecord).where(
                    BuildingRelationshipRecord.city_id == city.id,
                    BuildingRelationshipRecord.relationship_kind == "street",
                )
            ),
            "communities": session.scalar(select(func.count()).select_from(DistrictRecord).where(DistrictRecord.city_id == city.id)),
        }
        for collection, expected_count in expected.items():
            if actual[collection] != expected_count:
                errors.append(f"{prefix}.{collection}: JSON={expected_count}, PostgreSQL={actual[collection]}")

        samples = {
            "paper": (
                first_json_id(PROCESSED_DIR / f"{prefix}_vertices.json", "paper_id"),
                session.scalar(
                    select(CityPaperRecord.external_paper_id)
                    .where(CityPaperRecord.city_id == city.id)
                    .order_by(CityPaperRecord.external_paper_id)
                    .limit(1)
                ),
            ),
            "building": (
                first_json_id(PROCESSED_DIR / f"{prefix}_buildings.json", "building_id"),
                session.scalar(
                    select(BuildingRecord.external_id)
                    .where(BuildingRecord.city_id == city.id)
                    .order_by(BuildingRecord.external_id)
                    .limit(1)
                ),
            ),
        }
        for kind, (json_id, postgres_id) in samples.items():
            if json_id != postgres_id:
                errors.append(f"{prefix}.{kind} sample: JSON={json_id}, PostgreSQL={postgres_id}")

    print(f"{prefix}: " + ", ".join(f"{name}={count}" for name, count in expected.items()))
    return errors


def main() -> None:
    settings = load_settings()
    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(engine)
    errors = [error for prefix in ("research", "seeded") for error in verify_city(prefix, session_factory)]
    engine.dispose()
    if errors:
        print("Parity verification failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        raise SystemExit(1)
    print("JSON and PostgreSQL parity verified.")


if __name__ == "__main__":
    main()
